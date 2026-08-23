"""Benchmark a nivel campo: la evidencia de que el sistema es confiable.

Las metricas por caso (ruteo correcto, FIRME/CON RESERVAS) no alcanzan para
demostrar reliability. Un 95% de exactitud con los errores declarados es
excelente en un workflow financiero; un 99% con 1% de errores silenciosos en
campos criticos es inaceptable. La diferencia solo se ve midiendo por campo.

Cuatro clases, y la ultima es el KPI:

    CORRECTO       extrajo exactamente el valor esperado
    DETECTADO      se equivoco, pero grounding/alerta forzo la revision
    ABSTENCION     el dato no se podia leer y no lo invento
    SILENCIOSO     produjo un dato incorrecto como si fuera valido   <-- KPI

Un error DETECTADO no es un error del sistema: es el sistema funcionando. Lo
unico que no se puede perdonar es el silencioso, porque nadie lo va a mirar.

Ademas separa por campo. El promedio esconde donde rompe el modelo: es
esperable que titular y matricula den casi perfecto y que los montos escritos
en prosa (garantia_valor) sean el punto debil, sobre todo cuando vienen de una
escritura escaneada. Esa tabla muestra que entendemos donde falla, no solo que
calculamos un promedio.

Y elige los tres casos del video con datos, no a dedo:

    A  ejecucion completamente limpia
    B  contradiccion real encontrada entre dos documentos
    C  el peor caso de OCR/grounding del dataset

Este modulo NO modifica el motor. Solo llama a `extraer_carpeta()` y
`analizar()` y clasifica lo que devuelven.

Uso:
    python -m riesgo.benchmark
    python -m riesgo.benchmark --bridge --dataset dataset99
    python -m riesgo.benchmark --guardar bench_dev.json
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

CORRECTO = "correcto"
DETECTADO = "detectado"
ABSTENCION = "abstencion"
SILENCIOSO = "SILENCIOSO"

# Campos con valor esperado en el ground truth. Los dos domicilios se extraen
# pero el generador no los expone, asi que no se pueden puntuar: se cuentan
# aparte para no inflar ni ensuciar el denominador.
MAPA_GT = {
    "titular_contrato":    ("nombre", None),
    "titular_escritura":   (None, "titular_escritura"),
    "matricula_contrato":  (None, "matricula_contrato"),
    "matricula_escritura": (None, "matricula_escritura"),
    "capital_adeudado":    (None, "capital_adeudado"),
    "cuotas_contrato":     (None, "cuotas_contrato"),
    "garantia_valor":      (None, "garantia_valor"),
    "tasacion_fecha":      (None, "tasacion_fecha"),
    "pagos_emitidos":      (None, "pagos_emitidos"),
    "puntualidad":         (None, "puntualidad"),
    "aviso_previo":        (None, "aviso_previo"),
}

SIN_GROUND_TRUTH = ("domicilio_contrato", "domicilio_escritura")


def _campos_criticos() -> set[str]:
    """Los que influyen en alguna rama del ruteo.

    Un error silencioso en uno de estos cambia la decision; en el resto solo
    ensucia el informe. La distincion es la que hace la metrica accionable.
    """
    from .ruteo import INFLUYEN
    return {c for grupo in INFLUYEN.values() for c in grupo}


def _esperado(caso: dict, campo: str):
    top, dentro = MAPA_GT[campo]
    return caso[top] if top else caso["campos"].get(dentro)


def _coincide(got, esp) -> bool:
    if got is None or esp is None:
        return got is esp
    if isinstance(got, bool) or isinstance(esp, bool):
        return bool(got) is bool(esp)
    if isinstance(got, (int, float)) and isinstance(esp, (int, float)):
        return abs(float(got) - float(esp)) < 0.01
    if isinstance(got, date):
        got = got.isoformat()
        esp = _fecha_iso(esp)
    return str(got).strip().casefold() == str(esp).strip().casefold()


def _fecha_iso(v) -> str:
    """El ground truth guarda fechas dd/mm/aaaa; el motor devuelve date."""
    s = str(v)
    if "/" in s:
        d, m, a = s.split("/")
        return f"{a}-{m}-{d}"
    return s


def clasificar(campo, esperado) -> str:
    """Las cuatro clases. `campo` es un riesgo.modelo.Campo.

    `campo.confiable` ya contempla grounding fallado, alerta de lectura y
    confianza de OCR baja -- o sea, todo lo que el sistema declara. Esto no
    reimplementa esa logica: la consulta.
    """
    declarado = not campo.confiable

    if campo.valor is None:
        # No produjo dato. Es abstencion correcta si efectivamente no habia
        # forma de leerlo; si el valor existia y era legible, se abstuvo de
        # mas (cuesta cobertura, no seguridad).
        return ABSTENCION

    if _coincide(campo.valor, esperado):
        return CORRECTO

    return DETECTADO if declarado else SILENCIOSO


async def correr(gt: list[dict], dataset: Path, bridge: bool,
                 limite: int | None) -> list[dict]:
    from .bridge import MotorBridge
    from .documentos import leer_carpeta
    from .extraccion import documentos_ilegibles, extraer_carpeta
    from .llm import Motor
    from .motor import analizar

    casos = gt[:limite] if limite else gt
    filas = []
    ctx = MotorBridge(verboso=False) if bridge else Motor(verboso=False)

    async with ctx as motor:
        for i, c in enumerate(casos, 1):
            docs = leer_carpeta(dataset / c["carpeta"])
            t0 = time.perf_counter()
            campos = await extraer_carpeta(motor, docs)
            v = analizar(c["cliente_id"], campos, nombre=campos["titular_contrato"].valor,
                         docs_ilegibles=documentos_ilegibles(docs))
            seg = time.perf_counter() - t0

            marcas = {}
            for nombre in MAPA_GT:
                campo = campos.get(nombre)
                if campo is None:
                    continue
                marcas[nombre] = {
                    "clase": clasificar(campo, _esperado(c, nombre)),
                    "obtenido": campo.valor.isoformat() if isinstance(campo.valor, date) else campo.valor,
                    "esperado": _esperado(c, nombre),
                    "crudo": campo.crudo,
                    "grounding_ok": campo.grounding_ok,
                    "ocr": campo.ocr_confianza,
                }

            filas.append({
                "carpeta": c["carpeta"],
                "escaneada": c["escritura_escaneada"],
                "ruteo": v.ruteo,
                "ruteo_esperado": c["ruteo_esperado"],
                "ruteo_ok": v.ruteo == c["ruteo_esperado"],
                "confianza": v.confianza,
                "graves_reales": [x["tipo"] for x in c["contradicciones"]
                                  if x["tipo"] in ("titular_garantia", "matricula_distinta")],
                "hallazgos": [{"tipo": h.tipo, "gravedad": h.gravedad, "estado": h.estado}
                              for h in v.hallazgos],
                "alertas": len(v.alertas),
                "segundos": seg,
                "campos": marcas,
            })
            silen = sum(1 for m in marcas.values() if m["clase"] == SILENCIOSO)
            print(f"  {i:>2}/{len(casos)}  {c['carpeta']:<15} {v.ruteo:<15} "
                  f"{v.confianza:<15} {'silenciosos:' + str(silen) if silen else '':<14} {seg:.0f}s",
                  flush=True)
    return filas


# ── Informe ──────────────────────────────────────────────────────────────────

def _global(filas: list[dict], criticos: set[str]) -> None:
    conteo = collections.Counter()
    conteo_crit = collections.Counter()
    for f in filas:
        for nombre, m in f["campos"].items():
            conteo[m["clase"]] += 1
            if nombre in criticos:
                conteo_crit[m["clase"]] += 1
    total = sum(conteo.values())

    print(f"\n{'=' * 72}")
    print(f"EXTRACCIONES — {len(filas)} carpetas / {total} campos evaluados")
    print("=" * 72)
    for clase, etiqueta in ((CORRECTO, "Correcto"),
                            (DETECTADO, "Incorrecto pero DETECTADO"),
                            (ABSTENCION, "Abstencion (no invento)"),
                            (SILENCIOSO, "ERROR SILENCIOSO")):
        n = conteo[clase]
        marca = "  <-- el que importa" if clase == SILENCIOSO else ""
        print(f"  {etiqueta:<28} {n:>4}  {n / total:>5.1%}{marca}")

    ns = conteo_crit[SILENCIOSO]
    tc = sum(conteo_crit.values())
    print(f"\n  Solo campos que definen el ruteo ({tc} extracciones):")
    print(f"    errores silenciosos: {ns}" +
          ("   <-- cada uno cambia una decision" if ns else "   (ninguno)"))


def _por_campo(filas: list[dict]) -> None:
    print(f"\n{'=' * 72}\nPOR CAMPO — donde rompe el modelo\n{'=' * 72}")
    print(f"  {'campo':<22}{'correcto':>9}{'detect.':>9}{'abst.':>7}{'SILEN.':>8}")
    print("  " + "-" * 56)
    por = collections.defaultdict(collections.Counter)
    for f in filas:
        for nombre, m in f["campos"].items():
            por[nombre][m["clase"]] += 1
    for nombre in MAPA_GT:
        c = por.get(nombre)
        if not c:
            continue
        t = sum(c.values())
        alerta = "  !!" if c[SILENCIOSO] else ""
        print(f"  {nombre:<22}{c[CORRECTO]:>4}/{t:<4}{c[DETECTADO]:>9}"
              f"{c[ABSTENCION]:>7}{c[SILENCIOSO]:>8}{alerta}")
    print(f"\n  ({', '.join(SIN_GROUND_TRUTH)} se extraen pero el generador no "
          f"expone su valor:\n   no se puntuan)")


def _automatizacion(filas: list[dict]) -> None:
    autom = [f for f in filas if f["confianza"] == "FIRME"]
    escal = [f for f in filas if f["confianza"] != "FIRME"]
    # Un escalado "justificado" es uno donde de verdad habia algo: una anomalia
    # real en el ground truth, o un documento que no se pudo leer.
    justificados = [f for f in escal if f["graves_reales"] or f["escaneada"] or f["alertas"]]
    ok_autom = sum(1 for f in autom if f["ruteo_ok"])

    print(f"\n{'=' * 72}\nRESOLUCION SEGURA\n{'=' * 72}")
    n = len(filas)
    print(f"  Resueltos automaticamente   {len(autom):>2}/{n}   ({len(autom)/n:.0%})")
    if autom:
        print(f"    de esos, ruteo correcto   {ok_autom}/{len(autom)}"
              f"   ({ok_autom/len(autom):.0%})")
    print(f"  Escalados a revision        {len(escal):>2}/{n}   ({len(escal)/n:.0%})")
    if escal:
        print(f"    con anomalia o documento ilegible real   "
              f"{len(justificados)}/{len(escal)}")
        ruido = len(escal) - len(justificados)
        if ruido:
            print(f"    escalados sin motivo aparente            {ruido}"
                  f"   <-- cuesta cobertura, no seguridad")

    segs = [f["segundos"] for f in filas]
    print(f"\n  Latencia mediana  {statistics.median(segs):.0f} s/caso"
          f"   (rango {min(segs):.0f}-{max(segs):.0f})")


def _tres_casos(filas: list[dict]) -> None:
    """A/B/C elegidos por los datos, no a dedo. Mata el cherry-picking."""
    def silen(f):
        return sum(1 for m in f["campos"].values() if m["clase"] == SILENCIOSO)

    limpios = [f for f in filas
               if f["confianza"] == "FIRME" and f["ruteo_ok"] and not silen(f)
               and not f["escaneada"]]
    contra = [f for f in filas
              if f["graves_reales"] and any(h["gravedad"] == "GRAVE" for h in f["hallazgos"])]
    # El peor: mas abstenciones + alertas, priorizando escaneadas.
    def dolor(f):
        ab = sum(1 for m in f["campos"].values() if m["clase"] == ABSTENCION)
        return (ab + f["alertas"] * 2 + (3 if f["escaneada"] else 0))

    print(f"\n{'=' * 72}\nLOS TRES CASOS DEL VIDEO — elegidos por los datos\n{'=' * 72}")
    a = limpios[0] if limpios else None
    b = max(contra, key=lambda f: len(f["graves_reales"])) if contra else None
    c = max(filas, key=dolor)

    if a:
        print(f"  A  limpio            {a['carpeta']:<15} "
              f"FIRME, ruteo correcto, sin errores, documentos nativos")
    if b:
        print(f"  B  contradiccion     {b['carpeta']:<15} "
              f"{', '.join(b['graves_reales'])} detectada")
    print(f"  C  el peor            {c['carpeta']:<15} "
          f"{'escaneada, ' if c['escaneada'] else ''}{c['alertas']} alerta(s), "
          f"{sum(1 for m in c['campos'].values() if m['clase'] == ABSTENCION)} abstenciones")
    print("\n  A representa una ejecucion correcta, B una contradiccion realmente")
    print("  encontrada, y C el peor caso de OCR/grounding del set. Ninguno se")
    print("  eligio a mano.")


def _silenciosos(filas: list[dict], criticos: set[str]) -> None:
    hay = False
    for f in filas:
        for nombre, m in f["campos"].items():
            if m["clase"] != SILENCIOSO:
                continue
            if not hay:
                print(f"\n{'=' * 72}\nDETALLE DE LOS ERRORES SILENCIOSOS\n{'=' * 72}")
                hay = True
            crit = "  [CRITICO: define el ruteo]" if nombre in criticos else ""
            print(f"  {f['carpeta']:<15} {nombre:<20}{crit}")
            print(f"      obtenido={m['obtenido']!r}  esperado={m['esperado']!r}")
            print(f"      crudo={m['crudo']!r}  grounding_ok={m['grounding_ok']}  ocr={m['ocr']}")
    if not hay:
        print(f"\n  Sin errores silenciosos: todo lo que el sistema erro, lo declaro.")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="dataset")
    ap.add_argument("--bridge", action="store_true")
    ap.add_argument("--casos", type=int)
    ap.add_argument("--guardar", help="ruta JSON con el detalle por campo")
    args = ap.parse_args()

    dataset = Path(args.dataset)
    gt_path = dataset / "ground_truth.json"
    if not gt_path.exists():
        print(f"falta {gt_path} -- corre: tar xzf dataset_riesgo.tar.gz")
        return 1
    gt = json.loads(gt_path.read_text(encoding="utf-8"))

    print(f"BENCHMARK — {args.dataset}, extraccion real\n")
    filas = asyncio.run(correr(gt, dataset, args.bridge, args.casos))
    criticos = _campos_criticos()

    _global(filas, criticos)
    _por_campo(filas)
    _automatizacion(filas)
    _silenciosos(filas, criticos)
    _tres_casos(filas)

    if args.guardar:
        Path(args.guardar).write_text(
            json.dumps(filas, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        print(f"\n  detalle por campo guardado en {args.guardar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
