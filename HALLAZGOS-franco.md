# Hallazgos — Franco

Lo que encontramos construyendo el motor de riesgo sobre QVAC. Seis entradas:
tres son bugs nuestros que enseñan algo sobre verificación, una es feedback de
producto para Tether, una explica un número que el jurado va a atacar, y la
última son los límites que dejamos declarados en vez de esconder.

El hilo que las une: **una señal existía y se perdía antes de llegar a la
decisión.** Aparece a tres escalas distintas, y en las tres el arreglo no fue
mejorar la lectura sino reconocer que un dato roto no es un dato.

---

## 1. El truncamiento del 457 — tres capas de verificación y ninguna lo atrapó

El caso `cliente_4498`. El OCR leyó una escritura escaneada y devolvió:

```
VALUACION FISCAL: ARS 457.    FECHA DE TASACIO 18/07/2024
```

El valor real es **$457.000**. El PDF lo escribe en formato es-AR —
`gen_dataset.py:53` produce `"ARS 457.000"`, con punto como separador de miles.
El OCR se comió los `000` y dejó el punto suelto.

Con eso, el sistema calculó una cobertura de **0,045%** sobre un capital
adeudado de $1.015.000. La cobertura real es 45%.

### Por qué las tres capas lo dejaron pasar

| Capa | Qué hizo | Por qué no alcanzó |
|---|---|---|
| Modelo | Extrajo `457` | No alucinó: extrajo exactamente lo que el OCR le dio |
| Grounding | Validó contra el texto | No falló: el valor **sí** estaba en el texto. El texto ya venía roto |
| Confianza OCR | `0.806`, sobre `UMBRAL_OCR = 0.75` | Es promedio **por página**: el bloque del monto se leyó mal, el resto perfecto |

El error estaba **antes** de las tres. Cada una hizo bien su trabajo y el caso
salió **FIRME** — con un ruteo equivocado y sin una sola señal de alarma.

Eso es lo peligroso: no es un error ruidoso, es un *confident-wrong*.

### El arreglo, y el que descartamos

El primer diseño fue detectar el punto suelto y reparar el string. **Lo
descartamos: no funciona.** Después de la truncación, `"457."` es genuinamente
ambiguo — puede ser 457 mil truncado o 457 con decimal. No hay forma de
resolverlo desde el string.

El segundo intento fue apoyarse en que `gen_dataset.py:281` genera la garantía
con `round(capital * cobertura, -3)`, o sea siempre múltiplo de 1000. **También
lo descartamos**, y esta es la parte que vale: habría dado 100% en nuestro
dataset y fallado con carpetas reales. Una garantía de verdad no es múltiplo de
1000. Era *overfitting al generador* disfrazado de check determinístico.

Lo que quedó (`riesgo/validacion.py`) son dos señales independientes, y **no
tienen el mismo estatus**:

- **Detector B** — cobertura fuera de la banda `[0.01, 100]`. **Es el que caza
  el 4498** y el que atrapa los confident-wrong reales.
- **Detector A** — separador de miles sobre el string **crudo**: en es-AR un `.`
  de miles lleva exactamente 3 dígitos detrás. Atrapa `"ARS 457."` y `"2.40"`, y
  no marca la coma decimal de `"2.400.000,00"`. **En este dataset no dispara
  nunca.** Es una guarda para un modo de fallo que existe pero que no aparece en
  las 20 muestras.

Lo decimos así a propósito. Un documento cuyo tema central es *código que
compilaba y nunca había corrido* no puede después presentar como logro un
detector que nunca se ejecutó. Sabemos cuál corrió y cuál no, y cuál de los dos
produjo el resultado.

Verificado sobre el caso: el Detector B con el valor truncado devuelve
`cobertura 0.0004502 fuera de [0.01, 100.0]`; con el valor correcto, `None`.
Ningún caso de los 20 lo dispara de más — aunque con `n=20` y una banda de
órdenes de magnitud, eso dice más de lo conservadora que es la banda que de la
robustez del detector.

