#!/usr/bin/env bash
#
# Provisioning del bridge en un server que YA CORRE OTRA COSA.
#
# Uso:
#   ssh -i ~/.ssh/id_hetzner root@<IP> 'bash -s' < scripts/qvac/provision-compartido.sh
#
# Diferencias con provision.sh (que es para una caja dedicada) — todas por la
# misma razón: acá hay producción corriendo y no se toca nada que la afecte.
#
#   - NO toca ufw. Si el firewall está inactivo y lo activáramos dejando sólo
#     SSH, se caerían los puertos que publica Docker (80, 443, 8000...).
#   - NO usa apt. Node se instala desde el tarball oficial a /opt/node22, así
#     no se modifican fuentes ni paquetes del sistema.
#   - NO crea swap. Si ya hay, se respeta.
#   - El servicio arranca con tope de memoria duro y con prioridad de OOM
#     invertida: ante presión de RAM el kernel mata ESTE proceso, no el resto.
set -euo pipefail

NODE_V=v22.20.0
DIR_NODE=/opt/node22
DIR_APP=/opt/qvac-bridge
USUARIO=qvac
ARCHIVO_ENV=/etc/qvac-bridge.env

log() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "correlo como root"; exit 1; }

# --- presupuesto de memoria ---------------------------------------------------
# El tope se calcula sobre lo que hay disponible AHORA, dejando un colchón para
# que producción respire. No es una sugerencia: systemd lo aplica como límite.
DISPONIBLE_MB=$(free -m | awk '/^Mem:/{print $7}')
COLCHON_MB=400
TOPE_MB=$(( DISPONIBLE_MB - COLCHON_MB ))

log "RAM disponible: ${DISPONIBLE_MB} MB — tope para el bridge: ${TOPE_MB} MB"
if [ "$TOPE_MB" -lt 800 ]; then
  echo "Con ${TOPE_MB} MB no entra ni el modelo más chico. Liberá memoria o usá otra caja." >&2
  exit 1
fi

# --- node sin apt -------------------------------------------------------------
if [ -x "$DIR_NODE/bin/node" ]; then
  log "Node ya presente: $($DIR_NODE/bin/node -v)"
else
  log "instalando Node ${NODE_V} en ${DIR_NODE} (sin apt, sin tocar el sistema)"
  mkdir -p "$DIR_NODE"
  curl -fsSL "https://nodejs.org/dist/${NODE_V}/node-${NODE_V}-linux-x64.tar.xz" -o /tmp/node.tar.xz
  tar -xJf /tmp/node.tar.xz -C "$DIR_NODE" --strip-components=1
  rm -f /tmp/node.tar.xz
  log "Node instalado: $($DIR_NODE/bin/node -v)"
fi

# --- usuario ------------------------------------------------------------------
if ! id "$USUARIO" >/dev/null 2>&1; then
  log "creando usuario ${USUARIO}"
  useradd --system --create-home --home-dir "$DIR_APP" --shell /usr/sbin/nologin "$USUARIO"
fi
mkdir -p "$DIR_APP/models"
chown -R "$USUARIO:$USUARIO" "$DIR_APP"

# --- entorno ------------------------------------------------------------------
if [ ! -f "$ARCHIVO_ENV" ]; then
  log "generando token del bridge"
  TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)
  cat > "$ARCHIVO_ENV" <<ENVEOF
QVAC_BRIDGE_HOST=127.0.0.1
QVAC_BRIDGE_PORT=8081
QVAC_BRIDGE_TOKEN=${TOKEN}
QVAC_LLM_MODEL=https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
QVAC_EMBED_MODEL=GTE_LARGE_FP16
HOME=${DIR_APP}
QVAC_CONFIG_PATH=${DIR_APP}/models
ENVEOF
  chmod 600 "$ARCHIVO_ENV"
else
  log "${ARCHIVO_ENV} ya existe, conservo el token"
fi

# --- systemd, con los frenos --------------------------------------------------
log "instalando el servicio con tope de ${TOPE_MB} MB"
cat > /etc/systemd/system/qvac-bridge.service <<UNITEOF
[Unit]
Description=QVAC bridge HTTP (convive con produccion - recursos acotados)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USUARIO}
Group=${USUARIO}
WorkingDirectory=${DIR_APP}
EnvironmentFile=${ARCHIVO_ENV}
ExecStart=${DIR_NODE}/bin/node ${DIR_APP}/server.mjs

# --- LOS FRENOS ---
# MemoryMax es un limite duro: si el bridge lo supera, el kernel lo mata a EL.
# Sin esto, la presion de memoria la pagaria cualquier proceso, incluido Postgres.
MemoryMax=${TOPE_MB}M
MemoryHigh=$(( TOPE_MB - 200 ))M
# 1000 = "matame primero". Produccion queda con prioridad normal (0).
OOMScoreAdjust=1000
# Peso de CPU bajo: si compite con la app del hostel, pierde el bridge.
CPUWeight=20
IOWeight=20

TimeoutStartSec=1800
TimeoutStopSec=60
Restart=on-failure
RestartSec=15

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${DIR_APP}

StandardOutput=journal
StandardError=journal
SyslogIdentifier=qvac-bridge

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
log "provisioning listo (firewall y paquetes del sistema: intactos)"
echo
grep QVAC_BRIDGE_TOKEN "$ARCHIVO_ENV"
echo
echo "Tope de memoria aplicado: ${TOPE_MB} MB"
