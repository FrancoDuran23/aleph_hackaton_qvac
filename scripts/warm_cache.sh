#!/usr/bin/env bash
# Precalienta las respuestas de demo/preguntas.json contra el pipeline
# real (necesita red + la ingesta ya hecha). Correr antes del pitch.
set -euo pipefail
docker compose exec app python -m app.precache
