#!/usr/bin/env bash
# Roda o experimento inteiro num container limitado, com um comando só:
# compila os apps, sobe os três dentro do container, mede e roda o stress test.
# Os CSVs ficam em resultados/<data>_<hora>/.
#
# Uso: ./experimento.sh [cenário] [opções]
#
# Cenários (mudam uma coisa de cada vez em relação ao C1):
#   C1   1 CPU,  1 GB, disco sem limite   (referência, é o padrão)
#   C2   1 CPU,  1 GB, disco a 5 MB/s     (disco limitado)
#   C3   2 CPUs, 1 GB, disco sem limite   (dobro de CPU)
#   C4   1 CPU,  2 GB, disco sem limite   (dobro de memória)
#
# Opções (valem por cima do cenário):
#   --cpus N        CPUs do container, ex.: 2 ou 0.5
#   --memoria M     RAM do container, sem swap, ex.: 512m ou 2g
#   --disco B       banda máxima de leitura e de escrita no disco, ex.: 10mb; "livre" tira o limite
#   --clientes N    produtores e consumidores do stress test (padrão 50 de cada)
#   --jobs N        jobs de cada um (padrão 100)
#
# Exemplos:
#   ./experimento.sh
#   ./experimento.sh C2
#   ./experimento.sh --cpus 2 --memoria 512m --disco 20mb --clientes 100

set -eu

uso() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

cenario=C1
case "${1:-}" in
    C1 | C2 | C3 | C4) cenario=$1; shift ;;
    -h | --help) uso ;;
esac

case "$cenario" in
    C1) CPUS=1; MEMORIA=1g; DISCO=livre ;;
    C2) CPUS=1; MEMORIA=1g; DISCO=5mb ;;
    C3) CPUS=2; MEMORIA=1g; DISCO=livre ;;
    C4) CPUS=1; MEMORIA=2g; DISCO=livre ;;
esac
CLIENTES=50
JOBS=100

while [ $# -gt 0 ]; do
    [ $# -ge 2 ] || { echo "Falta o valor de $1" >&2; uso 1; }
    case "$1" in
        --cpus) CPUS=$2 ;;
        --memoria) MEMORIA=$2 ;;
        --disco) DISCO=$2 ;;
        --clientes) CLIENTES=$2 ;;
        --jobs) JOBS=$2 ;;
        *) echo "Opção desconhecida: $1" >&2; uso 1 ;;
    esac
    shift 2
done
export CENARIO=$cenario CPUS MEMORIA DISCO CLIENTES JOBS

cd "$(dirname "$0")"

# Disco onde o Docker guarda os containers: é nele que o limite de banda vale
dispositivo() {
    if [ "$(uname)" = Darwin ]; then
        echo /dev/vda   # o disco da máquina virtual do Docker Desktop
        return
    fi
    local origem pai
    origem=$(df --output=source "$(docker info -f '{{.DockerRootDir}}')" | tail -1)
    pai=$(lsblk -no pkname "$origem" 2> /dev/null | head -1)
    echo "/dev/${pai:-${origem#/dev/}}"
}

limite_disco=()
if [ "$DISCO" != livre ]; then
    disco=${DISCO_DISPOSITIVO:-$(dispositivo)}
    limite_disco=(--device-write-bps "$disco:$DISCO" --device-read-bps "$disco:$DISCO")
fi

echo "Compilando a imagem (a primeira vez demora alguns minutos)..."
docker build -q -t io-bound . > /dev/null

echo "Cenário $cenario: cpus=$CPUS, memoria=$MEMORIA, disco=$DISCO, $CLIENTES clientes com $JOBS jobs cada"
mkdir -p resultados
docker run --rm \
    --cpus "$CPUS" --memory "$MEMORIA" --memory-swap "$MEMORIA" \
    ${limite_disco[@]+"${limite_disco[@]}"} \
    --user "$(id -u):$(id -g)" \
    -e CENARIO -e CPUS -e MEMORIA -e DISCO -e CLIENTES -e JOBS \
    -v "$PWD/resultados:/app/resultados" \
    io-bound
