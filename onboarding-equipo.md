# Onboarding — tu parte del proyecto

Leé esto entero. Son cinco minutos y te ahorra preguntar veinte cosas.

---

## 1. Qué estamos construyendo

Una **CLI que corre IA local** y hace el trabajo que hoy hace un analista de riesgo crediticio cuando un cliente entra en mora.

Hoy: llega un listado de 47 clientes atrasados. Un analista abre cada carpeta (contrato, escritura de la garantía, recibos, mails), lee todo, calcula cuánto está descubierto el banco, detecta si hay algo raro en los papeles, escribe una nota interna y decide si el caso va a cobranzas, refinanciación o legales. **Una a dos horas por caso.** Le quedan 46.

Nuestro agente hace lo mismo en segundos:

```
$ riesgo analizar --cliente 4471

CLIENTE 4471 — Juan Perez
Disparo: 32 dias de atraso

EXPOSICION
  Capital adeudado    $2.800.000   [contrato p.3]    ✓ alta
  Garantia: terreno   $2.000.000   [escritura p.1]   ⚠ media
  Descubierto           $800.000

⚠ CONTRADICCION DETECTADA
  Escritura a nombre de "M. Perez"   [escritura p.1]
  Titular del prestamo: "Juan Perez" [contrato p.1]
  → La garantia puede no ser ejecutable.

RUTEO → LEGALES
```

**Por qué IA local y no una API:** ningún banco puede mandar la carpeta crediticia de un cliente a un servidor de terceros. Hay regulación. Ese es el argumento entero del proyecto y del track.

---

## 2. El track y qué premia el jurado

Vamos al **track QVAC**, primer premio: *"agentes locales que reemplazan trabajo operativo"* — $1.000 USDT.

Jurado: **Raquel Raigal**, DevRel de Tether. Estas son sus palabras textuales sobre qué busca:

> "Funciona con inputs reales y desordenados, no un PDF limpio elegido a mano."

> "Muestra su razonamiento para que un humano pueda auditarlo en cinco segundos."

> "Es honesto sobre lo que no puede hacer: un agente que marca su incertidumbre le gana a uno que alucina un número con confianza."

> "Evidencia, no vibes: corré la misma tarea N veces y mostrá el porcentaje de éxito."

**Cada decisión rara del proyecto sale de una de esas frases.** Si dudás de algo, volvé acá.

**Y esto se descarta sin revisar:** métodos del SDK inventados, código muerto, README que promete lo que no existe, o un demo que solo anda con un input elegido a dedo. Usar IA para programar está permitido y alentado, pero hay que correr lo que escribe antes de entregarlo.

**Deadline:** domingo 12:00 ARG. El demo es un **video grabado**, no hay pitch en vivo.

---

## 3. Tu parte

Somos dos. El reparto:

| | |
|---|---|
| **Franco** | Pipeline de extracción, contradicciones, cálculos, ruteo |
| **Vos** | **OCR sobre documentos escaneados** + **script de evaluación** |

Las dos cosas tuyas son las que definen si ganamos. Te explico por qué.

### Tarea A — OCR (la parte que más se rompe)

El dataset tiene 20 carpetas. **6 de las escrituras están "escaneadas"**: rasterizadas, rotadas uno o dos grados, con manchas de fotocopia y grano JPEG. No se les puede extraer texto con `pypdf` — hay que pasarles OCR de verdad.

QVAC tiene OCR y multimodal. Tu trabajo:

1. Detectar si un PDF es nativo o escaneado (si `extract_text()` devuelve casi nada, es escaneado)
2. Para los escaneados, rasterizar la página y pasarla por OCR de QVAC
3. Devolver texto que el pipeline de Franco pueda consumir igual que el nativo

La interfaz entre los dos es simple:

```python
def leer_documento(path: str) -> tuple[str, bool]:
    """Devuelve (texto, fue_ocr)."""
```

Nada más. Franco no necesita saber cómo lo hacés adentro.

**Ojo:** VisionPsy no está soportado por el SDK todavía. Usá las capacidades de multimodal y OCR del SDK, no VisionPsy.

### Tarea B — Script de evaluación (el que da el número del video)

El dataset viene con `ground_truth.json`: para cada uno de los 20 casos, ya sabemos cuál es la respuesta correcta.

