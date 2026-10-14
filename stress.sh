#!/usr/bin/env bash
# Stress test: N produtores e N consumidores ao mesmo tempo, cada um com J jobs.
#
# Uso: ./stress.sh [clientes=50] [jobs=100]

set -u

CLIENTES=${1:-50}
JOBS=${2:-100}
PRODUTOR=${PRODUTOR_URL:-http://localhost:8081}
CONSUMIDOR=${CONSUMIDOR_URL:-http://localhost:8082}

saida=$(mktemp -d)
trap 'rm -rf "$saida"' EXIT

echo "$CLIENTES produtores e $CLIENTES consumidores, $JOBS jobs cada"

# A mesma URL repetida N vezes
repetir() {
    for _ in $(seq 1 "$CLIENTES"); do echo "$1"; done
}

# Um curl só para cada lado, com as N requisições em paralelo (até 300).
# Cem processos curl separados gastariam memória que é do experimento.
# shellcheck disable=SC2046
curl -s --parallel --parallel-immediate --parallel-max "$CLIENTES" -w '\n' -X POST \
    $(repetir "$PRODUTOR/produzir?jobs=$JOBS") > "$saida/produtor.txt" &
produtores=$!
# shellcheck disable=SC2046
curl -s --parallel --parallel-immediate --parallel-max "$CLIENTES" -w '\n' -X POST \
    $(repetir "$CONSUMIDOR/consumir?jobs=$JOBS") > "$saida/consumidor.txt" &
consumidores=$!
wait "$produtores" "$consumidores"

# Soma um campo numérico de todas as respostas JSON de um arquivo
soma() {
    grep -o "\"$1\":[0-9]*" "$2" | cut -d: -f2 | awk '{ s += $1 } END { print s + 0 }'
}

total=$((CLIENTES * JOBS))
echo "produtor:   $(soma concluidos "$saida/produtor.txt") de $total jobs, buffer cheio $(soma vezesCheio "$saida/produtor.txt") vezes"
echo "consumidor: $(soma concluidos "$saida/consumidor.txt") de $total jobs, buffer vazio $(soma vezesVazio "$saida/consumidor.txt") vezes"
echo "tempo total: ${SECONDS} s"
