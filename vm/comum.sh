# Funcoes comuns para controlar a VM do grupo pelo hospedeiro.
# Tudo pode ser trocado por variavel de ambiente, ex.: VM=outra-vm ./rodar_experimento.sh io V1

VM="${VM:-vm-poi-exp}"                      # a mesma VM para as 3 aplicacoes
PORTA_SSH="${PORTA_SSH:-2222}"          # hospedeiro 2222 -> VM 22
SENHA_VM="${SENHA_VM:-osboxes.org}"     # senha do osboxes, passada ao sudo pelo ssh
export VM PORTA_SSH SENHA_VM

SSH_OPCOES=(-p "$PORTA_SSH" -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR
            -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

na_vm() {
    ssh -n "${SSH_OPCOES[@]}" osboxes@localhost "$@"
}

estado_vm() {
    VBoxManage showvminfo "$VM" --machinereadable | grep '^VMState=' | cut -d'"' -f2
}

desligar_vm() {
    [ "$(estado_vm)" = "running" ] || return 0
    echo "Desligando a VM..."
    VBoxManage controlvm "$VM" acpipowerbutton
    for _ in $(seq 60); do
        [ "$(estado_vm)" != "running" ] && break
        sleep 1
    done
    if [ "$(estado_vm)" = "running" ]; then
        echo "A VM nao desligou em 60 s. Desligando a forca."
        VBoxManage controlvm "$VM" poweroff
    fi
    sleep 3
}

# configurar_vm CPUS MEMORIA_MB: com a VM desligada. Tenta de novo porque, logo
# depois de desligar, o VirtualBox pode ficar travado por alguns segundos.
configurar_vm() {
    echo "Configurando: $1 vCPU(s), $2 MB."
    for tentativa in $(seq 10); do
        VBoxManage modifyvm "$VM" --ioapic on --cpus "$1" --memory "$2" 2> /dev/null && return 0
        sleep 3
    done
    echo "Nao consegui mudar a configuracao da VM."
    return 1
}

# Controlador do disco da VM: o que tem um .vdi na porta 0 (a VM pode ter um IDE antes).
controlador_disco() {
    echo "${CONTROLADOR:-$(VBoxManage showvminfo "$VM" --machinereadable | grep -i '^"[^"]*-0-0"=".*\.vdi"' | head -1 | cut -d'"' -f2 | sed 's/-0-0$//')}"
}

# limitar_disco LIMITE|livre: com a VM desligada. LIMITE no formato do VirtualBox, ex.: 5M.
limitar_disco() {
    local ctl arquivo grupo=none
    ctl=$(controlador_disco)
    arquivo=$(VBoxManage showvminfo "$VM" --machinereadable | grep "^\"$ctl-0-0\"=" | cut -d'"' -f4)
    if [ "$1" != livre ]; then
        VBoxManage bandwidthctl "$VM" add Disco --type disk --limit "$1" 2> /dev/null \
            || VBoxManage bandwidthctl "$VM" set Disco --limit "$1"
        grupo=Disco
    fi
    echo "Disco: $1"
    VBoxManage storageattach "$VM" --storagectl "$ctl" --port 0 --device 0 --type hdd \
        --medium "$arquivo" --bandwidthgroup "$grupo"
}

# Espera o servidor ssh da VM responder (com ou sem chave).
esperar_porta_ssh() {
    for _ in $(seq 60); do
        timeout 5 bash -c "exec 3<>/dev/tcp/localhost/$PORTA_SSH && head -c 4 <&3" 2> /dev/null | grep -q SSH && return 0
        sleep 3
    done
    echo "O ssh da VM nao respondeu em 3 minutos (porta $PORTA_SSH)."
    return 1
}

ligar_vm() {
    echo "Ligando a VM (sem janela)..."
    VBoxManage startvm "$VM" --type headless > /dev/null
    echo "Esperando o ssh da VM..."
    esperar_porta_ssh
    garantir_chave
}

# Copia a chave ssh do hospedeiro para a VM, se ainda nao estiver la. A senha e
# a padrao da imagem (SENHA_VM), entregue ao ssh-copy-id por um SSH_ASKPASS.
garantir_chave() {
    na_vm true 2> /dev/null && return 0
    echo "Copiando a chave ssh do hospedeiro para a VM (uma vez por VDI)..."
    if [ ! -f ~/.ssh/id_ed25519.pub ]; then
        mkdir -p ~/.ssh && chmod 700 ~/.ssh
        ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/id_ed25519
    fi
    local askpass
    askpass=$(mktemp)
    printf '#!/bin/sh\necho "%s"\n' "$SENHA_VM" > "$askpass"
    chmod 700 "$askpass"
    SSH_ASKPASS="$askpass" SSH_ASKPASS_REQUIRE=force DISPLAY="${DISPLAY:-:0}" \
        ssh-copy-id -i ~/.ssh/id_ed25519.pub -p "$PORTA_SSH" -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR osboxes@localhost < /dev/null > /dev/null 2>&1 || true
    rm -f "$askpass"
    na_vm true 2> /dev/null && return 0
    echo "Nao consegui copiar a chave. Rode uma vez: ssh-copy-id -p $PORTA_SSH osboxes@localhost (senha $SENHA_VM)"
    return 1
}

# Deixa tudo pronto antes de qualquer experimento, sem passo manual:
# VM existente, portas e cache de disco configurados, VM ligada e chave ssh copiada.
garantir_vm() {
    if ! VBoxManage showvminfo "$VM" > /dev/null 2>&1; then
        local vms
        vms=$(VBoxManage list vms | cut -d'"' -f2)
        if [ "$(echo "$vms" | grep -c .)" = 1 ]; then
            VM=$vms
            echo "Usando a VM $VM (a unica registrada)."
        else
            echo "A VM \"$VM\" nao existe. VMs registradas:"
            echo "$vms"
            echo "Rode com VM=nome-da-vm ./rodar_experimento.sh ..."
            return 1
        fi
    fi
    export VM
    if ! VBoxManage showvminfo "$VM" --machinereadable | grep -q '^Forwarding.*="io-consumidor,'; then
        echo "Primeira execucao com esta VM: configurando portas e cache de disco."
        desligar_vm
        vm/configurar_vm.sh
    fi
    if [ "$(estado_vm)" != running ]; then
        ligar_vm
    else
        esperar_porta_ssh
        garantir_chave
    fi
}

# Roda o down.sh de todos os projetos da pasta pessoal da VM.
derrubar_todos() {
    na_vm "for s in ~/*/down.sh; do echo '$SENHA_VM' | sudo -S -p '' \"\$s\"; done"
}

# subir APLICACAO: derruba todas e sobe so esta (cpu-bound, memory-bound ou io-bound).
subir() {
    derrubar_todos
    na_vm "echo '$SENHA_VM' | sudo -S -p '' ~/$1/up.sh"
}
