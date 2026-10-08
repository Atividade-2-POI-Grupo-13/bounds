#!/usr/bin/env bash
# Baixa o k6 (binário único) para ~/bin, sem root. Roda no hospedeiro do LCC3.
# Sem internet no LCC3: rodar antes em outra máquina Linux x86_64 e levar ~/bin/k6 no pendrive.
# Depois: export K6=~/bin/k6
set -euo pipefail
VERSAO="${VERSAO:-v2.3.0}"
case "$(uname -m)" in
  x86_64) arquitetura=amd64 ;;
  aarch64 | arm64) arquitetura=arm64 ;;
  *) echo "arquitetura desconhecida: $(uname -m)" >&2; exit 1 ;;
esac
mkdir -p ~/bin
curl -sL "https://github.com/grafana/k6/releases/download/$VERSAO/k6-$VERSAO-linux-$arquitetura.tar.gz" \
  | tar -xz -C ~/bin --strip-components=1 "k6-$VERSAO-linux-$arquitetura/k6"
~/bin/k6 version
echo "ok: use export K6=~/bin/k6"
