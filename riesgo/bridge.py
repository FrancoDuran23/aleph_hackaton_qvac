"""Transporte HTTP contra el bridge de QVAC (el modelo vive en otro server).

Misma superficie que :class:`riesgo.llm.Motor`, asi que el resto del pipeline
no sabe -- ni le importa -- si la inferencia corre local, delegada por DHT o
detras de este bridge.

Config por entorno (.env):

    QVAC_BRIDGE_URL      http://127.0.0.1:8081  (a traves del tunel SSH)
    QVAC_BRIDGE_TOKEN    el que imprimio provision.sh
    QVAC_BRIDGE_TIMEOUT  segundos; alto a proposito, en CPU una respuesta
                         larga tarda decenas de segundos
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from .llm import PARAMS_DETERMINISTAS, Respuesta, schema_json  # noqa: F401

# Qwen3 razona antes de responder. Para extraccion eso es desperdicio puro: el
# modelo no tiene que deducir nada, solo copiar campos que ya estan en el
# texto. Medido contra el bridge: la misma respuesta cuesta 58 tokens con
# thinking y 9 sin el. A ~20 tok/s en CPU, es la diferencia entre 2,9s y 0,45s
# por llamada -- multiplicado por 20 casos y varias iteraciones, es la noche.
SIN_RAZONAMIENTO = {"reasoning_budget": 0}

# Conectar falla rapido ("el bridge no esta"); generar puede tardar
# ("el modelo esta pensando").
TIMEOUT_CONEXION = 5.0


def cargar_env(ruta: str | Path = ".env") -> None:
    """Lee un .env sin dependencias. Las variables ya presentes no se pisan."""
    p = Path(ruta)
    if not p.exists():
        return
    for linea in p.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, _, v = linea.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


class MotorBridge:
    """Modelo remoto detras del bridge HTTP.

    Uso identico a :class:`riesgo.llm.Motor`:

        async with MotorBridge() as motor:
            r = await motor.completar([{"role": "user", "content": "hola"}])
    """

    def __init__(self, url: str | None = None, token: str | None = None,
                 timeout: float | None = None, razonar: bool = False,
                 verboso: bool = True) -> None:
        cargar_env()
        self.url = (url or os.environ.get("QVAC_BRIDGE_URL", "http://127.0.0.1:8081")).rstrip("/")
        self.token = token or os.environ.get("QVAC_BRIDGE_TOKEN", "")
        self.timeout = timeout or float(os.environ.get("QVAC_BRIDGE_TIMEOUT", 600))
        self.razonar = razonar
        self.verboso = verboso
        self.segundos_de_carga = 0.0
        self.modelo: str | None = None
        self._http: httpx.AsyncClient | None = None

    delegado = False

    async def __aenter__(self) -> "MotorBridge":
        inicio = time.perf_counter()
        self._http = httpx.AsyncClient(
            base_url=self.url,
            timeout=httpx.Timeout(self.timeout, connect=TIMEOUT_CONEXION),
            headers={"authorization": f"Bearer {self.token}"} if self.token else {},
        )
        try:
            salud = (await self._http.get("/health")).json()
        except httpx.HTTPError as e:
            await self._http.aclose()
            raise RuntimeError(
                f"no se pudo contactar el bridge en {self.url}: {e}\n"
                f"  el tunel SSH suele ser la causa: ./scripts/qvac/tunnel.sh <IP>"
            ) from e

        self.modelo = salud.get("llm")
        # Si el modelo ya estaba cargado no hay carga que medir; el numero solo
        # es real la primera vez que el bridge arranca.
        self.segundos_de_carga = time.perf_counter() - inicio
        if self.verboso:
            cargados = salud.get("cargados") or []
            print(f"  bridge OK  modelo={self.modelo}  "
                  f"{'ya cargado' if self.modelo in cargados else 'se cargara en la 1a llamada'}")
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def completar(self, messages: list[dict[str, str]],
                        system: str | None = None,
                        schema: dict[str, Any] | None = None,
                        max_tokens: int = 512) -> Respuesta:
        if self._http is None:
            raise RuntimeError("el motor no esta abierto: usa 'async with MotorBridge()'")

        params = {**PARAMS_DETERMINISTAS, "predict": max_tokens}
        if not self.razonar:
            params |= SIN_RAZONAMIENTO

        cuerpo: dict[str, Any] = {"messages": messages, "generation_params": params}
        if system is not None:
            cuerpo["system"] = system
        if schema is not None:
            cuerpo["response_format"] = schema

        inicio = time.perf_counter()
        resp = await self._http.post("/v1/completion", json=cuerpo)
        resp.raise_for_status()
        datos = resp.json()
        segundos = time.perf_counter() - inicio

        stats = datos.get("stats") or {}
        return Respuesta(
            texto=datos.get("texto") or "",
            segundos=segundos,
            stop_reason=datos.get("stop_reason"),
            tokens_por_segundo=stats.get("tokensPerSecond"),
        )
