"""Tabelas e graficos a partir dos resultados brutos dos cenarios.

Le cada results/<...>/<cenario>/resumo.csv (uma linha por teste, do gerador) e as
metricas por segundo do mesmo cenario: docker_stats.csv (Docker) ou
vbox_stats.csv (VirtualBox). Para cada teste,
recorta o docker stats na janela medida e calcula a CPU media e a memoria maxima
do container. Depois junta as repeticoes de cada (cenario, taxa).

Na VM, tambem le a coleta de dentro dela, quando existe: vmstat.txt (CPU e
memoria vistas pelo Ubuntu) e metrics.txt (fila, threads e memoria da
aplicacao, do /metrics).

Uso: python3 analysis/analisar.py [PASTA_DE_RESULTADOS]   (padrao: results)
Gera, na pasta de resultados: tabela.csv, tabela.md e graficos/*.png.
"""

import json
import re
import sys
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# Cores das series (taxa baixa e taxa alta): slots 1 e 2 da paleta de referencia.
CORES = ["#2a78d6", "#eb6834"]
TINTA = "#3d3d3a"
TINTA_FRACA = "#7a7a75"
GRADE = "#e6e5e0"
UNIDADES_MB = {"B": 1 / 2**20, "KiB": 1 / 1024, "MiB": 1, "GiB": 1024}


def para_mb(texto):
    numero, unidade = re.fullmatch(r"([\d.]+)\s*([KMG]?i?B)", texto.strip()).groups()
    return float(numero) * UNIDADES_MB[unidade]


def ler_vbox_stats(pasta, config):
    """Converte as metricas do VirtualBox para o formato do docker stats.

    CPU/Load vem como percentual do hospedeiro inteiro; multiplicando pelas CPUs
    do hospedeiro, fica "100% = 1 nucleo", como no Docker. User e Kernel sao
    somados, porque o VirtualBox lanca quase todo o tempo da VM como Kernel.
    A memoria e a do processo da VM no hospedeiro (RAM/Usage/Used, em kB).
    """
    cpus_hospedeiro = int(config["cpus do hospedeiro"])
    bruto = pd.read_csv(pasta / "vbox_stats.csv")
    bruto["segundo"] = bruto["epoch"].round()
    tabela = bruto.pivot_table(index="segundo", columns="metrica", values="valor", aggfunc="mean")
    return pd.DataFrame({
        "epoch": tabela.index,
        "cpu_percent": (tabela["CPU/Load/User"] + tabela["CPU/Load/Kernel"]).values * cpus_hospedeiro,
        "memoria_mb": tabela["RAM/Usage/Used"].values / 1024,
    })


def ler_vmstat(pasta, config):
    """vmstat.txt: 'epoch r b swpd free buff cache si so bi bo in cs us sy id wa st', em kB."""
    nomes = ["epoch", "r", "b", "swpd", "free", "buff", "cache", "si", "so",
             "bi", "bo", "in", "cs", "us", "sy", "id", "wa", "st"]
    linhas = []
    for linha in (pasta / "vmstat.txt").read_text().splitlines():
        partes = linha.split()
        if len(partes) == len(nomes) and all(p.isdigit() for p in partes):
            linhas.append([int(p) for p in partes])
    v = pd.DataFrame(linhas, columns=nomes)
    v["epoch"] = v["epoch"] + float(config["diferenca de relogio hospedeiro - vm (s)"])
    total_kb = int(config["memoria total da vm (kB)"])
    nucleos = int(config["nucleos"].split()[0])
    return pd.DataFrame({
        "epoch": v["epoch"],
        # vmstat da a CPU em % de todas as vCPUs; convertido para "100% = 1 nucleo".
        "cpu_vm_percent": (100 - v["id"]) * nucleos,
        "steal_percent": v["st"],
        "memoria_usada_vm_mb": (total_kb - v["free"] - v["buff"] - v["cache"]) / 1024,
        "swap_mb": v["swpd"] / 1024,
    })


def ler_metrics(pasta, config):
    """metrics.txt: um JSON do /metrics por linha (hora da VM)."""
    linhas = []
    for linha in (pasta / "metrics.txt").read_text().splitlines():
        try:
            linhas.append(json.loads(linha))
        except json.JSONDecodeError:
            pass  # leitura que falhou (por exemplo, aplicacao reiniciando)
    m = pd.DataFrame(linhas)
    m["epoch"] = m["epoch"] + float(config["diferenca de relogio hospedeiro - vm (s)"])
    return m


def ler_config_bruta(pasta):
    config = {}
    for linha in (pasta / "config.txt").read_text().splitlines():
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            config[chave.strip()] = valor.strip()
    return config


def ler_config(pasta):
    config = ler_config_bruta(pasta)
    nucleos = int(config["nucleos"].split()[0])
    memoria = re.search(r"memoria: (\S+)", config["nucleos"]).group(1)
    return nucleos, memoria


