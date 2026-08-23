# SDD 8 — Benchmark a nivel campo

**Qué es:** `riesgo/benchmark.py`, ya en `main` (commit `900b7ef`). Corre y
reporta. No hay que implementar nada.

**Por qué existe:** las métricas que tenemos son a nivel caso (ruteo correcto,
FIRME/CON RESERVAS). Eso no alcanza para demostrar reliability, y es la
diferencia entre una submission de 7,6 y una de 9.

**No toca el motor.** Es un observador: llama a `extraer_carpeta()` y
`analizar()` y clasifica lo que devuelven. Los permalinks a `58d217e` siguen
válidos — verificado, `llm.py` y `ocr.py` están intactos desde ese commit.

---

## 1. El problema que cierra

Hoy podemos decir *"8 de 8 sobre los casos que el sistema declara resolver"*.
Un jurado escucha eso y piensa, con razón: **¿y los campos?**

En un workflow financiero:

```
95% de exactitud con el 5% escalado correctamente   →  excelente
99% de exactitud con 1% de errores silenciosos      →  inaceptable
    en campos que definen el ruteo
```

Los dos números se ven parecidos en un promedio. La diferencia solo aparece
midiendo por campo y separando **qué tipo** de error es.

---

## 2. Las cuatro clases

| Clase | Qué significa |
|---|---|
| `CORRECTO` | extrajo exactamente el valor esperado |
| `DETECTADO` | se equivocó, pero grounding/alerta forzó la revisión |
| `ABSTENCION` | el dato no se podía leer y no lo inventó |
| **`SILENCIOSO`** | **produjo un dato incorrecto como si fuera válido** |

**El último es el KPI.** Un `DETECTADO` no es una falla del sistema — es el
sistema funcionando. El silencioso es el único imperdonable, porque nadie lo va
a mirar.

El informe además separa **solo los campos que definen el ruteo**
(`titular_*`, `matricula_*`, `capital_adeudado`, `garantia_valor`,
`puntualidad`, `aviso_previo`). Un silencioso ahí cambia una decisión; en el
resto solo ensucia el informe.

### Cómo clasifica, y por qué no puede hacerse trampa

El clasificador **no reimplementa** el criterio de confianza: consulta
`campo.confiable`, el mismo que usa el motor para decidir FIRME.

Si lo reimplementara, podría contar como `DETECTADO` algo que el sistema en
realidad no declara — y el benchmark se estaría midiendo contra una versión
optimista de sí mismo. Consultando el criterio real, no puede.

---

## 3. Qué correr, en este orden

**El holdout primero.** Es el número que va al video: datos que el sistema
nunca vio. Si solo llegás a correr uno, que sea ese.

```bash
# 1 — EL número                                      ~18 min
python -m riesgo.benchmark --dataset dataset99 --guardar bench_holdout.json

# 2 — control, la tabla por campo                    ~15 min
python -m riesgo.benchmark --dataset dataset --guardar bench_dev.json
```

Si no está el holdout generado:

```bash
python gen_dataset.py --n 20 --seed 99 --out ./dataset99
```

Flags útiles:

```
--bridge        contra el endpoint HTTP en vez del SDK local
--casos 10      la mitad del tiempo; la tabla por campo ya se ve
--guardar X     JSON con el detalle campo por campo (incluye el crudo del OCR)
```

**No agrega llamadas al modelo.** Hace el mismo trabajo que un
`evaluar --real` — 2 llamadas por caso más OCR en las escaneadas. El costo es
el mismo que ya conocés: ~46 s/caso.

---

## 4. Qué sale, y qué mirar

