# SDD 2 — Decisiones y correcciones

Complementa al SDD original. Todo lo de acá surgió **después** de escribirlo, corriendo código o leyendo las docs reales.

---

## 1. Corrección metodológica: el modo oracle no es un logro

**El problema.** `gen_dataset.py:410` usa `descubierto > 1_000_000` y el mismo orden de reglas que implementa el ruteador. Reproducir 20/20 en modo oracle prueba que el código coincide con la especificación — nada más. No mide extracción, no mide clasificación, no mide nada que el generador no haya puesto ahí.

**El barrido del corte tiene el mismo defecto.** $1M "gana" porque es el número con el que se generaron los datos. Cualquier barrido lo iba a coronar. Es circular.

**Qué sí es defendible:**

```
precisión sobre los FIRMES
```

Ese número depende de la extracción y de la clasificación de confianza — dos cosas que el generador no regaló.

**Cómo se presenta el corte de descubierto en el video:**

> "Lo fijamos en un millón. En una cartera real ese número sale de la política de riesgo del banco, no de los datos."

Más honesto que presentar un umbral "calibrado" que en realidad venía de fábrica.

**Regla general:** antes de reportar cualquier métrica, preguntarse si el generador ya sabía la respuesta. Si la sabía, la métrica mide fidelidad a la spec, no capacidad del sistema.

---

## 2. Parámetros de generación — bug encontrado y arreglado

**El bug.** `server.mjs` mandaba `temperature` y `maxTokens` como claves top-level. **No son claves del contrato de QVAC: se descartan en silencio.** La inferencia corría con sampling por defecto sin avisar.

Consecuencia: cualquier medición hecha antes de este arreglo era ruido. Si el mismo contrato podía devolver `2.800.000` una vez y `2.880.000` la siguiente, la extracción no era reproducible y no había forma de saberlo.

**La forma correcta:**

```js
generationParams: {
  temp:    0,
  top_p:   1,
  seed:    <fijo>,
  predict: <max tokens>
}
```

Anidado, no top-level.

**Y además:** el bridge ahora forwardea `response_format`, que es lo que da JSON garantizado por gramática. Eso cierra la duda que quedó abierta en el SDD original sobre dónde se configuraba la temperatura.

**Al README.** Que hayan encontrado que los parámetros top-level se descartaban en silencio es evidencia de haber corrido las cosas en serio. Va en la sección de aprendizajes.

---

## 3. Delegated inference — reemplaza el bridge HTTP custom

QVAC trae delegación de inferencia P2P out-of-the-box, vía la DHT de Hyperswarm. Está pensada exactamente para esto: *"usalo cuando una inferencia requiere más recursos de los que el dispositivo local puede dar"*.

### Cómo funciona

**Servidor — provider:**

```js
import { startQVACProvider } from '@qvac/sdk';

const res = await startQVACProvider({
  firewall: { mode: 'allow', publicKeys: [consumerPublicKey] }
});
console.log(res.publicKey);   // se lo pasás al consumer
```

**Laptop — consumer:**

```js
const modelId = await loadModel({
  modelSrc: QWEN3_1_7B_INST_Q4,
  delegate: {
    providerPublicKey,
    timeout: 60_000,
    fallbackToLocal: true
  }
});
// completion() se usa IGUAL que si el modelo fuera local
```

La conexión es directa: el consumer hace `dht.connect(providerPublicKey)`. No hay topic ni fase de descubrimiento — el provider se publica en la DHT con su keypair y el consumer conecta por clave pública.

### Por qué es mejor que el bridge custom

| | Bridge HTTP | Delegated inference |
|---|---|---|
| Integración | código propio | **capability oficial de QVAC** |
| Auth | token custom | firewall por clave pública |
| Cifrado | hay que armarlo | end-to-end incluido |
| Si el server cae | falla | `fallbackToLocal: true` → corre local |
| Permalinks al jurado | apuntan a un proxy | apuntan al SDK |

**Y el argumento narrativo.** Con un bridge HTTP, "local-first" se debilita: se ve que le pegás a una IP remota. Con delegated inference no estás rompiendo el modelo local — estás usando **la capa P2P que QVAC diseñó para eso**. Es la diferencia entre parecer un atajo y ser arquitectura.

