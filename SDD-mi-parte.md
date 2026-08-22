# SDD — Motor de análisis de riesgo (mi parte)

**Aleph Hackathon 2026 · Track QVAC**
Alcance: **todo menos ingesta y OCR**, que los hace mi compañero.

---

## 1. Qué me toca

```
                    ┌─────────────────────────┐
   [COMPAÑERO]      │        [YO]             │
                    │                         │
 leer_documento() ──┼─> extracción            │
   (pypdf + OCR)    │      ↓                  │
                    │   contradicciones       │
                    │      ↓                  │
                    │   cálculo               │
                    │      ↓                  │
                    │   redacción             │
                    │      ↓                  │
                    │   ruteo                 │
                    │      ↓                  │
                    │   CLI / informe         │
                    └─────────────────────────┘
```

**No me toca:** leer PDFs escaneados, OCR, el script de evaluación.

---

## 2. El contrato con mi compañero

Lo único que consumo de él:

```python
def leer_documento(path: str) -> tuple[str, bool]:
    """Devuelve (texto, fue_ocr)."""
```

**Mientras no exista, uso un stub** y sigo trabajando con documentos nativos:

```python
def leer_documento(path):
    return PdfReader(path).pages[0].extract_text(), False
```

Cuando él entregue la versión real, borro el stub. Cero cambios en mi código.

**Lo que le pido además del texto:** que cada bloque venga con `confianza` (el OCR de QVAC la devuelve por bloque). Sin eso no puedo distinguir "contradicción real" de "el OCR leyó mal".

---

## 3. Modelo

```python
from tetherto.qvac_sdk.models import QWEN3_1_7B_INST_Q4
```

**Uso una constante del SDK, no un GGUF suelto.** El SDK lo descarga solo con barra de progreso y no tengo que buscar la cuantización correcta ni pelear con rutas.

Constantes verificadas en las docs oficiales:

| Constante | Tamaño | Nota |
|---|---|---|
| `QWEN3_600M_INST_Q4` | ~0,5 GB | si 1.7B no entra |
| `QWEN3_1_7B_INST_Q4` | ~1,2 GB | **el elegido** |
| `LLAMA_3_2_1B_INST_Q4_0` | ~0,8 GB | alternativa |

Con 4 GB de techo, 1.7B deja aire de sobra para el OCR, los embeddings y el sistema.

Y juega a favor del segundo premio del track: *"small models, hard tasks"*.

**Si se le escapan campos:** primero simplificar el prompt y reducir campos por llamada. Subir de tamaño es el último recurso.

---

## 4. Extracción

### Un prompt por documento, no por campo

Todos los campos de un mismo documento salen en una sola llamada. Los campos con dependencias numéricas se extraen mejor juntos, y me ahorra 12 llamadas por caso.

**Si un campo falla la validación, ese campo solo se reintenta aparte.**

```python
CAMPOS_POR_DOC = {
    "contrato": ["capital_original", "capital_adeudado", "cuotas_contrato",
                 "titular", "matricula", "domicilio_titular"],
    "escritura": ["titular", "matricula", "garantia_valor",
                  "tasacion_fecha", "domicilio_titular"],
    "recibos": ["pagos"],           # tabla
    "correspondencia": ["aviso_previo", "fecha_aviso"],
}
```

⚠️ **La escritura tiene dos domicilios**: el del titular y el del inmueble. El que comparo contra el contrato es **el del titular**. Confundirlos = 20 falsos positivos.

### Formato del prompt

```python
prompt = f"""Extraé los siguientes datos del documento.
Respondé SOLO este JSON, sin backticks ni explicación:

{{"capital_adeudado": number|null,
  "cuotas_contrato": number|null,
  "titular": string|null,
  ...}}

Si un dato no está en el texto, poné null. No inventes valores.
No uses "no encontrado" ni "": usá null.

DOCUMENTO:
{texto}"""
```

Temperatura 0. Nada de chain-of-thought — en modelos de este tamaño descarrila más de lo que ayuda.

### Validación

```
salida → parsear JSON
  ├─ falla       → 1 reintento
  └─ ok          → validar con pydantic
                     ├─ falla   → reintentar ese campo solo
                     └─ ok      → grounding
```

### Grounding: de dónde sale la página

**No le pido la página al modelo — la inventa.** La derivo buscando el valor extraído en el texto:

