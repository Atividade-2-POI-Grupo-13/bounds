# Calibração

Medido no Mac (Apple Silicon, Python 3.10) com `tools/calibrate.py`. O custo de CPU na VM do LCC3 é medido pelo `experiments/teste_fumaca.sh` (início de viagem com 1 usuário).

## 1. Mapas

Base: RSS do processo logo após carregar o mapa, na primeira versão do servidor (seção 2).

| mapa | nós | arestas | arquivo | base |
|---|---|---|---|---|
| campina_grande | 12.808 | 34.045 | 0,3 MB | 60 MB |
| campina_grande_full (sem simplificar) | 62.755 | 127.695 | 1,2 MB | 87 MB |
| paraiba | 214.373 | 565.101 | 5,7 MB | 204 MB |
| paraiba_full (sem simplificar) | 2.472.615 | 5.041.246 | 45 MB | 1.454 MB |

- `paraiba_full` não cabe na VM e fica fora do Git.
- O experimento usa `paraiba`. Com o código atual (trânsito e grafo invertido), a base é 291 MB.

## 2. Primeira versão: rota avulsa sem trânsito

"+RSS N" é o crescimento do RSS com N requisições disparadas juntas, servidor recém-iniciado.

| mapa | endpoint | nós visitados | mem/req média | mem/req máx | CPU/req | +RSS 1 | +RSS 5 | +RSS 10 | +RSS 20 | +RSS 40 |
|---|---|---|---|---|---|---|---|---|---|---|
| campina_grande | rota | 6.250 | 1,0 MB | 2,0 MB | 4 ms | 1 | 2 | 2 | 4 | 5 |
| campina_grande_full | rota | 26.242 | 4,2 MB | 8,7 MB | 18 ms | 8 | 15 | 24 | 26 | 32 |
| paraiba | rota | 104.728 | 17,2 MB | 34,5 MB | 93 ms | 59 | 83 | 98 | 165 | 223 |
| paraiba | alcance 60 min | 23.064 | 3,6 MB | 8,6 MB | 22 ms | 0 | 15 | 20 | 23 | 32 |
| paraiba | alcance 120 min | 78.006 | 12,0 MB | 17,8 MB | 68 ms | 29 | 72 | 76 | 91 | 158 |
| paraiba_full | rota | 1.174.964 | 182 MB | 288 MB | 863 ms | 524 | 1.258 | 1.538 | 4.052 | 4.674 |

- Rotas acima de 200 km em `paraiba`: 27 MB e 114 ms de CPU em média.
- Em todos os mapas o Dijkstra gasta cerca de 0,2 MB por ms de CPU (cerca de 160 bytes por nó visitado).

## 3. Mecanismos testados

1. Rota avulsa sem trânsito (seção 2): 17 MB por requisição. Caiu porque a memória só acumula com requisições simultâneas, e com 1 núcleo isso só acontece com a CPU em 100%.
2. Trânsito compartilhado com foto de pesos por requisição (commit `4483695`, API `/rota?veiculo=`, removida depois): 49 MB por requisição (tabela abaixo). Caiu pelo mesmo motivo. A foto de pesos ficou como custo de toda busca completa.
3. Viagem com árvore de caminhos guardada (código atual, seção 4): a memória cresce com usuários dirigindo, mesmo sem requisição em andamento. Adotado.
4. Vários processos para usar a segunda CPU: cada processo carrega o mapa (291 MB) e o trânsito deixa de ser compartilhado. Descartado. Medição avulsa, sem script no repositório, com 8 rotas: em sequência 1,76 s, 4 threads 1,80 s, 4 processos 0,74 s. Repetição em 11/10/2026 (só Dijkstra, foto de pesos fora do tempo): 0,76 s, 0,78 s e 0,30 s. Threads não paralelizam o Dijkstra por causa do GIL.

Versão 2, mapa `paraiba`, base 227 MB:

| endpoint | mem/req média | mem/req máx | CPU/req | +RSS 1 | +RSS 5 | +RSS 10 | +RSS 20 | +RSS 40 |
|---|---|---|---|---|---|---|---|---|
| rota | 49,1 MB | 66,4 MB | 218 ms | 102 | 245 | 436 | 731 | 1.271 |
| alcance 60 min | 35,5 MB | 40,5 MB | 151 ms | 42 | 220 | 319 | 386 | 681 |

O trânsito (capacidade 2) aumenta a busca em cerca de 5%: 103.728 nós visitados sem veículos, 109.689 com 40, tempo de rota 1,07 vez o tempo livre.

## 4. Versão atual: memória por viagem

`python tools/calibrate.py data/paraiba.map.gz --viagens`, em 11/10/2026. Viagens abertas e nunca encerradas. Base 291 MB.

| viagens abertas | RSS MB | +RSS MB | +RSS por viagem MB | árvore média MB | nós por árvore | CPU de início ms |
|---|---|---|---|---|---|---|
| 1 | 326 | 34 | 34,2 | 13,6 | 128.013 | 263 |
| 5 | 414 | 123 | 24,5 | 14,7 | 133.715 | 243 |
| 10 | 525 | 233 | 23,3 | 16,6 | 141.312 | 248 |
| 20 | 708 | 417 | 20,8 | 16,5 | 139.867 | 238 |
| 40 | 702 | 410 | 10,3 | 16,8 | 144.782 | 242 |
| 80 | 1.021 | 730 | 9,1 | 16,4 | 142.793 | 240 |

- Recálculo pela árvore guardada: 1,5 ms de CPU (0 de 80 refizeram a árvore).
- "árvore média" é a estimativa da própria aplicação (`memoria_arvore_mb`).
- Com 40 e 80 viagens o RSS por viagem cai pela metade. Hipótese: compressão de memória do macOS, que tira páginas do RSS. Por isso a referência de memória por usuário vem do Docker (Linux): em C3, 341 MB com 1 usuário e 1.981 MB com 60, cerca de 28 MB por usuário (`docs/perfil_local.md`).
