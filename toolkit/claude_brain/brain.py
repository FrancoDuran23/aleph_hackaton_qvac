"""Wrapper directo sobre el SDK de Anthropic: retry, prompt caching, tool-use loop.

Extraído casi verbatim de D:\\bot\\bizbot-ventas\\agent\\brain.py — ver README.md
en esta misma carpeta para el detalle de qué se sacó y qué se dejó afuera.
"""
import os
import sys
import asyncio
import time
from datetime import datetime
from pathlib import Path

import anthropic

RESPUESTA_FALLBACK = "Uy, tuve un problema técnico un segundo. ¿Me repetís lo que me dijiste?"

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

ERRORS_LOG = Path(__file__).parent / "errors_log.md"


def _system_cacheable(system: str) -> list[dict]:
    """Convierte el system prompt en bloques con cache_control ephemeral.

    El descuento aplica si el bloque supera el mínimo cacheable del modelo
    (~1024 tokens Sonnet/Opus, ~2048 Haiku); por debajo, marcar es no-op.
    """
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


def _tools_cacheable(tools: list[dict]) -> list[dict]:
    """Marca el último tool con cache_control para cachear el array entero."""
    if not tools:
        return tools
    return [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]


def registrar_error(error: Exception, contexto: str = "") -> None:
    """Registra un error en errors_log.md. Nunca rompe el flujo del caller."""
    try:
        with open(ERRORS_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n- {datetime.now().isoformat()} | {type(error).__name__}: {error} | Contexto: {contexto}")
    except OSError as e:
        print(f"no se pudo escribir en {ERRORS_LOG}: {e}", file=sys.stderr)


def llamar_claude_sync(messages: list[dict], system: str,
                        modelo: str = "claude-haiku-4-5-20251001",
                        max_retries: int = 3,
                        prefill: str | None = None) -> tuple[str, int, int]:
    """Llama a Claude de forma sincrónica con retry y backoff exponencial.

    Retorna (respuesta, input_tokens, output_tokens).
    prefill: texto inicial forzado de la respuesta del asistente.
    """
    msgs = list(messages)
    if prefill:
        msgs.append({"role": "assistant", "content": prefill})

    for intento in range(max_retries):
        try:
            response = client.messages.create(
                model=modelo,
                max_tokens=500,
                system=_system_cacheable(system),
                messages=msgs,
            )
            texto = response.content[0].text
            if prefill:
                texto = prefill + texto
            return texto, response.usage.input_tokens, response.usage.output_tokens
        except anthropic.RateLimitError:
            time.sleep(2 ** intento)
        except anthropic.APIError as e:
            registrar_error(e, contexto="brain")
            if intento == max_retries - 1:
                return RESPUESTA_FALLBACK, 0, 0

    return RESPUESTA_FALLBACK, 0, 0


async def llamar_claude(messages: list[dict], system: str,
                         modelo: str = "claude-haiku-4-5-20251001",
                         max_retries: int = 3,
                         prefill: str | None = None) -> tuple[str, int, int]:
    """Versión async de llamar_claude_sync. Retorna (respuesta, input_tokens, output_tokens)."""
    msgs = list(messages)
    if prefill:
        msgs.append({"role": "assistant", "content": prefill})

    for intento in range(max_retries):
        try:
            response = client.messages.create(
                model=modelo,
                max_tokens=500,
                system=_system_cacheable(system),
                messages=msgs,
            )
            texto = response.content[0].text
            if prefill:
                texto = prefill + texto
            return texto, response.usage.input_tokens, response.usage.output_tokens
        except anthropic.RateLimitError:
            await asyncio.sleep(2 ** intento)
        except anthropic.APIError as e:
            registrar_error(e, contexto="brain")
            if intento == max_retries - 1:
                return RESPUESTA_FALLBACK, 0, 0

    return RESPUESTA_FALLBACK, 0, 0


async def llamar_claude_con_tools(messages: list[dict], system: str,
                                    tools: list[dict],
                                    tool_dispatcher,
                                    contexto_dispatcher: dict,
                                    modelo: str = "claude-haiku-4-5-20251001",
                                    max_iterations: int = 5,
                                    max_retries: int = 3) -> tuple[str, int, int]:
    """Llama a Claude con soporte de tool_use en loop.

    Loop:
    1. Llama a Claude con messages + tools
    2. Si responde con texto puro -> retorna ese texto
    3. Si responde con tool_use -> ejecuta tools via tool_dispatcher -> agrega tool_result -> vuelve a llamar
    4. Hasta max_iterations o hasta que responda texto puro

    Args:
        messages: historial de conversación
        system: system prompt
        tools: lista de schemas de tools (formato Anthropic)
        tool_dispatcher: callable(nombre_tool, args, contexto) -> str con el resultado
        contexto_dispatcher: dict que se le pasa al dispatcher
        max_iterations: tope de turnos del loop tool_use (evita infinitos)

    Returns:
        (texto_final, input_tokens_acumulados, output_tokens_acumulados)
    """
    msgs = list(messages)
    total_input = 0
    total_output = 0

    for _iteracion in range(max_iterations):
        response = None
        for intento in range(max_retries):
            try:
                response = client.messages.create(
                    model=modelo,
                    max_tokens=1024,
                    system=_system_cacheable(system),
                    tools=_tools_cacheable(tools),
                    messages=msgs,
                )
                break
            except anthropic.RateLimitError:
                await asyncio.sleep(2 ** intento)
            except anthropic.APIError as e:
                registrar_error(e, contexto="brain.tools")
                if intento == max_retries - 1:
                    return RESPUESTA_FALLBACK, total_input, total_output

        if response is None:
            return RESPUESTA_FALLBACK, total_input, total_output

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

        if response.stop_reason == "tool_use":
            msgs.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    resultado = tool_dispatcher(block.name, block.input, contexto_dispatcher)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": resultado,
                    })

            msgs.append({"role": "user", "content": tool_results})
            continue

        texto_final = "".join(block.text for block in response.content if block.type == "text")
        return texto_final.strip() or RESPUESTA_FALLBACK, total_input, total_output

    return RESPUESTA_FALLBACK, total_input, total_output
