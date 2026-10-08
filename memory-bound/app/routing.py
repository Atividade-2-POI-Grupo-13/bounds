"""Dijkstra (melhor rota) e isócrona (tudo que se alcança em X minutos).

Cada chamada cria as próprias estruturas (dist, prev, visitados, fila) e solta
tudo ao terminar. Nada é compartilhado entre requisições: é isso que faz a
memória do processo crescer com o número de requisições simultâneas.
"""

import heapq
import sys

from app.graph import Graph

TAMANHO_AMOSTRA = 500


def estimar_memoria_mb(dist: dict, prev: dict, visitados: set, fila: list) -> float:
    """Estimativa da memória usada pelas estruturas de uma busca.

    Conta as tabelas (dict, set, list), os floats de dist e as tuplas da fila.
    Os ints dos nós são compartilhados com o grafo e não entram na conta.
    """
    total = sys.getsizeof(dist) + sys.getsizeof(prev) + sys.getsizeof(visitados) + sys.getsizeof(fila)
    total += len(dist) * sys.getsizeof(0.0)
    total += len(fila) * sys.getsizeof((0.0, 0))
    return total / 1_000_000


def _dijkstra(graph: Graph, origem: int, destino: int | None, limite_segundos: float):
    """Dijkstra pelo tempo de viagem.

    Para quando chega ao destino (se houver) ou quando passa do limite de tempo.
    Devolve (dist, prev, visitados, memoria_mb).
    """
    dist: dict[int, float] = {origem: 0.0}
    prev: dict[int, int] = {origem: -1}
    visitados: set[int] = set()
    fila: list[tuple[float, int]] = [(0.0, origem)]

    while fila:
        d, u = heapq.heappop(fila)
        if u in visitados:
            continue
        if d > limite_segundos:
            break
        visitados.add(u)
        if u == destino:
            break
        for v, _metros, segundos in graph.adj[u]:
            novo = d + segundos
            atual = dist.get(v)
            if atual is None or novo < atual:
                dist[v] = novo
                prev[v] = u
                heapq.heappush(fila, (novo, v))

    # ponytail: estimativa no fim da busca; a fila pode ter sido um pouco maior no meio.
    memoria = estimar_memoria_mb(dist, prev, visitados, fila)
    return dist, prev, visitados, memoria


def shortest_path(graph: Graph, origem: int, destino: int) -> dict | None:
    """Melhor rota de origem a destino, ou None se não houver caminho."""
    dist, prev, visitados, memoria = _dijkstra(graph, origem, destino, float("inf"))
    if destino not in visitados:
        return None

    caminho: list[int] = []
    no = destino
    while no != -1:
        caminho.append(no)
        no = prev[no]
    caminho.reverse()

    # Soma os metros de cada trecho. Entre dois nós pode haver mais de uma aresta:
    # a usada pelo Dijkstra é a mais rápida.
    metros_total = 0.0
    for i in range(len(caminho) - 1):
        u = caminho[i]
        v = caminho[i + 1]
        melhor_segundos = float("inf")
        metros_trecho = 0.0
        for vizinho, metros, segundos in graph.adj[u]:
            if vizinho == v and segundos < melhor_segundos:
                melhor_segundos = segundos
                metros_trecho = metros
        metros_total += metros_trecho

    coordenadas: list[list[float]] = []
    for no in caminho:
        coordenadas.append([graph.lats[no], graph.lons[no]])

    return {
        "distancia_m": round(metros_total, 1),
        "tempo_s": round(dist[destino], 1),
        "nos_rota": len(caminho),
        "nos_visitados": len(visitados),
        "memoria_estimada_mb": round(memoria, 2),
        "rota": coordenadas,
    }


def isochrone(graph: Graph, origem: int, minutos: float) -> dict:
    """Todos os nós alcançáveis a partir da origem em até `minutos`."""
    _dist, _prev, visitados, memoria = _dijkstra(graph, origem, None, minutos * 60)

    # Amostra espaçada dos nós alcançados, para a resposta não ficar enorme.
    passo = max(1, len(visitados) // TAMANHO_AMOSTRA)
    amostra: list[list[float]] = []
    i = 0
    for no in visitados:
        if i % passo == 0:
            amostra.append([graph.lats[no], graph.lons[no]])
        i += 1

    return {
        "minutos": minutos,
        "nos_alcancados": len(visitados),
        "nos_visitados": len(visitados),
        "memoria_estimada_mb": round(memoria, 2),
        "amostra": amostra,
    }
