"""Viagens ativas: o estado que o servidor guarda entre uma requisição e outra.

Ao iniciar uma viagem, o servidor calcula a árvore de caminhos até o destino
e guarda enquanto a viagem durar. Os recálculos seguem essa árvore e quase não
gastam CPU. A árvore só é refeita quando fica velha (o trânsito mudou) ou
quando o motorista sai da área que ela cobre.

É aqui que a memória cresce com a demanda: cada usuário ativo segura a sua
árvore, mesmo enquanto só está dirigindo e não faz nenhuma requisição.
"""

import itertools
import threading
import time

from app.graph import Graph
from app.routing import caminho_pela_arvore, descrever_rota, reverse_tree
from app.traffic import Transito

# A árvore cobre até 20% a mais que o tempo da origem ao destino.
FOLGA_ARVORE = 1.2


class Viagem:
    def __init__(self, destino: int):
        self.destino = destino
        self.tempo: dict[int, float] = {}
        self.proxima: dict[int, int] = {}
        self.memoria_mb = 0.0
        self.arvore_criada_em = 0.0
        self.ultimo_uso = time.monotonic()
        self.arestas: list[tuple[int, int]] = []


class Viagens:
    def __init__(self, graph: Graph, transito: Transito, validade_arvore_s: float, expira_s: float):
        self.graph = graph
        self.transito = transito
        self.validade_arvore_s = validade_arvore_s
        self.expira_s = expira_s
        self.ativas: dict[str, Viagem] = {}
        self._trava = threading.Lock()
        self._ids = itertools.count(1)

    def _montar_arvore(self, viagem: Viagem, posicao: int) -> None:
        pesos = self.transito.foto_pesos()
        tempo, proxima, memoria = reverse_tree(self.graph, pesos, viagem.destino, posicao, FOLGA_ARVORE)
        del pesos
        viagem.tempo = tempo
        viagem.proxima = proxima
        viagem.memoria_mb = memoria
        viagem.arvore_criada_em = time.monotonic()

    def _seguir(self, viagem: Viagem, posicao: int, arvore_nova: bool) -> dict | None:
        """Rota de `posicao` até o destino pela árvore, e atualiza o trânsito."""
        if posicao != viagem.destino and posicao not in viagem.proxima:
            return None
        arestas = caminho_pela_arvore(self.graph, viagem.proxima, posicao)
        self.transito.trocar(viagem.arestas, arestas)
        viagem.arestas = arestas
        viagem.ultimo_uso = time.monotonic()

        resultado = descrever_rota(self.graph, arestas, posicao)
        resultado["tempo_s"] = round(viagem.tempo[posicao], 1)
        resultado["arvore_nova"] = arvore_nova
        resultado["nos_arvore"] = len(viagem.tempo)
        resultado["memoria_arvore_mb"] = round(viagem.memoria_mb, 2)
        return resultado

    def criar(self, origem: int, destino: int) -> dict | None:
        """Inicia uma viagem. Devolve None se não houver caminho."""
        self.expirar()
        viagem = Viagem(destino)
        self._montar_arvore(viagem, origem)
        resultado = self._seguir(viagem, origem, arvore_nova=True)
        if resultado is None:
            return None
        viagem_id = str(next(self._ids))
        with self._trava:
            self.ativas[viagem_id] = viagem
        resultado["viagem"] = viagem_id
        return resultado

    def buscar(self, viagem_id: str) -> Viagem | None:
        with self._trava:
            return self.ativas.get(viagem_id)

    def recalcular(self, viagem: Viagem, posicao: int) -> dict | None:
        """Rota a partir da posição atual. Refaz a árvore se ela estiver velha ou não cobrir a posição."""
        velha = time.monotonic() - viagem.arvore_criada_em > self.validade_arvore_s
        if not velha:
            resultado = self._seguir(viagem, posicao, arvore_nova=False)
            if resultado is not None:
                return resultado
        self._montar_arvore(viagem, posicao)
        return self._seguir(viagem, posicao, arvore_nova=True)

    def encerrar(self, viagem_id: str) -> bool:
        """O veículo chegou: libera a árvore e sai do trânsito. False se a viagem não existe."""
        with self._trava:
            viagem = self.ativas.pop(viagem_id, None)
        if viagem is None:
            return False
        self.transito.trocar(viagem.arestas, [])
        return True

    def expirar(self) -> int:
        """Encerra viagens sem uso há mais de `expira_s` (motorista que sumiu sem avisar)."""
        agora = time.monotonic()
        vencidas: list[str] = []
        with self._trava:
            for viagem_id, viagem in self.ativas.items():
                if agora - viagem.ultimo_uso > self.expira_s:
                    vencidas.append(viagem_id)
        for viagem_id in vencidas:
            self.encerrar(viagem_id)
        return len(vencidas)

    def quantidade(self) -> int:
        with self._trava:
            return len(self.ativas)
