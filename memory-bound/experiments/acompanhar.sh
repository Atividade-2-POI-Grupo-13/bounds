#!/usr/bin/env bash
# Mostra, uma linha por segundo, o estado da VM e da aplicação.
# Serve para a demonstração ao vivo e para acompanhar os experimentos.
# Roda no hospedeiro. Ctrl+C para parar.
#
# Memória, swap, CPU e reinícios vêm do monitor da VM (porta 8081 no hospedeiro), que
# responde mesmo com a aplicação ocupada ou reiniciando. As viagens ativas vêm do
# /metrics da aplicação (porta 8080) e aparecem como "-" quando ela demora a responder.
#
# Uso: experiments/acompanhar.sh
#      MONITOR_URL=http://localhost:8081 BASE_URL=http://localhost:8080 experiments/acompanhar.sh
set -uo pipefail
BASE_URL="${BASE_URL:-http://localhost:8080}"
MONITOR_URL="${MONITOR_URL:-http://localhost:8081}"

campo() {
  # campo JSON NOME -> valor numérico do primeiro "NOME":valor (vazio se não houver)
  echo "$1" | grep -o "\"$2\":[0-9.]*" | head -1 | cut -d: -f2
}

printf "%-8s %8s %9s %11s %10s %8s  %s\n" hora viagens "rss MB" "mem VM MB" "swap MB" "CPU VM" aplicação
inicio_anterior=""
while true; do
  hora=$(date +%H:%M:%S)
  monitor=$(curl -s -m 2 "$MONITOR_URL")
  app=$(curl -s -m 1 "$BASE_URL/metrics")
  viagens=$(campo "$app" viagens_ativas)
  if [ -z "$monitor" ]; then
    printf "%-8s %s\n" "$hora" "monitor sem resposta (porta 8081)"
  else
    inicio=$(campo "$monitor" inicio_epoch)
    situacao="rodando"
    if [ -z "$inicio" ]; then
      situacao="FORA DO AR"
    elif [ -n "$inicio_anterior" ] && [ "$inicio" != "$inicio_anterior" ]; then
      situacao="REINICIOU"
    fi
    if [ -n "$inicio" ]; then
      inicio_anterior="$inicio"
    fi
    printf "%-8s %8s %9s %11s %10s %7s%%  %s\n" "$hora" "${viagens:--}" "$(campo "$monitor" rss_mb)" \
      "$(campo "$monitor" mem_usada_mb)" "$(campo "$monitor" swap_usado_mb)" \
      "$(campo "$monitor" cpu_percent)" "$situacao"
  fi
  sleep 1
done
