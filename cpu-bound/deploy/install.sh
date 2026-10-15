#!/usr/bin/env bash
# Instala a aplicação CPU-bound DENTRO da VM (Ubuntu 22.04) como serviço do systemd.
#
# Rodar como o usuário normal (osboxes), de dentro da pasta do projeto copiada para a VM:
#   ./deploy/install.sh
# Usa sudo para apt e systemd. Pode rodar de novo quantas vezes precisar.
#
# O que faz:
#   1. instala o Java com apt, se faltar (17 ou mais novo);
#   2. compila app-cpu.jar, se ainda não existir;
#   3. instala a unidade app-cpu.service, fora do boot (só uma aplicação do grupo roda por vez);
#   4. sobe a aplicação, confere o /health e derruba de novo.
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/.." && pwd)"
USUARIO="$(id -un)"
cd "$PASTA"
echo "== Projeto em $PASTA, serviço vai rodar como $USUARIO"

java_ok() {
  command -v java > /dev/null && [ "$(java -version 2>&1 | grep -oP 'version "\K[0-9]+' | head -1)" -ge 17 ]
}

pacote=""
if [ ! -f app-cpu.jar ] && ! command -v javac > /dev/null; then
  pacote=openjdk-21-jdk-headless   # o JDK compila o .jar
elif ! java_ok; then
  pacote=openjdk-21-jre-headless
fi
if [ -n "$pacote" ]; then
  echo "== Instalando com apt: $pacote"
  # NEEDRESTART_MODE=a evita a tela "Daemons using outdated libraries", que trava o apt no Ubuntu 22.04.
  sudo apt-get update -qq
  sudo env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get install -y -qq "$pacote"
  sudo apt-get clean
fi

# A atualização automática do Ubuntu disputa a CPU com a aplicação durante os testes.
sudo systemctl disable --now -q unattended-upgrades 2> /dev/null || true

if [ ! -f app-cpu.jar ]; then
  echo "== Compilando app-cpu.jar"
  ./build.sh
fi

echo "== Instalando o serviço systemd"
sed -e "s#__PASTA__#$PASTA#g" -e "s#__USUARIO__#$USUARIO#g" \
    deploy/app-cpu.service | sudo tee /etc/systemd/system/app-cpu.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl disable -q app-cpu 2> /dev/null || true

echo "== Testando: sobe e derruba a aplicação"
sudo ./up.sh
sudo ./down.sh
echo "== Instalado. Para subir: sudo ./up.sh  Para parar: sudo ./down.sh"
