"""OCR de documentos escaneados sobre QVAC — la parte del compañero.

Da texto por página y confianza por página para las escrituras escaneadas,
respetando el contrato **síncrono** de ``documentos.leer_documento(path)``.

Por qué un hilo aparte: el OCR de QVAC es asyncio-nativo, pero el pipeline ya
corre dentro de un event loop (``evaluar_real`` abre el ``Motor`` con
``async with`` y lee las carpetas ahí adentro). Hacer ``asyncio.run`` dentro de
un loop ya corriendo revienta. Para no cambiar la firma síncrona que espera el
resto del código —y no tocar nada del pipeline— la inferencia corre en un hilo
dedicado con su propio loop; ``leer`` es una llamada síncrona que bloquea hasta
el resultado. El modelo OCR se carga una sola vez por proceso.

Config afinada en un Intel Core Ultra 5 125U (15W, sin GPU): ~9-12 s por página
escaneada. Con los defaults del SDK la misma página tardaba ~350 s. El detalle
de cada perilla está más abajo.
"""

from __future__ import annotations

import asyncio
import base64
import os
import threading
from pathlib import Path

import pymupdf

from tetherto.qvac_sdk import Client, load_model, ocr_stream
from tetherto.qvac_sdk.models import OCR_LATIN
from tetherto.qvac_sdk.schemas import OcrStreamRequest

# canvasSize es lo que más pesa en CPU: bajarlo de ~2560 (default) a 960 es el
# grueso del 350s -> 9s, sin perder precisión de campo (medido). nThreads=4:
# subirlo a 14 hace thrashing en un CPU híbrido P/E-core. defaultRotationAngles
# vacío = solo 0°; los escaneos del dataset están rotados ±2° (el deskew los
# maneja), probar 90/180/270 cuadruplica el costo. langList: OCR_LATIN no acepta
# "es"; el alfabeto latino lee español igual con "en".
_OCR_CONFIG = {
    "langList": ["en"],
    "defaultRotationAngles": [],
    "magRatio": 1.0,
    "canvasSize": 960,
    "nThreads": 4,
    "contrastRetry": False,
}

# A4 a escala 1.0 sale ~600x840, por debajo del cap de canvasSize: no hay
# reescalado extra y la imagen viaja chica.
_OCR_SCALE = 1.0

# El primer connect en Windows es lento (Defender escanea el binario nativo).
_TIMEOUT_CONEXION = 180


def _resolver_worker() -> tuple[str, str]:
    """(bare, worker) del worker instalado, tolerando el hoisting de npm.

    ``install-worker`` deja el binario nativo ``bare`` en el node_modules de
    nivel superior, mientras el SDK lo busca anidado bajo ``@qvac/sdk``. Lo
    localizamos donde esté para que ande desde un clone limpio sin exportar
    QVAC_BARE_PATH a mano.
    """
    from tetherto.qvac_sdk.client import managed_worker_prefix

    prefix = managed_worker_prefix()
    worker = prefix / "node_modules" / "@qvac" / "sdk" / "dist" / "server" / "worker.js"
    nombre = "bare.exe" if os.name == "nt" else "bare"
    bares = list(prefix.rglob(nombre))
    if not bares or not worker.exists():
        raise FileNotFoundError(
            "worker de QVAC no encontrado. Corré: "
            "python -m tetherto.qvac_sdk install-worker"
        )
    return str(bares[0]), str(worker)


class _MotorOCR:
    """Modelo OCR cargado una vez, servido desde un hilo con su propio loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cliente: Client | None = None
        self._transport = None
        self._model_id: str | None = None

    def leer(self, imagenes_png: list[bytes]) -> tuple[list[str], list[float]]:
        """Sincrónico: OCR de una lista de páginas (PNG) -> (textos, confianzas)."""
        with self._lock:
            self._asegurar_arrancado()
            fut = asyncio.run_coroutine_threadsafe(
                self._ocr(imagenes_png), self._loop)
            return fut.result()

    def _asegurar_arrancado(self) -> None:
        if self._loop is not None:
            return
        loop = asyncio.new_event_loop()

        def correr() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        threading.Thread(target=correr, daemon=True, name="qvac-ocr").start()
        self._loop = loop
        asyncio.run_coroutine_threadsafe(self._init(), loop).result()

    async def _init(self) -> None:
        bare, worker = _resolver_worker()
        self._cliente = Client(bare_path=bare, worker_path=worker)
        await self._cliente.connect(timeout=_TIMEOUT_CONEXION)
        self._transport = self._cliente.transport
        self._model_id = await load_model(
            self._transport, model_src=OCR_LATIN,
            model_config=_OCR_CONFIG, on_progress=None)

    async def _ocr(self, imagenes: list[bytes]) -> tuple[list[str], list[float]]:
        textos: list[str] = []
        confianzas: list[float] = []
        for img in imagenes:
            b64 = base64.b64encode(img).decode("ascii")
            req = OcrStreamRequest(
                type="ocrStream", model_id=self._model_id,
                image={"type": "base64", "value": b64},
                options={"paragraph": False})
            bloques = []
            async for r in ocr_stream(self._transport, req):
                if r.error:
                    raise RuntimeError(f"OCR falló: {r.error}")
                if r.blocks:
                    bloques.extend(r.blocks)
            textos.append(" ".join(
                b.text.strip() for b in bloques if b.text and b.text.strip()))
            confs = [b.confidence for b in bloques if b.confidence is not None]
            confianzas.append(sum(confs) / len(confs) if confs else 0.0)
        return textos, confianzas


_motor = _MotorOCR()


def ocr_pdf(path: str | Path) -> tuple[list[str], list[float]]:
    """Rasteriza cada página del PDF y devuelve (texto_por_página, confianza_por_página)."""
    doc = pymupdf.open(str(path))
    try:
        imagenes = []
        for n in range(len(doc)):
            pix = doc.load_page(n).get_pixmap(
                matrix=pymupdf.Matrix(_OCR_SCALE, _OCR_SCALE))
            imagenes.append(pix.tobytes("png"))
    finally:
        doc.close()
    return _motor.leer(imagenes)
