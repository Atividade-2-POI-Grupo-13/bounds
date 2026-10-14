#!/usr/bin/env bash
# Plano B quando a VM não tem ssh (sem scp): o hospedeiro serve o projeto por HTTP
# e a VM baixa pela rede NAT do VirtualBox, onde o hospedeiro é 10.0.2.2.
# Roda no hospedeiro, a partir da pasta do projeto. Ctrl+C para parar depois do download.
set -euo pipefail
cd "$(dirname "$0")/.."
PORTA="${PORTA:-8099}"
pasta_tmp="$(mktemp -d)"
# --no-xattrs: sem isso o tar do macOS enche o console da VM de avisos.
# *_full*: mapas grandes que a VM não usa.
tar --no-xattrs --exclude '*_full*' --exclude .venv --exclude .pacotes --exclude cache \
  --exclude results --exclude .git --exclude __pycache__ \
  -czf "$pasta_tmp/projeto.tgz" -C .. "$(basename "$PWD")"
# Comando curto para digitar no console da VM, onde não há colar nem o layout do teclado é garantido.
echo "curl -s http://10.0.2.2:$PORTA/projeto.tgz | tar -xz && cd $(basename "$PWD") && ./deploy/install.sh < /dev/null" > "$pasta_tmp/i"
echo "Digite no console da VM (a senha do sudo é osboxes.org):"
echo
echo "  curl -s 10.0.2.2:$PORTA/i | sh"
echo
cd "$pasta_tmp"
python3 -m http.server "$PORTA"
