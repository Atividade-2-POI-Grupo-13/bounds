"""Trânsito compartilhado entre todas as requisições.

Cada viagem ativa ocupa as arestas da sua rota. Quanto mais veículos numa
aresta, mais lento fica passar por ela (fórmula BPR, padrão em engenharia de
tráfego). Quando uma viagem recalcula, sai da rota antiga e entra na nova;
se muitas fogem para a mesma alternativa, ela também congestiona.
"""

import threading

from app.graph import Graph

# Parâmetros clássicos da fórmula BPR (Bureau of Public Roads).
ALFA = 0.15
BETA = 4


class Transito:
    def __init__(self, graph: Graph, capacidade: float):
        self.graph = graph
        # Veículos na aresta a partir da qual o trânsito começa a pesar.
        # Cada usuário simulado representa um grupo de carros, por isso o valor é pequeno.
        self.capacidade = capacidade
        # fluxo[u][i] = veículos na i-ésima aresta que sai de u (mesma ordem de graph.adj[u])
        self.fluxo: list[list[int]] = []
        for vizinhos in graph.adj:
            self.fluxo.append([0] * len(vizinhos))
        self._trava = threading.Lock()

    def foto_pesos(self) -> list[list[float]]:
        """Tempo de cada aresta com o trânsito de agora, em segundos.

        Cada busca usa a sua própria foto: assim o trânsito não muda no meio do
        Dijkstra enquanto outras requisições mexem no fluxo. É a maior estrutura
        de uma requisição (um float por aresta do mapa).
        """
        # ponytail: lê o fluxo sem trava; uma aresta pode sair com o valor de um instante antes
        # ou depois, o que não muda nada para uma foto de trânsito.
        pesos: list[list[float]] = []
        for u in range(len(self.graph.adj)):
            vizinhos = self.graph.adj[u]
            fluxo_u = self.fluxo[u]
            pesos_u: list[float] = []
            for i in range(len(vizinhos)):
                segundos = vizinhos[i][2]
                pesos_u.append(segundos * (1 + ALFA * (fluxo_u[i] / self.capacidade) ** BETA))
            pesos.append(pesos_u)
        return pesos

    def trocar(self, antigas: list[tuple[int, int]], novas: list[tuple[int, int]]) -> None:
        """Um veículo sai das arestas antigas e entra nas novas (listas de (u, i))."""
        with self._trava:
            for u, i in antigas:
                self.fluxo[u][i] -= 1
            for u, i in novas:
                self.fluxo[u][i] += 1
