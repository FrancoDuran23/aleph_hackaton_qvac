"""PDF folder -> chunks -> embeddings -> pgvector.

Extracción de PDF con pypdf, adaptada de D:\\AIRgent\\legal_corpus_ingestor.py.
El trozado ahí era por artículo legal (regex "Articulo N") porque el
dominio era fijo (textos legales). Acá el dominio no se conoce hasta el
día del hackathon, así que el trozado es una ventana deslizante genérica
sobre caracteres -- funciona con cualquier PDF, sin asumir estructura.

Correr (desde la raíz del repo, con las env vars cargadas):
    python -m toolkit.hybrid_rag.ingest [carpeta_pdfs]

Cada corrida borra el índice anterior y lo arma de cero -- es idempotente,
podés correrlo de nuevo después de agregar o sacar PDFs de la carpeta.
"""
import sys
from pathlib import Path

import pypdf

from . import db
from .embeddings import dim, embed

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def extraer_texto_pdf(path: Path) -> str:
    reader = pypdf.PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def trozar(texto: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Ventana deslizante simple sobre caracteres, con superposición para no
    cortar una idea justo en el borde de un chunk."""
    texto = texto.strip()
    if not texto:
        return []
    trozos = []
    inicio = 0
    n = len(texto)
    while inicio < n:
        fin = min(inicio + chunk_size, n)
        trozo = texto[inicio:fin].strip()
        if trozo:
            trozos.append(trozo)
        if fin == n:
            break
        inicio = fin - overlap
    return trozos


def ingestar_carpeta(carpeta: Path) -> int:
    pdfs = sorted(carpeta.glob("*.pdf"))
    if not pdfs:
        print(f"No hay PDFs en {carpeta}")
        return 0

    print(f"Encontrados {len(pdfs)} PDFs en {carpeta}")

    filas = []
    for pdf_path in pdfs:
        print(f"\n[{pdf_path.name}] extrayendo texto...")
        texto = extraer_texto_pdf(pdf_path)
        trozos = trozar(texto)
        print(f"  -> {len(trozos)} chunks")
        for i, contenido in enumerate(trozos):
            filas.append({
                "doc_id": pdf_path.stem,
                "chunk_index": i,
                "contenido": contenido,
                "fuente": pdf_path.name,
            })

    if not filas:
        print("\nNingún PDF produjo texto extraíble. Nada para indexar.")
        return 0

    print(f"\nTotal: {len(filas)} chunks de {len(pdfs)} documentos")
    print("Generando embeddings (Gemini)...")

    embeddings = []
    for i, fila in enumerate(filas, 1):
        embeddings.append(embed(fila["contenido"]))
        if i % 5 == 0 or i == len(filas):
            print(f"  [{i}/{len(filas)}] embebido")

    embedding_dim = dim()
    print(f"\nDimensión de embedding detectada: {embedding_dim}")

    conn = db.conectar()
    try:
        db.inicializar_esquema(conn, embedding_dim)
        db.reemplazar_chunks(conn, filas, embeddings)
    finally:
        conn.close()

    print(f"\nListo: {len(filas)} chunks indexados en pgvector.")
    return len(filas)


if __name__ == "__main__":
    carpeta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/pdfs")
    ingestar_carpeta(carpeta)
