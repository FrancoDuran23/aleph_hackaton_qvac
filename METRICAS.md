# Métricas medidas — motor de análisis de riesgo

**Aleph Hackathon 2026 · Track QVAC**

Todo lo de acá salió de correr código, no de estimar. Cada número dice con qué comando se reproduce.

Medición: 2026-08-22 · Modelo: `QWEN3_1_7B_INST_Q4` · Backend: CPU

---

## 0. Lo que hay que decir primero

**El 20/20 en modo oracle no es un logro y no lo vamos a presentar como tal.**

`gen_dataset.py:410` produce el `ruteo_esperado` con `descubierto > 1_000_000` y el mismo orden de reglas que implementa el ruteador. Reproducirlo verifica que el código coincide con la especificación — no mide capacidad del sistema.

El número que sí depende de nosotros es **precisión sobre los casos FIRMES**, porque depende de la extracción y de la clasificación de confianza: dos cosas que el generador no regaló.

> Regla: antes de reportar una métrica, preguntarse si el generador ya sabía la respuesta.

---

## 1. Inferencia local — Hito 1

```bash
.venv/Scripts/python -m riesgo.hito1 --bridge
```

| Paso | Qué verifica | Resultado |
|---|---|---|
| 1 | El modelo carga y responde | OK |
| 2 | `temp=0` llega al motor | `['75', '75', '75']` en 3 corridas |
| 3 | `response_format` restringe el decoder | parsea sin limpiar nada |
| 4 | Extracción contra valores conocidos | **5/5 campos** |

**Paso 2 — determinismo.** Tres corridas del mismo prompt devuelven el mismo número. Es la prueba de que `generationParams` viaja anidado y de que el campo se llama `temp`, no `temperature`. Sin esto la inferencia corre con sampling por defecto y **ninguna medición posterior es reproducible**.

**Paso 3 — JSON garantizado, no pedido.** Salida cruda del modelo, sin post-procesar:

```json
{
  "capital_original": 2400000,
  "capital_adeudado": 1494000,
  "cuotas_contrato": 32,
  "titular": "Juan Perez",
  "matricula": "11-59965",
  "domicilio_titular": "Av. Rivadavia 4471, CABA"
}
```

Sin backticks, sin preámbulo, sin truncar. `response_format` con `json_schema` se compila a una gramática GBNF en llama.cpp: el decoder **no puede** emitir nada que viole el schema. Cero reintentos de parseo en todo el desarrollo.

En el paso 4 el modelo distinguió `capital_original` de `capital_adeudado` estando en la misma página, y normalizó los dos formatos de monto a número.

---

## 2. Latencia

| Métrica | Valor |
|---|---|
| Extracción de 6 campos | **9,8 s** |
| Throughput | 17 tok/s (CPU) |
| Time to first token | 485 ms |
| Proyección: 20 casos × 4 documentos | ~13 min por iteración |

### La palanca que más rindió: apagar el razonamiento

Qwen3-1.7B es un modelo de razonamiento: emite un bloque `<think>` antes de responder. Medido sobre la misma pregunta:

| Configuración | Tokens generados | Texto devuelto |
|---|---|---|
| Por defecto | 58 | `Hola!` |
| `reasoning_budget: 0` | **9** | `Hola! ¿Cómo puedo ayudarte hoy?` |

**6,4× menos tokens para una respuesta mejor.** Con `predict` bajo el efecto es peor que lento: el modelo gasta el presupuesto entero pensando y devuelve texto **vacío** con `stop_reason: "length"`.

Para extracción el razonamiento es desperdicio puro: el modelo no deduce nada, copia campos que ya están en el texto.

---

## 3. Comparación de valores — números y texto se comparan distinto

```bash
.venv/Scripts/python -m riesgo.calibrar
```

### Números: dígitos exactos, nunca fuzzy

40 montos reales del ground truth, cada uno en 3 formatos distintos:

| | dígitos exactos | `partial_ratio ≥ 90` |
|---|---|---|
| Valores reales encontrados | **120/120** | **40/120** |
| Alucinaciones tragadas | 0/40 | 0/40 |

El fuzzy no traga alucinaciones — **se pierde dos de cada tres valores legítimos**. Los separadores de miles rompen la subsecuencia. Y un grounding que no encuentra el valor real marca el campo como inventado, degradando el caso entero por nada.

**Regla: números → dígitos exactos. Texto → fuzzy.**

### Nombres: Jaro-Winkler combinado con token_sort_ratio

| Umbral 0.85 | solo JW | JW + TSR |
|---|---|---|
| Falsas alarmas (misma persona, escrita distinto) | 125/200 | **65/200** |
| Detecta personas distintas | 190/190 | 190/190 |

Jaro-Winkler pondera el prefijo, así que `Perez, Juan` contra `Juan Perez` da bajísimo aunque sean la misma persona. Combinar con `token_sort_ratio`, que ordena las palabras antes de comparar, corta las falsas alarmas a la mitad.

