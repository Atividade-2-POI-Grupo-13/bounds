#!/usr/bin/env bash
# Sobe os tres apps da io-bound e espera o health de cada um.
# Uso (dentro da VM): sudo ~/io-bound/up.sh
#
# So uma aplicacao do grupo deve rodar por vez durante as medicoes: antes,
# derrube as outras (sudo ~/<aplicacao>/down.sh). Para medir, use o
# experimento.sh, que sobe os apps sozinho (rode antes este down.sh).
set -euo pipefail

systemctl start io-bound@buffer io-bound@produtor io-bound@consumidor
for porta in 8080 8081 8082; do
    for tentativa in $(seq 90); do
        curl -fs -m 2 "localhost:$porta/actuator/health" > /dev/null && break
        if [ "$tentativa" = 90 ]; then
            echo "O app da porta $porta nao respondeu em 3 minutos. Veja: journalctl -u 'io-bound@*' -n 30"
            exit 1
        fi
        sleep 2
    done
done
echo "io-bound no ar: buffer 8080, produtor 8081, consumidor 8082"
