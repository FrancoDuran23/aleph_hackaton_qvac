# hybrid_rag

Ingesta de una carpeta de PDFs a pgvector + búsqueda híbrida (vector +
léxica, fusionadas con RRF) + multihop (unas pocas sub-búsquedas
adicionales por sub-consulta, generadas por LLM).

El trozado es una ventana deslizante genérica, no por estructura del
documento: el dominio de los PDFs no se sabe hasta el día del hackathon.

Las sub-consultas del multihop las decide el LLM según la pregunta, sin
facetas fijas ni supuestos de dominio.

Toda la inferencia — embeddings, descomposición y respuesta — corre sobre un
modelo QVAC local vía `qvac_brain`. **Cero proveedores externos, cero API
keys.** Sin rerank: es un cross-encoder opcional y no hace falta para un
corpus chico.

## Cómo funciona una búsqueda

```
pregunta del usuario
   │
   ├─► embed(pregunta) ─► buscar_hibrido() ── RRF(vector + tsvector) ──► pool base
   │
   └─► descomponer_pregunta(pregunta)   [QVAC local → passthrough]
          │
          ├─► sub-consulta 1 ─► embed ─► buscar_vectorial() ─┐
          ├─► sub-consulta 2 ─► embed ─► buscar_vectorial() ─┼─► unidos al pool (sin duplicados)
          └─► sub-consulta 3 ─► embed ─► buscar_vectorial() ─┘
```

No es un loop iterativo ("buscar, evaluar si alcanza, reformular, volver a
buscar") — son como máximo `MAX_HOPS=3` sub-consultas generadas **una
sola vez**, cada una busca en paralelo conceptual (no hay dependencia
entre hops), y todo se une en un solo pool. Esto
suma cobertura para vocabulario que la pregunta original no menciona, no
reemplaza ni reordena la búsqueda base.

## Qué hay en cada archivo

- `embeddings.py` — `embed(texto) -> list[float]`, `dim() -> int` (detecta
  la dimensión real del modelo en la primera llamada, no la hardcodea).
- `db.py` — conexión a Postgres + `inicializar_esquema()` (crea la
  extensión `vector`, la tabla `chunks` con columna `VECTOR(N)` +
  `TSVECTOR` generada, índices HNSW y GIN) + `reemplazar_chunks()`
  (idempotente, borra todo e inserta de cero).
- `ingest.py` — `ingestar_carpeta(carpeta)`: PDF → texto (pypdf) → trozos
  (ventana deslizante, 1000 chars, 150 de superposición) → embeddings →
  pgvector. Correr con `python -m toolkit.hybrid_rag.ingest [carpeta]`.
- `retrieval.py` — `buscar_hibrido(texto, vector, top_k)` (RRF vector+FTS,
  una sola query SQL) y `buscar_vectorial(vector, top_k)` (solo vector,
  usado por los hops).
- `multihop.py` — `descomponer_pregunta(pregunta) -> list[str]` y
  `buscar_multihop(pregunta) -> list[Chunk]`, que orquesta todo el
  diagrama de arriba.

## Env vars

- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY` (fallback de la descomposición)
- `DATABASE_URL`

## Cómo reusarlo rápido en el próximo hackathon

```python
from toolkit.hybrid_rag.multihop import buscar_multihop

chunks = buscar_multihop("¿qué dice el documento sobre X?")
contexto = "\n\n".join(f"[{c.fuente}] {c.contenido}" for c in chunks)
# ... pasarle `contexto` a qvac_brain.llamar_llm como parte del system/user prompt
```

Si el hackathon NO necesita multihop (corpus chico, preguntas simples),
usar directo `retrieval.buscar_hibrido()` y ahorrarse las llamadas extra
de descomposición — es más rápido y más barato.

## Qué quedó afuera a propósito
- Voyage AI, Cohere rerank, Supabase Storage — dependencias de producción
  que no valen la pena para un corpus de PDFs cargados a mano.
- El parseo estructurado de la pregunta en campos tipados (`ParsedQuery`
  con `must_have_skills`, `seniority_band`, etc.) — específico de
  matchear CVs contra vacantes. Acá `descomponer_pregunta` no tipa nada,
  solo pide sub-consultas de texto libre.
- El cross-encoder rerank de Cohere y la verificación post-hoc con Claude
  Vision (`verify-negatives.ts`) — hardening de producción, no aporta al
  demo de un hackathon.
- El caché de embeddings en tabla aparte (`embedding_cache.sql`) — con un
  corpus chico no hace falta, pero si el hackathon reingesta muy seguido
  los mismos PDFs, es la primera optimización a copiar de ahí.
