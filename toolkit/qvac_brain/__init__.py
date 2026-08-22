"""Inferencia local con QVAC, vía el bridge HTTP de `scripts/qvac/`.

Reemplaza a `claude_brain` (generación) y a `hybrid_rag.embeddings` (embeddings)
sin cambiar sus firmas. Ver README.md en esta carpeta.
"""
from .brain import (
    RESPUESTA_FALLBACK,
    llamar_claude,
    llamar_claude_sync,
    llamar_llm,
    llamar_llm_sync,
)
from .cliente import QvacBridgeError, salud
from .embeddings import dim, embed, embed_lote

__all__ = [
    "RESPUESTA_FALLBACK",
    "QvacBridgeError",
    "dim",
    "embed",
    "embed_lote",
    "llamar_claude",
    "llamar_claude_sync",
    "llamar_llm",
    "llamar_llm_sync",
    "salud",
]
