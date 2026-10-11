# Rotas com trânsito

Trabalho da Atividade 2 de Provisionamento e Operação de Infraestrutura (UFCG). A atividade pede uma aplicação cujo limite seja a memória, instalada numa VM, e um experimento que varie a CPU e a RAM da VM.

A nossa aplicação é o servidor de um app de navegação para a Paraíba. Nossa hipótese é que, com mais motoristas usando o app ao mesmo tempo, a VM fica sem memória bem antes de ficar sem CPU. Se for isso, a VM com o dobro de RAM deve aguentar a carga, e a VM com o dobro de CPU deve se sair igual à de referência.

## 1. Como o app é usado

Um motorista usa o app em três passos:

1. `POST /viagens` com origem e destino. O servidor calcula a rota e devolve o número da viagem.
2. Enquanto dirige, o app manda a posição de tempos em tempos para `GET /viagens/{id}/rota`, e o servidor devolve o caminho dali até o destino.
3. Ao chegar, `DELETE /viagens/{id}`.

Toda viagem aberta conta como um carro em cada rua da sua rota até o destino. Quando muitos carros passam pela mesma rua, o tempo dela sobe, e as rotas calculadas depois desviam dela. A capacidade de cada rua é baixa de propósito (2 carros), para que as poucas dezenas de motoristas do experimento já formem congestionamento.

## 2. Onde vai a memória

O mapa da Paraíba tem 214 mil cruzamentos e 565 mil trechos de rua, e fica todo carregado: uns 290 MB.

O passo 2 é a chamada mais frequente, então ele precisa ser barato. Para isso, ao abrir a viagem o servidor calcula de uma vez o melhor caminho até o destino a partir de todos os pontos em volta da rota (uma árvore de caminhos) e guarda essa árvore até a viagem terminar. Ela ocupa uns 20 MB. Com ela, cada recálculo custa 2 ms, contra 280 ms de uma busca nova.

As buscas completas (abrir viagem, rota avulsa e alcance) ainda copiam os tempos atuais de todas as ruas antes de começar, mais uns 35 MB enquanto rodam. O recálculo pela árvore não faz essa cópia. Ele só refaz a árvore, com busca completa, se ela tiver mais de 60 s ou se o carro se afastar demais da rota.

Somando:

```
memória ≈ 290 MB + 20 MB × viagens abertas + 35 MB × buscas rodando agora
```

Cada motorista novo, então, soma 20 MB enquanto dirige. Quando a RAM acaba, a VM passa a usar swap e as respostas ficam lentas. Quando o swap também acaba, o kernel mata o processo e o systemd sobe ele de novo, o que aparece como erros no k6. A CPU segue com folga em todo esse caminho. As medições estão em `docs/calibracao.md` e `docs/perfil_local.md`.

## 3. O experimento

A VM é a imagem Ubuntu 22.04 fornecida pelo professor, rodando no VirtualBox de uma máquina do LCC3. O k6 roda na própria máquina do LCC3, fora da VM, e alcança a aplicação por redirecionamento de portas do VirtualBox (8080 no hospedeiro para 8000 na VM).

Cenários da VM:

| cenário | CPUs | RAM |
|---|---|---|
| C1 | 1 | 512 MB |
| C2 | 1 | 1 GB |
| C3 | 1 | 2 GB |
| C4 | 2 | 1 GB |

C2 é a referência. C3 dobra a RAM e C4 dobra a CPU. C1 é o cenário apertado. O swap da imagem fica igual em todos e o tamanho dele é registrado junto com os resultados.

O k6 só usa o fluxo de viagens. Cada motorista simulado avança pela rota e faz a viagem completa: abre, recalcula 6 vezes com 5 s entre cada recálculo e encerra (35 s de viagem), e logo começa outra.