def ler_cenario(pasta):
    testes = pd.read_csv(pasta / "resumo.csv")
    if (pasta / "docker_stats.csv").exists():
        stats = pd.read_csv(pasta / "docker_stats.csv")
        stats["memoria_mb"] = stats["memoria_uso"].map(para_mb)
    else:
        stats = ler_vbox_stats(pasta, ler_config_bruta(pasta))
    nucleos, memoria = ler_config(pasta)
    config = ler_config_bruta(pasta)
    vmstat = ler_vmstat(pasta, config) if (pasta / "vmstat.txt").exists() else None
    metrics = ler_metrics(pasta, config) if (pasta / "metrics.txt").exists() else None

    linhas = []
    for repeticao, (_, teste) in enumerate(testes.iterrows()):
        def recorte(tabela):
            return tabela[(tabela["epoch"] >= teste["janela_inicio_epoch"])
                          & (tabela["epoch"] <= teste["janela_fim_epoch"])]
        janela = recorte(stats)
        extras = {}
        if vmstat is not None:
            v = recorte(vmstat)
            extras.update({
                "cpu_vm_percent": v["cpu_vm_percent"].mean(),
                "steal_percent": v["steal_percent"].mean(),
                "memoria_usada_vm_mb": v["memoria_usada_vm_mb"].max(),
                "swap_mb": v["swap_mb"].max(),
            })
        if metrics is not None:
            m = recorte(metrics)
            extras.update({
                "fila_max": m["fila"].max(),
                "threads_ocupadas": m["threads_ocupadas"].mean(),
                "rss_app_mb": m["rss_mb"].max(),
            })
        linhas.append({
            "cenario": pasta.name,
            "nucleos": nucleos,
            "memoria": memoria,
            "taxa": teste["taxa"],
            "vazao": teste["vazao"],
            "p50_ms": teste["p50_ms"],
            "p95_ms": teste["p95_ms"],
            "p99_ms": teste["p99_ms"],
            "erros": teste["erros"],
            "sem_resposta_no_fim": teste["sem_resposta_no_fim"],
            # 100% = 1 nucleo inteiro (Docker e VirtualBox convertido).
            "cpu_percent": janela["cpu_percent"].mean(),
            "memoria_max_mb": janela["memoria_mb"].max(),
            "amostras_stats": len(janela),
            **extras,
        })
    return pd.DataFrame(linhas)


def juntar_repeticoes(testes):
    metricas = [c for c in ["vazao", "p50_ms", "p95_ms", "p99_ms", "erros",
                            "sem_resposta_no_fim", "cpu_percent", "memoria_max_mb",
                            "cpu_vm_percent", "steal_percent", "memoria_usada_vm_mb", "swap_mb",
                            "fila_max", "threads_ocupadas", "rss_app_mb"]
                if c in testes.columns]
    grupos = testes.groupby(["cenario", "nucleos", "memoria", "taxa"], sort=True)
    tabela = grupos[metricas].agg(["mean", "min", "max"])
    tabela.columns = [f"{m}_{a}".replace("_mean", "") for m, a in tabela.columns]
    tabela["repeticoes"] = grupos.size()
    return tabela.reset_index()


def tabela_markdown(tabela):
    colunas = [("cenário", lambda t: t.cenario), ("CPU", lambda t: t.nucleos),
               ("memória", lambda t: t.memoria), ("taxa (pedidos/s)", lambda t: f"{t.taxa:g}"),
               ("vazão (respostas/s)", lambda t: f"{t.vazao:.1f}"), ("p50 (ms)", lambda t: f"{t.p50_ms:.0f}"),
               ("p95 (ms)", lambda t: f"{t.p95_ms:.0f}"), ("CPU (%)", lambda t: f"{t.cpu_percent:.0f}"),
               ("memória máx. (MB)", lambda t: f"{t.memoria_max_mb:.0f}"),
               ("sem resposta ao fim", lambda t: f"{t.sem_resposta_no_fim:.0f}")]
    # Coleta de dentro da VM, quando existe.
    if "cpu_vm_percent" in tabela.columns:
        colunas += [("CPU dentro da VM (%)", lambda t: f"{t.cpu_vm_percent:.0f}"),
                    ("memória usada na VM (MB)", lambda t: f"{t.memoria_usada_vm_mb:.0f}"),
                    ("swap (MB)", lambda t: f"{t.swap_mb:.0f}")]
    if "fila_max" in tabela.columns:
        colunas += [("fila máx.", lambda t: f"{t.fila_max:.0f}"),
                    ("memória da aplicação (MB)", lambda t: f"{t.rss_app_mb:.0f}")]
    linhas = ["| " + " | ".join(nome for nome, _ in colunas) + " |",
              "|" + "---|" * len(colunas)]
    for _, t in tabela.iterrows():
        linhas.append("| " + " | ".join(str(valor(t)) for _, valor in colunas) + " |")
    return "\n".join(linhas) + "\n"


