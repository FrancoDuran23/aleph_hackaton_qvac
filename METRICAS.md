# Métricas medidas — motor de análisis de riesgo

**Aleph Hackathon 2026 · Track QVAC**

Todo lo de acá salió de correr código, no de estimar. Cada número dice con qué comando se reproduce.

## Configuración de la medición

Todo número de este documento corresponde a **una** configuración. Si se cambia
el modelo hay que volver a correr los tres comandos de la sección 7 y anotar
una fila nueva — no editar la existente.

| | |
|---|---|
| **Modelo de generación** | `QWEN3_1_7B_INST_Q4` |
| **Modelo de embeddings** | `EMBEDDINGGEMMA_300M_Q4_0` |
| **Backend** | CPU |
| **Parámetros** | `temp=0`, `top_p=1`, `seed=7`, `reasoning_budget=0` |
| **Fecha** | 2026-08-22 |

### Comparativa entre modelos — PENDIENTE, tarea del final

Las métricas de las secciones 3, 4 y 5 son de la lógica y **no dependen del
modelo**: se calculan sobre el ground truth, sin inferencia. Solo las secciones
1 y 2 hay que rehacer al cambiar de modelo.

⏳ **No correr esto hasta que el pipeline esté estable.** Cada modelo son ~2,5 GB
de descarga y un rato de setup. Arrancarlo antes deja tres modelos bajados y
nada funcionando. Es la última media hora, no la primera.

Tres modelos, cada uno responde una pregunta distinta:

| Constante del SDK | Pregunta que responde |
|---|---|
| `QWEN3_600M_INST_Q4` | ¿alcanza con el más chico? |
| `QWEN3_1_7B_INST_Q4` | el candidato |
| `HEALTHCARE_1_7B_MEDICAL_Q4_K_M` | ¿el fine-tune de dominio degrada fuera de su dominio? |

> El tercero es el interesante: **mismo tamaño y misma familia que el candidato,
> distinta especialización**. Si degrada, es evidencia de que un fine-tune de
> dominio transfiere mal — y sobre un modelo del catálogo propio de QVAC. Si no
> degrada, es un hallazgo más raro todavía.
>
> ⚠️ No existe una constante `MedPsy` en el SDK. La familia médica se llama
> `HEALTHCARE_*`; verificado sobre `tetherto-qvac-sdk 0.17.1`.

**Diseño del experimento, para que sea barato:**

- **5 casos, no 20.** Con 5 se ve la diferencia si es grande; si es chica, 20 tampoco alcanzan.
- **Solo extracción.** Nada de pipeline completo: campos correctos contra ground truth.
- **Mismo prompt, misma semilla, `temp=0`.** Cambiar dos cosas a la vez no deja atribuir nada.

| Modelo | Campos correctos | JSON válido | Alucinaciones | seg/caso |
|---|---|---|---|---|
| `QWEN3_600M_INST_Q4` | — | — | — | — |
| `QWEN3_1_7B_INST_Q4` | — | — | — | — |
| `HEALTHCARE_1_7B_MEDICAL_Q4_K_M` | — | — | — | — |

```bash
QVAC_LLM_MODEL=<constante> .venv/Scripts/python -m riesgo.hito1 --bridge
```

⚠️ La familia Qwen3 razona por defecto y por eso usamos `reasoning_budget: 0`.
Si se prueba un modelo que **no** sea de razonamiento, ese parámetro no aplica y
las cifras de la sección 2 no son comparables directamente — anotarlo en la fila.

---

## 0. Lo que hay que decir primero

**El 20/20 en modo oracle no es un logro y no lo vamos a presentar como tal.**

`gen_dataset.py:410` produce el `ruteo_esperado` con `descubierto > 1_000_000` y el mismo orden de reglas que implementa el ruteador. Reproducirlo verifica que el código coincide con la especificación — no mide capacidad del sistema.

El número que sí depende de nosotros es **precisión sobre los casos FIRMES**, porque depende de la extracción y de la clasificación de confianza: dos cosas que el generador no regaló.

> Regla: antes de reportar una métrica, preguntarse si el generador ya sabía la respuesta.

---

## 1. Inferencia local — Hito 1

> Depende del modelo. Ver la comparativa de arriba.

```bash
.venv/Scripts/python -m riesgo.hito1 --bridge
```

| Paso | Qué verifica | Resultado |
|---|---|---|
| 1 | El modelo carga y responde | OK |
| 2 | `temp=0` llega al motor | 3 corridas, mismo `sha256` |
| 3 | `response_format` restringe el decoder | parsea sin limpiar nada |
| 4 | Extracción contra valores conocidos | **5/5 campos** |

**Paso 2 — determinismo, verificado byte a byte** (`riesgo/medir.py`):

```
corrida 1:  sha256=8192b6a9b1cf   194 chars
corrida 2:  sha256=8192b6a9b1cf   194 chars
corrida 3:  sha256=8192b6a9b1cf   194 chars
```

Tres extracciones completas, hash idéntico. No es una respuesta corta que
coincide por azar: son 194 caracteres de JSON estructurado.

Es la prueba de que `generationParams` viaja anidado y de que el campo se llama
`temp`, no `temperature`. Sin esto la inferencia corre con sampling por defecto
y **ninguna medición posterior es reproducible**.

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

> Depende del modelo y del hardware. Ver la comparativa de arriba.

Medida con `riesgo/medir.py`, descartando la primera llamada (cold start).

| Métrica | Valor |
|---|---|
| **Extracción de 6 campos, en caliente** | **9,3 s** |
| Rango sobre las corridas | 9,2 – 9,3 s |
| Throughput | 18,2 tok/s (CPU) |
| Primera llamada (en frío) | 9,5 s |
| Time to first token | 485 ms |
| **Proyección: 20 casos × 4 documentos** | **~12 min por iteración** |

La dispersión es de una décima: la latencia es predecible, no un promedio de
valores dispares. Sirve para presupuestar.

**Qué habilita este número.** A 9,3 s por llamada, un segundo pase de
verificación sobre los campos dudosos cuesta ~12 min más por iteración. Es
pagable una vez, no en cada vuelta de desarrollo. Iterar sobre 5 casos y correr
los 20 solo al final.

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

> Independiente del modelo: se mide sobre el ground truth, sin inferencia.

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

> Con extracción desde el ground truth. Cuando el extractor esté enchufado, esta sección pasa a depender del modelo.

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

Ningún camino del proyecto sale a la red. Verificado por grep sobre todo el
árbol de código:

```bash
grep -rn "claude|anthropic|genai|gemini" --include=*.py --include=*.txt      app/ toolkit/ scripts/ riesgo/ requirements.txt
#  (sin resultados)
```

| Módulo | Importa | Estado |
|---|---|---|
| `app/answer.py` | `qvac_brain.llamar_llm_sync` | local |
| `hybrid_rag/multihop.py` | `qvac_brain.llamar_llm_sync`, `embed` | local |
| `hybrid_rag/ingest.py` | `qvac_brain.embed`, `dim` | local |

Se eliminaron del repo: el módulo `claude_brain/` completo, el
`hybrid_rag/embeddings.py` que importaba `google.genai`, los alias
`llamar_claude*`, y las dependencias `anthropic` y `google-genai` de
`requirements.txt`.

## 7. Cómo reproducir todo

```bash
tar xzf dataset_riesgo.tar.gz
.venv/Scripts/python -m riesgo.calibrar          # sección 3
.venv/Scripts/python -m riesgo.evaluar           # sección 4
.venv/Scripts/python -m riesgo.hito1 --bridge    # secciones 1 y 2 (necesita el bridge)
```
