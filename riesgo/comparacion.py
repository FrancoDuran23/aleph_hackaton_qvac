"""Primitivas de comparacion: nombres por fuzzy, numeros por digitos exactos.

La regla de oro de este modulo, medida y no intuida:

    numeros -> digitos exactos
    texto   -> fuzzy

Mezclarlas es el error caro. ``2.800.000`` contra ``2.830.000`` da 97% de
similitud fuzzy: con umbral 90 una alucinacion del modelo pasa como si
estuviera respaldada por el documento, y el grounding deja de servir.
"""

from __future__ import annotations

import unicodedata

from jellyfish import jaro_winkler_similarity
from rapidfuzz import fuzz

# Calibrado contra el ground truth. Entre 0.82 y 0.95 el resultado es casi
# identico; lo que importa es no quedar en los extremos.
UMBRAL_NOMBRES = 0.85


def norm(s: str) -> str:
    """Minusculas, sin acentos, sin espacios de borde."""
    s = unicodedata.normalize("NFKD", s.lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))


def similitud_nombres(a: str, b: str) -> float:
    """Similitud entre dos nombres de persona, en [0, 1].

    Jaro-Winkler solo no alcanza: pondera el prefijo comun, asi que
    ``"Perez, Juan"`` contra ``"Juan Perez"`` da bajisimo aunque sean la
    misma persona. ``token_sort_ratio`` ordena las palabras antes de
    comparar, y cubre justamente ese caso.

    Tomamos el maximo de las dos: alcanza con que una de las dos vias
    reconozca a la persona para no levantar una falsa alarma.
    """
    na, nb = norm(a), norm(b)
    return max(
        jaro_winkler_similarity(na, nb),
        fuzz.token_sort_ratio(na, nb) / 100,
    )


def misma_persona(a: str | None, b: str | None,
                  umbral: float = UMBRAL_NOMBRES) -> bool:
    """False solo si hay evidencia de que son personas distintas.

    Si falta alguno de los dos nombres no afirmamos nada: la ausencia de dato
    no es una contradiccion, se anota aparte como campo nulo.
    """
    if not a or not b:
        return True
    return similitud_nombres(a, b) >= umbral


def digitos(s: object) -> str:
    """Solo los digitos de la representacion textual del valor."""
    return "".join(c for c in str(s) if c.isdigit())


def grounding_numero(valor: object, texto: str) -> bool:
    """Tolera formato distinto, no tolera un digito distinto.

    ``$ 2.400.000,00`` y ``ARS 2400000`` matchean porque comparten la
    secuencia de digitos. Un digito cambiado no matchea, que es exactamente
    lo que queremos detectar de un modelo que inventa un monto.
    """
    d = digitos(valor)
    return bool(d) and d in digitos(texto)


def mismo_numero(a: object, b: object) -> bool:
    """Igualdad de numeros por su secuencia de digitos."""
    da, db = digitos(a), digitos(b)
    return bool(da) and da == db
