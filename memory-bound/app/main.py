"""Serviço de rotas: rotas HTTP.

Os endpoints são síncronos (def). O FastAPI roda cada um numa thread do pool,
então várias rotas ficam em andamento ao mesmo tempo e a memória delas se soma.
"""

import logging
import os
import threading
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException

from app import metrics
from app.graph import load_graph
from app.routing import isochrone, shortest_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rotas")

MAP_FILE = os.environ.get("MAP_FILE", "data/campina_grande.map.gz")
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "0"))
MAX_ALCANCE_MIN = float(os.environ.get("MAX_ALCANCE_MIN", "30"))

log.info("carregando mapa %s", MAP_FILE)
graph = load_graph(MAP_FILE)
log.info("mapa carregado: %d nós, %d arestas, RSS do processo %.1f MB",
         graph.num_nodes, graph.num_edges, metrics.rss_mb())

semaforo = threading.BoundedSemaphore(max(MAX_CONCURRENT, 1))

app = FastAPI(title="Rotas (memory-bound)")


@contextmanager
def vaga():
    """Espera uma vaga para calcular.

    Sem limite (MAX_CONCURRENT=0): todas as requisições calculam juntas.
    Com limite: as que passam do limite esperam a vez (menos memória, mais espera).
    """
    if MAX_CONCURRENT <= 0:
        yield
        return
    with metrics.na_fila():
        semaforo.acquire()
    try:
        yield
    finally:
        semaforo.release()


def parse_ponto(texto: str) -> tuple[float, float]:
    partes = texto.split(",")
    if len(partes) != 2:
        raise HTTPException(400, f"coordenada inválida: {texto!r}, use LAT,LON")
    try:
        lat = float(partes[0])
        lon = float(partes[1])
    except ValueError:
        raise HTTPException(400, f"coordenada inválida: {texto!r}, use LAT,LON")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(400, f"coordenada fora da faixa: {texto!r}")
    return lat, lon


def no_mais_proximo(texto: str) -> int:
    lat, lon = parse_ponto(texto)
    no = graph.nearest_node(lat, lon)
    if no is None:
        raise HTTPException(400, f"ponto fora do mapa: {texto!r}")
    return no


@app.get("/health")
def health():
    return {"status": "ok", "nodes": graph.num_nodes, "edges": graph.num_edges}


@app.get("/rota")
def rota(origem: str, destino: str):
    with metrics.track("rota") as info:
        no_origem = no_mais_proximo(origem)
        no_destino = no_mais_proximo(destino)
        with vaga():
            resultado = shortest_path(graph, no_origem, no_destino)
        if resultado is None:
            raise HTTPException(404, "não há caminho entre os pontos")
        info["nos_visitados"] = resultado["nos_visitados"]
        return resultado


@app.get("/alcance")
def alcance(origem: str, minutos: float = 15):
    with metrics.track("alcance") as info:
        if not (0 < minutos <= MAX_ALCANCE_MIN):
            raise HTTPException(400, f"minutos deve estar entre 0 e {MAX_ALCANCE_MIN:g}")
        no_origem = no_mais_proximo(origem)
        with vaga():
            resultado = isochrone(graph, no_origem, minutos)
        info["nos_visitados"] = resultado["nos_visitados"]
        return resultado


@app.get("/metrics")
def metrics_endpoint():
    return metrics.snapshot()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
