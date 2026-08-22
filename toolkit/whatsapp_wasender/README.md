# whatsapp_wasender

Cliente mínimo para WASenderApi (servicio cloud de WhatsApp, no hace falta
correr un gateway propio como Evolution API). Dos funciones: parsear un
webhook entrante, mandar un mensaje.

Sin ABC ni capa de proveedores intercambiables: para un solo proveedor fijo
es una abstracción de más. Quedaron las dos funciones directas.

## Qué hay acá

- `MensajeEntrante` — dataclass: `numero`, `texto`, `mensaje_id`, `nombre`.
- `parsear_webhook(body: dict) -> MensajeEntrante | None` — soporta el
  shape de payload de WASenderApi (`event` + `data`, con varios alias de
  campo: `from`/`sender`, `body`/`text`/`message`). Devuelve `None` si no
  es un mensaje entrante procesable (evento distinto, sin número, sin
  texto, payload mal formado).
- `enviar_mensaje(numero, texto) -> bool` — `POST /send-message` a
  `https://app.wasenderapi.com/api`. `True` solo si WASenderApi devolvió
  200.

## Env vars

- `WASENDER_API_TOKEN`
- `WASENDER_SESSION_ID`

Se consiguen creando una sesión en el dashboard de wasenderapi.com.

## Importante para el demo en vivo

WASenderApi necesita poder pegarle a tu webhook por HTTP público — en
`localhost` no le llega nada. Para probar WhatsApp real en el hackathon
hace falta exponer el puerto con algo tipo `ngrok http 8000` y configurar
esa URL como webhook en el dashboard de WASenderApi. **La pantalla de chat
web no tiene esta limitación** — es la vía recomendada para la demo en
vivo frente al jurado, WhatsApp queda como plus si da el tiempo.

## Cómo reusarlo rápido en el próximo hackathon

```python
from whatsapp_wasender.provider import parsear_webhook, enviar_mensaje

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    msg = parsear_webhook(body)
    if msg is None:
        return {"ok": True}  # evento ignorado, no es un mensaje
    respuesta = mi_logica(msg.texto)
    await enviar_mensaje(msg.numero, respuesta)
    return {"ok": True}
```

## Qué NO se trajo

- Soporte multi-proveedor (Evolution API, WAHA) — hace falta una capa de
  abstracción que acá no existe.
- Creación de sesión por código (QR pairing, multi-tenant) — solo hace
  falta si necesitás crear sesiones de WhatsApp sin pasar por el dashboard.
- Verificación de firma del webhook — WASenderApi
  no manda ninguna. Si esto se convirtiera en producto real habría que
  agregar algún secreto compartido en la URL como mínimo.
