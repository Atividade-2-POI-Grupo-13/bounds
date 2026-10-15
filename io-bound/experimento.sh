#!/usr/bin/env bash
# Roda o experimento na VM com um comando só: compila os apps (só na primeira vez),
# sobe os três, roda o stress test medindo tudo, derruba os apps e gera os gráficos.
# Os resultados ficam em resultados/<data>_<hora>/.
#
# Uso: ./experimento.sh <cenário> [--clientes N] [--jobs N]
#
# Cenários (configure a VM no VirtualBox antes, com ela desligada):
#   V1   1 CPU,  1024 MB                                  (referência)
#   V2   1 CPU,  1024 MB, disco limitado a 5 MB/s         (disco lento, veja o README)
#   V3   2 CPUs, 1024 MB                                  (mais CPU)
#   V4   1 CPU,   768 MB                                  (menos memória)
#
# Opções:
#   --clientes N    produtores e consumidores do stress test (padrão 50 de cada)
#   --jobs N        jobs de cada um (padrão 100)

set -eu

uso() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

case "${1:-}" in
    V1) CPUS=1; MEMORIA=1024m; DISCO=livre ;;
    V2) CPUS=1; MEMORIA=1024m; DISCO=5mb ;;
    V3) CPUS=2; MEMORIA=1024m; DISCO=livre ;;
    V4) CPUS=1; MEMORIA=768m; DISCO=livre ;;
    -h | --help) uso ;;
    *) echo "Escolha um cenário: V1, V2, V3 ou V4" >&2; uso 1 ;;
esac
cenario=$1
shift

CLIENTES=50
JOBS=100
while [ $# -gt 0 ]; do
    [ $# -ge 2 ] || { echo "Falta o valor de $1" >&2; uso 1; }
    case "$1" in
        --clientes) CLIENTES=$2 ;;
        --jobs) JOBS=$2 ;;
        *) echo "Opção desconhecida: $1" >&2; uso 1 ;;
    esac
    shift 2
done

cd "$(dirname "$0")"

if [ "$(nproc)" != "$CPUS" ]; then
    echo "Aviso: o cenário $cenario é com $CPUS CPU, mas a VM tem $(nproc). Confira o VirtualBox." >&2
fi

if [ ! -f buffer/target/buffer-0.1.0.jar ] || [ ! -f produtor/target/produtor-0.1.0.jar ] \
        || [ ! -f consumidor/target/consumidor-0.1.0.jar ]; then
    echo "Compilando os apps (só na primeira vez, demora alguns minutos)..."
    ./mvnw -q -B package -Dmaven.test.skip=true
fi

# Os três Java precisam caber juntos na memória da VM. Além do heap, a JVM gasta
# memória com código compilado, classes, threads e buffers de rede, então limitamos
# tudo isso, usamos o coletor de lixo mais simples (Serial) e só o compilador mais
# leve (C1). A aplicação passa o tempo esperando I/O, então quase não perde desempenho.
JAVA_OPTS="-Xmx64m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -XX:MaxMetaspaceSize=80m -XX:ReservedCodeCacheSize=24m -XX:MaxDirectMemorySize=32m -Xss256k"
# Menos áreas de memória do malloc por processo (o padrão cresce com o número de threads)
export MALLOC_ARENA_MAX=2

# As portas precisam estar livres: outra aplicacao do grupo ou o up.sh podem estar no ar.
for porta in 8080 8081 8082; do
    if curl -s -m 2 -o /dev/null "localhost:$porta"; then
        echo "A porta $porta ja esta em uso. Derrube as aplicacoes antes: for s in ~/*/down.sh; do sudo \"\$s\"; done" >&2
        exit 1
    fi
done

logs=$(mktemp -d)
apps=()
# Derruba os apps no fim, mesmo se algo der errado no meio
trap 'kill "${apps[@]}" 2> /dev/null || true; rm -rf "$logs"' EXIT

echo "Subindo os apps..."
for app in buffer produtor consumidor; do
    # shellcheck disable=SC2086
    java $JAVA_OPTS -jar "$app/target/$app-0.1.0.jar" --buffer.dir="$PWD/data" > "$logs/$app.log" 2>&1 &
    apps+=($!)
done
for porta in 8080 8081 8082; do
    for tentativa in $(seq 1 180); do
        curl -sf "localhost:$porta/actuator/health" > /dev/null && break
        if [ "$tentativa" = 180 ]; then
            echo "O app da porta $porta não subiu em 3 min. Logs:" >&2
            tail -n 20 "$logs"/*.log >&2
            exit 1
        fi
        sleep 1
    done
done

echo "Cenário $cenario: $CPUS CPU, $MEMORIA, disco $DISCO, $CLIENTES clientes com $JOBS jobs cada"
./monitorar.sh ./stress.sh "$CLIENTES" "$JOBS"

# Guarda o cenário e os logs dos apps junto com os resultados
pasta=$(ls -d resultados/*/ | tail -1)
echo "cenario: $cenario (cpus=$CPUS, memoria=$MEMORIA, disco=$DISCO)" >> "$pasta/info.txt"
cp "$logs"/*.log "$pasta"

python3 plotar.py resultados
