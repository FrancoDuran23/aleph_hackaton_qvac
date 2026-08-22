#!/usr/bin/env python3
"""Auditoria de solo lectura sobre las salidas ya generadas (dev + holdout).

NO toca codigo de produccion ni re-corre inferencia. Lee los JSON que produce
`riesgo.evaluar --real --guardar`, que incluyen el CRUDO del OCR por campo.

Dos detectores independientes:

  A  separador de miles mal formado, sobre el string CRUDO (no el normalizado).
     En formato es-AR un "." de miles va seguido de exactamente 3 digitos.
     ROTO:  punto al final ("ARS 457.")  |  punto con <3 digitos ("2.40").
     La coma decimal ("2.400.000,00") es valida y NO se marca.

  B  magnitud implausible: cobertura = garantia_valor / capital_adeudado
     fuera de [0.01, 100]. Plausibilidad de dominio, NO sacada de los datos.

Uso:  python auditoria_ocr.py
"""
from __future__ import annotations

import json
from pathlib import Path

from riesgo.ruteo import (COBERTURA_REFINANCIABLE, CORTE_DESCUBIERTO,
                          PUNTUALIDAD_MINIMA)
from riesgo.validacion import COBERTURA_MAX, COBERTURA_MIN
from riesgo.validacion import cobertura_implausible as detector_b
from riesgo.validacion import separador_miles_roto as detector_a

SALIDAS = {
    "DEV": Path("salidas/dev_real.json"),
    "HOLDOUT": Path("salidas/holdout_real.json"),
}


# ── Recalculo de ruteo con el valor corregido ────────────────────────────────

def _rutear(descubierto, cobertura, puntualidad, aviso, hay_grave_confirmada,
            corte=CORTE_DESCUBIERTO) -> str:
    """Replica el orden de reglas de riesgo.ruteo.rutear() sobre valores dados."""
    if hay_grave_confirmada:
        return "LEGALES"
    if descubierto is not None and descubierto > corte:
        return "LEGALES"
    if puntualidad is not None and puntualidad < PUNTUALIDAD_MINIMA:
        return "LEGALES"
    if cobertura is not None and cobertura >= COBERTURA_REFINANCIABLE and aviso:
        return "REFINANCIACION"
    return "COBRANZAS"


def _num(campos, nombre):
    c = campos.get(nombre) or {}
    return c.get("valor")


def auditar(nombre_set: str, casos: list[dict]) -> dict:
    print(f"\n{'='*100}\n{nombre_set}\n{'='*100}")
    print(f"{'caso':<15}{'campo':<18}{'crudo_ocr':<16}{'valor_norm':>12}  "
          f"{'det':<4}{'conf':>6}  {'ruteo':<15}{'FIRME?':<7}motivo")
    sospechosos = []

    for caso in casos:
        campos = caso["campos"]
        firme = caso["confianza"] == "FIRME"
        for cn, cd in campos.items():
            ma = detector_a(cd.get("crudo"))
            if ma is None:
                continue
            conf = cd.get("ocr_confianza")
            print(f"{caso['carpeta']:<15}{cn:<18}{str(cd.get('crudo'))[:15]:<16}"
                  f"{str(cd.get('valor')):>12}  {'A':<4}{(conf if conf is not None else 0):>6.3f}  "
                  f"{caso['ruteo']:<15}{'SI' if firme else 'no':<7}{ma}")
            sospechosos.append((caso, cn, cd, "A", ma))

        # Detector B: a nivel caso (cobertura)
        g, cap = _num(campos, "garantia_valor"), _num(campos, "capital_adeudado")
        mb = detector_b(g, cap)
        if mb:
            print(f"{caso['carpeta']:<15}{'(cobertura)':<18}{'-':<16}{'-':>12}  "
                  f"{'B':<4}{'-':>6}  {caso['ruteo']:<15}{'SI' if firme else 'no':<7}{mb}")
            sospechosos.append((caso, "garantia_valor", campos.get("garantia_valor", {}), "B", mb))

    return {"set": nombre_set, "casos": casos, "sospechosos": sospechosos}


