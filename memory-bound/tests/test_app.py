"""Testes com um grafo de 5 nós feito à mão (tests/mini.map).

    0 --10s--> 1 --10s--> 3        3 --10s--> 0
    0 --5s---> 2 --30s--> 3        4 --15s--> 0  (ninguém chega no 4)

Melhor rota de 0 a 3 sem trânsito: 0 -> 1 -> 3, 20 s e 200 m.
A alternativa 0 -> 2 -> 3 leva 35 s.
"""

import os

MINI_MAP = os.path.join(os.path.dirname(__file__), "mini.map")
os.environ["MAP_FILE"] = MINI_MAP
os.environ["CAPACIDADE_VIA"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.graph import load_graph  # noqa: E402
from app.main import app  # noqa: E402
from app.routing import isochrone, shortest_path  # noqa: E402
from app.traffic import Transito  # noqa: E402

graph = load_graph(MINI_MAP)
sem_transito = Transito(graph, capacidade=1).foto_pesos()
client = TestClient(app)

PONTO_0 = "-7.2300,-35.8800"
PONTO_3 = "-7.2310,-35.8790"
PONTO_4 = "-7.2320,-35.8780"


def test_carrega_mapa():
    assert graph.num_nodes == 5
    assert graph.num_edges == 6


def test_no_mais_proximo():
    assert graph.nearest_node(-7.23001, -35.87901) == 1
    assert graph.nearest_node(0.0, 0.0) is None


def test_dijkstra_escolhe_caminho_mais_rapido():
    r = shortest_path(graph, sem_transito, 0, 3)
    assert r["tempo_s"] == 20.0
    assert r["distancia_m"] == 200.0
    assert r["nos_rota"] == 3
    assert r["rota"][1] == [-7.23, -35.879]
    assert r["arestas"] == [(0, 0), (1, 0)]


def test_dijkstra_sem_caminho():
    assert shortest_path(graph, sem_transito, 0, 4) is None


def test_isocrona():
    # Em 15 s a partir do 0: o próprio 0 (0 s), o 2 (5 s) e o 1 (10 s).
    r = isochrone(graph, sem_transito, 0, 0.25)
    assert r["nos_alcancados"] == 3


def test_transito_desvia_e_libera():
    transito = Transito(graph, capacidade=1)
    rapida = shortest_path(graph, transito.foto_pesos(), 0, 3)["arestas"]
    # Dois veículos na rota rápida: cada aresta passa de 10 s para 34 s (BPR), 68 s no total.
    transito.registrar("a", rapida)
    transito.registrar("b", rapida)
    r = shortest_path(graph, transito.foto_pesos(), 0, 3)
    assert r["nos_rota"] == 3
    assert r["rota"][1] == [-7.231, -35.88]  # foi pelo nó 2
    assert r["tempo_s"] == 35.0
    assert r["tempo_sem_transito_s"] == 35.0

    # Um veículo recalcula para a alternativa: sai da rota antiga e entra na nova.
    transito.registrar("b", r["arestas"])
    assert transito.fluxo[0] == [1, 1]
    assert transito.remover("a") is True
    assert transito.remover("a") is False
    assert transito.veiculos_ativos() == 1


def test_endpoint_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "nodes": 5, "edges": 6}


def test_endpoint_rota():
    r = client.get("/rota", params={"origem": PONTO_0, "destino": PONTO_3})
    assert r.status_code == 200
    assert r.json()["tempo_s"] == 20.0
    assert "arestas" not in r.json()


def test_endpoint_veiculo_entra_e_sai_do_transito():
    params = {"origem": PONTO_0, "destino": PONTO_3, "veiculo": "v1"}
    assert client.get("/rota", params=params).status_code == 200
    assert client.get("/metrics").json()["veiculos_ativos"] == 1
    assert client.delete("/veiculos/v1").status_code == 200
    assert client.delete("/veiculos/v1").status_code == 404
    assert client.get("/metrics").json()["veiculos_ativos"] == 0


def test_endpoint_rota_erros():
    assert client.get("/rota", params={"origem": "abc", "destino": PONTO_3}).status_code == 400
    assert client.get("/rota", params={"origem": "0,0", "destino": PONTO_3}).status_code == 400
    assert client.get("/rota", params={"origem": PONTO_0, "destino": PONTO_4}).status_code == 404


def test_endpoint_alcance():
    r = client.get("/alcance", params={"origem": PONTO_0, "minutos": 0.25})
    assert r.status_code == 200
    assert r.json()["nos_alcancados"] == 3
    assert client.get("/alcance", params={"origem": PONTO_0, "minutos": 999}).status_code == 400


def test_endpoint_metrics_conta_requisicoes_e_erros():
    antes = client.get("/metrics").json()
    client.get("/rota", params={"origem": PONTO_0, "destino": PONTO_3})
    client.get("/rota", params={"origem": PONTO_0, "destino": PONTO_4})
    depois = client.get("/metrics").json()
    assert depois["total"] == antes["total"] + 2
    assert depois["erros"] == antes["erros"] + 1
    assert depois["rss_mb"] > 0
