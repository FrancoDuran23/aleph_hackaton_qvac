"""Cliente HTTP contra el bridge de QVAC.

Un solo lugar donde viven la URL, el token, los timeouts y el retry, para que
`brain.py` y `embeddings.py` no dupliquen esa lógica.

Sobre los timeouts: la inferencia corre en CPU sin GPU, así que una respuesta
de 500 tokens puede tardar decenas de segundos y la *primera* llamada además
descarga el modelo (cientos de MB). Por eso el default es alto y la conexión
tiene su propio timeout corto — así distinguimos "el bridge no está" (falla en
2s) de "el modelo está pensando" (tarda, pero funciona).
"""
import asyncio
import os
import time

import httpx

BRIDGE_URL = os.getenv("QVAC_BRIDGE_URL", "http://127.0.0.1:8081").rstrip("/")
BRIDGE_TOKEN = os.getenv("QVAC_BRIDGE_TOKEN", "")
TIMEOUT_INFERENCIA = float(os.getenv("QVAC_BRIDGE_TIMEOUT", "600"))
TIMEOUT_CONEXION = 5.0


class QvacBridgeError(RuntimeError):
    """El bridge respondió un error, o no se pudo llegar a él."""


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(TIMEOUT_INFERENCIA, connect=TIMEOUT_CONEXION)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {BRIDGE_TOKEN}"} if BRIDGE_TOKEN else {}


def pedir(ruta: str, payload: dict, max_retries: int = 3) -> dict:
    """POST al bridge con retry y backoff exponencial.

    Reintenta errores de red y 5xx. Un 4xx es culpa nuestra (payload mal armado,
    token inválido): reintentarlo solo hace perder tiempo, así que corta.
    """
    url = f"{BRIDGE_URL}{ruta}"
    ultimo_error: Exception | None = None

    for intento in range(max_retries):
        try:
            respuesta = httpx.post(url, json=payload, headers=_headers(), timeout=_timeout())
        except httpx.HTTPError as e:
            ultimo_error = e
        else:
            if respuesta.status_code < 400:
                return respuesta.json()
            if respuesta.status_code < 500:
                # 4xx es culpa nuestra (payload mal armado, token inválido):
                # reintentarlo solo hace perder tiempo.
                raise QvacBridgeError(f"{respuesta.status_code} en {ruta}: {respuesta.text[:300]}")
            ultimo_error = QvacBridgeError(f"{respuesta.status_code}: {respuesta.text[:300]}")

        if intento < max_retries - 1:
            time.sleep(2 ** intento)

    raise QvacBridgeError(
        f"el bridge de QVAC no respondió en {BRIDGE_URL} tras {max_retries} intentos. "
        f"¿Levantaste el túnel SSH? Último error: {ultimo_error}"
    )


async def pedir_async(ruta: str, payload: dict, max_retries: int = 3) -> dict:
    """Versión async de `pedir`, con la misma política de retry.

    Usa httpx.AsyncClient de verdad (no `pedir` envuelto): una completion en CPU
    bloquea segundos, y hacerla sincrónica adentro de un handler de FastAPI
    congelaría el event loop y con él todas las demás requests.
    """
    url = f"{BRIDGE_URL}{ruta}"
    ultimo_error: Exception | None = None

    async with httpx.AsyncClient(timeout=_timeout()) as cliente:
        for intento in range(max_retries):
            try:
                respuesta = await cliente.post(url, json=payload, headers=_headers())
            except httpx.HTTPError as e:
                ultimo_error = e
            else:
                if respuesta.status_code < 400:
                    return respuesta.json()
                if respuesta.status_code < 500:
                    raise QvacBridgeError(f"{respuesta.status_code} en {ruta}: {respuesta.text[:300]}")
                ultimo_error = QvacBridgeError(f"{respuesta.status_code}: {respuesta.text[:300]}")

            if intento < max_retries - 1:
                await asyncio.sleep(2 ** intento)

    raise QvacBridgeError(
        f"el bridge de QVAC no respondió en {BRIDGE_URL} tras {max_retries} intentos. "
        f"¿Levantaste el túnel SSH? Último error: {ultimo_error}"
    )


def salud() -> dict:
    """GET /health — no requiere token. Útil para chequear que el túnel está vivo."""
    try:
        respuesta = httpx.get(f"{BRIDGE_URL}/health", timeout=httpx.Timeout(10, connect=TIMEOUT_CONEXION))
        respuesta.raise_for_status()
        return respuesta.json()
    except httpx.HTTPError as e:
        raise QvacBridgeError(f"no se pudo contactar al bridge en {BRIDGE_URL}: {e}") from e
