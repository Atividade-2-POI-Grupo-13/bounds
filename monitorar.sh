#!/usr/bin/env bash
# Mede CPU, memória, disco e rede (da máquina e de cada app) a cada segundo
# e grava tudo em CSV dentro de resultados/<data>/, para plotar depois.
# Feito para Linux.
#
# Uso:
#   ./monitorar.sh                      mede até apertar Ctrl+C
#   ./monitorar.sh ./stress.sh 50 100   mede enquanto o comando roda, com 3 s antes e depois
#
# Precisa de vmstat (procps), iostat, sar e pidstat (sysstat) e ss (iproute2).
# No Ubuntu/Debian: sudo apt install sysstat procps iproute2

set -u

FOLGA=3                                             # segundos medidos antes e depois do comando
APPS="buffer:8080 produtor:8081 consumidor:8082"    # nome:porta de cada app

# Ponto decimal e hora em 24 h nas saídas do sysstat, para o CSV não quebrar
export LC_ALL=C S_TIME_FORMAT=ISO

for comando in vmstat iostat sar pidstat ss; do
    if ! command -v "$comando" > /dev/null; then
        echo "Falta o comando $comando. No Ubuntu/Debian: sudo apt install sysstat procps iproute2" >&2
        exit 1
    fi
done

pasta="resultados/$(date +%Y-%m-%d_%H-%M-%S)"
mkdir -p "$pasta"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# PID de cada app, achado pela porta em que ele escuta
pids=""
mapa=""
for app in $APPS; do
    nome=${app%%:*}
    porta=${app##*:}
    pid=$(ss -Hltnp "sport = :$porta" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
    if [ -n "$pid" ]; then
        echo "$nome: PID $pid (porta $porta)"
        pids="$pids,$pid"
        mapa="$mapa $pid=$nome"
    else
        echo "Aviso: nada escutando na porta $porta ($nome), ele fica fora de processos.csv" >&2
    fi
done
pids=${pids#,}

{
    echo "inicio: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "maquina: $(uname -srm), $(nproc) CPUs"
    echo "apps (pid=nome):$mapa"
    echo "comando: ${*:-nenhum}"
} > "$pasta/info.txt"

# Lê do stdin um cabeçalho e as linhas de dados; o cabeçalho só entra na primeira vez
gravar_csv() {
    local arquivo=$1 cabecalho
    IFS= read -r cabecalho || return 0
    [ -s "$arquivo" ] || echo "$cabecalho" > "$arquivo"
    cat >> "$arquivo"
}

# Uma amostra: roda as ferramentas em paralelo por 1 s e converte a saída de cada uma em CSV
amostrar() {
    local t
    t=$(date +%s)
    vmstat -n 1 2 > "$tmp/vmstat" &
    local p1=$!
    iostat -dxy 1 1 > "$tmp/iostat" &
    local p2=$!
    sar -n DEV 1 1 > "$tmp/sar" &
    local p3=$!
    local p4=""
    if [ -n "$pids" ]; then
        pidstat -h -u -r -d -p "$pids" 1 1 > "$tmp/pidstat" &
        p4=$!
    fi
    ss -Htan > "$tmp/ss"
    wait $p1 $p2 $p3 $p4

    # vmstat: a 2ª linha é o cabeçalho e a última é a média do último segundo
    awk -v t="$t" '
        NR == 2 { $1 = $1; gsub(/ /, ","); print "tempo," $0 }
        { ultima = $0 }
        END { $0 = ultima; $1 = $1; gsub(/ /, ","); print t "," $0 }
    ' "$tmp/vmstat" | gravar_csv "$pasta/sistema.csv"

    # iostat: uma linha por disco (sem os discos virtuais loop e ram)
    awk -v t="$t" '
        /^Device/ { sub(/:$/, "", $1); $1 = $1; gsub(/ /, ","); print "tempo," $0; lendo = 1; next }
        lendo && NF == 0 { lendo = 0 }
        lendo && $1 !~ /^(loop|ram)/ { $1 = $1; gsub(/ /, ","); print t "," $0 }
    ' "$tmp/iostat" | gravar_csv "$pasta/disco.csv"

    # sar -n DEV: uma linha por interface de rede (lo é o tráfego entre os apps no localhost)
    awk -v t="$t" '
        $1 ~ /^Average/ { exit }
        $2 == "IFACE" { $1 = "tempo"; gsub(/ /, ","); print; lendo = 1; next }
        lendo && NF > 0 { $1 = t; gsub(/ /, ","); print }
    ' "$tmp/sar" | gravar_csv "$pasta/rede.csv"

    # pidstat: uma linha por app, com CPU, memória e disco do processo
    if [ -n "$pids" ]; then
        awk -v t="$t" -v mapa="$mapa" '
            BEGIN { n = split(mapa, pares, " "); for (i = 1; i <= n; i++) { split(pares[i], p, "="); nome[p[1]] = p[2] } }
            $1 ~ /^Average/ { exit }
            /^#/ && !cabecalho {
                sub(/^# */, ""); for (i = 1; i <= NF; i++) if ($i == "PID") col = i
                $1 = "tempo,app"; gsub(/ /, ","); print; cabecalho = 1; next
            }
            cabecalho && NF > 0 && !/^#/ { app = nome[$col]; $1 = t "," app; gsub(/ /, ","); print }
        ' "$tmp/pidstat" | gravar_csv "$pasta/processos.csv"
    fi

    # ss: conexões TCP abertas em cada app (lado de quem recebe, pela porta local)
    awk -v t="$t" -v apps="$APPS" '
        BEGIN {
            n = split(apps, lista, " ")
            for (i = 1; i <= n; i++) { split(lista[i], p, ":"); porta[i] = p[2]; nome[p[2]] = p[1] }
            print "tempo,app,porta,estabelecidas,time_wait,outras"
        }
        {
            local = $4; sub(/.*:/, "", local)
            if (!(local in nome) || $1 == "LISTEN") next
            if ($1 == "ESTAB") estab[local]++; else if ($1 == "TIME-WAIT") tw[local]++; else outras[local]++
        }
        END { for (i = 1; i <= n; i++) { q = porta[i]; print t "," nome[q] "," q "," estab[q] + 0 "," tw[q] + 0 "," outras[q] + 0 } }
    ' "$tmp/ss" | gravar_csv "$pasta/conexoes.csv"
}

evento() {
    echo "$(date +%s),$1" >> "$pasta/eventos.csv"
}

# O laço de medição roda em segundo plano até alguém criar o arquivo "parar"
( while [ ! -e "$tmp/parar" ]; do amostrar; done ) &
medidor=$!

interrompido=0
trap 'interrompido=1' INT
echo "tempo,evento" > "$pasta/eventos.csv"
evento inicio_medicao

if [ $# -gt 0 ]; then
    sleep "$FOLGA"
    evento inicio_comando
    "$@" 2>&1 | tee "$pasta/saida_comando.txt"
    evento fim_comando
    [ "$interrompido" = 1 ] || sleep "$FOLGA"
else
    echo "Medindo... aperte Ctrl+C para parar."
    wait "$medidor"
fi

touch "$tmp/parar"
wait "$medidor"
evento fim_medicao

echo
echo "Resultados em $pasta/"
for arquivo in "$pasta"/*.csv; do
    echo "  $(basename "$arquivo"): $(($(wc -l < "$arquivo") - 1)) linhas"
done
