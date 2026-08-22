"""Adaptador WASenderApi (https://wasenderapi.com) para enviar y recibir WhatsApp.

Extraído de D:\\bot\\bizbot-ventas\\agent\\providers\\wasender.py — ahí estaba
como una clase que implementaba una ABC multi-proveedor (Evolution/WAHA/
WASenderApi intercambiables). Acá hay un solo proveedor, así que quedaron
dos funciones planas en vez de una clase con interfaz.
"""
import os
from dataclasses import dataclass

import httpx

WASENDER_BASE_URL = "https://app.wasenderapi.com/api"


@dataclass
class MensajeEntrante:
    numero: str
    texto: str
    mensaje_id: str | None = None
    nombre: str | None = None


def parsear_webhook(body: dict) -> MensajeEntrante | None:
    """Parsea el body del webhook de WASenderApi. None si no es un mensaje válido."""
    try:
        if body.get("event") not in ("message", "message.received", None):
            return None

        data = body.get("data", body)

        numero = data.get("from", data.get("sender", ""))
        if not numero:
            return None

        texto = data.get("body", data.get("text", data.get("message", "")))
        if not texto:
            return None

        mensaje_id = data.get("id", data.get("message_id", None))
        nombre = data.get("pushName", data.get("name", None))

        return MensajeEntrante(numero=numero, texto=texto, mensaje_id=mensaje_id, nombre=nombre)
    except (KeyError, TypeError):
        return None


async def enviar_mensaje(numero: str, texto: str) -> bool:
    """Envía un mensaje de texto via WASenderApi. True si WASenderApi devolvió 200."""
    api_token = os.getenv("WASENDER_API_TOKEN", "")
    session_id = os.getenv("WASENDER_SESSION_ID", "")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{WASENDER_BASE_URL}/send-message",
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
                json={"sessionId": session_id, "to": numero, "text": texto},
                timeout=30,
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False
