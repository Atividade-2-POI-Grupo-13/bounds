"""Análise dos experimentos na VM (etapa 7). Roda no Mac.

Lê results/raw/ (gerado por experiments/run_all.sh) e gera:
  results/resumo.csv        uma linha por cenário, endpoint, usuários e repetição
  results/graficos/*.png    uma linha por cenário, eixo X = usuários simultâneos,
                            média entre repetições com barra de desvio padrão
  results/observacoes.md    pontos de degradação detectados automaticamente

Uso: python analysis/analyze.py [--pasta results]
"""

import argparse
import csv
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Paleta categórica validada, em ordem fixa; marcadores diferentes para quem não distingue cor.
CORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
MARCADORES = ["o", "s", "^", "D", "v", "P", "X", "*"]
TINTA = "#52514e"
TITULO = "#0b0b0b"
GRADE = "#e4e3df"
FUNDO = "#fcfcfb"


# ---------- leitura dos arquivos de um nível ----------

def ler_chave_valor(arquivo: str) -> dict[str, str]:
    """Lê linhas "chave=valor" (várias por linha, separadas por espaço)."""
    dados: dict[str, str] = {}
    if not os.path.exists(arquivo):
        return dados
    with open(arquivo) as f:
        for linha in f:
            for parte in linha.split():
                if "=" in parte:
                    chave, valor = parte.split("=", 1)
                    dados[chave] = valor
    return dados


def ram_total_mb(arquivo_vm: str) -> float:
    """RAM total da VM, da linha "Mem:" do free -m gravado por cenario.sh."""
    if not os.path.exists(arquivo_vm):
        return 0.0
    with open(arquivo_vm) as f:
        for linha in f:
            if linha.startswith("Mem:"):
                return float(linha.split()[1])
    return 0.0


def ler_k6(arquivo: str, medicao_s: float) -> dict:
    with open(arquivo) as f:
        metricas = json.load(f)["metrics"]
    duracao = metricas.get("http_req_duration{fase:medicao}", {})
    falhas = metricas.get("http_req_failed{fase:medicao}", {})
    requisicoes = metricas.get("http_reqs{fase:medicao}", {})
    linha = {
        "lat_media_ms": duracao.get("avg", math.nan),
        "lat_p50_ms": duracao.get("med", math.nan),
        "lat_p95_ms": duracao.get("p(95)", math.nan),
        "lat_p99_ms": duracao.get("p(99)", math.nan),
        "req_s": requisicoes.get("count", 0) / medicao_s,
        "erro_pct": falhas.get("value", math.nan) * 100,
    }
    # p95 de cada tipo de requisição (inicio, recalculo, rota, alcance).
    prefixo = "http_req_duration{fase:medicao,name:"
    for nome, valores in metricas.items():
        if nome.startswith(prefixo):
            tipo = nome[len(prefixo):-1]
            linha[f"p95_{tipo}_ms"] = valores.get("p(95)", math.nan)
    return linha


def ler_vmstat(arquivo: str, aquecimento_s: int, total_mb: float) -> dict:
    """CPU, memória usada e swap da VM, só nas amostras depois do aquecimento."""
    cpus: list[float] = []
    memorias: list[float] = []
    swap_max = 0.0
    amostra = 0
    if os.path.exists(arquivo):
        with open(arquivo) as f:
            for linha in f:
                partes = linha.split()
                # Cabeçalhos do vmstat começam com texto; amostras começam com número.
                if not partes or not partes[0].isdigit():
                    continue
                amostra += 1
                if amostra <= aquecimento_s:
                    continue
                swpd, livre, buff, cache = (int(partes[2]), int(partes[3]), int(partes[4]), int(partes[5]))
                ocioso = int(partes[14])
                cpus.append(100 - ocioso)
                if total_mb > 0:
                    memorias.append(total_mb - (livre + buff + cache) / 1024)
                swap_max = max(swap_max, swpd / 1024)
    return {
        "cpu_media_pct": media(cpus),
        "cpu_max_pct": max(cpus) if cpus else math.nan,
        "mem_media_mb": media(memorias),
        "mem_max_mb": max(memorias) if memorias else math.nan,
        "swap_max_mb": swap_max,
    }


def ler_rss_max(arquivo: str) -> float:
    """Maior RSS do processo visto pelo /metrics (linhas "tempo json")."""
    maior = math.nan
    if not os.path.exists(arquivo):
        return maior
    with open(arquivo) as f:
        for linha in f:
            partes = linha.split(" ", 1)
            if len(partes) < 2:
                continue
            try:
                rss = json.loads(partes[1]).get("rss_mb")
            except json.JSONDecodeError:
                continue
            if rss is not None and (math.isnan(maior) or rss > maior):
                maior = rss
    return maior


