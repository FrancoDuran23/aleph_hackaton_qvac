"""Calibracion de umbrales contra el ground truth. No es un test: es la
evidencia con la que se eligen los numeros de la seccion 5 del SDD.

Uso:  .venv/Scripts/python -m riesgo.calibrar
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

from jellyfish import jaro_winkler_similarity
from rapidfuzz import fuzz

from .comparacion import digitos, grounding_numero, norm, similitud_nombres

GT = Path("dataset/ground_truth.json")


def variantes(nombre: str) -> list[str]:
    """Las formas en que un mismo nombre aparece escrito en documentos reales."""
    pila, apellido = nombre.split()[0], nombre.split()[-1]
    return [
        nombre,                          # Juan Perez
        f"{apellido}, {pila}",           # Perez, Juan     <- el caso que rompe JW
        f"{pila[0]}. {apellido}",        # J. Perez
        nombre.upper(),                  # JUAN PEREZ
        f"  {nombre}  ",                 # con espacios de sobra
    ]


def _tabla(titulo: str, filas: list[tuple[str, object, object]]) -> None:
    print(f"\n{titulo}")
    print("  " + "-" * 64)
    for etiqueta, a, b in filas:
        print(f"  {etiqueta:<34} {str(a):>12} {str(b):>12}")


def calibrar_nombres(gt: list[dict]) -> None:
    nombres = sorted({c["nombre"] for c in gt})

    # MISMA persona escrita distinto -> no debe disparar contradiccion
    mismos = [(v, w) for n in nombres
              for v, w in itertools.combinations(variantes(n), 2)]
    # PERSONAS distintas -> debe disparar contradiccion
    distintos = list(itertools.combinations(nombres, 2))

    print(f"\n{'=' * 68}\nNOMBRES\n{'=' * 68}")
    print(f"  pares misma persona (escrita distinto): {len(mismos)}")
    print(f"  pares personas distintas:               {len(distintos)}")

    solo_jw = lambda a, b: jaro_winkler_similarity(norm(a), norm(b))

    for u in (0.85,):
        fa_jw = sum(1 for a, b in mismos if solo_jw(a, b) < u)
        fa_mix = sum(1 for a, b in mismos if similitud_nombres(a, b) < u)
        ok_jw = sum(1 for a, b in distintos if solo_jw(a, b) < u)
        ok_mix = sum(1 for a, b in distintos if similitud_nombres(a, b) < u)
        _tabla(f"umbral {u}                              solo JW      JW+TSR", [
            ("falsas alarmas (misma persona)", f"{fa_jw}/{len(mismos)}", f"{fa_mix}/{len(mismos)}"),
            ("detecta distintas", f"{ok_jw}/{len(distintos)}", f"{ok_mix}/{len(distintos)}"),
        ])

    print("\n  barrido de umbral (JW+TSR):")
    print("  umbral   falsas alarmas   detecta distintas")
    for u in (0.80, 0.82, 0.85, 0.90, 0.95, 0.98):
        fa = sum(1 for a, b in mismos if similitud_nombres(a, b) < u)
        ok = sum(1 for a, b in distintos if similitud_nombres(a, b) < u)
        print(f"    {u:.2f}    {fa:>4}/{len(mismos):<10} {ok:>4}/{len(distintos)}")

    peores = sorted(mismos, key=lambda p: similitud_nombres(*p))[:4]
    print("\n  peores pares de MISMA persona (los que casi disparan):")
    for a, b in peores:
        print(f"    jw={solo_jw(a, b):.3f} -> mix={similitud_nombres(a, b):.3f}   {a!r} vs {b!r}")


def calibrar_numeros(gt: list[dict]) -> None:
    """Grounding por digitos contra grounding por fuzzy."""
    montos = [c["campos"]["capital_adeudado"] for c in gt] + \
             [c["campos"]["garantia_valor"] for c in gt]
    montos = [int(m) for m in montos if m]

    def formatos(n: int) -> list[str]:
        s = f"{n:,}".replace(",", ".")
        return [f"$ {s},00", f"ARS {n}", f"$ {s}"]

    def alucinacion(n: int) -> int:
        """Un digito cambiado: lo que hace un modelo cuando inventa."""
        d = list(str(n))
        d[1] = str((int(d[1]) + 3) % 10)
        return int("".join(d))

    reales_ok = fuzzy_reales_ok = 0
    total_reales = 0
    for n in montos:
        for txt in formatos(n):
            total_reales += 1
            reales_ok += grounding_numero(n, txt)
            fuzzy_reales_ok += fuzz.partial_ratio(str(n), txt) >= 90

    tragadas = fuzzy_tragadas = 0
    for n in montos:
        falso = alucinacion(n)
        doc = formatos(n)[0]
        tragadas += grounding_numero(falso, doc)
        fuzzy_tragadas += fuzz.partial_ratio(str(falso), doc) >= 90

    print(f"\n{'=' * 68}\nNUMEROS\n{'=' * 68}")
    _tabla(f"                                        digitos       fuzzy>=90", [
        ("valores reales encontrados", f"{reales_ok}/{total_reales}", f"{fuzzy_reales_ok}/{total_reales}"),
        ("alucinaciones tragadas", f"{tragadas}/{len(montos)}", f"{fuzzy_tragadas}/{len(montos)}"),
    ])
    a, b = 2_800_000, 2_830_000
    print(f"\n  el caso que rompe el fuzzy:")
    print(f"    {a} vs {b}  ->  fuzzy={fuzz.ratio(str(a), str(b)):.0f}%  "
          f"digitos_iguales={digitos(a) == digitos(b)}")


def cortes_descubierto(gt: list[dict]) -> None:
    print(f"\n{'=' * 68}\nCORTE DE DESCUBIERTO (es politica, no optimizacion)\n{'=' * 68}")
    desc = [c["derivados"]["descubierto"] for c in gt]
    print("  corte          manda a LEGALES")
    for corte in (500_000, 1_000_000, 2_000_000):
        print(f"    ${corte:>9,}    {sum(1 for d in desc if d > corte):>2}/{len(desc)}")


def main() -> int:
    if not GT.exists():
        print(f"falta {GT} -- corre:  tar xzf dataset_riesgo.tar.gz")
        return 1
    gt = json.loads(GT.read_text(encoding="utf-8"))
    calibrar_nombres(gt)
    calibrar_numeros(gt)
    cortes_descubierto(gt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
