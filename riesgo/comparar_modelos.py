"""Comparativa de modelos: por que elegimos el que elegimos, medido.

Responde tres preguntas distintas con tres modelos, no cinco variantes del
mismo:

    QWEN3_600M_INST_Q4               ¿alcanza con el mas chico?
    QWEN3_1_7B_INST_Q4               el candidato
    HEALTHCARE_1_7B_MEDICAL_Q4_K_M   ¿un fine-tune de dominio degrada
                                     fuera de su dominio?

El tercero es el interesante: mismo tamano y misma familia que el candidato,
distinta especializacion. Si degrada, es evidencia sobre transferencia de
dominio en el catalogo propio de QVAC.

Diseno, para que sea barato:

  * pocos casos (5 por defecto) -- si la diferencia es grande se ve con 5, y
    si es chica no alcanza ni con 20
  * solo extraccion, sin pipeline completo: campos correctos contra el
    ground truth y listo
  * mismo prompt, misma semilla, temp 0 -- cambiar dos cosas a la vez no
    deja atribuir nada

Cada modelo son ~1-3 GB de descarga la primera vez. Corre esto al final,
con el pipeline ya estable.

Uso:
    python -m riesgo.comparar_modelos
    python -m riesgo.comparar_modelos --casos 5 --dataset dataset
    python -m riesgo.comparar_modelos --bridge          # contra el endpoint HTTP
    python -m riesgo.comparar_modelos --modelos QWEN3_600M_INST_Q4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Constantes del SDK. Se resuelven por nombre para no romper el import cuando
# el SDK no esta instalado (la maquina que solo usa --bridge no lo necesita).
MODELOS_POR_DEFECTO = [
    "QWEN3_600M_INST_Q4",
    "QWEN3_1_7B_INST_Q4",
    "HEALTHCARE_1_7B_MEDICAL_Q4_K_M",
]

# Los campos del contrato, que es el documento denso y nativo: mide extraccion
# sin mezclarla con la calidad del OCR.
CAMPOS_MEDIDOS = ("capital_original", "capital_adeudado", "cuotas_contrato",
                  "titular", "matricula")


@dataclass
class Resultado:
    modelo: str
    casos: int = 0
    campos_ok: int = 0
    campos_total: int = 0
    json_ok: int = 0
    alucinaciones: int = 0          # valor que no aparece en el documento
    segundos: list[float] = field(default_factory=list)
    error: str | None = None

    @property
    def seg_por_caso(self) -> float | None:
        return statistics.mean(self.segundos) if self.segundos else None

    def fila(self) -> str:
        if self.error:
            return f"  {self.modelo:<32} ERROR: {self.error[:40]}"
        pct_json = f"{self.json_ok / self.casos:.0%}" if self.casos else "—"
        pct_alu = f"{self.alucinaciones / self.campos_total:.0%}" if self.campos_total else "—"
        seg = f"{self.seg_por_caso:.1f}" if self.seg_por_caso else "—"
        return (f"  {self.modelo:<32} {self.campos_ok:>3}/{self.campos_total:<7} "
                f"{pct_json:>6}  {pct_alu:>6}  {seg:>6}")


def _resolver(nombre: str):
    """Nombre de constante -> el valor que espera `model_src`."""
    import tetherto.qvac_sdk.models as m
    if not hasattr(m, nombre):
        raise ValueError(f"{nombre} no es una constante del SDK")
    return getattr(m, nombre)


async def _medir_modelo(nombre: str, casos: list[dict], dataset: Path,
                        bridge: bool) -> Resultado:
    from .documentos import leer_documento
    from .extraccion import CAMPOS_POR_DOC, extraer_documento

    r = Resultado(modelo=nombre)
    try:
        if bridge:
            from .bridge import MotorBridge
            ctx = MotorBridge(verboso=False)
            ctx.modelo = nombre          # el bridge toma el modelo por nombre
        else:
            from .llm import Motor
            ctx = Motor(modelo=_resolver(nombre), verboso=False)
    except Exception as e:                # noqa: BLE001 - queremos el motivo en la tabla
        r.error = str(e)
        return r

    try:
        async with ctx as motor:
            for c in casos:
                doc = leer_documento(dataset / c["carpeta"] / "contrato.pdf")
                t0 = time.perf_counter()
                campos = await extraer_documento(motor, doc, "contrato.pdf")
                r.segundos.append(time.perf_counter() - t0)
                r.casos += 1

                # JSON valido = el schema produjo algo parseable y con campos.
                if any(campos.get(k) for k in CAMPOS_POR_DOC["contrato.pdf"]):
                    r.json_ok += 1

                gt = c["campos"]
                esperado = {
                    "capital_original": gt.get("capital_original"),
                    "capital_adeudado": gt.get("capital_adeudado"),
                    "cuotas_contrato": gt.get("cuotas_contrato"),
                    "titular": c.get("nombre"),
                    "matricula": gt.get("matricula_contrato"),
                }
                for campo in CAMPOS_MEDIDOS:
                    got = campos.get(campo)
                    if got is None:
                        r.campos_total += 1
                        continue
                    r.campos_total += 1
                    esp = esperado.get(campo)
                    if _coincide(got.valor, esp):
                        r.campos_ok += 1
                    # Alucinacion: el valor no se encontro en el documento.
                    if got.valor is not None and not got.grounding_ok:
                        r.alucinaciones += 1
    except Exception as e:                # noqa: BLE001
        r.error = str(e)
    return r


def _coincide(got, esp) -> bool:
    if got is None or esp is None:
        return got is esp
    if isinstance(got, (int, float)) and isinstance(esp, (int, float)):
        return abs(float(got) - float(esp)) < 1
    return str(got).strip().casefold() == str(esp).strip().casefold()


async def main_async(args) -> int:
    dataset = Path(args.dataset)
    gt_path = dataset / "ground_truth.json"
    if not gt_path.exists():
        print(f"falta {gt_path} -- corre: tar xzf dataset_riesgo.tar.gz")
        return 1
    casos = json.loads(gt_path.read_text(encoding="utf-8"))[:args.casos]

    print(f"\nCOMPARATIVA DE MODELOS -- {len(casos)} casos, solo extraccion del contrato")
    print(f"temp 0, seed fija, mismo prompt. {'bridge HTTP' if args.bridge else 'SDK local'}\n")
    print(f"  {'modelo':<32} {'campos':>11} {'JSON':>6}  {'aluc.':>6}  {'seg':>6}")
    print("  " + "-" * 68)

    resultados = []
    for nombre in args.modelos:
        r = await _medir_modelo(nombre, casos, dataset, args.bridge)
        resultados.append(r)
        print(r.fila(), flush=True)

    print()
    _lectura(resultados)

    if args.guardar:
        Path(args.guardar).write_text(
            json.dumps([r.__dict__ for r in resultados], indent=2, default=str),
            encoding="utf-8")
        print(f"\n  guardado en {args.guardar}")
    return 0


def _lectura(resultados: list[Resultado]) -> None:
    """La conclusion, si los numeros la sostienen. No inventa una si no."""
    utiles = [r for r in resultados if not r.error and r.campos_total]
    if len(utiles) < 2:
        print("  (sin datos suficientes para comparar)")
        return

    mejor = max(utiles, key=lambda r: r.campos_ok / r.campos_total)
    print(f"  Mejor extraccion: {mejor.modelo} "
          f"({mejor.campos_ok}/{mejor.campos_total})")

    chico = next((r for r in utiles if "600M" in r.modelo), None)
    cand = next((r for r in utiles if "QWEN3_1_7B" in r.modelo), None)
    medico = next((r for r in utiles if "HEALTHCARE" in r.modelo), None)

    if chico and cand:
        d = (cand.campos_ok / cand.campos_total) - (chico.campos_ok / chico.campos_total)
        print(f"  600M vs 1.7B: {d:+.0%} de campos correctos a favor del 1.7B")
    if medico and cand:
        d = (medico.campos_ok / medico.campos_total) - (cand.campos_ok / cand.campos_total)
        print(f"  fine-tune medico vs instruct, mismo tamano: {d:+.0%}")
        print("    (negativo = el fine-tune de dominio degrada fuera de su dominio)")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--casos", type=int, default=5)
    ap.add_argument("--dataset", default="dataset")
    ap.add_argument("--bridge", action="store_true",
                    help="usar el endpoint HTTP en vez del SDK local")
    ap.add_argument("--modelos", nargs="+", default=MODELOS_POR_DEFECTO)
    ap.add_argument("--guardar", help="ruta JSON donde volcar los resultados")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
