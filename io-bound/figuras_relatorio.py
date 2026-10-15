#!/usr/bin/env python3
"""Figuras e tabela do relatório a partir das rodadas da VM.

Uso: python3 figuras_relatorio.py [pasta]   (padrão: resultados/vm)

Usa a última rodada de cada cenário (pastas V1_..., V2_...) e gera em <pasta>/relatorio/:
  tempo.png, vazao.png, disco.png, fsync.png, iowait.png, cpu.png, memoria.png,
  disco_tempo.png (escrita no disco ao longo da rodada, um painel por cenário)
  tabela.csv (os números da tabela do relatório)
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402

from plotar import Rodada, media, numero  # noqa: E402

# Mesmo estilo dos gráficos da cpu-bound (cpu-bound/analysis/analisar.py).
AZUL = "#2a78d6"
TINTA = "#3d3d3a"
TINTA_FRACA = "#7a7a75"
GRADE = "#e6e5e0"


def br(valor, casas=1):
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def rotulo(rodada):
    disco = ", disco 5MB/s" if rodada.limite_disco != "livre" else ""
    return f"{rodada.cenario}\n{rodada.cpus} CPU, {rodada.memoria.upper()}B{disco}"


def fsync_por_s(rodada):
    """Pedidos de flush por segundo (iostat f/s), somados entre os discos, durante a carga."""
    serie = rodada.serie(rodada.durante_stress(rodada.disco), lambda l: numero(l.get("f/s")))
    return media([v for _, v in serie])


def util_disco(rodada):
    """Ocupação do disco (iostat %util), média durante a carga."""
    serie = rodada.serie(rodada.durante_stress(rodada.disco), lambda l: numero(l.get("%util")))
    return media([v for _, v in serie])


def estilo(ax):
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRADE, linewidth=0.8, zorder=0)
    ax.tick_params(colors=TINTA_FRACA, labelsize=8)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRADE)


def barras(rodadas, valores, titulo, eixo_y, arquivo, casas=1, capacidade=None):
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    largura = 0.5
    posicoes = range(len(rodadas))
    barras_ = ax.bar(posicoes, valores, largura, color=AZUL, edgecolor="white", linewidth=1, zorder=3)
    for barra, valor in zip(barras_, valores):
        ax.annotate(br(valor, casas), (barra.get_x() + barra.get_width() / 2, barra.get_height()),
                    xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8, color=TINTA)
    if capacidade:
        for p, c in zip(posicoes, capacidade):
            ax.hlines(c, p - largura / 2, p + largura / 2, colors=TINTA, linestyles="--", linewidth=1, zorder=5)
    ax.set_xticks(list(posicoes), [rotulo(r) for r in rodadas], fontsize=9, color=TINTA)
    ax.set_ylabel(eixo_y, fontsize=9, color=TINTA)
    ax.set_title(titulo, fontsize=11, color=TINTA, loc="left")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: br(v, 0)))
    ax.margins(y=0.12)
    estilo(ax)
    fig.tight_layout()
    fig.savefig(arquivo)
    plt.close(fig)


def disco_no_tempo(rodadas, arquivo):
    fig, eixos = plt.subplots(len(rodadas), 1, figsize=(7.5, 1.5 * len(rodadas) + 0.6), dpi=150,
                              sharex=True, sharey=True)
    for eixo, rodada in zip(eixos, rodadas):
        inicio, fim = rodada.eventos.get("inicio_comando"), rodada.eventos.get("fim_comando")
        x, y = zip(*rodada.disco_mb_s(rodada.disco))
        if inicio is not None and fim is not None:
            eixo.axvspan(inicio - rodada.inicio, fim - rodada.inicio, color="#f0efeb", zorder=0, linewidth=0)
        eixo.plot(x, y, color=AZUL, linewidth=1.5, zorder=3)
        eixo.set_title(rotulo(rodada).replace("\n", " (") + f"): {rodada.tempo} s", fontsize=9, color=TINTA,
                       loc="left")
        eixo.set_ylabel("MB/s", fontsize=8, color=TINTA)
        estilo(eixo)
    eixos[-1].set_xlabel("segundos", fontsize=9, color=TINTA)
    fig.tight_layout()
    fig.savefig(arquivo)
    plt.close(fig)


def main():
    raiz = Path(sys.argv[1] if len(sys.argv) > 1 else "resultados/vm")
    ultimas = {}
    for pasta in sorted(p for p in raiz.iterdir() if p.is_dir() and (p / "info.txt").exists()):
        rodada = Rodada(pasta)
        ultimas[rodada.cenario] = rodada
    rodadas = [ultimas[c] for c in sorted(ultimas)]
    destino = raiz / "relatorio"
    destino.mkdir(exist_ok=True)

    resumos = [r.resumo() for r in rodadas]
    vazao = [r.consumidos / r.tempo if r.tempo else 0 for r in rodadas]  # jobs que chegaram ao fim
    fsync = [fsync_por_s(r) for r in rodadas]
    util = [util_disco(r) for r in rodadas]
    limite_cpu = [(numero(r.cpus) * 100, "tracejado: limite de CPU do cenário") for r in rodadas]

    barras(rodadas, [r.tempo for r in rodadas], "Tempo para concluir a carga", "segundos",
           destino / "tempo.png", casas=0)
    barras(rodadas, vazao, "Vazão por cenário", "jobs/s", destino / "vazao.png")
    barras(rodadas, [s["disco_escrita_mb_s"] for s in resumos], "Escrita no disco (média durante a carga)",
           "MB/s", destino / "disco.png")
    barras(rodadas, fsync, "Flushes no disco (média durante a carga)", "flushes/s", destino / "fsync.png", casas=0)
    barras(rodadas, [s["iowait_pct"] for s in resumos], "CPU esperando o disco (iowait)", "% do tempo",
           destino / "iowait.png")
    barras(rodadas, [s["cpu_apps_pct"] for s in resumos], "CPU usada pelos três serviços", "% (100% = 1 núcleo)",
           destino / "cpu.png", capacidade=[numero(r.cpus) * 100 for r in rodadas])
    barras(rodadas, [s["memoria_apps_max_mb"] for s in resumos], "Memória máxima dos três serviços (RSS)", "MB",
           destino / "memoria.png", casas=0)
    disco_no_tempo(rodadas, destino / "disco_tempo.png")

    with open(destino / "tabela.csv", "w", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["cenario", "cpus", "memoria", "disco", "completa", "tempo_s", "jobs_s",
                           "disco_mb_s", "fsync_s", "util_disco_pct", "iowait_pct", "cpu_apps_pct",
                           "rede_lo_mb_s", "memoria_max_mb", "recusas_cheio", "recusas_vazio", "pasta"])
        for r, s, v, fs, u in zip(rodadas, resumos, vazao, fsync, util):
            escritor.writerow([r.cenario, r.cpus, r.memoria, r.limite_disco, s["completa"], r.tempo, round(v, 1),
                               s["disco_escrita_mb_s"], round(fs, 1), round(u, 1), s["iowait_pct"],
                               s["cpu_apps_pct"], s["rede_lo_mb_s"], s["memoria_apps_max_mb"],
                               r.cheio, r.vazio, r.pasta.name])
    print(f"Figuras e tabela em {destino}/")


if __name__ == "__main__":
    main()
