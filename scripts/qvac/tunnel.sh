#!/usr/bin/env bash
#
# Abre el túnel SSH al bridge de QVAC.
#
# Uso:
#   ./scripts/qvac/tunnel.sh <IP> [ruta-a-la-key]
#
# Dejalo corriendo en una terminal aparte. Mientras esté abierto, la app ve el
# bridge en http://127.0.0.1:8081 como si fuera local.
#
# El bridge escucha solo en loopback del server: sin este túnel no hay forma de
# llegarle desde afuera, que es exactamente la idea.
set -euo pipefail

IP="${1:-}"
KEY="${2:-$HOME/.ssh/id_hetzner}"
PUERTO=8081

[ -n "$IP" ] || { echo "uso: $0 <IP> [ruta-a-la-key]"; exit 1; }

echo "▸ túnel 127.0.0.1:${PUERTO} -> ${IP}:${PUERTO}  (Ctrl-C para cerrar)"

# ExitOnForwardFailure evita el caso confuso de un túnel "abierto" que en
# realidad no reenvía nada porque el puerto local ya estaba ocupado.
exec ssh -i "$KEY" -N \
  -o StrictHostKeyChecking=accept-new \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L "${PUERTO}:127.0.0.1:${PUERTO}" \
  "root@${IP}"
