"""Mede memória e CPU da aplicação para cada mapa, para escolher mapa e peso.

Para cada mapa e endpoint, sobe um servidor novo e mede:
  - RSS logo depois de carregar o mapa (base);
  - memória estimada de uma requisição (média e máxima, vinda da própria resposta);
  - tempo de CPU médio de uma requisição;
  - quanto o RSS cresce com 1, 5, 10, 20 e 40 requisições simultâneas.

Exemplo:
    python tools/calibrate.py data/campina_grande.map.gz data/paraiba.map.gz --minutos 15
"""

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import psutil

PORTA = 8011
URL = f"http://127.0.0.1:{PORTA}"
NIVEIS = [1, 5, 10, 20, 40]


def get_json(caminho: str) -> dict:
    with urllib.request.urlopen(URL + caminho, timeout=600) as resposta:
        return json.loads(resposta.read())


def subir_servidor(mapa: str) -> subprocess.Popen:
    env = dict(os.environ, MAP_FILE=mapa, PORT=str(PORTA), MAX_ALCANCE_MIN="120")
    proc = subprocess.Popen([sys.executable, "-m", "app.main"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(600):
        try:
            get_json("/health")
            return proc
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"servidor não subiu com {mapa}")


def caminho_requisicao(endpoint: str, par: dict, minutos: float) -> str:
    origem = f"{par['origem'][0]},{par['origem'][1]}"
    destino = f"{par['destino'][0]},{par['destino'][1]}"
    if endpoint == "rota":
        return f"/rota?origem={origem}&destino={destino}"
    return f"/alcance?origem={origem}&minutos={minutos}"


def medir_pico_rss(processo: psutil.Process, parar: threading.Event, saida: list) -> None:
    """Lê o RSS a cada 5 ms até `parar` ser sinalizado; guarda o maior valor em saida[0]."""
    while not parar.is_set():
        rss = processo.memory_info().rss / 1_000_000
        if rss > saida[0]:
            saida[0] = rss
        time.sleep(0.005)


def rodada_simultanea(processo: psutil.Process, caminhos: list[str]) -> tuple[float, float]:
    """Dispara todas as requisições ao mesmo tempo. Devolve (pico de RSS em MB, duração em s)."""
    pico = [0.0]
    parar = threading.Event()
    monitor = threading.Thread(target=medir_pico_rss, args=(processo, parar, pico))
    monitor.start()

    threads: list[threading.Thread] = []
    for caminho in caminhos:
        threads.append(threading.Thread(target=get_json, args=(caminho,)))
    inicio = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duracao = time.perf_counter() - inicio

    parar.set()
    monitor.join()
    return pico[0], duracao


def calibrar(mapa: str, pontos: list[dict], endpoint: str, minutos: float, amostras: int) -> dict:
    proc = subir_servidor(mapa)
    processo = psutil.Process(proc.pid)
    try:
        saude = get_json("/health")
        base = processo.memory_info().rss / 1_000_000
        rng = random.Random(1)

        # Primeiro as requisições simultâneas, em níveis crescentes, com o servidor
        # recém-iniciado. O RSS não diminui entre níveis (o Python reaproveita a memória
        # liberada), então o pico de cada nível mostra a memória de N requisições vivas
        # ao mesmo tempo.
        crescimento: dict[int, float] = {}
        duracao_nivel: dict[int, float] = {}
        for n in NIVEIS:
            caminhos: list[str] = []
            for _ in range(n):
                caminhos.append(caminho_requisicao(endpoint, rng.choice(pontos), minutos))
            pico, dur = rodada_simultanea(processo, caminhos)
            crescimento[n] = max(0.0, pico - base)
            duracao_nivel[n] = dur

        # Depois, uma de cada vez: memória estimada e CPU por requisição.
        memorias: list[float] = []
        visitados: list[int] = []
        cpu_antes = processo.cpu_times()
        inicio = time.perf_counter()
        for _ in range(amostras):
            r = get_json(caminho_requisicao(endpoint, rng.choice(pontos), minutos))
            memorias.append(r["memoria_estimada_mb"])
            visitados.append(r["nos_visitados"])
        duracao = time.perf_counter() - inicio
        cpu_depois = processo.cpu_times()
        cpu_total = (cpu_depois.user - cpu_antes.user) + (cpu_depois.system - cpu_antes.system)
    finally:
        proc.terminate()
        proc.wait()

    return {
        "mapa": os.path.basename(mapa),
        "endpoint": endpoint if endpoint == "rota" else f"alcance {minutos:g}min",
        "nos": saude["nodes"],
        "arestas": saude["edges"],
        "base_mb": base,
        "visitados_medio": sum(visitados) / len(visitados),
        "mem_req_media_mb": sum(memorias) / len(memorias),
        "mem_req_max_mb": max(memorias),
        "cpu_req_ms": cpu_total / amostras * 1000,
        "lat_req_ms": duracao / amostras * 1000,
        "crescimento": crescimento,
        "duracao_nivel": duracao_nivel,
    }


def arquivo_pontos(mapa: str) -> str:
    nome = os.path.basename(mapa).replace(".map.gz", "")
    return os.path.join(os.path.dirname(mapa), f"pontos_{nome}.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mapas", nargs="+")
    parser.add_argument("--minutos", type=float, default=15, help="minutos usados no /alcance")
    parser.add_argument("--amostras", type=int, default=30, help="requisições em sequência por endpoint")
    parser.add_argument("--endpoints", default="rota,alcance")
    args = parser.parse_args()

    resultados: list[dict] = []
    for mapa in args.mapas:
        with open(arquivo_pontos(mapa)) as f:
            pontos = json.load(f)
        for endpoint in args.endpoints.split(","):
            print(f"calibrando {mapa} {endpoint}...", file=sys.stderr)
            resultados.append(calibrar(mapa, pontos, endpoint, args.minutos, args.amostras))

    colunas_niveis = ""
    for n in NIVEIS:
        colunas_niveis += f" +RSS {n} sim. |"
    print("| mapa | endpoint | nós | arestas | base MB | visitados | mem/req média MB | mem/req máx MB "
          "| CPU/req ms |" + colunas_niveis + " tempo 20 sim. s |")
    print("|" + "---|" * (10 + len(NIVEIS)))
    for r in resultados:
        linha = (f"| {r['mapa']} | {r['endpoint']} | {r['nos']} | {r['arestas']} | {r['base_mb']:.0f} "
                 f"| {r['visitados_medio']:.0f} | {r['mem_req_media_mb']:.1f} | {r['mem_req_max_mb']:.1f} "
                 f"| {r['cpu_req_ms']:.0f} |")
        for n in NIVEIS:
            linha += f" {r['crescimento'][n]:.0f} |"
        linha += f" {r['duracao_nivel'][NIVEIS[-1]]:.1f} |"
        print(linha)


if __name__ == "__main__":
    main()
