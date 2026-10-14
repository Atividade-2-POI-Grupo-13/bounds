#!/usr/bin/env bash
# Cenario V2 na VM: 2 vCPU(s) e 1024 MB de RAM, taxas 10 e 30 pedidos/s.
# Prepara a VM sozinho (desliga, ajusta, liga) e roda o cenario. Cerca de 3,5 min.
# Uso: experiments/vm_2cpu_1gb.sh
set -euo pipefail
cd "$(dirname "$0")/.."

experiments/preparar_vm.sh 2 1024
experiments/cenario_vm.sh V2
