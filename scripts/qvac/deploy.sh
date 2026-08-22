#!/usr/bin/env bash
#
# Sube el bridge al server, instala dependencias y lo reinicia.
#
# Uso:
#   ./scripts/qvac/deploy.sh <IP> [ruta-a-la-key]
#
# Corré primero provision.sh — este script asume que Node, el usuario `qvac`
# y /etc/qvac-bridge.env ya existen.
set -euo pipefail

IP="${1:-}"
KEY="${2:-$HOME/.ssh/id_hetzner}"
DIR_APP=/opt/qvac-bridge
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ -n "$IP" ] || { echo "uso: $0 <IP> [ruta-a-la-key]"; exit 1; }
[ -f "$KEY" ] || { echo "no encuentro la key en $KEY"; exit 1; }

SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "root@${IP}")

log() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }

log "subiendo el bridge a ${IP}"
# Sin --delete: node_modules vive en el destino y borrarlo obligaría a
# recompilar los addons nativos en cada deploy (varios minutos).
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  "$AQUI/bridge/server.mjs" "$AQUI/bridge/package.json" \
  "root@${IP}:${DIR_APP}/"

log "instalando la unit de systemd"
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  "$AQUI/qvac-bridge.service" "root@${IP}:/etc/systemd/system/qvac-bridge.service"

log "npm install (compila addons nativos, puede tardar)"
"${SSH[@]}" "cd ${DIR_APP} && npm install --omit=dev --no-audit --no-fund && chown -R qvac:qvac ${DIR_APP}"

log "reiniciando el servicio"
"${SSH[@]}" "systemctl daemon-reload && systemctl enable --now qvac-bridge && systemctl restart qvac-bridge"

log "esperando a que levante"
# El primer arranque descarga los modelos: puede tardar minutos. Sondeamos
# /health en vez de dormir un número fijo y esperar que alcance.
for i in $(seq 1 60); do
  if "${SSH[@]}" "curl -sf http://127.0.0.1:8081/health" 2>/dev/null; then
    echo
    log "bridge arriba"
    exit 0
  fi
  sleep 5
done

echo
echo "el bridge no respondió a /health en 5 minutos. Últimos logs:" >&2
"${SSH[@]}" "journalctl -u qvac-bridge -n 40 --no-pager" >&2
exit 1