Tu script corre el pipeline sobre los 20 casos y compara. Salida esperada:

```
EXTRACCION       198/240 campos correctos    82.5%
  nativos        156/168                     92.9%
  escaneados      42/72                      58.3%   ← acá se rompe
CONTRADICCIONES    8/11 detectadas
  falsos positivos 2
RUTEO             16/20 correctos            80.0%
```

**Ese corte entre nativos y escaneados es lo más valioso del video.** Es exactamente lo que Raquel pidió: mostrar honestamente dónde falla el modelo chico.

**Arrancá este script hoy temprano, aunque no haya nada que evaluar todavía.** Es lo primero que se abandona si se deja para el final, y sin él no tenemos número.

---

## 4. El dataset

```
dataset/
  ground_truth.json       la respuesta correcta de los 20 casos
  cliente_4400/
    trigger.json          el disparo: cliente + dias de atraso
    contrato.pdf          texto nativo
    escritura.pdf         nativo o escaneado
    recibos.pdf           tabla de pagos
    tasacion.pdf          solo en algunos casos
    correspondencia.txt   mail del cliente o intimacion del banco
```

**Es sintético a propósito.** Documentos reales de un banco tienen datos personales y no se suben a un repo público. Además, con reales tendríamos que leer los 20 legajos a mano para saber la respuesta correcta; acá el generador la sabe porque él la puso.

Trampas puestas adrede:
- Montos en tres formatos distintos: `$ 2.400.000,00` / `ARS 2.400.000` / `$ 2,40 millones`
- 6 escrituras escaneadas
- 11 casos con contradicciones plantadas (titular distinto, cuotas que no cuadran, tasación de 2019, matrícula distinta, domicilio distinto)

**Regla del test final:** el desarrollo se hace con `--seed 1`. El número que va al video se saca regenerando con `--seed 99`, o sea 20 casos que nadie vio. Eso es la defensa contra el *"demo que solo funciona con un input elegido a dedo"*.

---

## 5. Stack y reglas de código

```
tetherto-qvac-sdk    inferencia, OCR, embeddings — todo local
pydantic             validar salida estructurada
pypdf                texto de PDFs nativos
typer / argparse     CLI
rich                 informe en pantalla
```

**Sin LangChain, sin LlamaIndex.** Con modelos de 1–4B las abstracciones esconden el prompt exacto, que es justo donde está el trabajo. Y los wrappers innecesarios son algo que el jurado penaliza.

**Tres reglas:**

1. **Un campo por prompt.** Nada de "leé todo y decime". Un modelo chico se pierde. Se pide un dato, con schema, se valida, se reintenta una vez, y si falla va `null` + flag de revisión.
2. **El modelo nunca decide el ruteo.** Extrae y redacta; la decisión la toma código determinista. Si el modelo se equivoca, reporta mal un campo — no manda un caso a legales por error.
3. **Cuando no sabe, lo dice.** Nunca inventa un número.

---

## 6. Requisitos de entrega

- [ ] Repo público con README de qué se construyó y qué capacidades de QVAC se usaron
- [ ] **Permalinks a la integración de QVAC** — links directos a los archivos y líneas donde ocurre la inferencia. *"Es lo primero que miramos"*
- [ ] Video demo mostrándolo correr localmente de punta a punta
- [ ] Modelo, cuantización, máquina y latencia aproximada
- [ ] Instrucciones de setup que funcionen desde un clone limpio

---

## 7. Lo primero que tenés que hacer

```bash
pip install tetherto-qvac-sdk
```

Bajá el modelo más chico de `huggingface.co/qvac` — son ~2,5 GB, empezá ya porque con el wifi de la sala puede tardar. Hacé una inferencia tonta para confirmar que corre.

**Si eso no anda en 40 minutos, es el único problema del proyecto.** Preguntá en el Telegram del hackathon tagueando a Raquel (`@rraigal`) — las consultas van al grupo, no por privado.

Docs: `docs.qvac.tether.io` · Discord: `discord.gg/tetherdev`

---

## 8. Corte de alcance

Si a las 20:00 la extracción no está estable, bajamos de 12 campos a 5 y los hacemos perfectos.

**Un pipeline que extrae 5 campos con 90% de precisión y muestra el número le gana a uno que intenta 12 y no puede medir nada.**
