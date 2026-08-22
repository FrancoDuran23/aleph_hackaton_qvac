/**
 * Bridge HTTP sobre el SDK de QVAC.
 *
 * El SDK de QVAC es Node y la app de este repo es Python, así que no hay forma
 * de llamarlo in-process. Este servicio carga los modelos una sola vez y los
 * expone por HTTP para que `toolkit/qvac_brain` los consuma desde Python.
 *
 * Escucha en 127.0.0.1 por defecto: el acceso desde afuera va por túnel SSH,
 * igual que el panel de Coolify. No lo expongas a internet sin repensar la auth.
 */
import { createServer } from 'node:http'
import { timingSafeEqual } from 'node:crypto'
import * as qvac from '@qvac/sdk'

const HOST = process.env.QVAC_BRIDGE_HOST || '127.0.0.1'
const PORT = Number(process.env.QVAC_BRIDGE_PORT || 8081)
const TOKEN = process.env.QVAC_BRIDGE_TOKEN || ''
const LLM_MODEL = process.env.QVAC_LLM_MODEL || 'QWEN3_1_7B_INST_Q4'
const EMBED_MODEL = process.env.QVAC_EMBED_MODEL || 'EMBEDDINGGEMMA_300M_Q4_0'
const MAX_BODY_BYTES = 8 * 1024 * 1024

/** Los modelos se cachean por nombre de constante: cargar cuesta minutos. */
const cargados = new Map()

/** ¿Es una fuente "pelada" (URL/ruta) en vez de una constante del SDK? */
function esFuenteDirecta (nombre) {
  return /^(https?:|pear:|file:|\.{0,2}\/)/.test(nombre)
}

/**
 * Resuelve el modelo a cargar.
 *
 * `loadModel` acepta tres formas de `modelSrc`, y las tres pasan por acá:
 *
 *   1. Una constante del SDK       -> 'EMBEDDINGGEMMA_300M_Q4_0'
 *   2. Un GGUF por URL o ruta      -> 'https://huggingface.co/.../modelo.gguf'
 *   3. Una key de Hyperdrive       -> 'pear://<key>/modelo.gguf'
 *
 * Las constantes son sólo atajos a modelos curados; no son un catálogo cerrado.
 * Cualquier GGUF compatible con llama.cpp sirve — el límite es la RAM, no QVAC.
 *
 * Las constantes salen de un `export *`, así que no están en el .d.ts y un
 * nombre mal escrito daría `undefined` y un error opaco al cargar. Por eso
 * fallamos temprano y listamos las disponibles.
 */
function resolverModelo (nombre) {
  // URL, ruta o hyperdrive: va tal cual al SDK.
  if (esFuenteDirecta(nombre)) return nombre

  const src = qvac[nombre]
  if (src === undefined) {
    const disponibles = Object.keys(qvac)
      .filter((k) => /^[A-Z][A-Z0-9_]{3,}$/.test(k))
      .sort()
    throw new Error(
      `Modelo desconocido "${nombre}". Pasá una URL/ruta a un .gguf, o una de estas constantes de @qvac/sdk:\n  ${disponibles.join('\n  ')}`
    )
  }
  return src
}

/** Nombre corto para los logs: una URL de HuggingFace ocupa media línea. */
function nombreCorto (nombre) {
  return nombre.includes('/') ? nombre.split('/').pop() : nombre
}

/**
 * Carga un modelo y cachea su id.
 *
 * `tipo` es el `modelType` canónico del SDK ('llamacpp-completion' para
 * generación, 'llamacpp-embedding' para embeddings). Sólo se manda cuando la
 * fuente es una URL o ruta: las constantes del SDK ya traen la metadata del
 * engine adentro, pero un string pelado no, y el SDK falla con
 * MODEL_TYPE_REQUIRED si no se lo decís.
 */
