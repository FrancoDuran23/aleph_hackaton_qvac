"""HITO 1 -- una inferencia local corriendo.

Prueba tres cosas, en orden de importancia:

  1. El modelo carga y responde. Si esto no pasa, no hay proyecto.
  2. ``response_format`` fuerza JSON valido de verdad (riesgo 1 del plan).
  3. Cuanto tarda una llamada del tamano real (riesgo 4 del plan).

Uso:  .venv/Scripts/python -m riesgo.hito1
"""

from __future__ import annotations

import asyncio
import json

from .llm import Motor, schema_json

# Un fragmento de contrato con las tres trampas del dataset juntas: el capital
# original y el adeudado en la misma linea, y tres formatos de monto distintos.
CONTRATO = """
CONTRATO DE PRESTAMO CON GARANTIA REAL

Titular: Juan Perez
Matricula del inmueble: 11-59965
Capital original otorgado: $ 2.400.000,00
Capital adeudado al dia de la fecha: ARS 1.494.000
Plazo pactado: 32 cuotas mensuales
Domicilio del titular: Av. Rivadavia 4471, CABA
"""

CAMPOS = {
    "capital_original": {"type": ["number", "null"]},
    "capital_adeudado": {"type": ["number", "null"]},
    "cuotas_contrato": {"type": ["integer", "null"]},
    "titular": {"type": ["string", "null"]},
    "matricula": {"type": ["string", "null"]},
    "domicilio_titular": {"type": ["string", "null"]},
}

ESPERADO = {
    "capital_original": 2400000,
    "capital_adeudado": 1494000,
    "cuotas_contrato": 32,
    "titular": "Juan Perez",
    "matricula": "11-59965",
}


def _linea(titulo: str) -> None:
    print(f"\n{'=' * 62}\n{titulo}\n{'=' * 62}")


async def main() -> int:
    _linea("1/3  cargando el modelo")
    async with Motor() as motor:
        print(f"\n  modelo listo en {motor.segundos_de_carga:.1f}s")

        _linea("2/3  inferencia libre")
        r = await motor.completar(
            [{"role": "user", "content": "Respondé en una sola línea: ¿qué es una hipoteca?"}],
            max_tokens=80,
        )
        print(f"  {r.texto.strip()[:200]}")
        print(f"\n  {r.segundos:.1f}s  |  {r.tokens_por_segundo or float('nan'):.1f} tok/s")

        _linea("3/3  extraccion con JSON forzado por gramatica")
        r = await motor.completar(
            [{"role": "user", "content":
              "Extraé los datos del documento. Si un dato no está, poné null. "
              "No inventes valores.\n\nDOCUMENTO:\n" + CONTRATO}],
            system="Sos un extractor de datos. Respondés solo con JSON.",
            schema=schema_json("campos_contrato", CAMPOS),
            max_tokens=300,
        )
        print(f"  crudo: {r.texto.strip()[:300]}")
        print(f"\n  {r.segundos:.1f}s  |  truncada={r.truncada}  |  stop={r.stop_reason}")

        try:
            datos = json.loads(r.texto)
        except json.JSONDecodeError as e:
            print(f"\n  FALLO: el JSON no parsea -> {e}")
            return 1

        print("\n  campo                 extraido              esperado")
        print("  " + "-" * 58)
        aciertos = 0
        for campo, esperado in ESPERADO.items():
            obtenido = datos.get(campo)
            ok = obtenido == esperado
            aciertos += ok
            print(f"  {'OK ' if ok else '!! '}{campo:<18} {str(obtenido)[:20]:<21} {esperado}")

        print(f"\n  {aciertos}/{len(ESPERADO)} campos correctos")
        return 0 if aciertos == len(ESPERADO) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
