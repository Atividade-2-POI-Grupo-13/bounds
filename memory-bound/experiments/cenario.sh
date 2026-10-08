#!/usr/bin/env bash
# Troca o provisionamento da VM: desliga, aplica CPUs e RAM, liga e espera a aplicação.
# Roda no hospedeiro.
#
# Uso: experiments/cenario.sh NOME CPUS RAM_MB
#   ex.: experiments/cenario.sh C1 1 512
#
# Salva em results/raw/NOME/vm.txt a memória, o swap e as CPUs que a VM enxerga.
set -euo pipefail
cd "$(dirname "$0")/.."
source experiments/comum.sh

if [ $# -ne 3 ]; then
  echo "uso: $0 NOME CPUS RAM_MB" >&2
  exit 1
fi
nome="$1"
cpus="$2"
ram_mb="$3"

estado_vm() {
  "$VBOXMANAGE" showvminfo "$VM" --machinereadable | grep '^VMState=' | cut -d'"' -f2
}

echo "== $nome: desligando $VM"
if [ "$(estado_vm)" = "running" ]; then
  "$VBOXMANAGE" controlvm "$VM" acpipowerbutton
  for _ in $(seq 1 60); do
    if [ "$(estado_vm)" != "running" ]; then
      break
    fi
    sleep 1
  done
  # Se o desligamento normal não terminou em 60 s, desliga na marra.
  if [ "$(estado_vm)" = "running" ]; then
    "$VBOXMANAGE" controlvm "$VM" poweroff
  fi
  sleep 3
fi

echo "== $nome: aplicando $cpus CPU e $ram_mb MB"
"$VBOXMANAGE" modifyvm "$VM" --cpus "$cpus" --memory "$ram_mb"
"$VBOXMANAGE" startvm "$VM" --type headless > /dev/null

echo "== $nome: esperando a aplicação"
esperar_health 300

mkdir -p "results/raw/$nome"
{
  echo "cenario=$nome cpus=$cpus ram_mb=$ram_mb data=$(date -Iseconds)"
  na_vm "nproc; free -m; swapon --show"
} > "results/raw/$nome/vm.txt"
cat "results/raw/$nome/vm.txt"
