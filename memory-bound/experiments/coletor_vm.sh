#!/usr/bin/env bash
# Roda DENTRO da VM. Coleta uma amostra por segundo:
#   /tmp/coleta/vmstat.txt   memória livre, swap usado, swap in/out, CPU da VM (vmstat)
#   /tmp/coleta/metrics.txt  "tempo json" com o /metrics da aplicação (RSS, viagens ativas...)
#
# Uso: coletor_vm.sh iniciar | parar
set -euo pipefail
PASTA=/tmp/coleta

case "${1:-}" in
  iniciar)
    rm -rf "$PASTA"
    mkdir -p "$PASTA"
    nohup vmstat -n -t 1 < /dev/null > "$PASTA/vmstat.txt" 2>&1 &
    echo $! > "$PASTA/vmstat.pid"
    nohup bash -c 'while true; do
        echo "$(date +%s) $(curl -s -m 2 localhost:8000/metrics || echo "{}")"
        sleep 1
      done' < /dev/null > "$PASTA/metrics.txt" 2>&1 &
    echo $! > "$PASTA/metrics.pid"
    ;;
  parar)
    for arquivo in "$PASTA"/*.pid; do
      kill "$(cat "$arquivo")" 2> /dev/null || true
    done
    ;;
  *)
    echo "uso: $0 iniciar | parar" >&2
    exit 1
    ;;
esac
