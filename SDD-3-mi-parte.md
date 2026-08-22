# SDD 3 — Mi parte (post-OCR real)

Complementa SDD, SDD-2, SDD-mi-parte. Todo lo de acá surge de la primera corrida con OCR real, que invalidó el freeze `v1.0-motor`.

---

## 0. Qué cambió y por qué este documento existe

`v1.0-motor` se congeló con `leer_documento()` en modo stub: las escrituras escaneadas devolvían "ilegible" y el caso salía CON RESERVAS por esa única razón. Nunca hubo texto de OCR real entrando al comparador de contradicciones.

Con el OCR real integrado, apareció un modo de fallo que **no podía existir antes**: el OCR lee con ruido, el comparador ve dos valores que no matchean bit a bit, y dispara una contradicción que no es tal. Holdout cayó a 65% con 14 contradicciones falsas.

**Esto no es que el sistema empeoró.** Es la primera medición sobre el sistema completo. `v1.0-motor` medía un sistema con la mitad de las escrituras en blanco.

---

## 1. El fix — versión correcta, no la del umbral

**Lo que NO hay que hacer:** aflojar el umbral de similitud (0.85 en nombres) cuando el dato viene de OCR.

Por qué no: ese umbral salió de barrer contra el ground truth (documentado en `calibrar_umbrales.py` y en el SDD original). Aflojarlo ad-hoc para tapar ruido de OCR **reabre exactamente el problema que se cerró** — vuelven a subir las falsas alarmas, solo que ahora en la dirección contraria y sin medición que lo respalde.

Y hay un problema metodológico más de fondo: si el umbral se toca mirando cómo mejora el número del holdout, es la misma trampa que ya se evitó con el corte de $1M. Ajustar un parámetro para que el test set dé mejor no es un fix, es sobreajuste con otro nombre.

**Lo que sí hay que hacer:** usar la clasificación que ya existe en la sección 5b del SDD original. No se cambia cuándo dos valores "matchean" — se cambia **qué tan firme es la conclusión** cuando uno de los dos lados viene con ruido.

```python
def evaluar_contradiccion(campo_a, campo_b, umbral=0.85):
    """
    campo_a, campo_b: {"valor": str, "origen": "nativo"|"ocr", "confianza": float|None}
    """
    similar = similitud_nombres(campo_a["valor"], campo_b["valor"]) >= umbral

    hay_ocr_dudoso = (
        (campo_a["origen"] == "ocr" and (campo_a["confianza"] or 1) < 0.7) or
        (campo_b["origen"] == "ocr" and (campo_b["confianza"] or 1) < 0.7)
    )

    if similar:
        return {"hallazgo": "DESCARTADA"}

    if hay_ocr_dudoso:
        # difieren, pero uno de los dos lados no es confiable:
        # no se puede afirmar que sea una contradicción real
        return {"hallazgo": "PROBABLE", "degrada_a_reservas": True}

    # difieren y los dos lados son confiables: es un hallazgo real
    return {"hallazgo": "CONFIRMADA", "degrada_a_reservas": False}
```

**Y el ruteo:** `PROBABLE` no dispara la regla de "contradicción grave → LEGALES". El caso rutea con las reglas normales de monto/puntualidad, y sale marcado CON RESERVAS con la anotación de qué no se pudo confirmar.

**Resultado esperado:** el número puede no mejorar tanto como con el umbral aflojado — y esa es la señal de que está bien hecho. Lo que tiene que pasar es que **las contradicciones falsas dejen de forzar LEGALES**, no que dejen de existir. Siguen anotadas, solo que como duda y no como certeza.

**Verificación de que no rompe nada:** correr dev (seed 1) después del fix. Si baja de 14/14 sobre FIRMES, algo está mal — dev tiene solo 6 escaneadas y no debería moverse.

---

## 2. Checklist de entrega

- [ ] **Permalinks a la integración de QVAC.** Links directos de GitHub a las líneas exactas donde ocurre la inferencia — `riesgo/llm.py` (completion) y `riesgo/ocr.py` (OCR). *Es lo primero que mira Raquel.*
- [ ] **README con modelo, cuantización, RAM, latencia real.** El número de latencia tiene que ser el del pipeline completo con OCR, no solo la extracción de texto (los 9,3s viejos ya no son la cifra correcta si el caso tiene escaneados).
- [ ] **Setup desde clone limpio, probado de verdad.** Clonar en un directorio nuevo, seguir el README al pie de la letra, sin atajos de memoria. Si falta un paso, mejor descubrirlo ahora.
- [ ] **`--json` funcionando** para que sea consumible fuera de la CLI.

---

## 3. CLI — pulido pendiente

Lo funcional ya está (extracción + contradicciones + ruteo + nota + impresión, contra el modelo real). Falta, según `SPEC-cli-rich.md`:

- Ancho de columna fijo — una cita larga no debe romper la grilla. Truncar con `...` si excede el ancho, no dejar que empuje el layout.
- Verificar que el caso con contradicción `PROBABLE` (nuevo, sección 1) se distinga visualmente de una `CONFIRMADA`. Sugerido: mismo color de advertencia (amarillo) que CON RESERVAS, no el rojo de GRAVE.

No tocar nada más de la CLI hasta que el fix de la sección 1 esté validado y re-tageado.

---

## 4. Orden

```
1. Avisar del fix correcto (sección 1) — bloqueante, antes que cualquier otra cosa
2. Esperar validación de dev + holdout con el fix aplicado
3. Re-tag v1.1-motor
4. Checklist de entrega (sección 2)
5. Pulido de CLI (sección 3)
6. HALLAZGOS.md (documento compartido, ver SDD del compañero)
7. Video sobre el holdout con OCR real y el fix correcto
```

No avanzar a 4-5 con un fix sin validar debajo. Si el número se mueve raro, mejor descubrirlo antes de construir el resto encima.

---

## 5. Para el video / README — cómo se cuenta este hallazgo

> "El modo de fallo más importante no apareció en la extracción ni en el modelo — apareció en cómo el sistema comparaba dos lecturas cuando una traía ruido de OCR. La primera solución que probamos aflojaba el umbral de comparación; la descartamos porque reabría falsas alarmas ya calibradas contra ground truth. La solución correcta fue declarar la duda en vez de forzar una certeza: cuando un lado de la comparación viene de un OCR de baja confianza, el hallazgo se marca PROBABLE y el caso sale CON RESERVAS — no CONFIRMADA forzando legales."

Esa frase, con el número de antes/después al lado, es más fuerte que un score alto sin la historia detrás.
