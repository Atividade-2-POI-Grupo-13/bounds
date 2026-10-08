# Calibração (etapa 2)

Medido no Mac (Apple Silicon, Python 3.10) com `tools/calibrate.py`. Na VM do LCC3 os tempos de CPU devem ser 2 a 3 vezes maiores; as memórias devem ficar parecidas.

## 1. Mapas disponíveis

| mapa | nós | arestas | arquivo | base (RSS após carregar) |
|---|---|---|---|---|
| campina_grande | 12.808 | 34.045 | 0,3 MB | 60 MB |
| campina_grande_full (sem simplificar) | 62.755 | 127.695 | 1,2 MB | 87 MB |
| paraiba | 214.373 | 565.101 | 5,7 MB | 204 MB |
| paraiba_full (sem simplificar) | 2.472.615 | 5.041.246 | 45 MB | 1.454 MB |

`paraiba_full` não cabe na VM e ficou fora do Git.

## 2. Custo por requisição

"+RSS N sim." é o crescimento do RSS do processo com N requisições disparadas juntas, servidor recém-iniciado.

| mapa | endpoint | visitados | mem/req média | mem/req máx | CPU/req | +RSS 1 | +RSS 5 | +RSS 10 | +RSS 20 | +RSS 40 |
|---|---|---|---|---|---|---|---|---|---|---|
| campina_grande | rota | 6.250 | 1,0 MB | 2,0 MB | 4 ms | 1 | 2 | 2 | 4 | 5 |
| campina_grande_full | rota | 26.242 | 4,2 MB | 8,7 MB | 18 ms | 8 | 15 | 24 | 26 | 32 |
| paraiba | rota | 104.728 | 17,2 MB | 34,5 MB | 93 ms | 59 | 83 | 98 | 165 | 223 |
| paraiba | alcance 60 min | 23.064 | 3,6 MB | 8,6 MB | 22 ms | 0 | 15 | 20 | 23 | 32 |
| paraiba | alcance 120 min | 78.006 | 12,0 MB | 17,8 MB | 68 ms | 29 | 72 | 76 | 91 | 158 |
| paraiba_full | rota | 1.174.964 | 182 MB | 288 MB | 863 ms | 524 | 1.258 | 1.538 | 4.052 | 4.674 |

Rotas longas em `paraiba` (origem e destino a mais de 200 km): 27 MB em média, 114 ms de CPU.

## 3. O que os números mostram

- Memória e CPU por requisição crescem juntas. Em todos os mapas o Dijkstra gasta cerca de 0,2 MB por ms de CPU (cerca de 160 bytes por nó visitado).
- A base fica perto de 1 KB por nó do mapa. Uma busca que percorre o mapa inteiro usa cerca de 1/6 da base. Com base até 250 MB, uma requisição de `/rota` fica em no máximo 35 MB.
- Requisições só se acumulam em memória quando estão em andamento ao mesmo tempo. Com 1 núcleo, isso só acontece quando a CPU já está em 100%. Então a CPU vai aparecer saturada em todos os cenários sob carga. A prova de que a aplicação é memory-bound vem da comparação entre cenários: C2 x C3 (mais RAM) contra C2 x C4 (mais CPU).
- Com 1 processo Python, a segunda CPU do C4 fica quase ociosa por causa do GIL.

## 4. Estimativa do joelho na VM

Supondo cerca de 120 MB usados pelo Ubuntu Server ocioso e o mapa `paraiba` (base 205 MB).

| opção | memória por usuário em carga | joelho 512 MB | joelho 1 GB | joelho 2 GB |
|---|---|---|---|---|
| A: código atual | cerca de 12 MB | cerca de 15 usuários | cerca de 55 | cerca de 140 |
| B: código atual + pesos por requisição | cerca de 45 MB | cerca de 4 | cerca de 15 | cerca de 38 |

Pesos por requisição: cada requisição monta a própria lista de custo de cada aresta (um float por aresta, 34 MB em cerca de 80 ms de CPU). Em memória por ms de CPU, isso rende o dobro do Dijkstra.
