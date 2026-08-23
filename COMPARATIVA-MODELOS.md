# Comparativa de modelos

**Estado: dev completo, holdout no medido.** Se cortó por tiempo. Los cuatro
números de dev están cerrados y verificados; el holdout (seed 99) queda como
trabajo pendiente y no se estima acá. Lo que sigue no afirma nada sobre
generalización — afirma cosas sobre el set de desarrollo, que es donde se midió.

Pipeline congelado en `v1.7-motor`. **Ni un archivo de `riesgo/` cambió.**

---

## Qué se midió

Cuatro corridas sobre el dev set (seed 1, 20 casos, 6 escrituras escaneadas),
extracción real desde los PDFs — no modo `oracle`.

| texto | OCR | precisión FIRMES | cobertura | **errores silenciosos** | exactitud global |
|---|---|---|---|---|---|
| **QWEN3_1_7B_INST_Q4** (elegido) | OCR_LATIN | **15/15 = 100%** | **75%** | **0** | 17/20 = 85% |
| QWEN3_600M_INST_Q4 | OCR_LATIN | 7/7 = 100% | 35% | 0 | 15/20 = 75% |
| LLAMA_3_2_1B_INST_Q4_0 | OCR_LATIN | 14/15 = 93% | 75% | **1** | 16/20 = 80% |
| QWEN3_1_7B_INST_Q4 | OCR_DOCTR | 15/15 = 100% | 75% | 0 | 17/20 = 85% |

### Latencia

Dos definiciones, y conviene no mezclarlas. La carga del modelo son ~2,4 min por
proceso y se paga **una vez**, no por caso:

| texto | por inferencia | nativos (14) | escaneados (6) | amortizando la carga |
|---|---|---|---|---|
| QWEN3_1_7B_INST_Q4 | **26,9 s** | 26,5 s | 27,7 s | 34,1 s |
| QWEN3_600M_INST_Q4 | **16,6 s** | 16,0 s | 18,2 s | 23,6 s |
| LLAMA_3_2_1B_INST_Q4_0 | **19,7 s** | 19,9 s | 19,3 s | 26,5 s |

La diferencia entre las dos últimas columnas es constante (~7 s/caso × 20 casos
≈ 2,4 min): es la carga del modelo repartida. **La cifra que corresponde citar
es la de inferencia** — en producción el proceso queda levantado.

⚠️ **La latencia de DOCTR quedó parcial.** La máquina se suspendió en medio de
la corrida y `time.perf_counter()` sigue contando durante el suspend en Windows,
así que el hueco entero cayó dentro de un caso (11.832 s contra 25-28 s de sus
vecinos). De los 4 casos que el suspend no tocó sale ~26,5 s, comparable al
baseline. **La exactitud de esa corrida no está afectada** — ver la nota de
método más abajo.

Máquina: AMD Zen3, 16 hilos, sin GPU. Windows 11, Python 3.14, Node 22.22,
SDK 0.17.1. `temp=0`, `seed=7`, `ctx_size=4096` en las cuatro.

### Señales de extracción

| texto | OCR | campos nulos | sin grounding | graves detectadas | alertas de lectura |
|---|---|---|---|---|---|
| QWEN3_1_7B_INST_Q4 | OCR_LATIN | 5 | 5 | 11 | 1 |
| QWEN3_600M_INST_Q4 | OCR_LATIN | 14 | 17 | 11 | 8 |
| LLAMA_3_2_1B_INST_Q4_0 | OCR_LATIN | 5 | 9 | 12 | 1 |
| QWEN3_1_7B_INST_Q4 | OCR_DOCTR | 6 | 5 | 11 | 1 |

---

## Las tres respuestas

### ¿Alcanza con menos? — No, pero falla del lado correcto

El 600M corre a **62% del tiempo** del 1.7B y entrega **menos de la mitad de la
cobertura**: 7 casos resueltos contra 15. El canje es 10 s por caso a cambio de
ocho carpetas que pasan a revisión humana. Ningún analista lo toma.

Lo que **no** pierde es la honestidad. **Cero errores silenciosos**, y precisión
7/7 sobre lo que sí declara.

Los campos que el 600M degrada respecto del 1.7B, sobre los mismos documentos:

| | casos |
|---|---|
| `capital_adeudado` **inventado** (falla grounding) | **6** |
| `capital_adeudado` nulo | 3 |
| `cuotas_contrato` nulo | 9 |

