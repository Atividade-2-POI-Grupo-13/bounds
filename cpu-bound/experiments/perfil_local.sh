#!/usr/bin/env bash
# Prova local do perfil CPU-bound, com Docker no lugar da VM.
#
# Roda os 4 cenarios (L1 a L4) com limites de CPU e memoria no container e, em
# cada um, as duas taxas de carga. Cada cenario comeca com um container novo.
# Serviu de ensaio antes dos experimentos na VM (experiments/vm_*.sh).
#
# A aplicacao fica nos E-cores a partir do 4 e o gerador nos E-cores 8 a 11,
# para os dois nao disputarem CPU. Valido para o i7-1255U do notebook.
#
# Uso: experiments/perfil_local.sh                 (todos os cenarios)
#      CENARIOS="L1 L2" experiments/perfil_local.sh
# Variaveis opcionais: REPETICOES (3), MEDICAO (30 s), AQUECIMENTO (10 s).
# Resultados em results/local/<cenario>/.
set -euo pipefail
cd "$(dirname "$0")/.."
export LC_ALL=C  # numeros com ponto decimal (o awk usaria virgula em pt_BR)

# Calibragem em results/local/calibracao.txt (tools/calibrar_local.sh):
# 253000 iteracoes = 50,3 ms por pedido em 1 nucleo, cerca de 20 pedidos/s.
ITERACOES=253000
TAXAS="10 30"
CENARIOS=${CENARIOS:-L1 L2 L3 L4}
REPETICOES=${REPETICOES:-3}
MEDICAO=${MEDICAO:-30}
AQUECIMENTO=${AQUECIMENTO:-10}
NUCLEOS_GERADOR=8-11
CONTAINER=app-cpu-exp
PORTA=8090

#        cenario  nucleos  memoria
declare -A NUCLEOS_DE=([L1]=1 [L2]=2 [L3]=1 [L4]=2)
declare -A MEMORIA_DE=([L1]=256m [L2]=256m [L3]=512m [L4]=512m)

cenario() {
    NOME=$1; NUCLEOS=$2; MEMORIA=$3
    NUCLEOS_APP=$(seq -s, 4 $((3 + NUCLEOS)))
    SAIDA=results/local/$NOME

    if [ -e "$SAIDA/resumo.csv" ]; then
        echo "$SAIDA/resumo.csv ja existe. Apague a pasta para refazer o cenario."
        return
    fi
    mkdir -p "$SAIDA/pedidos"

    docker rm -f "$CONTAINER" > /dev/null 2>&1 || true
    docker run -d --name "$CONTAINER" -p "$PORTA:8080" \
        --cpuset-cpus="$NUCLEOS_APP" --memory="$MEMORIA" --memory-swap="$MEMORIA" app-cpu > /dev/null
    until curl -fs "localhost:$PORTA/health" > /dev/null; do sleep 0.5; done

    # Coleta do docker stats: uma linha por segundo, com o horario em epoch.
    echo "epoch,cpu_percent,memoria_uso,memoria_limite" > "$SAIDA/docker_stats.csv"
    docker stats --format '{{.CPUPerc}},{{.MemUsage}}' "$CONTAINER" \
        | sed -u 's/\x1b\[[0-9;]*[A-Za-z]//g' \
        | while IFS= read -r linha; do
            [ -n "$linha" ] && echo "$(date +%s.%N | cut -c1-14),${linha// \/ /,}" | tr -d '%'
          done >> "$SAIDA/docker_stats.csv" &
    COLETOR=$!

    {
        echo "cenario: $NOME"
        echo "nucleos: $NUCLEOS ($NUCLEOS_APP)  memoria: $MEMORIA  iteracoes: $ITERACOES"
        echo "taxas: $TAXAS pedidos/s"
        echo "repeticoes: $REPETICOES  aquecimento: ${AQUECIMENTO}s  medicao: ${MEDICAO}s"
        echo "health: $(curl -s "localhost:$PORTA/health")"
        echo "inicio: $(date -Iseconds)"
    } | tee "$SAIDA/config.txt"

    URL="http://localhost:$PORTA/hash?senha=x&iteracoes=$ITERACOES"
    for REP in $(seq "$REPETICOES"); do
        for TAXA in $TAXAS; do
            echo "== $NOME  repeticao $REP  taxa $TAXA/s"
            if ! taskset -c "$NUCLEOS_GERADOR" java load/Carga.java "url=$URL" taxa="$TAXA" \
                duracao="$MEDICAO" aquecimento="$AQUECIMENTO" \
                saida="$SAIDA/pedidos/r${REP}_t${TAXA}.csv" resumo="$SAIDA/resumo.csv" > "$SAIDA/ultimo_teste.log" 2>&1; then
                cat "$SAIDA/ultimo_teste.log"
                echo "O gerador falhou. Cenario interrompido."
                return 1
            fi
            grep -E "Vazao|Tempo de resposta|AVISO" "$SAIDA/ultimo_teste.log" || true
            sleep 5
        done
    done
    echo "fim: $(date -Iseconds)" >> "$SAIDA/config.txt"
    kill $COLETOR 2> /dev/null || true
    docker rm -f "$CONTAINER" > /dev/null 2>&1 || true
    echo "Cenario $NOME terminado. Resultados em $SAIDA/"
}

docker build -q -t app-cpu . > /dev/null
trap 'pkill -f "docker stats.*$CONTAINER" 2> /dev/null; docker rm -f "$CONTAINER" > /dev/null 2>&1 || true' EXIT
for NOME in $CENARIOS; do
    cenario "$NOME" "${NUCLEOS_DE[$NOME]}" "${MEMORIA_DE[$NOME]}"
done
echo "Prova local terminada."
