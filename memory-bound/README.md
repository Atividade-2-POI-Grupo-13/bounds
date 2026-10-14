# Rotas com trânsito

Aplicação memory-bound da Atividade 2 de Provisionamento e Operação de Infraestrutura (UFCG).

É um servidor de rotas para o mapa da Paraíba, escrito em Python 3.10 com FastAPI, num único processo. O mapa vem do OpenStreetMap e tem 214.373 nós e 565.101 arestas.

Quando um motorista abre uma viagem, o servidor calcula a árvore de caminhos até o destino e a mantém na memória enquanto a viagem durar. Por isso a memória cresce com o número de motoristas dirigindo ao mesmo tempo, mesmo quando quase ninguém faz requisição:

```
memória ≈ 290 MB (mapa) + 20 a 30 MB × viagens abertas + 35 a 50 MB × buscas em andamento
```

As medições de memória e CPU estão em `docs/calibracao.md`. Os dados da prova feita antes do laboratório, com Docker, estão em `results/local/`.

## 1. Rodar

Precisa de Python 3.10 ou mais novo.

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
MAP_FILE=data/paraiba.map.gz .venv/bin/python -m app.main
```

Para rodar os testes, instale também `requirements-tools.txt` e chame `.venv/bin/python -m pytest`.

Com Docker, a imagem já traz o mapa da Paraíba: `docker build -t rotas . && docker run -p 8000:8000 rotas`.

## 2. Endpoints

As coordenadas vão no formato `LAT,LON`. Uma coordenada inválida ou fora do mapa devolve 400. Uma viagem que não existe, ou sem caminho entre os pontos, devolve 404.

| método | caminho | o que faz |
|---|---|---|
| GET | `/health` | nós e arestas do mapa carregado |
| POST | `/viagens?origem=&destino=` | abre uma viagem e guarda a árvore de caminhos |
| GET | `/viagens/{id}/rota?posicao=` | rota da posição atual até o destino, pela árvore guardada |
| DELETE | `/viagens/{id}` | encerra a viagem e libera a árvore |
| GET | `/rota?origem=&destino=` | rota avulsa, sem guardar nada |
| GET | `/alcance?origem=&minutos=` | pontos alcançáveis em X minutos |
| GET | `/metrics` | RSS, CPU, requisições, erros, viagens abertas, memória e swap do sistema |
| POST | `/admin/reiniciar` | encerra o processo para o systemd subir de novo (403 sem `PERMITIR_REINICIO=1`) |

Exemplo com Campina Grande e João Pessoa (134 km):

```
curl -X POST "localhost:8000/viagens?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
curl "localhost:8000/viagens/1/rota?posicao=-7.2000,-35.5000"
curl -X DELETE localhost:8000/viagens/1
```

## 3. Variáveis de ambiente

| variável | padrão | o que faz |
|---|---|---|
| `MAP_FILE` | `data/campina_grande.map.gz` | mapa carregado (a VM usa `data/paraiba.map.gz`) |
| `PORT` | `8000` | porta |
| `MAX_CONCURRENT` | `0` | máximo de buscas ao mesmo tempo (0 deixa sem limite) |
| `MAX_ALCANCE_MIN` | `60` | maior valor aceito em `/alcance` |
| `CAPACIDADE_VIA` | `2` | carros por aresta na fórmula BPR do trânsito |
| `ARVORE_VALIDADE_S` | `60` | idade máxima da árvore; depois disso o recálculo refaz a busca |
| `VIAGEM_EXPIRA_S` | `300` | viagem sem recálculo por esse tempo é encerrada |
| `PERMITIR_REINICIO` | `0` | com `1`, libera `/admin/reiniciar` |

## 4. Pastas

| pasta | conteúdo |
|---|---|
| `app/` | o servidor |
| `tests/` | testes do servidor (mapa de teste em `tests/mini.map`) |
| `data/` | mapas (`*.map.gz`) e 300 pares de origem e destino por mapa (`pontos_*.json`, semente 42) |
| `tools/` | geração do mapa (`prepare_map.py`) e calibração (`calibrate.py`) |
| `load/` | scripts do k6; o experimento usa `load/viagem.js` |
| `deploy/` | instalação na VM, passo a passo em `deploy/README.md` |
| `experiments/` | scripts que rodam no hospedeiro e prova local com Docker |
| `analysis/` | tabelas e gráficos a partir dos resultados |
| `results/` | dados brutos, resumo e gráficos do experimento |
| `docs/` | calibração, prova local, roteiro do laboratório e rascunho do relatório |

Para gerar o mapa de novo, instale `requirements-tools.txt` e o `osmium-tool`, baixe `https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf` e rode:

```
python tools/prepare_map.py --lugar "Paraíba, Brazil" --nome paraiba --pbf nordeste-latest.osm.pbf
```

## 5. Experimento

O k6 roda no hospedeiro e chega à VM pelas portas redirecionadas do VirtualBox.

| hospedeiro | VM | serviço |
|---|---|---|
| 8080 | 8000 | aplicação (`rotas`) |
| 8081 | 8001 | monitor da VM (`rotas-monitor`, `deploy/monitor.py`) |
| 2222 | 22 | ssh |
| 8088 | 80 | nginx do teste de rede |

Se a 8080 do hospedeiro já estiver ocupada, troque a regra da aplicação (por exemplo para 18080) e rode os scripts com `PORTA_APP=18080`.

### 5.1 Cenários e carga

| cenário | CPUs | RAM |
|---|---|---|
| C1 | 1 | 768 MB (o padrão do `run_all.sh` é 512 MB, o teste de fumaça recomenda 768 MB) |
| C2 | 1 | 1 GB (referência) |
| C3 | 1 | 2 GB |
| C4 | 2 | 1 GB |

Cada usuário virtual do k6 (`load/viagem.js`) abre uma viagem, recalcula 6 vezes com uma pausa entre os recálculos e encerra. Os níveis são 1, 2, 5, 10, 20, 40 e 60 usuários. A cada nível o serviço é reiniciado, o k6 roda um aquecimento que fica fora da medição e depois 60 s de medição.

O serviço `rotas` tem `MemoryMax=80%` e `MemorySwapMax=1G` (`deploy/rotas.service`). A imagem do professor traz 12 GiB de swap, e com tanto swap a VM trava em vez de matar o processo. O swap da própria VM não é alterado.

### 5.2 Experimento completo

Os passos, com os prints, estão em `docs/roteiro_lcc.md`. Em resumo:

1. Criar a VM, testar a rede com o nginx e instalar a aplicação com `git clone` dentro da VM (`deploy/README.md`).
2. Instalar o k6 sem root com `experiments/instalar_k6.sh` e `export K6=~/bin/k6`.
3. Se a VM tem ssh, copiar a chave com `ssh-copy-id -p 2222 osboxes@localhost` (senha `osboxes.org`).
4. Rodar `experiments/teste_fumaca.sh`, que leva cerca de 6 min. Ele imprime recomendações e grava o comando completo em `results/fumaca/comando.sh`.
5. Rodar `results/fumaca/comando.sh`. Ele troca CPU e RAM com `VBoxManage` e percorre os níveis. Se for interrompido, rodar de novo continua de onde parou.
6. Rodar `python analysis/analyze.py`, que gera `results/resumo.csv`, `results/graficos/*.png` e `results/observacoes.md`.

O teste de fumaça sugere três ajustes:

- C1 com 768 MB, se a RAM livre da VM de 512 MB comportar menos de 3 viagens.
- Uma pausa maior entre recálculos, se a CPU com 10 usuários multiplicada por 6 passar de 60%.
- 2 repetições, se 3 passarem de 2h30.

Quando a VM não tem ssh, o teste liga `SEM_SSH=1`. Nesse modo o reinício entre níveis usa `POST /admin/reiniciar`, a memória, o swap e a CPU vêm só do monitor, e as mortes por falta de memória aparecem como mudanças de `inicio_epoch`. Ficam sem `vmstat` e sem o log do kernel.

### 5.3 Demonstração rápida

O experimento completo leva mais de 2 horas. Para mostrar o efeito ao vivo existe `experiments/demo_rapido.sh`. Ele usa a VM como está e roda dois níveis, 5 e 20 usuários, com 25 s de aquecimento e 30 s de medição cada. No fim imprime uma tabela com p95, req/s, erros, memória e swap.

```
experiments/demo_rapido.sh
```

Numa VM com 1 CPU e 1 GB, a execução inteira leva cerca de 3 min. O resultado típico:

| usuários | p95 do início | req/s | erros | memória máx. da VM | swap máx. |
|---|---|---|---|---|---|
| 5 | 1,4 s | 1,1 | 0% | 785 MB | 0 MB |
| 20 | 12,4 s | 2,2 | 0% | 1010 MB | 247 MB |

Em outro terminal, `experiments/acompanhar.sh` mostra a memória e o swap subindo a cada segundo.

### 5.4 O que o experimento completo mostrou

Medido num computador de casa (Core i3-2130, 7,6 GB), com 2 repetições por nível e pausa de 7 s entre recálculos. São 56 execuções, mais de 2 horas no total.

| cenário | primeiro nível com swap | primeiro nível com erros | req/s com 60 usuários | erros com 60 usuários |
|---|---|---|---|---|
| C1 (1 CPU, 768 MB) | 10 usuários | 20 usuários | 1,6 | 100% |
| C2 (1 CPU, 1 GB) | 20 usuários | 40 usuários | 1,6 | 100% |
| C3 (1 CPU, 2 GB) | 60 usuários | 60 usuários | 6,8 | 11% |
| C4 (2 CPUs, 1 GB) | 20 usuários | 20 usuários | 1,6 | 100% |

- Mais RAM adia o swap e os erros. O C3 aguenta 40 usuários sem swap, a 7,8 req/s.
- Duas CPUs (C4) não ajudaram. O C4 teve resultado pior que o C2. Uma explicação provável é a disputa por CPU no computador de casa, que tem 2 núcleos físicos e rodava também o k6 e outros serviços. Essa explicação não foi testada.
- Nenhuma execução teve reinício do serviço ou mensagem do OOM killer. Os erros são timeouts do k6 (30 s). O processo ficou lento por causa do swap e continuou vivo.
- O p95 de 30 s nos gráficos é o limite de timeout do k6. O tempo real das requisições que falharam é maior.
