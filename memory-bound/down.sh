#!/usr/bin/env bash
# Derruba a aplicacao memory-bound (rotas) e o monitor da VM.
# Uso (dentro da VM): sudo ~/memory-bound/down.sh
set -euo pipefail

systemctl stop rotas rotas-monitor
echo "memory-bound parada."
