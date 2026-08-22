# Bitácora de pruebas

Todo lo que se verificó corriendo algo, en orden. Cada entrada dice **qué se
probó**, **con qué comando** y **qué dio** — para poder revisar después si una
conclusión sigue siendo válida, o rehacerla si cambia el modelo o el dataset.

Las que dicen **CIRCULAR** no miden lo que parecen medir. Están anotadas
igual, con la advertencia, porque el error es fácil de repetir.

Sesión: 2026-08-22 · Modelo `QWEN3_1_7B_INST_Q4` · CPU

---

## A. El SDK de QVAC — qué existe de verdad

Regla 12.5 del SDD: nada de código contra métodos que no se verificaron.
Un README que promete lo que el SDK no tiene se descarta sin revisar.

### A1 · El SDK de Python existe

```bash
pip index versions tetherto-qvac-sdk
pip download tetherto-qvac-sdk --no-deps \
  -f https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.17.0
```

**Resultado:** `0.17.1` y `0.17.0` disponibles. Descarga OK.

**Importa porque** `scripts/qvac/README.md` afirmaba que el bridge HTTP era
*"la única forma"* de usar QVAC desde Python. Es falso.

**Matiz descubierto después (A7):** el SDK de Python es un cliente delgado
sobre un worker Node que administra solo. El motor de inferencia sí es Node.

### A2 · Firma real de `completion()`

```bash
python -c "import tetherto.qvac_sdk as s, inspect; print(inspect.signature(s.completion))"
```

```python
completion(transport, *, model_id, history, tools=None, stream=True,
           generation_params: dict|None = None,
           response_format: dict|None = None, ...)
```

**Cierra** el `⚠️ Temperatura — a verificar` del SDD original. No hace falta
migrar al servidor HTTP ni preguntar en el Telegram.

### A3 · El parámetro se llama `temp`, no `temperature`

```bash
python -c "from tetherto.qvac_sdk._generated.models import _internal as I; \
print(list(I.BatchCompletionStreamRequestPromptsItemGenerationParams.model_fields))"
```

```
temp, top_p, top_k, predict, seed, frequency_penalty, presence_penalty,
repeat_penalty, reasoning_budget, remove_thinking_from_context
```

⚠️ **Una clave desconocida se descarta en silencio.** Si mandás `temperature`
no falla: corre con sampling por defecto y nada lo delata. Ver D1.

### A4 · `response_format` compila a gramática GBNF

`_generated/models/_internal.py:195`:

> *"JSON Schema the model output must validate against. Forwarded to the addon
> as-is and converted to GBNF natively by llama.cpp's `json_schema_to_grammar()`."*

**No es una sugerencia en el prompt: es una restricción del decoder.** El
modelo no puede emitir backticks, JSON truncado ni `"no encontrado"` donde el
schema declara `number | null`.

Forma exacta:

```python
{"type": "json_schema",
 "json_schema": {"name": str, "schema": {...}, "strict": bool}}
```

### A5 · Delegated inference existe en Python, las dos puntas

```bash
python -c "import tetherto.qvac_sdk as s, inspect; \
print(inspect.signature(s.load_model).parameters['delegate']); \
print(inspect.signature(s.provide))"
```

```python
# consumer
load_model(..., delegate={"providerPublicKey": str,   # requerido
                          "timeout": float,
                          "healthCheckTimeout": float,
                          "fallbackToLocal": bool,
                          "forceNewConnection": bool})
# provider
provide(transport, ProvideRequest(firewall={"mode": "allow"|"deny",
                                            "publicKeys": [...]}))
  -> ProvideResponse.public_key
```

**Cierra** el ítem 2 de la sección 8 del SDD-2, que quedaba pendiente de
verificar contra `llms-full.txt`. No hace falta JS.

⚠️ **Sin verificar:** la unidad de `timeout`. La anotación es `float` y el
ejemplo JS pasa `60_000`, lo que sugiere milisegundos, pero nada en el SDK lo
confirma.

### A6 · Constantes de modelos

```bash
python -c "import tetherto.qvac_sdk.models as m; print([n for n in dir(m) if n.isupper()])"
```

| Constante | Existe |
|---|---|
| `QWEN3_600M_INST_Q4` | sí |
| `QWEN3_1_7B_INST_Q4` | sí — **el que usamos** |
| `LLAMA_3_2_1B_INST_Q4_0` | sí |
| `QWEN3_4B_Q4_K_M` | sí |
| `EMBEDDINGGEMMA_300M_Q4_0` | sí |
| `MedPsy-1.7B` | **NO** |
| `HEALTHCARE_1_7B_MEDICAL_Q4_K_M` | sí — es la familia médica real |

