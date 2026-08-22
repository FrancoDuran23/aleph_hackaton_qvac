"""Conexión a Postgres + esquema de la tabla `chunks` (pgvector + tsvector).

Sin pool de conexiones a propósito: para el volumen de un hackathon (una
carpeta de PDFs, un puñado de usuarios probando el chat) abrir una
conexión por request es simple y no es el cuello de botella. Si esto
escalara de verdad, ahí sí vale la pena psycopg_pool.
"""
import os

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://hackaton:hackaton@localhost:5432/hackaton")

# pgvector solo indexa (HNSW/ivfflat) vectores de hasta ~2000 dimensiones.
# Si el modelo de embeddings devuelve más, la tabla igual funciona (vector
# se banca hasta 16000 dims para guardar), simplemente no se crea el
# índice y las búsquedas por similitud hacen sequential scan -- lento en
# un corpus grande, pero un hackathon carga unos pocos PDFs.
HNSW_MAX_DIM = 2000


def conectar() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=True)


def inicializar_esquema(conn: psycopg.Connection, embedding_dim: int) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                contenido TEXT NOT NULL,
                fuente TEXT NOT NULL,
                embedding VECTOR({embedding_dim}) NOT NULL,
                contenido_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('spanish', contenido)) STORED
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (contenido_tsv)")
        if embedding_dim <= HNSW_MAX_DIM:
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS chunks_embedding_idx
                ON chunks USING hnsw (embedding vector_cosine_ops)
                """
            )
        else:
            print(
                f"Aviso: dimensión de embedding ({embedding_dim}) supera {HNSW_MAX_DIM}, "
                "no se crea índice HNSW -- las búsquedas por vector van a hacer sequential scan."
            )


def reemplazar_chunks(conn: psycopg.Connection, filas: list[dict], embeddings: list[list[float]]) -> None:
    """Idempotente: borra todo lo indexado antes y lo carga de cero, igual
    que el ingestor de AIRgent (el orden de los PDFs no importa, los ids
    son deterministicos)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunks")
        for fila, embedding in zip(filas, embeddings):
            chunk_id = f"{fila['doc_id']}_{fila['chunk_index']}"
            vector_literal = "[" + ",".join(repr(float(v)) for v in embedding) + "]"
            cur.execute(
                """
                INSERT INTO chunks (id, doc_id, chunk_index, contenido, fuente, embedding)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (chunk_id, fila["doc_id"], fila["chunk_index"], fila["contenido"], fila["fuente"], vector_literal),
            )


def contar_chunks(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks")
        return cur.fetchone()[0]
