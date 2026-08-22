"""Orquesta un caso completo: contradicciones -> calculo -> ruteo -> confianza.

Nada frena el ruteo. El sistema siempre produce un veredicto; lo que varia es
cuanta confianza declara tener. Un caso sale FIRME solo si ningun dato que
influyo en la decision arrastra reservas.
"""

from __future__ import annotations

from datetime import date

from .calculo import derivar
from .contradicciones import detectar
from .modelo import PROBABLE, Advertencia, Campo, Veredicto
from .ruteo import CORTE_DESCUBIERTO, rutear


def _advertencias(campos: dict[str, Campo], influyen: tuple[str, ...],
                  hallazgos: list, docs_ilegibles: set[str]) -> list[Advertencia]:
    """Todo lo que el sistema no pudo garantizar. Se anota siempre.

    Solo degrada el caso lo que afecto a un campo que influyo en el ruteo:
    una reserva sobre un dato que no movio la aguja es ruido, no incertidumbre.
    """
    avisos: list[Advertencia] = []

    for nombre, campo in sorted(campos.items()):
        pesa = nombre in influyen

        motivo = campo.reserva()
        if motivo:
            avisos.append(Advertencia(nombre, motivo, degrada=pesa))
            continue

        if campo.vacio:
            # Un campo nulo es honesto... salvo que sea nulo porque el
            # documento no se pudo leer. Eso no es ausencia de dato, es una
            # falla silenciosa: sin OCR la escritura extrae vacio, no se
            # detecta ninguna contradiccion y el caso rutea como si estuviera
            # limpio. Ese es el peor error posible de este sistema.
            if campo.doc in docs_ilegibles:
                avisos.append(Advertencia(
                    nombre, f"{campo.doc} no produjo texto legible: el dato "
                            f"puede existir y no haberse leido", degrada=pesa))
            else:
                avisos.append(Advertencia(nombre, "sin dato en el documento", degrada=False))

    for h in hallazgos:
        if h.estado == PROBABLE:
            avisos.append(Advertencia(h.tipo, f"hallazgo no confirmado: {h.detalle}",
                                      degrada=False))

    return avisos


def analizar(cliente_id: int, campos: dict[str, Campo], *,
             nombre: str | None = None,
             docs_ilegibles: set[str] | None = None,
             corte: float = CORTE_DESCUBIERTO,
             hoy: date | None = None) -> Veredicto:
    """Un caso de punta a punta, a partir de campos ya extraidos.

    ``docs_ilegibles`` son los documentos que no produjeron texto (escaneados
    sin OCR). Los campos que salieron nulos por culpa de esos documentos
    degradan el caso en vez de pasar como ausencias legitimas.
    """
    docs_ilegibles = docs_ilegibles or set()

    hallazgos = detectar(campos, hoy=hoy)
    derivados = derivar(campos)
    graves = [h for h in hallazgos if h.gravedad == "GRAVE"]

    aviso = campos.get("aviso_previo", Campo(None)).valor
    ruta, motivo, influyen = rutear(graves, derivados, aviso, corte=corte)

    return Veredicto(
        cliente_id=cliente_id,
        nombre=nombre,
        ruteo=ruta,
        motivo=motivo,
        derivados=derivados,
        hallazgos=hallazgos,
        advertencias=_advertencias(campos, influyen, hallazgos, docs_ilegibles),
    )