También hay `OCR_LATIN`, `OCR_DOCTR`, `OCR_3B_MULTIMODAL_Q4_0` y la función
`ocr_stream`, para la parte del compañero.

### A7 · El SDK de Python necesita un worker Node local

```bash
python -m tetherto.qvac_sdk install-worker
```

```
WorkerNotFoundError: no worker found -- run `python -m tetherto.qvac_sdk
install-worker` to fetch @qvac/sdk@0.17.1 via npm
```

⚠️ **Bug del SDK en Windows:** busca `npm`, pero el ejecutable es `npm.cmd`, así
que el auto-install falla con *"npm was not found"* aunque npm esté instalado.

Instalación manual en la ruta que el SDK espera:

```bash
cd ~/.cache/qvac/worker/0.17.1
npm install @qvac/sdk@0.17.1
```

⚠️ **La primera instalación quedó incompleta** (`changed 2 packages`) y faltaba
`bare-runtime-win32-x64`. Un `rm -rf node_modules package-lock.json` seguido de
reinstalar trajo los 186 paquetes.

---

## B. El dataset — qué contiene realmente

### B1 · Distribución del ground truth

```bash
tar xzf dataset_riesgo.tar.gz
python -m riesgo.calibrar
```

| | |
|---|---|
| Casos | 20 |
| Ruteo esperado | 12 LEGALES · 6 COBRANZAS · 2 REFINANCIACION |
| Contradicciones | 8 `titular_garantia` · 3 `matricula_distinta` · 2 `tasacion_vencida` · 2 `domicilio_distinto` · 1 `cuotas_no_coinciden` |
| Casos sin contradicción | 9 |
| Escrituras escaneadas | 6 / 20 |
| Campos críticos en `null` | **0** |

**Consecuencia:** los caminos de manejo de `null` del SDD nunca se ejercitan
con este dataset. No invertir ahí.

### B2 · Los tres formatos de monto

`gen_dataset.py:fmt_ars` genera el mismo valor de tres formas:

```
$ 2.400.000,00      ARS 2.400.000      $ 2,40 millones
```

El tercero rompe cualquier parseo ingenuo.

### B3 · `capital_adeudado` sí está escrito

Al principio parecía derivado. Está en la cláusula SEXTA del contrato:

> *"Al 31/07/2026, el capital adeudado asciende a ARS 1.494.000."*

**Importa porque** si fuera derivado habría que calcularlo, no extraerlo.

### B4 · La trampa de los dos domicilios es real

`cliente_4400/contrato.pdf` tiene **dos** direcciones:

```
"con domicilio en Caseros 964, Rosario"     <- del titular
"sito en Balcarce 159, Rosario"             <- del inmueble
```

Confundirlas da un falso positivo de `domicilio_distinto` en cada caso.

### B5 · Las escrituras escaneadas extraen CERO caracteres

```bash
python -c "from pypdf import PdfReader; ..."
```

| Caso | Escaneada | Chars | Contradicciones que esconde |
|---|---|---|---|
| `cliente_4421` | sí | **0** | `matricula_distinta`, `titular_garantia` |
| `cliente_4470` | sí | **0** | `titular_garantia` |
| `cliente_4512` | sí | **0** | `titular_garantia` |
| `cliente_4519` | sí | **0** | `matricula_distinta` |
| `cliente_4435` | sí | 0 | — |
| `cliente_4498` | sí | 0 | — |

**4 de 20 casos (20%) pierden una contradicción GRAVE sin OCR**, y fallan **en
silencio**: la escritura extrae vacío, no se detecta nada y el caso rutea a
COBRANZAS con cara de limpio.

**Decisión de diseño que sale de acá:** un `null` causado por un documento
ilegible degrada el caso; un `null` normal no. Ver `Documento.ilegible`.

---

## C. Umbrales — calibración contra el ground truth

```bash
python -m riesgo.calibrar
```

### C1 · Números: dígitos exactos, nunca fuzzy

40 montos reales × 3 formatos:

| | dígitos | `partial_ratio ≥ 90` |
|---|---|---|
| Valores reales encontrados | **120/120** | **40/120** |
| Alucinaciones tragadas | 0/40 | 0/40 |

⚠️ **Corrige una hipótesis previa.** Se creía que el fuzzy tragaba
alucinaciones. No: **se pierde dos de cada tres valores legítimos** porque los
separadores de miles rompen la subsecuencia. Y `2.800.000` vs `2.830.000` da
**86%**, no 97%.

