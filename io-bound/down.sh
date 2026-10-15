#!/usr/bin/env bash
# Derruba os tres apps da io-bound, inclusive os que o experimento.sh deixou para tras.
# Uso (dentro da VM): sudo ~/io-bound/down.sh
set -euo pipefail

systemctl stop io-bound@buffer io-bound@produtor io-bound@consumidor 2> /dev/null || true
pkill -f 'io-bound/.*/target/.*-0.1.0.jar' 2> /dev/null || true
pkill -f -- '-jar (buffer|produtor|consumidor)/target/' 2> /dev/null || true
echo "io-bound parada."
