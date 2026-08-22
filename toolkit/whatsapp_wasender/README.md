# whatsapp_wasender

Cliente mínimo para WASenderApi (servicio cloud de WhatsApp, no hace falta
correr un gateway propio como Evolution API). Dos funciones: parsear un
webhook entrante, mandar un mensaje.

**Origen**: `agent/providers/wasender.py` en `D:\bot\bizbot-ventas`
(BizBot). Ahí implementaba una ABC (`ProveedorWhatsApp`) pensada para
soportar múltiples proveedores intercambiables (Evolution/WAHA/WASenderApi)
en un bot multi-tenant. Acá se sacó la ABC — para un solo proveedor fijo
es una abstracción de más — y quedaron las dos funciones directas.

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

- La ABC `ProveedorWhatsApp` / soporte multi-proveedor — si en algún
  hackathon futuro hace falta soportar Evolution API o WAHA además de
  WASenderApi, mirá `agent/providers/base.py` y `agent/providers/evolution.py`
  en BizBot para el patrón.
- `WASenderSessionProvider` (creación de sesión, QR pairing, multi-tenant)
  — eso vive en `onboarding/providers/wasender_sessions.py` de BizBot, solo
  hace falta si necesitás crear sesiones de WhatsApp por código en vez de
  desde el dashboard.
- Verificación de firma del webhook — el original tampoco la tiene, WASenderApi
  no manda ninguna. Si esto se convirtiera en producto real habría que
  agregar algún secreto compartido en la URL como mínimo.
