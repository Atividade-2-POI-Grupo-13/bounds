#!/usr/bin/env bash
# Demonstração curta para o laboratório: roda dois níveis de carga contra a VM como
# ela está (sem trocar CPU nem RAM) e mostra uma tabela no fim. Roda no hospedeiro.
#
# Uso: experiments/demo_rapido.sh
#
# Variáveis (com o padrão):
#   NIVEIS="5 20"                  usuários simultâneos, um nível depois do outro
#   AQUECIMENTO_S=25 MEDICAO_S=30  por nível
#   PAUSA_S=3                      segundos entre as requisições de uma viagem
#
# Com a VM em 1 CPU e 1 GB, o nível pequeno fica sem swap e o grande enche o swap.
# Cada nível leva cerca de 1,5 min. Para ver a memória subindo ao vivo, abra outro
# terminal e rode experiments/acompanhar.sh (ou abra o monitor no navegador).
#
# Saída: results/demo/viagem/vus_N/rep_1/ (mesmos arquivos do run_level.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
source experiments/comum.sh

NIVEIS="${NIVEIS:-5 20}"
MEDICAO_S="${MEDICAO_S:-30}"
export AQUECIMENTO_S="${AQUECIMENTO_S:-25}"
export PAUSA_S="${PAUSA_S:-3}"
export DURATION="$((AQUECIMENTO_S + MEDICAO_S))s"
export RESULTADOS="results"

esperar_health 5

for vus in $NIVEIS; do
  # O cenário se chama "demo": a pasta fica results/demo/viagem/vus_N/rep_1.
  experiments/run_level.sh demo "$vus" viagem 1
done

python3 - "$RESULTADOS/demo/viagem" "$NIVEIS" << 'PYTHON'
import json
import sys

pasta = sys.argv[1]
niveis = sys.argv[2].split()

print()
print("usuários  p95 início  req/s  erros  memória máx. VM  swap máx.")
for nivel in niveis:
    base = pasta + "/vus_" + nivel + "/rep_1"

    with open(base + "/k6.json") as arquivo:
        metricas = json.load(arquivo)["metrics"]
    p95_ms = metricas["http_req_duration{fase:medicao,name:inicio}"]["p(95)"]
    req_s = metricas["http_reqs{fase:medicao}"]["rate"]
    erros = metricas["http_req_failed{fase:medicao}"]["value"] * 100

    mem_max = 0.0
    swap_max = 0.0
    with open(base + "/metrics_host.txt") as arquivo:
        for linha in arquivo:
            partes = linha.split(" ", 1)
            if len(partes) < 2:
                continue
            try:
                sistema = json.loads(partes[1])["sistema"]
            except (ValueError, KeyError):
                continue
            mem_max = max(mem_max, sistema["mem_usada_mb"])
            swap_max = max(swap_max, sistema["swap_usado_mb"])

    print("%8s  %8.1f s  %5.1f  %4.0f%%  %12.0f MB  %6.0f MB"
          % (nivel, p95_ms / 1000, req_s, erros, mem_max, swap_max))
PYTHON
