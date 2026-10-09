#!/usr/bin/env bash
# Troca o provisionamento da VM: desliga, aplica CPUs e RAM, liga e espera a aplicação.
# Roda no hospedeiro.
#
# Uso: experiments/cenario.sh NOME CPUS RAM_MB
#   ex.: experiments/cenario.sh C1 1 512
#
# Salva em $RESULTADOS/NOME/vm.txt (padrão results/raw) a memória, o swap e as CPUs que a VM enxerga.
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
# Logo depois de desligar, a VM pode continuar travada por alguns segundos: tenta de novo.
# O IO-APIC precisa estar ligado para a VM subir com mais de 1 CPU.
# Também garante o redirecionamento do monitor da VM (hospedeiro 8081 -> VM 8001):
# apaga a regra (se existir) e cria de novo.
aplicado=0
for _ in $(seq 1 10); do
  "$VBOXMANAGE" modifyvm "$VM" --natpf1 delete monitor 2> /dev/null || true
  if "$VBOXMANAGE" modifyvm "$VM" --ioapic on --cpus "$cpus" --memory "$ram_mb" \
       --natpf1 "monitor,tcp,,$PORTA_MONITOR,,8001"; then
    aplicado=1
    break
  fi
  sleep 3
done
if [ "$aplicado" = 0 ]; then
  echo "ERRO: modifyvm falhou 10 vezes" >&2
  exit 1
fi
"$VBOXMANAGE" startvm "$VM" --type headless > /dev/null

echo "== $nome: esperando a aplicação"
esperar_health 300

mkdir -p "$RESULTADOS/$nome"
{
  echo "cenario=$nome cpus=$cpus ram_mb=$ram_mb data=$(date -Iseconds)"
  if [ "$SEM_SSH" = 1 ]; then
    echo "sem ssh; dados do /metrics:"
    curl -s -m 5 "$BASE_URL/metrics"
    echo
  else
    na_vm "nproc; free -m; swapon --show"
  fi
} > "$RESULTADOS/$nome/vm.txt"
cat "$RESULTADOS/$nome/vm.txt"