```python
from rapidfuzz import fuzz

def grounding(valor, texto_por_pagina, umbral=90):
    """Devuelve (pagina, encontrado). None si no aparece en ningún lado."""
    if valor is None:
        return None, True          # null válido, no penalizar
    for pag, txt in enumerate(texto_por_pagina, 1):
        if fuzz.partial_ratio(str(valor), txt) >= umbral:
            return pag, True
    return None, False             # ← posible alucinación
```

Si `encontrado == False`, el campo va con flag de revisión. **Esta es mi señal de confianza principal**, y es más barata y más confiable que cualquier otra.

### Normalización

En Python, no en el prompt. Los montos vienen en tres formatos a propósito:

```
$ 2.400.000,00      ARS 2.400.000      $ 2,40 millones
```

Extraigo el string tal cual y lo normalizo con regex. Fechas con `dateutil`.

---

## 5. Contradicciones

Comparo campos ya extraídos. **No le pregunto al modelo "buscá inconsistencias"** — es demasiado abierto para un modelo chico y genera falsos positivos.

### Comparación de nombres

⚠️ **Jaro-Winkler solo NO alcanza.** Pesa el prefijo, así que `"Perez, Juan"` contra `"Juan Perez"` da bajísimo aunque sean la misma persona.

Combinado con `token_sort_ratio` (que ordena las palabras antes de comparar), las falsas alarmas caen a la mitad.

> **Medido** (`riesgo/calibrar.py`, 200 pares de misma persona escrita distinto): JW solo → 125 falsas alarmas; JW+TSR → 65. La mejora es real y la dirección es la del párrafo de arriba.
>
> **Pero en ESTE dataset el problema no existe.** `gen_dataset.py` escribe siempre `"Nombre Apellido"`, nunca invertido ni abreviado — verificado extrayendo el texto de los PDFs. Contra el ground truth real, cualquier umbral entre 0.80 y 0.95 da **8/8 contradicciones detectadas, 0 falsos positivos**. La combinación con TSR se mantiene como seguro barato para documentos reales, no porque haga falta acá.

```python
from jellyfish import jaro_winkler_similarity
from rapidfuzz import fuzz
import unicodedata

def norm(s):
    s = unicodedata.normalize("NFKD", s.lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))

def similitud_nombres(a, b):
    na, nb = norm(a), norm(b)
    return max(jaro_winkler_similarity(na, nb),
               fuzz.token_sort_ratio(na, nb) / 100)
```

**Umbral: 0.85.** Calibrado contra el ground truth: detecta 208 de 210 pares distintos con la menor cantidad de falsas alarmas. Entre 0.82 y 0.95 el resultado es casi igual; lo que importa es no estar en los extremos.

### Comparación de números

⚠️ **El fuzzy NO sirve para números** — pero por el motivo contrario al que parece.

> **Medido** (`riesgo/calibrar.py`, 40 montos reales del ground truth en 3 formatos):
>
> | | dígitos | fuzzy ≥ 90 |
> |---|---|---|
> | valores reales encontrados | **120/120** | **40/120** |
> | alucinaciones tragadas | 0/40 | 0/40 |
>
> El fuzzy no traga alucinaciones: **se pierde dos de cada tres valores legítimos**. `partial_ratio("2400000", "$ 2.400.000,00")` no matchea porque los puntos separadores rompen la subsecuencia. Y `2.800.000` vs `2.830.000` da 86%, no 97%.

```python
def digitos(s):
    return "".join(c for c in str(s) if c.isdigit())

def grounding_numero(valor, texto):
    """Tolera formato distinto, no tolera un dígito distinto."""
    d = digitos(valor)
    return bool(d) and d in digitos(texto)
```

`$ 2.400.000,00` y `ARS 2400000` matchean porque comparten la secuencia de dígitos; un dígito cambiado no.

**Regla: números → dígitos exactos. Texto → fuzzy.**

### Los chequeos

| Chequeo | Regla | Gravedad |
|---|---|---|
| `titular_garantia` | `similitud_nombres(...) < 0.85` | **GRAVE** |
| `matricula_distinta` | matrículas no coinciden | **GRAVE** |
| `cuotas_no_coinciden` | `cuotas_contrato != len(pagos)` | media |
| `tasacion_vencida` | `año(tasacion) < año_actual - 5` | media |
| `domicilio_distinto` | domicilios del **titular** no coinciden | baja |