El daño es igual de grave por el otro lado: un grounding que no encuentra el
valor real marca el campo como inventado y degrada el caso por nada.

### C2 · Nombres: Jaro-Winkler + token_sort_ratio

200 pares de misma persona escrita distinto, 190 pares de personas distintas:

| Umbral 0.85 | solo JW | JW + TSR |
|---|---|---|
| Falsas alarmas | 125/200 | **65/200** |
| Detecta distintas | 190/190 | 190/190 |

Peores casos de misma persona, los que casi disparan:

```
'Vega, Natalia' vs 'N. Vega'    jw=0.566 -> mix=0.600
'Ruiz, Camila'  vs 'C. Ruiz'    jw=0.577 -> mix=0.632
```

### C3 · Pero en este dataset el problema no existe

```bash
python -c "from riesgo.documentos import leer_documento; ..."
```

`gen_dataset.py` escribe **siempre** `"Nombre Apellido"`, nunca invertido ni
abreviado — verificado extrayendo el texto de los PDFs, no leyendo el
generador. Contra el ground truth real:

| Umbral | Detecta | Falsos positivos |
|---|---|---|
| 0.80 → 0.95 | **8/8** | **0** |

`max(distinta) = 0.780`, `min(misma) = 1.000`. Hay un abismo de 0.22 entre las
dos clases.

**Conclusión:** el umbral 0.85 está bien, pero no porque esté finamente
calibrado — porque el problema es fácil con estos datos. La combinación con TSR
queda como seguro barato para documentos reales.

### C4 · Corte de descubierto — **CIRCULAR, no usar para elegir**

| Corte | Aciertos | A LEGALES |
|---|---|---|
| $500.000 | 16/20 | 16/20 |
| $750.000 | 19/20 | 13/20 |
| **$1.000.000** | **20/20** | 12/20 |
| $2.000.000 | 19/20 | 11/20 |

⚠️ `gen_dataset.py:410` usa `descubierto > 1_000_000` para producir el
`ruteo_esperado`. Que $1M dé 20/20 no dice nada sobre la política: dice que la
implementación reproduce la regla del generador.

**Es política, no optimización.** Elegirlo y defenderlo.

---

## D. Inferencia — Hito 1

### D1 · Determinismo, comparación byte a byte

```bash
python -m riesgo.medir --bridge --corridas 3
```

```
corrida 1:  sha256=8192b6a9b1cf   194 chars
corrida 2:  sha256=8192b6a9b1cf   194 chars
corrida 3:  sha256=8192b6a9b1cf   194 chars
```

**Tres extracciones completas de JSON, hash idéntico.** `temp=0` llega al motor.

⚠️ La evidencia anterior era tres copias de una respuesta de **2 caracteres**
(`'75'`), que podían coincidir por azar. Esta no.

**Si esto falla, ninguna medición posterior vale.** Correrlo primero al cambiar
de modelo o de transporte.

### D2 · JSON garantizado por gramática

```bash
python -m riesgo.hito1 --bridge
```

Salida cruda, sin post-procesar:

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

Parsea sin limpiar backticks ni recortar. **Cero reintentos de parseo en todo
el desarrollo.** 5/5 campos correctos.

### D3 · Apagar el razonamiento — la palanca más grande

Qwen3 emite un bloque `<think>` antes de responder. Misma pregunta:

| Configuración | Tokens generados | Texto devuelto |
|---|---|---|
| Por defecto | 58 | `Hola!` |
| `reasoning_budget: 0` | **9** | `Hola! ¿Cómo puedo ayudarte hoy?` |

**6,4× menos tokens para una respuesta mejor.**

⚠️ Con `predict` bajo el efecto es peor que lento. Primera prueba contra el
bridge, `max_tokens=32`:

```json
{"texto":"", "pensamiento":"Okay, the user said hola...", "stop_reason":"length"}
```

**`texto` vacío.** El modelo gastó el presupuesto entero pensando.

### D4 · Latencia

```bash
python -m riesgo.medir --bridge --corridas 3
```

| Métrica | Valor |
|---|---|
| **Extracción de 6 campos, en caliente** | **9,3 s** |
| Rango | 9,2 – 9,3 s |
| Throughput | 18,2 tok/s (CPU) |
| Primera llamada (en frío) | 9,5 s |
| Time to first token | 485 ms |

La dispersión es de una décima: la latencia es **predecible**, sirve para
presupuestar. Un segundo pase de verificación cuesta ~12 min más por iteración
completa: pagable una vez, no en cada vuelta.

