"""De documentos a campos con procedencia.

Un prompt por documento, no por campo: los campos de un mismo documento salen
en una sola llamada. A ~9 s por llamada, pedirlos de a uno costaría doce
llamadas por caso en vez de dos.

**No todo pasa por el modelo.** Los recibos son una tabla de columnas fijas y
la correspondencia es un mail con encabezado: parsearlos con regex es exacto,
gratis e instantáneo. El modelo se reserva para la prosa, que es donde aporta.

**Los montos se extraen como string, verbatim.** Convertirlos es trabajo de
:mod:`riesgo.normalizacion`; pedirle aritmética a un modelo chico es pedirle
justo lo que peor hace.

**La página no se le pregunta al modelo** — la inventa. Se deriva buscando el
valor extraído en el texto de cada página. Si no aparece en ninguna, el campo
va con ``grounding_ok=False``: es la señal de alucinación más barata y más
confiable que tenemos.
"""

from __future__ import annotations

import json
import re

from .comparacion import digitos, norm as norm_texto
from .documentos import Documento
from .modelo import Campo
from .normalizacion import (normalizar_entero, normalizar_fecha,
                            normalizar_monto, normalizar_texto)
from .validacion import separador_miles_roto

SISTEMA = ("Sos un extractor de datos de documentos legales y financieros. "
           "Respondés solo con JSON. No inventás valores: si un dato no está "
           "en el texto, va null.")

_TXT = {"type": ["string", "null"]}

# Qué campos salen de cada documento, y con qué schema. Los montos son string
# a propósito: el modelo copia lo que ve, Python lo convierte.
CAMPOS_POR_DOC: dict[str, dict[str, dict]] = {
    "contrato.pdf": {
        "titular": _TXT,
        "capital_original": _TXT,
        "capital_adeudado": _TXT,
        "cuotas_contrato": _TXT,
        "matricula": _TXT,
        "domicilio_titular": _TXT,
    },
    "escritura.pdf": {
        "titular": _TXT,
        "matricula": _TXT,
        "garantia_valor": _TXT,
        "tasacion_fecha": _TXT,
        "domicilio_titular": _TXT,
    },
}

# Instrucciones por campo. Sin esto el modelo confunde sistemáticamente los
# pares que aparecen juntos en la misma página.
PISTAS: dict[str, str] = {
    "capital_original": "el monto del préstamo otorgado originalmente",
    "capital_adeudado": "el saldo que se debe HOY, no el capital original",
    "cuotas_contrato": "cuántas cuotas se pactaron, solo el número",
    "matricula": "la matrícula del inmueble, con guion si lo tiene",
    "titular": "el nombre de la persona deudora o compareciente, no el banco",
    "domicilio_titular": ("el domicilio de LA PERSONA, no el del inmueble "
                          "hipotecado; si hay dos direcciones, la del titular "
                          "es la que aparece junto a su nombre y DNI"),
    "garantia_valor": "la valuación o el valor del inmueble en garantía",
    "tasacion_fecha": "la fecha de la tasación o valuación, formato dd/mm/aaaa",
}

CONVERSORES = {
    "capital_original": normalizar_monto,
    "capital_adeudado": normalizar_monto,
    "garantia_valor": normalizar_monto,
    "cuotas_contrato": normalizar_entero,
    "tasacion_fecha": normalizar_fecha,
}

# --- parseo determinista, sin modelo -----------------------------------------

_FILA_PAGO = re.compile(
    r"^\s*(\d{1,3})\s*$\n\s*(\d{2}/\d{2}/\d{4})\s*$\n\s*(\d{2}/\d{2}/\d{4})\s*$",
    re.MULTILINE)
TOLERANCIA_DIAS = 5


