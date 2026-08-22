#!/usr/bin/env python3
"""Prueba de humo del bridge de QVAC, de punta a punta desde Python.

Uso (con el túnel abierto):
    python scripts/qvac/smoke_test.py

Verifica, en orden: que el bridge responda, que genere texto, que devuelva
embeddings, y que la dimensión sea estable entre llamadas — que es lo que
`db.py` asume cuando arma la columna VECTOR(N).

La primera corrida descarga los modelos y puede tardar varios minutos.
"""
import sys
import time
from pathlib import Path

# La consola de Windows usa cp1252 por defecto y tira UnicodeEncodeError al
# imprimir cualquier cosa fuera de ese charset — incluida una respuesta del
# modelo con tildes. Forzamos UTF-8 antes de imprimir nada.
for flujo in (sys.stdout, sys.stderr):
    if hasattr(flujo, "reconfigure"):
        flujo.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from toolkit.qvac_brain import QvacBridgeError, embeddings, salud  # noqa: E402
from toolkit.qvac_brain import brain  # noqa: E402


def paso(titulo: str) -> None:
    print(f"\n\033[1;36m▸ {titulo}\033[0m")


def main() -> int:
    paso("1/4  health")
    try:
        print(f"    {salud()}")
    except QvacBridgeError as e:
        print(f"    FALLA: {e}")
        print("\n    ¿Está el túnel abierto?  ./scripts/qvac/tunnel.sh <IP>")
        return 1

    paso("2/4  generación de texto")
    inicio = time.monotonic()
    texto, tok_in, tok_out = brain.llamar_llm_sync(
        messages=[{"role": "user", "content": "Respondé sólo con la palabra: listo"}],
        system="Sos conciso.",
        max_tokens=20,
    )
    demora = time.monotonic() - inicio
    print(f"    respuesta: {texto!r}")
    print(f"    tokens: in={tok_in} out={tok_out} — {demora:.1f}s")
    if texto == brain.RESPUESTA_FALLBACK:
        print("    FALLA: el bridge devolvió el fallback (mirá journalctl -u qvac-bridge)")
        return 1

    paso("3/4  embeddings")
    inicio = time.monotonic()
    vector = embeddings.embed("una prueba de embeddings")
    print(f"    dim={len(vector)} primeros={ [round(v, 4) for v in vector[:4]] } — {time.monotonic() - inicio:.1f}s")

    paso("4/4  lote y estabilidad de la dimensión")
    lote = embeddings.embed_lote(["primero", "segundo", "tercero"])
    print(f"    {len(lote)} vectores, dims={[len(v) for v in lote]}")
    if any(len(v) != len(vector) for v in lote):
        print("    FALLA: la dimensión cambia entre llamadas; db.py no lo va a tolerar")
        return 1
    if embeddings.dim() != len(vector):
        print(f"    FALLA: dim() dice {embeddings.dim()} pero embed() devolvió {len(vector)}")
        return 1

    print("\n\033[1;32m✔ todo en orden\033[0m")
    print(f"  Poné esto en tu .env:  EMBEDDING_DIM={len(vector)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