### D5 · Infra

El server tiene **3,7 GB** de RAM, no los 8 GB que recomienda el README del
bridge. Con el 1.7B cargado quedan ~1,5 GB. Entra, pero no hay lugar para
subir a 4B ni para cargar el OCR en paralelo en la misma caja.

---

## E. Extracción

### E1 · Normalización de montos y fechas

```bash
python -c "from riesgo.normalizacion import normalizar_monto; ..."
```

**11/11**, incluidos los tres formatos del dataset y `$ 2,40 millones`.

Los montos se extraen como **string verbatim** y se convierten en Python. Pedirle
la conversión al modelo es pedirle aritmética, que es lo que peor hace: con
`$ 2,40 millones` devuelve `2.40` tan seguido como `2400000`, y las dos se ven
plausibles en el JSON.

### E2 · Recibos: parseo determinista, sin modelo

```bash
python -c "from riesgo.extraccion import parsear_recibos; ..."
```

**20/20 carpetas correctas** en cantidad de recibos y puntualidad.

La tabla tiene columnas fijas: regex es exacto, gratis e instantáneo. El modelo
se reserva para la prosa. 15 filas × 20 casos serían muchos tokens por un dato
que el regex saca sin error.

### E3 · Extracción con modelo, un caso

```bash
python -c "... extraer_carpeta(motor, docs) ..."   # cliente_4400
```

**10/10 campos correctos**, 37,1 s (dos llamadas: contrato + escritura).

```
titular_contrato     Juan Perez        ok p1
titular_escritura    Juan Perez        ok p1
matricula_contrato   11-59965          ok p1
matricula_escritura  11-59965          ok p1
capital_adeudado     1494000.0         ok p1
cuotas_contrato      32                ok p1
garantia_valor       374000.0          ok p1
pagos_emitidos       15                ok p1
puntualidad          0.933             ok p1
aviso_previo         True              ok
```

**La trampa de los dos domicilios (B4) fue evitada:**

```
domicilio_contrato:  'Caseros 964, Rosario'    <- del titular, correcto
domicilio_escritura: 'Caseros 964, Rosario'
```

No agarró `Balcarce 159` (el inmueble). La pista explícita en el prompt
funcionó.

---

## F. Métricas del sistema

```bash
python -m riesgo.evaluar
```

### F1 · Modo oracle — **CIRCULAR**

20/20, 11/11 contradicciones graves.

⚠️ Con extracción perfecta desde el ground truth y la misma regla de ruteo que
`gen_dataset.py:410`. **Verifica la implementación contra la spec, no mide el
sistema.** No presentarlo como accuracy.

### F2 · Sin OCR — el número que sí vale

Simula que las 6 escrituras escaneadas no producen texto:

```
14 FIRMES         → 14/14 correctos      precisión 100%
 6 CON RESERVAS   →  2/6  correctos

Cobertura: 70%
Contradicciones GRAVES: 6/11
```

**Los 4 casos mal ruteados salieron los 4 marcados CON RESERVAS.** Cero errores
silenciosos.

| Caso | Esperado | Obtenido | Confianza |
|---|---|---|---|
| `cliente_4421` | LEGALES | COBRANZAS | CON RESERVAS |
| `cliente_4470` | LEGALES | COBRANZAS | CON RESERVAS |
| `cliente_4512` | LEGALES | COBRANZAS | CON RESERVAS |
| `cliente_4519` | LEGALES | COBRANZAS | CON RESERVAS |

### F3 · Extracción real, 20 casos

```bash
python -m riesgo.evaluar --real --bridge
```

Salida completa en [`salida-real-20casos.txt`](salida-real-20casos.txt).

_(pendiente de completar con el resultado)_

---

## H. El hallazgo: el grounding verifica existencia, no corrección

La corrida real destapó `cliente_4407` ruteado mal **con confianza FIRME** —
un error que el sistema no declaró, que es justo lo que la sección 5b del SDD
promete que no pasa.

### H1 · La hipótesis: confusión de campo

Un grounding que solo busca el valor en el texto cubre un modo de fallo y no
el otro:

| Modo de fallo | Qué pasa | ¿Lo atrapa el grounding? |
|---|---|---|
| **Alucinación** | valor que no existe en el documento | **sí** |
| **Confusión de campo** | valor real, campo equivocado | **no** |

Si el modelo extrae `capital_original` cuando le pedimos `capital_adeudado`,
ese número **está** en el documento. Pasa el grounding con nota perfecta, y el
caso sale FIRME con un dato equivocado.

