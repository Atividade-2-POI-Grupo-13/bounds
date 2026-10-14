#!/usr/bin/env python3
"""Gera os gráficos e o resumo a partir das pastas criadas pelo monitorar.sh.

Uso: python3 plotar.py [pasta_de_resultados]   (padrão: resultados)

Gera:
  <rodada>/graficos.png      disco, rede e CPU ao longo de uma rodada
  resultados/comparacao.png  os cenários lado a lado
  resultados/resumo.csv      uma linha por rodada, com os números

Precisa de matplotlib (o container do experimento.sh já tem).
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Uma cor por cenário, sempre na mesma ordem (paleta segura para daltonismo)
CORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
AZUL = CORES[0]
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
FAIXA_STRESS = "#efeeea"

# Nome curto de cada cenário pronto do experimento.sh
APELIDOS = {
    ("V1", "1", "1024m", "livre"): "referência",
    ("V2", "1", "1024m", "5mb"): "disco lento",
    ("V3", "2", "1024m", "livre"): "mais CPU",
    ("V4", "1", "768m", "livre"): "menos memória",
}

plt.rcParams.update({
    "font.size": 11,
    "axes.edgecolor": TEXTO_SECUNDARIO,
    "axes.labelcolor": TEXTO_SECUNDARIO,
    "axes.titlecolor": TEXTO,
    "axes.titlesize": 12,
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": "#e4e3df",
    "xtick.color": TEXTO_SECUNDARIO,
    "ytick.color": TEXTO_SECUNDARIO,
    "lines.linewidth": 2,
    "figure.facecolor": "white",
    "savefig.dpi": 150,
})


def ler_csv(arquivo):
    if not arquivo.exists():
        return []
    with open(arquivo, newline="") as f:
        return list(csv.DictReader(f))


def numero(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def media(valores):
    return sum(valores) / len(valores) if valores else 0.0


def br(valor):
    """Número no formato brasileiro: 1.234 ou 5,2"""
    return f"{valor:,.0f}".replace(",", ".") if valor >= 100 else f"{valor:.1f}".replace(".", ",")


class Rodada:
    """Uma pasta de resultados: os CSVs, os eventos e o que o stress test imprimiu."""

    def __init__(self, pasta):
        self.pasta = pasta
        self.sistema = ler_csv(pasta / "sistema.csv")
        self.disco = ler_csv(pasta / "disco.csv")
        self.rede = ler_csv(pasta / "rede.csv")
        self.processos = ler_csv(pasta / "processos.csv")
        self.eventos = {e["evento"]: int(e["tempo"]) for e in ler_csv(pasta / "eventos.csv")}
        self.inicio = self.eventos.get("inicio_medicao", 0)

        info = (pasta / "info.txt").read_text() if (pasta / "info.txt").exists() else ""
        achado = re.search(r"^cenario: (\S+) \((.*)\)$", info, re.M)
        self.cenario = achado.group(1) if achado else pasta.name
        limites = dict(re.findall(r"(\w+)=([^,)]+)", achado.group(2))) if achado else {}
        self.cpus = limites.get("cpus", "")
        self.memoria = limites.get("memoria", "")
        self.limite_disco = limites.get("disco", "")
        achado = re.search(r"stress\.sh (\d+) (\d+)", info)
        self.clientes, self.jobs = (int(achado.group(1)), int(achado.group(2))) if achado else (0, 0)

        saida = (pasta / "saida_comando.txt").read_text() if (pasta / "saida_comando.txt").exists() else ""
        achado = re.search(r"produtor:\s+(\d+) de (\d+) jobs, buffer cheio (\d+)", saida)
        self.produzidos, self.total, self.cheio = map(int, achado.groups()) if achado else (0, 0, 0)
        achado = re.search(r"consumidor:\s+(\d+) de \d+ jobs, buffer vazio (\d+)", saida)
        self.consumidos, self.vazio = map(int, achado.groups()) if achado else (0, 0)
        achado = re.search(r"tempo total: (\d+) s", saida)
        self.tempo = int(achado.group(1)) if achado else 0
        self.completa = self.total > 0 and self.produzidos == self.total and self.consumidos == self.total

    def nome(self):
        """Ex.: "C2 · disco lento"; um cenário mudado na mão mostra os próprios limites."""
        apelido = APELIDOS.get((self.cenario, self.cpus, self.memoria, self.limite_disco))
        if apelido:
            return f"{self.cenario} · {apelido}"
        return f"{self.cenario} · {self.cpus} CPU, {self.memoria}, disco {self.limite_disco}" if self.cpus else self.cenario

    def durante_stress(self, linhas):
        """Só as linhas medidas enquanto o stress test rodava."""
        inicio, fim = self.eventos.get("inicio_comando"), self.eventos.get("fim_comando")
        if inicio is None or fim is None:
            return linhas
        return [l for l in linhas if inicio <= int(l["tempo"]) < fim]

    def serie(self, linhas, valor):
        """Soma o valor das linhas de cada segundo: [(segundos desde o início, total)]."""
        por_tempo = defaultdict(float)
        for linha in linhas:
            por_tempo[int(linha["tempo"])] += valor(linha)
        return [(t - self.inicio, v) for t, v in sorted(por_tempo.items())]

    def disco_mb_s(self, linhas):
        return self.serie(linhas, lambda l: numero(l.get("wkB/s")) / 1024)

    def rede_mb_s(self, linhas):
        return self.serie([l for l in linhas if l.get("IFACE") == "lo"], lambda l: numero(l.get("rxkB/s")) / 1024)

    def cpu_apps(self, linhas):
        return self.serie(linhas, lambda l: numero(l.get("%CPU")))

    def resumo(self):
        valores = lambda serie: [v for _, v in serie]  # noqa: E731
        memoria = self.serie(self.processos, lambda l: numero(l.get("RSS")) / 1024)
        return {
            "pasta": self.pasta.name,
            "cenario": self.cenario,
            "cpus": self.cpus,
            "memoria": self.memoria,
            "disco": self.limite_disco,
            "clientes": self.clientes,
            "jobs": self.jobs,
            "completa": "sim" if self.completa else "nao",
            "tempo_s": self.tempo,
            "recusas_cheio": self.cheio,
            "recusas_vazio": self.vazio,
            "disco_escrita_mb_s": round(media(valores(self.disco_mb_s(self.durante_stress(self.disco)))), 2),
            "iowait_pct": round(media([numero(l.get("wa")) for l in self.durante_stress(self.sistema)]), 2),
            "cpu_apps_pct": round(media(valores(self.cpu_apps(self.durante_stress(self.processos)))), 1),
            "rede_lo_mb_s": round(media(valores(self.rede_mb_s(self.durante_stress(self.rede)))), 1),
            "memoria_apps_max_mb": round(max(valores(memoria), default=0), 0),
        }


def graficos_da_rodada(rodada):
    """graficos.png: disco, rede e CPU ao longo do tempo, um embaixo do outro."""
    paineis = [
        ("Quanto foi gravado no disco (MB por segundo)", rodada.disco_mb_s(rodada.disco)),
        ("Quanto passou pela rede entre os apps (MB por segundo)", rodada.rede_mb_s(rodada.rede)),
        ("Quanto de CPU os três apps usaram (%)", rodada.cpu_apps(rodada.processos)),
    ]
    fig, eixos = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    fig.suptitle(f"{rodada.nome()}: {rodada.tempo} s para concluir os jobs\n"
                 "A faixa cinza é o período do stress test.",
                 x=0.06, ha="left", fontsize=13, color=TEXTO)

    inicio, fim = rodada.eventos.get("inicio_comando"), rodada.eventos.get("fim_comando")
    for eixo, (titulo, serie) in zip(eixos, paineis):
        if serie:
            x, y = zip(*serie)
            eixo.plot(x, y, color=AZUL)
        eixo.set_title(titulo)
        eixo.set_ylim(bottom=0)
        if inicio is not None and fim is not None:
            eixo.axvspan(inicio - rodada.inicio, fim - rodada.inicio, color=FAIXA_STRESS, zorder=0)

    # Linha do limite de CPU do cenário: mostra quanto sobrou
    if rodada.cpus:
        limite = numero(rodada.cpus) * 100
        eixos[2].axhline(limite, color=TEXTO_SECUNDARIO, linestyle="--", linewidth=1.2)
        eixos[2].annotate(f"limite do cenário ({rodada.cpus} CPU)", xy=(1, limite), xycoords=("axes fraction", "data"),
                          xytext=(0, 4), textcoords="offset points", ha="right", color=TEXTO_SECUNDARIO, fontsize=10)
        eixos[2].set_ylim(0, limite * 1.2)

    eixos[2].set_xlabel("segundos")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(rodada.pasta / "graficos.png")
    plt.close(fig)


def comparacao(rodadas, destino):
    """comparacao.png: três perguntas, uma barra por cenário (média das rodadas)."""
    grupos = defaultdict(list)
    for rodada in rodadas:
        grupos[(rodada.cenario, rodada.nome(), rodada.clientes, rodada.jobs)].append(rodada.resumo())
    if not grupos:
        return
    chaves = sorted(grupos)
    rotulos = [nome.replace(" · ", "\n", 1) for _, nome, _, _ in chaves]
    cores = [CORES[i] if i < len(CORES) else TEXTO_SECUNDARIO for i in range(len(chaves))]

    perguntas = [
        ("tempo_s", "Quanto tempo levou (s)"),
        ("disco_escrita_mb_s", "Quanto gravou no disco (MB/s)"),
        ("iowait_pct", "Quanto a CPU ficou esperando o disco (%)"),
    ]
    fig, eixos = plt.subplots(1, 3, figsize=(14, 5))
    for eixo, (campo, titulo) in zip(eixos, perguntas):
        medias = [media([float(r[campo]) for r in grupos[c]]) for c in chaves]
        barras = eixo.bar(range(len(chaves)), medias, color=cores, width=0.6)
        eixo.bar_label(barras, labels=[br(m) for m in medias], padding=3, color=TEXTO)
        eixo.set_title(titulo)
        eixo.set_xticks(range(len(chaves)), rotulos)
        eixo.grid(axis="x", visible=False)
        eixo.margins(y=0.15)

    total = sum(len(v) for v in grupos.values())
    subtitulo = "Cada barra é a média das rodadas do cenário." if total > len(grupos) else ""
    fig.suptitle(f"Comparação dos cenários\n{subtitulo}".strip(), x=0.04, ha="left", fontsize=13, color=TEXTO)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(destino)
    plt.close(fig)


def main():
    raiz = Path(sys.argv[1] if len(sys.argv) > 1 else "resultados")
    pastas = sorted(p for p in raiz.iterdir() if (p / "eventos.csv").exists())
    if not pastas:
        print(f"Nenhuma rodada encontrada em {raiz}/")
        return

    rodadas = [Rodada(pasta) for pasta in pastas]
    for rodada in rodadas:
        graficos_da_rodada(rodada)
        if not rodada.completa:
            print(f"Aviso: {rodada.pasta.name} não concluiu todos os jobs e fica fora da comparação")

    resumos = [rodada.resumo() for rodada in rodadas]
    with open(raiz / "resumo.csv", "w", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(resumos[0]))
        escritor.writeheader()
        escritor.writerows(resumos)

    comparacao([r for r in rodadas if r.completa], raiz / "comparacao.png")
    print(f"Gráficos: {raiz}/<rodada>/graficos.png e {raiz}/comparacao.png; números em {raiz}/resumo.csv")


if __name__ == "__main__":
    main()
