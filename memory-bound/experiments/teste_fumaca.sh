#!/usr/bin/env bash
# Teste de fumaça: uns 6 minutos no LCC3, ANTES do run_all.sh.
# Confere as ferramentas e mede na VM real o que a calibração no Mac só estimou:
#   1. se as ferramentas existem (VBoxManage, k6, curl, python3);
#   2. quanta memória sobra na VM do C1 com a aplicação carregada;
#   3. se o ssh para a VM funciona (se não, recomenda SEM_SSH=1) e se o monitor da VM responde;
#   4. quanto custa iniciar uma viagem na CPU do LCC3;
#   5. quanto de CPU 10 usuários usam com a configuração real.
# No fim, recomenda a RAM do C1, a pausa entre recálculos e o comando do run_all.sh.
#
# Uso: experiments/teste_fumaca.sh
# Variáveis: RAM_C1 (512), NIVEL_MAX (60), PAUSA_S (5), RECALCULOS (6), REPETICOES (3)
set -euo pipefail
cd "$(dirname "$0")/.."
source experiments/comum.sh

export RESULTADOS=results/fumaca
RAM_C1="${RAM_C1:-512}"
NIVEL_MAX="${NIVEL_MAX:-60}"
PAUSA_S="${PAUSA_S:-5}"
RECALCULOS="${RECALCULOS:-6}"
REPETICOES="${REPETICOES:-3}"
DURACAO_VIAGEM_S=$((PAUSA_S * (RECALCULOS + 1)))
rm -rf "$RESULTADOS"
mkdir -p "$RESULTADOS"

echo "== 1. Ferramentas"
faltando=0
for ferramenta in "$VBOXMANAGE" "${K6:-k6}" curl python3 ssh; do
  if command -v "$ferramenta" > /dev/null; then
    echo "   ok: $ferramenta"
  else
    echo "   FALTA: $ferramenta"
    faltando=1
  fi
done
if [ "$faltando" = 1 ]; then
  echo "ERRO: instale o que falta (k6: experiments/instalar_k6.sh)" >&2
  exit 1
fi

echo "== 2. VM com 1 CPU e $RAM_C1 MB (memória livre com a aplicação carregada)"
SEM_SSH=1 experiments/cenario.sh c1 1 "$RAM_C1" > /dev/null

echo "== 3. ssh para a VM"
tem_ssh=0
if [ "$SEM_SSH" != 1 ] && na_vm true 2> /dev/null; then
  tem_ssh=1
  echo "   ok"
else
  echo "   sem ssh: o teste segue com SEM_SSH=1"
  export SEM_SSH=1
fi

if curl -sf -m 3 "$MONITOR_URL" > /dev/null; then
  echo "   monitor da VM ok ($MONITOR_URL)"
else
  echo "   AVISO: monitor da VM sem resposta em $MONITOR_URL (confira o serviço rotas-monitor e a"
  echo "   regra NAT 8081 -> 8001); a coleta pelo hospedeiro vai usar o /metrics da aplicação"
fi

echo "== 4. Custo de iniciar uma viagem (VM com 2 GB, 1 usuário, viagens curtas)"
experiments/cenario.sh cpu 1 2048 > /dev/null
PAUSA_S=1 RECALCULOS=1 AQUECIMENTO_S=5 DURATION=50s experiments/run_level.sh cpu 1 viagem 1 > /dev/null

echo "== 5. CPU com 10 usuários e a configuração real (pausa de ${PAUSA_S}s)"
PAUSA_S="$PAUSA_S" RECALCULOS="$RECALCULOS" AQUECIMENTO_S="$DURACAO_VIAGEM_S" \
  DURATION="$((DURACAO_VIAGEM_S + 45))s" experiments/run_level.sh cpu 10 viagem 2 > /dev/null

echo "== 6. Recomendações"
python3 - "$RESULTADOS" "$RAM_C1" "$NIVEL_MAX" "$PAUSA_S" "$RECALCULOS" "$REPETICOES" "$tem_ssh" \
  << 'PYTHON' | tee "$RESULTADOS/recomendacoes.txt"
import json
import math
import os
import sys

pasta, ram_c1, nivel_max, pausa, recalculos, repeticoes, tem_ssh = sys.argv[1:]
ram_c1 = int(ram_c1)
nivel_max = int(nivel_max)
pausa = float(pausa)
recalculos = int(recalculos)
repeticoes = int(repeticoes)
MEMORIA_POR_VIAGEM_MB = 28  # medido no Docker, Linux (results/local/)
CPU_ALVO = 60  # % de CPU no maior nível, para a CPU não virar o limite

