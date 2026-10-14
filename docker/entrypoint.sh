#!/usr/bin/env bash
# Roda dentro do container: sobe os três apps, espera ficarem prontos
# e roda o stress test com o monitoramento.

set -u

# Os três Java precisam caber juntos no limite de memória do container. Além do heap,
# a JVM gasta memória com código compilado, classes, threads e buffers de rede,
# então limitamos tudo isso, usamos o coletor de lixo mais simples (Serial) e só o
# compilador mais leve (C1). A aplicação passa o tempo esperando I/O, então quase
# não perde desempenho com isso.
JAVA_OPTS=${JAVA_OPTS:--Xmx128m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -XX:MaxMetaspaceSize=96m -XX:ReservedCodeCacheSize=32m -XX:MaxDirectMemorySize=64m -Xss512k}
# Menos áreas de memória do malloc por processo (o padrão cresce com o número de threads)
export MALLOC_ARENA_MAX=2

cd /app
# O buffer grava no disco do próprio container, que é o disco limitado
# shellcheck disable=SC2086
java $JAVA_OPTS -jar buffer-0.1.0.jar --buffer.dir=/app/data > buffer.log 2>&1 &
# shellcheck disable=SC2086
java $JAVA_OPTS -jar produtor-0.1.0.jar > produtor.log 2>&1 &
# shellcheck disable=SC2086
java $JAVA_OPTS -jar consumidor-0.1.0.jar > consumidor.log 2>&1 &

echo "Subindo os apps..."
for porta in 8080 8081 8082; do
    for tentativa in $(seq 1 120); do
        curl -sf "localhost:$porta/actuator/health" > /dev/null && break
        if [ "$tentativa" = 120 ]; then
            echo "O app da porta $porta não subiu em 2 min. Logs:" >&2
            tail -n 20 ./*.log >&2
            exit 1
        fi
        sleep 1
    done
done

./monitorar.sh ./stress.sh "${CLIENTES:-50}" "${JOBS:-100}"

# Guarda os limites usados e os logs dos apps junto com os resultados
pasta=$(ls -d resultados/*/ | tail -1)
echo "cenario: ${CENARIO:-?} (cpus=${CPUS:-?}, memoria=${MEMORIA:-?}, disco=${DISCO:-?})" >> "$pasta/info.txt"
cp ./*.log "$pasta"

# Gráficos desta rodada e a comparação com todas as rodadas que já estão em resultados/
MPLCONFIGDIR=/tmp/matplotlib python3 plotar.py resultados
