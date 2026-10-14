#!/usr/bin/env bash
# Mede o tempo de um pedido no container com 1 nucleo e sugere o valor de
# iteracoes para cerca de 50 ms por pedido.
#
# Uso: tools/calibrar_local.sh [ITERACOES_DE_TESTE]   (padrao 100000)
# Grava o resultado em results/local/calibracao.txt.
set -euo pipefail
cd "$(dirname "$0")/.."

ITERACOES=${1:-100000}
ALVO_MS=50
NOME=app-cpu-calibracao
PORTA=8090

docker build -q -t app-cpu . > /dev/null
docker rm -f "$NOME" > /dev/null 2>&1 || true
docker run -d --name "$NOME" -p "$PORTA:8080" --cpuset-cpus=4 app-cpu > /dev/null
trap 'docker rm -f "$NOME" > /dev/null 2>&1 || true' EXIT
until curl -fs "localhost:$PORTA/health" > /dev/null; do sleep 0.5; done

URL="localhost:$PORTA/hash?senha=x&iteracoes=$ITERACOES"
echo "Aquecendo a JVM (40 pedidos)..."
for _ in $(seq 40); do curl -s "$URL" > /dev/null; done

echo "Medindo 30 pedidos com $ITERACOES iteracoes..."
TEMPOS=$(for _ in $(seq 30); do curl -s "$URL" | grep -o '"tempo_ms":[0-9.]*' | cut -d: -f2; done | sort -n)
MEDIANA=$(echo "$TEMPOS" | sed -n 15p)
SUGERIDO=$(awk -v i="$ITERACOES" -v m="$MEDIANA" -v a="$ALVO_MS" 'BEGIN { printf "%d", int(i * a / m / 1000) * 1000 }')

mkdir -p results/local
{
    echo "data: $(date -Iseconds)"
    echo "container: 1 nucleo (--cpuset-cpus=4)"
    echo "iteracoes testadas: $ITERACOES"
    echo "tempos (ms, ordenados): $(echo $TEMPOS)"
    echo "mediana: $MEDIANA ms"
    echo "iteracoes para ${ALVO_MS} ms: $SUGERIDO"
} | tee results/local/calibracao.txt
