# Rotas com trânsito (aplicação memory-bound)

Backend de um app de navegação para o estado da Paraíba: calcula rotas, acompanha viagens com recálculo e simula o trânsito gerado pelos próprios usuários. É a aplicação memory-bound da Atividade 2 de Provisionamento e Operação de Infraestrutura (UFCG).

## 1. Por que é memory-bound

- O mapa da Paraíba (214 mil esquinas, 565 mil trechos de rua) fica carregado na RAM: cerca de 290 MB.
- Cada viagem ativa guarda no servidor a árvore de caminhos até o destino, para recalcular a rota sem refazer a busca: cerca de 20 MB por viagem, enquanto o motorista dirige.
- Cada cálculo em andamento monta a sua foto do trânsito (um tempo por trecho de rua): cerca de 35 MB enquanto calcula.
- Iniciar uma viagem custa cerca de 280 ms de CPU. Recalcular pela árvore guardada custa cerca de 2 ms.

Modelo de memória:

```
memória ≈ mapa + viagens ativas × árvore + cálculos em andamento × foto do trânsito
```

Com mais usuários dirigindo, a memória sobe até o limite da máquina, enquanto a CPU fica com folga. Daí em diante entra swap, e depois o processo é morto por falta de memória. Os números estão em `docs/calibracao.md` e `docs/perfil_local.md`.

## 2. Rodar localmente

Precisa de Python 3.10 ou mais novo.

```
python3 -m venv .venv
.venv/bin/pip install -r requirements-tools.txt
MAP_FILE=data/paraiba.map.gz .venv/bin/python -m app.main
```

Testes: `.venv/bin/python -m pytest`.

Com Docker: `docker build -t rotas . && docker run -p 8000:8000 rotas`.

## 3. Endpoints

Coordenadas no formato `LAT,LON`. Erros: 400 para coordenada inválida ou fora do mapa, 404 quando não há caminho ou a viagem não existe.

| método | caminho | o que faz |
|---|---|---|
| GET | `/health` | status, nós e arestas do mapa |
| GET | `/rota?origem=&destino=` | rota avulsa com o trânsito de agora |
| POST | `/viagens?origem=&destino=` | inicia uma viagem e guarda a árvore de caminhos |
| GET | `/viagens/{id}/rota?posicao=` | recálculo a partir da posição atual |
| DELETE | `/viagens/{id}` | chegada: libera a árvore e sai do trânsito |
| GET | `/alcance?origem=&minutos=` | isócrona: o que se alcança em X minutos |
| GET | `/metrics` | RSS, pico de RSS, CPU, requisições, erros, viagens ativas |

Exemplos (Campina Grande para João Pessoa):

```
curl localhost:8000/health
curl "localhost:8000/rota?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
curl -X POST "localhost:8000/viagens?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
curl "localhost:8000/viagens/1/rota?posicao=-7.2000,-35.5000"
curl -X DELETE localhost:8000/viagens/1
curl "localhost:8000/alcance?origem=-7.2307,-35.8817&minutos=30"
curl localhost:8000/metrics
```

A rota de exemplo tem 134 km e 1h47 sem trânsito. A resposta traz `tempo_s` (com trânsito), `tempo_sem_transito_s`, `distancia_m`, `nos_rota`, `rota` (coordenadas) e quanto de memória a busca usou.

## 4. Variáveis de ambiente

| variável | padrão | o que faz |
|---|---|---|
| `MAP_FILE` | `data/campina_grande.map.gz` | mapa carregado (nos experimentos: `data/paraiba.map.gz`) |
| `PORT` | `8000` | porta |
| `MAX_CONCURRENT` | `0` | cálculos ao mesmo tempo; acima disso esperam na fila (0 = sem limite) |
| `MAX_ALCANCE_MIN` | `60` | minutos máximos do `/alcance` |
| `CAPACIDADE_VIA` | `2` | veículos por trecho antes de o trânsito pesar (fórmula BPR) |
| `ARVORE_VALIDADE_S` | `60` | idade da árvore de uma viagem antes de refazer com o trânsito novo |
| `VIAGEM_EXPIRA_S` | `300` | viagem sem uso por esse tempo é encerrada |

## 5. Gerar o mapa

Roda só no Mac (usa osmnx). Campina Grande vem do Overpass. Para o estado inteiro, o Overpass recusa a consulta, então o mapa sai do extrato do Geofabrik, recortado com `osmium` (`brew install osmium-tool`).

```
python tools/prepare_map.py --lugar "Campina Grande, Paraíba, Brazil" --nome campina_grande
curl -L -o nordeste.osm.pbf https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf
python tools/prepare_map.py --lugar "Paraíba, Brazil" --nome paraiba --pbf nordeste.osm.pbf
```

Cada execução gera `data/NOME.map.gz` e `data/pontos_NOME.json` (300 pares de origem e destino com semente fixa, para a carga ser reproduzível). Medir memória e CPU de um mapa: `python tools/calibrate.py data/paraiba.map.gz --viagens`.

## 6. Pastas

| pasta | conteúdo |
|---|---|
| `app/` | servidor: `main.py` (HTTP), `graph.py` (mapa), `routing.py` (Dijkstra), `traffic.py` (trânsito), `trips.py` (viagens), `metrics.py` |
| `tools/` | preparação do mapa e calibração |
| `load/` | scripts k6 (`viagem.js`, `rota.js`, `alcance.js`) e `rodar.sh` para um nível de carga |
| `deploy/` | instalação na VM (`install.sh`, serviço systemd, wheels para instalar sem internet) e o roteiro em `deploy/README.md` |
| `experiments/` | troca de cenário na VM, execução dos níveis e coleta (rodam no hospedeiro Linux do LCC3); `perfil_local.sh` faz a prova local com Docker |
| `analysis/` | `analyze.py` gera `results/resumo.csv`, `results/graficos/` e `results/observacoes.md` |
| `docs/` | calibração, prova local do perfil e rascunho do relatório |

## 7. Experimentos no LCC3

1. Criar a VM e instalar: `deploy/README.md`.
2. No hospedeiro, copiar a chave ssh para a VM uma vez: `ssh-copy-id -p 2222 osboxes@localhost`.
3. Baixar o k6 para a home (sem root): binário único em https://github.com/grafana/k6/releases, e exportar `K6=~/bin/k6`.
4. Rodar tudo: `experiments/run_all.sh`. Ele mostra o tempo estimado antes de começar. Com o padrão (4 cenários, 7 níveis, 3 repetições) dá cerca de 3 h; com `REPETICOES=2`, cerca de 2 h.
5. No Mac: `python analysis/analyze.py`.
