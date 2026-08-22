"""Inferencia local con QVAC, vía el endpoint HTTP de `QVAC_BRIDGE_URL`.

Generación y embeddings locales sobre QVAC
sin cambiar sus firmas. Ver README.md en esta carpeta.
"""
from .brain import (
    RESPUESTA_FALLBACK,
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
    "llamar_llm",
    "llamar_llm_sync",
    "salud",
]
