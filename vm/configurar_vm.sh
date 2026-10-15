#!/usr/bin/env bash
# Deixa a VM do grupo com as regras de porta das 3 aplicacoes e o cache de disco
# do hospedeiro desligado (a io-bound precisa disso). Roda no hospedeiro, com a VM
# desligada. Pode rodar de novo quantas vezes precisar.
#
# Uso: vm/configurar_vm.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source vm/comum.sh

if [ "$(estado_vm)" = "running" ]; then
    echo "Desligue a VM antes (sudo poweroff dentro dela)."
    exit 1
fi

#        nome           hospedeiro  VM    uso
REGRAS="ssh:2222:22            acesso e coleta dos experimentos
        nginx:8088:80          teste de rede do roteiro
        app:8080:8080          cpu-bound
        rotas:8000:8000        memory-bound, aplicacao
        monitor:8001:8001      memory-bound, monitor da VM
        io-buffer:18080:8080   io-bound, buffer
        io-produtor:18081:8081 io-bound, produtor
        io-consumidor:18082:8082 io-bound, consumidor"

# Apaga todas as regras antigas (ensaios com outras portas) e cria as do grupo.
VBoxManage showvminfo "$VM" --machinereadable | grep '^Forwarding' | cut -d'"' -f2 | cut -d, -f1 \
    | while read -r nome; do VBoxManage modifyvm "$VM" --natpf1 delete "$nome"; done
echo "$REGRAS" | while read -r regra _; do
    IFS=: read -r nome hospedeiro vm <<< "$regra"
    VBoxManage modifyvm "$VM" --natpf1 "$nome,tcp,,$hospedeiro,,$vm"
    echo "porta $hospedeiro -> $vm ($nome)"
done

CTL=$(controlador_disco)
VBoxManage storagectl "$VM" --name "$CTL" --hostiocache off
echo "Cache de I/O do hospedeiro desligado no controlador $CTL."
