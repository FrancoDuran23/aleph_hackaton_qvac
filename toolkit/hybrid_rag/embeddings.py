"""Embeddings con Gemini. Llamada extraída de D:\\AIRgent\\legal_rag.py y
legal_corpus_ingestor.py — el mismo `embed_content` que ya funciona ahí.

No se fuerza una dimensión de salida por parámetro: distintos modelos de
Gemini devuelven distinto default y adivinar el parámetro correcto rompe
en runtime si no coincide con la versión del SDK instalada. En cambio, la
dimensión real se detecta en la primera llamada y se reusa desde ahí
(ver dim()). db.py arma la columna VECTOR(N) con ese número.
"""
import os

from google import genai

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

_client = None
_dim_cache: int | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


def embed(text: str) -> list[float]:
    """Devuelve el embedding de un texto."""
    global _dim_cache
    response = _get_client().models.embed_content(model=EMBEDDING_MODEL, contents=text)
    values = list(response.embeddings[0].values)
    if _dim_cache is None:
        _dim_cache = len(values)
    return values


def dim() -> int:
    """Dimensión del embedding. Si todavía no se llamó a embed(), hace una
    llamada de prueba para detectarla."""
    if _dim_cache is None:
        embed("deteccion de dimension")
    return _dim_cache