La banda no sale de los datos. Es de órdenes de magnitud, no de dos decimales
—nadie ajusta `[0.01, 100]` mirando un holdout— y por eso se defiende igual que
el corte de $1M: como decisión de dominio declarada.

> Una garantía que cubre el 0,045% de la deuda no es un préstamo, es un dato
> roto.

---

## 2. El bug de `Campo.confiable` — la alerta que nacía muerta

`Campo.confiable` chequeaba `vacio` **antes** que `alerta_lectura`.

Cuando un detector anulaba un valor sospechoso (poniendo `valor=None` más el
motivo en `alerta_lectura`), el campo se leía como *vacío* antes de leerse como
*alertado*. Y un campo vacío es honesto: no degrada nada. La alerta existía, se
guardaba, y no llegaba nunca a la decisión.

El caso seguía saliendo FIRME.

```python
# ahora, en riesgo/modelo.py
if self.alerta_lectura is not None:
    return False        # esto tiene que ir PRIMERO
if self.vacio:
    return True         # un campo nulo es honesto...
```

Verificado antes/después: **FIRME → CON RESERVAS**, sin regresión en los
harnesses existentes.

Es la misma lección que la sección 1 a otra escala. Ahí la señal se perdía en el
OCR; acá se perdía en un `if` mal ordenado. En los dos casos el sistema afirmaba
con seguridad porque la duda no había llegado.

---

## 3. El SDK Python de QVAC en Windows — feedback para Tether

> Esta sección es feedback de producto sobre el SDK, no documentación del
> proyecto.

### 3.1 Vulkan es obligatorio incluso para inferencia por CPU

La documentación dice que en Linux hay *fallback a CPU* si no hay Vulkan. Lo que
no dice es que **la librería `libvulkan.so.1` tiene que estar presente igual**:
los addons nativos (`@qvac/asr-ggml` entre otros) están linkeados contra ella y
el worker muere con `SIGABRT` / `CANNOT_LOAD` antes de cargar ningún modelo.

```
Uncaught AddonError: CANNOT_LOAD: Cannot load addon '.../qvac__asr-ggml.bare'
  [cause]: Error: libvulkan.so.1: cannot open shared object file
```

En un server headless sin GPU eso no es obvio. El arreglo es
`apt-get install libvulkan1` — el loader solo, sin driver. Vale la pena que esté
en los requisitos de sistema.

En Windows el requisito es más duro: Vulkan **≥1.4**, y ahí no hay fallback. Una
máquina con Intel UHD Graphics (Vulkan 1.3.301) no puede correr QVAC en absoluto,
ni por CPU. Eso es lo que nos empujó a correr el modelo en un server aparte.

### 3.2 `modelType` es obligatorio cuando `modelSrc` es una URL

Las constantes del SDK llevan metadata del engine adentro. Un string pelado no,
y el error no lo dice hasta que ya intentaste cargar:

```
MODEL_TYPE_REQUIRED: modelSrc is a plain string or lacks an engine descriptor
```

Cargar un GGUF arbitrario de HuggingFace necesita
`modelType: 'llamacpp-completion'` explícito. Razonable, pero no está en el
quickstart, que es donde uno prueba primero.

### 3.3 Las constantes de modelo no están en el `.d.ts`

`LLAMA_3_2_1B_INST_Q4_0`, `GTE_LARGE_FP16` y el resto salen de un
`export * from './models/registry/index.js'`, así que no aparecen en el tipado
que ve el editor. Hay que bajar el tarball de npm para saber cuáles existen.

### 3.4 `QVAC_CONFIG_PATH` no es el directorio de modelos

Es la ruta a un **archivo** de config (`.json`/`.js`/`.mjs`/`.ts`). Apuntarlo a
un directorio da `CONFIG_FILE_INVALID: Unsupported config format`. El directorio
de modelos se setea con `QVAC_CACHE_DIR`. Los nombres invitan a confundirlos.

### 3.5 Confianza de OCR por página, no por bloque

