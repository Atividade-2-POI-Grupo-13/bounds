#!/usr/bin/env bash
# Roda os 4 cenarios da VM em sequencia (cerca de 15 min).
# Deixe o notebook na tomada e sem outros programas pesados.
# Uso: experiments/vm_todos_os_cenarios.sh
set -euo pipefail
cd "$(dirname "$0")/.."

#       resultado  script
for PAR in "V1 vm_1cpu_1gb" "V2 vm_2cpu_1gb" "V3 vm_1cpu_2gb" "V4 vm_2cpu_2gb"; do
    set -- $PAR
    if [ -e "results/vm/$1/resumo.csv" ]; then
        echo "== $1 ja existe em results/vm/$1, pulando."
        continue
    fi
    echo "======== $1 ($2)"
    "experiments/$2.sh"
done
echo "Todos os cenarios da VM terminados."
