#!/usr/bin/env bash
# Deixa a VM com os recursos pedidos e a aplicacao respondendo:
# desliga a VM (se estiver ligada), troca vCPUs e RAM, liga sem janela, sobe a
# aplicacao pelo ssh e confere o /health. Antes de subir a CPU-bound, roda o
# down.sh de todos os projetos da pasta pessoal da VM, para so ela usar a VM.
#
# Requer, uma vez: chave ssh do hospedeiro copiada para a VM
# (deploy/README.md, passo 7). A senha do sudo vem de SENHA_VM (comum.sh).
#
# Uso: experiments/preparar_vm.sh CPUS MEMORIA_MB
#   ex.: experiments/preparar_vm.sh 2 1024
# Nome da VM e porta em experiments/comum.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
source experiments/comum.sh

if [ $# -ne 2 ]; then
    sed -n 6,7p "$0"
    exit 1
fi
CPUS=$1
MEMORIA=$2

estado() {
    VBoxManage showvminfo "$VM" --machinereadable | grep '^VMState=' | cut -d'"' -f2
}

if [ "$(estado)" = "running" ]; then
    echo "Desligando a VM..."
    # Equivale a apertar o botao de desligar: o Ubuntu encerra normalmente.
    VBoxManage controlvm "$VM" acpipowerbutton
    for _ in $(seq 60); do
        [ "$(estado)" != "running" ] && break
        sleep 1
    done
    if [ "$(estado)" = "running" ]; then
        echo "A VM nao desligou em 60 s. Desligando a forca."
        VBoxManage controlvm "$VM" poweroff
    fi
    sleep 3
fi

echo "Configurando: $CPUS vCPU(s), $MEMORIA MB."
# Logo depois de desligar, o VirtualBox pode ficar travado por alguns segundos.
# O I/O APIC precisa estar ligado para a VM subir com mais de 1 vCPU.
for tentativa in $(seq 10); do
    if VBoxManage modifyvm "$VM" --ioapic on --cpus "$CPUS" --memory "$MEMORIA" 2> /dev/null; then
        break
    fi
    if [ "$tentativa" = 10 ]; then
        echo "Nao consegui mudar a configuracao da VM."
        exit 1
    fi
    sleep 3
done

echo "Ligando a VM (sem janela)..."
VBoxManage startvm "$VM" --type headless > /dev/null

echo "Esperando o ssh da VM..."
SSH=(ssh -n -p "$PORTA_SSH" -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR
     -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null osboxes@localhost)
for tentativa in $(seq 60); do
    "${SSH[@]}" true 2> /dev/null && break
    if [ "$tentativa" = 60 ]; then
        echo "O ssh da VM nao respondeu em 3 minutos. A chave foi copiada (ssh-copy-id)?"
        exit 1
    fi
    sleep 3
done
echo "Subindo a aplicacao..."
"${SSH[@]}" \
    "for s in ~/*/down.sh; do echo '$SENHA_VM' | sudo -S -p '' \"\$s\"; done; echo '$SENHA_VM' | sudo -S -p '' ~/cpu-bound/up.sh"

echo "Conferindo a aplicacao..."
for _ in $(seq 30); do
    if HEALTH=$(curl -fs -m 2 "localhost:$PORTA/health"); then
        PROCESSADORES=$(echo "$HEALTH" | grep -o '"processadores":[0-9]*' | cut -d: -f2)
        if [ "$PROCESSADORES" = "$CPUS" ]; then
            echo "Pronta: $HEALTH"
            # Alguns segundos para o Ubuntu terminar de iniciar antes de medir.
            sleep 20
            exit 0
        fi
        echo "A aplicacao respondeu com $PROCESSADORES processador(es), esperado $CPUS."
        exit 1
    fi
    sleep 2
done
echo "A aplicacao nao respondeu em localhost:$PORTA. A regra de porta 8080 existe?"
exit 1
