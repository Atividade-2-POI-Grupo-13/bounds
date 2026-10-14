#!/usr/bin/env bash
# Mede o tempo de um pedido na VM com 1 vCPU e sugere o valor de iteracoes
# para cerca de 50 ms por pedido. Roda no hospedeiro e nao mexe na VM:
# antes, deixe a VM ligada com 1 vCPU e a aplicacao no ar (sudo ~/cpu-bound/up.sh).
#
# Uso: tools/calibrar_vm.sh [ITERACOES_DE_TESTE]   (padrao 100000)
# Grava o resultado em results/vm/calibracao.txt. Depois, copie o valor
# sugerido para ITERACOES em experiments/comum.sh.
set -euo pipefail
export LC_ALL=C
cd "$(dirname "$0")/.."
source experiments/comum.sh

TESTE=${1:-100000}
ALVO_MS=50

HEALTH=$(curl -fs -m 5 "localhost:$PORTA/health") || {
    echo "A aplicacao nao respondeu em localhost:$PORTA. A VM esta ligada e a regra de porta existe?"
    exit 1
}
PROCESSADORES=$(echo "$HEALTH" | grep -o '"processadores":[0-9]*' | cut -d: -f2)
if [ "$PROCESSADORES" != 1 ]; then
    echo "A VM esta com $PROCESSADORES vCPUs. Calibre com 1 vCPU."
    exit 1
fi

URL="localhost:$PORTA/hash?senha=x&iteracoes=$TESTE"
echo "Aquecendo a JVM (40 pedidos)..."
for _ in $(seq 40); do curl -s "$URL" > /dev/null; done

echo "Medindo 30 pedidos com $TESTE iteracoes..."
TEMPOS=$(for _ in $(seq 30); do curl -s "$URL" | grep -o '"tempo_ms":[0-9.]*' | cut -d: -f2; done | sort -n)
MEDIANA=$(echo "$TEMPOS" | sed -n 15p)
SUGERIDO=$(awk -v i="$TESTE" -v m="$MEDIANA" -v a="$ALVO_MS" 'BEGIN { printf "%d", int(i * a / m / 1000) * 1000 }')

mkdir -p results/vm
{
    echo "data: $(date -Iseconds)"
    echo "hospedeiro: $(hostname), $(nproc) CPUs"
    echo "vm: $VM, 1 vCPU"
    echo "iteracoes testadas: $TESTE"
    echo "tempos (ms, ordenados): $(echo $TEMPOS)"
    echo "mediana: $MEDIANA ms"
    echo "iteracoes para ${ALVO_MS} ms: $SUGERIDO"
} | tee results/vm/calibracao.txt
