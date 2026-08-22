# qvac_brain — inferencia local en lugar de Anthropic y Gemini

Reemplaza las dos dependencias de red del pipeline (`claude_brain` para
generación, `hybrid_rag.embeddings` para embeddings) por un modelo local
servido por el bridge de QVAC. Las firmas son las mismas, así que migrar es
cambiar imports — no reescribir lógica.

Requiere el bridge andando. Si todavía no lo levantaste, empezá por
[`scripts/qvac/README.md`](../../scripts/qvac/README.md).

## Quick path

Tres imports. Nada más.

```python
# app/answer.py:7
- from toolkit.claude_brain import brain
+ from toolkit import qvac_brain as brain

# toolkit/hybrid_rag/multihop.py:28
- from ..claude_brain import brain
+ from .. import qvac_brain as brain

# toolkit/hybrid_rag/multihop.py:30  y  toolkit/hybrid_rag/ingest.py:21
- from .embeddings import embed          # ingest.py importa además: dim
+ from ..qvac_brain.embeddings import embed
```

Después **reindexá**, que no es opcional — ver la advertencia de abajo:

```bash
./scripts/ingest.sh
```

## La advertencia que importa

**Cambiar de modelo de embeddings invalida todo lo que ya está indexado.**

Gemini devuelve 3072 dimensiones; GTE Large devuelve 1024. Son espacios
vectoriales distintos: un vector viejo y uno nuevo no son comparables aunque
tuvieran el mismo largo. Si no reindexás, la búsqueda no falla con un error
prolijo — devuelve resultados sin sentido, que es mucho peor durante una demo.

`ingest.sh` reindexa todo de cero en cada corrida, así que alcanza con
correrlo. `db.py` arma la columna `VECTOR(N)` a partir de `dim()`, o sea que
se adapta solo al nuevo tamaño.

Efecto secundario bueno: pgvector sólo soporta índices HNSW hasta 2000
dimensiones. Con Gemini en 3072 el índice no se podía crear y la búsqueda iba
por scan secuencial; con 1024 el HNSW entra y la recuperación mejora.

## Qué se mantiene y qué cambia

| Aspecto | `claude_brain` | `qvac_brain` |
|---|---|---|
| Firma de `llamar_claude_sync` | `(messages, system, modelo, max_retries, prefill)` | idéntica, más `max_tokens` opcional |
| Retorno | `(texto, input_tokens, output_tokens)` | idéntico |
| `RESPUESTA_FALLBACK` ante fallo | sí | sí |
| Retry con backoff exponencial | sí | sí |
| Prompt caching | sí | no aplica — no hay API que facturar |
| Tool use (`llamar_claude_con_tools`) | sí | **no implementado** |
| `modelo="claude-sonnet-4-6"` | nativo | se mapea al modelo local con un aviso |
| Versión async | declarada `async`, pero bloquea el event loop | async de verdad, con `httpx.AsyncClient` |

Los alias `llamar_claude` y `llamar_claude_sync` existen para que el swap sea
sólo el import. Los nombres reales son `llamar_llm` y `llamar_llm_sync`: acá
no hay Claude.

## Lo que queda sin cubrir

Migrar estos tres imports **no** deja la app 100% offline. Falta:

| Dónde | Qué sigue saliendo a la red | Nota |
|---|---|---|
| `multihop.py:65-67` | Llama a `genai` directo para descomponer la consulta | Su fallback ya es `brain`, así que al migrar el import el fallback pasa a ser local. El camino feliz sigue siendo Gemini hasta que lo cambies. |
| `claude_brain.llamar_claude_con_tools` | Sin equivalente en `qvac_brain` | El SDK de QVAC soporta `tools` en `completion()`; el bridge todavía no lo expone. |

Si el objetivo es una demo sin red, esos dos puntos hay que cerrarlos.

## Configuración

En tu `.env` local:

```bash
QVAC_BRIDGE_URL=http://127.0.0.1:8081
QVAC_BRIDGE_TOKEN=<el que imprimió provision.sh>
QVAC_LLM_MODEL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
QVAC_EMBED_MODEL=GTE_LARGE_FP16
QVAC_BRIDGE_TIMEOUT=600
```

`QVAC_BRIDGE_TIMEOUT` es alto a propósito: en CPU una respuesta larga tarda
decenas de segundos. La conexión tiene su propio timeout de 5s, así que "el
bridge no está" falla rápido y "el modelo está pensando" no.

## API

```python
from toolkit import qvac_brain

qvac_brain.salud()                      # {'ok': True, 'llm': ..., 'cargados': [...]}

texto, tok_in, tok_out = qvac_brain.llamar_llm_sync(
    messages=[{"role": "user", "content": "hola"}],
    system="Sos conciso.",
    max_tokens=200,
)

vector  = qvac_brain.embed("un texto")            # list[float]
vectores = qvac_brain.embed_lote(["uno", "dos"])  # list[list[float]] — 1 sola request
n = qvac_brain.dim()                              # 1024 con GTE Large
```

`embed_lote` no existe en la versión Gemini. Es útil en la ingesta: cientos de
chunks en una request en lugar de un round-trip por chunk.

## Checklist

- [ ] El bridge responde (`python scripts/qvac/smoke_test.py` pasa)
- [ ] Cambié los tres imports
- [ ] Corrí `./scripts/ingest.sh` para reindexar con la nueva dimensión
- [ ] Probé una pregunta en `http://localhost:8000` y la respuesta tiene sentido
- [ ] Decidí qué hacer con la llamada a Gemini de `multihop.py:65`
