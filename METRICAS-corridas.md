# Métricas — corridas reales del pipeline QVAC

Inferencia **100% local** (OCR + LLM sobre QVAC). Sin APIs cloud.

## Entorno

| | |
|---|---|
| Máquina | Intel Core Ultra 5 125U (15 W, sin GPU), 16 GB RAM |
| SO / runtime | Windows 11 · Python 3.12 · Node v22.19 |
| SDK | tetherto-qvac-sdk 0.17.1 |
| Modelo OCR | `OCR_LATIN` |
| Modelo texto | `QWEN3_1_7B_INST_Q4` (~1.2 GB) |
| Determinismo | temp 0, seed 7 |

---

## 1. OCR sobre escrituras escaneadas (`benchmark_ocr.py`, dev set)

| Métrica | Valor |
|---|---|
| Latencia OCR | 7–13 s/página, **prom ~9–12 s** (varía con la carga) |
| Recuperación de campos en el texto OCR | **23/24 = 95.8%** |

Con los defaults del SDK la misma página tardaba **~350 s** (config afinada en `riesgo/ocr.py`).

---

## 2. Pipeline completo (`riesgo.evaluar --real`) — baseline vs fix

`--real` = extracción con el modelo desde los PDFs (incluye OCR en las escaneadas).

### El problema (baseline, antes del fix de confianza)

El ruido de OCR generaba **contradicciones falsas** (una matrícula/nombre con un
carácter mal leído parecía "otro inmueble/persona") que forzaban el ruteo a
LEGALES. Se notaba poco en el dev (6 escaneadas) y mucho en el holdout (12).

### El fix (elegido)

Si un campo comparado viene de OCR, la contradicción se marca **PROBABLE** en vez
de CONFIRMADA. Solo una GRAVE **CONFIRMADA** fuerza LEGALES; una PROBABLE no
fuerza y **degrada el caso a CON RESERVAS** (revisión humana). En documentos
nativos el comportamiento es idéntico. (`contradicciones.py`, `motor.py`.)

### Resultados

| | Baseline | **Con fix** |
|---|---|---|
| **Dev (seed 1, 20 casos)** | | |
| · Ruteo global | 95% (19/20) | 80% (16/20) |
| · **FIRME precisión** | 3 confident-wrong | **94% (15/16)** |
| · Cobertura FIRME | 100% | 80% |
| **Holdout (seed 99, 20 casos)** | | |
| · Ruteo global | 65% (13/20) | **90% (18/20)** |
| · **FIRME precisión** | — | **100% (8/8)** |
| · Cobertura FIRME | — | 40% |
| · Confident-wrong | varios | **0** |
| Latencia | ~18–26 s/caso | ~20–26 s/caso |

**Lectura:** cuando el sistema resuelve solo (FIRME) acierta **94% dev / 100%
holdout**; lo incierto (incl. escaneadas mal leídas) sale CON RESERVAS a revisión.
El holdout —el test de generalización que nadie vio— sube de 65% a **90%**, con
**cero respuestas seguras y equivocadas**.

### Casos que quedan a revisión / error

- Dev, único FIRME-erróneo: `cliente_4498` — no es OCR, es el **corte de política**
  ($1.014.543 vs corte $1.000.000).
- Holdout, 2 mal ruteados (`cliente_4470`, `cliente_4533`): contradicción real en
  escritura escaneada → PROBABLE → CON RESERVAS. No se fuerza a LEGALES, se flaguea.

---

## Notas

- El path `--real` (extracción con modelo) requirió fixes de compatibilidad con
  el SDK 0.17.1 (`llm.py`: `connect()` y `await completion`), ya en `main` (PR #1).
- El fix de confianza (esta corrida) está en la rama del PR, pendiente de mergear.
- Contradicciones detectadas: el detector sigue marcando las diferencias; lo que
  cambia es que las de OCR no fuerzan ruteo (quedan PROBABLE + CON RESERVAS).
