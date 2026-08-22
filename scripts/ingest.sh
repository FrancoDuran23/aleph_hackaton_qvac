#!/usr/bin/env bash
# Ingesta los PDFs de data/pdfs/ al índice pgvector. Correr después de
# levantar docker-compose y de haber puesto los PDFs en esa carpeta.
set -euo pipefail
docker compose exec app python -m toolkit.hybrid_rag.ingest "${1:-data/pdfs}"
