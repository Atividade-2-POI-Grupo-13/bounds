"""Dijkstra (melhor rota) e isócrona (tudo que se alcança em X minutos).

Cada chamada cria as próprias estruturas (foto de pesos, dist, prev, visitados,
fila) e solta tudo ao terminar. Nada é compartilhado entre requisições: é isso
que faz a memória do processo crescer com o número de requisições simultâneas.
"""

import heapq
import sys

from app.graph import Graph

TAMANHO_AMOSTRA = 500


def estimar_memoria_mb(pesos: list[list[float]], num_arestas: int,
                       dist: dict, prev: dict, visitados: set, fila: list) -> float:
    """Estimativa da memória usada pelas estruturas de uma busca.

    Conta a foto de pesos (uma lista por nó, um float por aresta), as tabelas
    (dict, set, list), os floats de dist e as tuplas da fila. Os ints dos nós
    são compartilhados com o grafo e não entram na conta.
    """
    tamanho_float = sys.getsizeof(0.0)
    total = sys.getsizeof(pesos) + len(pesos) * sys.getsizeof([]) + num_arestas * (8 + tamanho_float)
    total += sys.getsizeof(dist) + sys.getsizeof(prev) + sys.getsizeof(visitados) + sys.getsizeof(fila)
    total += len(dist) * tamanho_float
    total += len(fila) * sys.getsizeof((0.0, 0))
    return total / 1_000_000


def _dijkstra(graph: Graph, pesos: list[list[float]], origem: int, destino: int | None,
              limite_segundos: float):
    """Dijkstra pelo tempo de viagem com trânsito (pesos[u][i] = tempo da aresta i de u).

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
        vizinhos = graph.adj[u]
        pesos_u = pesos[u]
        for i in range(len(vizinhos)):
            v = vizinhos[i][0]
            novo = d + pesos_u[i]
            atual = dist.get(v)
            if atual is None or novo < atual:
                dist[v] = novo
                prev[v] = u
                heapq.heappush(fila, (novo, v))

    # ponytail: estimativa no fim da busca; a fila pode ter sido um pouco maior no meio.
    memoria = estimar_memoria_mb(pesos, graph.num_edges, dist, prev, visitados, fila)
    return dist, prev, visitados, memoria


def shortest_path(graph: Graph, pesos: list[list[float]], origem: int, destino: int) -> dict | None:
    """Melhor rota de origem a destino com o trânsito da foto, ou None se não houver caminho."""
    dist, prev, visitados, memoria = _dijkstra(graph, pesos, origem, destino, float("inf"))
    if destino not in visitados:
        return None

    caminho: list[int] = []
    no = destino
    while no != -1:
        caminho.append(no)
        no = prev[no]
    caminho.reverse()

    # Acha a aresta usada em cada trecho. Entre dois nós pode haver mais de uma:
    # a usada pelo Dijkstra é a mais rápida com trânsito.
    arestas: list[tuple[int, int]] = []
    metros_total = 0.0
    tempo_livre = 0.0
    for k in range(len(caminho) - 1):
        u = caminho[k]
        v = caminho[k + 1]
        vizinhos = graph.adj[u]
        melhor = -1
        for i in range(len(vizinhos)):
            if vizinhos[i][0] == v and (melhor == -1 or pesos[u][i] < pesos[u][melhor]):
                melhor = i
        arestas.append((u, melhor))
        metros_total += vizinhos[melhor][1]
        tempo_livre += vizinhos[melhor][2]

    coordenadas: list[list[float]] = []
    for no in caminho:
        coordenadas.append([graph.lats[no], graph.lons[no]])

    return {
        "distancia_m": round(metros_total, 1),
        "tempo_s": round(dist[destino], 1),
        "tempo_sem_transito_s": round(tempo_livre, 1),
        "nos_rota": len(caminho),
        "nos_visitados": len(visitados),
        "memoria_estimada_mb": round(memoria, 2),
        "rota": coordenadas,
        "arestas": arestas,
    }


def isochrone(graph: Graph, pesos: list[list[float]], origem: int, minutos: float) -> dict:
    """Todos os nós alcançáveis a partir da origem em até `minutos`, com o trânsito da foto."""
    _dist, _prev, visitados, memoria = _dijkstra(graph, pesos, origem, None, minutos * 60)

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
