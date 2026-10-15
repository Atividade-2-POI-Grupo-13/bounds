#!/usr/bin/env bash
# Instala a aplicação IO-bound DENTRO da VM (Ubuntu 22.04) como serviço do systemd.
#
# Rodar como o usuário normal (osboxes), de dentro da pasta do projeto copiada para a VM:
#   ./deploy/install.sh
# Usa sudo para apt e systemd. Pode rodar de novo quantas vezes precisar.
#
# O que faz:
#   1. instala com apt o que faltar: Java 21, sysstat (iostat, sar, pidstat) e matplotlib;
#   2. compila os três serviços, se os .jar ainda não existirem (precisa de internet);
#   3. instala a unidade io-bound@.service, fora do boot (só uma aplicação do grupo roda por vez);
#   4. sobe os três serviços, confere o health de cada um e derruba de novo.
set -euo pipefail

PASTA="$(cd "$(dirname "$0")/.." && pwd)"
USUARIO="$(id -un)"
cd "$PASTA"
echo "== Projeto em $PASTA, serviços vão rodar como $USUARIO"

java_ok() {
  command -v java > /dev/null && [ "$(java -version 2>&1 | grep -oP 'version "\K[0-9]+' | head -1)" -ge 21 ]
}
jars_ok() {
  for app in buffer produtor consumidor; do
    [ -f "$app/target/$app-0.1.0.jar" ] || return 1
  done
}

pacotes=""
if ! jars_ok; then
  pacotes="$pacotes openjdk-21-jdk-headless"   # o JDK compila os .jar
elif ! java_ok; then
  pacotes="$pacotes openjdk-21-jre-headless"
fi
command -v iostat > /dev/null || pacotes="$pacotes sysstat"
python3 -c "import matplotlib" 2> /dev/null || pacotes="$pacotes python3-matplotlib"
if [ -n "$pacotes" ]; then
  echo "== Instalando com apt:$pacotes"
  # NEEDRESTART_MODE=a evita a tela "Daemons using outdated libraries", que trava o apt no Ubuntu 22.04.
  # shellcheck disable=SC2086
  sudo apt-get update -qq
  sudo env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get install -y -qq $pacotes
  sudo apt-get clean
fi

# A atualização automática do Ubuntu disputa CPU e disco com os testes.
sudo systemctl disable --now -q unattended-upgrades 2> /dev/null || true

if ! jars_ok; then
  echo "== Compilando os três serviços (só na primeira vez, demora alguns minutos)"
  ./mvnw -q -B package -Dmaven.test.skip=true
fi

echo "== Instalando o serviço systemd"
sed -e "s#__PASTA__#$PASTA#g" -e "s#__USUARIO__#$USUARIO#g" \
    deploy/io-bound@.service | sudo tee /etc/systemd/system/io-bound@.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl disable -q io-bound@buffer io-bound@produtor io-bound@consumidor 2> /dev/null || true

echo "== Testando: sobe e derruba os três serviços"
sudo ./up.sh
sudo ./down.sh
echo "== Instalado. Para subir: sudo ./up.sh  Para parar: sudo ./down.sh  Experimento: ./experimento.sh V1"