Los seis `capital_adeudado` alucinados son el hallazgo: es el número del que
cuelga todo el cálculo del descubierto, y el 600M lo inventa en 6 de 20
carpetas. **El grounding los atrapó a todos** — de ahí que la precisión siga en
7/7. El modelo chico no es peligroso, es inútil: se declara incompetente en dos
tercios de la cartera en vez de equivocarse.

Eso vale como resultado independiente: **la maquinaria de confianza es
independiente del modelo.** El README afirmaba "sabe qué sabe" con un solo
modelo medido; ahora está medido con tres.

> **Reconciliación con `METRICAS-corridas.md` §5.** Una corrida previa de 5
> casos sobre `contrato.pdf` reportó **0% de alucinación** para el 600M. No es
> una contradicción: con 5 casos el modo no aparecía. Estos 20 casos sobre el
> pipeline completo lo destapan. La corrida de 20 es la que manda.

### ¿Importa la familia? — Sí, y es la variante más engañosa de las tres

Llama cambia una sola cosa (la familia; 0,8 GB contra 1,2 GB) y a primera vista
mejora: **misma cobertura que el 1.7B, 27% más rápido.** Un benchmark que
reportara solo exactitud global — 16/20 contra 17/20 — lo llamaría "un punto
peor y más barato", que es una recomendación de compra.

Lo que pierde es la única propiedad que el proyecto vende: **contesta 15 casos
con confianza y en uno está equivocado.** Es el único error silencioso medido en
la historia del proyecto.

Esta es la fila que descarta a Llama, y es la única de las cinco que lo hace.
**Es exactamente para lo que existe la métrica de "precisión sobre FIRMES".**

**Con la salvedad honesta:** el fallo no es de Llama sola, es de la interacción
entre Llama y una rama del pipeline (ver *Límite conocido*, abajo). Con esa rama
corregida, Llama daría 14/14 con 70% de cobertura y sería defendible. El
veredicto correcto es **"no elegir Llama sobre este código"**, que es una
afirmación más chica y más cierta que "Llama es peor".

### ¿Otro pipeline de OCR lee mejor? — Empate, en dev

**Ruteo idéntico en las 6 escaneadas**: misma ruta, misma confianza, mismos
aciertos (3/6, 1/1 en FIRMES). No hay razón medida para cambiar de OCR ni para
no hacerlo.

Los crudos **sí** difieren, y en direcciones distintas según la página: DOCTR a
veces conserva separadores que LATIN pierde (`471.000` contra `471000`) y a
veces se come espacios y puntuación. Ninguna de esas diferencias movió un
veredicto en dev.

El caso `cliente_4498` — el truncamiento documentado en `METRICAS-corridas.md` —
es el más interesante:

| | crudo | valor | qué lo salvó |
|---|---|---|---|
| LATIN | `ARS 457` | `457` | Detector B (magnitud) |
| DOCTR | `ARS 457. 0` | `None` | no parsea |

Dos lecturas erróneas distintas convergen al mismo veredicto correcto
(`COBRANZAS · CON RESERVAS · ok`) por dos caminos distintos. Es un punto a favor
de la arquitectura de confianza, no del OCR.

**Esta es la pregunta que más pierde por no tener el holdout**: dev tiene 6
escaneadas y el holdout 12, con otra semilla de ruido de escaneo. Un empate en 6
casos no decide nada.

---

## Dónde difieren, caso por caso

### 600M vs baseline — 10 casos distintos

| caso | esperado | baseline (1.7B) | 600M |
|---|---|---|---|
| `cliente_4407` | COBRANZAS | COBRANZAS · FIRME ok | COBRANZAS · CON RESERVAS ok |
| `cliente_4421` | LEGALES | LEGALES · CON RESERVAS ok | COBRANZAS · CON RESERVAS **MAL** |
| `cliente_4435` | COBRANZAS | COBRANZAS · FIRME ok | COBRANZAS · CON RESERVAS ok |
| `cliente_4442` | LEGALES | LEGALES · FIRME ok | LEGALES · CON RESERVAS ok |
| `cliente_4463` | LEGALES | LEGALES · FIRME ok | COBRANZAS · CON RESERVAS **MAL** |
| `cliente_4477` | LEGALES | LEGALES · FIRME ok | LEGALES · CON RESERVAS ok |
| `cliente_4484` | LEGALES | LEGALES · FIRME ok | LEGALES · CON RESERVAS ok |
| `cliente_4491` | REFINANCIACION | REFINANCIACION · FIRME ok | LEGALES · CON RESERVAS **MAL** |
| `cliente_4519` | LEGALES | COBRANZAS · CON RESERVAS **MAL** | LEGALES · CON RESERVAS ok |
| `cliente_4533` | LEGALES | LEGALES · FIRME ok | LEGALES · CON RESERVAS ok |

