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

## 4. Decisão: trânsito compartilhado

O código sem trânsito dava cerca de 12 MB por usuário em carga. Com esse valor, a VM de 1 GB só degradaria perto de 55 usuários, e a fila de CPU dominaria o tempo de resposta antes disso.

A aplicação ganhou trânsito compartilhado (`app/traffic.py`):

- cada `/rota` com `veiculo=ID` registra o veículo nas arestas da rota; um novo pedido do mesmo veículo é um recálculo e troca a rota;
- `DELETE /veiculos/ID` tira o veículo do trânsito na chegada;
- o tempo de cada aresta segue a fórmula BPR: `tempo_livre × (1 + 0,15 × (fluxo / CAPACIDADE_VIA)^4)`;
- cada busca monta a própria foto dos pesos (um float por aresta), para o trânsito não mudar no meio do Dijkstra. Essa foto é a maior estrutura da requisição.

Modelo de memória:

```
memória total ≈ mapa + fluxo do trânsito + (requisições simultâneas × (foto de pesos + busca))
```

## 5. Números com trânsito (mapa paraiba)

| endpoint | base MB | mem/req média | mem/req máx | CPU/req | +RSS 1 | +RSS 5 | +RSS 10 | +RSS 20 | +RSS 40 |
|---|---|---|---|---|---|---|---|---|---|
| rota | 227 | 49,1 MB | 66,4 MB | 218 ms | 102 | 245 | 436 | 731 | 1.271 |
| alcance 60 min | 227 | 35,5 MB | 40,5 MB | 151 ms | 42 | 220 | 319 | 386 | 681 |

Efeito da cascata (15 rotas de teste, capacidade 2):

| veículos ativos | nós visitados por busca | tempo com trânsito / tempo livre |
|---|---|---|
| 0 | 103.728 | 1,00 |
| 20 | 109.341 | 1,07 |
| 40 | 109.689 | 1,07 |
| 80 | 109.038 | 1,06 |

O trânsito aumenta a busca em cerca de 5%. O peso maior da cascata na carga vem dos recálculos: cada usuário faz várias requisições por viagem.

## 6. Estimativa do joelho na VM

Supondo cerca de 120 MB usados pelo Ubuntu Server ocioso e cerca de 30 MB por requisição simultânea (coluna +RSS).

| VM | sobra para requisições | joelho estimado |
|---|---|---|
| 512 MB | cerca de 165 MB | cerca de 5 usuários |
| 1 GB | cerca de 680 MB | cerca de 20 usuários |
| 2 GB | cerca de 1.700 MB | cerca de 55 usuários |

Recomendação: mapa `paraiba`, endpoint principal `/rota` com veículos e recálculos, `/alcance 60` como segundo peso. Níveis de demanda: 1, 2, 5, 10, 20, 40 e 60. Os tempos de CPU no LCC3 devem ser 2 a 3 vezes maiores que os do Mac.
