"""Montos y fechas: del string tal como aparece en el documento, al valor.

El modelo extrae el string **verbatim** y la conversión pasa acá. Pedirle al
modelo que devuelva un número lo obliga a hacer aritmética, que es justo lo que
peor hace: con ``$ 2,40 millones`` un modelo chico devuelve ``2.40`` tan
seguido como ``2400000``, y las dos son plausibles mirando el JSON.

Los tres formatos del dataset, todos para el mismo valor:

    $ 2.400.000,00      punto de miles, coma decimal
    ARS 2.400.000       sin decimales
    $ 2,40 millones     coma decimal, escala en palabra
"""

from __future__ import annotations

import re
from datetime import date

from dateutil import parser as _fechas

# "millones" / "millon" / "M" al final del monto multiplica por 1e6.
_ESCALA = re.compile(r"\b(millones|millon|mill\.?|m)\b\s*$", re.IGNORECASE)
_NO_NUMERO = re.compile(r"[^\d.,]")


def normalizar_monto(bruto: object) -> float | None:
    """Devuelve el valor en pesos, o None si no se puede interpretar.

    Nunca adivina: si el string no tiene dígitos, o queda ambiguo después de
    limpiarlo, devuelve None. Un monto inventado es peor que un monto faltante,
    porque el faltante se declara y el inventado no.
    """
    if bruto is None:
        return None
    if isinstance(bruto, (int, float)):
        return float(bruto)

    s = str(bruto).strip()
    if not s:
        return None

    escala = 1_000_000.0 if _ESCALA.search(s) else 1.0
    s = _ESCALA.sub("", s).strip()
    s = _NO_NUMERO.sub("", s)
    if not any(c.isdigit() for c in s):
        return None

    s = _separadores(s)
    try:
        return float(s) * escala
    except ValueError:
        return None


def _separadores(s: str) -> str:
    """Resuelve cuál de los dos separadores es el decimal.

    En es-AR el punto agrupa miles y la coma separa decimales, pero los
    documentos no son consistentes, así que se decide por la forma:

      * si están los dos, el que aparece último es el decimal
      * si está solo la coma, es decimal salvo que agrupe de a tres
      * si está solo el punto, es de miles salvo que deje 1 o 2 decimales
    """
    tiene_punto, tiene_coma = "." in s, "," in s

    if tiene_punto and tiene_coma:
        decimal = "," if s.rindex(",") > s.rindex(".") else "."
        miles = "." if decimal == "," else ","
        return s.replace(miles, "").replace(decimal, ".")

    if tiene_coma:
        # "2,400" es ambiguo; "2,40" y "2,4" son decimales. Tres dígitos
        # después de la coma se lee como agrupación de miles.
        cola = s.rsplit(",", 1)[1]
        return s.replace(",", "") if len(cola) == 3 else s.replace(",", ".")

    if tiene_punto:
        cola = s.rsplit(".", 1)[1]
        return s if len(cola) in (1, 2) else s.replace(".", "")

    return s


def normalizar_entero(bruto: object) -> int | None:
    """Para cuotas, cantidades: solo la parte entera."""
    v = normalizar_monto(bruto)
    return None if v is None else int(round(v))


def normalizar_fecha(bruto: object) -> date | None:
    """Fechas del dataset en dd/mm/aaaa. ``dayfirst`` no es opcional acá:
    sin eso ``12/04/2024`` se lee como diciembre."""
    if bruto is None:
        return None
    if isinstance(bruto, date):
        return bruto
    s = str(bruto).strip()
    if not s:
        return None
    try:
        return _fechas.parse(s, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def normalizar_texto(bruto: object) -> str | None:
    """Colapsa espacios y descarta los no-valores que el modelo inventa igual.

    El schema declara ``string | null``, y aun así un modelo chico devuelve
    ``"no encontrado"`` o ``"N/A"`` de vez en cuando. Eso es un nulo disfrazado
    y hay que tratarlo como nulo, no como el nombre del titular.
    """
    if bruto is None:
        return None
    s = " ".join(str(bruto).split())
    if not s:
        return None
    if s.casefold() in {"null", "none", "n/a", "na", "-", "--",
                        "no encontrado", "no especificado", "sin datos",
                        "desconocido", "no disponible"}:
        return None
    return s