Cada contradicción se reporta con documento y página de **ambos lados**, para que un humano la verifique en cinco segundos.

⚠️ **La escritura tiene dos domicilios**: el del titular y el del inmueble. El que comparo contra el contrato es **el del titular**. Confundirlos = 20 falsos positivos.

---

## 5b. Clasificación y honestidad del sistema

El track premia explícitamente que el sistema declare sus límites: *"un agente que marca su incertidumbre le gana a uno que alucina un número con confianza"*.

**Decisión de diseño: nada frena el ruteo.** El sistema siempre produce un veredicto. Lo que varía es cuánta confianza declara tener.

### Dos ejes independientes

**Por hallazgo — ¿hay contradicción?**

```
CONFIRMADA    ambos valores con grounding sólido, y difieren
PROBABLE      difieren, pero al menos uno tiene señal débil
DESCARTADA    no difieren
```

**Por caso — ¿cuánto vale este veredicto?**

```
FIRME           ningún dato que influyó en la decisión tiene reservas
CON RESERVAS    ruteó igual, pero con N advertencias anotadas
```

### Qué degrada un caso a CON RESERVAS

Solo si el campo afectado **influyó en la decisión de ruteo**:

| Señal | Degrada | Motivo |
|---|---|---|
| Grounding fallado | **sí** | el valor no existe en el documento: el modelo lo inventó |
| Confianza de OCR baja | **sí** | el número puede estar mal leído |
| Dos documentos con el mismo dato distinto | **sí** | no hay forma de saber cuál es el bueno |
| Campo `null` | no | es honesto, no sospechoso — solo se anota |
| Similitud en zona gris (0.80–0.85) | no | se anota como PROBABLE |

### Todas las señales se anotan, siempre

Como nada frena, anotar no cuesta nada. Cada caso arrastra su lista completa de advertencias, aunque salga FIRME. El analista ve el veredicto y, al lado, todo lo que el sistema no pudo garantizar.

### Por qué esto hace medible la métrica principal

La precisión se calcula **solo sobre los FIRMES**.

**Medido** (`riesgo/evaluar.py`, modo `sin-ocr`: las 6 escrituras escaneadas no producen texto):

```
De 20 casos:
  14 FIRMES         → 14/14 correctos    precisión 100%
   6 CON RESERVAS   →  2/6  correctos

Cobertura: 70% resuelto con confianza plena.
Contradicciones GRAVES: 6/11 (las otras 5 están en escrituras ilegibles)
```

Los 4 casos mal ruteados salieron **los 4 marcados CON RESERVAS**. Cero errores silenciosos: el sistema nunca se equivocó sin avisar.

⚠️ **Documento vacío no es documento limpio.** Sin OCR, la escritura extrae 0 caracteres, todos sus campos salen `null`, no se detecta ninguna contradicción y el caso rutea a COBRANZAS con cara de limpio. Por eso un `null` causado por un documento ilegible **sí degrada** el caso, a diferencia de un `null` normal. Es el peor error posible de este sistema y es el que 5b existe para atrapar.

Es más fuerte que "18 de 20", porque separa lo que el sistema **sabe** de lo que **cree**.

Frase para el video: *"resuelve solo el 70% de los casos y en ese 70% no se equivoca nunca; el 30% restante lo rutea igual, pero declara exactamente por qué no está seguro"*.

### Orden de las métricas

1. **Precisión sobre los FIRMES** — el número protagonista
2. **Cobertura** — qué porcentaje sale FIRME
3. **Contradicciones graves detectadas** — ninguna se escapa
4. **Ruido** — cuántos CON RESERVAS eran en realidad casos limpios

## 6. Cálculo

Python puro. Los modelos chicos son malos en aritmética.

```python
descubierto = max(0, capital_adeudado - garantia_valor)
cobertura   = garantia_valor / capital_adeudado
puntualidad = pagos_a_tiempo / len(pagos)    # tolerancia 5 días
```

**Si `garantia_valor` es `null`, no calculo descubierto.** El caso sale a revisión humana. No asumo cero.

---

## 7. Ruteo

**El modelo no decide esto.** Orden de evaluación, y el orden importa:

```python
if contradiccion_grave:                     → LEGALES
elif descubierto > 1_000_000:               → LEGALES
elif puntualidad < 0.5:                     → LEGALES
elif cobertura >= 0.6 and aviso_previo:     → REFINANCIACION
else:                                       → COBRANZAS
```

