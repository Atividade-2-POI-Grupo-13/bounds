# Rascunho do relatório: aplicação memory-bound

Trechos entre colchetes são para preencher depois da ida ao LCC3. Os gráficos de `results/graficos/` aparecem depois de rodar `python analysis/analyze.py` com os dados de lá.

## 1. Aplicações desenvolvidas

### 1.1 Descrição e características

Serviço de rotas com trânsito para o estado da Paraíba, como o backend de um app de navegação. Python 3.10, FastAPI, um processo com um pool de threads.

- O mapa vem do OpenStreetMap: 214.373 esquinas e 565.101 trechos de rua, carregados na RAM como grafo (cerca de 290 MB).
- `POST /viagens` inicia uma viagem. O servidor calcula a árvore de caminhos até o destino (Dijkstra no grafo invertido) e guarda enquanto a viagem durar.
- `GET /viagens/{id}/rota` recalcula a rota da posição atual seguindo a árvore guardada.
- `DELETE /viagens/{id}` encerra a viagem e libera a memória.
- Cada viagem ocupa os trechos da sua rota. O tempo de cada trecho segue a fórmula BPR de engenharia de tráfego: `tempo_livre × (1 + 0,15 × (fluxo / capacidade)^4)`. Rotas muito usadas ficam lentas e os recálculos desviam.
- `GET /rota` (rota avulsa) e `GET /alcance` (isócrona) completam a API.

Por que é memory-bound:

```
memória ≈ mapa + viagens ativas × árvore (≈ 20 MB) + cálculos em andamento × foto do trânsito (≈ 35 MB)
```

- A memória cresce com o número de usuários dirigindo ao mesmo tempo, mesmo quando eles não estão fazendo requisição.
- Iniciar uma viagem custa cerca de 280 ms de CPU; recalcular custa cerca de 2 ms. Um usuário dirigindo gasta pouca CPU e segura 20 MB.
- Quando a memória acaba, o Linux usa swap. Quando o swap também acaba, o OOM killer mata o processo e o systemd o reinicia, perdendo as viagens em andamento.

Como chegamos a esse desenho (cada versão foi medida em `docs/calibracao.md`):

- Rota avulsa com Dijkstra: 17 MB por requisição. Descartada como mecanismo principal porque a memória só acumulava com requisições simultâneas, e com 1 núcleo isso só acontece com a CPU em 100%.
- Foto do trânsito por requisição: 49 MB por requisição. Mesma limitação da anterior; ficou como parte do custo de cada cálculo.
- Estado por viagem: cerca de 20 MB por usuário ativo, com a CPU com folga. Adotado.

Sobre o GIL do Python: medimos 8 rotas em sequência (1,76 s), com `ThreadPoolExecutor(4)` (1,80 s) e com `ProcessPoolExecutor(4)` (0,74 s). Threads não paralelizam o Dijkstra. Processos paralelizam, mas cada processo carrega o mapa de novo e o trânsito deixa de ser compartilhado. Ficamos com um processo. Como a CPU tem folga no ponto em que a memória acaba, o limite está na memória.

### 1.2 Monitoramento

- Desempenho, medido de fora da VM com o k6 no hospedeiro: latência média, p50, p95 e p99 (geral e por tipo de requisição), vazão em req/s e taxa de erro.
- VM: `vmstat 1` dentro da VM (CPU, memória livre, buffers, cache, swap usado, swap in/out).
- Aplicação: `/metrics` a cada segundo (RSS, pico de RSS, CPU do processo, viagens ativas, requisições em andamento).
- VM vista de fora: monitor em processo separado (`deploy/monitor.py`), lido pelo hospedeiro a cada segundo. Mostra memória, swap e CPU da VM e o RSS da aplicação, e continua respondendo quando a aplicação está ocupada ou reiniciando.
- Falhas por memória: reinícios do serviço (`systemctl show rotas -p NRestarts`) e mensagens do OOM killer (`journalctl -k`).

## 2. Configuração da VM e deploy

### 2.1 Etapas da VM

Roteiro completo em `deploy/README.md`.

1. Cópia da VDI `ubuntu_serve_2204_poi.vdi` de `/local/uasc/images` para `/tmp`. [PRINT]
2. Criação da VM `vm-rotas`: Linux Ubuntu 64-bit, pasta em `/tmp`, 1 CPU, 1 GB, disco existente. [PRINT]
3. Rede NAT com redirecionamento: hospedeiro 8080 para 8000 (aplicação) e 2222 para 22 (ssh). [PRINT]
4. Login com `osboxes` / `osboxes.org`. [PRINT]

