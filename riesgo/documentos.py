"""Lectura de documentos: el límite entre esta parte y la del compañero.

El contrato es uno solo:

    leer_documento(path) -> Documento

`Documento` trae el texto **por página**, porque el grounding necesita saber en
qué página apareció cada valor, y una confianza por página cuando el texto vino
de OCR.

Mientras el OCR no exista, el stub usa pypdf y funciona con los documentos
nativos. Los escaneados devuelven texto vacío — que **no** es lo mismo que un
documento sin datos, y por eso `Documento.ilegible` existe: un campo nulo
porque no se pudo leer degrada el caso, uno nulo porque el dato no está no.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

# Menos que esto en un PDF entero es papel escaneado sin capa de texto, no un
# documento corto. Un contrato nativo del dataset ronda los 500 caracteres.
MINIMO_LEGIBLE = 40


@dataclass(frozen=True)
class Documento:
    """Un documento leído, con su texto por página y su procedencia."""

    nombre: str
    paginas: list[str]
    fue_ocr: bool = False
    # Confianza por página, cuando el lector la reporta. El OCR de QVAC la
    # devuelve por bloque; el compañero la agrega por página antes de esto.
    confianzas: list[float] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(self.paginas)

    @property
    def ilegible(self) -> bool:
        """El documento existe pero no produjo texto utilizable.

        Es la señal más importante que produce este módulo. Sin ella, una
        escritura escaneada sin OCR se ve exactamente igual que una escritura
        sin contradicciones, y el caso rutea limpio cuando no lo está.
        """
        return len(self.texto.strip()) < MINIMO_LEGIBLE

    def confianza_de(self, pagina: int | None) -> float | None:
        """Confianza de una página (1-indexada), o None si no se reporta."""
        if pagina is None or not self.confianzas:
            return None
        i = pagina - 1
        return self.confianzas[i] if 0 <= i < len(self.confianzas) else None


def leer_documento(path: str | Path) -> Documento:
    """Lee un PDF: texto nativo con pypdf; si está escaneado, OCR de QVAC.

    Un PDF nativo (con capa de texto) sale por pypdf y es instantáneo. Uno
    escaneado —sin capa de texto, o sea ``ilegible``— pasa por el OCR de QVAC,
    que devuelve texto y confianza por página. Esa confianza es la señal que el
    resto del pipeline usa para distinguir "el OCR leyó mal" de "contradicción
    real". La firma no cambia: el resto del pipeline sigue consumiendo el mismo
    `Documento`.
    """
    p = Path(path)
    lector = PdfReader(str(p))
    nativo = Documento(nombre=p.name,
                       paginas=[pag.extract_text() or "" for pag in lector.pages])
    if not nativo.ilegible:
        return nativo

    # Escaneado: sin capa de texto -> OCR de QVAC (texto + confianza por página).
    # Import perezoso: un caso 100% nativo no necesita pymupdf ni el worker.
    from . import ocr

    paginas, confianzas = ocr.ocr_pdf(p)
    return Documento(nombre=p.name, paginas=paginas,
                     fue_ocr=True, confianzas=confianzas)


def leer_texto_plano(path: str | Path) -> Documento:
    """Para la correspondencia, que viene en .txt y no pasa por pypdf."""
    p = Path(path)
    return Documento(nombre=p.name, paginas=[p.read_text(encoding="utf-8", errors="ignore")])


def leer_carpeta(carpeta: str | Path) -> dict[str, Documento]:
    """Lee todos los documentos de una carpeta de cliente, por nombre de archivo.

    Un documento que falta simplemente no aparece en el dict. Un documento que
    está pero no se puede leer aparece con `ilegible=True`, que es una
    situación distinta y se trata distinto.
    """
    c = Path(carpeta)
    docs: dict[str, Documento] = {}
    for p in sorted(c.iterdir()):
        if p.suffix.lower() == ".pdf":
            docs[p.name] = leer_documento(p)
        elif p.suffix.lower() == ".txt":
            docs[p.name] = leer_texto_plano(p)
    return docs
