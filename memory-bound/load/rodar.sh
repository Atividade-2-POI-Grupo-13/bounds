#!/usr/bin/env bash
# Roda um nível de carga com o k6 e salva os resultados.
#
# Uso: load/rodar.sh ENDPOINT VUS PASTA_SAIDA
#   ENDPOINT: viagem, rota ou alcance (o script load/ENDPOINT.js)
#
# Gera em PASTA_SAIDA:
#   k6.json    resumo (latência média, p50, p95, p99, req/s, taxa de erro)
#   k6.csv.gz  uma linha por métrica de cada requisição
#   k6.log     saída do k6
#
# As outras opções vão por variável de ambiente, que o k6 lê direto:
#   BASE_URL, DURATION, TIMEOUT, AQUECIMENTO_S, PAUSA_S, RECALCULOS, MINUTOS, PONTOS
# K6 aponta para o binário (padrão: k6 no PATH), por exemplo K6=~/bin/k6 no LCC.
#
# Exemplo: BASE_URL=http://localhost:8080 DURATION=60s load/rodar.sh viagem 10 results/teste
set -euo pipefail

if [ $# -ne 3 ]; then
  echo "uso: $0 ENDPOINT VUS PASTA_SAIDA" >&2
  exit 1
fi
endpoint="$1"
vus="$2"
saida="$3"
pasta_load="$(cd "$(dirname "$0")" && pwd)"
script="$pasta_load/$endpoint.js"
if [ ! -f "$script" ]; then
  echo "não existe $script" >&2
  exit 1
fi

mkdir -p "$saida"
# O k6 sai com código diferente de zero quando há erros; o resultado fica salvo mesmo assim.
VUS="$vus" "${K6:-k6}" run -q \
  --summary-export "$saida/k6.json" \
  --out "csv=$saida/k6.csv.gz" \
  "$script" > "$saida/k6.log" 2>&1 || echo "aviso: k6 terminou com código $? (veja $saida/k6.log)" >&2
echo "resultado em $saida"
