"""La nota interna: el único lugar donde el modelo escribe libre.

Y aun así no ve los documentos. Recibe **hechos ya validados** —los campos que
pasaron grounding, los números que calculó Python, la ruta que decidió el
código— y los redacta. Pasar hechos en vez de texto crudo acota la superficie
de alucinación a la redacción misma: el modelo puede elegir mal una palabra,
no puede inventar un monto que no le dimos.

Si la nota falla, el caso no se cae: sale sin nota. Es prosa de cortesía sobre
un veredicto que ya está tomado.
"""

from __future__ import annotations

import json

from .modelo import Veredicto

SISTEMA = ("Sos un analista de riesgo crediticio. Escribís notas internas "
           "breves, en español rioplatense neutro, sin saludos ni firma.")

_PLANTILLA = """Redactá una nota interna de 3 a 5 líneas para un analista de riesgo.

Usá ÚNICAMENTE estos hechos. No agregues información, estimaciones ni
recomendaciones que no estén acá. No repitas los números en formato de lista:
escribí prosa.

{hechos}"""


def hechos_de(v: Veredicto) -> dict:
    """El veredicto reducido a lo que la nota necesita saber.

    Deliberadamente sin páginas ni nombres de archivo: la cita va en la
    pantalla, no en la prosa, y meterla en el prompt invita al modelo a
    inventar referencias.
    """
    d = v.derivados
    hechos: dict = {"cliente": v.nombre, "ruteo": v.ruteo, "motivo": v.motivo}

    if d.get("descubierto") is not None:
        hechos["descubierto"] = f"${d['descubierto']:,.0f}".replace(",", ".")
    if d.get("cobertura") is not None:
        hechos["cobertura_garantia"] = f"{d['cobertura']:.0%}"
    if d.get("puntualidad") is not None:
        hechos["pagos_puntuales"] = f"{d['puntualidad']:.0%}"

    if v.hallazgos:
        hechos["contradicciones"] = [
            {"tipo": h.tipo, "gravedad": h.gravedad, "estado": h.estado}
            for h in v.hallazgos
        ]
    reservas = [a.motivo for a in v.advertencias if a.degrada]
    if reservas:
        hechos["no_se_pudo_verificar"] = reservas

    return hechos


async def redactar(motor, v: Veredicto, max_tokens: int = 220) -> str | None:
    """La nota, o None si el modelo no responde. Nunca levanta."""
    prompt = _PLANTILLA.format(
        hechos=json.dumps(hechos_de(v), ensure_ascii=False, indent=2))
    try:
        r = await motor.completar([{"role": "user", "content": prompt}],
                                  system=SISTEMA, max_tokens=max_tokens)
    except Exception:
        return None
    texto = r.texto.strip()
    return texto or None
