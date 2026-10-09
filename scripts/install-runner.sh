#!/usr/bin/env bash
# Install (or upgrade) a remote Anvil runner on this test host as a systemd service.
#
# Run as root ON THE TEST HOST from an Anvil checkout:
#
#   sudo ./scripts/install-runner.sh [--port 9470] [--wheelhouse DIR]
#
#   --port N          TCP port to listen on (default 9470)
#   --bind ADDR       address to bind (default 0.0.0.0)
#   --wheelhouse DIR  install Python packages offline from DIR (no PyPI access);
#                     build it on a machine with internet using the same Python:
#                       pip wheel ./runner setuptools wheel -w wheelhouse/
#   --no-apt          skip installing fio/nvme-cli/smartmontools/... via apt
#
# Idempotent: re-running upgrades the runner code but keeps the token and the
# TLS certificate, so the registration on the Anvil server stays valid.
#
# At the end it prints the address, token and certificate fingerprint to enter
# in Anvil → Runners → Add runner.
set -euo pipefail

PORT=9470
BIND=0.0.0.0
WHEELHOUSE=""
DO_APT=1
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --bind) BIND="$2"; shift 2 ;;
    --wheelhouse) WHEELHOUSE="$(cd "$2" && pwd)"; shift 2 ;;
    --no-apt) DO_APT=0; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root (sudo)" >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX=/opt/anvil-runner
CONF=/etc/anvil-runner

if [ "$DO_APT" -eq 1 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq fio nvme-cli smartmontools pciutils util-linux hdparm \
    python3 python3-venv openssl ca-certificates >/dev/null
fi
for bin in fio nvme smartctl lsblk python3 openssl; do
  command -v "$bin" >/dev/null || { echo "missing required tool: $bin" >&2; exit 1; }
done

echo ">> installing runner into $PREFIX"
[ -x "$PREFIX/bin/python" ] || python3 -m venv "$PREFIX"
if [ -n "$WHEELHOUSE" ]; then
  "$PREFIX/bin/pip" install -q --no-index --find-links "$WHEELHOUSE" --upgrade setuptools wheel
  "$PREFIX/bin/pip" install -q --no-index --find-links "$WHEELHOUSE" --no-build-isolation \
    --upgrade "$REPO_DIR/runner"
else
  "$PREFIX/bin/pip" install -q --upgrade pip
  "$PREFIX/bin/pip" install -q --upgrade "$REPO_DIR/runner"
fi

install -d -m 0700 "$CONF"
if [ ! -s "$CONF/token" ]; then
  echo ">> generating token"
  (umask 077; openssl rand -hex 32 > "$CONF/token")
fi
if [ ! -s "$CONF/tls.crt" ] || [ ! -s "$CONF/tls.key" ]; then
  echo ">> generating self-signed TLS certificate"
  HOST_FQDN="$(hostname -f 2>/dev/null || hostname)"
  SAN="DNS:$(hostname),DNS:${HOST_FQDN}"
  for ip in $(hostname -I 2>/dev/null); do
    case "$ip" in *:*) ;; *) SAN="$SAN,IP:$ip" ;; esac
  done
  (umask 077; openssl req -x509 -newkey rsa:3072 -nodes -days 3650 \
    -subj "/CN=anvil-runner ${HOST_FQDN}" -addext "subjectAltName=${SAN}" \
    -keyout "$CONF/tls.key" -out "$CONF/tls.crt" 2>/dev/null)
fi
if [ ! -f "$CONF/runner.env" ]; then
  echo "ANVIL_RUNNER_LISTEN=${BIND}:${PORT}" > "$CONF/runner.env"
else
  sed -i "s|^ANVIL_RUNNER_LISTEN=.*|ANVIL_RUNNER_LISTEN=${BIND}:${PORT}|" "$CONF/runner.env"
fi

install -m 0644 "$REPO_DIR/deploy/systemd/anvil-runner.service" /etc/systemd/system/anvil-runner.service
systemctl daemon-reload
systemctl enable -q anvil-runner.service
systemctl restart anvil-runner.service
sleep 2
if ! systemctl is-active -q anvil-runner.service; then
  journalctl -u anvil-runner.service -n 30 --no-pager >&2
  echo "anvil-runner failed to start" >&2
  exit 1
fi

FP="$(openssl x509 -in "$CONF/tls.crt" -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f')"
ADDR_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
cat <<EOF

Anvil runner is running ($("$PREFIX/bin/anvil-runner" --help >/dev/null 2>&1 && echo ok)).
Register it in Anvil → Runners → Add runner:

  Address:          ${ADDR_IP:-<this-host>}:${PORT}
  Token:            $(cat "$CONF/token")
  TLS fingerprint:  ${FP}

Only the Anvil server needs to reach TCP ${PORT} on this host; restrict it with
your firewall if the network is shared.
EOF