```
EXTRACCIONES — 20 carpetas / N campos evaluados
  Correcto                     ...
  Incorrecto pero DETECTADO    ...
  Abstencion (no invento)      ...
  ERROR SILENCIOSO             ...        <-- el que importa

  Solo campos que definen el ruteo (N extracciones):
    errores silenciosos: 0   (ninguno)    <-- la línea del video

POR CAMPO — donde rompe el modelo
  campo                 correcto  detect.  abst.  SILEN.
  titular_contrato        20/20        0      0       0
  garantia_valor           ...       ...    ...     ...   ← el sospechoso

RESOLUCION SEGURA
  Resueltos automaticamente   N/20
    de esos, ruteo correcto   N/N
  Escalados a revision        N/20
    con anomalia o documento ilegible real   N/N   ← señal vs ruido
  Latencia mediana  N s/caso

DETALLE DE LOS ERRORES SILENCIOSOS      (si hay alguno)

LOS TRES CASOS DEL VIDEO — elegidos por los datos
  A  limpio          cliente_XXXX
  B  contradiccion   cliente_XXXX
  C  el peor         cliente_XXXX
```

**La tabla por campo es la que más muestra.** El promedio esconde dónde rompe
el modelo. La hipótesis es que `titular` y `matricula` dan casi perfecto y que
los montos en prosa (`garantia_valor`), sobre todo vía OCR, son el punto débil.
Si sale así, poder decirlo **es evidencia de que entendemos el sistema**, no una
debilidad.

**Los escalados justificados** son el matiz que importa: no alcanza con saber
cuántos escaló, hay que saber cuántos de esos tenían de verdad una anomalía.
Escalar 7 con 6 anomalías reales es señal; escalar 7 con 2 es ruido y cuesta
cobertura.

**Los tres casos A/B/C salen de los datos**, no elegidos a mano: A es la
ejecución más limpia, B la contradicción real con más hallazgos graves, y C el
peor caso de OCR/grounding (score de abstenciones + alertas + escaneada). Eso
mata la sospecha de cherry-picking antes de que la planteen.

---

## 5. Las dos reglas

**1. No arreglar mirando los resultados.**

Si aparece un silencioso nuevo en el holdout, **se anota como límite conocido**.
Ajustar un umbral para que ese caso pase es exactamente la trampa que el
proyecto ya evitó dos veces (el corte de $1M y el check de "múltiplo de 1000").

Un fallo declarado es una decisión. Un fallo corregido mirándolo es sobreajuste
al test set.

**2. No tocar el motor.**

`llm.py` y `ocr.py` están intactos desde `58d217e`, que es el commit al que
apuntan los permalinks del README. Mientras siga así, no hay que rehacerlos.

---

## 6. Qué mandar de vuelta

```
bench_holdout.json      el detalle campo por campo
bench_dev.json          si llegaste a correrlo
la salida de consola    completa, para pegar los números en METRICAS
```

Con eso se cierra la sección de métricas y el guion.

---

## 7. Por qué estos números son comprobables

Vale tenerlo a mano por si preguntan.

```bash
git clone <repo>
python gen_dataset.py --n 20 --seed 99 --out ./dataset99
python -m riesgo.benchmark --dataset dataset99
```

Un jurado corre eso y **obtiene los mismos números**. Tres razones:

- el generador del dataset está en el repo — no es un set privado
- el ground truth lo produce código, no etiquetado humano
- la inferencia es determinista (`temp=0`, `seed=7`) — verificado byte a byte

Verificado también que el generador es determinista: regenerar `--seed 99`
produce un `ground_truth.json` con el mismo SHA (`28de7c3f…`).

⚠️ **El límite honesto:** reproducible **no es** representativo. Cualquiera
puede verificar que los números son reales; nadie puede verificar que un
contrato sintético se parezca a uno de banco. Eso se declara, no se esconde:

> El dataset es sintético y el generador está en el repo — cualquiera reproduce
> estos números con dos comandos. Lo que no puedo afirmar es que un contrato
> generado se parezca a uno real. Por eso descartamos un chequeo que habría dado
> 100% contra nuestro propio generador: habría medido el generador, no el
> sistema.

---

## 8. Estado

| | |
|---|---|
| `riesgo/benchmark.py` | **en `main`**, `900b7ef` |
| Clasificador | verificado contra `Campo` sintéticos, sin inferencia |
| Corridas | **pendientes** — es lo único que falta |
| `riesgo/comparar_modelos.py` | en `main`, también pendiente de correr |

Las dos corridas juntas son ~25 min de máquina, desatendidos. No compiten: el
benchmark responde *"¿cómo sé que no alucina?"* y la comparativa responde
*"¿por qué ese modelo?"*.
