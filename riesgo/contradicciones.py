"""Deteccion de contradicciones entre documentos de una carpeta.

Comparo campos ya extraidos. No le pregunto al modelo "busca inconsistencias":
es una consigna demasiado abierta para un modelo chico y genera falsos
positivos. El modelo extrae, el codigo decide.

Cada chequeo devuelve un :class:`Hallazgo` con estado:

    CONFIRMADA   ambos valores con grounding solido, y difieren
    PROBABLE     difieren, pero al menos uno tiene senal debil
    DESCARTADA   no difieren (o falta un lado para poder comparar)
"""

from __future__ import annotations

from datetime import date

from dateutil import parser as fechas

from .comparacion import misma_persona, mismo_numero, norm, similitud_nombres
from .modelo import (BAJA, CONFIRMADA, DESCARTADA, GRAVE, MEDIA, PROBABLE,
                     Campo, Hallazgo)

ANIOS_TASACION_VALIDA = 5

# Zona gris: difieren, pero no tanto como para estar seguros. Se reporta como
# PROBABLE en vez de CONFIRMADA. No degrada el caso, solo se anota.
ZONA_GRIS = (0.80, 0.85)


def _estado(a: Campo, b: Campo, difieren: bool, dudoso: bool = False) -> str:
    """CONFIRMADA solo si difieren y ambos lados son confiables."""
    if not difieren:
        return DESCARTADA
    if dudoso or not a.confiable or not b.confiable:
        return PROBABLE
    return CONFIRMADA


def _comparables(a: Campo, b: Campo) -> bool:
    """Sin los dos valores no hay contradiccion: hay un dato faltante.

    Esa ausencia se anota como advertencia aparte, no como hallazgo.
    """
    return not a.vacio and not b.vacio


def titular_garantia(titular_contrato: Campo, titular_escritura: Campo) -> Hallazgo:
    """La escritura a nombre de otra persona: la garantia puede no ser ejecutable."""
    if not _comparables(titular_contrato, titular_escritura):
        return Hallazgo("titular_garantia", GRAVE, DESCARTADA,
                        "falta el titular de alguno de los dos documentos")

    sim = similitud_nombres(str(titular_contrato.valor), str(titular_escritura.valor))
    difieren = not misma_persona(str(titular_contrato.valor), str(titular_escritura.valor))
    dudoso = ZONA_GRIS[0] <= sim < ZONA_GRIS[1]

    return Hallazgo(
        "titular_garantia", GRAVE,
        _estado(titular_contrato, titular_escritura, difieren, dudoso),
        f"Escritura a nombre de {titular_escritura.valor!r} "
        f"{titular_escritura.cita()}; titular del prestamo {titular_contrato.valor!r} "
        f"{titular_contrato.cita()}. Garantia posiblemente no ejecutable. "
        f"(similitud {sim:.2f})",
        (str(titular_contrato.doc), str(titular_escritura.doc)),
    )


def matricula_distinta(mat_contrato: Campo, mat_escritura: Campo) -> Hallazgo:
    """La escritura describe otro inmueble que el que garantiza el prestamo."""
    if not _comparables(mat_contrato, mat_escritura):
        return Hallazgo("matricula_distinta", GRAVE, DESCARTADA,
                        "falta la matricula de alguno de los dos documentos")

    difieren = norm(str(mat_contrato.valor)) != norm(str(mat_escritura.valor))
    return Hallazgo(
        "matricula_distinta", GRAVE,
        _estado(mat_contrato, mat_escritura, difieren),
        f"Matricula en escritura {mat_escritura.valor!r} {mat_escritura.cita()} "
        f"vs contrato {mat_contrato.valor!r} {mat_contrato.cita()}.",
        (str(mat_contrato.doc), str(mat_escritura.doc)),
    )


def cuotas_no_coinciden(cuotas: Campo, pagos: Campo) -> Hallazgo:
    """El contrato pacta N cuotas pero existen M recibos."""
    if not _comparables(cuotas, pagos):
        return Hallazgo("cuotas_no_coinciden", MEDIA, DESCARTADA,
                        "faltan las cuotas del contrato o los recibos")

    emitidos = pagos.valor if isinstance(pagos.valor, int) else len(pagos.valor)
    difieren = not mismo_numero(cuotas.valor, emitidos)
    return Hallazgo(
        "cuotas_no_coinciden", MEDIA,
        _estado(cuotas, pagos, difieren),
        f"El contrato estipula {cuotas.valor} cuotas {cuotas.cita()} "
        f"pero existen {emitidos} recibos emitidos {pagos.cita()}.",
        (str(cuotas.doc), str(pagos.doc)),
    )


def tasacion_vencida(tasacion: Campo, hoy: date | None = None) -> Hallazgo:
    """Una tasacion vieja no respalda el valor actual de la garantia."""
    if tasacion.vacio:
        return Hallazgo("tasacion_vencida", MEDIA, DESCARTADA, "no hay fecha de tasacion")

    hoy = hoy or date.today()
    try:
        anio = fechas.parse(str(tasacion.valor), dayfirst=True).year
    except (ValueError, OverflowError):
        return Hallazgo("tasacion_vencida", MEDIA, PROBABLE,
                        f"no se pudo interpretar la fecha de tasacion "
                        f"{tasacion.valor!r} {tasacion.cita()}")

    vencida = anio < hoy.year - ANIOS_TASACION_VALIDA
    return Hallazgo(
        "tasacion_vencida", MEDIA,
        DESCARTADA if not vencida else (CONFIRMADA if tasacion.confiable else PROBABLE),
        f"Tasacion con fecha {tasacion.valor} {tasacion.cita()}: "
        f"{hoy.year - anio} anios de antiguedad.",
        (str(tasacion.doc),),
    )


def domicilio_distinto(dom_contrato: Campo, dom_escritura: Campo) -> Hallazgo:
    """Domicilios del TITULAR que no coinciden.

    Ojo: la escritura trae dos domicilios, el del titular y el del inmueble.
    El que se compara es el del titular. Confundirlos es un falso positivo
    en cada caso del dataset.
    """
    if not _comparables(dom_contrato, dom_escritura):
        return Hallazgo("domicilio_distinto", BAJA, DESCARTADA,
                        "falta el domicilio del titular en alguno de los documentos")

    from rapidfuzz import fuzz
    sim = fuzz.token_sort_ratio(norm(str(dom_contrato.valor)),
                                norm(str(dom_escritura.valor))) / 100
    difieren = sim < 0.90
    return Hallazgo(
        "domicilio_distinto", BAJA,
        _estado(dom_contrato, dom_escritura, difieren),
        f"Domicilio del titular: {dom_escritura.valor!r} {dom_escritura.cita()} "
        f"vs {dom_contrato.valor!r} {dom_contrato.cita()}. (similitud {sim:.2f})",
        (str(dom_contrato.doc), str(dom_escritura.doc)),
    )


def detectar(campos: dict[str, Campo], hoy: date | None = None) -> list[Hallazgo]:
    """Corre los cinco chequeos y devuelve solo los que dieron algo."""
    v = lambda k: campos.get(k, Campo(None))
    todos = [
        titular_garantia(v("titular_contrato"), v("titular_escritura")),
        matricula_distinta(v("matricula_contrato"), v("matricula_escritura")),
        cuotas_no_coinciden(v("cuotas_contrato"), v("pagos_emitidos")),
        tasacion_vencida(v("tasacion_fecha"), hoy),
        domicilio_distinto(v("domicilio_contrato"), v("domicilio_escritura")),
    ]
    return [h for h in todos if h.cuenta]
