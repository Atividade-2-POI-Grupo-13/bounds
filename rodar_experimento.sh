#!/usr/bin/env bash
# Roda, do hospedeiro, os experimentos das 3 aplicacoes na VM do grupo.
# A VM tem as 3 instaladas e nenhuma sobe no boot: cada experimento desliga a VM,
# troca CPU, RAM (e disco), liga, derruba todas e sobe so a sua.
#
# Uso: ./rodar_experimento.sh APLICACAO ACAO
#   APLICACAO: cpu | memory | io
#   ACAO, igual para as 3:
#     listar      mostra os cenarios (vCPUs, RAM, disco)
#     calibrar    passo obrigatorio antes do primeiro cenario neste computador
#     <CENARIO>   roda um cenario (os nomes aparecem em listar)
#     todos       roda todos os cenarios em sequencia (pula os ja feitos)
#     analisar    gera tabelas e graficos dos resultados
#     demo        (so memory) dois niveis curtos, para mostrar ao vivo
#
#   ./rodar_experimento.sh subir APLICACAO   so deixa a aplicacao no ar, sem medir
#   ./rodar_experimento.sh parar             derruba as 3 (a VM continua ligada)
#
# Toda execucao grava a saida em logs/<data>_<aplicacao>_<acao>.log.
# Requer so a VM criada no VirtualBox com o VDI do grupo. Na primeira execucao o
# script configura as portas e o cache de disco, liga a VM, copia a chave ssh e,
# para a memory-bound, instala o k6. Ver COMANDOS.md.
set -euo pipefail
cd "$(dirname "$0")"
source vm/comum.sh

uso() {
    sed -n '5,19p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
}

# ---------------------------------------------------------------- cenarios
# Uma linha por cenario: NOME VCPUS RAM_MB DISCO DESCRICAO
cenarios() {
    case "$1" in
        cpu) cat <<'T'
V1 1 1024 livre referencia
V2 2 1024 livre mais CPU
V3 1 2048 livre mais memoria
V4 2 2048 livre mais CPU e memoria
T
        ;;
        memory) cat <<'T'
C1 1 768 livre menos memoria
C2 1 1024 livre referencia
C3 1 2048 livre mais memoria
C4 2 1024 livre mais CPU
T
        ;;
        io) cat <<'T'
V1 1 1024 livre referencia
V2 1 1024 5M disco lento (5 MB/s)
V3 2 1024 livre mais CPU
V4 1 768 livre menos memoria
T
        ;;
    esac
}

cenario_existe() {
    cenarios "$1" | grep -q "^$2 "
}

listar() {
    printf "%-8s %-6s %-8s %-7s %s\n" cenario vcpus ram_mb disco descricao
    cenarios "$1" | while read -r nome cpus ram disco desc; do
        printf "%-8s %-6s %-8s %-7s %s\n" "$nome" "$cpus" "$ram" "$disco" "$desc"
    done
}

# ---------------------------------------------------------------- cpu-bound
cpu_calibrar() {
    # Mede o tempo de um pedido com 1 vCPU e sugere ITERACOES (cpu-bound/experiments/comum.sh).
    cpu-bound/experiments/preparar_vm.sh 1 1024
    cpu-bound/tools/calibrar_vm.sh
}
cpu_cenario() {
    local nome=$1 cpus=$2 ram=$3
    if [ -e "cpu-bound/results/vm/$nome/resumo.csv" ]; then
        echo "== cpu $nome ja existe em cpu-bound/results/vm/$nome, pulando (apague a pasta para refazer)."
        return
    fi
    cpu-bound/experiments/preparar_vm.sh "$cpus" "$ram"
    cpu-bound/experiments/cenario_vm.sh "$nome"
}
cpu_analisar() {
    (cd cpu-bound && "$PYTHON" analysis/analisar.py results/vm)
}

# ---------------------------------------------------------------- memory-bound
memory_calibrar() {
    # Teste de fumaca (~6 min): mede a VM real e grava recomendacoes em results/fumaca/.
    memory-bound/experiments/teste_fumaca.sh
}
memory_cenario() {
    # run_all.sh pula os niveis que ja tem resultado.
    CENARIOS="$1:$2:$3" memory-bound/experiments/run_all.sh
}
memory_analisar() {
    (cd memory-bound && "$PYTHON" analysis/analyze.py)
}