El patrón: casi todo lo que el 600M cambia es **FIRME → CON RESERVAS**. Baja la
cobertura, no la seguridad.

### Llama vs baseline — 1 caso distinto

| caso | esperado | baseline (1.7B) | Llama |
|---|---|---|---|
| `cliente_4414` | REFINANCIACION | REFINANCIACION · FIRME ok | COBRANZAS · **FIRME MAL** |

Un solo caso, y es el único error silencioso del proyecto. Ver abajo.

---

## Método — por qué esto no tocó el pipeline

La variable de modelo ya era inyectable sin editar nada:

- **Texto.** `evaluar_real` hace `from .llm import Motor` *dentro* de la función,
  así que el nombre se resuelve en cada llamada. Se reemplaza el atributo
  `riesgo.llm.Motor` por una fábrica que fija `modelo=X` y delega en la clase
  real. **La corrida es literalmente `riesgo.evaluar.evaluar_real`** — el mismo
  código que produjo los números publicados.
- **OCR.** `riesgo.ocr._init` lee el global `OCR_LATIN` del módulo; se reasigna.
  `_OCR_CONFIG` queda intacta, y DOCTR la acepta — si hubiera necesitado otra
  config, eso sí habría sido tocar el pipeline.

Un proceso por variante (tanto `Motor` como el singleton `riesgo.ocr._motor`
cargan el modelo una vez por proceso) y corridas estrictamente secuenciales.

Archivos nuevos, ninguno dentro de `riesgo/`: `bench_modelos.py` (una corrida),
`bench_todo.sh` (las ocho, con lock), `comparar.py` (fusiona y tabula).

### El baseline se re-midió acá, y reprodujo exacto

Los números de `METRICAS-corridas.md` salieron de un Intel Core Ultra 5 125U con
Python 3.12. Esta máquina es otra. El baseline re-medido dio **15/15, cobertura
75%, exactitud 85%, 0 errores silenciosos** — los cuatro idénticos.

Eso es lo que hace válida la comparación: cualquier diferencia en las otras tres
variantes es del modelo, no del entorno.

### La exactitud reproduce, la latencia no

Durante las corridas pasaron dos accidentes, y los dos dejaron la misma lección.
Primero dos cadenas quedaron corriendo en paralelo peleándose la CPU; después la
máquina se suspendió en medio de una corrida.

Se re-corrieron las cuatro y **los `.casos.json` salieron idénticos byte a byte**
a los de las corridas contaminadas. Las cuatro veces.

> **En este pipeline la exactitud es reproducible byte a byte y la latencia no
> sobrevive ni a contención ni a suspend.** Quien reproduzca esto puede confiar
> en sus números de acierto sin cuidar la carga de la máquina, y no puede
> confiar en un solo segundo sin aislarla.

De ahí el lock por `mkdir` atómico en `bench_todo.sh`.

---

## Lo que falta

- **Holdout (seed 99), las cuatro variantes.** Es lo único que decide la
  pregunta de OCR y lo único que habla de generalización. El set ya está
  generado y reproducido (`gen_dataset.py --seed 99`, 12/20 escaneadas, coincide
  con lo documentado). Comando listo: `bash bench_todo.sh`.
- **Latencia limpia de DOCTR sobre las 6 de dev.** ~3 min de cómputo.

---

# Límite conocido — el nulo limpio esquiva la maquinaria de confianza

**Lo encontró la comparativa de modelos, no el dataset.** Veinte casos de dev
con el 1.7B nunca lo destaparon. Apareció en la primera corrida con otro modelo
de texto.

Se anota, no se arregla: el pipeline está congelado y los números publicados
salen de ese estado. Es la línea que el README ya dibuja — *"Un fallo nuevo
sobre datos frescos se anota como límite conocido; no se arregla mirándolo."*

