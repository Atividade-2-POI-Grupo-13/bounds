#!/usr/bin/env bash
# Roda um nível de demanda contra a VM. Roda no hospedeiro (a carga sai de fora da VM).
#
# Uso: experiments/run_level.sh CENARIO VUS ENDPOINT [REPETICAO]
#   ex.: experiments/run_level.sh C1 10 viagem 1
#
# Passos:
#   1. reinicia o serviço na VM, para o nível começar com a memória limpa;
#   2. liga os coletores: /metrics lido do hospedeiro (sempre) e, com ssh,
#      vmstat e /metrics dentro da VM;
#   3. roda o k6 no hospedeiro (aquecimento + medição);
#   4. desliga os coletores e, com ssh, traz os arquivos da VM;
#   5. registra reinícios do serviço e, com ssh, mensagens do OOM killer.
#
# Com SEM_SSH=1, pula tudo que precisa de ssh (ver experiments/comum.sh).
#
# Saída: $RESULTADOS/CENARIO/ENDPOINT/vus_N/rep_R/ (padrão results/raw)
#   k6.json, k6.csv.gz, k6.log, metrics_host.txt, estado.txt
#   e, com ssh: vmstat.txt, metrics.txt
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
pasta="$RESULTADOS/$cenario/$endpoint/vus_$vus/rep_$repeticao"
mkdir -p "$pasta"

echo "== $cenario $endpoint vus=$vus rep=$repeticao"

reiniciar_servico
esperar_health 120
inicio=$(date +%s)

coletar_metrics_host "$pasta/metrics_host.txt" &
coletor_host=$!
if [ "$SEM_SSH" != 1 ]; then
  inicio_vm=$(na_vm "date +%s")  # relógio da VM, para filtrar o log do kernel dela
  na_vm "$PASTA_VM/experiments/coletor_vm.sh iniciar"
fi

load/rodar.sh "$endpoint" "$vus" "$pasta" > /dev/null

kill "$coletor_host"
wait "$coletor_host" 2> /dev/null || true

if [ "$SEM_SSH" = 1 ]; then
  reinicios=$(contar_reinicios "$pasta/metrics_host.txt")
  oom="sem_ssh"
else
  na_vm "$PASTA_VM/experiments/coletor_vm.sh parar" || echo "aviso: não consegui parar os coletores" >&2
  trazer_da_vm /tmp/coleta/vmstat.txt "$pasta/vmstat.txt" || echo "aviso: vmstat.txt não veio" >&2
  trazer_da_vm /tmp/coleta/metrics.txt "$pasta/metrics.txt" || echo "aviso: metrics.txt não veio" >&2
  # NRestarts conta só os reinícios automáticos (processo morto) desde o restart do passo 1.
  reinicios=$(na_vm "systemctl show rotas -p NRestarts --value" || contar_reinicios "$pasta/metrics_host.txt")
  oom=$(sudo_na_vm journalctl -k --since "@$inicio_vm" --no-pager | grep -i -c -E "out of memory|killed process" || true)
fi

{
  echo "cenario=$cenario"
  echo "endpoint=$endpoint"
  echo "vus=$vus"
  echo "repeticao=$repeticao"
  echo "inicio=$inicio"
  echo "sem_ssh=$SEM_SSH"
  echo "reinicios=$reinicios"
  echo "mensagens_oom=$oom"
} > "$pasta/estado.txt"
echo "   reinícios=$reinicios mensagens_oom=$oom -> $pasta"
