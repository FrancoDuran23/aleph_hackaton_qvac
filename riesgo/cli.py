"""La CLI. Lo que ve el analista, y lo que se ve en el video.

    riesgo analizar --cliente 4471
    riesgo analizar --cliente 4471 --json
    riesgo cartera

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

from .modelo import BAJA, CONFIRMADA, FIRME, GRAVE, MEDIA, Campo, Veredicto

ANCHO = 80

# Verde para lo verificado, ámbar para lo que tiene reservas, rojo para lo
# grave. Nada de color decorativo: el color ES información.
COLOR_RUTA = {"LEGALES": "bold red", "REFINANCIACION": "bold yellow",
              "COBRANZAS": "bold green"}
COLOR_GRAVEDAD = {GRAVE: "bold red", MEDIA: "yellow", BAJA: "dim"}


def _pesos(v: float | None) -> str:
    return "—" if v is None else f"${v:,.0f}".replace(",", ".")


def _marca(c: Campo) -> Text:
    """La confianza del campo, en una palabra."""
    if c.vacio:
        return Text("sin dato", style="dim")
    if not c.grounding_ok:
        return Text("⚠ no verificado", style="bold red")
    if c.ocr_confianza is not None and c.ocr_confianza < 0.75:
        return Text(f"⚠ ocr {c.ocr_confianza:.0%}", style="yellow")
    return Text("✓ verificado", style="green")


def _cita(campo: Campo) -> Text:
    """La cita como Text, no como str.

    Rich interpreta los corchetes como markup: pasar "[contrato.pdf p.1]" en
    crudo hace que lo lea como una etiqueta de estilo y lo borre de la
    pantalla. Justo la información que no puede faltar.
    """
    return Text(campo.cita() or "—", style="dim")


def _fila_monto(t: Table, etiqueta: str, campo: Campo) -> None:
    t.add_row(etiqueta, _pesos(campo.valor), _cita(campo), _marca(campo))


def imprimir(con: Console, v: Veredicto, campos: dict[str, Campo],
             nota: str | None, disparo: str | None) -> None:
    cabecera = Text(f"CLIENTE {v.cliente_id}", style="bold")
    if v.nombre:
        cabecera.append(f" — {v.nombre}", style="bold white")
    con.print()
    con.print(cabecera)
    if disparo:
        con.print(Text(f"Disparo: {disparo}", style="dim"))
    con.print()

    # --- exposicion ---------------------------------------------------
    con.print(Text("EXPOSICION", style="bold"))
    t = Table.grid(padding=(0, 2))
    t.add_column(width=20)
    t.add_column(width=13, justify="right")
    t.add_column(width=20)
    t.add_column(width=16)
    _fila_monto(t, "Capital adeudado", campos.get("capital_adeudado", Campo(None)))
    _fila_monto(t, "Garantia", campos.get("garantia_valor", Campo(None)))
    desc = v.derivados.get("descubierto")
    t.add_row(Text("Descubierto", style="bold"),
              Text(_pesos(desc), style="bold red" if desc else "bold"), "", "")
    con.print(t)
    con.print()

    # --- historial ------------------------------------------------------
    con.print(Text("HISTORIAL", style="bold"))
    h = Table.grid(padding=(0, 2))
    h.add_column(width=44)
    h.add_column(width=20)
    punt = v.derivados.get("puntualidad")
    pagos = campos.get("pagos_emitidos", Campo(None))
    if punt is not None and pagos.valor:
        n = round(punt * pagos.valor)
        h.add_row(f"{n} de {pagos.valor} pagos puntuales", _cita(pagos))
    aviso = campos.get("aviso_previo", Campo(None))
    if aviso.valor is True:
        h.add_row("Aviso previo del deudor", _cita(aviso))
    elif aviso.valor is False:
        h.add_row(Text("Sin aviso previo", style="dim"), _cita(aviso))
    con.print(h)
    con.print()

    # --- contradicciones -------------------------------------------------
    for hall in v.hallazgos:
        etiqueta = f"⚠ CONTRADICCION — {hall.gravedad.upper()}"
        if hall.estado != CONFIRMADA:
            etiqueta += f"  ({hall.estado.lower()})"
        con.print(Text(etiqueta, style=COLOR_GRAVEDAD.get(hall.gravedad, "")))
        for linea in _envolver(hall.detalle, ANCHO - 4):
            con.print(Text(f"  {linea}"))
        con.print()

    # --- nota ------------------------------------------------------------
    if nota:
        con.print(Text("NOTA INTERNA", style="bold"))
        for linea in _envolver(nota, ANCHO - 4):
            con.print(Text(f"  {linea}"))
        con.print()

    # --- ruteo -----------------------------------------------------------
    con.print(Panel(
        Text.assemble((f"→ {v.ruteo}", COLOR_RUTA.get(v.ruteo, "bold")),
                      ("\n" + v.motivo, "")),
        title="RUTEO", title_align="left", width=ANCHO - 2))

    # --- lo que no se pudo garantizar ------------------------------------
    if v.confianza != FIRME:
        con.print()
        con.print(Text(f"⚠ {v.confianza} — el veredicto se emitio igual",
                       style="bold yellow"))
        for a in v.advertencias:
            if a.degrada:
                for linea in _envolver(f"{a.campo}: {a.motivo}", ANCHO - 6):
                    con.print(Text(f"    {linea}", style="yellow"))
    else:
        con.print()
        con.print(Text("✓ FIRME — ningun dato de la decision tiene reservas",
                       style="green"))

    anotadas = [a for a in v.advertencias if not a.degrada]
    if anotadas:
        con.print()
        con.print(Text("Anotado, sin efecto en la decision:", style="dim"))
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
    motor_ctx = MotorBridge(verboso=False) if bridge else Motor(provider=provider,
                                                                verboso=False)
    async with motor_ctx as motor:
        campos = await extraer_carpeta(motor, docs)
        v = analizar(cliente_id, campos, nombre=campos["titular_contrato"].valor,
                     docs_ilegibles=documentos_ilegibles(docs), hoy=hoy)
        nota = await redactar(motor, v) if con_nota else None
    return v, campos, nota


def _disparo(carpeta: Path) -> str | None:
    t = carpeta / "trigger.json"
    if not t.exists():
        return None
    d = json.loads(t.read_text(encoding="utf-8"))
    dias = d.get("dias_atraso")
    return f"{dias} dias de atraso" if dias else None


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(prog="riesgo", description=__doc__)
    sub = ap.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("analizar", help="analiza una carpeta de cliente")
    a.add_argument("--cliente", required=True, help="id o nombre de carpeta")
    a.add_argument("--dataset", default="dataset")
    a.add_argument("--json", action="store_true", dest="como_json")
    a.add_argument("--sin-nota", action="store_true",
                   help="saltea la redaccion (una llamada menos)")
    a.add_argument("--bridge", action="store_true", default=True)
    a.add_argument("--provider")

    c = sub.add_parser("cartera", help="resumen sobre todas las carpetas")
    c.add_argument("--dataset", default="dataset")

    args = ap.parse_args(argv)

    if args.comando == "cartera":
        from .resumen import main as resumen_main
        return resumen_main()

    base = Path(args.dataset)
    carpeta = base / args.cliente
    if not carpeta.is_dir():
        carpeta = base / f"cliente_{args.cliente}"
    if not carpeta.is_dir():
        print(f"no encontre {carpeta}", file=sys.stderr)
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