### H2 · Se probó, y no era eso

```bash
python -c "... extraer_documento(...) sobre 5 casos ..."
```

| Caso | Extraído | Adeudado (correcto) | Original (el otro) | |
|---|---|---|---|---|
| `cliente_4400` | 1 494 000 | 1 494 000 | 2 400 000 | ok |
| `cliente_4407` | 829 000 | 829 000 | 1 500 000 | ok |
| `cliente_4414` | 796 000 | 796 000 | 1 500 000 | ok |
| `cliente_4428` | 1 490 000 | 1 490 000 | 2 400 000 | ok |
| `cliente_4442` | 2 238 000 | 2 238 000 | 4 000 000 | ok |

**0/5 confusiones.** Los dos montos están en el mismo documento, a pocas líneas
uno del otro, y el modelo los distingue. Lo que lo sostiene es la pista
explícita del prompt:

```python
"capital_adeudado": "el saldo que se debe HOY, no el capital original"
```

### H3 · La causa real: un heurístico de presencia

El bug estaba en `aviso_previo`, y era peor: **ni siquiera pasaba por el
grounding.** Era un heurístico que dice "si existe `correspondencia.txt`,
hubo aviso previo".

El archivo **existe siempre**. Lo que cambia es quién escribió:

```
aviso_previo = True    De: juan.perez@mail.com    -> el deudor avisa
                       "Les escribo para informar que voy a demorarme"

aviso_previo = False   De: cobranzas@banco...     -> el banco intima
                       "Intimamos a regularizar bajo apercibimiento"
```

Las dos son correspondencia. Solo la primera es un aviso previo.

| | |
|---|---|
| Casos con `aviso_previo` incorrecto | 10 / 20 |
| **De esos, casos que cambian de ruta** | **7 / 20** |

**El sesgo es direccional, y ahí está lo grave.** Los 7 van a REFINANCIACION,
porque la regla es `cobertura >= 0.6 and aviso_previo` y la cobertura ya daba:

| Debía ir a | Fue a | Casos |
|---|---|---|
| LEGALES | REFINANCIACION | **4** |
| COBRANZAS | REFINANCIACION | 3 |

No es ruido simétrico: **el bug empuja siempre hacia el resultado más
benévolo.** Un banco con esto refinancia cuatro carpetas cuya garantía tiene
un defecto formal. El costo no se mide en puntos de accuracy.

### H4 · Por qué estaba invisible

Los modos `oracle` y `sin-ocr` toman `aviso_previo` del ground truth. **El bug
solo existe cuando el dato sale de los documentos**, así que ninguna métrica
anterior lo podía ver.

Es el argumento para correr la extracción real aunque cueste 12 minutos: los
modos baratos miden la lógica, no el sistema.

### H5 · El fix, y por qué generaliza

La mitigación correcta para el modo "valor real, campo errado" es **mirar el
contexto alrededor del valor, no solo su presencia**. Acá eso se traduce en
mirar la dirección del mensaje:

```python
remitente = norm(re.search(r"^De\s*:\s*(.+)$", texto, re.M).group(1))
partes = [p for p in norm(titular).split() if len(p) > 2]
return bool(partes) and all(p in remitente for p in partes)
```

El criterio es *¿salió del deudor?*, no *¿la dirección dice cobranzas?*, así
que no depende de las direcciones concretas de este dataset.

**20/20** después del fix, con y sin nombre del titular.

### H6 · Lo que queda abierto

La confusión de campo **no ocurre hoy**, pero el grounding sigue sin poder
verla. Si al cambiar de modelo apareciera, la mitigación ya está diseñada:
verificar que el match esté precedido del texto que corresponde
(`"el capital adeudado asciende a"` vs `"otorga un prestamo por la suma de"`).

No se implementó porque hoy no hay nada que arreglar, y código sin un fallo
que lo justifique es código sin probar.

---

## G. Pendientes de verificar

| Qué | Por qué importa |
|---|---|
| **Delegated inference end-to-end** | El código existe (A5) y **nunca se ejecutó**. Es la misma situación que tenía `llm.py` antes del Hito 1. |
| Unidad de `timeout` en `delegate` | Se asume ms por el ejemplo JS. Sin confirmar. |
| Confianza de OCR | Umbral sin fijar hasta ver la distribución real sobre los 6 escaneados. |
| Comparativa de 3 modelos | Diseñada en `METRICAS.md`. Tarea del final: cada modelo son ~2,5 GB. |
