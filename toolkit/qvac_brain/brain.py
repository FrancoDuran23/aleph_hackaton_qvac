"""Generación de texto con QVAC. Reemplazo drop-in de `toolkit.claude_brain.brain`.

Mantiene la firma y el contrato de retorno de `llamar_claude` /
`llamar_claude_sync` — `(texto, input_tokens, output_tokens)` — para que
`app/answer.py` y `toolkit/hybrid_rag/multihop.py` cambien solo el import.

Diferencias respecto de la versión Anthropic, a propósito:

- **No hay prompt caching.** Es una optimización de facturación de la API de
  Anthropic; acá el modelo es local y no hay nada que facturar.
- **`modelo` es una constante del SDK de QVAC** (QWEN3_1_7B_INST_Q4,
  LLAMA_3_2_1B_INST_Q4_0, ...), no un ID de Anthropic. Si le pasás un ID de
  Claude el bridge devuelve 400 con la lista de constantes válidas.
- **La versión async es async de verdad.** La de `claude_brain` declara `async`
  pero adentro llama al cliente sincrónico, así que bloquea el event loop; acá
  usamos httpx.AsyncClient.
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


_modelos_avisados: set[str] = set()


def _resolver_modelo(modelo: str) -> str:
    """Traduce un ID de Anthropic al modelo local configurado.

    Los call sites de `claude_brain` traen el modelo hardcodeado
    (`modelo="claude-sonnet-4-6"`). Si eso llegara tal cual al bridge daría 400
    y el swap dejaría de ser drop-in, así que lo mapeamos al modelo local y
    avisamos una vez por ID — que el aviso no ensucie el log en cada request.
    """
    if not modelo.startswith("claude"):
        return modelo
    if modelo not in _modelos_avisados:
        _modelos_avisados.add(modelo)
        print(f"[qvac_brain] '{modelo}' es un ID de Anthropic; uso el modelo local {MODELO_DEFAULT}")
    return MODELO_DEFAULT


def _armar_payload(messages: list[dict], system: str, modelo: str,
                   max_tokens: int, prefill: str | None,
                   generation_params: dict | None = None) -> dict:
    """Arma el body para POST /v1/completion."""
    msgs = list(messages)
    if prefill:
        # Mismo truco que en la versión Anthropic: un turno de assistant abierto
        # que el modelo continúa. Con chat templates de llama.cpp el efecto es
        # parecido pero no idéntico — verificá la salida si dependés del prefill.
        msgs.append({"role": "assistant", "content": prefill})

    payload = {
        "messages": msgs,
        "model": _resolver_modelo(modelo),
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


# Alias con los nombres de `claude_brain`, para que migrar un módulo sea cambiar
# el import y nada más. Los nombres reales son llamar_llm* — acá no hay Claude.
llamar_claude_sync = llamar_llm_sync
llamar_claude = llamar_llm
