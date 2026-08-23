# Benchmark a nivel campo

Las métricas por caso dicen si el sistema acertó. Estas dicen **dónde rompe el
modelo**. Hacen falta las dos, y no coinciden — la última sección explica por qué.

```bash
python -m riesgo.benchmark --dataset dataset99 --guardar bench_holdout.json
python -m riesgo.benchmark --dataset dataset   --guardar bench_dev.json
```

`QWEN3_1_7B_INST_Q4` + `OCR_LATIN`, `temp=0`, `seed=7`. AMD Zen3, 16 hilos, sin
GPU. Python 3.14, Node 22.22, SDK 0.17.1. Sobre `bcd4bdb`, sin tocar el motor.

---

## Los números

| | dev (seed 1) | **holdout (seed 99)** |
|---|---|---|
| campos evaluados | 220 | 220 |
| Correcto | 205 · **93,2%** | 181 · **82,3%** |
| Incorrecto pero DETECTADO | 0 | 23 · 10,5% |
| Abstención (no inventó) | 5 · 2,3% | 9 · 4,1% |
| Marcados SILENCIOSO por el clasificador | 10 · 4,5% | 7 · 3,2% |
| | | |
| Resueltos automáticamente | 15/20 · 75% | 8/20 · 40% |
| · de esos, **ruteo correcto** | **15/15 · 100%** | **8/8 · 100%** |
| Escalados a revisión | 5/20 | 12/20 |
| · con anomalía o documento ilegible real | 5/5 | **12/12** |
| Latencia mediana | 23 s/caso | 23 s/caso |

**Las dos filas por caso reproducen exacto lo publicado** en
`METRICAS-corridas.md` §4 — en otra CPU, otro Python y otro Node. La medición
por caso es sólida.

**Los 12 escalados del holdout son 12/12 justificados**: ninguno es escalado de
relleno. El sistema no infla la cobertura de revisión para verse prudente.

---

## Los 17 "silenciosos", desarmados uno por uno

El informe los rotula `[CRITICO: define el ruteo]`. Esa etiqueta significa *"el
campo pertenece a la clase que alimenta el ruteo"*, **no** *"el error cambió el
ruteo"*. **Ninguno lo cambió** — el 15/15 y el 8/8 lo prueban.

| familia | casos | ¿error real del sistema? |
|---|---|---|
| `titular_escritura` — nombre + DNI | 7 | **no**: lo absorbe la comparación difusa |
| `capital_adeudado` — monto redondeado en el documento | **9** | **no, pero es un límite real** |
| `garantia_valor` — truncamiento OCR del `4498` | 1 | **no**: lo agarra el Detector B |

### Familia 1 — nombre con DNI pegado: el clasificador es más estricto que el motor

El modelo copió `"Maria Gonzalez, DNI 32238510"` donde el ground truth dice
`"Maria Gonzalez"`. Contra la capa de comparación real (`comparacion.py`,
umbral 0,85):

| par | similitud | ¿misma persona? |
|---|---|---|
| `Maria Gonzalez, DNI …` | 0,900 | sí |
| `Martin Diaz, DNI …` | 0,888 | sí |
| `Ricardo Acosta, DNI …` | 0,900 | sí |

Los siete pasan. **Ninguno generó contradicción falsa ni forzó LEGALES**: es
`token_sort_ratio` haciendo exactamente el trabajo para el que está. El modelo
copió de más, no se equivocó de persona.

El clasificador los marca porque compara contra el ground truth **literal** en
vez de preguntarle a `misma_persona()` — que es el criterio que el motor sí usa
para decidir. La discrepancia es del comparador del benchmark, no del pipeline.

### Familia 2 — el monto redondeado: el techo está en el documento, no en el modelo

| set | caso | crudo en el documento | obtenido | esperado | dif |
|---|---|---|---|---|---|
| dev | 4421 | `'7,75 millones'` | 7.750.000 | 7.751.000 | −1.000 |
| dev | 4456 | `'5,51 millones'` | 5.510.000 | 5.506.000 | +4.000 |
| dev | 4484 | `'1,92 millones'` | 1.920.000 | 1.915.000 | +5.000 |
| dev | 4491 | `'1,56 millones'` | 1.560.000 | 1.565.000 | −5.000 |
| dev | 4519 | `'1,74 millones'` | 1.740.000 | 1.736.000 | +4.000 |
| dev | 4526 | `'0,80 millones'` | 800.000 | 798.000 | +2.000 |
| holdout | 4400 | `'4,54 millones'` | 4.540.000 | 4.535.000 | +5.000 |
| holdout | 4470 | `'0,80 millones'` | 800.000 | 795.000 | +5.000 |
| holdout | 4484 | `'2,63 millones'` | 2.630.000 | 2.633.000 | −3.000 |

