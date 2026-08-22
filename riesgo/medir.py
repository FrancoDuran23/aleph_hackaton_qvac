"""Determinismo y latencia. Los dos números que condicionan todo lo demás.

**Determinismo.** Corre la misma extracción N veces y compara las salidas byte
a byte. Si difieren, `generationParams` no está llegando al motor y la
inferencia corre con sampling por defecto: todo lo que se mida después es
ruido. El test barato de dos tokens no alcanza — con salidas cortas dos
corridas pueden coincidir por azar. Acá se compara una extracción real de
varios cientos de caracteres.

**Latencia.** Segundos por caso, en caliente. La primera llamada incluye cold
start (carga del modelo, o bootstrap de la DHT si es delegada) y no representa
nada; se descarta. Es requisito de entrega, y es el dato que define si se puede
pagar un segundo pase o más campos por llamada.

Uso:
    .venv/Scripts/python -m riesgo.medir --bridge
    .venv/Scripts/python -m riesgo.medir --bridge --corridas 5
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
from difflib import unified_diff

from .bridge import MotorBridge
from .hito1 import CAMPOS, PROMPT_EXTRACCION
from .llm import Motor, schema_json

SISTEMA = "Sos un extractor de datos. Respondés solo con JSON."


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def _informe_determinismo(salidas: list[str]) -> bool:
    hashes = [_sha(s) for s in salidas]
    unicos = set(hashes)

    print(f"\n{'=' * 66}\nDETERMINISMO -- {len(salidas)} corridas, comparación byte a byte\n{'=' * 66}")
    for i, (h, s) in enumerate(zip(hashes, salidas), 1):
        print(f"  corrida {i}:  sha256={h}  {len(s):>4} chars")

    if len(unicos) == 1:
        print(f"\n  OK  las {len(salidas)} salidas son idénticas byte a byte")
        print(f"      temp=0 está llegando al motor")
        return True

    print(f"\n  FALLO  {len(unicos)} salidas distintas entre {len(salidas)} corridas")
    print(f"         generationParams NO está llegando: la inferencia corre con")
    print(f"         sampling por defecto y ninguna medición posterior es válida.")
    print(f"         Revisar que el campo se llame 'temp' (no 'temperature') y")
    print(f"         que viaje anidado en generationParams, no top-level.\n")
    base = salidas[0].splitlines(keepends=True)
    for i, otra in enumerate(salidas[1:], 2):
        d = list(unified_diff(base, otra.splitlines(keepends=True),
                              fromfile="corrida 1", tofile=f"corrida {i}", n=0))
        if d:
            print(f"  --- diferencias 1 vs {i} ---")
            print("".join("    " + l for l in d[:14]))
    return False


def _informe_latencia(tiempos: list[float], tokens_seg: list[float]) -> None:
    frio, calientes = tiempos[0], tiempos[1:]
    print(f"\n{'=' * 66}\nLATENCIA -- extracción de {len(CAMPOS)} campos\n{'=' * 66}")
    print(f"  primera llamada (en frío):  {frio:.1f} s   <- se descarta")
    if not calientes:
        print("  sin corridas en caliente: usar --corridas 2 o más")
        return

    media = statistics.mean(calientes)
    print(f"\n  en caliente ({len(calientes)} corridas)")
    print(f"    media    {media:.1f} s")
    print(f"    mediana  {statistics.median(calientes):.1f} s")
    print(f"    rango    {min(calientes):.1f} - {max(calientes):.1f} s")
    if tokens_seg:
        print(f"    throughput {statistics.mean(tokens_seg):.1f} tok/s")

    # Lo que importa para decidir: cuánto cuesta una vuelta completa.
    docs_por_caso, casos = 4, 20
    total = media * docs_por_caso * casos
    print(f"\n  proyección: {casos} casos x {docs_por_caso} documentos")
    print(f"    {total / 60:.0f} min por iteración completa")
    if media > 15:
        print(f"\n  AVISO  {media:.0f}s por llamada es caro. Antes de bajar de modelo,")
        print(f"         reducir campos por llamada -- cuesta menos calidad.")
    elif total / 60 > 20:
        print(f"\n  AVISO  una iteración completa no entra en una pausa de café.")
        print(f"         Iterar sobre 5 casos y correr los 20 solo al final.")


async def main(bridge: bool, provider: str | None, corridas: int) -> int:
    motor_ctx = MotorBridge() if bridge else Motor(provider=provider)
    salidas: list[str] = []
    tiempos: list[float] = []
    tokens_seg: list[float] = []

    async with motor_ctx as motor:
        print(f"  modelo: {getattr(motor, 'modelo', '?')}")
        for i in range(corridas):
            r = await motor.completar(
                [{"role": "user", "content": PROMPT_EXTRACCION}],
                system=SISTEMA,
                schema=schema_json("campos_contrato", CAMPOS),
                max_tokens=300,
            )
            salidas.append(r.texto)
            tiempos.append(r.segundos)
            if r.tokens_por_segundo:
                tokens_seg.append(r.tokens_por_segundo)
            print(f"  corrida {i + 1}/{corridas} -- {r.segundos:.1f}s")

    determinista = _informe_determinismo(salidas)
    _informe_latencia(tiempos, tokens_seg[1:] if len(tokens_seg) > 1 else tokens_seg)

    # La salida tiene que ser JSON válido además de estable: un modelo que
    # devuelve siempre la misma basura también es determinista.
    try:
        json.loads(salidas[0])
        print(f"\n  la salida parsea como JSON")
    except json.JSONDecodeError as e:
        print(f"\n  AVISO  la salida no parsea como JSON: {e}")
        return 1

    return 0 if determinista else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", action="store_true")
    ap.add_argument("--provider")
    ap.add_argument("--corridas", type=int, default=3)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.bridge, a.provider, a.corridas)))
