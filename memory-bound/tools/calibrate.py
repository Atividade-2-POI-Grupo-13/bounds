"""Mede memória e CPU da aplicação para cada mapa, para escolher mapa e peso.

Para cada mapa e endpoint, sobe um servidor novo e mede:
  - RSS logo depois de carregar o mapa (base);
  - memória estimada de uma requisição (média e máxima, vinda da própria resposta);
  - tempo de CPU médio de uma requisição;
  - quanto o RSS cresce com 1, 5, 10, 20 e 40 requisições simultâneas.

Com --viagens, mede o estado guardado entre requisições:
  - quanto o RSS cresce com 1, 5, 10, 20, 40 e 80 viagens ativas;
  - CPU para iniciar uma viagem e para um recálculo que usa a árvore guardada.

Exemplos:
    python tools/calibrate.py data/campina_grande.map.gz data/paraiba.map.gz --minutos 15
    python tools/calibrate.py data/paraiba.map.gz --viagens
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
NIVEIS_VIAGENS = [1, 5, 10, 20, 40, 80]


def get_json(caminho: str, metodo: str = "GET") -> dict:
    requisicao = urllib.request.Request(URL + caminho, method=metodo)
    with urllib.request.urlopen(requisicao, timeout=600) as resposta:
        return json.loads(resposta.read())


def cpu_s(processo: psutil.Process) -> float:
    tempos = processo.cpu_times()
    return tempos.user + tempos.system


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


def calibrar_viagens(mapa: str, pontos: list[dict]) -> None:
    """Abre viagens e não fecha: mede quanto cada viagem ativa segura de memória."""
    proc = subir_servidor(mapa)
    processo = psutil.Process(proc.pid)
    try:
        base = processo.memory_info().rss / 1_000_000
        print(f"{os.path.basename(mapa)}: base {base:.0f} MB")
        print("| viagens ativas | RSS MB | +RSS MB | +RSS por viagem MB | árvore média MB | nós por árvore | CPU início ms |")
        print("|---|---|---|---|---|---|---|")
        abertas: list[dict] = []
        memorias: list[float] = []
        nos: list[int] = []
        cpu_inicios = 0.0
        for nivel in NIVEIS_VIAGENS:
            while len(abertas) < nivel:
                par = pontos[len(abertas) % len(pontos)]
                caminho = (f"/viagens?origem={par['origem'][0]},{par['origem'][1]}"
                           f"&destino={par['destino'][0]},{par['destino'][1]}")
                antes = cpu_s(processo)
                r = get_json(caminho, "POST")
                cpu_inicios += cpu_s(processo) - antes
                abertas.append(r)
                memorias.append(r["memoria_arvore_mb"])
                nos.append(r["nos_arvore"])
            rss = processo.memory_info().rss / 1_000_000
            print(f"| {nivel} | {rss:.0f} | {rss - base:.0f} | {(rss - base) / nivel:.1f} "
                  f"| {sum(memorias) / len(memorias):.1f} | {sum(nos) / len(nos):.0f} "
                  f"| {cpu_inicios / len(abertas) * 1000:.0f} |")

        # Recálculo do meio da rota, com a árvore ainda válida.
        antes = cpu_s(processo)
        novas = 0
        for r in abertas:
            meio = r["rota"][len(r["rota"]) // 2]
            resposta = get_json(f"/viagens/{r['viagem']}/rota?posicao={meio[0]},{meio[1]}")
            if resposta["arvore_nova"]:
                novas += 1
        cpu_recalculo = (cpu_s(processo) - antes) / len(abertas) * 1000
        print(f"\nCPU por recálculo pela árvore guardada: {cpu_recalculo:.1f} ms "
              f"({novas} de {len(abertas)} precisaram refazer a árvore)")
    finally:
        proc.terminate()
        proc.wait()


def arquivo_pontos(mapa: str) -> str:
    nome = os.path.basename(mapa).replace(".map.gz", "")
    return os.path.join(os.path.dirname(mapa), f"pontos_{nome}.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mapas", nargs="+")
    parser.add_argument("--minutos", type=float, default=15, help="minutos usados no /alcance")
    parser.add_argument("--amostras", type=int, default=30, help="requisições em sequência por endpoint")
    parser.add_argument("--endpoints", default="rota,alcance")
    parser.add_argument("--viagens", action="store_true", help="mede memória por viagem ativa")
    args = parser.parse_args()

    if args.viagens:
        for mapa in args.mapas:
            with open(arquivo_pontos(mapa)) as f:
                calibrar_viagens(mapa, json.load(f))
        return

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