async function obtenerModelo (nombre, tipo) {
  const cacheado = cargados.get(nombre)
  if (cacheado) return cacheado

  // Guardamos la promesa, no el id: dos requests simultáneos durante la carga
  // inicial tienen que esperar la misma descarga en vez de arrancar dos.
  const promesa = (async () => {
    const inicio = Date.now()
    log(`cargando modelo ${nombreCorto(nombre)} (${tipo})...`)
    let ultimoPorcentaje = -1
    const modelId = await qvac.loadModel({
      modelSrc: resolverModelo(nombre),
      ...(esFuenteDirecta(nombre) ? { modelType: tipo } : {}),
      onProgress: (p) => {
        const pct = Math.floor(p.percentage ?? 0)
        if (pct >= ultimoPorcentaje + 10) {
          ultimoPorcentaje = pct
          log(`  ${nombreCorto(nombre)}: descargando ${pct}%`)
        }
      }
    })
    log(`modelo ${nombreCorto(nombre)} listo en ${((Date.now() - inicio) / 1000).toFixed(1)}s (id=${modelId})`)
    return modelId
  })()

  cargados.set(nombre, promesa)
  promesa.catch(() => cargados.delete(nombre)) // que un fallo no envenene el cache
  return promesa
}

/**
 * Serializa las inferencias.
 *
 * La caja es de pocos vCPU sin GPU: dos completions en paralelo no van el doble
 * de rápido, compiten por los mismos cores y multiplican el pico de RAM. Con
 * una cola el throughput es el mismo y el uso de memoria es predecible.
 */
let cola = Promise.resolve()
function enCola (fn) {
  const resultado = cola.then(fn, fn)
  cola = resultado.then(() => {}, () => {})
  return resultado
}

function log (msg) {
  console.log(`[qvac-bridge] ${msg}`)
}

function autorizado (req) {
  if (!TOKEN) return true // sin token configurado el bridge queda abierto en loopback
  const header = req.headers.authorization || ''
  const enviado = Buffer.from(header.replace(/^Bearer\s+/i, ''))
  const esperado = Buffer.from(TOKEN)
  return enviado.length === esperado.length && timingSafeEqual(enviado, esperado)
}

function leerJson (req) {
  return new Promise((resolve, reject) => {
    const trozos = []
    let total = 0
    req.on('data', (t) => {
      total += t.length
      if (total > MAX_BODY_BYTES) {
        reject(new Error('body demasiado grande'))
        req.destroy()
        return
      }
      trozos.push(t)
    })
    req.on('end', () => {
      if (total === 0) return resolve({})
      try {
        resolve(JSON.parse(Buffer.concat(trozos).toString('utf8')))
      } catch (e) {
        reject(new Error(`JSON inválido: ${e.message}`))
      }
    })
    req.on('error', reject)
  })
}

function responder (res, codigo, cuerpo) {
  const payload = JSON.stringify(cuerpo)
  res.writeHead(codigo, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(payload)
  })
  res.end(payload)
}

/**
 * Saca el bloque de razonamiento del texto visible.
 *
 * `captureThinking: true` hace que el SDK mande el razonamiento por
 * `thinkingText`, pero no todos los modelos lo emiten con el mismo formato y
 * alcanza con que uno se desvíe para que un `<think>` en inglés termine en la
 * respuesta al usuario. Esto es la red por si eso pasa; el caso normal ya
 * viene limpio y esta función no toca nada.
 *
 * Un `<think>` sin cerrar significa que la generación se cortó por límite de
 * tokens en medio del razonamiento: ahí no hay respuesta que rescatar, así que
 * devolvemos vacío y el cliente cae a su fallback.
 */
function limpiarPensamiento (texto) {
  return texto
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<think>[\s\S]*$/i, '')
    .trim()
}

/** Arma el `history` de QVAC a partir de un system prompt + mensajes. */
function armarHistory (body) {
  const mensajes = body.history || body.messages || []
  if (!Array.isArray(mensajes) || mensajes.length === 0) {
    throw new Error('se esperaba "messages" (o "history") con al menos un mensaje')
  }
  const history = mensajes.map((m) => ({
    role: m.role,
    content: typeof m.content === 'string'
      ? m.content
      // La app manda bloques estilo Anthropic en algunos caminos; los aplanamos.
      : (m.content ?? []).map((b) => b.text ?? '').join('')
  }))
  const system = body.system
  return system ? [{ role: 'system', content: system }, ...history] : history
}