La contradicción grave va **primero**, antes de mirar montos: una garantía con defecto formal no sirve por más que cubra el 200% de la deuda.

**Nada frena el ruteo.** Si un campo crítico quedó en `null` o con reservas, el caso rutea igual con la información disponible y sale marcado **CON RESERVAS** (ver 5b). El analista siempre recibe un veredicto más el detalle de qué no se pudo garantizar.

---

## 8. Redacción

Único lugar donde el modelo escribe libre. **Recibe hechos ya validados, no documentos:**

```python
prompt = f"""Redactá una nota interna de 3 a 5 líneas para un analista
de riesgo crediticio. Usá ÚNICAMENTE estos hechos.
No agregues información, estimaciones ni recomendaciones.

{json.dumps(hechos, indent=2)}"""
```

Pasar hechos y no texto crudo acota la superficie de alucinación.

---

## 9. CLI

```bash
$ riesgo analizar --cliente 4471
```

Sin interfaz web. Los requisitos de entrega no la piden y `rich` se ve bien en video.

```
CLIENTE 4471 — Juan Perez
Disparo: 32 dias de atraso

EXPOSICION
  Capital adeudado    $2.800.000   [contrato p.3]    ✓ alta
  Garantia: terreno   $2.000.000   [escritura p.1]   ⚠ media (ocr)
  Descubierto           $800.000

HISTORIAL
  11 de 12 pagos puntuales          [recibos]
  Aviso previo (12/09)              [correspondencia]

⚠ CONTRADICCION — GRAVE
  Escritura a nombre de "M. Perez"   [escritura p.1]
  Titular del prestamo: "Juan Perez" [contrato p.1]
  → Garantia posiblemente no ejecutable.

NOTA INTERNA
  [texto redactado]

RUTEO → LEGALES
  (defecto formal en la garantia)

⚠ REVISAR: tasacion con fecha 2019.
```

Flag `--json` para que el script de evaluación de mi compañero consuma la salida.

---

## 10. Orden de trabajo

| # | Tarea | Hito |
|---|---|---|
| 1 | Qwen2.5-3B cargado, una inferencia andando | **bloqueante** |
| 2 | Stub de `leer_documento` + leer `contrato.pdf` | |
| 3 | Extracción del contrato (6 campos) con validación | primer JSON válido |
| 4 | Grounding con rapidfuzz | primera página citada |
| 5 | Extracción de escritura, recibos, correspondencia | 12 campos |
| 6 | Contradicciones | |
| 7 | Cálculo + ruteo | primer caso completo |
| 8 | Redacción de nota | |
| 9 | CLI con `rich` + `--json` | |
| 10 | Enchufar el `leer_documento` real del compañero | escaneados entran |

**Corte:** si a las 8 horas la extracción no está estable, bajo de 12 campos a 5 y los hago perfectos. Un pipeline con 5 campos al 90% y un número en pantalla le gana a uno con 12 que no puedo medir.

---

## 11. Anexo — API real de QVAC

Todo esto está verificado contra `docs.qvac.tether.io`. **No inventar métodos**: el jurado descarta sin revisar los proyectos con métodos alucinados del SDK.

### Antes de escribir una línea

```bash
curl -o qvac-docs.txt https://docs.qvac.tether.io/llms-full.txt
```

Es la documentación entera exportada en texto plano, publicada por Tether específicamente para herramientas de IA. **Va como contexto en Claude Code.** Es la contramedida directa al "AI slop" que descalifica.

### Instalación

```bash
pip install tetherto-qvac-sdk \
  -f https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.17.0
```

⚠️ Sin el `-f` no anda. No es un `pip install` normal.

### El SDK es asyncio-nativo

Trae una fachada síncrona para notebooks, pero el código va async desde el arranque. Migrar después es reescribir.

### Flujo canónico

```
load_model()  →  completion()  →  unload_model()
```

```python
from tetherto.qvac_sdk import Client, load_model, unload_model
from tetherto.qvac_sdk.models import QWEN3_1_7B_INST_Q4

async with Client() as client:
    t = client.transport
    model_id = await load_model(
        t,
        model_src=QWEN3_1_7B_INST_Q4,
        model_config={"ctx_size": 4096},
        on_progress=print_progress,
    )
    # ... completion ...
    await unload_model(t, model_id)
```

