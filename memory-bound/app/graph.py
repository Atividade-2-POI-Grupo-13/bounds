"""Carrega o mapa de ruas na memória e acha o nó mais próximo de uma coordenada.

O grafo usa só estruturas Python puras (listas e tuplas). Elas ocupam bastante
memória por nó, o que faz parte do perfil memory-bound da aplicação.
"""

import gzip
import math

# Tamanho de cada célula da grade de busca, em graus (cerca de 550 m no equador).
CELULA_GRAUS = 0.005
# Raio máximo (em células) da busca antes de dizer que o ponto está fora do mapa.
ANEIS_MAXIMOS = 2


def distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Aproximação equiretangular: suficiente para achar o nó mais próximo.
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371000.0 * math.hypot(x, y)


def celula(lat: float, lon: float) -> tuple[int, int]:
    return (math.floor(lat / CELULA_GRAUS), math.floor(lon / CELULA_GRAUS))


class Graph:
    def __init__(self, lats: list[float], lons: list[float], adj: list[list[tuple[int, float, float]]]):
        self.lats = lats
        self.lons = lons
        # adj[u] = lista de (vizinho, metros, segundos)
        self.adj = adj
        self.num_edges = 0
        for vizinhos in adj:
            self.num_edges += len(vizinhos)

        # Índice em grade: cada célula guarda os nós que caem nela.
        self.grade: dict[tuple[int, int], list[int]] = {}
        for no in range(len(lats)):
            chave = celula(lats[no], lons[no])
            if chave not in self.grade:
                self.grade[chave] = []
            self.grade[chave].append(no)

    @property
    def num_nodes(self) -> int:
        return len(self.lats)

    def nearest_node(self, lat: float, lon: float) -> int | None:
        """Nó mais próximo do ponto, ou None se não houver nó nas células em volta."""
        clat, clon = celula(lat, lon)
        # Começa pelo quadrado 3x3 em volta (raio 1): todo nó a menos de uma célula
        # do ponto está nele. Só amplia o quadrado se não achar nada.
        for raio in range(1, ANEIS_MAXIMOS + 1):
            melhor = None
            melhor_dist = math.inf
            for dlat in range(-raio, raio + 1):
                for dlon in range(-raio, raio + 1):
                    for no in self.grade.get((clat + dlat, clon + dlon), []):
                        d = distancia_metros(lat, lon, self.lats[no], self.lons[no])
                        if d < melhor_dist:
                            melhor = no
                            melhor_dist = d
            if melhor is not None:
                return melhor
        return None


def load_graph(caminho: str) -> Graph:
    """Lê o arquivo gerado por tools/prepare_map.py (gzip se terminar em .gz)."""
    if caminho.endswith(".gz"):
        f = gzip.open(caminho, "rt")
    else:
        f = open(caminho)
    with f:
        n, m = f.readline().split()
        n = int(n)
        m = int(m)

        lats: list[float] = []
        lons: list[float] = []
        for _ in range(n):
            lat, lon = f.readline().split()
            lats.append(float(lat))
            lons.append(float(lon))

        adj: list[list[tuple[int, float, float]]] = []
        for _ in range(n):
            adj.append([])
        for _ in range(m):
            u, v, metros, segundos = f.readline().split()
            adj[int(u)].append((int(v), float(metros), float(segundos)))

    return Graph(lats, lons, adj)
