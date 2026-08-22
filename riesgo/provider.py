"""Lado provider de delegated inference: se corre en el server, no en la laptop.

Publica este proceso en la DHT de Hyperswarm con su clave publica y espera
consumers. Reemplaza al bridge HTTP: la auth es el firewall por clave publica
y el cifrado es end-to-end, ambos del SDK, sin codigo propio en el medio.

Uso, en el server:

    QVAC_HYPERSWARM_SEED=<64 hex> .venv/bin/python -m riesgo.provider \
        --permitir <clave_publica_del_consumer>

Imprime la clave publica del provider. Esa clave va al consumer:

    Motor(provider="<clave>")

``QVAC_HYPERSWARM_SEED`` fija la identidad: sin el seed la clave cambia en
cada arranque y hay que volver a copiarla a mano.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal

from tetherto.qvac_sdk import Client, provide, stop_provide
from tetherto.qvac_sdk.schemas import ProvideRequest, StopProvideRequest


async def servir(permitidos: list[str]) -> int:
    """Publica el provider y bloquea hasta recibir SIGINT/SIGTERM.

    ``mode: "allow"`` con una lista vacia no deja entrar a nadie. Es el default
    a proposito: un provider abierto es inferencia gratis para cualquiera que
    escanee la DHT.
    """
    if not permitidos:
        print("ERROR: sin --permitir no entra ningun consumer.")
        print("Pasa la clave publica del consumer, o --abierto si sabes lo que haces.")
        return 2

    if not os.environ.get("QVAC_HYPERSWARM_SEED"):
        print("aviso: sin QVAC_HYPERSWARM_SEED la clave publica cambia en cada arranque")

    async with Client() as cliente:
        transport = cliente.transport
        res = await provide(transport, ProvideRequest(
            firewall={"mode": "allow", "publicKeys": permitidos},
        ))
        if not res.success:
            print(f"ERROR al publicar el provider: {res.error}")
            return 1

        print(f"\n  provider arriba")
        print(f"  clave publica: {res.public_key}")
        print(f"  consumers permitidos: {len(permitidos)}")
        print(f"\n  en el consumer:  Motor(provider={res.public_key!r})")
        print(f"\n  ctrl-c para bajar\n")

        parar = asyncio.Event()
        bucle = asyncio.get_running_loop()
        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                bucle.add_signal_handler(s, parar.set)
            except NotImplementedError:
                pass  # Windows no soporta add_signal_handler para SIGTERM
        try:
            await parar.wait()
        except KeyboardInterrupt:
            pass
        finally:
            await stop_provide(transport, StopProvideRequest())
            print("  provider bajado")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--permitir", action="append", default=[], metavar="CLAVE",
                    help="clave publica de un consumer autorizado (repetible)")
    ap.add_argument("--abierto", action="store_true",
                    help="acepta cualquier consumer. No usar fuera de una demo controlada.")
    args = ap.parse_args()

    if args.abierto:
        print("aviso: provider ABIERTO, cualquiera que tenga la clave puede inferir")
        return asyncio.run(servir(["*"]))
    return asyncio.run(servir(args.permitir))


if __name__ == "__main__":
    raise SystemExit(main())
