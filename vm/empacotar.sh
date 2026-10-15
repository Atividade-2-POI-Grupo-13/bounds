#!/usr/bin/env bash
# Compila as 3 aplicacoes no hospedeiro e gera vm/bounds.tar.gz para levar ao VDI.
# Compilar fora evita baixar Maven e dependencias dentro da VM (o VDI cresce menos).
# Requer JDK 21 no hospedeiro. Uso: vm/empacotar.sh
set -euo pipefail
cd "$(dirname "$0")/.."

cpu-bound/build.sh
(cd io-bound && ./mvnw -q -B package -Dmaven.test.skip=true)

# Sem resultados, caches e mapas grandes que a VM nao usa.
tar czf vm/bounds.tar.gz \
    --exclude=results --exclude=resultados --exclude=.venv --exclude=.pacotes --exclude=cache \
    --exclude=__pycache__ --exclude='*_full*' --exclude=.git --exclude=io-bound/data \
    --exclude='io-bound/*/src' --exclude=io-bound/.mvn \
    cpu-bound memory-bound io-bound
echo "Gerado: vm/bounds.tar.gz ($(du -h vm/bounds.tar.gz | cut -f1))"
echo "Servir para a VM: cd vm && python3 -m http.server 8099 --bind 127.0.0.1"
