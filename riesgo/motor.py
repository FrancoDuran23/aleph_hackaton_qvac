"""Orquesta un caso completo: contradicciones -> calculo -> ruteo -> confianza.

Nada frena el ruteo. El sistema siempre produce un veredicto; lo que varia es
cuanta confianza declara tener. Un caso sale FIRME solo si ningun dato que
influyo en la decision arrastra reservas.
"""

from __future__ import annotations

from datetime import date

from .calculo import derivar
from .contradicciones import detectar
from .modelo import CONFIRMADA, GRAVE, PROBABLE, Advertencia, Alerta, Campo, Veredicto
from .ruteo import CORTE_DESCUBIERTO, rutear
from .validacion import cobertura_implausible


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
                    nombre, f"{campo.doc} produced no readable text: the value "
                            f"may exist and not have been read", degrada=pesa))
            else:
                avisos.append(Advertencia(nombre, "no data in the document", degrada=False))

    for h in hallazgos:
        if h.estado == PROBABLE:
            # Una contradiccion GRAVE que quedo en PROBABLE (p.ej. por venir de
            # OCR) no fuerza el ruteo, pero SI degrada el caso a CON RESERVAS:
            # hay un posible defecto de garantia que no se pudo confirmar. Mejor
            # que un analista lo mire, no que el caso salga FIRME y equivocado.
            avisos.append(Advertencia(h.tipo, f"unconfirmed finding: {h.detalle}",
                                      degrada=(h.gravedad == GRAVE)))

    return avisos


def _alertas(campos: dict[str, Campo]) -> list[Alerta]:
    """Los campos marcados por la validacion numerica (el companero, punto 2).

    Esta funcion solo empaqueta lo que ya esta en el Campo -- el detector que
    decide si un valor esta incompleto vive en la extraccion, no aca. Un campo
    sin `alerta_lectura` no genera nada.
    """
    return [
        Alerta(campo=nombre, crudo_ocr=c.crudo or "", motivo=c.alerta_lectura,
              documento=c.doc, pagina=c.pagina, confianza_ocr=c.ocr_confianza)
        for nombre, c in sorted(campos.items())
        if c.alerta_lectura is not None
    ]


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
    # Solo una contradiccion grave CONFIRMADA fuerza el ruteo a LEGALES. Una
    # PROBABLE (p.ej. un valor leido por OCR de baja confianza) no fuerza: queda
    # anotada y el caso sale CON RESERVAS para revision humana, en vez de mandar
    # a legales por un posible error de lectura.
    graves = [h for h in hallazgos if h.gravedad == "GRAVE" and h.estado == CONFIRMADA]

    # Detector B (punto 2, cross-campo): una cobertura implausible delata un
    # monto mal leido que paso las validaciones de campo -- p.ej. "ARS 457" ->
    # 457, un numero limpio pero con los ceros comidos, que ningun chequeo por
    # campo puede ver. Los financieros no son confiables: no se rutea por ellos
    # (no se fuerza LEGALES por un descubierto que sale de un numero roto) y el
    # caso se degrada con una alerta que lleva el crudo.
    gv = campos.get("garantia_valor", Campo(None))
    cap = campos.get("capital_adeudado", Campo(None))
    motivo_b = cobertura_implausible(gv.valor, cap.valor)
    derivados_ruteo = derivados
    alertas = _alertas(campos)
    advertencias_b: list[Advertencia] = []
    if motivo_b:
        derivados_ruteo = {**derivados, "descubierto": None, "cobertura": None}
        alertas = alertas + [Alerta(
            campo="garantia_valor/capital_adeudado",
            crudo_ocr=f"garantia={gv.crudo!r}, capital={cap.crudo!r}",
            motivo=motivo_b, documento=gv.doc or cap.doc,
            pagina=gv.pagina, confianza_ocr=gv.ocr_confianza)]
        advertencias_b.append(Advertencia(
            "capital/garantia",
            f"{motivo_b}: amount not trustworthy, review manually", degrada=True))

    aviso = campos.get("aviso_previo", Campo(None)).valor
    ruta, motivo, influyen = rutear(graves, derivados_ruteo, aviso, corte=corte)

    return Veredicto(
        cliente_id=cliente_id,
        nombre=nombre,
        ruteo=ruta,
        motivo=motivo,
        derivados=derivados,
        hallazgos=hallazgos,
        advertencias=_advertencias(campos, influyen, hallazgos, docs_ilegibles) + advertencias_b,
        alertas=alertas,
    )
