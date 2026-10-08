"""Serviço de rotas com trânsito: rotas HTTP.

Os endpoints são síncronos (def). O FastAPI roda cada um numa thread do pool.
A memória cresce com as viagens ativas (cada uma guarda a sua árvore de caminhos)
e com as requisições em andamento (cada uma monta a sua foto do trânsito).
"""

import logging
import os
import threading
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException

from app import metrics
from app.graph import load_graph
from app.routing import isochrone, shortest_path
from app.traffic import Transito
from app.trips import Viagens

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rotas")

MAP_FILE = os.environ.get("MAP_FILE", "data/campina_grande.map.gz")
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "0"))
MAX_ALCANCE_MIN = float(os.environ.get("MAX_ALCANCE_MIN", "30"))
CAPACIDADE_VIA = float(os.environ.get("CAPACIDADE_VIA", "2"))
ARVORE_VALIDADE_S = float(os.environ.get("ARVORE_VALIDADE_S", "60"))
VIAGEM_EXPIRA_S = float(os.environ.get("VIAGEM_EXPIRA_S", "300"))

log.info("carregando mapa %s", MAP_FILE)
graph = load_graph(MAP_FILE)
log.info("mapa carregado: %d nós, %d arestas, RSS do processo %.1f MB",
         graph.num_nodes, graph.num_edges, metrics.rss_mb())
transito = Transito(graph, CAPACIDADE_VIA)
viagens = Viagens(graph, transito, ARVORE_VALIDADE_S, VIAGEM_EXPIRA_S)

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
    """Melhor rota avulsa com o trânsito de agora (não guarda nada depois)."""
    with metrics.track("rota") as info:
        no_origem = no_mais_proximo(origem)
        no_destino = no_mais_proximo(destino)
        with vaga():
            pesos = transito.foto_pesos()
            resultado = shortest_path(graph, pesos, no_origem, no_destino)
            # Solta a foto antes de liberar a vaga, para MAX_CONCURRENT limitar a memória de fato.
            del pesos
        if resultado is None:
            raise HTTPException(404, "não há caminho entre os pontos")
        del resultado["arestas"]
        info["nos_visitados"] = resultado["nos_visitados"]
        return resultado


@app.post("/viagens")
def iniciar_viagem(origem: str, destino: str):
    """Inicia uma viagem: calcula e guarda a árvore de caminhos até o destino."""
    with metrics.track("viagem_inicio") as info:
        no_origem = no_mais_proximo(origem)
        no_destino = no_mais_proximo(destino)
        with vaga():
            resultado = viagens.criar(no_origem, no_destino)
        if resultado is None:
            raise HTTPException(404, "não há caminho entre os pontos")
        info["nos_visitados"] = resultado["nos_arvore"]
        return resultado


@app.get("/viagens/{viagem_id}/rota")
def recalcular_viagem(viagem_id: str, posicao: str):
    """Recálculo: rota da posição atual até o destino da viagem."""
    with metrics.track("viagem_recalculo") as info:
        viagem = viagens.buscar(viagem_id)
        if viagem is None:
            raise HTTPException(404, f"viagem {viagem_id!r} não existe")
        no_posicao = no_mais_proximo(posicao)
        with vaga():
            resultado = viagens.recalcular(viagem, no_posicao)
        if resultado is None:
            raise HTTPException(404, "não há caminho da posição até o destino")
        resultado["viagem"] = viagem_id
        info["nos_visitados"] = resultado["nos_arvore"] if resultado["arvore_nova"] else 0
        return resultado


@app.delete("/viagens/{viagem_id}")
def encerrar_viagem(viagem_id: str):
    """O veículo chegou: libera a árvore e sai do trânsito."""
    with metrics.track("viagem_fim"):
        if not viagens.encerrar(viagem_id):
            raise HTTPException(404, f"viagem {viagem_id!r} não existe")
        return {"viagem": viagem_id, "status": "encerrada"}


@app.get("/alcance")
def alcance(origem: str, minutos: float = 15):
    with metrics.track("alcance") as info:
        if not (0 < minutos <= MAX_ALCANCE_MIN):
            raise HTTPException(400, f"minutos deve estar entre 0 e {MAX_ALCANCE_MIN:g}")
        no_origem = no_mais_proximo(origem)
        with vaga():
            pesos = transito.foto_pesos()
            resultado = isochrone(graph, pesos, no_origem, minutos)
            del pesos
        info["nos_visitados"] = resultado["nos_visitados"]
        return resultado


@app.get("/metrics")
def metrics_endpoint():
    dados = metrics.snapshot()
    dados["viagens_ativas"] = viagens.quantidade()
    return dados


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