def resumen(resultados: list[dict]) -> None:
    print(f"\n\n{'#'*100}\nRESUMEN\n{'#'*100}")
    for r in resultados:
        a = [s for s in r["sospechosos"] if s[3] == "A"]
        b = [s for s in r["sospechosos"] if s[3] == "B"]
        firmes = [s for s in r["sospechosos"] if s[0]["confianza"] == "FIRME"]
        print(f"\n{r['set']}: {len(a)} sospechosos por A (truncamiento), "
              f"{len(b)} por B (magnitud). FIRME entre ellos: {len(firmes)} "
              f"(confident-wrong potenciales)")

        for caso, cn, cd, det, motivo in r["sospechosos"]:
            campos = caso["campos"]
            cap = _num(campos, "capital_adeudado")
            g = _num(campos, "garantia_valor")
            cob = caso["derivados"].get("cobertura")
            punt = _num(campos, "puntualidad")
            aviso = _num(campos, "aviso_previo")
            grave_conf = any(h["gravedad"] == "GRAVE" and h["estado"] == "CONFIRMADA"
                             for h in caso["hallazgos"])

            # Correccion segun la direccion de la implausibilidad:
            #   cobertura << 1  -> garantia leida demasiado chica (zeros perdidos)
            #   cobertura >> 1  -> capital leido demasiado chico
            g_corr, cap_corr, nota = g, cap, "sin correccion"
            if cob is not None and cob < COBERTURA_MIN and g is not None:
                g_corr, nota = g * 1000, "garantia x1000 (zeros perdidos)"
            elif cob is not None and cob > COBERTURA_MAX and cap:
                nota = "capital mal leido; correccion exacta no determinable del crudo"

            desc_corr = (cap_corr - g_corr) if (cap_corr is not None and g_corr is not None) else None
            cob_corr = (g_corr / cap_corr) if (cap_corr and g_corr is not None) else None
            ruteo_corr = _rutear(desc_corr, cob_corr, punt, aviso, grave_conf)
            cambia = ruteo_corr != caso["ruteo"]

            print(f"  - {caso['carpeta']} [{det}] campo={cn} crudo={cd.get('crudo')!r} "
                  f"valor={cd.get('valor')} origen={cd.get('origen')}")
            print(f"      ruteo actual={caso['ruteo']} (esperado={caso['ruteo_esperado']}, "
                  f"{caso['confianza']}, {'OK' if caso['ok'] else 'MAL'})")
            print(f"      correccion: {nota}")
            print(f"      descubierto {caso['derivados'].get('descubierto')} -> {desc_corr} | "
                  f"cobertura {cob} -> {cob_corr}")
            print(f"      ruteo recalculado={ruteo_corr}  => {'CAMBIA' if cambia else 'no cambia'}"
                  f"{'  (coincide con esperado)' if ruteo_corr == caso['ruteo_esperado'] else ''}")

    # Limite 1: contaminacion de casos hoy 'correctos' (por A o por B)
    print(f"\n{'-'*100}\nLIMITE 1 — casos hoy 'OK' pero con un monto mal leido (A o B):")
    hubo = False
    for r in resultados:
        contaminados = [s for s in r["sospechosos"] if s[0]["ok"]]
        for caso, cn, cd, det, motivo in contaminados:
            hubo = True
            print(f"  {r['set']} {caso['carpeta']}: figura OK, pero {cn} crudo="
                  f"{cd.get('crudo')!r} ({motivo}). Correcto por otra regla "
                  f"(hallazgos: {[h['tipo'] for h in caso['hallazgos'] if h['estado']=='CONFIRMADA']}), "
                  f"no por leer bien el monto.")
    if not hubo:
        print("  ningun caso OK esta contaminado por un monto mal leido")


def main() -> int:
    disponibles = {n: p for n, p in SALIDAS.items() if p.exists()}
    if not disponibles:
        print("No hay salidas para auditar. Generalas con:")
        print("  python -m riesgo.evaluar --real --dataset <set> --guardar <ruta>")
        return 1
    for n, p in SALIDAS.items():
        if n not in disponibles:
            print(f"[aviso] falta {p} ({n}) — se audita solo lo disponible por ahora")

    resultados = []
    for nombre, ruta in disponibles.items():
        casos = json.loads(ruta.read_text(encoding="utf-8"))
        resultados.append(auditar(nombre, casos))
    resumen(resultados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
