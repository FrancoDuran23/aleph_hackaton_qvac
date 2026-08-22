"""Validacion de campos numericos: separador de miles y magnitud.

Dos senales independientes. La auditoria (auditoria_ocr.py) confirmo que hacen
falta las dos y que no se solapan:

  A  separador de miles mal formado, sobre el string CRUDO (no el normalizado).
     En formato es-AR un "." de miles va seguido de exactamente 3 digitos.
     Atrapa "ARS 457." o "2.40". NO marca la coma decimal ("2.400.000,00").
     Es una guardia defensiva: en el dataset actual no dispara, pero corta el
     modo de fallo si aparece.

  B  magnitud implausible: cobertura = garantia_valor / capital_adeudado fuera
     de una banda de plausibilidad de dominio. Es la senal que SI atrapa los
     confident-wrong reales (un monto al que el OCR le comio los ceros, o una
     normalizacion que leyo "2,63 millones" como 2.63). La banda no sale de los
     datos: una garantia razonable cubre entre el 1% y 100x la deuda.
"""
from __future__ import annotations

import re

# Banda de plausibilidad de dominio (NO ajustada a los datos de test).
COBERTURA_MIN, COBERTURA_MAX = 0.01, 100.0

_NUMERO = re.compile(r"[\d.,]+")


def separador_miles_roto(crudo: object) -> str | None:
    """Detector A. Devuelve el motivo si el separador de miles esta roto, o None."""
    if not crudo:
        return None
    m = _NUMERO.search(str(crudo))
    if not m:
        return None
    entero = m.group().split(",")[0]      # descarta la parte decimal (coma es-AR)
    if "." not in entero:
        return None
    if entero.endswith("."):
        return "separador de miles al final de la cifra"
    for grupo in entero.split(".")[1:]:
        if len(grupo) != 3:
            return f"grupo de miles con {len(grupo)} digito(s), no 3"
    return None


def cobertura_implausible(garantia: float | None,
                          capital: float | None) -> str | None:
    """Detector B. Motivo si la cobertura esta fuera de la banda de dominio."""
    if garantia is None or not capital:
        return None
    cob = garantia / capital
    if cob < COBERTURA_MIN or cob > COBERTURA_MAX:
        return f"cobertura {cob:.4g} fuera de [{COBERTURA_MIN}, {COBERTURA_MAX}]"
    return None
