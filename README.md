# hackaton

Repo base para hackathons: bot de WhatsApp + chat web que responden
preguntas sobre una carpeta de PDFs que vos cargás, con retrieval híbrido
+ multihop sobre pgvector, y un cache de respuestas precalentadas para no
depender de la red durante el pitch.

**Cero datos de dominio acá adentro.** `data/pdfs/` y `demo/preguntas.json`
están vacíos/gitignoreados a propósito — los llenás vos el día del evento.

## Arrancar en 5 minutos

1. **Variables de entorno**:
   ```bash
   cp .env.example .env
   ```
   Completá `ANTHROPIC_API_KEY` y `GEMINI_API_KEY`. `WASENDER_API_TOKEN` /
   `WASENDER_SESSION_ID` solo si vas a probar WhatsApp real (ver más abajo).

2. **Levantar todo**:
   ```bash
   docker compose up --build
   ```
   Esto levanta Postgres con pgvector + la app FastAPI en un solo comando.
   Esperá a que el log diga `Uvicorn running on http://0.0.0.0:8000`.

3. **Cargar tus PDFs**: poné los archivos en `data/pdfs/`, después:
   ```bash
   ./scripts/ingest.sh
   ```
   (o `docker compose exec app python -m toolkit.hybrid_rag.ingest` a mano).
   Podés correrlo de nuevo cuantas veces quieras — cada corrida reindexa
   todo de cero, no hay que borrar nada a mano.

4. **Probar el chat**: abrí `http://localhost:8000` en el navegador.

Listo — desde acá, lo único que falta es lógica de dominio.

## Antes del pitch: precalentar respuestas

Si vas a mostrar un recorrido de preguntas específico frente al jurado,
no dependas de que la red/API estén bien en el momento:

1. Completá `demo/preguntas.json` (copiá `demo/preguntas.example.json`
   como punto de partida) con las preguntas exactas que vas a hacer.
2. Corré `./scripts/warm_cache.sh` — esto ejecuta el pipeline real una vez
   por pregunta (necesita red) y guarda las respuestas en
   `demo/cache_calentado.json`.
3. Durante la demo, cualquier pregunta que matchee (exacta o parecida) con
   una precalentada responde al instante desde ese archivo, sin tocar la
   red ni la base de datos. Si algo se cae en el medio del pitch, el
   recorrido ensayado sigue funcionando igual.

Preguntas fuera del recorrido siguen yendo por el camino normal
(retrieval + LLM en vivo).

## Estructura del repo

```
toolkit/            piezas reusables, documentadas, extraídas de proyectos
                     que ya funcionan (ver toolkit/README.md)
  claude_brain/      wrapper de Anthropic con retry + caching + tool-use
  whatsapp_wasender/ cliente de WASenderApi
  hybrid_rag/        ingesta de PDFs + búsqueda híbrida RRF + multihop

app/                 la app de este hackathon puntual, arma las piezas del
                     toolkit para responder por WhatsApp y por web
  main.py            rutas FastAPI: /webhook, /chat, /, /health
  answer.py          responder(pregunta, historial) -- un solo lugar,
                     lo usan tanto el webhook como el chat
  precache.py        cache de respuestas precalentadas para el pitch
  static/            UI de chat (HTML/CSS/JS sin build step)

data/pdfs/           tus PDFs van acá (vacío en el repo)
demo/                preguntas del recorrido + cache calentado (vacío en el repo)
scripts/             atajos de docker compose exec
```

## Dónde escribir tu lógica de dominio

- **Cambiar cómo se arma la respuesta**: `app/answer.py` — ahí está el
  system prompt y qué se le pasa a Claude.
- **Cambiar qué se busca**: `toolkit/hybrid_rag/multihop.py` y
  `retrieval.py` si necesitás filtros o ranking distinto.
- **Agregar tools de Claude** (acciones, no solo respuestas): usá
  `toolkit/claude_brain/brain.py:llamar_claude_con_tools` — ya tiene el
  loop armado, solo hace falta definir el schema de la tool y un
  dispatcher.

## WhatsApp: la letra chica

WASenderApi necesita pegarle a tu webhook por una URL pública — en
`localhost` no le llega nada. Para probarlo en el hackathon:

```bash
ngrok http 8000
```

y configurá esa URL (`https://....ngrok.../webhook`) como webhook en el
dashboard de WASenderApi. **Para la demo frente al jurado, usá la pantalla
de chat web** (`http://localhost:8000`) — no depende de ngrok ni de que
WASenderApi esté funcionando ese día. WhatsApp queda como plus si sobra
tiempo de armar el túnel.

## Troubleshooting rápido

- **`docker compose up` no arranca / el healthcheck de postgres no pasa**:
  `docker compose logs postgres` — normalmente es un volumen viejo con
  datos de otra corrida. `docker compose down -v` y volver a levantar (esto
  borra los datos indexados, hay que reingestar).
- **`/chat` tarda mucho o tira error de Gemini/Anthropic**: revisá que
  `GEMINI_API_KEY` y `ANTHROPIC_API_KEY` estén bien en `.env`, y que
  `docker compose up` haya sido levantado *después* de crear `.env` (si lo
  creaste con los contenedores ya corriendo, hacé `docker compose restart app`).
- **El chat responde "no se encontró contexto relevante"**: todavía no
  corriste `./scripts/ingest.sh`, o los PDFs no tenían texto extraíble
  (escaneados sin OCR, por ejemplo).