## El caso

`cliente_4414`, con `LLAMA_3_2_1B_INST_Q4_0`. Escritura **nativa**: el OCR no
participa, así que no hay ruido de lectura en el medio.

Llama devolvió `null` en los cinco campos de `contrato.pdf` — `titular`,
`matricula`, `domicilio`, `capital_adeudado`, `cuotas_contrato`. Los cinco de
`escritura.pdf` salieron correctos. Falló una de las dos llamadas del caso, no
el modelo entero.

Resultado: `REFINANCIACION` esperado, `COBRANZAS` obtenido, **FIRME**.

## La cadena, en tres pasos

**1. El derivado se anula.** Sin `capital_adeudado`, `calculo.py` deja
`descubierto = None` y `cobertura = None`.

**2. El ruteo cae al default.** En `ruteo.py:rutear()` las dos guardas que
podían mover el caso se saltean solas:

```python
if desc is not None and desc > corte:            # desc is None -> no entra
    return LEGALES, ...
if cob is not None and cob >= COBERTURA_REFINANCIABLE and aviso_previo:
    return REFINANCIACION, ...                    # cob is None -> no entra
return COBRANZAS, "no formal defects and shortfall within the threshold", ...
```

El caso sale con un motivo que **afirma** que el descubierto está bajo el
umbral. El descubierto nunca se calculó.

**3. La confianza no lo degrada.** En `motor.py:_advertencias()`, un campo nulo
cuyo documento sí se pudo leer entra por esta rama:

```python
avisos.append(Advertencia(nombre, "no data in the document", degrada=False))
```

`degrada=False` está fijo. La variable `pesa = nombre in influyen` se calcula
arriba y la respetan las otras dos ramas —la de `campo.reserva()` y la de
documento ilegible— pero esta la ignora. Y `capital_adeudado` está en
`INFLUYEN["descubierto"]`: influyó en la decisión.

## Por qué el 600M no lo destapó

El 600M también dejó `descubierto = None` en tres casos (`4407`, `4435`,
`4463`) y los tres salieron **CON RESERVAS**, correctamente degradados. La
diferencia está en el crudo:

| | `alerta_lectura` | rama de `_advertencias` | resultado |
|---|---|---|---|
| 600M (3 casos) | `thousands group with 2 digit(s), not 3` | `campo.reserva()` → `degrada=pesa` | CON RESERVAS ✓ |
| Llama (`4414`) | `None` | nulo limpio → `degrada=False` | **FIRME** ✗ |

El pipeline degrada bien un nulo **que vino de un valor roto** y deja pasar un
nulo **que vino de un modelo que no contestó**. El segundo es el más obvio de
los dos.

## Por qué el grounding no puede verlo

Los cinco campos nulos salieron con `grounding_ok=True`. Buscar un valor ausente
dentro del documento pasa por vacuidad: **no hay string que no aparezca**. La
señal de confianza principal del sistema es ciega a este modo por construcción,
igual que a la confusión de campo.

Y está invisible en los modos de evaluación baratos: en `oracle` los campos
salen del ground truth y nunca son nulos. Solo aparece extrayendo de los
documentos reales — el mismo argumento que justificó la corrida completa cuando
apareció el bug de `aviso_previo`.

## La familia a la que pertenece

Es el cuarto agujero del mismo tipo que documenta este proyecto, y el patrón se
repite entero:

| | esquiva | empuja hacia |
|---|---|---|
| confusión de campo | grounding (el valor está en el doc) | — |
| `aviso_previo` (corregido) | grounding (no pasaba por ahí) | REFINANCIACION |
| truncamiento OCR `4498` (corregido) | grounding (el texto ya venía roto) | LEGALES |
| **nulo limpio** | grounding (ausencia trivialmente válida) + advertencia | **COBRANZAS** |

Los tres corregidos y este comparten forma: **un dato que no pasa por la
maquinaria de confianza y desvía el caso a una ruta fija.** No falla al azar.

## Qué haría falta

Una línea — `degrada=pesa` en esa rama — o, mejor, que `rutear()` no caiga al
default cuando `desc is None`: un descubierto que no se pudo calcular no es un
descubierto bajo el umbral, y el motivo no debería afirmar lo contrario. Las dos
cosas cambian números publicados, así que quedan fuera de esta tarea.
