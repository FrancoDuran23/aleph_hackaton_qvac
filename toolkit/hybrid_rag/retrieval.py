"""Retrieval híbrido: fusión RRF de búsqueda vectorial (pgvector, coseno) y
léxica (tsvector nativo de Postgres).

Mismo algoritmo de fusión que usa D:\\talentbase\\src\\lib\\match\\run-match.ts
(el paso "4. Hybrid retrieval") -- ahí armaban esta CTE con Drizzle; acá es
la misma CTE escrita directo con psycopg, sin ORM.

A diferencia de AIRgent (Chroma + un índice BM25 aparte en un .pkl), acá
todo vive en una sola tabla de Postgres: menos piezas móviles, y es lo que
ya vas a tener levantado con docker-compose de cualquier forma.
"""
from dataclasses import dataclass

from . import db

RRF_K = 60
POR_BRAZO = 50  # cuántos candidatos trae cada pierna (vectorial/léxica) antes de fusionar


@dataclass
class Chunk:
    id: str
    doc_id: str
    contenido: str
    fuente: str
    score: float = 0.0


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def buscar_hibrido(query_texto: str, query_vec: list[float], top_k: int = 8) -> list[Chunk]:
    """Búsqueda base: fusiona un pase vectorial + uno léxico con RRF."""
    sql = """
        WITH v AS (
            SELECT id, row_number() OVER (ORDER BY embedding <=> %(vec)s::vector) AS pos
            FROM chunks
            ORDER BY embedding <=> %(vec)s::vector
            LIMIT %(por_brazo)s
        ),
        f AS (
            SELECT id, row_number() OVER (
                ORDER BY ts_rank_cd(contenido_tsv, plainto_tsquery('spanish', %(texto)s)) DESC
            ) AS pos
            FROM chunks
            WHERE contenido_tsv @@ plainto_tsquery('spanish', %(texto)s)
            LIMIT %(por_brazo)s
        )
        SELECT c.id, c.doc_id, c.contenido, c.fuente,
               coalesce(1.0 / (%(k)s + v.pos), 0) + coalesce(1.0 / (%(k)s + f.pos), 0) AS rrf
        FROM chunks c
        LEFT JOIN v ON v.id = c.id
        LEFT JOIN f ON f.id = c.id
        WHERE v.id IS NOT NULL OR f.id IS NOT NULL
        ORDER BY rrf DESC
        LIMIT %(top_k)s
    """
    conn = db.conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "vec": _vector_literal(query_vec),
                "texto": query_texto,
                "por_brazo": POR_BRAZO,
                "k": RRF_K,
                "top_k": top_k,
            })
            filas = cur.fetchall()
    finally:
        conn.close()
    return [Chunk(id=r[0], doc_id=r[1], contenido=r[2], fuente=r[3], score=r[4]) for r in filas]


def buscar_vectorial(query_vec: list[float], top_k: int = 5) -> list[Chunk]:
    """Búsqueda de un solo brazo (solo vector, sin fusión). La usa
    multihop.py para cada sub-consulta -- en talentbase los hops tampoco
    fusionan con léxico, van directo a vector (ver docs/agentic-rag.md
    de ese repo, sección "After")."""
    sql = """
        SELECT id, doc_id, contenido, fuente
        FROM chunks
        ORDER BY embedding <=> %(vec)s::vector
        LIMIT %(top_k)s
    """
    conn = db.conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, {"vec": _vector_literal(query_vec), "top_k": top_k})
            filas = cur.fetchall()
    finally:
        conn.close()
    return [Chunk(id=r[0], doc_id=r[1], contenido=r[2], fuente=r[3]) for r in filas]
