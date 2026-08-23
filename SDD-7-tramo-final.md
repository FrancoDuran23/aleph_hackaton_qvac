# SDD 7 — Mi parte, tramo final

**Estado:** PR #3 mergeado. Cadena `alerta_lectura` verificada de punta a punta (extracción setea, motor lee, CLI muestra). `main` sano, sin campos duplicados. Clone limpio cerrado con cinco agujeros encontrados y arreglados.

**Único bloqueante abierto:** la corrida de holdout **sobre el merge**. Los números que tenemos (8/8, 90%) se midieron sobre la implementación anterior del compañero, antes de reescribirla sobre mi schema. Es otro código.

**Lo que ese bloqueante frena:** solo el tag. Todo lo demás de este documento se hace en paralelo.

---

## 0. Por qué hace falta re-correr

El compañero midió con `Campo.malformado` y una advertencia ad-hoc en `motor.py`. Después reescribió sobre `Campo.alerta_lectura` y movió el Detector B a `Veredicto.alertas`.

El comportamiento **debería** ser equivalente. Pero "debería" no es una medición, y este es el número que va al video.

Y en la misma corrida sale el diff que quedó pendiente: **que los 8 FIRMES del holdout sean los mismos 8**, no un empate por compensación (uno sale, otro entra, mismo total).

```
Pedido al compañero:
  - holdout (seed 99) sobre el merge
  - las cuatro líneas
  - lista de qué casos salieron FIRME, para comparar contra la corrida anterior
```

---

## 1. Guion — corregir el comando y el caso