def media(valores: list[float]) -> float:
    if not valores:
        return math.nan
    return sum(valores) / len(valores)


def desvio(valores: list[float]) -> float:
    """Desvio padrão amostral (0 com uma repetição só)."""
    if len(valores) < 2:
        return 0.0
    m = media(valores)
    soma = 0.0
    for v in valores:
        soma += (v - m) ** 2
    return math.sqrt(soma / (len(valores) - 1))


# ---------- consolidação ----------

def ler_tudo(pasta_raw: str, aquecimento_s: int, medicao_s: float) -> list[dict]:
    linhas: list[dict] = []
    for cenario in sorted(os.listdir(pasta_raw)):
        pasta_cenario = os.path.join(pasta_raw, cenario)
        if not os.path.isdir(pasta_cenario):
            continue
        total_mb = ram_total_mb(os.path.join(pasta_cenario, "vm.txt"))
        for endpoint in sorted(os.listdir(pasta_cenario)):
            pasta_endpoint = os.path.join(pasta_cenario, endpoint)
            if not os.path.isdir(pasta_endpoint):
                continue
            for nivel in os.listdir(pasta_endpoint):
                for rep in os.listdir(os.path.join(pasta_endpoint, nivel)):
                    pasta = os.path.join(pasta_endpoint, nivel, rep)
                    if not os.path.exists(os.path.join(pasta, "k6.json")):
                        continue
                    estado = ler_chave_valor(os.path.join(pasta, "estado.txt"))
                    linha = {
                        "cenario": cenario,
                        "endpoint": endpoint,
                        "vus": int(nivel.replace("vus_", "")),
                        "repeticao": int(rep.replace("rep_", "")),
                        "ram_vm_mb": total_mb,
                    }
                    linha.update(ler_k6(os.path.join(pasta, "k6.json"), medicao_s))
                    linha.update(ler_vmstat(os.path.join(pasta, "vmstat.txt"), aquecimento_s, total_mb))
                    linha["rss_max_mb"] = ler_rss_max(os.path.join(pasta, "metrics.txt"))
                    linha["reinicios"] = estado.get("reinicios", "")
                    linha["mensagens_oom"] = estado.get("mensagens_oom", "")
                    linhas.append(linha)
    linhas.sort(key=lambda l: (l["cenario"], l["endpoint"], l["vus"], l["repeticao"]))
    return linhas


def salvar_csv(linhas: list[dict], arquivo: str) -> None:
    colunas: list[str] = []
    for linha in linhas:
        for chave in linha:
            if chave not in colunas:
                colunas.append(chave)
    with open(arquivo, "w", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas)
        escritor.writeheader()
        for linha in linhas:
            arredondada: dict = {}
            for chave, valor in linha.items():
                if isinstance(valor, float):
                    arredondada[chave] = "" if math.isnan(valor) else round(valor, 2)
                else:
                    arredondada[chave] = valor
            escritor.writerow(arredondada)


