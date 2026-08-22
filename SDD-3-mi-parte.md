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

## 3b. Hallazgo nuevo — grounding numérico no detecta montos truncados por OCR

Encontrado corriendo dev (seed 1) como control del fix de la sección 1. **No es
el bug de las SDD-3** — ese ya está resuelto y dev pasó de 14/14 a 19/20 con
100% de cobertura. Es un modo de fallo distinto, en el mismo sistema de
confianza, y **queda como límite documentado, sin aplicar todavía** (ver
sección 4 — coordinación con el companero, que está corriendo dev/holdout con
su fix en paralelo).

### El caso

`cliente_4498`, escritura escaneada. El OCR de QVAC leyó:

```
"...VALUACION FISCAL: ARS 457. FECHA DE TASACIO 18/07/2024..."
```

El valor real es `$457.000`. El OCR se comió `000` — probablemente el separador
de miles confundió al modelo o el bloque se cortó. El extractor copió `"457"`
fielmente: no alucinó nada, el modelo hizo su trabajo bien.

**El grounding dio `True`.** `_grounding()` en `riesgo/extraccion.py:160` busca
la secuencia de dígitos extraída como substring de los dígitos de la página:

```python
d = digitos(s)                       # "457"
if d and len(d) >= 3:
    for n, pag in enumerate(doc.paginas, 1):
        if d in digitos(pag):        # "457" in "...457..." -> True
            return n, True
```

`"457"` **es** exactamente los dígitos que hay en el texto — no es una
alucinación del modelo, es el texto fuente que está mal. El grounding no puede
distinguir "el valor completo está acá" de "un fragmento truncado del valor
está acá", porque las dos cosas se ven idénticas desde la perspectiva de
"¿aparecen estos dígitos en la página?".

**Consecuencia en el ruteo:** `descubierto = 1.015.000 − 457 ≈ 1.014.543` en vez
de `558.000`. Cruza el corte de $1M. Rutea a LEGALES en vez de COBRANZAS.
Sale **FIRME**, porque `ocr_confianza = 0.806` — arriba de `UMBRAL_OCR` (0.75).
El OCR estaba "seguro" de un texto que estaba truncado; la confianza por bloque
no mide si el número está completo, mide si el bloque se leyó con nitidez.

### Por qué no es el mismo bug que ya arreglamos

Sección 1 es sobre **comparación de texto** (nombres, matrículas) cuando un
lado viene con ruido de OCR — la clasificación PROBABLE/CONFIRMADA ya cubre
eso. Esto es sobre **grounding numérico** validando presencia de dígitos sin
validar que el número esté completo. Ningún umbral de similitud de texto
resuelve esto: el string `"457"` no se compara contra nada, se busca tal cual.

### El fix diseñado — no aplicado

Mismo principio que la sección 1: **no inventar el número correcto** (sumar
ceros a ojo es alucinar exactamente lo que la regla #2 del SDD prohíbe).
**Declarar duda cuando la fuente parece truncada**, en vez de forzar certeza.

La señal: un monto en este dataset nunca termina en un separador decimal sin
dígitos después. `"457."` seguido de una palabra o el final de la línea es la
firma de un número cortado — un monto real termina en `.000`, `,00`, o sigue
con más dígitos.

```python
# en riesgo/extraccion.py, junto a _grounding()

_CORTE_SOSPECHOSO = re.compile(r"\d[.,]\s*(?:[A-ZÁÉÍÓÚÑ]|$)")

def _posible_truncado(d: str, pag: str) -> bool:
    """True si el punto donde aparece `d` en la página termina en un
    separador decimal sin dígitos detrás -- la firma de un monto que el OCR
    cortó a mitad de camino.
    """
    i = digitos(pag).find(d)
    if i == -1:
        return False
    # ubicar el fragmento de texto real (no solo dígitos) alrededor del match
    # y chequear si termina en "." o "," sin numero despues
    ...  # implementación exacta pendiente: mapear posición en digitos(pag)
         # de vuelta a la posición en pag es lo único no trivial acá
```

Y en `_grounding`, cuando el campo es un monto (`normalizar_monto` en
`CONVERSORES`) y `_posible_truncado` da `True`: devolver `grounding_ok=True`
pero marcar el `Campo` con una reserva nueva (no `ocr_confianza`, que ya
significa otra cosa) — algo como `posible_truncado=True` en `modelo.Campo`,
que `Campo.confiable` trate igual que `grounding_ok=False`: degrada el caso,
no fuerza ruteo con ese número.

**Alcance:** solo aplica a campos que pasan por `normalizar_monto`
(`capital_original`, `capital_adeudado`, `garantia_valor`). `cuotas_contrato`
es un entero chico y truncarlo no tiene el mismo patrón de daño.

### Por qué no se aplica ahora

1. Estoy en medio del checklist de entrega y la CLI, que son la entrega
   garantizada.
2. El companero está corriendo dev y holdout con su fix (sección 1) en
   paralelo. Meter un cambio en el grounding ahora mezclaría dos fixes en la
   misma medición — si el número se mueve, no se sabría cuál de los dos lo
   causó.

**Si sobra tiempo después de la CLI y el checklist:** aplicar, correr los 20 de
dev, y si mejora sin romper nada, entra. Si no llega, queda declarado como
límite conocido — que es una entrega válida igual, y es literalmente lo que el
track premia.

**Antes de correr con el fix aplicado: avisar al companero.** No se mide con
código distinto al mismo tiempo.

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
