"""FastAPI: webhook de WhatsApp, endpoint de chat web, UI estática.

Local sin Docker: `python -m uvicorn app.main:app --reload --port 8000`
(necesita Postgres accesible en DATABASE_URL de todas formas, salvo que
la pregunta esté precalentada en el cache de demo).
"""
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from toolkit.whatsapp_wasender.provider import enviar_mensaje, parsear_webhook

from . import answer

app = FastAPI(title="Hackaton RAG + WhatsApp")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Historial en memoria, por número de WhatsApp. Se pierde al reiniciar el
# proceso -- alcanza para un demo de hackathon. Si hace falta persistirlo
# entre reinicios, hace falta persistirlo.
_historial_whatsapp: dict[str, list[dict]] = {}
_ultimo_mensaje_id: dict[str, str] = {}


class ChatRequest(BaseModel):
    pregunta: str
    historial: list[dict] = []


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatRequest):
    respuesta = answer.responder(body.pregunta, body.historial)
    return {"respuesta": respuesta}


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    msg = parsear_webhook(body)
    if msg is None:
        return {"ok": True}

    if msg.mensaje_id is not None and _ultimo_mensaje_id.get(msg.numero) == msg.mensaje_id:
        return {"ok": True}  # ya procesado, WhatsApp reintentó la entrega
    _ultimo_mensaje_id[msg.numero] = msg.mensaje_id

    historial = _historial_whatsapp.setdefault(msg.numero, [])
    respuesta = answer.responder(msg.texto, historial)

    historial.append({"role": "user", "content": msg.texto})
    historial.append({"role": "assistant", "content": respuesta})
    del historial[:-20]  # tope simple para no crecer sin límite

    await enviar_mensaje(msg.numero, respuesta)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
