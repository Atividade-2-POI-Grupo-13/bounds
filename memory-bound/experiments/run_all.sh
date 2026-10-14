#!/usr/bin/env bash
# Roda todos os cenários e níveis em sequência. Roda no hospedeiro do LCC3.
#
# Uso: experiments/run_all.sh
#
# Variáveis (com o padrão):
#   CENARIOS="C1:1:512 C2:1:1024 C3:1:2048 C4:2:1024"   nome:cpus:ram_mb
#   NIVEIS="1 2 5 10 20 40 60"                          usuários simultâneos
#   ENDPOINTS="viagem"                                   scripts de load/
#   REPETICOES=3
#   AQUECIMENTO_S=35  MEDICAO_S=60                      por nível
#   PAUSA_ENTRE_NIVEIS_S=10
#
# Roda uma repetição completa (todos os cenários e níveis) antes da próxima: se o
# tempo acabar, já existe pelo menos uma passada inteira.
# Pode ser rodado de novo depois de uma interrupção: pula os níveis que já têm
# resultado (REFAZER=1 refaz tudo).
#
# Antes de começar, mostra o tempo estimado e espera 10 s (Ctrl+C para desistir).
set -euo pipefail
cd "$(dirname "$0")/.."
source experiments/comum.sh

CENARIOS="${CENARIOS:-C1:1:512 C2:1:1024 C3:1:2048 C4:2:1024}"
NIVEIS="${NIVEIS:-1 2 5 10 20 40 60}"
ENDPOINTS="${ENDPOINTS:-viagem}"
REPETICOES="${REPETICOES:-3}"
AQUECIMENTO_S="${AQUECIMENTO_S:-35}"
MEDICAO_S="${MEDICAO_S:-60}"
PAUSA_ENTRE_NIVEIS_S="${PAUSA_ENTRE_NIVEIS_S:-10}"
REFAZER="${REFAZER:-0}"
export AQUECIMENTO_S
export DURATION="$((AQUECIMENTO_S + MEDICAO_S))s"

# Estimativa: troca de cenário ~90 s; cada nível = duração do k6 + ~20 s de reinício e coleta + pausa.
num_cenarios=0
for _ in $CENARIOS; do num_cenarios=$((num_cenarios + 1)); done
num_niveis=0
for _ in $NIVEIS; do num_niveis=$((num_niveis + 1)); done
num_endpoints=0
for _ in $ENDPOINTS; do num_endpoints=$((num_endpoints + 1)); done
por_nivel=$((AQUECIMENTO_S + MEDICAO_S + 20 + PAUSA_ENTRE_NIVEIS_S))
execucoes=$((num_cenarios * num_endpoints * num_niveis * REPETICOES))
total_s=$((num_cenarios * REPETICOES * 90 + execucoes * por_nivel))
echo "== $execucoes execuções de ${por_nivel}s + $((num_cenarios * REPETICOES)) trocas de cenário"
if [ "$SEM_SSH" = 1 ]; then
  echo "== modo SEM_SSH: coleta só pelo /metrics, sem vmstat nem log do kernel"
fi
echo "== tempo estimado: $((total_s / 3600))h$(((total_s % 3600) / 60))min"
echo "== começando em 10 s (Ctrl+C para desistir)"
sleep 10

mkdir -p "$RESULTADOS"
{
  echo "data=$(date -Iseconds)"
  echo "hospedeiro=$(hostname)"
  echo "cpus_hospedeiro=$(nproc)"
  free -m
  echo "CENARIOS=$CENARIOS"
  echo "NIVEIS=$NIVEIS ENDPOINTS=$ENDPOINTS REPETICOES=$REPETICOES"
  echo "AQUECIMENTO_S=$AQUECIMENTO_S MEDICAO_S=$MEDICAO_S SEM_SSH=$SEM_SSH"
  echo "PAUSA_S=${PAUSA_S:-5} RECALCULOS=${RECALCULOS:-6}"
} >> "$RESULTADOS/execucao.txt"

for repeticao in $(seq 1 "$REPETICOES"); do
  for cenario in $CENARIOS; do
    IFS=: read -r nome cpus ram_mb <<< "$cenario"

    # Pula o cenário inteiro se todos os níveis desta repetição já foram feitos.
    falta=0
    for endpoint in $ENDPOINTS; do
      for vus in $NIVEIS; do
        if [ "$REFAZER" = 1 ] || [ ! -f "$RESULTADOS/$nome/$endpoint/vus_$vus/rep_$repeticao/estado.txt" ]; then
          falta=1
        fi
      done
    done
    if [ "$falta" = 0 ]; then
      echo "== $nome rep=$repeticao já feito, pulando"
      continue
    fi

    if ! experiments/cenario.sh "$nome" "$cpus" "$ram_mb"; then
      echo "aviso: não consegui preparar o cenário $nome, pulando para o próximo" >&2
      continue
    fi
    for endpoint in $ENDPOINTS; do
      for vus in $NIVEIS; do
        if [ "$REFAZER" != 1 ] && [ -f "$RESULTADOS/$nome/$endpoint/vus_$vus/rep_$repeticao/estado.txt" ]; then
          continue
        fi
        # Uma falha num nível (VM travada, por exemplo) não derruba o resto.
        experiments/run_level.sh "$nome" "$vus" "$endpoint" "$repeticao" \
          || echo "aviso: $nome $endpoint vus=$vus rep=$repeticao falhou" >&2
        sleep "$PAUSA_ENTRE_NIVEIS_S"
      done
    done
  done
done
echo "== fim: resultados em $RESULTADOS/"