La que más nos costó. `ocr_stream` devuelve confianza promediada por página, y
eso diluye exactamente la señal que sirve: en el caso del 457, el bloque del
monto se leyó mal y el resto de la página perfecto, así que el promedio dio
`0.806` y pasó el umbral.

**Confianza por bloque sería la mejora de mayor impacto para nuestro caso de
uso.** Recuperaría cobertura FIRME sin perder precisión.

---

## 4. El patrón: código que compilaba y nunca había corrido

No son bugs sueltos. Es el mismo patrón cinco veces, en cinco lugares
independientes:

```
connect() / completion()      el path --real nunca había corrido contra el modelo
riesgo analizar --cliente     el comando del propio banner no existía
riesgo cartera                fallaba con unrecognized arguments
llm.py / ocr.py               el camino remoto exigía el SDK local
--help                        anuncia un comando y un cliente que no existen
```

Los dos últimos salieron hoy, y el cuarto es el más ilustrativo.

`riesgo/bridge.py` existe justamente para correr el modelo en otra máquina.
Pero importaba tres símbolos puros de `llm.py`, y `llm.py` importaba el SDK a
nivel de módulo. Resultado: **la máquina que no puede correr el modelo tampoco
podía hablarle a la que sí.** El código era correcto, los tipos cerraban, y el
único caso de uso que justificaba el módulo estaba roto.

El quinto: `--help` sigue anunciando `riesgo analizar --cliente 4471`. Ni el
comando tenía entry point ni el cliente 4471 existe en el dataset.

Todos tienen la misma forma: código que compilaba, documentación que se veía
bien, y nadie lo había ejecutado. Conecta directo con la regla 12.5 del SDD
original — *"nada de código generado que no haya corrido"*.

Y explica por qué medimos todo: cada número de este documento salió de una
corrida, no de una estimación.

---

## 5. La cobertura sigue la proporción de OCR, no la dificultad del caso

La cobertura FIRME es 75% en dev y 40% en holdout. Casi la mitad, y la
explicación no es que el sistema rinda peor en el set que no vio.

```
dev      (seed 1)    6 escaneadas de 20     cobertura FIRME  75%
holdout  (seed 99)  12 escaneadas de 20     cobertura FIRME  40%
```

**El doble de exposición a OCR.** Y el escaneo es exactamente lo que produce la
duda: una contradicción sobre texto de OCR se marca PROBABLE en vez de
CONFIRMADA, y eso degrada el caso a CON RESERVAS. Los documentos nativos se
comportan igual que antes.

Esto vale más como explicación porque **predice** en vez de excusar: la cobertura
de un set nuevo se puede estimar mirando cuántas carpetas tienen escaneos, antes
de correr nada.

---

## 6. Límites declarados

Lo que sabemos que falta. Está acá y no escondido porque un límite declarado es
una decisión; uno que el jurado encuentra solo es una sorpresa.

| Límite | Estado | Por qué no se aplicó |
|---|---|---|
| Confianza de OCR por página, no por bloque | Límite del SDK | Ver 3.5. Es la mejora de mayor impacto y depende de Tether |
| Confianza como señal general (cualquier campo crítico bajo umbral degrada) | Diseñado, no aplicado | No podía mejorar precisión —ya está en 100%— y solo bajaba cobertura |
| Doble lectura OCR (`OCR_LATIN` vs `OCR_DOCTR`) | Diseñado, no aplicado | Reemplaza una señal diluida por acuerdo entre dos lectores. Cuesta el doble de tiempo de OCR |
| OCR sin camino remoto | Conocido | El OCR corre contra el worker Node local, no por el bridge HTTP. Una máquina sin Vulkan ≥1.4 no puede analizar carpetas escaneadas |

Y una decisión de diseño que revisamos y mantuvimos: **el ruteo nunca se
suspende.** La sección 7 del SDD original proponía un estado `SUSPENDIDO` para
casos con datos dudosos. Quedó superada por el Detector B: el sistema siempre
produce un destino, y la confianza es un eje separado del ruteo. Un campo con
`alerta_lectura` degrada a CON RESERVAS por el mecanismo que ya existía — no
hacía falta un tercer estado.