def numero(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return math.nan


def agregar(linhas: list[dict], endpoint: str, campo: str) -> dict[str, list[tuple[int, float, float]]]:
    """cenário -> [(usuários, média, desvio)] entre as repetições."""
    valores: dict[str, dict[int, list[float]]] = {}
    for linha in linhas:
        if linha["endpoint"] != endpoint:
            continue
        v = numero(linha.get(campo))
        if math.isnan(v):
            continue
        porcenario = valores.setdefault(linha["cenario"], {})
        porcenario.setdefault(linha["vus"], []).append(v)
    resultado: dict[str, list[tuple[int, float, float]]] = {}
    for cenario, niveis in valores.items():
        pontos: list[tuple[int, float, float]] = []
        for vus in sorted(niveis):
            pontos.append((vus, media(niveis[vus]), desvio(niveis[vus])))
        resultado[cenario] = pontos
    return resultado


# ---------- gráficos ----------

def estilizar(eixo, titulo: str, rotulo_x: str) -> None:
    eixo.set_title(titulo, fontsize=11, color=TITULO, loc="left")
    eixo.set_xlabel(rotulo_x, fontsize=9, color=TINTA)
    eixo.grid(True, color=GRADE, linewidth=0.8)
    eixo.tick_params(colors=TINTA, labelsize=9)
    for lado in ("top", "right"):
        eixo.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        eixo.spines[lado].set_color(GRADE)


def grafico_linhas(linhas: list[dict], endpoint: str, campo: str, titulo: str, arquivo: str,
                   cenarios: list[str], log: bool = False) -> None:
    dados = agregar(linhas, endpoint, campo)
    if not dados:
        return
    fig, eixo = plt.subplots(figsize=(7, 4.2))
    for cenario, pontos in dados.items():
        i = cenarios.index(cenario)
        xs: list[int] = []
        ys: list[float] = []
        erros: list[float] = []
        for vus, m, d in pontos:
            xs.append(vus)
            ys.append(m)
            erros.append(d)
        eixo.errorbar(xs, ys, yerr=erros, color=CORES[i], marker=MARCADORES[i], markersize=6,
                      linewidth=2, capsize=3, label=cenario)
        eixo.annotate(cenario, (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                      va="center", fontsize=9, color=TINTA)
    if log:
        eixo.set_yscale("log")
    estilizar(eixo, titulo, "usuários simultâneos")
    eixo.legend(fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(arquivo, dpi=120, facecolor=FUNDO)
    plt.close(fig)


def grafico_barras(linhas: list[dict], endpoint: str, cenarios_comparados: list[str],
                   cenarios: list[str], arquivo: str) -> int | None:
    """Barras de p95 e erro no maior nível de usuários comum aos cenários comparados."""
    niveis_por_cenario: list[set[int]] = []
    for cenario in cenarios_comparados:
        niveis: set[int] = set()
        for linha in linhas:
            if linha["endpoint"] == endpoint and linha["cenario"] == cenario:
                niveis.add(linha["vus"])
        niveis_por_cenario.append(niveis)
    if not niveis_por_cenario or not all(niveis_por_cenario):
        return None
    comuns = set.intersection(*niveis_por_cenario)
    if not comuns:
        return None
    nivel = max(comuns)

    paineis = [("lat_p95_ms", "p95 (ms)"), ("erro_pct", "Erros (%)"), ("mem_max_mb", "Memória usada máx (MB)")]
    fig, eixos = plt.subplots(1, len(paineis), figsize=(11, 3.8))
    for (campo, titulo), eixo in zip(paineis, eixos):
        alturas: list[float] = []
        desvios: list[float] = []
        cores: list[str] = []
        for cenario in cenarios_comparados:
            valores: list[float] = []
            for linha in linhas:
                if linha["endpoint"] == endpoint and linha["cenario"] == cenario and linha["vus"] == nivel:
                    valores.append(numero(linha.get(campo)))
            alturas.append(media(valores))
            desvios.append(desvio(valores))
            cores.append(CORES[cenarios.index(cenario)])
        posicoes = list(range(len(cenarios_comparados)))
        eixo.bar(posicoes, alturas, yerr=desvios, color=cores, width=0.6, capsize=3,
                 edgecolor=FUNDO, linewidth=2, ecolor=TINTA)
        eixo.set_xticks(posicoes, cenarios_comparados)
        for x, altura in zip(posicoes, alturas):
            if not math.isnan(altura):
                eixo.annotate(f"{altura:.0f}", (x, altura), xytext=(0, 4), textcoords="offset points",
                              ha="center", fontsize=9, color=TINTA)
        estilizar(eixo, titulo, "")
        eixo.grid(False, axis="x")
    fig.suptitle(f"{endpoint}: comparação com {nivel} usuários", fontsize=11, color=TITULO, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(arquivo, dpi=120, facecolor=FUNDO)
    plt.close(fig)
    return nivel


# ---------- observações ----------

def usuarios(n: int) -> str:
    if n == 1:
        return "1 usuário"
    return f"{n} usuários"


def observacoes(linhas: list[dict], endpoints: list[str], cenarios: list[str]) -> list[str]:
    texto: list[str] = ["# Observações automáticas", "",
                        "Gerado por `analysis/analyze.py`. Médias entre repetições.", ""]
    for endpoint in endpoints:
        texto.append(f"## {endpoint}")
        texto.append("")
        p95 = agregar(linhas, endpoint, "lat_p95_ms")
        erro = agregar(linhas, endpoint, "erro_pct")
        swap = agregar(linhas, endpoint, "swap_max_mb")
        cpu = agregar(linhas, endpoint, "cpu_media_pct")
        reinicios = agregar(linhas, endpoint, "reinicios")
        for cenario in cenarios:
            if cenario not in p95:
                continue
            base_vus, base_p95, _ = p95[cenario][0]
            cpu_por_vus: dict[int, float] = {}
            for vus, m, _ in cpu.get(cenario, []):
                cpu_por_vus[vus] = m

            def primeiro(serie: dict, limite: float) -> int | None:
                for vus, m, _ in serie.get(cenario, []):
                    if m > limite:
                        return vus
                return None

            achados: list[str] = []
            nivel = primeiro(p95, 5 * base_p95)
            if nivel is not None:
                frase = (f"p95 passa de 5x a linha de base ({base_p95:.0f} ms com {usuarios(base_vus)}) "
                         f"a partir de {usuarios(nivel)}")
                cpu_nivel = cpu_por_vus.get(nivel, math.nan)
                if not math.isnan(cpu_nivel):
                    frase += f", com CPU média de {cpu_nivel:.0f}%"
                achados.append(frase)
            nivel = primeiro(swap, 50)
            if nivel is not None:
                achados.append(f"swap acima de 50 MB a partir de {usuarios(nivel)}")
            nivel = primeiro(erro, 1)
            if nivel is not None:
                achados.append(f"erros acima de 1% a partir de {usuarios(nivel)}")
            nivel = primeiro(reinicios, 0)
            if nivel is not None:
                achados.append(f"processo morto por falta de memória a partir de {usuarios(nivel)}")
            if not achados:
                achados.append("sem degradação detectada nos níveis testados")
            texto.append(f"- **{cenario}:** " + "; ".join(achados) + ".")
        texto.append("")
    return texto


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta", default="results")
    args = parser.parse_args()

    pasta_raw = os.path.join(args.pasta, "raw")
    execucao = ler_chave_valor(os.path.join(pasta_raw, "execucao.txt"))
    aquecimento_s = int(execucao.get("AQUECIMENTO_S", "35"))
    medicao_s = float(execucao.get("MEDICAO_S", "60"))

    linhas = ler_tudo(pasta_raw, aquecimento_s, medicao_s)
    if not linhas:
        print(f"nenhum resultado em {pasta_raw}")
        return
    salvar_csv(linhas, os.path.join(args.pasta, "resumo.csv"))

    cenarios: list[str] = []
    endpoints: list[str] = []
    for linha in linhas:
        if linha["cenario"] not in cenarios:
            cenarios.append(linha["cenario"])
        if linha["endpoint"] not in endpoints:
            endpoints.append(linha["endpoint"])
    cenarios.sort()

    pasta_graficos = os.path.join(args.pasta, "graficos")
    os.makedirs(pasta_graficos, exist_ok=True)
    graficos = [
        ("lat_p95_ms", "Latência p95 (ms, escala log)", "p95", True),
        ("req_s", "Vazão (req/s)", "vazao", False),
        ("erro_pct", "Requisições com erro (%)", "erros", False),
        ("mem_max_mb", "Memória usada máxima da VM (MB)", "memoria", False),
        ("swap_max_mb", "Swap usado máximo (MB)", "swap", False),
        ("cpu_media_pct", "CPU média da VM (%)", "cpu", False),
        ("rss_max_mb", "RSS máximo do processo (MB)", "rss", False),
    ]
    # p95 de cada tipo de requisição (por exemplo inicio e recalculo, no endpoint viagem).
    tipos: list[str] = []
    for linha in linhas:
        for chave in linha:
            if chave.startswith("p95_") and chave not in tipos:
                tipos.append(chave)
    for chave in tipos:
        tipo = chave[len("p95_"):-len("_ms")]
        graficos.append((chave, f"p95 de {tipo} (ms, escala log)", f"p95_{tipo}", True))

    for endpoint in endpoints:
        for campo, titulo, nome, log in graficos:
            arquivo = os.path.join(pasta_graficos, f"{endpoint}_{nome}.png")
            grafico_linhas(linhas, endpoint, campo, f"{endpoint}: {titulo}", arquivo, cenarios, log)
        comparados: list[str] = []
        for cenario in ("C2", "C3", "C4"):
            if cenario in cenarios:
                comparados.append(cenario)
        if len(comparados) >= 2:
            nivel = grafico_barras(linhas, endpoint, comparados, cenarios,
                                   os.path.join(pasta_graficos, f"{endpoint}_comparacao.png"))
            if nivel is not None:
                print(f"{endpoint}: comparação {', '.join(comparados)} com {nivel} usuários")

    with open(os.path.join(args.pasta, "observacoes.md"), "w") as f:
        f.write("\n".join(observacoes(linhas, endpoints, cenarios)))

    print(f"{len(linhas)} execuções -> {args.pasta}/resumo.csv, {pasta_graficos}/, {args.pasta}/observacoes.md")


if __name__ == "__main__":
    main()
