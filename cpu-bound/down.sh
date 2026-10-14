#!/usr/bin/env bash
# Derruba a aplicacao CPU-bound na VM.
# Uso (dentro da VM): sudo ~/cpu-bound/down.sh
set -euo pipefail

systemctl stop app-cpu
echo "cpu-bound parada."
