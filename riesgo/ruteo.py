"""A que area va el caso. El modelo no decide esto: lo decide el codigo.

El orden de evaluacion importa. La contradiccion grave va primero, antes de
mirar montos: una garantia con defecto formal no sirve por mas que cubra el
200% de la deuda.

Nada frena el ruteo. Si falta un dato, el caso rutea igual con lo que hay y
sale marcado CON RESERVAS. El analista siempre recibe un veredicto mas el
detalle de que no se pudo garantizar.
"""

from __future__ import annotations

from .modelo import COBRANZAS, LEGALES, REFINANCIACION, Hallazgo


def _pesos(v: float) -> str:
    """Formato local: punto para miles. Solo presentación."""
    return f"${v:,.0f}".replace(",", ".")

# Politica, no optimizacion. Sobre el dataset de desarrollo:
#   $500.000 manda 13/20 a legales, $1.000.000 manda 6/20, $2.000.000 manda 3/20.
# No hay valor optimo: hay que elegirlo y defenderlo. Ver seccion 13 del SDD.
CORTE_DESCUBIERTO = 1_000_000.0

PUNTUALIDAD_MINIMA = 0.5
COBERTURA_REFINANCIABLE = 0.6

# Campos que influyen en cada decision. Se usa para saber que reservas
# degradan el caso: solo importan las de los campos que movieron la aguja.
INFLUYEN = {
    "contradiccion_grave": ("titular_contrato", "titular_escritura",
                            "matricula_contrato", "matricula_escritura"),
    "descubierto": ("capital_adeudado", "garantia_valor"),
    "puntualidad": ("puntualidad",),
    "cobertura": ("capital_adeudado", "garantia_valor", "aviso_previo"),
}


def rutear(graves: list[Hallazgo], derivados: dict, aviso_previo: bool | None,
           corte: float = CORTE_DESCUBIERTO) -> tuple[str, str, tuple[str, ...]]:
    """Devuelve (ruta, motivo, campos_que_influyeron)."""
    desc = derivados.get("descubierto")
    punt = derivados.get("puntualidad")
    cob = derivados.get("cobertura")

    if graves:
        tipos = ", ".join(sorted({h.tipo for h in graves}))
        return LEGALES, f"defecto formal en la garantia ({tipos})", INFLUYEN["contradiccion_grave"]

    if desc is not None and desc > corte:
        return LEGALES, (f"descubierto de {_pesos(desc)} sobre el corte "
                         f"de {_pesos(corte)}"), INFLUYEN["descubierto"]

    if punt is not None and punt < PUNTUALIDAD_MINIMA:
        return LEGALES, f"puntualidad de {punt:.0%}, bajo el minimo de {PUNTUALIDAD_MINIMA:.0%}", INFLUYEN["puntualidad"]

    if cob is not None and cob >= COBERTURA_REFINANCIABLE and aviso_previo:
        return REFINANCIACION, f"cobertura de {cob:.0%} y aviso previo cursado", INFLUYEN["cobertura"]

    return COBRANZAS, "sin defectos formales ni descubierto sobre el corte", INFLUYEN["descubierto"]
