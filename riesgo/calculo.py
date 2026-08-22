"""Aritmetica del caso. Python puro: los modelos chicos son malos en cuentas.

Todo lo que devuelve es ``None`` cuando falta un insumo. No asumimos cero:
un descubierto de cero y un descubierto desconocido son cosas distintas, y
confundirlas manda un caso a la ruta equivocada con cara de certeza.
"""

from __future__ import annotations

from .modelo import Campo

TOLERANCIA_DIAS = 5


def descubierto(capital_adeudado: Campo, garantia_valor: Campo) -> float | None:
    """Cuanto de la deuda no cubre la garantia."""
    if capital_adeudado.vacio or garantia_valor.vacio:
        return None
    return max(0.0, float(capital_adeudado.valor) - float(garantia_valor.valor))


def cobertura(capital_adeudado: Campo, garantia_valor: Campo) -> float | None:
    """Que fraccion de la deuda cubre la garantia."""
    if capital_adeudado.vacio or garantia_valor.vacio:
        return None
    deuda = float(capital_adeudado.valor)
    if deuda == 0:
        return None
    return float(garantia_valor.valor) / deuda


def puntualidad(pagos: Campo) -> float | None:
    """Fraccion de pagos hechos a tiempo, con tolerancia de 5 dias.

    Acepta la lista de pagos o el valor ya calculado, para poder correr el
    motor contra el ground truth sin pasar por la extraccion.
    """
    if pagos.vacio:
        return None
    if isinstance(pagos.valor, (int, float)):
        return float(pagos.valor)
    if not pagos.valor:
        return None
    a_tiempo = sum(1 for p in pagos.valor if p.get("atraso_dias", 0) <= TOLERANCIA_DIAS)
    return a_tiempo / len(pagos.valor)


def derivar(campos: dict[str, Campo]) -> dict[str, float | None]:
    v = lambda k: campos.get(k, Campo(None))
    return {
        "descubierto": descubierto(v("capital_adeudado"), v("garantia_valor")),
        "cobertura": cobertura(v("capital_adeudado"), v("garantia_valor")),
        "puntualidad": puntualidad(v("puntualidad")),
    }
