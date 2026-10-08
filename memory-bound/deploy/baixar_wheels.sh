#!/usr/bin/env bash
# Plano B sem internet na VM: baixa (numa máquina com internet) as wheels do
# servidor para Linux x86_64 e Python 3.10, o Python da VM.
# O install.sh usa deploy/wheels/ quando a pasta existe.
#
# O pip precisa rodar num Python 3.10: algumas dependências só são exigidas
# abaixo do 3.11 (por exemplo exceptiongroup) e o pip decide isso pela versão
# do Python em que ele roda.
#   No Mac, com uv:   PIP="uvx --python 3.10 pip" deploy/baixar_wheels.sh
#   Com python3.10:   deploy/baixar_wheels.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PIP="${PIP:-python3.10 -m pip}"
rm -rf deploy/wheels
$PIP download -r requirements.txt -d deploy/wheels \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
  --python-version 3.10 --implementation cp --only-binary=:all:
ls deploy/wheels
