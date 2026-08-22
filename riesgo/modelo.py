"""Tipos del dominio: un campo extraido, un hallazgo, un veredicto.

Todo lo que el motor produce arrastra de donde salio y que tan confiable es.
No hay valores desnudos: un numero sin procedencia no se puede defender ante
un analista, y el track premia justamente eso.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- gravedad de un hallazgo -------------------------------------------------
GRAVE = "GRAVE"
MEDIA = "media"
BAJA = "baja"

# --- estado de un hallazgo ---------------------------------------------------
CONFIRMADA = "CONFIRMADA"
PROBABLE = "PROBABLE"
DESCARTADA = "DESCARTADA"

# --- confianza del caso ------------------------------------------------------
FIRME = "FIRME"
CON_RESERVAS = "CON RESERVAS"

# --- rutas -------------------------------------------------------------------
LEGALES = "LEGALES"
REFINANCIACION = "REFINANCIACION"
COBRANZAS = "COBRANZAS"


@dataclass(frozen=True)
class Campo:
    """Un dato extraido, con su procedencia y sus reservas.

    ``grounding_ok=False`` significa que el valor no se encontro en el texto
    del documento: el modelo lo invento. Es la senal de confianza principal.
    """

    valor: Any
    doc: str | None = None
    pagina: int | None = None
    grounding_ok: bool = True
    ocr_confianza: float | None = None

    @property
    def vacio(self) -> bool:
        return self.valor is None

    @property
    def confiable(self) -> bool:
        """Sin reservas de ningun tipo. Un campo nulo es honesto, no dudoso."""
        if self.vacio:
            return True
        if not self.grounding_ok:
            return False
        return self.ocr_confianza is None or self.ocr_confianza >= UMBRAL_OCR

    def reserva(self) -> str | None:
        """Por que este campo no es confiable, si no lo es."""
        if self.vacio or self.confiable:
            return None
        if not self.grounding_ok:
            return "el valor no aparece en el documento: posible alucinacion"
        return f"confianza de OCR baja ({self.ocr_confianza:.2f})"

    def cita(self) -> str:
        if self.doc is None:
            return ""
        return f"[{self.doc}{f' p.{self.pagina}' if self.pagina else ''}]"


# Sin fijar: depende de que devuelva el OCR de QVAC en la practica. Ver
# seccion 13 del SDD. Este valor es un placeholder conservador.
UMBRAL_OCR = 0.75


@dataclass(frozen=True)
class Hallazgo:
    """Una contradiccion detectada entre dos documentos."""

    tipo: str
    gravedad: str
    estado: str
    detalle: str
    fuentes: tuple[str, ...] = ()

    @property
    def cuenta(self) -> bool:
        """Solo las CONFIRMADAS y PROBABLES influyen en el ruteo."""
        return self.estado in (CONFIRMADA, PROBABLE)


@dataclass(frozen=True)
class Advertencia:
    """Algo que el sistema no pudo garantizar. Se anota siempre."""

    campo: str
    motivo: str
    degrada: bool


@dataclass
class Veredicto:
    """El resultado completo de un caso. Nunca se suspende: siempre hay ruteo."""

    cliente_id: int
    nombre: str | None
    ruteo: str
    motivo: str
    derivados: dict[str, Any] = field(default_factory=dict)
    hallazgos: list[Hallazgo] = field(default_factory=list)
    advertencias: list[Advertencia] = field(default_factory=list)

    @property
    def confianza(self) -> str:
        """FIRME solo si nada que influyo en la decision tiene reservas."""
        return CON_RESERVAS if any(a.degrada for a in self.advertencias) else FIRME

    @property
    def graves(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == GRAVE and h.cuenta]
