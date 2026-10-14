#!/usr/bin/env bash
# Etapa 3: prova local do perfil memory-bound, com Docker no lugar da VM.
#
# Roda os 4 cenários (C1 a C4) com limites de CPU e memória no container e,
# em cada um, vários níveis de usuários com o k6. Cada nível começa com o
# container recém-criado (memória limpa).
#
# Os limites de memória ficam de 112 a 148 MB abaixo da RAM da VM equivalente,
# porque na VM o Ubuntu também usa memória. O swap extra é igual em todos.
#
# Uso: experiments/perfil_local.sh            (todos os cenários e níveis)
#      CENARIOS="C1" NIVEIS="1 5" experiments/perfil_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."

CENARIOS="${CENARIOS:-C1 C2 C3 C4}"
NIVEIS="${NIVEIS:-1 2 5 10 20 40 60}"
DURACAO="${DURACAO:-60s}"
PAUSA_S="${PAUSA_S:-3}"
RECALCULOS="${RECALCULOS:-6}"
SWAP_EXTRA_MB="${SWAP_EXTRA_MB:-1024}"
PORTA=8090
CONTAINER=rotas-perfil
SAIDA=results/local

# cenário -> "cpus memória_mb"
limites() {
  case "$1" in
    C1) echo "1 400" ;;   # VM de 512 MB
    C2) echo "1 900" ;;   # VM de 1 GB
    C3) echo "1 1900" ;;  # VM de 2 GB
    C4) echo "2 900" ;;   # VM de 1 GB com 2 CPUs
  esac
}

coletar_recursos() {
  # Uma linha por segundo: tempo, memória, swap e CPU acumulada (µs) do container.
  local arquivo="$1"
  echo "tempo,memoria_bytes,swap_bytes,cpu_usec" > "$arquivo"
  while true; do
    local valores
    valores=$(docker exec "$CONTAINER" sh -c \
      'cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.swap.current; grep usage_usec /sys/fs/cgroup/cpu.stat' \
      2>/dev/null | awk '{print $NF}' | paste -sd, - || true)
    if [ -n "$valores" ]; then
      echo "$(date +%s),$valores" >> "$arquivo"
    fi
    sleep 1
  done
}

docker build -q -t rotas . > /dev/null

for cenario in $CENARIOS; do
  read -r cpus memoria_mb <<< "$(limites "$cenario")"
  for vus in $NIVEIS; do
    pasta="$SAIDA/$cenario/vus_$vus"
    mkdir -p "$pasta"
    echo "== $cenario ($cpus CPU, $memoria_mb MB) com $vus usuários"

    docker rm -f "$CONTAINER" > /dev/null 2>&1 || true
    docker run -d --name "$CONTAINER" \
      --cpus "$cpus" --memory "${memoria_mb}m" --memory-swap "$((memoria_mb + SWAP_EXTRA_MB))m" \
      --restart always -p "$PORTA:8000" rotas > /dev/null
    until curl -sf "localhost:$PORTA/health" > /dev/null; do sleep 1; done

    coletar_recursos "$pasta/recursos.csv" &
    coletor=$!

    BASE_URL="http://localhost:$PORTA" DURATION="$DURACAO" PAUSA_S="$PAUSA_S" RECALCULOS="$RECALCULOS" \
      load/rodar.sh viagem "$vus" "$pasta" > /dev/null

    kill "$coletor"
    wait "$coletor" 2> /dev/null || true
    curl -s -m 5 "localhost:$PORTA/metrics" > "$pasta/metrics.json" || true
    # Reinícios do container = vezes que o processo foi morto por falta de memória.
    docker inspect -f '{"reinicios": {{.RestartCount}}, "cpus": '"$cpus"', "memoria_mb": '"$memoria_mb"'}' \
      "$CONTAINER" > "$pasta/estado.json"
    cat "$pasta/estado.json"
  done
done

docker rm -f "$CONTAINER" > /dev/null
echo "Resultados em $SAIDA"
