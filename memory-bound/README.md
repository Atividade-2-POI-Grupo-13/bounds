# Rotas com trânsito

Aplicação memory-bound da Atividade 2 de Provisionamento e Operação de Infraestrutura (UFCG).

Servidor de rotas com trânsito para o mapa da Paraíba (OpenStreetMap, 214.373 nós e 565.101 arestas). Python 3.10, FastAPI, um processo.

Cada viagem aberta guarda na memória a sua árvore de caminhos até o destino. A memória cresce com o número de motoristas dirigindo ao mesmo tempo:

```
memória ≈ 290 MB (mapa) + 20 a 30 MB × viagens abertas + 35 a 50 MB × buscas em andamento
```

Medições em `docs/calibracao.md` (memória e CPU por versão) e `docs/perfil_local.md` (prova no Docker).

## 1. Rodar

Python 3.10 ou mais novo:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
MAP_FILE=data/paraiba.map.gz .venv/bin/python -m app.main
```

Testes: `.venv/bin/pip install -r requirements-tools.txt` e `.venv/bin/python -m pytest`.

Docker (já usa o mapa da Paraíba): `docker build -t rotas . && docker run -p 8000:8000 rotas`.

## 2. Endpoints

Coordenadas no formato `LAT,LON`. Coordenada inválida ou fora do mapa: 400. Viagem inexistente ou sem caminho: 404.

| método | caminho | o que faz |
|---|---|---|
| GET | `/health` | nós e arestas do mapa carregado |
| POST | `/viagens?origem=&destino=` | abre uma viagem e guarda a árvore de caminhos |
| GET | `/viagens/{id}/rota?posicao=` | rota da posição atual até o destino, pela árvore guardada |
| DELETE | `/viagens/{id}` | encerra a viagem e libera a árvore |
| GET | `/rota?origem=&destino=` | rota avulsa, sem guardar nada |
| GET | `/alcance?origem=&minutos=` | pontos alcançáveis em X minutos |
| GET | `/metrics` | RSS, CPU, requisições, erros, viagens abertas, memória e swap do sistema |
| POST | `/admin/reiniciar` | encerra o processo para o systemd subir de novo; 403 sem `PERMITIR_REINICIO=1` |

Exemplo, de Campina Grande a João Pessoa (134 km):

```
curl -X POST "localhost:8000/viagens?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
curl "localhost:8000/viagens/1/rota?posicao=-7.2000,-35.5000"
curl -X DELETE localhost:8000/viagens/1
```

## 3. Variáveis de ambiente

| variável | padrão | o que faz |
|---|---|---|
| `MAP_FILE` | `data/campina_grande.map.gz` | mapa carregado; a VM usa `data/paraiba.map.gz` |
| `PORT` | `8000` | porta |
| `MAX_CONCURRENT` | `0` | máximo de buscas simultâneas; 0 deixa sem limite |
| `MAX_ALCANCE_MIN` | `60` | maior valor aceito em `/alcance` |
| `CAPACIDADE_VIA` | `2` | carros por aresta na fórmula BPR do trânsito |
| `ARVORE_VALIDADE_S` | `60` | idade máxima da árvore; depois disso o recálculo refaz a busca |
| `VIAGEM_EXPIRA_S` | `300` | viagem sem recálculo por esse tempo é encerrada |
| `PERMITIR_REINICIO` | `0` | `1` libera `/admin/reiniciar` |

## 4. Pastas

| pasta | conteúdo |
|---|---|
| `app/` | servidor |
| `tests/` | testes do servidor (mapa `tests/mini.map`) |
| `data/` | mapas (`*.map.gz`) e 300 pares de origem e destino por mapa (`pontos_*.json`, semente 42) |
| `tools/` | geração do mapa (`prepare_map.py`) e calibração (`calibrate.py`) |
| `load/` | scripts do k6; o experimento usa `load/viagem.js` |
| `deploy/` | instalação na VM; passo a passo em `deploy/README.md` |
| `experiments/` | scripts do hospedeiro no LCC3 e prova local com Docker |
| `analysis/` | tabela e gráficos a partir dos resultados |
| `results/local/` | dados brutos da prova local com Docker |
| `docs/` | calibração, prova local, roteiro do dia no LCC3 e rascunho do relatório |

Para gerar o mapa de novo: instalar `requirements-tools.txt` e o `osmium-tool`, baixar `https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf` e rodar `python tools/prepare_map.py --lugar "Paraíba, Brazil" --nome paraiba --pbf nordeste-latest.osm.pbf`.

## 5. Experimento no LCC3

O k6 roda no hospedeiro do LCC3 e alcança a VM pelas portas redirecionadas do VirtualBox.

| hospedeiro | VM | serviço |
|---|---|---|
| 8080 | 8000 | aplicação (`rotas`) |
| 8081 | 8001 | monitor da VM (`rotas-monitor`, `deploy/monitor.py`) |
| 2222 | 22 | ssh |
| 8088 | 80 | nginx do teste de rede |

Cenários (padrão de `experiments/run_all.sh`):

| cenário | CPUs | RAM |
|---|---|---|
| C1 | 1 | 512 MB |
| C2 | 1 | 1 GB (referência) |
| C3 | 1 | 2 GB |
| C4 | 2 | 1 GB |

Carga (`load/viagem.js`): cada usuário virtual abre uma viagem, recalcula 6 vezes com 5 s entre recálculos e encerra (35 s por viagem). Níveis de 1, 2, 5, 10, 20, 40 e 60 usuários. Cada nível: serviço reiniciado, 35 s de aquecimento, 60 s de medição. 3 repetições.

Passos (detalhe e prints em `docs/roteiro_lcc.md`):

1. Criar a VM, testar a rede com nginx e instalar a aplicação: `deploy/README.md`.
2. k6 sem root: `experiments/instalar_k6.sh` e `export K6=~/bin/k6`.
3. Com ssh na VM: `ssh-copy-id -p 2222 osboxes@localhost` (senha `osboxes.org`).
4. `experiments/teste_fumaca.sh` (cerca de 6 min). Imprime o comando do passo 5.
5. Rodar o comando impresso. Ele troca CPU e RAM com `VBoxManage` e roda os níveis. Estimativa do próprio script: 3h13 com 3 repetições, 2h08 com 2. Rodar de novo o mesmo comando retoma de onde parou.
6. Levar `results/raw/` para casa (pendrive ou `git push`).
7. `python analysis/analyze.py`: gera `results/resumo.csv`, `results/graficos/*.png` e `results/observacoes.md`.

O teste de fumaça sugere três ajustes:

- C1 com 768 MB se couberem menos de 3 viagens de 28 MB na memória livre da VM de 512 MB.
- `PAUSA_S` maior se a CPU com 10 usuários, multiplicada por 6, passar de 60%.
- 2 repetições se 3 passarem de 2h30.

Ele também liga `SEM_SSH=1` quando a VM não tem ssh. Nesse modo o reinício entre níveis usa `POST /admin/reiniciar`, memória, swap e CPU vêm só do monitor, e as mortes por falta de memória são contadas pelas mudanças de `inicio_epoch` do processo. Ficam faltando `vmstat` e o log do kernel.

Acompanhar ao vivo: `experiments/acompanhar.sh` num segundo terminal.