### completion()

Recibe `history`, una lista de `{role, content}` con `role` en `"user"` | `"assistant"` | `"system"`.

Devuelve un run con dos superficies:

- **`events`** — async iterable de eventos tipados: `contentDelta`, `thinkingDelta`, `toolCall`, `toolError`, `completionStats`, `completionDone`, `rawDelta`
- **`final`** — promise que resuelve al terminar, con `contentText`, `thinkingText`, `toolCalls`, `stats`, `stopReason`, `raw.fullText`

Para extracción me alcanza con `final.content_text`. No necesito streaming.

`final.stats.tokensPerSecond` me da la latencia para el README, que es requisito de entrega.

### modelConfig — parámetros vistos en las docs

```
ctx_size    tamaño de contexto (4096 en los ejemplos)
device      "cpu" | "gpu"
verbosity   VERBOSITY.ERROR para silenciar
tools       true si voy a usar tool calling (no es mi caso)
```

### ⚠️ Temperatura — a verificar

**No encontré el parámetro de temperatura en la página de text generation.** Los ejemplos oficiales solo muestran `ctx_size`, `device`, `verbosity` y `tools`.

**No lo asumo.** Antes de escribirlo:
1. Buscar `temperature` en el `llms-full.txt` descargado
2. Si no aparece, revisar la referencia de API
3. Si sigue sin aparecer, preguntar en el Telegram tagueando a Raquel

Por qué importa: con temperatura por defecto (suele ser 0.7) el mismo contrato me puede devolver `2.800.000` una vez y `2.880.000` la siguiente. Para extracción necesito determinismo.

**Plan B si el SDK no expone temperatura:** usar el servidor HTTP OpenAI-compatible, que sí acepta `temperature` como parámetro estándar.

### Servidor HTTP como alternativa

QVAC expone un servidor compatible con la API REST de OpenAI en `http://localhost:11434/v1/`. El track dice explícito que usarlo **cuenta** como inferencia local.

⚠️ Es el mismo puerto que Ollama. Si tengo Ollama corriendo, hay conflicto.

Ventaja: puedo usar el cliente de OpenAI de siempre y tengo `temperature`, `response_format` y todo lo estándar sin aprender la API del SDK.

Desventaja: la integración se ve menos "profunda" y el jurado mira primero los permalinks a donde ocurre la inferencia.

**Decisión: arranco con el SDK. Si la temperatura o el JSON estructurado se complican, migro al servidor HTTP.**

### Ejemplos oficiales

`github.com/tetherto/qvac-examples` — mirar antes de escribir.

---

## 12. Reglas que no negocio

1. **El modelo extrae y redacta. El código decide.**
2. **Nunca inventa un número.** `null` + flag antes que un valor plausible.
3. **Cada dato lleva su fuente**, derivada del grounding y no del modelo.
4. **Nombres se comparan con fuzzy**, nunca con `==`.
5. **Nada de código generado que no haya corrido.** El jurado descarta sin revisar los métodos alucinados del SDK y los README que prometen lo que no existe.

---

## 13. Umbrales pendientes

**Confianza de OCR: sin fijar.** Depende de qué valores devuelva el OCR de QVAC en la práctica. Cuando esté andando, mirar la distribución sobre los 6 escaneados y sacar el corte de ahí.

**Corte de descubierto: a definir.** Barrido real (`riesgo/evaluar.py`):

| Corte | Aciertos de ruteo | Manda a LEGALES |
|---|---|---|
| $500.000 | 16/20 | 16/20 |
| $750.000 | 19/20 | 13/20 |
| **$1.000.000** | **20/20** | 12/20 |
| $2.000.000 | 19/20 | 11/20 |

⚠️ **Este barrido es circular y no sirve para elegir el corte.** `gen_dataset.py:410` usa
`descubierto > 1_000_000` para producir el `ruteo_esperado`. Que $1.000.000 dé 20/20 no dice
nada sobre la política: dice que mi implementación reproduce la regla del generador.

Lo mismo vale para el **20/20 del modo oracle**: es una verificación de que el código coincide
con la spec, no evidencia de que el ruteo sea bueno. Presentarlo como accuracy del sistema es
insostenible ante cualquiera que abra el generador.

El número defendible es el de la sección 5b: **precisión sobre los FIRMES**, que sí mide algo
que el generador no regaló.