# Memória livre no C1, gravada por cenario.sh (linha com o JSON do /metrics).
disponivel = None
with open(f"{pasta}/c1/vm.txt") as f:
    for linha in f:
        if linha.startswith("{"):
            dados = json.loads(linha)
            disponivel = dados["sistema"]["mem_disponivel_mb"]
            rss = dados["rss_mb"]
            swap = dados["sistema"]["swap_total_mb"]
viagens = disponivel / MEMORIA_POR_VIAGEM_MB
print(f"C1 ({ram_c1} MB): aplicação com {rss:.0f} MB, {disponivel:.0f} MB disponíveis, swap de {swap:.0f} MB")
print(f"   cabem cerca de {viagens:.0f} viagens antes do swap")
ram_sugerida = ram_c1
if viagens < 3:
    ram_sugerida = 768
    print(f"   RECOMENDAÇÃO: pouca folga para mostrar a degradação aos poucos; use C1 com {ram_sugerida} MB")
else:
    print("   ok")

# Custo de iniciar uma viagem: mediana com 1 usuário (sem fila).
with open(f"{pasta}/cpu/viagem/vus_1/rep_1/k6.json") as f:
    metricas = json.load(f)["metrics"]
inicio_ms = metricas["http_req_duration{fase:medicao,name:inicio}"]["med"]
print(f"Iniciar uma viagem: {inicio_ms:.0f} ms (no Mac: cerca de 250 ms)")

# CPU média da VM com 10 usuários, depois do aquecimento (/metrics lido do hospedeiro).
cpus = []
with open(f"{pasta}/cpu/viagem/vus_10/rep_2/metrics_host.txt") as f:
    linhas = f.readlines()
duracao_viagem = pausa * (recalculos + 1)
for linha in linhas[int(duracao_viagem):]:
    partes = linha.split(" ", 1)
    try:
        sistema = json.loads(partes[1]).get("sistema")
    except (IndexError, json.JSONDecodeError):
        continue
    if sistema:
        cpus.append(sistema["cpu_percent"])
cpu_10 = sum(cpus) / len(cpus)
cpu_max = cpu_10 * nivel_max / 10
print(f"CPU com 10 usuários: {cpu_10:.0f}%; previsão com {nivel_max} usuários: {cpu_max:.0f}%")
pausa_sugerida = pausa
if cpu_max > CPU_ALVO:
    pausa_sugerida = math.ceil(pausa * cpu_max / CPU_ALVO)
    print(f"   RECOMENDAÇÃO: com {nivel_max} usuários a CPU passaria de {CPU_ALVO}%; "
          f"use PAUSA_S={pausa_sugerida:.0f} (viagens mais longas, mesma memória por usuário)")
else:
    print("   ok")

aquecimento = int(pausa_sugerida * (recalculos + 1))
por_nivel = aquecimento + 60 + 30
total = 4 * repeticoes * 90 + 4 * 7 * repeticoes * por_nivel
print(f"Tempo estimado do run_all.sh com {repeticoes} repetições: {total // 3600}h{(total % 3600) // 60:02d}min")
if total > 2.5 * 3600 and repeticoes > 2:
    repeticoes = 2
    total = 4 * repeticoes * 90 + 4 * 7 * repeticoes * por_nivel
    print(f"   com 2 repetições: {total // 3600}h{(total % 3600) // 60:02d}min (sugerido abaixo)")
sem_ssh = "" if tem_ssh == "1" else "SEM_SSH=1 "
comando = (f'{sem_ssh}CENARIOS="C1:1:{ram_sugerida} C2:1:1024 C3:1:2048 C4:2:1024" '
           f"PAUSA_S={pausa_sugerida:.0f} AQUECIMENTO_S={aquecimento} REPETICOES={repeticoes} experiments/run_all.sh")
# O comando fica num script para não precisar digitar. As variáveis exportadas no terminal
# (K6, PORTA_APP, PASTA_VM) valem também para ele.
with open(f"{pasta}/comando.sh", "w") as f:
    f.write(f'#!/usr/bin/env bash\ncd "$(dirname "$0")/../.."\n{comando}\n')
os.chmod(f"{pasta}/comando.sh", 0o755)
print("\nComando sugerido (salvo em results/fumaca/comando.sh):")
print(f"  {comando}")
print("\nPara rodar tudo: results/fumaca/comando.sh")
PYTHON
