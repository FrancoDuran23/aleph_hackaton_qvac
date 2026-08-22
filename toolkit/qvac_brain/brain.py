"""Generación de texto con QVAC: inferencia local, sin salir a la red.

Mantiene el contrato de retorno `(texto, input_tokens, output_tokens)` para que
`app/answer.py` y `toolkit/hybrid_rag/multihop.py` cambien solo el import.

`modelo` es una constante del SDK de QVAC (QWEN3_1_7B_INST_Q4,
LLAMA_3_2_1B_INST_Q4_0, ...). Un nombre que no exista da 400 con la lista de
constantes válidas.

No hay prompt caching: es una optimización de facturación de APIs remotas, y
acá no hay nada que facturar.
"""
import os

from .cliente import QvacBridgeError, pedir, pedir_async

RESPUESTA_FALLBACK = "Uy, tuve un problema técnico un segundo. ¿Me repetís lo que me dijiste?"

MODELO_DEFAULT = os.getenv("QVAC_LLM_MODEL", "QWEN3_1_7B_INST_Q4")

# Parametros de generacion por defecto.
#
# Sin esto el bridge no recibe ningun `generationParams` y el modelo corre con
# sampling por defecto: la misma pregunta devuelve respuestas distintas y nada
# lo delata. Es el mismo error que tenia el bridge del lado servidor, pero del
# lado cliente.
#
# `reasoning_budget: 0` apaga el bloque <think> de Qwen3. Medido contra el
# bridge: la misma respuesta cuesta 58 tokens con razonamiento y 9 sin el. Con
# `max_tokens` bajo el efecto es peor que lento -- el modelo agota el
# presupuesto pensando y devuelve texto vacio con stop_reason "length".
PARAMS_DEFAULT: dict[str, object] = {"temp": 0.0, "top_p": 1.0, "reasoning_budget": 0}




def _armar_payload(messages: list[dict], system: str, modelo: str,
                   max_tokens: int, prefill: str | None,
                   generation_params: dict | None = None) -> dict:
    """Arma el body para POST /v1/completion."""
    msgs = list(messages)
    if prefill:
        # Un turno de assistant abierto
        # que el modelo continúa. Con chat templates de llama.cpp el efecto es
        # parecido pero no idéntico — verificá la salida si dependés del prefill.
        msgs.append({"role": "assistant", "content": prefill})

    payload = {
        "messages": msgs,
        "model": modelo or MODELO_DEFAULT,
        "max_tokens": max_tokens,
        "generation_params": {**PARAMS_DEFAULT, **(generation_params or {})},
    }
    if system:
        payload["system"] = system
    return payload


def _leer_tokens(stats: dict | None) -> tuple[int, int]:
    """Extrae (input_tokens, output_tokens) de las stats del SDK.

    Los nombres de campo cambiaron entre versiones del SDK y las stats son
    opcionales, así que probamos alias y caemos a 0 en vez de romper: el conteo
    de tokens es telemetría, no vale tirar una respuesta buena por eso.
    """
    if not stats:
        return 0, 0
    entrada = stats.get("promptTokens") or stats.get("inputTokens") or stats.get("nPromptTokens") or 0
    # 'generatedTokens' es el nombre que devuelve el SDK hoy (verificado contra
    # una respuesta real); el resto son alias de otras versiones.
    salida = (stats.get("generatedTokens") or stats.get("emittedTokens")
              or stats.get("completionTokens") or stats.get("outputTokens")
              or stats.get("nPredictedTokens") or 0)
    return int(entrada), int(salida)


def _interpretar(datos: dict, prefill: str | None) -> tuple[str, int, int]:
    texto = datos.get("texto", "")
    if prefill:
        texto = prefill + texto
    entrada, salida = _leer_tokens(datos.get("stats"))
    return texto.strip() or RESPUESTA_FALLBACK, entrada, salida


def llamar_llm_sync(messages: list[dict], system: str = "",
                    modelo: str = MODELO_DEFAULT,
                    max_retries: int = 3,
                    max_tokens: int = 500,
                    prefill: str | None = None) -> tuple[str, int, int]:
    """Llama al modelo local de forma sincrónica.

    Retorna (respuesta, input_tokens, output_tokens). El retry y el backoff los
    hace `cliente.pedir`.
    """
    payload = _armar_payload(messages, system, modelo, max_tokens, prefill)
    try:
        return _interpretar(pedir("/v1/completion", payload, max_retries=max_retries), prefill)
    except QvacBridgeError as e:
        print(f"[qvac_brain] {e}")
        return RESPUESTA_FALLBACK, 0, 0


async def llamar_llm(messages: list[dict], system: str = "",
                     modelo: str = MODELO_DEFAULT,
                     max_retries: int = 3,
                     max_tokens: int = 500,
                     prefill: str | None = None) -> tuple[str, int, int]:
    """Versión async de `llamar_llm_sync`."""
    payload = _armar_payload(messages, system, modelo, max_tokens, prefill)
    try:
        datos = await pedir_async("/v1/completion", payload, max_retries=max_retries)
        return _interpretar(datos, prefill)
    except QvacBridgeError as e:
        print(f"[qvac_brain] {e}")
        return RESPUESTA_FALLBACK, 0, 0