# ---------------------------------------------------------------- io-bound
# O experimento da io-bound roda dentro da VM (a carga sai do localhost da VM).
io_ligar() {
    desligar_vm
    configurar_vm "$1" "$2"
    limitar_disco "$3"
    ligar_vm
    derrubar_todos
    sleep 20  # o Ubuntu termina de iniciar antes de medir
}
io_calibrar() {
    # Teste rapido: sobe os 3 apps no cenario de referencia e roda uma carga pequena.
    io_ligar 1 1024 livre
    subir io-bound
    na_vm "cd ~/io-bound && ./stress.sh 5 10"
    derrubar_todos
}
io_cenario() {
    local nome=$1
    if ls -d io-bound/resultados/vm/"$nome"_* > /dev/null 2>&1; then
        echo "== io $nome ja existe em io-bound/resultados/vm/, pulando (apague a pasta para refazer)."
        return
    fi
    io_ligar "$2" "$3" "$4"
    na_vm "cd ~/io-bound && ./experimento.sh $nome"
    local pasta
    pasta=$(na_vm 'ls -d ~/io-bound/resultados/*/ | tail -1')
    pasta=${pasta%/}
    mkdir -p io-bound/resultados/vm
    # Prefixo com o cenario, para todos e analisar saberem o que ja foi feito.
    if scp -q -r -P "$PORTA_SSH" "${SSH_OPCOES[@]:2}" "osboxes@localhost:$pasta" \
            "io-bound/resultados/vm/${nome}_$(basename "$pasta")"; then
        echo "Resultados em io-bound/resultados/vm/${nome}_$(basename "$pasta")"
    else
        echo "Aviso: nao consegui copiar $pasta da VM."
        return 1
    fi
}
io_analisar() {
    (cd io-bound && "$PYTHON" plotar.py resultados/vm)
}

# ---------------------------------------------------------------- hospedeiro
# k6 (memory-bound): instala em ~/bin sem root se faltar.
garantir_k6() {
    if [ -z "${K6:-}" ]; then
        if command -v k6 > /dev/null; then K6=k6; else K6=~/bin/k6; fi
    fi
    [ -x "$(command -v "$K6")" ] || memory-bound/experiments/instalar_k6.sh
    export K6
}

# Python com matplotlib e pandas para analisar: cria .venv-analise se o do sistema nao tiver.
PYTHON=python3
garantir_python() {
    python3 -c "import matplotlib, pandas" 2> /dev/null && return 0
    PYTHON="$PWD/.venv-analise/bin/python"
    if ! "$PYTHON" -c "import matplotlib, pandas" 2> /dev/null; then
        echo "Instalando matplotlib e pandas em .venv-analise (uma vez)..."
        python3 -m venv .venv-analise
        "$PYTHON" -m pip install -q matplotlib pandas
    fi
}

# ---------------------------------------------------------------- comum
rodar() {
    local app=$1 acao=$2
    case "$acao" in
        listar) listar "$app" ;;
        calibrar) "${app}_calibrar" ;;
        analisar) garantir_python; "${app}_analisar" ;;
        demo)
            # So a memory-bound tem demonstracao: dois niveis curtos na VM como esta.
            [ "$app" = memory ] || { echo "So a memory-bound tem demo."; exit 1; }
            subir memory-bound
            memory-bound/experiments/demo_rapido.sh ;;
        todos)
            cenarios "$app" | while read -r nome _; do
                echo "======== $app $nome"
                rodar "$app" "$nome" < /dev/null
            done
            echo "Todos os cenarios de $app terminados." ;;
        *)
            cenario_existe "$app" "$acao" || { echo "Cenario desconhecido: $acao"; listar "$app"; exit 1; }
            local nome cpus ram disco
            read -r nome cpus ram disco _ <<< "$(cenarios "$app" | grep "^$acao ")"
            echo "== $app $nome: $cpus vCPU(s), $ram MB, disco $disco"
            case "$app" in
                io) io_cenario "$nome" "$cpus" "$ram" "$disco" ;;
                *) limitar_disco_livre_se_preciso; "${app}_cenario" "$nome" "$cpus" "$ram" ;;
            esac ;;
    esac
}

# O limite de disco da io-bound V2 fica gravado na VM: tira antes das outras
# aplicacoes. Os scripts delas desligam a VM de qualquer jeito.
limitar_disco_livre_se_preciso() {
    desligar_vm
    limitar_disco livre
}

app_de() {
    case "$1" in
        cpu) echo cpu-bound ;;
        memory) echo memory-bound ;;
        io) echo io-bound ;;
        *) uso ;;
    esac
}

[ $# -ge 1 ] || uso
mkdir -p logs
LOG="logs/$(date +%Y-%m-%d_%H-%M-%S)_${1}_${2:-}.log"
case "$1" in
    cpu|memory|io)
        [ $# -eq 2 ] || uso
        [ "$2" = listar ] && { listar "$1"; exit 0; }
        echo "Saida tambem em $LOG"
        {
            if [ "$2" != analisar ]; then
                garantir_vm
                [ "$1" = memory ] && garantir_k6
            fi
            rodar "$1" "$2"
        } 2>&1 | tee "$LOG"
        exit "${PIPESTATUS[0]}" ;;
    subir) [ $# -eq 2 ] || uso; garantir_vm; subir "$(app_de "$2")" ;;
    parar) garantir_vm; derrubar_todos ;;
    *) uso ;;
esac