### 2.2 Requisitos e deploy

- Requisitos: Ubuntu 22.04, Python 3.10, FastAPI, uvicorn e psutil. O mapa vai no repositório (`data/paraiba.map.gz`, 5,7 MB).
- Cópia do projeto: `scp -P 2222 -r memory-bound-rotas osboxes@localhost:~/`. [PRINT]
- Instalação: `./deploy/install.sh`. Cria o ambiente Python, instala as dependências a partir das wheels do repositório (funciona sem internet) e liga o serviço `rotas` no systemd com `Restart=always`. [PRINT da saída]
- Verificação: `systemctl status rotas` e `curl localhost:8080/health` no hospedeiro. [PRINT]
- Memória e swap da VM: [colar `free -h` e `swapon --show`]. O swap não muda entre cenários.

## 3. Teste de stress

### 3.1 Cenários

| cenário | CPU | RAM | para que serve |
|---|---|---|---|
| C1 | 1 | 512 MB | pouca memória: deve degradar cedo |
| C2 | 1 | 1 GB | configuração do roteiro (linha de base) |
| C3 | 1 | 2 GB | mais memória, mesma CPU |
| C4 | 2 | 1 GB | mais CPU, mesma memória |

C2 contra C3 isola o efeito da memória. C2 contra C4 isola o efeito da CPU.

### 3.2 Como os testes foram feitos

- Carga gerada no hospedeiro, fora da VM, com o k6 (`load/viagem.js`).
- Cada usuário virtual dirige viagens: inicia, dirige 5 s, recalcula, repete 6 vezes e avisa a chegada (35 s por viagem). Origem e destino vêm de 300 pares fixos.
- Níveis: 1, 2, 5, 10, 20, 40 e 60 usuários simultâneos.
- Cada nível: 35 s de aquecimento (fora da medição) e 60 s de medição, [3] repetições.
- O serviço reinicia antes de cada nível, para começar com a memória limpa.
- Tudo automatizado em `experiments/run_all.sh`. Hospedeiro: [modelo, CPUs, RAM].

### 3.3 Resultados

Prova local antes do LCC3 (Docker no Mac, limites equivalentes aos cenários, uma repetição; detalhes em `docs/perfil_local.md`):

![Prova local do perfil](img/perfil_local.png)

Resultados na VM:

![p95 do início de viagem](../results/graficos/viagem_p95_inicio.png)

![Erros](../results/graficos/viagem_erros.png)

![Memória usada da VM](../results/graficos/viagem_memoria.png)

![Swap usado](../results/graficos/viagem_swap.png)

![CPU da VM](../results/graficos/viagem_cpu.png)

![Vazão](../results/graficos/viagem_vazao.png)

![Comparação C2, C3 e C4](../results/graficos/viagem_comparacao.png)

[Colar os pontos de `results/observacoes.md`.]

### 3.4 Interpretação e conclusões

[Conferir com os números do LCC3. Na prova local o resultado foi este:]

- Mais usuários ocupam mais memória: de 341 MB com 1 usuário para 1.981 MB com 60 (C3).
- C1 entra em swap com 5 usuários e o p95 do início de viagem sobe de 355 ms para 1,2 s com 10 usuários, com a CPU em 15%.
- Com o swap esgotado, o processo é morto e as viagens em andamento se perdem: 25% de erros em C2 com 60 usuários.
- Mais RAM (C3) eliminou os erros com 60 usuários. Mais CPU (C4) deixou swap e erros iguais aos de C2.
- A CPU média ficou abaixo de 55% em todos os níveis. O recurso que limita a aplicação é a memória.

### 3.5 Limitações

- O k6 roda no mesmo hospedeiro que a VM e disputa CPU com ela. A configuração foi a mesma em todos os cenários.
- O swap absorve bem as árvores das viagens paradas, então o tamanho do swap da VM muda o ponto de degradação.
- Com 40 ou mais usuários, inícios de viagem simultâneos disputam a CPU e o p95 sobe mesmo sem swap (C3).
- A aplicação usa um processo Python. A segunda CPU de C4 só ajuda em tarefas fora do Python (kernel, swap).
