#!/usr/bin/env bash
#
# Bootstrap del server que corre el bridge de QVAC.
#
# Idempotente: podés correrlo de nuevo sin romper nada.
#
# Uso (desde tu máquina):
#   ssh -i ~/.ssh/id_hetzner root@<IP> 'bash -s' < scripts/qvac/provision.sh
#
# Pensado para Ubuntu 22.04+ x64. NO lo corras en el server de producción:
# instala Node global, crea un usuario y toca ufw.
set -euo pipefail

NODE_MAJOR=22
DIR_APP=/opt/qvac-bridge
USUARIO=qvac
ARCHIVO_ENV=/etc/qvac-bridge.env

log() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }

# --- chequeos previos --------------------------------------------------------
[ "$(id -u)" -eq 0 ] || { echo "correlo como root"; exit 1; }

RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
log "RAM detectada: ${RAM_MB} MB"
if [ "$RAM_MB" -lt 3500 ]; then
  echo "AVISO: QVAC recomienda 4 GB+. Con ${RAM_MB} MB solo entran modelos muy chicos." >&2
fi

# --- paquetes base -----------------------------------------------------------
# g++ >= 13 y build-essential los pide el SDK para compilar/enlazar sus addons.
log "instalando paquetes base"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential g++ curl ca-certificates gnupg rsync ufw >/dev/null

# --- swap --------------------------------------------------------------------
# Cargar un modelo tiene un pico de memoria mayor al estado estable. Sin swap,
# ese pico es un OOM-kill; con swap es un momento lento y sigue de largo.
if ! swapon --show | grep -q .; then
  log "creando swap de 4G"
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
else
  log "swap ya presente, no toco nada"
fi

# --- node --------------------------------------------------------------------
# El SDK pide Node >= 22.17; el de los repos de Ubuntu suele ser más viejo.
if ! command -v node >/dev/null || [ "$(node -v | sed 's/v\([0-9]*\).*/\1/')" -lt "$NODE_MAJOR" ]; then
  log "instalando Node ${NODE_MAJOR}"
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi
log "node $(node -v) / npm $(npm -v)"

# --- usuario y directorios ---------------------------------------------------
# Usuario sin login: si algún día el bridge queda expuesto, no es una shell.
if ! id "$USUARIO" >/dev/null 2>&1; then
  log "creando usuario ${USUARIO}"
  useradd --system --create-home --home-dir "$DIR_APP" --shell /usr/sbin/nologin "$USUARIO"
fi
mkdir -p "$DIR_APP/models"
chown -R "$USUARIO:$USUARIO" "$DIR_APP"

# --- token de auth -----------------------------------------------------------
# Se genera una sola vez y queda en un archivo 600: si regenerara en cada corrida
# invalidaría el token que ya tenés configurado del lado del cliente.
if [ ! -f "$ARCHIVO_ENV" ]; then
  log "generando token del bridge"
  TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)
  cat > "$ARCHIVO_ENV" <<ENVEOF
QVAC_BRIDGE_HOST=127.0.0.1
QVAC_BRIDGE_PORT=8081
QVAC_BRIDGE_TOKEN=${TOKEN}
QVAC_LLM_MODEL=QWEN3_1_7B_INST_Q4
QVAC_EMBED_MODEL=EMBEDDINGGEMMA_300M_Q4_0
HOME=${DIR_APP}
QVAC_CACHE_DIR=${DIR_APP}/models
ENVEOF
  chmod 600 "$ARCHIVO_ENV"
else
  log "${ARCHIVO_ENV} ya existe, conservo el token"
fi

# --- firewall ----------------------------------------------------------------
# El bridge escucha en 127.0.0.1, así que no hace falta abrirle un puerto:
# el acceso desde afuera entra por el túnel SSH.
log "configurando ufw (solo SSH entrante)"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
ufw status | head -5

log "provisioning listo"
echo
echo "Token del bridge (guardalo, lo necesitás en tu .env):"
grep QVAC_BRIDGE_TOKEN "$ARCHIVO_ENV"
echo
echo "Siguiente paso, desde tu máquina:  ./scripts/qvac/deploy.sh <IP>"