const rutas = {
  'GET /health': async (_req, res) => {
    responder(res, 200, {
      ok: true,
      llm: LLM_MODEL,
      embed: EMBED_MODEL,
      cargados: [...cargados.keys()]
    })
  },

  'GET /v1/models': async (_req, res) => {
    const recursos = await qvac.getSystemResources({ sample: true }).catch((e) => ({ error: e.message }))
    responder(res, 200, { llm: LLM_MODEL, embed: EMBED_MODEL, cargados: [...cargados.keys()], recursos })
  },

  'POST /v1/completion': async (req, res) => {
    const body = await leerJson(req)
    const history = armarHistory(body)
    const modelId = await obtenerModelo(body.model || LLM_MODEL, 'llamacpp-completion')

    const final = await enCola(async () => {
      // `maxTokens` y `temperature` NO son claves del contrato de wire: el
      // payload real de completionStream lleva `generationParams` (con `temp`,
      // no `temperature`) y `responseFormat`. Una clave desconocida se
      // descarta en silencio, asi que la version anterior de este handler
      // corria siempre con sampling por defecto: el mismo documento devolvia
      // montos distintos en corridas distintas, sin ningun error visible.
      const generationParams = {
        ...(body.temperature !== undefined ? { temp: body.temperature } : {}),
        ...(body.top_p !== undefined ? { top_p: body.top_p } : {}),
        ...(body.seed !== undefined ? { seed: body.seed } : {}),
        ...(body.max_tokens ? { predict: body.max_tokens } : {}),
        ...(body.generation_params ?? {})
      }

      const run = qvac.completion({
        modelId,
        history,
        stream: false,
        // Los Qwen3 razonan antes de responder. Sin esto el bloque <think>...</think>
        // se cuela en contentText y termina en la cara del usuario; con esto el SDK
        // lo separa en thinkingText y contentText queda limpio.
        captureThinking: true,
        ...(Object.keys(generationParams).length ? { generationParams } : {}),
        // Con `json_schema`, llama.cpp lo convierte a una gramatica GBNF: el
        // decoder no puede emitir nada que viole el schema. Es la diferencia
        // entre pedir JSON y garantizarlo.
        ...(body.response_format ? { responseFormat: body.response_format } : {})
      })
      return run.final
    })

    responder(res, 200, {
      texto: limpiarPensamiento(final.contentText ?? ''),
      pensamiento: final.thinkingText ?? null,
      stop_reason: final.stopReason ?? null,
      stats: final.stats ?? null
    })
  },

  'POST /v1/embeddings': async (req, res) => {
    const body = await leerJson(req)
    // Aceptamos texto suelto o lote; el SDK devuelve number[] o number[][] según el input.
    const entrada = body.texts ?? body.text
    if (entrada === undefined) throw new Error('se esperaba "text" o "texts"')
    const esLote = Array.isArray(entrada)
    if (esLote && entrada.length === 0) return responder(res, 200, { embeddings: [], dim: 0 })

    const modelId = await obtenerModelo(body.model || EMBED_MODEL, 'llamacpp-embedding')
    const { embedding } = await enCola(() => qvac.embed({ modelId, text: entrada }))
    const embeddings = esLote ? embedding : [embedding]

    responder(res, 200, { embeddings, dim: embeddings[0]?.length ?? 0 })
  }
}

const servidor = createServer(async (req, res) => {
  const ruta = `${req.method} ${new URL(req.url, 'http://localhost').pathname}`
  const handler = rutas[ruta]

  if (!handler) return responder(res, 404, { error: `ruta desconocida: ${ruta}` })
  if (ruta !== 'GET /health' && !autorizado(req)) {
    return responder(res, 401, { error: 'token inválido o ausente' })
  }

  try {
    await handler(req, res)
  } catch (e) {
    log(`ERROR en ${ruta}: ${e.stack || e.message}`)
    if (!res.headersSent) responder(res, 500, { error: e.message })
  }
})

servidor.listen(PORT, HOST, () => {
  log(`escuchando en http://${HOST}:${PORT}`)
  log(`llm=${LLM_MODEL} embed=${EMBED_MODEL} auth=${TOKEN ? 'bearer' : 'SIN TOKEN'}`)
})

// systemd manda SIGTERM en `stop`/`restart`: liberamos los modelos antes de morir
// para no dejar la RAM tomada si el proceso tarda en bajar.
for (const senal of ['SIGTERM', 'SIGINT']) {
  process.on(senal, async () => {
    log(`${senal} recibida, descargando modelos...`)
    servidor.close()
    for (const [nombre, promesa] of cargados) {
      try {
        await qvac.unloadModel({ modelId: await promesa, clearStorage: false })
        log(`  ${nombreCorto(nombre)} descargado`)
      } catch (e) {
        log(`  no se pudo descargar ${nombreCorto(nombre)}: ${e.message}`)
      }
    }
    process.exit(0)
  })
}
