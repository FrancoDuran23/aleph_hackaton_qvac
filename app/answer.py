"""Punto único de respuesta: lo usan tanto el webhook de WhatsApp como el
chat web, así la lógica de "cómo se responde una pregunta" vive en un solo
lugar en vez de duplicarse entre los dos canales.
"""
import sys

from toolkit.claude_brain import brain
from toolkit.hybrid_rag.multihop import buscar_multihop

from . import precache

SYSTEM_PROMPT = """Respondés preguntas usando ÚNICAMENTE la información de los
documentos que te paso a continuación como contexto. Si la respuesta no
está en el contexto, decilo explícitamente en vez de inventar. Citá de qué
documento (fuente) sacaste cada afirmación importante.

Contexto:
{contexto}"""


def _formatear_contexto(chunks) -> str:
    if not chunks:
        return "(no se encontró contexto relevante en los documentos cargados)"
    return "\n\n".join(f"[{c.fuente}] {c.contenido}" for c in chunks)


def responder(pregunta: str, historial: list[dict], usar_cache: bool = True) -> str:
    """historial: lista de {"role": "user"|"assistant", "content": str}, sin
    incluir la pregunta actual (se agrega acá adentro)."""
    if usar_cache:
        cacheada = precache.buscar_en_cache(pregunta)
        if cacheada is not None:
            return cacheada

    try:
        contexto = _formatear_contexto(buscar_multihop(pregunta))
    except Exception as e:
        # Si Gemini/Postgres están caídos y la pregunta no estaba
        # precalentada, mejor responder honestamente sin contexto que
        # devolver un 500 crudo en medio de la demo.
        print(f"aviso: búsqueda en documentos falló ({e}), respondo sin contexto recuperado", file=sys.stderr)
        contexto = "(no se pudo buscar en los documentos en este momento -- problema de red o de la base de datos)"

    system = SYSTEM_PROMPT.format(contexto=contexto)

    messages = [*historial, {"role": "user", "content": pregunta}]
    texto, _in_tok, _out_tok = brain.llamar_claude_sync(
        messages=messages,
        system=system,
        modelo="claude-sonnet-4-6",
    )
    return texto
