"""Corre el motor contra el ground truth y saca las metricas de la seccion 5b.

Dos modos, y la diferencia entre los dos es el argumento del proyecto:

  oracle    extraccion perfecta (los campos salen del ground truth).
            Mide la LOGICA sola, sin contaminarla con errores del modelo.

  sin-ocr   simula que el OCR del companiero todavia no existe: las 6
            escrituras escaneadas no producen texto. Mide que pasa cuando
            un documento no se puede leer.

Uso:  .venv/Scripts/python -m riesgo.evaluar [--corte 1000000]
"""

from __future__ import annotations

import argparse
import collections
import json
from datetime import date
from pathlib import Path

from .modelo import CON_RESERVAS, FIRME, Campo
from .motor import analizar
from .ruteo import CORTE_DESCUBIERTO

GT = Path("dataset/ground_truth.json")
HOY = date(2026, 8, 22)

ESCRITURA = "escritura.pdf"
CONTRATO = "contrato.pdf"


def construir_campos(c: dict, sin_ocr: bool) -> tuple[dict[str, Campo], set[str]]:
    """Traduce un caso del ground truth a campos del motor.

    En modo ``sin_ocr`` los campos que salen de una escritura escaneada quedan
    nulos: es exactamente lo que devuelve pypdf sobre esos PDFs (0 caracteres).
    """
    g = c["campos"]
    ilegible = sin_ocr and c["escritura_escaneada"]

    def de_escritura(valor):
        return Campo(None if ilegible else valor, doc=ESCRITURA, pagina=1)

    campos = {
        "titular_contrato": Campo(c["nombre"], doc=CONTRATO, pagina=1),
        "titular_escritura": de_escritura(g["titular_escritura"]),
        "matricula_contrato": Campo(g["matricula_contrato"], doc=CONTRATO, pagina=1),
        "matricula_escritura": de_escritura(g["matricula_escritura"]),
        "capital_adeudado": Campo(g["capital_adeudado"], doc=CONTRATO, pagina=3),
        "garantia_valor": de_escritura(g["garantia_valor"]),
        "cuotas_contrato": Campo(g["cuotas_contrato"], doc=CONTRATO, pagina=1),
        "pagos_emitidos": Campo(g["pagos_emitidos"], doc="recibos.pdf"),
        "puntualidad": Campo(g["puntualidad"], doc="recibos.pdf"),
        "tasacion_fecha": de_escritura(g["tasacion_fecha"]),
        "aviso_previo": Campo(g["aviso_previo"], doc="correspondencia.txt"),
    }
    return campos, ({ESCRITURA} if ilegible else set())


def evaluar(gt: list[dict], sin_ocr: bool, corte: float) -> list[tuple]:
    filas = []
    for c in gt:
        campos, ilegibles = construir_campos(c, sin_ocr)
        v = analizar(c["cliente_id"], campos, nombre=c["nombre"],
                     docs_ilegibles=ilegibles, corte=corte, hoy=HOY)
        filas.append((c, v, v.ruteo == c["ruteo_esperado"]))
    return filas


def _metricas(titulo: str, filas: list[tuple]) -> None:
    firmes = [(c, v, ok) for c, v, ok in filas if v.confianza == FIRME]
    reservas = [(c, v, ok) for c, v, ok in filas if v.confianza == CON_RESERVAS]
    ok_firmes = sum(ok for _, _, ok in firmes)
    ok_total = sum(ok for _, _, ok in filas)
    n = len(filas)

    print(f"\n{'=' * 70}\n{titulo}\n{'=' * 70}")
    print(f"  {len(firmes):>2} FIRMES        -> {ok_firmes}/{len(firmes)} correctos"
          f"{f'    precision {ok_firmes / len(firmes):.0%}' if firmes else ''}")
    print(f"  {len(reservas):>2} CON RESERVAS  -> {sum(ok for _, _, ok in reservas)}/{len(reservas)} correctos")
    print(f"\n  Cobertura (FIRMES / total):  {len(firmes) / n:.0%}")
    print(f"  Exactitud global (sin separar): {ok_total}/{n} = {ok_total / n:.0%}")

    # contradicciones graves: ninguna se puede escapar
    esperadas = sum(1 for c, _, _ in filas
                    for x in c["contradicciones"]
                    if x["tipo"] in ("titular_garantia", "matricula_distinta"))
    detectadas = sum(len(v.graves) for _, v, _ in filas)
    print(f"  Contradicciones GRAVES: {detectadas}/{esperadas} detectadas")

    malos = [(c, v) for c, v, ok in filas if not ok]
    if malos:
        print(f"\n  casos mal ruteados ({len(malos)}):")
        for c, v in malos:
            print(f"    {c['carpeta']:15} esperado={c['ruteo_esperado']:15} "
                  f"obtenido={v.ruteo:15} [{v.confianza}]")
            print(f"    {'':15} motivo: {v.motivo}")


def barrido_corte(gt: list[dict]) -> None:
    print(f"\n{'=' * 70}\nCORTE DE DESCUBIERTO -- es politica, pero se puede medir\n{'=' * 70}")
    print("  corte           aciertos   a LEGALES")
    for corte in (250_000, 500_000, 750_000, 1_000_000, 1_500_000, 2_000_000):
        filas = evaluar(gt, sin_ocr=False, corte=corte)
        ok = sum(o for *_, o in filas)
        legales = sum(1 for _, v, _ in filas if v.ruteo == "LEGALES")
        print(f"    ${corte:>9,}    {ok:>2}/{len(filas)}      {legales:>2}/{len(filas)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corte", type=float, default=CORTE_DESCUBIERTO)
    args = ap.parse_args()

    if not GT.exists():
        print(f"falta {GT} -- corre:  tar xzf dataset_riesgo.tar.gz")
        return 1
    gt = json.loads(GT.read_text(encoding="utf-8"))

    _metricas(f"ORACLE -- extraccion perfecta, corte ${args.corte:,.0f}",
              evaluar(gt, sin_ocr=False, corte=args.corte))
    _metricas("SIN OCR -- las 6 escrituras escaneadas no producen texto",
              evaluar(gt, sin_ocr=True, corte=args.corte))
    barrido_corte(gt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
