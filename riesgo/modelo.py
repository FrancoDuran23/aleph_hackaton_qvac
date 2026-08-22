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
    # El string tal como vino del modelo/OCR, antes de normalizar. Se guarda
    # aparte de `valor` porque una alerta de lectura necesita mostrar el crudo
    # -- "OCR leyo: 'ARS 457.'" es lo que hace la alerta accionable frente al
    # documento real; el valor ya normalizado (457.0) no alcanza para eso.
    crudo: str | None = None
    # Motivo si el valor parece incompleto o mal leido -- presente en el
    # documento, pero no confiable. Distinto de grounding_ok=False (que es
    # "no aparece en el documento"): esto es "aparece, pero no se puede usar".
    alerta_lectura: str | None = None

    @property
    def vacio(self) -> bool:
        return self.valor is None

    @property
    def confiable(self) -> bool:
        """Sin reservas de ningun tipo. Un campo nulo es honesto, no dudoso --

        salvo que el vacio se deba a una alerta de lectura. Ese es el caso
        contrario: el dato estaba en el documento, se detecto que no se podia
        usar (p.ej. un monto truncado por OCR) y por eso quedo en null en vez
        de un valor inventado. Si `alerta_lectura` no se revisara antes de
        `vacio`, esta rama nunca se ejecutaria: un campo anulado por alerta
        pasaria por "honesto" y la alerta no degradaria nada.
        """
        if self.alerta_lectura is not None:
            return False
        if self.vacio:
            return True
        if not self.grounding_ok:
            return False
        return self.ocr_confianza is None or self.ocr_confianza >= UMBRAL_OCR

    def reserva(self) -> str | None:
        """Por que este campo no es confiable, si no lo es."""
        if self.alerta_lectura is not None:
            return self.alerta_lectura
        if self.vacio or self.confiable:
            return None
        if not self.grounding_ok:
            return "value not found in the document: possible hallucination"
        return f"low OCR confidence ({self.ocr_confianza:.2f})"

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


@dataclass(frozen=True)
class Alerta:
    """Un campo cuyo valor parece incompleto o mal leido.

    No es un dato ausente -- es uno presente pero no confiable, y esa
    distincion importa: un analista no busca lo que falta, verifica lo que
    esta mal. El crudo va siempre: es lo que convierte la alerta en accionable
    frente al documento real, en vez de una sospecha sin evidencia.
    """

    campo: str
    crudo_ocr: str
    motivo: str
    documento: str | None = None
    pagina: int | None = None
    confianza_ocr: float | None = None


@dataclass
class Veredicto:
    """El resultado completo de un caso. Nunca se suspende: siempre hay ruteo.

    Una alerta de lectura degrada el caso por el mismo camino que cualquier
    otra reserva -- no introduce un tercer estado de confianza. El campo
    marcado no confiable ya empuja a CON RESERVAS si influyo en la decision;
    "suspender" el ruteo seria la unica excepcion a una regla que el resto
    del sistema sostiene en todos lados.
    """

    cliente_id: int
    nombre: str | None
    ruteo: str
    motivo: str
    derivados: dict[str, Any] = field(default_factory=dict)
    hallazgos: list[Hallazgo] = field(default_factory=list)
    advertencias: list[Advertencia] = field(default_factory=list)
    alertas: list[Alerta] = field(default_factory=list)

    @property
    def confianza(self) -> str:
        """FIRME solo si nada que influyo en la decision tiene reservas."""
        return CON_RESERVAS if any(a.degrada for a in self.advertencias) else FIRME

    @property
    def graves(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == GRAVE and h.cuenta]
