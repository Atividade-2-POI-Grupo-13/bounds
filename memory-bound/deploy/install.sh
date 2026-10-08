#!/usr/bin/env bash
# Instala o serviço de rotas DENTRO da VM (Ubuntu 22.04) e deixa rodando no systemd.
#
# Rodar como o usuário normal (osboxes), de dentro da pasta do projeto copiada para a VM:
#   ./deploy/install.sh
# Usa sudo para apt e systemd. Pode rodar de novo quantas vezes precisar.
#
# Dependências Python:
#   1. Com python3-venv (já instalado ou via apt): cria .venv e instala com pip.
#      Se deploy/wheels/ existir, instala só dela, sem internet.
#   2. Sem python3-venv e sem internet: descompacta as wheels de deploy/wheels/
#      em .pacotes/ e o serviço usa essa pasta no PYTHONPATH (não precisa de pip).
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/.." && pwd)"
USUARIO="$(id -un)"
WHEELS="$PASTA/deploy/wheels"
cd "$PASTA"

echo "== Projeto em $PASTA, serviço vai rodar como $USUARIO"

# Pacotes do sistema: só funciona com internet. Sem internet, segue sem eles.
if ! python3 -c "import ensurepip, venv" 2> /dev/null || ! command -v sar > /dev/null; then
  echo "== Tentando instalar python3-venv e sysstat com apt"
  if sudo apt-get update -qq && sudo apt-get install -y -qq python3-venv sysstat; then
    echo "apt ok"
  else
    echo "apt falhou (sem internet?), seguindo sem os pacotes"
  fi
fi

TEM_WHEELS=0
if ls "$WHEELS"/*.whl > /dev/null 2>&1; then
  TEM_WHEELS=1
fi

PYTHONPATH_SERVICO=""
if python3 -c "import ensurepip, venv" 2> /dev/null; then
  echo "== Criando .venv"
  python3 -m venv --clear .venv
  if [ "$TEM_WHEELS" = 1 ]; then
    .venv/bin/pip install -q --no-index --find-links "$WHEELS" -r requirements.txt
  else
    .venv/bin/pip install -q -r requirements.txt
  fi
  PYTHON="$PASTA/.venv/bin/python"
else
  if [ "$TEM_WHEELS" = 0 ]; then
    echo "ERRO: sem python3-venv e sem deploy/wheels/. Rode deploy/baixar_wheels.sh numa máquina com internet." >&2
    exit 1
  fi
  echo "== Sem venv: descompactando as wheels em .pacotes/"
  rm -rf .pacotes
  mkdir .pacotes
  for wheel in "$WHEELS"/*.whl; do
    python3 -m zipfile -e "$wheel" .pacotes/
  done
  PYTHON="$(command -v python3)"
  PYTHONPATH_SERVICO="$PASTA/.pacotes"
fi

echo "== Conferindo se a aplicação importa"
PYTHONPATH="$PYTHONPATH_SERVICO" "$PYTHON" -c "import fastapi, uvicorn, psutil; print('dependências ok')"

echo "== Instalando o serviço systemd"
sed -e "s#__PASTA__#$PASTA#g" \
    -e "s#__USUARIO__#$USUARIO#g" \
    -e "s#__PYTHON__#$PYTHON#g" \
    -e "s#__PYTHONPATH__#$PYTHONPATH_SERVICO#g" \
    deploy/rotas.service | sudo tee /etc/systemd/system/rotas.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable -q rotas
sudo systemctl restart rotas

echo "== Esperando /health (o mapa leva alguns segundos para carregar)"
for _ in $(seq 1 60); do
  if curl -sf localhost:8000/health; then
    echo
    echo "== Memória e swap da VM (registrar no relatório; não mudar entre cenários)"
    free -h
    swapon --show || true
    exit 0
  fi
  sleep 1
done
echo "ERRO: /health não respondeu em 60 s. Veja: journalctl -u rotas -n 50" >&2
exit 1