def parsear_recibos(doc: Documento) -> tuple[int | None, float | None]:
    """(cantidad de recibos, fracción pagada a tiempo).

    La tabla sale de pypdf con una celda por línea: numero, vencimiento, pago,
    importe, estado. Alcanza con las tres primeras.
    """
    filas = _FILA_PAGO.findall(doc.texto)
    if not filas:
        return None, None

    a_tiempo = 0
    for _, venc, pago in filas:
        d_venc, d_pago = normalizar_fecha(venc), normalizar_fecha(pago)
        if d_venc and d_pago and (d_pago - d_venc).days <= TOLERANCIA_DIAS:
            a_tiempo += 1
    return len(filas), round(a_tiempo / len(filas), 3)


_REMITENTE = re.compile(r"^\s*De\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


def parsear_correspondencia(doc: Documento | None,
                            titular: str | None = None) -> bool | None:
    """Hubo aviso previo si **el deudor** escribió al banco antes de la mora.

    ⚠️ La presencia del archivo NO alcanza, y creer que sí alcanza costó 10 de
    20 casos mal. La carta existe siempre; lo que cambia es quién la escribió:

        aviso previo    De: juan.perez@mail.com      -> el deudor avisa
        sin aviso       De: cobranzas@banco...       -> el banco intima

    Las dos son "correspondencia". Solo la primera es un aviso previo, y la
    diferencia entre una y otra manda el caso a REFINANCIACION o no.

    Se decide por el remitente comparado contra el nombre del titular, que es
    el criterio de fondo (¿salió del deudor?) y no depende de la dirección de
    mail concreta que use este dataset.

    Devuelve None si no se puede determinar: es un dato faltante, no un no.
    """
    if doc is None or doc.ilegible:
        return None

    m = _REMITENTE.search(doc.texto)
    if not m:
        return None

    remitente = norm_texto(m.group(1))
    if titular:
        # El deudor escribe desde una dirección armada con su nombre.
        partes = [p for p in norm_texto(titular).split() if len(p) > 2]
        if partes and all(p in remitente for p in partes):
            return True
        return False

    # Sin nombre del titular: el remitente institucional delata al banco.
    return not any(p in remitente for p in ("cobranzas", "legales", "banco", "noreply"))


# --- extracción con modelo ---------------------------------------------------

def _prompt(doc: Documento, campos: dict[str, dict]) -> str:
    pedidos = "\n".join(f"- {c}: {PISTAS[c]}" for c in campos if c in PISTAS)
    return (
        f"Extraé estos datos del documento:\n{pedidos}\n\n"
        "Copiá los montos y fechas TAL COMO APARECEN en el texto, sin "
        "convertirlos ni reformatearlos. Si un dato no está, poné null.\n\n"
        f"DOCUMENTO:\n{doc.texto}"
    )


def _grounding(valor: object, doc: Documento) -> tuple[int | None, bool]:
    """(página donde aparece, si se encontró).

    Los números se buscan por su secuencia de dígitos, que tolera el formato
    pero no un dígito distinto. El texto se busca literal, sin acentos ni
    mayúsculas. Un campo nulo no se penaliza: la ausencia es honesta.
    """
    if valor is None:
        return None, True

    s = str(valor)
    d = digitos(s)
    if d and len(d) >= 3:
        for n, pag in enumerate(doc.paginas, 1):
            if d in digitos(pag):
                return n, True
        return None, False

    aguja = " ".join(s.lower().split())
    for n, pag in enumerate(doc.paginas, 1):
        if aguja in " ".join(pag.lower().split()):
            return n, True
    return None, False


async def extraer_documento(motor, doc: Documento, tipo: str) -> dict[str, Campo]:
    """Un documento -> sus campos, ya normalizados y con procedencia.

    Un documento ilegible devuelve los campos en nulo, pero conservando
    ``doc`` para que el motor sepa que el nulo viene de un documento que no se
    pudo leer y no de un dato ausente. Esos dos casos se tratan distinto.
    """
    from .llm import schema_json

    campos = CAMPOS_POR_DOC[tipo]
    if doc.ilegible:
        return {c: Campo(None, doc=doc.nombre) for c in campos}

    r = await motor.completar(
        [{"role": "user", "content": _prompt(doc, campos)}],
        system=SISTEMA,
        schema=schema_json(tipo.replace(".pdf", ""), campos),
        max_tokens=400,
    )

    try:
        crudo = json.loads(r.texto)
    except json.JSONDecodeError:
        # Con response_format esto no debería pasar. Si pasa, es un dato sobre
        # el modelo, no un caso a manejar en silencio.
        return {c: Campo(None, doc=doc.nombre) for c in campos}

    salida: dict[str, Campo] = {}
    for nombre in campos:
        bruto = normalizar_texto(crudo.get(nombre))
        pagina, encontrado = _grounding(bruto, doc)
        conf = doc.confianza_de(pagina) if doc.fue_ocr else None
        conv = CONVERSORES.get(nombre)
        es_monto = conv in (normalizar_monto, normalizar_entero)
        valor = (conv or (lambda v: v))(bruto)

        # Validacion numerica (punto 2): un monto que no se puede leer con
        # seguridad no se descarta ni se usa. Se anula el valor y se marca
        # `alerta_lectura` con el crudo, que motor.py convierte en Alerta y el
        # CLI muestra como "OCR leyo: ...". Dos gatillos de campo:
        #   - Detector A: separador de miles roto ("ARS 457.").
        #   - crudo con digitos pero no interpretable ("2,63000000") -> distingue
        #     "no se pudo leer" de "no estaba".
        alerta = None
        if es_monto:
            alerta = separador_miles_roto(bruto)
            if (not alerta and valor is None and bruto
                    and any(ch.isdigit() for ch in str(bruto))):
                alerta = "monto con formato no interpretable"

        salida[nombre] = Campo(
            valor=None if alerta else valor,
            doc=doc.nombre,
            pagina=pagina,
            grounding_ok=encontrado,
            ocr_confianza=conf,
            crudo=bruto,
            alerta_lectura=alerta,
        )
    return salida


async def extraer_carpeta(motor, docs: dict[str, Documento]) -> dict[str, Campo]:
    """Una carpeta de cliente -> los campos que consume :func:`riesgo.motor.analizar`.

    Los nombres de salida llevan sufijo de documento (``titular_contrato`` vs
    ``titular_escritura``) porque la comparación entre esos dos pares es
    justamente lo que detecta las contradicciones graves.
    """
    contrato = docs.get("contrato.pdf")
    escritura = docs.get("escritura.pdf")

    de_contrato = await extraer_documento(motor, contrato, "contrato.pdf") if contrato else {}
    de_escritura = await extraer_documento(motor, escritura, "escritura.pdf") if escritura else {}

    campos: dict[str, Campo] = {
        "titular_contrato": de_contrato.get("titular", Campo(None)),
        "titular_escritura": de_escritura.get("titular", Campo(None)),
        "matricula_contrato": de_contrato.get("matricula", Campo(None)),
        "matricula_escritura": de_escritura.get("matricula", Campo(None)),
        "domicilio_contrato": de_contrato.get("domicilio_titular", Campo(None)),
        "domicilio_escritura": de_escritura.get("domicilio_titular", Campo(None)),
        "capital_adeudado": de_contrato.get("capital_adeudado", Campo(None)),
        "cuotas_contrato": de_contrato.get("cuotas_contrato", Campo(None)),
        "garantia_valor": de_escritura.get("garantia_valor", Campo(None)),
        "tasacion_fecha": de_escritura.get("tasacion_fecha", Campo(None)),
    }

    recibos = docs.get("recibos.pdf")
    if recibos:
        cantidad, puntualidad = parsear_recibos(recibos)
        campos["pagos_emitidos"] = Campo(cantidad, doc=recibos.nombre, pagina=1)
        campos["puntualidad"] = Campo(puntualidad, doc=recibos.nombre, pagina=1)

    correo = docs.get("correspondencia.txt")
    titular = campos["titular_contrato"].valor
    campos["aviso_previo"] = Campo(
        parsear_correspondencia(correo, titular),
        doc=correo.nombre if correo else None,
        pagina=1 if correo else None)
    return campos


def documentos_ilegibles(docs: dict[str, Documento]) -> set[str]:
    return {n for n, d in docs.items() if d.ilegible}
