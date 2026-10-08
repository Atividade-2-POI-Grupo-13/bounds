#!/usr/bin/env bash
# Plano B quando a VM não tem ssh (sem scp): o hospedeiro serve o projeto por HTTP
# e a VM baixa pela rede NAT do VirtualBox, onde o hospedeiro é 10.0.2.2.
# Roda no hospedeiro, a partir da pasta do projeto. Ctrl+C para parar depois do download.
set -euo pipefail
cd "$(dirname "$0")/.."
PORTA="${PORTA:-8099}"
pasta_tmp="$(mktemp -d)"
tar --exclude .venv --exclude .pacotes --exclude cache --exclude results --exclude .git \
  --exclude __pycache__ -czf "$pasta_tmp/projeto.tgz" -C .. "$(basename "$PWD")"
echo "Digite no console da VM:"
echo
echo "  curl -s http://10.0.2.2:$PORTA/projeto.tgz | tar -xz && cd $(basename "$PWD") && ./deploy/install.sh"
echo
cd "$pasta_tmp"
python3 -m http.server "$PORTA"
