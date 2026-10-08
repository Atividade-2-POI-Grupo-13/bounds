"""Testes com um grafo de 5 nós feito à mão (tests/mini.map).

    0 --10s--> 1 --10s--> 3        3 --10s--> 0
    0 --5s---> 2 --30s--> 3        4 --15s--> 0  (ninguém chega no 4)

Melhor rota de 0 a 3: 0 -> 1 -> 3, 20 s e 200 m.
"""

import os

MINI_MAP = os.path.join(os.path.dirname(__file__), "mini.map")
os.environ["MAP_FILE"] = MINI_MAP

from fastapi.testclient import TestClient  # noqa: E402

from app.graph import load_graph  # noqa: E402
from app.main import app  # noqa: E402
from app.routing import isochrone, shortest_path  # noqa: E402

graph = load_graph(MINI_MAP)
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
    r = shortest_path(graph, 0, 3)
    assert r["tempo_s"] == 20.0
    assert r["distancia_m"] == 200.0
    assert r["nos_rota"] == 3
    assert r["rota"][1] == [-7.23, -35.879]


def test_dijkstra_sem_caminho():
    assert shortest_path(graph, 0, 4) is None


def test_isocrona():
    # Em 15 s a partir do 0: o próprio 0 (0 s), o 2 (5 s) e o 1 (10 s).
    r = isochrone(graph, 0, 0.25)
    assert r["nos_alcancados"] == 3


def test_endpoint_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "nodes": 5, "edges": 6}


def test_endpoint_rota():
    r = client.get("/rota", params={"origem": PONTO_0, "destino": PONTO_3})
    assert r.status_code == 200
    assert r.json()["tempo_s"] == 20.0


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
