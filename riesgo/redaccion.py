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
import re

from .modelo import Veredicto

SISTEMA = ("You are a credit risk analyst. You write brief internal notes in "
           "neutral English, with no greetings or signature.")

_PLANTILLA = """Write a 3 to 5 line internal note for a risk analyst.

Use ONLY these facts. Do not add information, estimates, or recommendations
that are not here. Do not repeat the numbers as a list: write prose.

Write every amount EXACTLY as given (e.g. "$4,262,000"). Do NOT reformat,
round, or rescale it -- never turn it into "4.262 million" or similar.

{hechos}"""

# Etiqueta de ruteo en ingles para la nota; el valor interno (v.ruteo) no cambia.
_RUTEO_EN = {"LEGALES": "LEGAL", "REFINANCIACION": "REFINANCE", "COBRANZAS": "COLLECTIONS"}

# Nombres legibles de cada tipo de contradiccion -- los identificadores internos
# (titular_garantia, etc.) no deben filtrarse a la prosa de la nota.
_TIPO_EN = {
    "titular_garantia": "collateral holder mismatch",
    "matricula_distinta": "registry number mismatch",
    "cuotas_no_coinciden": "installment count mismatch",
    "tasacion_vencida": "expired appraisal",
    "domicilio_distinto": "address mismatch",
}


def hechos_de(v: Veredicto) -> dict:
    """El veredicto reducido a lo que la nota necesita saber.

    Deliberadamente sin páginas ni nombres de archivo: la cita va en la
    pantalla, no en la prosa, y meterla en el prompt invita al modelo a
    inventar referencias.
    """
    d = v.derivados
    hechos: dict = {"client": v.nombre,
                    "routing": _RUTEO_EN.get(v.ruteo, v.ruteo),
                    "reason": v.motivo}

    if d.get("descubierto") is not None:
        # Formato ingles sin ambiguedad ("$4,262,000"): la coma agrupa miles y
        # no hay palabra de escala que el modelo pueda malinterpretar.
        hechos["shortfall"] = f"${d['descubierto']:,.0f}"
    if d.get("cobertura") is not None:
        hechos["collateral_coverage"] = f"{d['cobertura']:.0%}"
    if d.get("puntualidad") is not None:
        hechos["on_time_payments"] = f"{d['puntualidad']:.0%}"

    if v.hallazgos:
        hechos["contradictions"] = [
            {"type": _TIPO_EN.get(h.tipo, h.tipo), "severity": h.gravedad,
             "state": h.estado}
            for h in v.hallazgos
        ]
    reservas = [a.motivo for a in v.advertencias if a.degrada]
    if reservas:
        hechos["could_not_verify"] = reservas

    return hechos


async def redactar(motor, v: Veredicto, max_tokens: int = 512) -> str | None:
    """La nota, o None si el modelo no responde. Nunca levanta."""
    prompt = _PLANTILLA.format(
        hechos=json.dumps(hechos_de(v), ensure_ascii=False, indent=2))
    try:
        r = await motor.completar([{"role": "user", "content": prompt}],
                                  system=SISTEMA, max_tokens=max_tokens)
    except Exception:
        return None
    # QWEN3 emite su razonamiento en <think>...</think>; el razonamiento NUNCA
    # va a pantalla. Se sacan los bloques completos; si quedo un <think> sin
    # cerrar (respuesta truncada dentro del razonamiento) no hay nota utilizable
    # y se descarta entera, en vez de mostrar el razonamiento crudo. max_tokens
    # alto deja lugar para el razonamiento y la nota completa.
    texto = re.sub(r"<think>.*?</think>", "", r.texto, flags=re.DOTALL)
    if "<think>" in texto or "</think>" in texto:
        return None
    texto = texto.strip()
    return texto or None