> **Sobre este dataset el problema no se presenta.** `gen_dataset.py` escribe siempre `Nombre Apellido` — verificado extrayendo el texto de los PDFs, no leyendo el generador. Contra el ground truth real cualquier umbral entre 0.80 y 0.95 da **8/8 detectadas, 0 falsos positivos**. La combinación queda como seguro barato para documentos reales.

---

## 4. La métrica principal — precisión sobre los FIRMES

```bash
.venv/Scripts/python -m riesgo.evaluar
```

El sistema **siempre** produce un veredicto. Nada frena el ruteo. Lo que varía es cuánta confianza declara tener:

- **FIRME** — ningún dato que influyó en la decisión tiene reservas
- **CON RESERVAS** — ruteó igual, con N advertencias anotadas

Escenario medido: el OCR todavía no está enchufado, así que las 6 escrituras escaneadas extraen **0 caracteres**.

```
14 FIRMES         → 14/14 correctos      precisión 100%
 6 CON RESERVAS   →  2/6  correctos

Cobertura: 70%
Contradicciones GRAVES: 6/11 detectadas
```

**Los 4 casos mal ruteados salieron los 4 marcados CON RESERVAS.** Cero errores silenciosos.

| Caso | Esperado | Obtenido | Confianza |
|---|---|---|---|
| `cliente_4421` | LEGALES | COBRANZAS | CON RESERVAS |
| `cliente_4470` | LEGALES | COBRANZAS | CON RESERVAS |
| `cliente_4512` | LEGALES | COBRANZAS | CON RESERVAS |
| `cliente_4519` | LEGALES | COBRANZAS | CON RESERVAS |

### Por qué esto es más fuerte que "16 de 20"

Separa lo que el sistema **sabe** de lo que **cree**. Un analista puede confiar en los 14 FIRMES sin revisarlos, y sabe exactamente cuáles de los otros 6 mirar y por qué.

> **Para el video:** *"resuelve el 70% de los casos con confianza plena y en ese 70% no se equivoca nunca; el 30% restante lo rutea igual, pero declara exactamente por qué no está seguro"*.

### El detalle de diseño que lo hace funcionar

**Documento vacío no es documento limpio.** Sin OCR la escritura extrae cero caracteres, todos sus campos salen `null`, no se detecta ninguna contradicción y el caso rutea a COBRANZAS **con cara de limpio**. Ese es el peor error posible de este sistema.

Por eso un `null` causado por un documento ilegible **degrada** el caso, mientras que un `null` normal solo se anota. Es la distinción que convierte 4 errores silenciosos en 4 advertencias explícitas.

---

## 5. Umbrales — qué está fijado y qué no

| Umbral | Valor | Cómo se decidió |
|---|---|---|
| Similitud de nombres | 0.85 | calibrado contra ground truth |
| Grounding numérico | exacto | medido: fuzzy pierde 2 de cada 3 |
| Antigüedad de tasación | 5 años | política |
| Tolerancia de puntualidad | 5 días | política |
| Corte de descubierto | $1.000.000 | **política, no calibración** |
| Confianza de OCR | sin fijar | pendiente de la distribución real sobre los 6 escaneados |

**Sobre el corte de descubierto.** El barrido existe pero es circular: $1M gana porque es el número con el que se generaron los datos.

> **Para el video:** *"lo fijamos en un millón; en una cartera real ese número sale de la política de riesgo del banco, no de los datos"*.

---

## 6. Inferencia 100% local — verificación

Ningún camino vivo del motor de riesgo sale a la red. Verificado por grep sobre los call sites:

| Módulo | Importa | Estado |
|---|---|---|
| `app/answer.py:7` | `from toolkit import qvac_brain as brain` | local |
| `hybrid_rag/multihop.py:27` | `from .. import qvac_brain as brain` | local |
| `hybrid_rag/multihop.py:29` | `from ..qvac_brain.embeddings import embed` | local |
| `hybrid_rag/ingest.py:21` | `from ..qvac_brain.embeddings import dim, embed` | local |

⚠️ **Los alias `llamar_claude` / `llamar_claude_sync` conservan el nombre viejo** para que la migración fuera solo cambiar imports (`qvac_brain/brain.py:123`). El nombre engaña: la inferencia es local. Conviene renombrarlos antes de entregar — un `grep claude` del jurado sobre el camino caliente obliga a explicar, y explicar cuesta.

Deuda a limpiar: `anthropic` y `google-genai` siguen en `requirements.txt`, y `toolkit/claude_brain/` sigue en el árbol sin que nadie lo importe.

---

## 7. Cómo reproducir todo

```bash
tar xzf dataset_riesgo.tar.gz
.venv/Scripts/python -m riesgo.calibrar          # sección 3
.venv/Scripts/python -m riesgo.evaluar           # sección 4
.venv/Scripts/python -m riesgo.hito1 --bridge    # secciones 1 y 2 (necesita el bridge)
```
