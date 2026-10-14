#!/usr/bin/env bash
# Roda o experimento inteiro com um comando só: compila os apps, sobe os três
# num container, roda o stress test medindo tudo e gera os gráficos.
# Os resultados ficam em resultados/<data>_<hora>/.
#
# Uso: ./experimento.sh <cenário> [--clientes N] [--jobs N]
#
# Cenários (configure a VM no VirtualBox antes de rodar):
#   V1   VM com 1 CPU,  1024 MB, disco sem limite   (referência)
#   V2   VM com 1 CPU,  1024 MB, disco a 5 MB/s     (disco lento)
#   V3   VM com 2 CPUs, 1024 MB, disco sem limite   (mais CPU)
#   V4   VM com 1 CPU,   768 MB, disco sem limite   (menos memória)
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
export CENARIO=$cenario CPUS MEMORIA DISCO CLIENTES JOBS

cd "$(dirname "$0")"

# Disco onde o Docker guarda os containers: é nele que o limite do V2 vale
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
    disco=$(dispositivo)
    limite_disco=(--device-write-bps "$disco:$DISCO" --device-read-bps "$disco:$DISCO")
fi

echo "Compilando a imagem (a primeira vez demora alguns minutos)..."
docker build -q -t io-bound . > /dev/null

echo "Cenário $cenario: $CPUS CPU, $MEMORIA, disco $DISCO, $CLIENTES clientes com $JOBS jobs cada"
mkdir -p resultados
# CPU e memória são as da VM; as portas ficam abertas para o redirecionamento do VirtualBox
docker run --rm \
    -p 8080:8080 -p 8081:8081 -p 8082:8082 \
    ${limite_disco[@]+"${limite_disco[@]}"} \
    --user "$(id -u):$(id -g)" \
    -e CENARIO -e CPUS -e MEMORIA -e DISCO -e CLIENTES -e JOBS \
    -v "$PWD/resultados:/app/resultados" \
    io-bound
