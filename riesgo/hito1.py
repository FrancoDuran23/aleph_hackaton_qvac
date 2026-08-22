"""HITO 1 -- una inferencia local corriendo.

Sigue el protocolo de primera corrida del SDD 2, seccion 6. El orden importa:
cada paso valida el anterior, asi que cuando algo falla se sabe donde esta el
problema en vez de tener que adivinar entre el prompt, el transporte y el
pipeline.

    1. inferencia pelada          el modelo carga y responde
    2. determinismo               temp:0 llega de verdad al motor
    3. JSON por gramatica         response_format restringe el decoder
    4. extraccion real            recien aca, un documento del dataset

El paso 2 es el que atrapa el bug caro: si `generationParams` no llega, la
inferencia corre con sampling por defecto y nada lo delata salvo que la misma
entrada devuelva salidas distintas.

Uso:
    .venv/Scripts/python -m riesgo.hito1                      # SDK local
    .venv/Scripts/python -m riesgo.hito1 --bridge             # bridge HTTP
    .venv/Scripts/python -m riesgo.hito1 --provider <clave>   # delegado P2P
"""

from __future__ import annotations

import argparse
import asyncio
import json

from .bridge import MotorBridge
from .llm import Motor, schema_json

# Un fragmento de contrato con las trampas del dataset juntas: capital original
# y adeudado en la misma pagina, y montos en tres formatos distintos.
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

PROMPT_EXTRACCION = (
    "Extraé los datos del documento. Si un dato no está, poné null. "
    "No inventes valores.\n\nDOCUMENTO:\n" + CONTRATO
)


def paso(n: int, titulo: str) -> None:
    print(f"\n{'=' * 64}\n{n}/4  {titulo}\n{'=' * 64}")


async def main(provider: str | None, bridge: bool) -> int:
    fallos: list[str] = []

    paso(1, "inferencia pelada")
    motor_ctx = MotorBridge() if bridge else Motor(provider=provider)
    async with motor_ctx as motor:
        donde = ("bridge HTTP" if bridge else
                 f"delegada a {provider[:16]}..." if motor.delegado else "SDK local")
        print(f"  modelo listo en {motor.segundos_de_carga:.1f}s ({donde})")

        r = await motor.completar(
            [{"role": "user", "content": "Respondé en una sola línea: ¿qué es una hipoteca?"}],
            max_tokens=80,
        )
        print(f"  {r.texto.strip()[:180]}")
        if not r.texto.strip():
            fallos.append("el modelo devolvio texto vacio")

        # La primera llamada incluye el cold start (bootstrap de la DHT si es
        # delegada: de 15 a 45s). La latencia se mide en caliente.
        print(f"  {r.segundos:.1f}s (en frio, no es la latencia real)")

        paso(2, "determinismo -- generationParams llega de verdad")
        pregunta = [{"role": "user", "content":
                     "Elegí un número entero entre 1 y 1000. Respondé solo el número."}]
        salidas = [(await motor.completar(pregunta, max_tokens=16)).texto.strip()
                   for _ in range(3)]
        print(f"  tres corridas con temp=0: {salidas}")
        if len(set(salidas)) == 1:
            print("  OK  misma entrada -> misma salida")
        else:
            print("  FALLO  las salidas difieren: temp=0 NO esta llegando al motor")
            print("         revisar que generationParams viaje anidado y que el campo")
            print("         se llame 'temp', no 'temperature'")
            fallos.append("la inferencia no es determinista")

        paso(3, "JSON garantizado por gramatica")
        r = await motor.completar(
            [{"role": "user", "content": PROMPT_EXTRACCION}],
            system="Sos un extractor de datos. Respondés solo con JSON.",
            schema=schema_json("campos_contrato", CAMPOS),
            max_tokens=300,
        )
        print(f"  crudo: {r.texto.strip()[:260]}")
        print(f"  {r.segundos:.1f}s (en caliente)  truncada={r.truncada}  stop={r.stop_reason}")

        try:
            datos = json.loads(r.texto)
            print("  OK  parsea sin limpiar backticks ni recortar nada")
        except json.JSONDecodeError as e:
            print(f"  FALLO  el JSON no parsea: {e}")
            return 1

        sobrantes = set(datos) - set(CAMPOS)
        if sobrantes:
            print(f"  aviso: el modelo agrego campos fuera del schema: {sobrantes}")

        paso(4, "extraccion real -- contra los valores del documento")
        print(f"  {'campo':<20} {'extraido':<22} esperado")
        print("  " + "-" * 58)
        aciertos = 0
        for campo, esperado in ESPERADO.items():
            obtenido = datos.get(campo)
            ok = obtenido == esperado
            aciertos += ok
            print(f"  {'OK ' if ok else '!! '}{campo:<17} {str(obtenido)[:21]:<22} {esperado}")
        print(f"\n  {aciertos}/{len(ESPERADO)} campos correctos")

        if r.tokens_por_segundo:
            print(f"  {r.tokens_por_segundo:.1f} tok/s")
        if r.segundos > 15:
            print(f"  aviso: {r.segundos:.0f}s por llamada. Con 20 casos son "
                  f"{r.segundos * 20 / 60:.0f} min por iteracion -- bajar campos o modelo.")

    print(f"\n{'=' * 64}")
    if fallos:
        print("HITO 1 CON FALLOS:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("HITO 1 OK -- hay proyecto")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", help="clave publica del provider (delegated inference)")
    ap.add_argument("--bridge", action="store_true", help="usar el bridge HTTP (tunel SSH)")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.provider, a.bridge)))
