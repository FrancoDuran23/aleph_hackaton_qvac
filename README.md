# riesgo — análisis de carpetas crediticias con IA local

**Aleph Hackathon 2026 · Track QVAC**

Una CLI que hace, en segundos, el trabajo que hoy le lleva una o dos horas a un
analista de riesgo cuando un cliente entra en mora: leer la carpeta completa
—contrato, escritura de la garantía, recibos, correspondencia—, calcular la
exposición, detectar contradicciones entre documentos, redactar una nota interna
y rutear el caso.

**Toda la inferencia corre local.** Ningún dato del cliente sale de la máquina.
Para una cartera crediticia eso no es una preferencia técnica: es la diferencia
entre poder usar la herramienta y no poder.

## Dónde ocurre la inferencia

Todo corre local con el SDK de QVAC. Enlaces directos a las líneas donde se llama
al SDK:

- **Generación de texto — `completion()`** → [`riesgo/llm.py#L242-L249`](https://github.com/FrancoDuran23/aleph_hackaton_qvac/blob/58d217e468e5ff832b85bd8c6646e72b40ea2ba9/riesgo/llm.py#L242-L249)
- **OCR — carga del modelo `OCR_LATIN`** → [`riesgo/ocr.py#L131-L133`](https://github.com/FrancoDuran23/aleph_hackaton_qvac/blob/58d217e468e5ff832b85bd8c6646e72b40ea2ba9/riesgo/ocr.py#L131-L133)
- **OCR — inferencia `ocr_stream()`** → [`riesgo/ocr.py#L145`](https://github.com/FrancoDuran23/aleph_hackaton_qvac/blob/58d217e468e5ff832b85bd8c6646e72b40ea2ba9/riesgo/ocr.py#L145)

Enlaces fijados al commit `58d217e` del tag **`v1.7-motor`**, para que el código
enlazado sea exactamente el que produjo los números del video (no a `main`, que
se mueve).

```
CLIENTE 4471 — Juan Perez
Disparo: 32 dias de atraso

EXPOSICION
  Capital adeudado    $2.800.000   [contrato p.3]    ✓ alta
  Garantia: terreno   $2.000.000   [escritura p.1]   ⚠ media (ocr)
  Descubierto           $800.000

⚠ CONTRADICCION — GRAVE
  Escritura a nombre de "M. Perez"   [escritura p.1]
  Titular del prestamo: "Juan Perez" [contrato p.1]
  → Garantia posiblemente no ejecutable.

RUTEO → LEGALES  (defecto formal en la garantia)
```

## La idea que sostiene el diseño

**El modelo extrae y redacta. El código decide.**

Un modelo chico es bueno copiando datos de un texto y malo en aritmética,
comparaciones y reglas de negocio. Así que el LLM solo hace lo primero: la
cuenta del descubierto, la detección de contradicciones y el ruteo son Python
determinista.

**Y nada frena el ruteo.** El sistema siempre produce un veredicto; lo que varía
es cuánta confianza declara. Un caso sale `FIRME` solo si ningún dato que
influyó en la decisión arrastra reservas. Si algo no se pudo garantizar —el
valor no aparece en el documento, el OCR leyó con poca confianza, un PDF no
produjo texto— el caso rutea igual pero sale `CON RESERVAS`, con el detalle de
qué falló.

Eso permite reportar la métrica que importa: **precisión sobre los casos
FIRMES**. Ver [`METRICAS.md`](METRICAS.md).

## Un hallazgo que vale más que el score

El grounding —buscar el valor extraído dentro del documento— es la señal de
confianza principal del sistema. Cubre un modo de fallo y **no** el otro:

| Modo de fallo | Ejemplo | ¿Lo atrapa? |
|---|---|---|
| Alucinación | el modelo inventa un monto | **sí** |
| Confusión de campo | extrae el capital original en vez del adeudado | **no** |

En el segundo caso el número **está** en el documento: pasa el grounding con
nota perfecta y el caso sale FIRME con un dato equivocado. Se midió sobre 5
casos y hoy no ocurre —la pista explícita en el prompt alcanza para separar los
dos montos— pero el sistema no podría detectarlo si ocurriera.

**El error que sí apareció fue una variante peor**: un dato que ni siquiera
pasaba por el grounding. `aviso_previo` se resolvía por presencia de archivo, y
el archivo existe siempre — lo que cambia es si lo escribió el deudor o el
banco.

**7 de 20 casos ruteados mal, y los 7 empujados a REFINANCIACION:**

| Debía ir a | Fue a | Casos |
|---|---|---|
| LEGALES | REFINANCIACION | **4** |
| COBRANZAS | REFINANCIACION | 3 |

No fallaba al azar: **empujaba sistemáticamente hacia el resultado más
benévolo.** Un banco con este bug refinancia carpetas que debía mandar a
cobranzas, y cuatro que debía mandar a legales — casos con la garantía
formalmente defectuosa. El error no es una métrica que baja, es plata.

Estaba invisible porque los modos de evaluación baratos toman ese campo del
ground truth. **Solo aparece extrayendo de los documentos reales**, que es el
argumento para pagar los 12 minutos de la corrida completa.

Detalle en [`pruebas/BITACORA.md`](pruebas/BITACORA.md), sección H.

## El número, sobre datos nunca vistos

Los 20 casos de desarrollo están gastados: el fix de `aviso_previo` se validó
contra ellos. El resultado que se presenta sale de un set generado con otra
semilla, que el sistema nunca vio.

| | desarrollo | **holdout (seed 99)** |
|---|---|---|
| Escrituras escaneadas | 6/20 | **12/20** |
| Cobertura (casos FIRMES) | 70% | **40%** |
| **Precisión sobre FIRMES** | **14/14** | **8/8** |
| Errores silenciosos | 0 | **0** |

**La cobertura sigue al input; la precisión no se mueve.**

Con el doble de papel escaneado el sistema declara la mitad de los casos, que
es exactamente lo que tiene que hacer: no puede leer esas escrituras y no
pretende que sí. Sobre lo que declara resolver, no se equivocó ni una vez en
ninguno de los dos conjuntos.

Las dos mitades del argumento: **sabe qué sabe, y lo que sabe lo sabe bien.**

Y en las dos corridas, cada caso mal ruteado salió marcado CON RESERVAS. El
sistema puede equivocarse; lo que no hace es equivocarse en silencio.

## La línea entre arreglar el sistema y arreglar el número

El fix de `aviso_previo` salió de una **regla de dominio** —¿quién escribió la
carta, el deudor o el banco?— y no de mirar qué casos fallaban. Por eso vale.

La alternativa era mirar los 7 casos rotos y hacer que pasaran: buscar
`"cobranzas"` en el remitente, que es la dirección que usa este dataset.
Habría dado el mismo 20/20 y habría sido **otra medición circular** —
funcionaría con estos documentos y con ningún otro.

Es la misma trampa que el corte de descubierto: un número que sale bien porque
lo ajustamos al set con el que lo medimos.

> **Si mañana movemos un umbral para que tres casos del holdout pasen,
> cruzamos la línea.** Un fallo nuevo sobre datos frescos se anota como límite
> conocido; no se arregla mirándolo.

## Estructura

```
riesgo/
  modelo.py          Campo, Hallazgo, Advertencia, Alerta, Veredicto
  comparacion.py     nombres por fuzzy, números por dígitos exactos
  contradicciones.py los cinco chequeos entre documentos
  calculo.py         descubierto, cobertura, puntualidad
  ruteo.py           a qué área va el caso y por qué
  motor.py           orquesta un caso: analizar() -> Veredicto

  documentos.py      leer_documento() -> texto por página + OCR si hace falta
  ocr.py             OCR de QVAC para escrituras escaneadas
  extraccion.py      documentos -> campos, un prompt por documento
  normalizacion.py   montos y fechas: del string crudo al valor
  redaccion.py       la nota interna, sobre hechos ya validados

  llm.py             cliente QVAC vía SDK (local o delegado por DHT)
  bridge.py          cliente QVAC vía HTTP
  provider.py        lado servidor de delegated inference

  cli.py             la CLI: `riesgo analizar` / `riesgo cartera`
  resumen.py         el bloque de cierre sobre una cartera completa
  hito1.py           verificación de punta a punta contra el modelo
  medir.py           determinismo y latencia
  evaluar.py         métricas contra el ground truth
  calibrar.py        barrido de umbrales
```

## Usar la CLI

No hay un comando `riesgo` instalado — se invoca como módulo:

```bash
.venv/Scripts/python -m riesgo.cli analizar --cliente 4400
.venv/Scripts/python -m riesgo.cli analizar --cliente 4400 --json
.venv/Scripts/python -m riesgo.cli cartera
```

`--cliente` acepta el número o el nombre completo de la carpeta
(`cliente_4400`). Los IDs válidos son los que trae `dataset/` después de
extraer `dataset_riesgo.tar.gz` — no hay un cliente `4471` en el dataset
real, ese número solo aparece como ejemplo ilustrativo más arriba en este
documento.

Necesita un endpoint de inferencia QVAC accesible en `QVAC_BRIDGE_URL` (ver
`.env`). Si no tenés uno propio levantado, pedile el `QVAC_BRIDGE_TOKEN` y la
URL a quien esté corriendo el server — `.env.example` los deja vacíos a
propósito, y sin ellos la CLI no tiene contra qué inferir.

## Arrancar

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt \
  -f https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.17.0

tar xzf dataset_riesgo.tar.gz          # 20 carpetas sintéticas + ground truth
cp .env.example .env                   # apuntar QVAC_BRIDGE_URL al endpoint
```

Verificar que la inferencia funciona antes de cualquier otra cosa:

```bash
.venv/Scripts/python -m riesgo.hito1 --bridge
```

### Si el caso tiene una escritura escaneada: hace falta un worker Node local

El OCR (`riesgo/ocr.py`) **no pasa por `QVAC_BRIDGE_URL`** — corre contra un
worker de QVAC instalado en esta máquina, aparte del bridge de inferencia de
texto. Sin él, cualquier cliente con `escritura_escaneada: true` en el ground
truth falla con `WorkerNotFoundError`.

```bash
python -m tetherto.qvac_sdk install-worker
```

Necesita Node ≥22.17 instalado y en el PATH.

⚠️ **En Windows el auto-install del SDK está roto**: busca el ejecutable
`npm`, pero en Windows es `npm.cmd`, así que falla con *"npm was not found"*
aunque npm esté instalado y funcionando. Instalación manual, en la ruta que
el SDK espera (`python -c "from tetherto.qvac_sdk.client import
managed_worker_prefix; print(managed_worker_prefix())"` para encontrarla):

```bash
cd ~/.cache/qvac/worker/0.17.1   # o la ruta que haya impreso el comando de arriba
npm install @qvac/sdk@0.17.1
```

Los clientes sin escrituras escaneadas no necesitan nada de esto —
`documentos.py` solo llama a `ocr.py` cuando `pypdf` no extrae texto.

Corre cuatro pasos en orden, y cada uno valida el anterior: el modelo responde,
`temp=0` llega de verdad al motor, `response_format` restringe el decoder, y la
extracción da los valores correctos. Si algo falla, el mensaje dice cuál de los
cuatro.

## Medir

```bash
.venv/Scripts/python -m riesgo.medir --bridge     # determinismo y latencia
.venv/Scripts/python -m riesgo.evaluar            # precisión sobre FIRMES
.venv/Scripts/python -m riesgo.calibrar           # umbrales
```

`medir` compara varias corridas byte a byte. Si difieren, `generationParams` no
está llegando y **cualquier medición posterior es ruido** — conviene correrlo
antes de creerle a un número.

## Dos cosas del SDK que cuestan horas

**El parámetro de temperatura se llama `temp`, no `temperature`,** y va anidado
en `generationParams`. Una clave desconocida se descarta en silencio: la
inferencia queda con sampling por defecto y nada lo delata.

**`response_format` con `json_schema` se compila a una gramática GBNF.** El
decoder no puede emitir nada que viole el schema: ni backticks, ni JSON
truncado, ni `"no encontrado"` donde el schema declara `number | null`. Es la
diferencia entre pedir JSON y garantizarlo.

## Documentos

| | |
|---|---|
| [`SDD-mi-parte.md`](SDD-mi-parte.md) | diseño del motor: extracción, contradicciones, ruteo |
| [`SDD-2.md`](SDD-2.md) | decisiones y correcciones posteriores |
| [`METRICAS.md`](METRICAS.md) | todo lo medido, con el comando que lo reproduce |
| [`onboarding-equipo.md`](onboarding-equipo.md) | para sumarse al proyecto |
