"""Trânsito compartilhado entre todas as requisições.

Cada veículo com rota ativa ocupa as arestas da sua rota. Quanto mais veículos
numa aresta, mais lento fica passar por ela (fórmula BPR, padrão em engenharia
de tráfego). Quando um veículo recalcula, sai da rota antiga e entra na nova;
se muitos fogem para a mesma alternativa, ela também congestiona.
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
        # veículo -> arestas (u, i) da rota que ele está seguindo
        self.veiculos: dict[str, list[tuple[int, int]]] = {}
        self._trava = threading.Lock()

    def foto_pesos(self) -> list[list[float]]:
        """Tempo de cada aresta com o trânsito de agora, em segundos.

        Cada busca usa a sua própria foto: assim o trânsito não muda no meio do
        Dijkstra enquanto outras requisições registram veículos. É a maior
        estrutura de uma requisição (um float por aresta do mapa).
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

    def registrar(self, veiculo: str, arestas: list[tuple[int, int]]) -> None:
        """Troca a rota do veículo: sai das arestas antigas e entra nas novas."""
        with self._trava:
            antigas = self.veiculos.get(veiculo, [])
            for u, i in antigas:
                self.fluxo[u][i] -= 1
            for u, i in arestas:
                self.fluxo[u][i] += 1
            self.veiculos[veiculo] = arestas

    def remover(self, veiculo: str) -> bool:
        """O veículo chegou: libera as arestas. Devolve False se ele não existia."""
        with self._trava:
            arestas = self.veiculos.pop(veiculo, None)
            if arestas is None:
                return False
            for u, i in arestas:
                self.fluxo[u][i] -= 1
            return True

    def veiculos_ativos(self) -> int:
        with self._trava:
            return len(self.veiculos)
