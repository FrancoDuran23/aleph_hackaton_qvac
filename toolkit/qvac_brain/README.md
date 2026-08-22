# qvac_brain — generación y embeddings locales

Toda la inferencia del pipeline: generación de texto y embeddings, sobre un
modelo QVAC. No sale a la red.

```
app/answer.py                 → llamar_llm_sync   (respuesta final)
hybrid_rag/multihop.py        → llamar_llm_sync   (descomposición de consultas)
hybrid_rag/multihop.py        → embed             (búsqueda vectorial)
hybrid_rag/ingest.py          → embed, dim        (indexado)
```

## API

```python
from toolkit import qvac_brain

qvac_brain.salud()                      # {'ok': True, 'llm': ..., 'cargados': [...]}

texto, tok_in, tok_out = qvac_brain.llamar_llm_sync(
    messages=[{"role": "user", "content": "hola"}],
    system="Sos conciso.",
    max_tokens=200,
)

vector   = qvac_brain.embed("un texto")           # list[float]
vectores = qvac_brain.embed_lote(["uno", "dos"])  # list[list[float]] — 1 sola request
n        = qvac_brain.dim()                       # dimensión del modelo activo
```

`embed_lote` manda cientos de chunks en una request en lugar de un round-trip
por chunk. Importa en la ingesta.

## Parámetros de generación

`_armar_payload` manda siempre `generation_params`:

```python
PARAMS_DEFAULT = {"temp": 0.0, "top_p": 1.0, "reasoning_budget": 0}
```

⚠️ **Los dos valores están ahí por un motivo medido, no por gusto.**

`temp: 0.0` — sin esto el modelo corre con sampling por defecto y la misma
pregunta devuelve respuestas distintas. No falla, no avisa: simplemente ninguna
medición es reproducible. El nombre del campo es `temp`, **no** `temperature`;
una clave desconocida se descarta en silencio.

`reasoning_budget: 0` — Qwen3 es un modelo de razonamiento y emite un bloque
`<think>` antes de responder. Medido: la misma respuesta cuesta 58 tokens con
razonamiento y 9 sin él. Con `max_tokens` bajo el efecto es peor que lento —
el modelo agota el presupuesto pensando y devuelve texto **vacío** con
`stop_reason: "length"`.

Se puede pisar por llamada pasando `generation_params`.

## Cambiar el modelo de embeddings invalida el índice

**Es la trampa que más caro sale.** Dos modelos de embeddings producen espacios
vectoriales distintos: un vector viejo y uno nuevo no son comparables aunque
tengan el mismo largo. Si no reindexás, la búsqueda no falla con un error
prolijo — devuelve resultados sin sentido, que en una demo es mucho peor.

```bash
./scripts/ingest.sh    # reindexa todo de cero
```

`db.py` arma la columna `VECTOR(N)` a partir de `dim()`, así que se adapta solo
al nuevo tamaño.

Dato útil: pgvector solo soporta índices HNSW hasta 2000 dimensiones. Por
encima de eso el índice no se puede crear y la búsqueda cae a scan secuencial.

## Configuración

```bash
QVAC_LLM_MODEL=QWEN3_1_7B_INST_Q4
QVAC_EMBED_MODEL=EMBEDDINGGEMMA_300M_Q4_0
```

Los nombres son constantes del SDK de QVAC. Un nombre que no existe devuelve
400 con la lista completa de constantes disponibles.

## Lo que no está implementado

**Tool use.** El SDK de QVAC soporta `tools` en `completion()`, pero el
transporte todavía no lo expone. Si algún camino lo necesita, hay que agregarlo.

## Checklist

- [ ] `python scripts/qvac/smoke_test.py` pasa
- [ ] Corrí `./scripts/ingest.sh` si cambié el modelo de embeddings
- [ ] Puse `EMBEDDING_DIM` en el `.env` con el valor que imprimió el smoke test
- [ ] Probé una pregunta en `http://localhost:8000` y la respuesta tiene sentido
