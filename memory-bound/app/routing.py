"""Dijkstra (melhor rota), árvore de caminhos até um destino e isócrona.

Cada chamada cria as próprias estruturas (dist, prev, visitados, fila). A rota
avulsa e a isócrona soltam tudo ao terminar. A árvore até o destino fica guardada
na viagem enquanto ela durar (ver app/trips.py).
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


def descrever_rota(graph: Graph, arestas: list[tuple[int, int]], inicio: int) -> dict:
    """Distância, tempo sem trânsito e coordenadas de uma rota dada por arestas (u, i)."""
    metros_total = 0.0
    tempo_livre = 0.0
    coordenadas: list[list[float]] = [[graph.lats[inicio], graph.lons[inicio]]]
    for u, i in arestas:
        v, metros, segundos = graph.adj[u][i]
        metros_total += metros
        tempo_livre += segundos
        coordenadas.append([graph.lats[v], graph.lons[v]])
    return {
        "distancia_m": round(metros_total, 1),
        "tempo_sem_transito_s": round(tempo_livre, 1),
        "nos_rota": len(coordenadas),
        "rota": coordenadas,
    }


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
    for k in range(len(caminho) - 1):
        u = caminho[k]
        v = caminho[k + 1]
        vizinhos = graph.adj[u]
        melhor = -1
        for i in range(len(vizinhos)):
            if vizinhos[i][0] == v and (melhor == -1 or pesos[u][i] < pesos[u][melhor]):
                melhor = i
        arestas.append((u, melhor))

    resultado = descrever_rota(graph, arestas, origem)
    resultado["tempo_s"] = round(dist[destino], 1)
    resultado["nos_visitados"] = len(visitados)
    resultado["memoria_estimada_mb"] = round(memoria, 2)
    resultado["arestas"] = arestas
    return resultado


def reverse_tree(graph: Graph, pesos: list[list[float]], destino: int, origem: int,
                 folga: float) -> tuple[dict[int, float], dict[int, int], float]:
    """Árvore de caminhos mais rápidos que terminam no destino (Dijkstra no grafo invertido).

    Vai até alcançar a origem e continua até `folga` vezes o tempo dela, para cobrir
    pontos perto da rota caso o motorista saia do caminho.
    Devolve (tempo_ate_destino, proxima_aresta, memoria_mb): de um nó u, o caminho segue
    pela aresta proxima_aresta[u] de u, até chegar ao destino.
    """
    tempo: dict[int, float] = {destino: 0.0}
    proxima: dict[int, int] = {}
    visitados: set[int] = set()
    fila: list[tuple[float, int]] = [(0.0, destino)]
    limite = float("inf")

    while fila:
        d, v = heapq.heappop(fila)
        if v in visitados:
            continue
        if d > limite:
            break
        visitados.add(v)
        if v == origem:
            limite = d * folga
        for u, i in graph.radj[v]:
            novo = d + pesos[u][i]
            atual = tempo.get(u)
            if atual is None or novo < atual:
                tempo[u] = novo
                proxima[u] = i
                heapq.heappush(fila, (novo, u))

    # A árvore guardada é tempo + proxima. visitados e fila somem ao sair daqui.
    memoria = (sys.getsizeof(tempo) + sys.getsizeof(proxima) + len(tempo) * sys.getsizeof(0.0)) / 1_000_000
    return tempo, proxima, memoria


def caminho_pela_arvore(graph: Graph, proxima: dict[int, int], inicio: int) -> list[tuple[int, int]]:
    """Arestas (u, i) do caminho de `inicio` até o destino da árvore."""
    arestas: list[tuple[int, int]] = []
    u = inicio
    while u in proxima:
        i = proxima[u]
        arestas.append((u, i))
        u = graph.adj[u][i][0]
    return arestas


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
