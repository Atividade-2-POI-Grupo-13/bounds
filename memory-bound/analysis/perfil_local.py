"""Resumo da etapa 3: lê results/local/ e gera tabela (markdown) e gráfico.

Uso: python analysis/perfil_local.py [--aquecimento 21] [--medicao 39]
"""

import argparse
import csv
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PASTA = "results/local"
FIGURA = "docs/img/perfil_local.png"

# Cores e marcadores fixos por cenário (paleta categórica validada, ordem fixa).
ESTILO = {
    "C1": ("#2a78d6", "o"),
    "C2": ("#eb6834", "s"),
    "C3": ("#1baf7a", "^"),
    "C4": ("#eda100", "D"),
}
DESCRICAO = {
    "C1": "1 CPU, 512 MB",
    "C2": "1 CPU, 1 GB",
    "C3": "1 CPU, 2 GB",
    "C4": "2 CPU, 1 GB",
}
TINTA = "#52514e"
GRADE = "#e4e3df"


def ler_recursos(arquivo: str, aquecimento_s: int) -> dict:
    """Memória, swap e CPU do container, só depois do aquecimento."""
    linhas: list[dict] = []
    with open(arquivo) as f:
        for linha in csv.DictReader(f):
            linhas.append(linha)
    if not linhas:
        return {"ram_mb": 0.0, "swap_mb": 0.0, "cpu_pct": 0.0}

    inicio = int(linhas[0]["tempo"]) + aquecimento_s
    ram_max = 0.0
    swap_max = 0.0
    cpu_usec = 0.0
    segundos = 0
    anterior = None
    for linha in linhas:
        if int(linha["tempo"]) < inicio:
            anterior = linha
            continue
        ram_max = max(ram_max, int(linha["memoria_bytes"]) / 1e6)
        swap_max = max(swap_max, int(linha["swap_bytes"]) / 1e6)
        if anterior is not None:
            delta = int(linha["cpu_usec"]) - int(anterior["cpu_usec"])
            # Se o container reiniciou, o contador volta a zero: ignora esse trecho.
            if delta > 0:
                cpu_usec += delta
                segundos += int(linha["tempo"]) - int(anterior["tempo"])
        anterior = linha

    cpu_pct = 0.0
    if segundos > 0:
        cpu_pct = cpu_usec / 1e6 / segundos * 100
    return {"ram_mb": ram_max, "swap_mb": swap_max, "cpu_pct": cpu_pct}


def metrica(k6: dict, nome: str, campo: str) -> float:
    valores = k6["metrics"].get(nome, {})
    return float(valores.get(campo, 0.0))


def ler_nivel(pasta: str, aquecimento_s: int, medicao_s: int) -> dict:
    with open(os.path.join(pasta, "k6.json")) as f:
        k6 = json.load(f)
    with open(os.path.join(pasta, "estado.json")) as f:
        estado = json.load(f)
    linha = {
        "p95_inicio_ms": metrica(k6, "http_req_duration{fase:medicao,name:inicio}", "p(95)"),
        "p95_recalculo_ms": metrica(k6, "http_req_duration{fase:medicao,name:recalculo}", "p(95)"),
        "req_s": metrica(k6, "http_reqs{fase:medicao}", "count") / medicao_s,
        "erro_pct": metrica(k6, "http_req_failed{fase:medicao}", "value") * 100,
        "reinicios": estado["reinicios"],
    }
    linha.update(ler_recursos(os.path.join(pasta, "recursos.csv"), aquecimento_s))
    return linha


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aquecimento", type=int, default=21, help="segundos de aquecimento")
    parser.add_argument("--medicao", type=int, default=39, help="segundos medidos")
    args = parser.parse_args()

    dados: dict[str, list[tuple[int, dict]]] = {}
    for cenario in sorted(os.listdir(PASTA)):
        niveis: list[tuple[int, dict]] = []
        for nome in os.listdir(os.path.join(PASTA, cenario)):
            pasta = os.path.join(PASTA, cenario, nome)
            if not os.path.exists(os.path.join(pasta, "k6.json")):
                continue
            vus = int(nome.replace("vus_", ""))
            niveis.append((vus, ler_nivel(pasta, args.aquecimento, args.medicao)))
        niveis.sort()
        dados[cenario] = niveis

    print("| cenário | usuários | p95 início ms | p95 recálculo ms | req/s | erros % "
          "| RAM máx MB | swap máx MB | CPU média % | reinícios |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for cenario, niveis in dados.items():
        for vus, d in niveis:
            print(f"| {cenario} | {vus} | {d['p95_inicio_ms']:.0f} | {d['p95_recalculo_ms']:.0f} "
                  f"| {d['req_s']:.1f} | {d['erro_pct']:.1f} | {d['ram_mb']:.0f} | {d['swap_mb']:.0f} "
                  f"| {d['cpu_pct']:.0f} | {d['reinicios']} |")

    paineis = [
        ("p95_inicio_ms", "p95 do início de viagem (ms, escala log)", True),
        ("erro_pct", "Requisições com erro (%)", False),
        ("ram_mb", "RAM máxima do container (MB)", False),
        ("swap_mb", "Swap máximo do container (MB)", False),
        ("cpu_pct", "CPU média (% de 1 núcleo)", False),
        ("req_s", "Vazão (req/s)", False),
    ]
    fig, eixos = plt.subplots(3, 2, figsize=(11, 11))
    for (campo, titulo, log), eixo in zip(paineis, eixos.flat):
        for cenario, niveis in dados.items():
            cor, marcador = ESTILO[cenario]
            xs: list[int] = []
            ys: list[float] = []
            for vus, d in niveis:
                xs.append(vus)
                ys.append(d[campo])
            eixo.plot(xs, ys, color=cor, marker=marcador, markersize=6, linewidth=2,
                      label=f"{cenario} ({DESCRICAO[cenario]})")
            if xs:
                eixo.annotate(cenario, (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                              va="center", fontsize=9, color=TINTA)
        eixo.set_title(titulo, fontsize=11, color="#0b0b0b", loc="left")
        eixo.set_xlabel("usuários simultâneos", fontsize=9, color=TINTA)
        if log:
            eixo.set_yscale("log")
        eixo.grid(True, color=GRADE, linewidth=0.8)
        eixo.tick_params(colors=TINTA, labelsize=9)
        for lado in ("top", "right"):
            eixo.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            eixo.spines[lado].set_color(GRADE)
    eixos.flat[0].legend(fontsize=9, frameon=False)
    fig.tight_layout()
    os.makedirs(os.path.dirname(FIGURA), exist_ok=True)
    fig.savefig(FIGURA, dpi=120, facecolor="#fcfcfb")
    print(f"\nFigura: {FIGURA}")


if __name__ == "__main__":
    main()
