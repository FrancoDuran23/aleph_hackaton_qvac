"""Cliente de inferencia local sobre el SDK de QVAC.

El SDK es asyncio-nativo. Cargar el modelo cuesta minutos, asi que el motor
se abre una vez por proceso y se reutiliza para todas las llamadas.

Contrato verificado contra tetherto-qvac-sdk 0.17.1:

    load_model(transport, *, model_src, model_config, on_progress) -> str
    completion(transport, *, model_id, history, generation_params,
               response_format, stream) -> CompletionRun
    unload_model(transport, model_id)

Dos detalles que no estan en la doc y cuestan horas:

  * El parametro de temperatura se llama ``temp``, no ``temperature``.
    Un nombre desconocido se descarta en silencio y la inferencia queda con
    sampling por defecto: el mismo documento devuelve numeros distintos en
    corridas distintas.

  * ``response_format`` con ``json_schema`` no es una sugerencia en el prompt.
    llama.cpp lo convierte a una gramatica GBNF, asi que el decoder no puede
    emitir nada que viole el schema: ni backticks, ni JSON truncado, ni
    "no encontrado" donde el schema declara ``number | null``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from tetherto.qvac_sdk import Client, completion, load_model, unload_model
from tetherto.qvac_sdk.models import QWEN3_1_7B_INST_Q4

MODELO_POR_DEFECTO = QWEN3_1_7B_INST_Q4
CTX_POR_DEFECTO = 4096

# Delegated inference: en vez de cargar el modelo en esta maquina, se delega a
# un peer que ya lo tiene cargado. La conexion es directa por clave publica
# sobre la DHT de Hyperswarm, con cifrado end-to-end incluido.
#
# Contrato verificado contra el SDK (los alias van en camelCase en el wire):
#
#     delegate = {
#         "providerPublicKey": str,      # requerido
#         "timeout": float,
#         "healthCheckTimeout": float,
#         "fallbackToLocal": bool,
#         "forceNewConnection": bool,
#     }
#
# El cold start de la primera conexion es de 15 a 45 segundos (bootstrap de la
# DHT). Las siguientes reusan el socket. Medir latencia en caliente, nunca en
# la primera llamada.
TIMEOUT_DELEGADO_MS = 60_000

# Determinismo: temperatura en cero y semilla fija. Para extraccion no
# queremos creatividad, queremos que dos corridas den el mismo numero.
PARAMS_DETERMINISTAS: dict[str, Any] = {"temp": 0.0, "top_p": 1.0, "seed": 7}


@dataclass(frozen=True)
class Respuesta:
    """Resultado de una completion, con la latencia ya medida."""

    texto: str
    segundos: float
    stop_reason: str | None
    tokens_por_segundo: float | None

    @property
    def truncada(self) -> bool:
        """True si el modelo se quedo sin presupuesto de tokens."""
        return self.stop_reason not in (None, "stop", "eos")


def schema_json(nombre: str, propiedades: dict[str, Any],
                requeridos: list[str] | None = None) -> dict[str, Any]:
    """Arma un response_format que fuerza la forma exacta de la salida.

    ``additionalProperties: False`` evita que el modelo agregue campos de su
    invencion, que es la otra mitad del problema de parseo.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": nombre,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": propiedades,
                "required": requeridos if requeridos is not None else list(propiedades),
                "additionalProperties": False,
            },
        },
    }


class Motor:
    """Modelo cargado y listo para inferir.

    Uso:

        async with Motor() as motor:
            r = await motor.completar([{"role": "user", "content": "hola"}])
    """

    def __init__(self, modelo: Any = MODELO_POR_DEFECTO,
                 ctx_size: int = CTX_POR_DEFECTO,
                 verboso: bool = True,
                 provider: str | None = None,
                 fallback_local: bool = True) -> None:
        """``provider`` es la clave publica del peer que corre la inferencia.

        Con ``fallback_local`` el SDK carga el modelo en esta maquina si el
        provider no responde, asi que matar el provider en vivo no rompe la
        demo: el siguiente caso corre local sin intervencion.
        """
        self.modelo = modelo
        self.ctx_size = ctx_size
        self.verboso = verboso
        self.provider = provider
        self.fallback_local = fallback_local
        self._cliente: Client | None = None
        self._transport: Any = None
        self._model_id: str | None = None
        self.segundos_de_carga: float = 0.0

    async def __aenter__(self) -> "Motor":
        inicio = time.perf_counter()
        self._cliente = Client()
        self._transport = await self._cliente.connect()
        delegate = None
        if self.provider:
            delegate = {
                "providerPublicKey": self.provider,
                "timeout": TIMEOUT_DELEGADO_MS,
                "fallbackToLocal": self.fallback_local,
            }

        self._model_id = await load_model(
            self._transport,
            model_src=self.modelo,
            model_config={"ctx_size": self.ctx_size},
            on_progress=self._progreso if self.verboso else None,
            delegate=delegate,
        )
        self.segundos_de_carga = time.perf_counter() - inicio
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._model_id is not None:
            await unload_model(self._transport, self._model_id)
        if self._cliente is not None:
            await self._cliente.close()

    def _progreso(self, ev: Any) -> None:
        pct = getattr(ev, "progress", None) or getattr(ev, "percent", None)
        if pct is not None:
            print(f"\r  descargando modelo: {float(pct):5.1f}%", end="", flush=True)

    @property
    def delegado(self) -> bool:
        """True si la inferencia corre en un peer y no en esta maquina."""
        return self.provider is not None

    async def completar(self, messages: list[dict[str, str]],
                        system: str | None = None,
                        schema: dict[str, Any] | None = None,
                        max_tokens: int = 512) -> Respuesta:
        """Una completion determinista. ``schema`` sale de :func:`schema_json`."""
        if self._model_id is None:
            raise RuntimeError("el motor no esta abierto: usa 'async with Motor()'")

        history = list(messages)
        if system is not None:
            history = [{"role": "system", "content": system}, *history]

        params = {**PARAMS_DETERMINISTAS, "predict": max_tokens}

        inicio = time.perf_counter()
        run = await completion(
            self._transport,
            model_id=self._model_id,
            history=history,
            generation_params=params,
            response_format=schema,
            stream=False,
        )
        final = await run.final
        segundos = time.perf_counter() - inicio

        return Respuesta(
            texto=final.content_text,
            segundos=segundos,
            stop_reason=final.stop_reason,
            tokens_por_segundo=getattr(final.stats, "tokens_per_second", None),
        )
