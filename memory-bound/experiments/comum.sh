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
RESULTADOS="${RESULTADOS:-results/raw}"  # onde cenario.sh e run_level.sh gravam
PORTA_MONITOR="${PORTA_MONITOR:-8081}"     # hospedeiro 8081 -> VM 8001 (deploy/monitor.py)
MONITOR_URL="${MONITOR_URL:-http://$HOST_VM:$PORTA_MONITOR}"
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

# SEM_SSH=1: a VM não tem ssh. O serviço reinicia pela API e a coleta vem só do
# /metrics (memória, swap e CPU da VM inteira), lido pelo hospedeiro.
SEM_SSH="${SEM_SSH:-0}"

reiniciar_servico() {
  if [ "$SEM_SSH" = 1 ]; then
    curl -sf -m 5 -X POST "$BASE_URL/admin/reiniciar" > /dev/null
    sleep 3
  else
    sudo_na_vm systemctl restart rotas
  fi
}

coletar_metrics_host() {
  # Uma linha por segundo: "tempo json", lido de fora da VM. Vem do monitor da VM
  # (processo separado, responde mesmo com a aplicação ocupada ou reiniciando);
  # se o monitor não responder, tenta o /metrics da aplicação.
  local arquivo="$1"
  : > "$arquivo"
  while true; do
    local json
    json=$(curl -s -m 2 "$MONITOR_URL" || true)
    if [ -z "$json" ]; then
      json=$(curl -s -m 2 "$BASE_URL/metrics" || echo "{}")
    fi
    echo "$(date +%s) $json" >> "$arquivo"
    sleep 1
  done
}

contar_reinicios() {
  # Quantas vezes o inicio_epoch do processo mudou ao longo do arquivo do coletor.
  grep -o '"inicio_epoch":[0-9]*' "$1" | awk -F: '
    { if (anterior != "" && $2 != anterior) { mudancas++ }; anterior = $2 }
    END { print mudancas + 0 }'
}
