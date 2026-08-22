# claude_brain

Wrapper directo sobre el SDK de Anthropic (`anthropic.Anthropic`) con retry +
backoff exponencial, prompt caching, y un loop de tool-use. Cero framework
(no LangChain), son funciones planas que llaman `client.messages.create`.

**Origen**: extraído casi sin cambios de `agent/brain.py` en
`D:\bot\bizbot-ventas` (BizBot). Se sacó todo lo específico de ese bot
(carga de skills en Markdown, máquina de estados del funnel de ventas,
compresión de historial, notificación al founder por WhatsApp en errores
críticos) y quedaron las tres funciones genéricas + los dos helpers de
cacheo.

## Qué hay acá

- `client` — instancia módulo-level de `anthropic.Anthropic`, lee
  `ANTHROPIC_API_KEY` del entorno.
- `llamar_claude_sync(messages, system, modelo, max_retries, prefill)` —
  llamada bloqueante simple. `max_tokens=500`.
- `llamar_claude(...)` — misma firma, versión `async`.
- `llamar_claude_con_tools(messages, system, tools, tool_dispatcher, contexto_dispatcher, modelo, max_iterations, max_retries)` —
  loop de tool-use: llama a Claude, si pide `tool_use` ejecuta
  `tool_dispatcher(nombre, args, contexto)` (callable sync que devuelve un
  string), agrega el `tool_result` y vuelve a llamar, hasta
  `max_iterations` o hasta que Claude responda texto puro. `max_tokens=1024`.
- `_system_cacheable` / `_tools_cacheable` — envuelven el system prompt y
  el array de tools con `cache_control: {type: "ephemeral"}` para
  aprovechar el descuento de prompt caching de Anthropic. Por debajo del
  mínimo cacheable del modelo (~1024 tokens Sonnet/Opus, ~2048 Haiku)
  marcar no hace nada, así que no hay downside en dejarlo siempre activo.
- `registrar_error(error, contexto)` — loggea a `errors_log.md` en esta
  misma carpeta. Nunca lanza (solo atrapa `OSError` al escribir el log).

## Cómo reusarlo rápido en el próximo hackathon

1. Copiá esta carpeta entera.
2. Seteá `ANTHROPIC_API_KEY`.
3. Para chat simple: `texto, in_tok, out_tok = await llamar_claude(messages, system)`.
4. Para tools: definí tu `TOOLS_SCHEMA` (formato Anthropic estándar) y un
   `def dispatcher(nombre, args, contexto) -> str`, después
   `await llamar_claude_con_tools(messages, system, TOOLS_SCHEMA, dispatcher, {})`.

## Qué NO se trajo (y por qué)

- Carga de skills desde archivos `.md` por estado — específico del funnel
  de ventas de BizBot.
- `comprimir_historial()` — resumen de conversación vía Haiku, útil pero
  atado a la lógica de negocio de "lead" que no aplica acá.
- `notificar_founder()` — mandaba un WhatsApp al founder en errores
  críticos usando `EvolutionProvider`. Si querés esto de vuelta, andá a
  `agent/brain.py:322` en BizBot.
- Precios hardcodeados de `token_tracker.py` — están desactualizados en el
  original, no vale la pena arrastrar el bug.
