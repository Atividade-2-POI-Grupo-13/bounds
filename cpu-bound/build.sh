#!/usr/bin/env bash
# Compila a aplicacao e gera app-cpu.jar. Requer apenas um JDK 17 ou mais novo.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf out app-cpu.jar
mkdir -p out
javac --release 17 -d out app/cpubound/App.java
jar --create --file app-cpu.jar --main-class cpubound.App -C out .
rm -rf out

echo "Gerado: $(pwd)/app-cpu.jar"
echo "Para executar: java -Xms128m -Xmx128m -jar app-cpu.jar"
