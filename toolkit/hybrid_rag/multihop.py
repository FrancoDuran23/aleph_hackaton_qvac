"""Multihop retrieval: además del pase híbrido base, descompone la pregunta
en unas pocas sub-consultas y las busca por separado, sumando resultados
nuevos al pool sin pisar el resultado base.

Algoritmo (no la implementación línea por línea) extraído de
D:\\talentbase\\src\\lib\\match\\query-decomposer.ts +
D:\\talentbase\\src\\lib\\match\\run-match.ts (bloque "4.2 multi-hop retrieval").
Ahí estaba armado para matchear candidatos contra vacantes con 3 facetas
fijas de RRHH (skills / seniority_domain / location_language). Acá se
generaliza: como el dominio de los PDFs no se conoce hasta el día del
hackathon, es el LLM el que decide las sub-consultas en vez de usar
facetas hardcodeadas.

Mismo diseño de fondo que el original: esto NO es un loop "buscar ->
evaluar si alcanza -> reformular -> buscar de nuevo" (talentbase también
aclara que no tiene ese "Sufficient Context Agent"). Son hasta MAX_HOPS
sub-consultas generadas una sola vez, cada una busca de forma
independiente por similitud vectorial, y todo se une en un pool sin
volver a fusionar con RRF. Aporta cobertura para vocabulario que la
pregunta original no menciona; no reemplaza la búsqueda base.
"""
import json
import re
import sys

from google import genai

from ..claude_brain import brain
from . import retrieval
from .embeddings import embed

MAX_HOPS = 3
TOP_K_POR_HOP = 5

_DECOMPOSE_PROMPT = """Te paso una pregunta de un usuario sobre un conjunto de documentos.
Generá hasta {max_hops} sub-consultas de búsqueda que cubran distintos
ángulos de esa pregunta (sinónimos, términos relacionados, aspectos que la
pregunta no menciona explícitamente pero que ayudarían a encontrar
información relevante). Cada sub-consulta tiene que ser un texto de
búsqueda corto, no una pregunta.

Devolvé SOLO un JSON con este formato, sin texto alrededor:
{{"sub_consultas": ["...", "...", "..."]}}

Pregunta: {pregunta}"""


def _parsear_json_sub_consultas(texto: str) -> list[str]:
    match = re.search(r"\{[\s\S]*\}", texto)
    if not match:
        raise ValueError("no se encontró un bloque JSON en la respuesta")
    data = json.loads(match.group(0))
    sub_consultas = data.get("sub_consultas", [])
    if not isinstance(sub_consultas, list) or not sub_consultas:
        raise ValueError("sub_consultas vacío o con formato inesperado")
    return [str(s) for s in sub_consultas[:MAX_HOPS]]


def descomponer_pregunta(pregunta: str) -> list[str]:
    """Gemini Flash primero, Claude Haiku si falla, passthrough (la pregunta
    tal cual, sin descomponer) si fallan los dos. Mismo orden de fallback
    que query-decomposer.ts en talentbase."""
    prompt = _DECOMPOSE_PROMPT.format(max_hops=MAX_HOPS, pregunta=pregunta)

    try:
        client = genai.Client()
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return _parsear_json_sub_consultas(response.text)
    except Exception as e:
        print(f"aviso: descomposición con Gemini falló ({e}), pruebo con Claude Haiku", file=sys.stderr)

    try:
        texto, _, _ = brain.llamar_claude_sync(
            messages=[{"role": "user", "content": prompt}],
            system="Respondés únicamente con el JSON pedido, sin explicaciones.",
            modelo="claude-haiku-4-5-20251001",
        )
        return _parsear_json_sub_consultas(texto)
    except Exception as e:
        print(f"aviso: descomposición con Claude también falló ({e}), sigo sin multihop (passthrough)", file=sys.stderr)

    return [pregunta]


def buscar_multihop(pregunta: str, top_k_base: int = 8) -> list[retrieval.Chunk]:
    """Búsqueda base (híbrida RRF) + hasta MAX_HOPS búsquedas vectoriales
    adicionales por sub-consulta, unidas sin duplicados."""
    vec_base = embed(pregunta)
    pool = retrieval.buscar_hibrido(pregunta, vec_base, top_k=top_k_base)
    vistos = {c.id for c in pool}

    for sub_consulta in descomponer_pregunta(pregunta):
        vec_hop = embed(sub_consulta)
        for chunk in retrieval.buscar_vectorial(vec_hop, top_k=TOP_K_POR_HOP):
            if chunk.id not in vistos:
                vistos.add(chunk.id)
                pool.append(chunk)

    return pool
