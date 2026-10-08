# Configurações comuns aos scripts de experimento (rodam no hospedeiro Linux do LCC3).
# Tudo pode ser trocado por variável de ambiente.

VM="${VM:-vm-rotas}"
HOST_VM="${HOST_VM:-localhost}"         # endereço da VM visto do hospedeiro (portas redirecionadas)
PORTA_APP="${PORTA_APP:-8080}"          # hospedeiro 8080 -> VM 8000
PORTA_SSH="${PORTA_SSH:-2222}"          # hospedeiro 2222 -> VM 22
USUARIO_VM="${USUARIO_VM:-osboxes}"
SENHA_VM="${SENHA_VM:-osboxes.org}"     # senha pública da imagem, usada só no sudo da VM
PASTA_VM="${PASTA_VM:-memory-bound-rotas}"  # pasta do projeto dentro da VM (a partir da home)
VBOXMANAGE="${VBOXMANAGE:-VBoxManage}"
BASE_URL="${BASE_URL:-http://$HOST_VM:$PORTA_APP}"
export BASE_URL

# A VM é recriada a cada ida ao LCC, então a chave do host muda: não guardar.
# SSH_OPCOES permite acrescentar opções, por exemplo -i ~/.ssh/chave_vm.
SSH_BASE=(-p "$PORTA_SSH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
          -o LogLevel=ERROR -o ConnectTimeout=10 ${SSH_OPCOES:-})

na_vm() {
  # Roda um comando na VM. Com tempo limite, porque a VM pode travar em swap pesado.
  timeout 60 ssh "${SSH_BASE[@]}" "$USUARIO_VM@$HOST_VM" "$@"
}

sudo_na_vm() {
  na_vm "echo '$SENHA_VM' | sudo -S -p '' $*"
}

trazer_da_vm() {
  # trazer_da_vm ARQUIVO_NA_VM DESTINO_LOCAL
  timeout 60 scp -P "$PORTA_SSH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR ${SSH_OPCOES:-} "$USUARIO_VM@$HOST_VM:$1" "$2"
}

esperar_health() {
  # esperar_health SEGUNDOS
  local limite="$1"
  for _ in $(seq 1 "$limite"); do
    if curl -sf -m 2 "$BASE_URL/health" > /dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "ERRO: $BASE_URL/health não respondeu em $limite s" >&2
  return 1
}
