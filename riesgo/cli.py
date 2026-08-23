"""La CLI. Lo que ve el analista, y lo que se ve en el video.

    python -m riesgo.cli analizar --cliente 4421
    python -m riesgo.cli analizar --cliente 4421 --json
    python -m riesgo.cli cartera

Todo se imprime dentro de **80 columnas**: si no entra en la terminal, no
entra en la grabación.

La regla de la pantalla: **ningún número aparece sin su fuente al lado.** Un
monto sin `[contrato p.3]` es un número que el analista tiene que ir a buscar,
y el punto del sistema es justamente ahorrarle eso.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .modelo import (BAJA, CONFIRMADA, DESCARTADA, FIRME, GRAVE, MEDIA, PROBABLE,
                     Campo, Veredicto)

ANCHO = 80

# Verde para lo verificado, ámbar para lo que tiene reservas, rojo para lo
# grave. Nada de color decorativo: el color ES información.
COLOR_RUTA = {"LEGALES": "bold red", "REFINANCIACION": "bold yellow",
              "COBRANZAS": "bold green"}
COLOR_GRAVEDAD = {GRAVE: "bold red", MEDIA: "yellow", BAJA: "dim"}

# Etiquetas en ingles para la salida. Los VALORES internos siguen en espaniol
# (son claves de datos que el eval compara contra el ground_truth); aca solo se
# traduce lo que ve el usuario.
RUTEO_EN = {"LEGALES": "LEGAL", "REFINANCIACION": "REFINANCE", "COBRANZAS": "COLLECTIONS"}
GRAVEDAD_EN = {GRAVE: "SEVERE", MEDIA: "MEDIUM", BAJA: "LOW"}
ESTADO_EN = {CONFIRMADA: "CONFIRMED", PROBABLE: "PROBABLE", DESCARTADA: "DISCARDED"}
CONFIANZA_EN = {FIRME: "FIRM", "CON RESERVAS": "WITH RESERVATIONS"}

# Ancho de columna de citas. Fijo a proposito: una cita larga
# ("[correspondencia.txt p.1]", 26 chars) rompia la grilla de HISTORIAL
# (columna de 20) empujando todo lo que venia despues. Se trunca, no se
# ensancha -- la grilla no se negocia por un nombre de archivo largo.
ANCHO_CITA = 26


def _pesos(v: float | None) -> str:
    return "—" if v is None else f"${v:,.0f}".replace(",", ".")


def _campos_alertados(v: Veredicto) -> set[str]:
    """Nombres de campo cubiertos por alguna alerta -- incluidas las de
    Alerta.campo compuestas tipo "garantia_valor/capital_adeudado" (Detector B,
    cruza dos campos y no vive en ningun Campo individual). Sin esto, el campo
    involucrado se sigue mostrando "✓ verificado" al lado de la alerta que
    dice lo contrario dos renglones mas abajo.
    """
    cubiertos: set[str] = set()
    for al in v.alertas:
        cubiertos.update(al.campo.split("/"))
    return cubiertos


def _marca(c: Campo, nombre: str | None = None, alertados: set[str] = frozenset()) -> Text:
    """La confianza del campo, en una palabra."""
    if c.alerta_lectura is not None or (nombre and nombre in alertados):
        return Text("⛔ alert", style="bold red")
    if c.vacio:
        return Text("no data", style="dim")
    if not c.grounding_ok:
        return Text("⚠ unverified", style="bold red")
    if c.ocr_confianza is not None and c.ocr_confianza < 0.75:
        return Text(f"⚠ ocr {c.ocr_confianza:.0%}", style="yellow")
    return Text("✓ verified", style="green")


def _cita(campo: Campo, ancho: int = ANCHO_CITA) -> Text:
    """La cita como Text, no como str, truncada al ancho de la columna.

    Rich interpreta los corchetes como markup: pasar "[contrato.pdf p.1]" en
    crudo hace que lo lea como una etiqueta de estilo y lo borre de la
    pantalla. Justo la información que no puede faltar.
    """
    s = campo.cita() or "—"
    if len(s) > ancho:
        s = s[:ancho - 1] + "…"
    return Text(s, style="dim")


def _fila_monto(t: Table, etiqueta: str, nombre: str, campo: Campo,
                alertados: set[str] = frozenset()) -> None:
    t.add_row(etiqueta, _pesos(campo.valor), _cita(campo), _marca(campo, nombre, alertados))


def imprimir(con: Console, v: Veredicto, campos: dict[str, Campo],
             nota: str | None, disparo: str | None) -> None:
    cabecera = Text(f"CLIENT {v.cliente_id}", style="bold")
    if v.nombre:
        cabecera.append(f" — {v.nombre}", style="bold white")
    con.print()
    con.print(cabecera)
    if disparo:
        con.print(Text(f"Trigger: {disparo}", style="dim"))
    con.print()

    # --- exposicion ---------------------------------------------------
    con.print(Text("EXPOSURE", style="bold"))
    alertados = _campos_alertados(v)
    t = Table.grid(padding=(0, 2))
    t.add_column(width=20)
    t.add_column(width=13, justify="right")
    t.add_column(width=20)
    t.add_column(width=16)
    _fila_monto(t, "Amount owed", "capital_adeudado",
               campos.get("capital_adeudado", Campo(None)), alertados)
    _fila_monto(t, "Collateral", "garantia_valor",
               campos.get("garantia_valor", Campo(None)), alertados)
    # Si el capital o la garantia estan alertados, el descubierto que sale de
    # ellos no es un numero -- es un numero mal leido con formato de numero.
    # Mostrarlo igual (como hacia antes esta version) es el mismo confident-
    # wrong que el sistema existe para evitar, solo que en pantalla en vez de
    # en el ruteo.
    desc = v.derivados.get("descubierto")
    desc_confiable = not ({"capital_adeudado", "garantia_valor", "descubierto"} & alertados)
    if desc_confiable:
        t.add_row(Text("Shortfall", style="bold"),
                  Text(_pesos(desc), style="bold red" if desc else "bold"), "", "")
    else:
        t.add_row(Text("Shortfall", style="bold"),
                  Text("not computed", style="dim"), "",
                  Text("⛔ alert", style="bold red"))
    con.print(t)
    con.print()

    # --- historial ------------------------------------------------------
    con.print(Text("HISTORY", style="bold"))
    h = Table.grid(padding=(0, 2))
    h.add_column(width=44)
    h.add_column(width=ANCHO_CITA)
    punt = v.derivados.get("puntualidad")
    pagos = campos.get("pagos_emitidos", Campo(None))
    if punt is not None and pagos.valor:
        n = round(punt * pagos.valor)
        h.add_row(f"{n} of {pagos.valor} payments on time", _cita(pagos))
    aviso = campos.get("aviso_previo", Campo(None))
    if aviso.valor is True:
        h.add_row("Prior notice from borrower", _cita(aviso))
    elif aviso.valor is False:
        h.add_row(Text("No prior notice", style="dim"), _cita(aviso))
    con.print(h)
    con.print()

    # --- contradicciones -------------------------------------------------
    for hall in v.hallazgos:
        etiqueta = f"⚠ CONTRADICTION — {GRAVEDAD_EN.get(hall.gravedad, hall.gravedad)}"
        if hall.estado != CONFIRMADA:
            etiqueta += f"  ({ESTADO_EN.get(hall.estado, hall.estado).lower()})"
        # PROBABLE se lee como duda, no como hallazgo: mismo amarillo que
        # CON RESERVAS, sin importar la gravedad. Es lo que causa lo otro.
        color = "yellow" if hall.estado == PROBABLE else COLOR_GRAVEDAD.get(hall.gravedad, "")
        con.print(Text(etiqueta, style=color))
        for linea in _envolver(hall.detalle, ANCHO - 4):
            con.print(Text(f"  {linea}"))
        con.print()

    # --- alertas de lectura ------------------------------------------------
    # El campo se muestra vacio, no en cero -- coherente con la seccion 6 del
    # SDD original, no se asume un valor por defecto. El crudo del OCR va en
    # pantalla porque es lo que convierte la alerta en accionable: el analista
    # abre el documento, va a la pagina citada, y verifica en cinco segundos.
    for al in v.alertas:
        con.print(Text("⛔ READING ALERT", style="bold red"))
        cita = f"[{al.documento}{f' p.{al.pagina}' if al.pagina else ''}]" if al.documento else ""
        # Campo y cita en una linea propia -- el campo compuesto de un
        # detector cruzado (p.ej. "garantia_valor/capital_adeudado") ya ocupa
        # buena parte del ancho por si solo.
        con.print(Text(f"  {al.campo}", style="bold"), Text(f"  {cita}", style="dim"))
        for linea in _envolver(f"OCR read: {al.crudo_ocr}", ANCHO - 6):
            con.print(Text(f"    {linea}"))
        for linea in _envolver(al.motivo, ANCHO - 6):
            con.print(Text(f"    {linea}", style="dim"))
        if al.confianza_ocr is not None:
            con.print(Text(f"    page confidence: {al.confianza_ocr:.0%}", style="dim"))
        con.print(Text("  → Value unusable. Verify against the document.", style="yellow"))
        con.print()

    # --- nota ------------------------------------------------------------
    if nota:
        con.print(Text("INTERNAL NOTE", style="bold"))
        for linea in _envolver(nota, ANCHO - 4):
            con.print(Text(f"  {linea}"))
        con.print()

    # --- ruteo -----------------------------------------------------------
    con.print(Panel(
        Text.assemble((f"→ {RUTEO_EN.get(v.ruteo, v.ruteo)}", COLOR_RUTA.get(v.ruteo, "bold")),
                      ("\n" + v.motivo, "")),
        title="ROUTING", title_align="left", width=ANCHO - 2))

    # --- lo que no se pudo garantizar ------------------------------------
    if v.confianza != FIRME:
        con.print()
        con.print(Text(f"⚠ {CONFIANZA_EN.get(v.confianza, v.confianza)} — verdict issued anyway",
                       style="bold yellow"))
        for a in v.advertencias:
            if a.degrada:
                for linea in _envolver(f"{a.campo}: {a.motivo}", ANCHO - 6):
                    con.print(Text(f"    {linea}", style="yellow"))
    else:
        con.print()
        con.print(Text("✓ FIRM — no decision input has reservations",
                       style="green"))

    anotadas = [a for a in v.advertencias if not a.degrada]
    if anotadas:
        con.print()
        con.print(Text("Noted, no effect on the decision:", style="dim"))
        for a in anotadas[:4]:
            for linea in _envolver(f"{a.campo}: {a.motivo}", ANCHO - 6):
                con.print(Text(f"    {linea}", style="dim"))
    con.print()


def _envolver(texto: str, ancho: int) -> list[str]:
    """Colapsa espacios y limpia la puntuación que quedó suelta.

    Los detalles se arman interpolando la cita de cada lado, y cuando un
    documento no aporta cita queda un hueco antes del punto.
    """
    import textwrap
    limpio = " ".join(texto.split())
    limpio = re.sub(r"\s+([.,;:])", r"\1", limpio)
    return textwrap.wrap(limpio, ancho) or [""]


def a_json(v: Veredicto, campos: dict[str, Campo], nota: str | None) -> dict:
    """Salida para el script de evaluación. Todo campo lleva su procedencia."""
    def campo(c: Campo) -> dict:
        d = asdict(c)
        d["valor"] = c.valor.isoformat() if isinstance(c.valor, date) else c.valor
        return d

    return {
        "cliente_id": v.cliente_id,
        "nombre": v.nombre,
        "ruteo": v.ruteo,
        "motivo": v.motivo,
        "confianza": v.confianza,
        "derivados": v.derivados,
        "campos": {k: campo(c) for k, c in sorted(campos.items())},
        "hallazgos": [asdict(h) for h in v.hallazgos],
        "advertencias": [asdict(a) for a in v.advertencias],
        "alertas": [asdict(a) for a in v.alertas],
        "nota_interna": nota,
    }


async def analizar_cliente(carpeta: Path, cliente_id: int, *, bridge: bool,
                           provider: str | None, con_nota: bool,
                           hoy: date | None = None) -> tuple:
    from .bridge import MotorBridge
    from .documentos import leer_carpeta
    from .extraccion import documentos_ilegibles, extraer_carpeta
    from .llm import Motor
    from .motor import analizar
    from .redaccion import redactar

    docs = leer_carpeta(carpeta)

    # Modelo local por defecto; el bridge es fallback. Con --bridge se fuerza.
    if bridge:
        motor_ctx = MotorBridge(verboso=False)
    else:
        motor_ctx = Motor(provider=provider, verboso=False)
    try:
        motor = await motor_ctx.__aenter__()
    except Exception as e:
        if bridge:
            raise
        print(f"notice: local model unavailable ({type(e).__name__}: {e}); "
              f"falling back to the bridge", file=sys.stderr)
        motor_ctx = MotorBridge(verboso=False)
        motor = await motor_ctx.__aenter__()

    try:
        campos = await extraer_carpeta(motor, docs)
        v = analizar(cliente_id, campos, nombre=campos["titular_contrato"].valor,
                     docs_ilegibles=documentos_ilegibles(docs), hoy=hoy)
        nota = await redactar(motor, v) if con_nota else None
    finally:
        await motor_ctx.__aexit__(None, None, None)
    return v, campos, nota


def _disparo(carpeta: Path) -> str | None:
    t = carpeta / "trigger.json"
    if not t.exists():
        return None
    d = json.loads(t.read_text(encoding="utf-8"))
    dias = d.get("dias_atraso")
    return f"{dias} days past due" if dias else None


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="riesgo", description=__doc__)
    sub = ap.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("analizar", help="analyze a client folder")
    a.add_argument("--cliente", required=True, help="folder id or name")
    a.add_argument("--dataset", default="dataset")
    a.add_argument("--json", action="store_true", dest="como_json")
    a.add_argument("--sin-nota", action="store_true",
                   help="skip the drafted note (one less model call)")
    a.add_argument("--bridge", action="store_true",
                   help="force the HTTP bridge instead of the local model "
                        "(default: local, with the bridge as fallback)")
    a.add_argument("--provider")

    c = sub.add_parser("cartera", help="summary over all folders")
    c.add_argument("--dataset", default="dataset")

    args = ap.parse_args(argv)

    if args.comando == "cartera":
        from .resumen import main as resumen_main
        return resumen_main(["--dataset", args.dataset])

    base = Path(args.dataset)
    carpeta = base / args.cliente
    if not carpeta.is_dir():
        carpeta = base / f"cliente_{args.cliente}"
    if not carpeta.is_dir():
        print(f"not found: {carpeta}", file=sys.stderr)
        return 1

    cliente_id = int("".join(ch for ch in carpeta.name if ch.isdigit()) or 0)
    v, campos, nota = asyncio.run(analizar_cliente(
        carpeta, cliente_id, bridge=args.bridge, provider=args.provider,
        con_nota=not args.sin_nota))

    if args.como_json:
        print(json.dumps(a_json(v, campos, nota), ensure_ascii=False, indent=2))
    else:
        imprimir(Console(width=ANCHO), v, campos, nota, _disparo(carpeta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