def grafico(tabela, metrica, titulo, eixo_y, arquivo, log=False, referencia_taxa=False):
    cenarios = list(dict.fromkeys(tabela["cenario"]))
    taxas = sorted(tabela["taxa"].unique())
    largura = 0.36
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)

    for i, taxa in enumerate(taxas):
        dados = tabela[tabela["taxa"] == taxa].set_index("cenario").loc[cenarios]
        posicoes = [c + (i - (len(taxas) - 1) / 2) * (largura + 0.03) for c in range(len(cenarios))]
        valores = dados[metrica]
        barras = ax.bar(posicoes, valores, largura, color=CORES[i], label=f"{taxa:g} pedidos/s",
                        edgecolor="white", linewidth=1, zorder=3)
        if (dados["repeticoes"] > 1).any():
            ax.errorbar(posicoes, valores,
                        yerr=[valores - dados[f"{metrica}_min"], dados[f"{metrica}_max"] - valores],
                        fmt="none", ecolor=TINTA, elinewidth=1, capsize=3, zorder=4)
        for barra, valor in zip(barras, valores):
            texto = f"{valor:,.0f}".replace(",", ".") if valor >= 100 else f"{valor:.1f}".replace(".", ",")
            ax.annotate(texto, (barra.get_x() + barra.get_width() / 2, barra.get_height()),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom",
                        fontsize=8, color=TINTA)
        if referencia_taxa:
            for p in posicoes:
                ax.hlines(taxa, p - largura / 2, p + largura / 2, colors=TINTA, linestyles="--",
                          linewidth=1, zorder=5)

    rotulos = []
    for c in cenarios:
        linha = tabela[tabela["cenario"] == c].iloc[0]
        rotulos.append(f"{c}\n{linha.nucleos} CPU, {linha.memoria.upper()}B")
    ax.set_xticks(range(len(cenarios)), rotulos, fontsize=9, color=TINTA)
    ax.set_ylabel(eixo_y, fontsize=9, color=TINTA)
    ax.set_title(titulo, fontsize=11, color=TINTA, loc="left")
    if log:
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
            lambda v, _: f"{v:,.0f}".replace(",", ".")))
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.grid(axis="y", color=GRADE, linewidth=0.8, zorder=0)
    ax.tick_params(colors=TINTA_FRACA, labelsize=8)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRADE)
    legenda = ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    if referencia_taxa:
        legenda.set_title("tracejado: taxa enviada", prop={"size": 7})
    fig.tight_layout()
    fig.savefig(arquivo)
    plt.close(fig)


def main():
    base = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
    pastas = sorted(p.parent for p in base.rglob("resumo.csv"))
    if not pastas:
        sys.exit(f"Nenhum resumo.csv em {base}/")

    testes = pd.concat([ler_cenario(p) for p in pastas], ignore_index=True)
    tabela = juntar_repeticoes(testes)
    tabela.to_csv(base / "tabela.csv", index=False, float_format="%.3f")
    (base / "tabela.md").write_text(tabela_markdown(tabela))

    graficos = base / "graficos"
    graficos.mkdir(exist_ok=True)
    grafico(tabela, "vazao", "Vazão por cenário", "respostas/s", graficos / "vazao.png",
            referencia_taxa=True)
    grafico(tabela, "p95_ms", "Tempo de resposta (p95, escala logarítmica)", "ms",
            graficos / "p95.png", log=True)
    grafico(tabela, "cpu_percent", "Uso de CPU (100% = 1 núcleo)", "%",
            graficos / "cpu.png")
    grafico(tabela, "memoria_max_mb", "Memória máxima", "MB",
            graficos / "memoria.png")
    # Coleta de dentro da VM, quando existe.
    if "memoria_usada_vm_mb" in tabela.columns:
        grafico(tabela, "memoria_usada_vm_mb", "Memória usada dentro da VM (máximo)", "MB",
                graficos / "memoria_dentro_vm.png")
        grafico(tabela, "cpu_vm_percent", "CPU vista de dentro da VM (100% = 1 vCPU)", "%",
                graficos / "cpu_dentro_vm.png")
    if "rss_app_mb" in tabela.columns:
        grafico(tabela, "rss_app_mb", "Memória da aplicação (RSS, máximo)", "MB",
                graficos / "memoria_aplicacao.png")
        grafico(tabela, "fila_max", "Pedidos na fila da aplicação (máximo)", "pedidos",
                graficos / "fila.png")

    print(tabela_markdown(tabela))
    print(f"Gerado: {base}/tabela.csv, {base}/tabela.md e {graficos}/*.png")


if __name__ == "__main__":
    main()
