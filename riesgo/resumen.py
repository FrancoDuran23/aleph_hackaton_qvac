"""El bloque de cierre: qué hizo el sistema sobre una cartera entera.

Es la última pantalla del video. Un caso suelto muestra que el sistema anda;
esto muestra qué pasa cuando le entra la cartera completa, que es la pregunta
que se hace alguien que tendría que comprarlo.

La regla de armado: **la precisión se reporta solo sobre los FIRMES**, y al
lado se dice cuántos casos son. Un 100% sobre 14 de 20 es una afirmación
honesta; un 80% sobre 20 mezcla lo que el sistema sabe con lo que sospecha.

Uso:
    python -m riesgo.resumen                       # texto plano
    python -m riesgo.resumen --dataset dataset99
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from .modelo import CON_RESERVAS, FIRME

ANCHO = 64


def _barra(n: int, total: int, ancho: int = 22) -> str:
    llenos = round(ancho * n / total) if total else 0
    return "█" * llenos + "·" * (ancho - llenos)


def bloque(filas: list[tuple], minutos: float | None = None,
           modelo: str = "?", etiqueta: str = "") -> str:
    """``filas`` son las tuplas (caso, veredicto, acerto) que devuelve evaluar."""
    total = len(filas)
    firmes = [f for f in filas if f[1].confianza == FIRME]
    reservas = [f for f in filas if f[1].confianza == CON_RESERVAS]
    ok_firmes = sum(ok for *_, ok in firmes)
    ok_reservas = sum(ok for *_, ok in reservas)

    rutas = collections.Counter(v.ruteo for _, v, _ in filas)
    graves_esperadas = sum(1 for c, _, _ in filas for x in c["contradicciones"]
                           if x["tipo"] in ("titular_garantia", "matricula_distinta"))
    graves = sum(len(v.graves) for _, v, _ in filas)

    L = []
    a = L.append
    a("=" * ANCHO)
    a(f"CARTERA ANALIZADA — {total} carpetas{f'  ·  {etiqueta}' if etiqueta else ''}")
    a("=" * ANCHO)
    a("")

    a("RESUELTO CON CONFIANZA PLENA")
    a(f"  {len(firmes)} de {total} casos FIRMES     {_barra(len(firmes), total)}  {len(firmes) / total:.0%}")
    if firmes:
        a(f"  de esos, correctos: {ok_firmes}/{len(firmes)}"
          f"          precision {ok_firmes / len(firmes):.0%}")
    a("")

    a("DERIVADO CON RESERVAS")
    a(f"  {len(reservas)} de {total} casos          {_barra(len(reservas), total)}  {len(reservas) / total:.0%}")
    if reservas:
        a(f"  de esos, correctos: {ok_reservas}/{len(reservas)}")
        motivos = collections.Counter(
            adv.motivo.split(":")[0].split(" no produjo")[0]
            for _, v, _ in reservas for adv in v.advertencias if adv.degrada)
        for motivo, n in motivos.most_common(3):
            a(f"    {n:>2}x  {motivo[:52]}")
    a("")

    a("RUTEO")
    for ruta in ("LEGALES", "REFINANCIACION", "COBRANZAS"):
        n = rutas.get(ruta, 0)
        a(f"  {ruta:<16} {n:>2}   {_barra(n, total, 18)}")
    a("")

    a("CONTRADICCIONES GRAVES")
    a(f"  detectadas {graves} de {graves_esperadas}")
    faltan = graves_esperadas - graves
    if faltan > 0:
        a(f"  las {faltan} restantes están en documentos escaneados;")
        a(f"  esos casos salieron CON RESERVAS, no como limpios")
    a("")

    a("-" * ANCHO)
    a(f"  {ok_firmes}/{len(firmes)} sobre los casos que el sistema declara resolver."
      if firmes else "  sin casos FIRMES")
    a(f"  Los {len(reservas)} restantes salen ruteados igual, con el detalle")
    a(f"  de que no se pudo garantizar en cada uno.")
    a("")
    a(f"  inferencia local · {modelo}"
      + (f" · {minutos:.0f} min" if minutos else ""))
    a("=" * ANCHO)
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    """``argv=None`` parsea ``sys.argv`` (uso standalone). Cuando ``cli.py``
    delega acá para ``riesgo cartera``, pasa una lista explicita -- si
    dejara que esto vuelva a leer ``sys.argv``, el token "cartera" que el
    subparser de cli.py ya consumio seguiria ahi y este parser lo rechazaria
    como argumento no reconocido.
    """
    # La consola de Windows por defecto es cp1252 y no puede con los bloques.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset")
    ap.add_argument("--corte", type=float, default=None)
    args = ap.parse_args(argv)

    from .evaluar import HOY, construir_campos
    from .motor import analizar
    from .ruteo import CORTE_DESCUBIERTO

    gt_path = Path(args.dataset) / "ground_truth.json"
    if not gt_path.exists():
        print(f"falta {gt_path}")
        return 1
    gt = json.loads(gt_path.read_text(encoding="utf-8"))

    filas = []
    for c in gt:
        campos, ilegibles = construir_campos(c, sin_ocr=True)
        v = analizar(c["cliente_id"], campos, nombre=c["nombre"],
                     docs_ilegibles=ilegibles,
                     corte=args.corte or CORTE_DESCUBIERTO, hoy=HOY)
        filas.append((c, v, v.ruteo == c["ruteo_esperado"]))

    print(bloque(filas, modelo="QWEN3_1_7B_INST_Q4", etiqueta=args.dataset))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