**El documento mismo dice el monto redondeado.** `gen_dataset.py:55` escribe
`f"$ {v/1_000_000:.2f} millones"`, así que el papel dice literalmente
`"$ 4,54 millones"` y el valor exacto, 4.535.000, **no está en ninguna parte
del documento**.

El modelo copia fiel. `normalizar_monto` convierte bien. `grounding_ok=True`
porque el string está en el texto. **Ningún pipeline, con ningún modelo, puede
recuperar 4.535.000 de un papel que dice "4,54 millones".** Es el techo de
información del documento, no un fallo del sistema.

**Cuánto riesgo hay, cuantificado.** El error más grande medido es **$5.000**.
La distancia del descubierto al corte de $1.000.000:

| set | caso más cercano | descubierto | margen |
|---|---|---|---|
| dev | `cliente_4498` | 1.014.543 | **$14.543** |
| dev | `cliente_4484` (el más cercano de los FIRMES) | 1.058.000 | $58.000 |
| holdout | `cliente_4477` | 879.000 | $121.000 |

El margen más chico es **2,9× el error más grande observado**; entre los que
salen FIRME, 11,6×. **El ruteo no se da vuelta en ninguno de los 40 casos.**

⚠️ **Pero el mecanismo no tiene tope por diseño.** Una carpeta cuyo descubierto
caiga dentro de $5.000 del umbral rutearía mal y saldría FIRME: ninguna etapa
tiene con qué objetar un número que está literalmente en el documento. Queda
como **límite conocido**, no como error medido.

### Familia 3 — el `4498`: acá el benchmark subestima al sistema

`crudo='ARS 457'` → 457 en vez de 457.000, confianza de OCR 0,806. Es el
truncamiento ya documentado en `METRICAS-corridas.md` §4.

El informe lo cuenta como silencioso, pero **a nivel caso el sistema lo agarra**:
sale `COBRANZAS · CON RESERVAS · ok`.

La razón: el clasificador consulta `campo.confiable`, y el Detector B es una
alerta **cross-campo a nivel caso** (cobertura `garantia/capital` fuera de
`[0.01, 100]`), no un `alerta_lectura` del campo. El campo no lleva reserva, así
que se clasifica como silencioso aunque el caso se haya degradado bien.

Consultar `campo.confiable` evita que el benchmark se mida contra una versión
optimista de sí mismo — y el efecto colateral es que **subestima al Detector B**.
La vista por campo no puede ver un detector que razona entre campos.

---

## Por qué hacen falta las dos vistas

| | ve | no ve |
|---|---|---|
| **por caso** | el veredicto real, los detectores cross-campo | qué campo se rompió |
| **por campo** | dónde rompe el modelo | detectores cross-campo, el fuzzy de nombres, los nulos |

Dos ejemplos concretos de la última columna:

- **Los nulos se cuentan como `ABSTENCION`**, la clase buena. Correcto en
  general — pero un nulo en `capital_adeudado` anula el descubierto, hace caer
  el ruteo al default y **sale FIRME** (ver el *nulo limpio* en
  [`COMPARATIVA-MODELOS.md`](COMPARATIVA-MODELOS.md)). La vista por campo no
  puede ver ese modo, porque un nulo no es "un dato incorrecto".
- **El Detector B y el fuzzy de nombres** absorben 8 de los 17, y la vista por
  campo los cuenta igual.

**Ninguna de las dos vistas es la correcta.** La de campo dice *dónde* rompe el
modelo; la de caso dice *si importó*.

---

## Lo que se puede afirmar

1. **Sobre los casos que el sistema declara resolver, no se equivocó nunca:
   15/15 en dev, 8/8 en holdout.** Reproducido en otra máquina.
2. **La cobertura sigue al input y la precisión no se mueve**: 75% con 6
   escrituras escaneadas, 40% con 12. Los 12 escalados del holdout son 12/12
   justificados.
3. **A nivel campo, 93,2% correcto en dev y 82,3% en holdout**, con la
   degradación concentrada en `titular_escritura`.
4. **Un límite nuevo, medido y acotado**: el monto redondeado en el documento.
   9 casos, error máximo $5.000, margen mínimo al umbral $14.543. No cambió
   ningún ruteo y no tiene tope por diseño.

**Lo que NO conviene afirmar:** *"17 errores silenciosos, cada uno cambia una
decisión"*. Es la línea que imprime el informe y no se sostiene — 8 los absorbe
la maquinaria de confianza, y los 9 restantes son el techo del documento, no un
fallo del pipeline. Ninguno movió un veredicto.
