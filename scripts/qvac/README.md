# Correr QVAC en un server propio

Levanta un modelo local de QVAC en un server Linux y lo expone por HTTP para
que la app Python de este repo lo use en lugar de Anthropic y Gemini. El
objetivo es sacar las llamadas a APIs externas del camino crítico: la
inferencia pasa a correr en hardware que controlás vos.

El motor de inferencia de QVAC es Node, y la app es Python, así que en el medio
hay un bridge HTTP (`bridge/server.mjs`).

> **Existe también un SDK Python oficial** (`pip install tetherto-qvac-sdk -f
> https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.17.0`), pero
> es un cliente delgado que levanta y administra el mismo worker Node por
> debajo: necesita Node ≥22.17 y `npm install -g @qvac/sdk` en la máquina donde
> corre. El bridge sigue siendo la opción correcta cuando el modelo vive en un
> server aparte y no querés el worker en cada máquina del equipo.

## Antes de empezar

Necesitás un server **dedicado a esto**. No lo instales en una caja que ya
corra algo que te importe: cargar un modelo tiene un pico de RAM alto y el
OOM-killer no distingue entre tu experimento y tu producción.

| Requisito | Mínimo | Recomendado |
|---|---|---|
| RAM | 4 GB | 8 GB (CX32) |
| Disco libre | 5 GB | 20 GB |
| CPU | 2 vCPU | 4 vCPU |
| OS | Ubuntu 22.04+ x64 | Ubuntu 24.04 |
| GPU | no hace falta | acelera, pero en Linux hay fallback a CPU |

Sin GPU la inferencia anda, pero lenta. Es aceptable para desarrollo; medí
antes de prometer tiempos en una demo.

## Quick path

```bash
# 1. Provisioning: Node 22, usuario, swap, firewall, token
ssh -i ~/.ssh/id_hetzner root@<IP> 'bash -s' < scripts/qvac/provision.sh

# 2. Subir el bridge e instalarlo como servicio
./scripts/qvac/deploy.sh <IP>

# 3. Túnel SSH — dejalo abierto en otra terminal
./scripts/qvac/tunnel.sh <IP>

# 4. Verificar de punta a punta
python scripts/qvac/smoke_test.py
```

El paso 1 imprime el `QVAC_BRIDGE_TOKEN`. Copiálo a tu `.env` antes de seguir.

La primera corrida del paso 4 descarga los modelos (cientos de MB) y puede
tardar varios minutos. Las siguientes arrancan en segundos.

## Qué hace cada script

| Script | Dónde corre | Qué hace |
|---|---|---|
| `provision.sh` | en el server, una vez | Node 22, usuario `qvac`, swap de 4 GB, `ufw` solo SSH, genera el token en `/etc/qvac-bridge.env` |
| `deploy.sh` | desde tu máquina | rsync del bridge, `npm install`, instala y reinicia el servicio systemd, sondea `/health` |
| `tunnel.sh` | desde tu máquina | túnel SSH `127.0.0.1:8081` → server |
| `smoke_test.py` | desde tu máquina | health, generación, embeddings y estabilidad de dimensión |

## Decisiones de diseño

| Tema | Decisión y por qué |
|---|---|
| Bind en loopback | El bridge escucha en `127.0.0.1`, no en `0.0.0.0`. El acceso entra por túnel SSH — mismo patrón que ya usás para Coolify. Un puerto de inferencia abierto a internet es CPU gratis para cualquiera. |
| Inferencia serializada | El bridge encola las requests. En pocos vCPU sin GPU, dos completions en paralelo no van más rápido: compiten por los mismos cores y duplican el pico de RAM. |
| Modelos cacheados en memoria | Cargar cuesta minutos; se hace una vez por modelo y queda residente. |
| Swap de 4 GB | La carga del modelo tiene un pico mayor al estado estable. Con swap ese pico es lento; sin swap es un OOM-kill. |
| `--omit=dev` en deploy | Los addons nativos ya vienen precompilados en el paquete; no hace falta el toolchain de desarrollo en el server. |

## Endpoints

| Ruta | Body | Devuelve |
|---|---|---|
| `GET /health` | — | `{ok, llm, embed, cargados}` — sin auth, para chequear el túnel |
| `GET /v1/models` | — | modelos configurados + `getSystemResources()` |
| `POST /v1/completion` | `{messages, system?, model?, max_tokens?, temperature?, top_p?, seed?, generation_params?, response_format?}` | `{texto, stop_reason, stats}` |
| `POST /v1/embeddings` | `{text}` o `{texts: [...]}` | `{embeddings, dim}` |

Todo menos `/health` pide `Authorization: Bearer <QVAC_BRIDGE_TOKEN>`.

## Configuración

`/etc/qvac-bridge.env` en el server (lo crea `provision.sh`):

| Variable | Default | Para qué |
|---|---|---|
| `QVAC_BRIDGE_HOST` | `127.0.0.1` | Cambialo solo si sabés lo que estás haciendo |
| `QVAC_BRIDGE_PORT` | `8081` | |
| `QVAC_BRIDGE_TOKEN` | generado | Debe coincidir con el de tu `.env` |
| `QVAC_LLM_MODEL` | Qwen2.5-3B-Instruct Q4_K_M (URL) | Constante del SDK **o** URL a un `.gguf` |
| `QVAC_EMBED_MODEL` | `GTE_LARGE_FP16` | 1024 dimensiones |

