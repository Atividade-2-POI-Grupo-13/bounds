#!/usr/bin/env bash
# Roda um nível de demanda contra a VM. Roda no hospedeiro (a carga sai de fora da VM).
#
# Uso: experiments/run_level.sh CENARIO VUS ENDPOINT [REPETICAO]
#   ex.: experiments/run_level.sh C1 10 viagem 1
#
# Passos:
#   1. reinicia o serviço na VM, para o nível começar com a memória limpa;
#   2. liga os coletores na VM (vmstat e /metrics a cada segundo);
#   3. roda o k6 no hospedeiro (aquecimento + medição);
#   4. desliga os coletores e traz os arquivos com scp;
#   5. registra reinícios do serviço e mensagens do OOM killer.
#
# Saída: results/raw/CENARIO/ENDPOINT/vus_N/rep_R/
#   k6.json, k6.csv.gz, k6.log, vmstat.txt, metrics.txt, estado.txt
set -euo pipefail
cd "$(dirname "$0")/.."
source experiments/comum.sh

if [ $# -lt 3 ]; then
  echo "uso: $0 CENARIO VUS ENDPOINT [REPETICAO]" >&2
  exit 1
fi
cenario="$1"
vus="$2"
endpoint="$3"
repeticao="${4:-1}"
pasta="results/raw/$cenario/$endpoint/vus_$vus/rep_$repeticao"
mkdir -p "$pasta"

echo "== $cenario $endpoint vus=$vus rep=$repeticao"

sudo_na_vm systemctl restart rotas
esperar_health 120
inicio=$(na_vm "date +%s")

na_vm "$PASTA_VM/experiments/coletor_vm.sh iniciar"
load/rodar.sh "$endpoint" "$vus" "$pasta" > /dev/null
na_vm "$PASTA_VM/experiments/coletor_vm.sh parar" || echo "aviso: não consegui parar os coletores" >&2

trazer_da_vm /tmp/coleta/vmstat.txt "$pasta/vmstat.txt" || echo "aviso: vmstat.txt não veio" >&2
trazer_da_vm /tmp/coleta/metrics.txt "$pasta/metrics.txt" || echo "aviso: metrics.txt não veio" >&2

# NRestarts conta só os reinícios automáticos (processo morto) desde o restart do passo 1.
reinicios=$(na_vm "systemctl show rotas -p NRestarts --value" || echo "?")
oom=$(sudo_na_vm journalctl -k --since "@$inicio" --no-pager | grep -i -c -E "out of memory|killed process" || true)
{
  echo "cenario=$cenario"
  echo "endpoint=$endpoint"
  echo "vus=$vus"
  echo "repeticao=$repeticao"
  echo "inicio=$inicio"
  echo "reinicios=$reinicios"
  echo "mensagens_oom=$oom"
} > "$pasta/estado.txt"
echo "   reinícios=$reinicios mensagens_oom=$oom -> $pasta"