**Bloqueante para grabar.** El SDD-6 dice grabar `riesgo analizar --cliente 4471`. Ese comando **no existe** (agujero #2 del clone limpio: sin entry point, sin `pyproject.toml`) y el cliente 4471 **tampoco existe en el dataset**.

```
Antes:   riesgo analizar --cliente 4471
Ahora:   python -m riesgo.cli analizar --cliente 4421
```

**Por qué 4421:** ya verificado con OCR real, y muestra `PROBABLE` en vivo sin forzar LEGALES. Ese plano vale doble — OCR real y el fix B funcionando en una sola corrida.

**Chequeo antes de grabar:** que el bloque `⛔ ALERTA DE LECTURA` se siga renderizando después de la reescritura. Es el plano de cierre del acto 3 y él tocó justo el mecanismo que lo alimenta. Si el 4421 no dispara alerta de lectura, hace falta un segundo caso que sí — probablemente 4498.

---

## 2. Números al guion

Provisorios hasta que confirme la corrida. La narrativa no cambia con ellos.

```
Holdout (seed 99, nunca visto)
  Exactitud global            90%   (18/20)
  Precisión sobre FIRMES      8/8 = 100%
  Errores silenciosos          0
  Cobertura FIRME             8/20  (40%)
```

### 2.1 El cambio de narrativa que hay que hacer

El SDD-6 decía *"esperar que la cobertura baje y reportarlo"*. **En holdout no bajó.** Se mantuvo idéntica antes y después de los detectores.

Eso es mejor de lo que parece y hay que decirlo así:

> Encontramos el modo de fallo en dev, lo corregimos, y verificamos que el holdout estaba limpio. El número no subió porque no había nada roto ahí — pero ahora sabemos que no lo había.

Eso cierra la pregunta que quedó abierta en el Límite 1 (*si el truncamiento contaminó casos del holdout que hoy figuran como correctos*). La respuesta es no, y está medida.

### 2.2 El 40% hay que enmarcarlo, no esconderlo

Es el número que el jurado va a atacar. La respuesta va en el video, no improvisada:

> De 20 casos, 18 rutean correctamente. En 8 el sistema resuelve solo, con 100% de precisión y cero errores silenciosos. Los otros 12 salen con la duda declarada y una alerta que un humano verifica en cinco segundos. No es un sistema que decide el 40% — es uno que sabe cuáles puede decidir.

Un sistema que afirma 20 de 20 con 90% de precisión es **peor** para un banco. Ese es el argumento, y es el mismo que sostiene toda la clasificación FIRME / CON RESERVAS.

### 2.3 La banda del Detector B, si preguntan

No es un umbral calibrado y no se presenta como tal:

> Es un rango de plausibilidad del dominio, no sale de los datos. Una garantía que cubre el 0,045% de la deuda no es un préstamo, es un dato roto.

Se defiende igual que el corte de $1M: decisión declarada. Y la banda misma lo demuestra — es de órdenes de magnitud, no de dos decimales. Nadie ajusta `[0.01, 100]` mirando un holdout.

---

## 3. `HALLAZGOS-franco.md`

Archivo separado. Se compila con el del compañero al final.

### 3.1 El truncamiento del `457`

La historia principal. Tres etapas de verificación y ninguna podía atraparlo:

- El **modelo** no alucinó — extrajo exactamente lo que el OCR le dio.
- El **grounding** no falló — validó fidelidad al texto, y el texto ya venía roto.
- La **confianza de OCR** era 0.806, alta, porque es promedio por página: el bloque del monto se leyó mal, el resto perfecto.

El error estaba antes de las tres. La corrección no fue mejorar la lectura, fue reconocer que un número mal formado no es un número.

### 3.2 El bug de `Campo.confiable`

`vacio` se chequeaba antes que `alerta_lectura`. Cuando el detector anulaba el valor, el campo se leía como vacío antes de leerse como alertado, y la alerta quedaba muerta: el caso salía FIRME igual.

Verificado antes/después: FIRME → CON RESERVAS. Sin regresión en los harnesses existentes.

**Es la misma lección que 3.1 a otra escala:** una señal existía y se perdía antes de llegar a la decisión.

### 3.3 El worker Node de OCR y el bug de `npm` vs `npm.cmd` en Windows

**Esta entrada es para Tether, no para el README.** El OCR corre contra un worker Node local, separado del bridge, y el SDK falla en Windows por `npm` vs `npm.cmd`. Verificado, con solución manual documentada.

Es feedback de producto sobre el SDK — exactamente lo que un DevRel no consigue sin builders reales.

### 3.4 El patrón: código que compilaba y nunca había corrido

Tres veces lo mismo, en tres lugares distintos:

```
connect() / completion()     el path --real nunca había corrido contra el modelo
riesgo analizar --cliente    el comando del propio banner no existía
riesgo cartera               fallaba con unrecognized arguments
```

**Nombrarlo como patrón, no como tres bugs sueltos.** Código que compilaba, documentación que se veía bien, y nadie lo había ejecutado. Es más fuerte así, y conecta directo con la regla 12.5 del SDD original: *"nada de código generado que no haya corrido"*.

### 3.5 Límites conocidos que quedan declarados

- **Confianza de OCR por página, no por bloque.** Es la mejora que recuperaría cobertura FIRME sin perder precisión. Feedback directo sobre la API de OCR de QVAC.
- **Confianza como señal general** (cualquier campo crítico bajo umbral degrada): diseñada, no aplicada. No podía mejorar precisión —ya está en 100%— y solo podía bajar cobertura.
- **Doble lectura OCR** (`OCR_LATIN` vs `OCR_DOCTR`): diseñada, no aplicada. Reemplaza una señal diluida por acuerdo entre dos lectores, que es una señal por campo.
- **Sección 7 del SDD original superada por el fix B.** El ruteo ya no se suspende: siempre produce un destino, y la confianza es un eje separado.

---

## 4. Pasada en seco

**Desde el clone limpio, no desde el directorio de desarrollo.** Todo el trabajo del punto 2 anterior se pierde si grabás desde donde tenés el entorno cargado.

```
1. Corrida completa de cada plano, cronometrada
2. Sin grabar
3. Anotar qué tarda más de lo esperado
```

Sale de ahí qué se cae. El orden de sacrificio del SDD-6:

```
1. La historia corta del bug de Campo.confiable
2. La tabla comparativa de modelos
3. El plano de PROBABLE vs CONFIRMADA
4. Todo lo del acto 2 más allá de un caso completo
```

**No se cae nunca:** el acto 3.1 (truncamiento) y las cuatro líneas del acto 4.

---

## 5. Tag y permalinks

**En este orden, no antes.**

```
1. Números del holdout confirmados sobre el merge
2. Tag v1.1-motor
3. git rev-parse HEAD  →  el hash
4. Permalinks de ese hash
```

**Los permalinks que van:**

- `riesgo/llm.py` — la línea donde se llama `completion()`
- `riesgo/ocr.py` — la línea donde se usa `OCR_LATIN`

En GitHub: abrís el archivo, clickeás el número de línea, apretás `y`. La URL se reescribe sola de `main` al hash.

**Por qué del hash y no de `main`:** el permalink existe para demostrar que la integración con el SDK es real. Si apunta a `main` y alguien commitea después, el link muestra otra línea — y un permalink roto demuestra exactamente lo contrario de su único trabajo.

**Por qué del hash del tag:** el link y el número apuntan al mismo estado del código. El jurado ve el código que produjo las cifras que están en el video.

---

## 6. Orden

```
paralelo, ahora:
  → pedir corrida de holdout sobre el merge (compañero)
  → guion: comando real + números                     (1, 2)
  → HALLAZGOS-franco.md                               (3)
  → verificar que ⛔ ALERTA DE LECTURA se renderiza

después:
  1. números confirmados
  2. tag v1.1-motor
  3. permalinks del hash
  4. pasada en seco desde el clone limpio
  5. grabar
```

---

## 7. Checklist

- [ ] Corrida de holdout sobre el merge, con lista de FIRMES para diff
- [ ] Guion: `python -m riesgo.cli` y caso 4421
- [ ] `⛔ ALERTA DE LECTURA` verificado en pantalla post-reescritura
- [ ] Números pegados en los huecos + enmarcado del 40%
- [ ] `HALLAZGOS-franco.md` con las cinco secciones
- [ ] Tag `v1.1-motor`
- [ ] Permalinks del hash del tag en el README
- [ ] Latencia del pipeline completo con OCR, medida en caliente
- [ ] Pasada en seco cronometrada desde el clone limpio
- [ ] Grabado
