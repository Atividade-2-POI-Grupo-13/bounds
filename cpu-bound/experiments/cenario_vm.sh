#!/usr/bin/env bash
# Roda um cenario na VM do VirtualBox, que ja deve estar ligada com os recursos
# do cenario e com a aplicacao rodando como servico (deploy/README.md, passo 6).
# Este script NAO muda a VM: manda carga pela porta 8080 e coleta, a cada segundo:
#   - de fora, as metricas do VirtualBox (vbox_stats.csv);
#   - de dentro, pelo ssh, o vmstat da VM (vmstat.txt) e o /metrics da
#     aplicacao (metrics.txt), copiados para o hospedeiro no fim.
# Requer a chave ssh copiada para a VM (deploy/README.md, passo 7).
#
# Uso: experiments/cenario_vm.sh NOME
#   ex.: experiments/cenario_vm.sh V1
#
# VM, porta, iteracoes e taxas em experiments/comum.sh.
# Variaveis opcionais: REPETICOES (1), MEDICAO (30 s), AQUECIMENTO (10 s).
# Resultados em results/vm/NOME/: resumo.csv (uma linha por teste),
# pedidos/*.csv (uma linha por pedido), vbox_stats.csv, vmstat.txt e metrics.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
export LC_ALL=C
source experiments/comum.sh

if [ $# -ne 1 ]; then
    sed -n 7,8p "$0"
    exit 1
fi
NOME=$1
REPETICOES=${REPETICOES:-1}
MEDICAO=${MEDICAO:-30}
AQUECIMENTO=${AQUECIMENTO:-10}
SAIDA=results/vm/$NOME

if [ -e "$SAIDA/resumo.csv" ]; then
    echo "$SAIDA/resumo.csv ja existe. Apague a pasta para refazer o cenario."
    exit 1
fi
if ! HEALTH=$(curl -fs "localhost:$PORTA/health"); then
    echo "A aplicacao nao responde em localhost:$PORTA. A VM esta ligada?"
    exit 1
fi
SSH=(ssh -n -p "$PORTA_SSH" -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR
     -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null osboxes@localhost)
if ! "${SSH[@]}" true 2> /dev/null; then
    echo "Sem ssh para a VM (porta $PORTA_SSH). A chave foi copiada (ssh-copy-id)?"
    exit 1
fi
mkdir -p "$SAIDA/pedidos"

# Coleta dentro da VM, uma linha por segundo, com a hora da VM em epoch.
"${SSH[@]}" 'rm -rf /tmp/coleta && mkdir /tmp/coleta && cd /tmp/coleta
    nohup sh -c "vmstat -n 1 | while read l; do echo \$(date +%s) \$l; done" > vmstat.txt 2>&1 &
    echo $! > vmstat.pid
    nohup sh -c "while true; do curl -s -m 1 localhost:8081/metrics; echo; sleep 1; done" > metrics.txt 2>&1 &
    echo $! > metrics.pid'
# Diferenca entre os relogios do hospedeiro e da VM, para alinhar as coletas.
DIFERENCA_RELOGIO=$(awk -v h="$(date +%s.%N)" -v v="$("${SSH[@]}" date +%s.%N)" 'BEGIN { printf "%.3f", h - v }')

# Metricas do VirtualBox, uma amostra por segundo. CPU/Load e percentual do
# hospedeiro inteiro; a analise converte para "100% = 1 nucleo".
VBoxManage metrics setup --period 1 --samples 1 "$VM" CPU/Load,RAM/Usage > /dev/null
echo "epoch,metrica,valor" > "$SAIDA/vbox_stats.csv"
VBoxManage metrics collect --period 1 --samples 1 "$VM" \
        CPU/Load/User,CPU/Load/Kernel,RAM/Usage/Used 2> /dev/null \
    | while read -r _ _ metrica valor _; do
        case "$metrica" in
            CPU/Load/*|RAM/Usage/Used) echo "$(date +%s.%N | cut -c1-14),$metrica,${valor%\%}" ;;
        esac
      done >> "$SAIDA/vbox_stats.csv" &
COLETOR=$!
parar_coletas() {
    kill $COLETOR 2> /dev/null || true
    pkill -f "VBoxManage metrics collect.*$VM" 2> /dev/null || true
    # Para os coletores da VM (o grupo de processos de cada um) e traz os arquivos.
    "${SSH[@]}" 'cd /tmp/coleta && for p in *.pid; do pkill -P "$(cat $p)"; kill "$(cat $p)"; done' 2> /dev/null || true
    scp -q -P "$PORTA_SSH" -o BatchMode=yes -o LogLevel=ERROR -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null osboxes@localhost:/tmp/coleta/{vmstat,metrics}.txt "$SAIDA/" \
        || echo "Aviso: nao consegui copiar a coleta de dentro da VM."
}
trap parar_coletas EXIT

{
    echo "cenario: $NOME"
    echo "vm: $VM  $(VBoxManage showvminfo "$VM" --machinereadable | grep -E '^(cpus|memory)=' | tr '\n' ' ')"
    echo "nucleos: $(echo "$HEALTH" | grep -o '"processadores":[0-9]*' | cut -d: -f2)  memoria: $(VBoxManage showvminfo "$VM" --machinereadable | grep '^memory=' | cut -d= -f2)m  iteracoes: $ITERACOES"
    echo "cpus do hospedeiro: $(nproc)"
    echo "memoria total da vm (kB): $("${SSH[@]}" "awk '/MemTotal/ {print \$2}' /proc/meminfo")"
    echo "diferenca de relogio hospedeiro - vm (s): $DIFERENCA_RELOGIO"
    echo "taxas: $TAXAS pedidos/s"
    echo "repeticoes: $REPETICOES  aquecimento: ${AQUECIMENTO}s  medicao: ${MEDICAO}s"
    echo "health: $HEALTH"
    echo "inicio: $(date -Iseconds)"
} | tee "$SAIDA/config.txt"

URL="http://localhost:$PORTA/hash?senha=x&iteracoes=$ITERACOES"
for REP in $(seq "$REPETICOES"); do
    for TAXA in $TAXAS; do
        echo "== $NOME  repeticao $REP  taxa $TAXA/s"
        if ! java load/Carga.java "url=$URL" taxa="$TAXA" \
            duracao="$MEDICAO" aquecimento="$AQUECIMENTO" \
            saida="$SAIDA/pedidos/r${REP}_t${TAXA}.csv" resumo="$SAIDA/resumo.csv" > "$SAIDA/ultimo_teste.log" 2>&1; then
            cat "$SAIDA/ultimo_teste.log"
            echo "O gerador falhou. Cenario interrompido."
            exit 1
        fi
        grep -E "Vazao|Tempo de resposta|AVISO" "$SAIDA/ultimo_teste.log" || true
        sleep 5
    done
done
echo "fim: $(date -Iseconds)" >> "$SAIDA/config.txt"
echo "Cenario $NOME terminado. Resultados em $SAIDA/"