### El momento de video que habilita

`fallbackToLocal: true` permite demostrar resiliencia en vivo:

> Corriendo con delegación al servidor → matás el provider → el siguiente caso corre local sin intervención.

Eso es P2P haciendo algo visible, no decorativo.

### Caveats verificados en las docs

- ~~**Los ejemplos publicados son JS/TS.**~~ **VERIFICADO contra el SDK instalado (`tetherto-qvac-sdk 0.17.1`): las dos puntas existen en Python.** No hace falta JS.

  ```python
  # consumer -- riesgo/llm.py
  load_model(transport, model_src=..., delegate={
      "providerPublicKey": clave,   # requerido
      "timeout": 60_000,
      "fallbackToLocal": True,
  })

  # provider -- riesgo/provider.py
  res = await provide(transport, ProvideRequest(
      firewall={"mode": "allow", "publicKeys": [clave_consumer]}))
  res.public_key   # la clave que va al consumer
  ```

  Los campos del `delegate` van en **camelCase** en el wire: `providerPublicKey`,
  `timeout`, `healthCheckTimeout`, `fallbackToLocal`, `forceNewConnection`. El
  firewall acepta `mode: "allow" | "deny"` y `publicKeys`.

  ⚠️ Lo que **no** está verificado: la unidad de `timeout`. La anotación es
  `float | None` y el ejemplo JS usa `60_000`, lo que sugiere milisegundos,
  pero no hay nada en el SDK que lo confirme. Medir en la primera corrida.
- **Cold start de 15 a 45 segundos** en la primera conexión (bootstrap de la DHT). Las siguientes son sub-segundo porque reusan el socket. Importante para la medición de latencia: **medir en caliente, no en la primera llamada.**
- **No hay reconexión automática.** Si el provider reinicia, hay que reiniciar el consumer.
- Se puede fijar identidad determinista del provider con `QVAC_HYPERSWARM_SEED` (hex de 64 caracteres). Útil para no tener que copiar una clave nueva cada vez.

---

## 4. Corrección: QVAC no tiene Bluetooth

El descubrimiento de pares por **BLE (Bluetooth Low Energy) es del track de Pears**, no de QVAC. Aparece como "dirección de bonificación: BLE-Swarm" en las bases de ese track.

Lo que QVAC tiene en P2P:

- **Delegated inference** — delegar a un peer más potente (sección 3)
- **Blind relays** — conectar peers a través de NAT/firewalls vía nodos relay
- **Descarga de modelos entre peers** — bajar el modelo de otro dispositivo en vez de un servidor central

Todo eso va sobre internet, vía Hyperswarm. **No hay Bluetooth. No prometerlo en el README.**

---

## 5. Justificación de modelos

Requisito de entrega, y lo primero que pregunta cualquiera que mire el repo.

### Qwen3-1.7B (extracción y redacción)

1. **Es constante del SDK** (`QWEN3_1_7B_INST_Q4`). Descarga y carga sin fricción, sin elegir cuantización ni pelear con rutas. Menos superficie de fallo en 24 horas.
2. **Entra con margen en 4 GB.** ~1,2 GB deja lugar para OCR, embeddings y sistema. Un 4B come el techo entero.
3. **El track premia modelos chicos en tareas difíciles.** Usar el más grande que entrara sería jugar en contra del segundo premio.

### OCR_LATIN (ONNX) en vez de un multimodal

El argumento no es la RAM: es el **`confidence` por bloque**.

El OCR de QVAC devuelve confianza por bloque de texto. Un VLM devuelve texto y punto. Sin esa señal no se puede distinguir *"contradicción real en el documento"* de *"el OCR leyó mal"* — y esa distinción es la que sostiene toda la clasificación FIRME / CON RESERVAS.

**Elegir el multimodal costaría la métrica principal.**

### Cómo escribirlo sin caer en AI slop

Separar argumento de evidencia:

> **Por qué este modelo:** constante del SDK, entra en 4 GB con margen, y el track premia modelos chicos en tareas difíciles.
>
> **Cómo rindió:** [número real, después del Hito 1]

Escribir "rinde bien en español" sin haberlo medido es exactamente lo que el jurado descarta: un README describiendo capacidades no probadas.

**Si sobra media hora:** correr los mismos 5 casos con `QWEN3_600M_INST_Q4` y con el 1.7B. Dos filas de tabla, y la justificación pasa de argumento a medición.

---

## 6. Deuda técnica declarada

### Hito 1 sigue abierto

**Nunca se corrió una inferencia real.** Bloqueado por: IP del servidor y `QVAC_BRIDGE_TOKEN`.

Esto es lo único que importa. Todo lo demás está escrito esperando esto.

### `riesgo/llm.py` está escrito pero nunca se ejecutó

Compila, pero no corrió. Viola la regla 12.5 del SDD original: *"nada de código generado que no haya corrido"*.

No es un problema todavía — es código contra una interfaz aún no probada. **Se vuelve problema si llega el domingo sin ejecutarse.**

**Protocolo para la primera corrida.** No arrancar con un caso completo:

1. Una inferencia pelada, sin pipeline
2. Verificar que `generationParams` llegue de verdad (que el `temp: 0` tenga efecto: misma entrada, misma salida, dos veces)
3. Verificar que `response_format` devuelva JSON válido
4. **Recién ahí** enchufar al pipeline

Si se salta esto y algo falla, no se sabe si el problema está en el prompt, en el bridge o en el pipeline.

---

## 7. Umbrales pendientes

| Umbral | Estado | Cómo se resuelve |
|---|---|---|
| Nombres | **0.85, fijado** | calibrado contra ground truth |
| Grounding numérico | **exacto, fijado** | fuzzy no sirve para números |
| Confianza de OCR | **sin fijar** | mirar la distribución real sobre los 6 escaneados cuando el OCR esté andando |
| Corte de descubierto | **$1M, por decisión** | no calibrable (ver sección 1). Documentar y defender |
| Tolerancia de puntualidad | **5 días, por decisión** | política, no estadística |

---

## 8. Orden de lo que queda

```
1. IP + token (o clave publica del provider)   ← bloqueante absoluto
2. ~~Verificar delegate en Python SDK~~        ✔ hecho, existe (ver seccion 3)
3. Inferencia pelada + temp:0 verificado       ← riesgo/hito1.py, pasos 1 y 2
4. response_format devolviendo JSON            ← riesgo/hito1.py, paso 3
5. Enchufar riesgo/llm.py al pipeline
6. Primer caso completo
7. Los 20 casos con precisión sobre FIRMES
```

Los pasos 3 y 4 ya están codificados en `riesgo/hito1.py`, que corre el protocolo
de la sección 6 entero y falla con un mensaje distinto en cada paso. Con provider:

```bash
# en el server
QVAC_HYPERSWARM_SEED=<64 hex> python -m riesgo.provider --permitir <clave_consumer>

# en la laptop
.venv/Scripts/python -m riesgo.hito1 --provider <clave_provider>
```

Del 3 en adelante, cada paso valida el anterior. Saltarse uno significa no saber dónde está el problema cuando aparezca.

---

## 9. Cambio de modelos — consecuencia para el índice vectorial

`.env.example` y el bridge pasaron de `GTE_LARGE_FP16` a `EMBEDDINGGEMMA_300M_Q4_0`.
Buena decisión por RAM, pero arrastra algo que no es obvio y que rompe en silencio:

**Cambiar el modelo de embeddings invalida todo lo que ya está indexado.** No son
vectores comparables aunque tuvieran el mismo largo, y la búsqueda no falla con un
error prolijo: devuelve resultados sin sentido, que en una demo es peor.

`toolkit/qvac_brain/README.md` ya lo documenta. Hay que correr `./scripts/ingest.sh`
después del cambio — `db.py` arma la columna `VECTOR(N)` desde `dim()`, así que se
adapta solo al nuevo tamaño.

Esto afecta al chatbot RAG, no al motor de riesgo, que no usa embeddings.
