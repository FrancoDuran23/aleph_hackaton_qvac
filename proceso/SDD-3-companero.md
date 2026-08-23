# SDD — Tu parte (OCR y métricas)

Post-integración del OCR real. Lee esto antes de pushear el fix que estás validando.

---

## 0. Lo que lograste y por qué cambia el proyecto

`riesgo/ocr.py` andando, 95.8% de recuperación de campos (23/24), y `cliente_4421/escritura.pdf` pasando de 0 caracteres a "Jorge Martinez" con confianza 0.815. Eso es la mitad del sistema que hasta ayer no existía.

Y los dos bugs que encontraste en `llm.py` (`connect()` devuelve `Client` no el transport, `completion()` no es coroutine) son más importantes de lo que parecen: **significan que el path `--real` nunca había corrido contra el modelo.** Fallaba antes de llegar al SDK. Eso va a `HALLAZGOS.md`.

**La consecuencia:** el tag `v1.0-motor` (8/8 sobre FIRMES en holdout) queda invalidado. Se midió con el OCR en stub, o sea con la mitad de las escrituras en blanco. Tu corrida de holdout al 65% con 14 contradicciones falsas **no es un empeoramiento** — es la primera medición del sistema completo.

---

## 1. El fix — parar antes de pushear

Estás por pushear comparación tolerante: umbral más laxo cuando el lado viene de OCR. **No lo pushees así.**

**Por qué no.** El 0.85 de nombres no es un número elegido a ojo: salió de barrer umbrales contra el ground truth (`calibrar_umbrales.py`). Aflojarlo para tapar el ruido de OCR reabre las falsas alarmas que ese barrido cerró — solo que ahora en la otra dirección y sin medición que lo respalde.

Y hay un problema metodológico peor: si el umbral se ajusta mirando cuánto mejora el holdout, es exactamente la trampa que el proyecto ya documentó y evitó con el corte de $1M. Ajustar un parámetro para que el test set dé mejor no es un fix — es sobreajuste con otro nombre, y el jurado descarta demos que solo funcionan sobre inputs elegidos.

**Lo que sí hay que hacer.** No cambiar *cuándo dos valores matchean*. Cambiar *qué tan firme es la conclusión* cuando un lado viene con ruido. La clasificación ya existe en la sección 5b del SDD:

```python
def evaluar_contradiccion(campo_a, campo_b, umbral=0.85):
    """
    campo_a, campo_b: {"valor", "origen": "nativo"|"ocr", "confianza": float|None}
    El umbral NO se toca. Lo que cambia es el nivel del hallazgo.
    """
    similar = similitud_nombres(campo_a["valor"], campo_b["valor"]) >= umbral

    hay_ocr_dudoso = (
        (campo_a["origen"] == "ocr" and (campo_a["confianza"] or 1) < 0.7) or
        (campo_b["origen"] == "ocr" and (campo_b["confianza"] or 1) < 0.7)
    )

    if similar:
        return {"hallazgo": "DESCARTADA"}
    if hay_ocr_dudoso:
        return {"hallazgo": "PROBABLE", "degrada_a_reservas": True}
    return {"hallazgo": "CONFIRMADA", "degrada_a_reservas": False}
```

**Y en el ruteo:** `PROBABLE` **no** dispara "contradicción grave → LEGALES". El caso rutea por monto y puntualidad como cualquier otro, y sale CON RESERVAS con la anotación.

**Qué esperar del número.** Puede no mejorar tanto como con el umbral aflojado, y eso está bien. Lo que tiene que pasar es que las contradicciones falsas **dejen de forzar LEGALES**, no que desaparezcan. Siguen anotadas, como duda en vez de certeza.

**Sobre el umbral de 0.7 en confianza de OCR:** es un punto de partida. Mirá la distribución real de confianzas sobre las 12 escaneadas del holdout antes de fijarlo. Si el 0.815 de `cliente_4421` fue una lectura correcta, el corte tiene que quedar por debajo de eso.

---

## 2. Las corridas que producen el número final

Con el fix correcto aplicado:

```
1. dev (seed 1)       — control. Solo 6 escaneadas, NO debería moverse.
                        Si baja de 14/14 sobre FIRMES, el fix rompió algo.

2. holdout (seed 99)  — EL número. 12 escaneadas, es el caso difícil.
                        Este es el que va al video.
```

**Reportar siempre estas cuatro líneas:**

```
precisión sobre FIRMES     x/x        ← el número protagonista
cobertura (% FIRMES)       x/20
contradicciones            detectadas / existentes  +  falsos positivos
errores silenciosos        (casos MAL que salieron FIRME)  ← tiene que ser 0
```

La última es la promesa del sistema. Si aparece un MAL FIRME, es lo primero a investigar.

**Y la regla que no se negocia:** si en el holdout aparece un caso mal, **no lo arregles mirándolo**. Se anota como límite conocido y va al README. Arreglar contra el test set es la versión sutil del input elegido a dedo.

---

## 3. Proceso de trabajo

**Pushear por PR, no directo a `main`.** El merge anterior tocó `llm.py` y `contradicciones.py` de Franco sin aviso previo. Salió bien, pero con dos personas editando los mismos archivos a esta altura del proyecto, un PR es media hora de seguro por dos minutos de trabajo.

**Commiteá `METRICAS-corridas.md`.** Está local y es parte de la evidencia de la entrega.

---

## 4. `HALLAZGOS.md` — lo que aportás vos

Documento compartido, sale de las bitácoras. Tus entradas:

- **`connect()` y `completion()`**: el path `--real` nunca había corrido contra el modelo. Código que compilaba pero fallaba antes de llegar al SDK.
- **Contradicciones falsas por ruido de OCR**: el modo de fallo que aparece recién cuando hay OCR real. Un dígito mal leído en una matrícula convierte un caso limpio en una garantía "de otro inmueble".
- **El umbral no era la solución**: por qué se descartó aflojar la comparación y se eligió declarar duda.
- **Recuperación de campos del OCR**: 95.8% (23/24), 9-12 s/página, con la distribución de confianzas.

Ese archivo es feedback de producto para Tether. Es lo que un DevRel no consigue sin builders reales.

---

## 5. Orden

```
1. Aplicar el fix correcto (sección 1)      ← bloqueante
2. Correr dev — verificar que no regresó
3. Correr holdout — EL número
4. PR con el fix + METRICAS-corridas.md
5. Tus entradas de HALLAZGOS.md
```

Los pasos 2 y 3 son secuenciales por una razón: si dev regresó, el problema está en el fix y no tiene sentido gastar la corrida del holdout.