Em cada cenário, a carga sobe em níveis de 1, 2, 5, 10, 20, 40 e 60 motoristas ao mesmo tempo. A aplicação é reiniciada antes de cada nível, para todos começarem com a memória limpa. Não há limite de buscas simultâneas (`MAX_CONCURRENT=0`). Cada nível tem 35 s de aquecimento e 60 s de medição, e a sequência inteira se repete 3 vezes.

Em cada nível medimos:

- no k6: tempo de resposta (média, p50, p95, p99), requisições por segundo e porcentagem de erros;
- na VM: memória usada, swap, CPU, memória do processo e quantas vezes ele foi morto por falta de memória.

Antes do LCC3, rodamos a mesma carga no Docker, com containers limitados por `--cpus` e `--memory` (`docs/perfil_local.md`). Lá, C1 piorou primeiro, C3 chegou a 60 motoristas sem erros e C4 teve os mesmos erros de C2.

## 4. Rodar no próprio computador

Precisa de Python 3.10 ou mais novo.

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
MAP_FILE=data/paraiba.map.gz .venv/bin/python -m app.main
```

Para os testes e as ferramentas da pasta `tools/`, instalar `requirements-tools.txt` e rodar `.venv/bin/python -m pytest`.

Com Docker (a imagem já usa o mapa da Paraíba): `docker build -t rotas . && docker run -p 8000:8000 rotas`.

## 5. Endpoints

Coordenadas no formato `LAT,LON`. Coordenada inválida ou fora do mapa dá 400. Viagem inexistente ou sem caminho dá 404.

| método | caminho | o que faz |
|---|---|---|
| GET | `/health` | confirma que o mapa carregou |
| POST | `/viagens?origem=&destino=` | abre uma viagem |
| GET | `/viagens/{id}/rota?posicao=` | rota da posição atual até o destino |
| DELETE | `/viagens/{id}` | encerra a viagem |
| GET | `/rota?origem=&destino=` | rota avulsa, sem abrir viagem |
| GET | `/alcance?origem=&minutos=` | pontos alcançáveis em X minutos |
| GET | `/metrics` | memória, CPU, requisições, erros e viagens abertas |
| POST | `/admin/reiniciar` | reinicia o processo; só funciona com `PERMITIR_REINICIO=1` |

Exemplo, de Campina Grande a João Pessoa (134 km):

```
curl -X POST "localhost:8000/viagens?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
curl "localhost:8000/viagens/1/rota?posicao=-7.2000,-35.5000"
curl -X DELETE localhost:8000/viagens/1
```

## 6. Variáveis de ambiente

| variável | padrão | o que faz |
|---|---|---|
| `MAP_FILE` | `data/campina_grande.map.gz` | mapa carregado; o experimento usa `data/paraiba.map.gz` |
| `PORT` | `8000` | porta |
| `MAX_CONCURRENT` | `0` | máximo de buscas ao mesmo tempo; 0 deixa sem limite |
| `MAX_ALCANCE_MIN` | `60` | maior valor aceito em `/alcance` |
| `CAPACIDADE_VIA` | `2` | carros por trecho antes de o trânsito pesar |
| `ARVORE_VALIDADE_S` | `60` | depois desse tempo, o recálculo refaz a árvore com o trânsito novo |
| `VIAGEM_EXPIRA_S` | `300` | viagem sem recálculo por esse tempo é encerrada |
| `PERMITIR_REINICIO` | desligado | libera `/admin/reiniciar` |

## 7. Rodar o experimento no LCC3

Tudo roda na máquina Linux do LCC3. A VM é criada e configurada seguindo `deploy/README.md`.

1. Criar a VM e instalar a aplicação (`deploy/README.md`). No fim, o `install.sh` diz se a VM tem ssh.
2. Instalar o k6 sem root: `experiments/instalar_k6.sh` e `export K6=~/bin/k6`. Se o LCC3 estiver sem internet, levar o `~/bin/k6` num pendrive.
3. Se a VM tem ssh, copiar a chave uma vez: `ssh-copy-id -p 2222 osboxes@localhost`. Usuário e senha são os da imagem do professor (`osboxes`, `osboxes.org`), e a porta 2222 do hospedeiro é redirecionada para o ssh da VM.
4. Rodar `experiments/teste_fumaca.sh` (uns 6 minutos). No fim ele imprime o comando do passo 5 com as sugestões abaixo já aplicadas. Nada muda sozinho: dá para editar o comando antes de rodar.
5. Rodar o comando impresso. Para cada cenário, ele desliga a VM, muda CPU e RAM com `VBoxManage`, liga de novo e roda os níveis. Com 3 repetições leva umas 3h15, e com 2, umas 2h10. Se parar no meio, rodar o mesmo comando de novo: ele pula os níveis que já terminaram e refaz o nível interrompido.
6. Copiar `results/raw/` para o pendrive ou fazer `git push`.
7. No computador de casa: `python analysis/analyze.py`. Sai a tabela `results/resumo.csv`, os gráficos em `results/graficos/` e um resumo em `results/observacoes.md`.

A máquina do LCC3 e a imagem da VM só são conhecidas no dia, então o teste de fumaça faz três medições curtas:

- a memória livre na VM do C1 com a aplicação carregada. Se cabem menos de 3 viagens antes do swap, ele sugere subir o C1 para 768 MB, e o relatório registra o valor usado;
- a CPU da VM com 10 motoristas, multiplicada por 6 para prever 60. Se a previsão passa de 60%, ele sugere uma pausa maior entre recálculos (`PAUSA_S`, 5 s por padrão), para a CPU não chegar perto do limite antes da memória;
- o tempo total. Se 3 repetições passam de 2h30, ele sugere 2.

Ele também confere se a VM tem ssh e liga o modo `SEM_SSH=1` quando não tem.

Para ver a memória subindo ao vivo, rodar `experiments/acompanhar.sh` num segundo terminal.

### Monitor da VM

Com a aplicação sobrecarregada, o `/metrics` dela chega a levar 9 s para responder, e fica mudo enquanto o processo reinicia. Por isso a VM tem um segundo serviço, `rotas-monitor` (`deploy/monitor.py`), que lê memória, swap e CPU direto do sistema. Ele escuta na porta 8001 da VM, redirecionada para a 8081 do hospedeiro, e é de onde a coleta e o `acompanhar.sh` leem.

### VM sem ssh

O experimento roda mesmo se a imagem da VM vier sem ssh:

- o reinício antes de cada nível, feito com `systemctl` quando há ssh, passa a ser feito por `POST /admin/reiniciar`;
- memória, swap e CPU vêm só do monitor;
- as mortes por falta de memória são contadas pelas vezes que a hora de início do processo muda durante o nível. O reinício proposital acontece antes da coleta começar e não entra nessa conta.

Nesse modo ficam faltando o `vmstat` e as mensagens do kernel sobre falta de memória.

## 8. Mapas

Os mapas já estão em `data/`. Para gerar de novo, instalar `requirements-tools.txt` e o `osmium-tool`. O mapa do estado sai do extrato do Geofabrik, porque o Overpass recusa uma consulta desse tamanho.

```
curl -L -o nordeste.osm.pbf https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf
python tools/prepare_map.py --lugar "Paraíba, Brazil" --nome paraiba --pbf nordeste.osm.pbf
```

Cada mapa vem com `data/pontos_NOME.json`: 300 pares de origem e destino sorteados com semente fixa, que o k6 usa.

## 9. Pastas

| pasta | conteúdo |
|---|---|
| `app/` | o servidor |
| `tools/` | geração do mapa e calibração |
| `load/` | scripts do k6 |
| `deploy/` | instalação na VM e o passo a passo em `deploy/README.md` |
| `experiments/` | scripts que rodam no LCC3: troca de cenário, níveis de carga, coleta |
| `analysis/` | tabela e gráficos a partir dos resultados |
| `docs/` | calibração, teste local com Docker, rascunho do relatório e roteiro do dia no LCC3 (`docs/dia_lcc.md`) |
