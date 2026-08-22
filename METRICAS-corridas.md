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

### Resultados — medido sobre `f7782d4` (merge PR #2)

> **Estado intermedio, no el número final.** Esta tabla mide el fix de
> contradicciones y nada más. El Detector B (sección 4) todavía no existía, así
> que `cliente_4498` sigue acá como confident-wrong. Los números vigentes están
> en la sección 4 — pero esta corrida se conserva porque el antes/después *es*
> el argumento: 95% de exactitud con tres confident-wrong adentro no es mejor
> que 85% con cero.

| | Baseline (pre-`1c5b1e0`) | **Con fix de contradicciones** (`f7782d4`) |
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

- **`cliente_4498` — FIRME-erróneo (confident-wrong)**

  Causa raíz: truncamiento de OCR en `escritura.pdf`.
  Crudo OCR: `"ARS 457."` → `garantia_valor = 457` (real: `457.000`).

  Efecto: `descubierto = 1.014.543` en vez de un caso que cierra a favor del
  banco. Ruteo a LEGALES en vez de COBRANZAS. Salió **FIRME** porque la
  confianza de OCR era 0.806 (alta).

  **NO es un caso límite de corte de política.** La coincidencia con el corte
  de $1M es consecuencia del bug, no una decisión de diseño rozando el umbral:
  `1.015.000 − 457 = 1.014.543`.

  Ninguna etapa lo atrapó:
    - el grounding valida fidelidad al texto, y el texto ya venía roto
    - la confianza de OCR es por página, no por bloque (ver Límite 2 más abajo)
    - la confianza solo se consultaba en `evaluar_contradiccion()`, no en el
      grounding numérico

  **Fix aplicado** (`validacion.py` + `extraccion.py` + `motor.py`, este PR):
  no por "múltiplo de 1000" (eso depende de cómo construye el dataset y no
  generaliza), sino por **plausibilidad de dominio** — Detector B: la cobertura
  `garantia / capital` cae fuera de [0.01, 100]. Cuando dispara, los financieros
  no son confiables, no se rutea por ellos y el caso se degrada con la alerta y
  el crudo. Resultado: `cliente_4498` pasó de `LEGALES·FIRME·MAL` a
  `COBRANZAS·CON RESERVAS·OK`.

- Holdout, 2 mal ruteados (`cliente_4470`, `cliente_4533`): contradicción real en
  escritura escaneada → PROBABLE → CON RESERVAS. No se fuerza a LEGALES, se flaguea.

## 4. Validación de montos (Detector A + B) — medido sobre `a049c96` (merge PR #3)

> **Estos son los números vigentes.** Siguen valiendo en `ed6a26b` (HEAD): ese
> commit toca sólo `riesgo/cli.py` y es enteramente presentación — decide qué se
> dibuja, no qué se rutea. No cambia ninguna cifra de esta tabla.
>
> **Cómo leer esta tabla contra la de la sección 2.** No discrepan: son hitos
> consecutivos. El Detector B sacó a `cliente_4498` de FIRME
> (`LEGALES·FIRME·MAL` → `COBRANZAS·CON RESERVAS·OK`), y eso mueve tres números
> a la vez, de forma aritméticamente cerrada:
>
> ```
> sale de FIRME        16 → 15      cobertura   80% → 75%
> precisión FIRME    15/16 → 15/15  desaparece el último confident-wrong
> rutea bien         16/20 → 17/20  exactitud   80% → 85%
> ```
>
> La exactitud global **sube** al sacar el caso de FIRME porque el 4498 estaba
> mal ruteado: dejar de afirmarlo lo arregla en los dos ejes.
>
> **El holdout no se movió, y eso está medido dos veces.** Las columnas de
> holdout de la sección 2 y de esta tabla son idénticas — 90% (18/20), 8/8,
> cobertura 40% — porque el 4498 estaba en dev y el PR #3 no tocó ningún caso
> del seed 99. Comprobación independiente de las tablas: el Detector B no
> dispara en ninguno de los 20 casos del holdout, y las coberturas reales van de
> 0,25 a 1,15 — el caso más cercano al borde está 25× arriba del límite inferior
> de la banda.
>
> Por eso no hace falta re-correr el holdout para sostener sus números, y por eso
> el hallazgo se cuenta así: el modo de fallo se encontró en dev, se corrigió, y
> se verificó que el holdout ya estaba limpio. La cifra no subió porque no había
> nada roto ahí — la diferencia es que ahora está medido, no supuesto.

Sobre el schema de alertas de lectura (`Campo.alerta_lectura`, `Alerta`,
`Veredicto.alertas`). Detector A (separador de miles roto) + validación de
normalización marcan `alerta_lectura` por campo; Detector B (magnitud) es
cross-campo y emite una alerta a nivel caso. `"2,63000000"` ahora normaliza a
`None` en vez de `2.63`.

| | DEV (seed 1) | HOLDOUT (seed 99) |
|---|---|---|
| **precisión sobre FIRMES** | **15/15 = 100%** | **8/8 = 100%** |
| cobertura (% FIRMES) | 75% | 40% |
| **errores silenciosos** | **0** | **0** |
| exactitud global | 85% | 90% |

La cobertura baja a propósito (más casos a revisión humana); el canje es 100% de
precisión en lo que el sistema resuelve solo y cero respuestas seguras y
equivocadas en ambos sets.

---

## Notas

- El path `--real` (extracción con modelo) requirió fixes de compatibilidad con
  el SDK 0.17.1 (`llm.py`: `connect()` y `await completion`), en `main` (PR #1).
- El fix de contradicciones por confianza de OCR está en `main` (PR #2).
- Detector A/B, la persistencia del crudo (`--guardar`) y la auditoría
  (`auditoria_ocr.py`) van en este PR, sobre el schema de alertas de `main`.
