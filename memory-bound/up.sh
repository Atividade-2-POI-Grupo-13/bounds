#!/usr/bin/env bash
# Sobe a aplicacao memory-bound (rotas) e o monitor da VM e espera o /health.
# Uso (dentro da VM): sudo ~/memory-bound/up.sh
#
# So uma aplicacao do grupo deve rodar por vez durante as medicoes: antes,
# derrube as outras (sudo ~/<aplicacao>/down.sh).
set -euo pipefail

systemctl start rotas rotas-monitor
# O mapa da Paraiba leva alguns segundos para carregar.
for _ in $(seq 120); do
    if HEALTH=$(curl -fs -m 2 localhost:8000/health); then
        echo "memory-bound no ar: $HEALTH"
        exit 0
    fi
    sleep 1
done
echo "A aplicacao nao respondeu em 2 minutos. Veja: journalctl -u rotas -n 30"
exit 1
