#!/usr/bin/env bash
# Sobe a aplicacao CPU-bound na VM e espera ela responder.
# Uso (dentro da VM): sudo ~/cpu-bound/up.sh
#
# So uma aplicacao do grupo deve rodar por vez durante as medicoes: antes,
# derrube as outras (sudo ~/<aplicacao>/down.sh).
set -euo pipefail

systemctl start app-cpu
for _ in $(seq 60); do
    if HEALTH=$(curl -fs -m 2 localhost:8080/health); then
        echo "cpu-bound no ar: $HEALTH"
        exit 0
    fi
    sleep 2
done
echo "A aplicacao nao respondeu em 2 minutos. Veja: journalctl -u app-cpu -n 30"
exit 1
