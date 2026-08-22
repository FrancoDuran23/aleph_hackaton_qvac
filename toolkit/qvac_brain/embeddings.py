"""Embeddings con QVAC. Reemplazo drop-in de `toolkit.hybrid_rag.embeddings`.

Expone la interfaz (`embed`, `dim`) que espera el pipeline, así que
`ingest.py`, `db.py` y `retrieval.py` no necesitan cambios: alcanza con
cambiar el import.

La dimensión no se hardcodea — se detecta en
la primera llamada y se reusa. GTE Large devuelve 1024, pero si cambiás
QVAC_EMBED_MODEL el número cambia y `db.py` arma el VECTOR(N) correcto solo.
"""
import os

from .cliente import pedir

EMBEDDING_MODEL = os.getenv("QVAC_EMBED_MODEL", "EMBEDDINGGEMMA_300M_Q4_0")

_dim_cache: int | None = None


def embed(text: str) -> list[float]:
    """Devuelve el embedding de un texto."""
    global _dim_cache
    datos = pedir("/v1/embeddings", {"text": text, "model": EMBEDDING_MODEL})
    valores = datos["embeddings"][0]
    if _dim_cache is None:
        _dim_cache = len(valores)
    return valores


def embed_lote(textos: list[str]) -> list[list[float]]:
    """Embeddings de varios textos en una sola llamada.

    La ingesta manda cientos de chunks; agruparlos evita pagar un round-trip
    HTTP por chunk. Antes no existía porque cada llamada salía
    a internet igual — acá el bridge es local y el batch sí rinde.
    """
    global _dim_cache
    if not textos:
        return []
    datos = pedir("/v1/embeddings", {"texts": textos, "model": EMBEDDING_MODEL})
    vectores = datos["embeddings"]
    if _dim_cache is None and vectores:
        _dim_cache = len(vectores[0])
    return vectores


def dim() -> int:
    """Dimensión del embedding. Si todavía no se llamó a embed(), hace una
    llamada de prueba para detectarla."""
    if _dim_cache is None:
        embed("deteccion de dimension")
    return _dim_cache