Modelos según cuánta RAM tengas.

**Los pesos en disco no son la RAM que vas a usar.** A los pesos hay que sumarle
el KV cache, el contexto y el overhead del runtime. Y el bridge tiene el LLM y
el modelo de embeddings cargados **al mismo tiempo**, así que el presupuesto
real es la suma de los dos más el sistema.

| Modelo | Pesos en disco | RAM estimada en uso |
|---|---|---|
| `QWEN3_600M_INST_Q4` | ~0.4 GB | ~1 GB |
| `LLAMA_3_2_1B_INST_Q4_0` | ~0.8 GB | ~1.5 GB |
| `QWEN3_1_7B_INST_Q4` | ~1.2 GB | ~2 GB |
| **Qwen2.5-3B-Instruct Q4_K_M** (default) | **2.10 GB** | ~2.6 GB |
| `QWEN3_4B_Q4_K_M` | ~2.6 GB | ~3.5-4 GB |
| `GTE_LARGE_FP16` (embeddings) | ~0.7 GB | ~1 GB |

El default no es una constante del SDK sino una URL de HuggingFace — el SDK
trae Qwen3, no Qwen2.5. `modelSrc` acepta las dos formas, así que da igual:

```
https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```

Los 2.10 GB son el `content-length` real de ese archivo, no una estimación.

Los pesos de 4B y 1.7B en Q4_K_M salen de la propia página de modelos de QVAC
(2.6 GB y 1.2 GB para MedPsy-4B / MedPsy-1.7B, misma familia y cuantización).
La columna de RAM es estimada: la única forma de saberlo exacto es medir con
`smoke_test.py` y mirar `free -h` con el modelo cargado.

Presupuesto sumando LLM + embeddings + sistema:

| Caja | RAM | 3B + GTE (default) | 4B + GTE |
|---|---|---|---|
| CX22 | 4 GB | ~4.3 GB — **no entra** | no entra |
| CX32 | 8 GB | ~4.3 GB — cómodo, ~3.7 GB libres | ~5 GB — entra bien |

Con el 3B seguís necesitando el CX32: el modelo solo entraría en 4 GB, pero el
de embeddings queda cargado en paralelo y el sistema también come. Los 3.7 GB
que sobran en el CX32 son el margen para subir a 4B más adelante sin migrar.

Si ponés un nombre que no existe, el bridge responde 400 con la lista completa
de constantes que exporta el SDK.

## Diagnóstico

```bash
# Logs del servicio
ssh -i ~/.ssh/id_hetzner root@<IP> 'journalctl -u qvac-bridge -f'

# Estado y consumo de RAM
ssh -i ~/.ssh/id_hetzner root@<IP> 'systemctl status qvac-bridge; free -h'
```

| Síntoma | Causa habitual |
|---|---|
| `no se pudo contactar al bridge` | El túnel se cayó. Reabrí `tunnel.sh`. |
| 401 en todo menos `/health` | El token del `.env` no coincide con el de `/etc/qvac-bridge.env`. |
| El servicio reinicia en loop | Casi siempre OOM. Mirá `journalctl -k \| grep -i oom` y bajá a un modelo más chico. |
| La primera request tarda muchísimo | Es la descarga del modelo. Seguila con `journalctl -u qvac-bridge -f`. |

## Checklist

- [ ] El server es dedicado, no comparte caja con producción
- [ ] `provision.sh` corrió y me guardé el `QVAC_BRIDGE_TOKEN`
- [ ] `deploy.sh` terminó con "bridge arriba"
- [ ] El túnel está abierto en una terminal aparte
- [ ] `smoke_test.py` pasa los 4 pasos
- [ ] Puse `EMBEDDING_DIM` en el `.env` con el valor que imprimió el smoke test

## Siguiente paso

Con el bridge andando, cambiá la app para que lo use:
[`toolkit/qvac_brain/README.md`](../../toolkit/qvac_brain/README.md).

## Parámetros de generación

⚠️ El contrato de wire de `completionStream` **no** acepta `temperature` ni
`maxTokens` como claves de primer nivel. Van adentro de `generationParams`, y
la temperatura se llama **`temp`**:

```json
{ "generationParams": { "temp": 0, "top_p": 1, "seed": 7, "predict": 512 } }
```

Una clave desconocida se descarta **en silencio**. Si mandás `temperature` a
secas, la inferencia corre con sampling por defecto y el mismo documento
devuelve números distintos en cada corrida, sin ningún error que lo delate.

El bridge acepta las dos formas: traduce `temperature`/`max_tokens` del body a
`temp`/`predict`, y deja pasar un `generation_params` explícito si preferís
armarlo vos.

### JSON garantizado, no pedido

`response_format` con `json_schema` se convierte a una gramática GBNF nativa de
llama.cpp. El decoder queda restringido: no puede emitir backticks, ni JSON
truncado, ni `"no encontrado"` donde el schema declara `number | null`.

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "campos_contrato",
      "strict": true,
      "schema": { "type": "object", "properties": { "...": {} },
                  "required": ["..."], "additionalProperties": false }
    }
  }
}
```

Para extracción estructurada esto no es un detalle: es la diferencia entre
parsear con reintentos y no tener que parsear defensivamente.
