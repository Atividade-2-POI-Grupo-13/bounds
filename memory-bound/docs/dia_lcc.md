# Dia no LCC3

Roteiro para a ida ao laboratório: o que levar, a ordem dos passos, os prints do relatório, a demonstração ao professor e como salvar o disco da VM.

## 1. Antes de ir

- Ensaio no Mac com o UTM (`deploy/README.md`, seção 8). Anotar três coisas:
  - se o ssh da VDI responde;
  - quanto `free -m` mostra com a VM parada;
  - se a aplicação sobe com 512 MB.
- Pendrive com:
  - o repositório inteiro (o mapa e as wheels já estão dentro);
  - o k6 para Linux x86_64: rodar `experiments/instalar_k6.sh` numa máquina Linux e copiar `~/bin/k6`.
- Conferir que `data/paraiba.map.gz` e `deploy/wheels/` estão no clone.

## 2. Ordem no dia

| passo | comando ou ação | tempo |
|---|---|---|
| 1 | Criar a VM e instalar (`deploy/README.md`, seções 1 a 5), tirando os prints da seção 3 deste documento | 20 min |
| 2 | `export K6=~/bin/k6` (do pendrive ou `experiments/instalar_k6.sh`) | 2 min |
| 3 | Com ssh: `ssh-copy-id -p 2222 osboxes@localhost` (senha `osboxes.org`) | 1 min |
| 4 | `experiments/teste_fumaca.sh` e print das recomendações | 6 min |
| 5 | Colar o comando que o teste de fumaça imprimir (`... experiments/run_all.sh`) | 2h10 (2 repetições) a 3h15 (3) |
| 6 | Durante o passo 5, num segundo terminal: `experiments/acompanhar.sh` e prints de um nível de C1 com swap ou reinício | |
| 7 | Copiar `results/raw/` para o pendrive (ou `git push`) | 2 min |
| 8 | Salvar o disco da VM (seção 5 deste documento) | 10 min |

Se o `run_all.sh` parar no meio (queda, falta de tempo), rodar o mesmo comando de novo continua de onde parou. Ele completa uma repetição de todos os cenários antes de começar a próxima.

## 3. Prints para o relatório

Seções do `docs/relatorio_rascunho.md`:

| seção | print |
|---|---|
| 2.1 | Terminal com o `cp` da VDI para `/tmp` |
| 2.1 | VirtualBox: criação da VM (nome, tipo Ubuntu 64-bit, pasta `/tmp`) |
| 2.1 | VirtualBox: Sistema com 1 CPU e 1024 MB |
| 2.1 | VirtualBox: Armazenamento com o disco existente |
| 2.1 | VirtualBox: Rede NAT, redirecionamento de portas (app 8080, ssh 2222, monitor 8081) |
| 2.1 | Console da VM com o login `osboxes` |
| 2.2 | Cópia do projeto (`scp` ou `deploy/servir_projeto.sh`) |
| 2.2 | Fim da saída do `./deploy/install.sh` (health, monitor, `free -h`, swap, ssh) |
| 2.2 | `systemctl status rotas` dentro da VM |
| 2.2 | `curl localhost:8080/health` no hospedeiro |
| 3.2 | Saída do `experiments/teste_fumaca.sh` |
| 3.2 | Início do `run_all.sh` com o tempo estimado |
| 3.3 | `experiments/acompanhar.sh` durante um nível de C1, mostrando swap subindo ou "REINICIOU" |

## 4. Demonstração ao professor (cerca de 5 minutos)

Três terminais no hospedeiro, VM no cenário C2 (1 CPU, 1 GB).

1. VirtualBox aberto na VM: mostrar CPU, memória e o redirecionamento de portas.
2. Terminal 1, a aplicação respondendo de fora da VM:

   ```
   curl localhost:8080/health
   curl -X POST "localhost:8080/viagens?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
   curl "localhost:8080/viagens/1/rota?posicao=-7.2000,-35.5000"
   ```

   No segundo comando, usar o número de `viagem` que o primeiro devolveu. Pontos a mostrar na resposta: a viagem de Campina Grande a João Pessoa tem 134 km, a árvore guardada usa cerca de 13 MB, e o recálculo responde com `arvore_nova: false`.
3. Terminal 2: `experiments/acompanhar.sh`.
4. Terminal 3, carga leve e depois pesada:

   ```
   BASE_URL=http://localhost:8080 DURATION=60s load/rodar.sh viagem 5 /tmp/demo5
   BASE_URL=http://localhost:8080 DURATION=90s load/rodar.sh viagem 40 /tmp/demo40
   ```

   No terminal 2: com 5 usuários a memória sobe pouco. Com 40 ela chega perto de 1 GB, entra swap, e a aplicação pode aparecer como "REINICIOU". A CPU fica com folga.
5. Mostrar `results/graficos/viagem_comparacao.png`: com a mesma carga, C3 (mais RAM) resolve e C4 (mais CPU) fica igual a C2.

## 5. Salvar o disco da VM no Drive

1. Voltar a VM para a configuração do roteiro e desligar:

   ```
   VBoxManage controlvm vm-rotas acpipowerbutton
   VBoxManage modifyvm vm-rotas --cpus 1 --memory 1024
   ```

2. O disco é o próprio `/tmp/ubuntu_serve_2204_poi.vdi`, com a aplicação instalada. Enviar esse arquivo para o Drive pelo navegador (ele tem alguns GB; começar o envio cedo).
3. Opcional, para guardar também a configuração da VM (CPU, memória, portas): `VBoxManage export vm-rotas -o /tmp/vm-rotas.ova` e enviar o `.ova`.

O `/tmp` pode ser apagado quando a máquina reinicia: só sair do laboratório depois que o envio terminar.

## 6. Perguntas prováveis

| pergunta | resposta curta | onde está o dado |
|---|---|---|
| É memory-bound mesmo ou é limitação do Python? | A CPU tem folga no ponto em que a memória acaba; mais RAM resolve e mais CPU não muda nada. | gráficos de CPU e de comparação |
| Guardar a árvore por viagem é artificial? | É a troca de memória por CPU que um app de navegação faz: recalcular pela árvore custa cerca de 2 ms; refazer a busca custa 280 ms. | `docs/calibracao.md` |
| Por que não usar vários processos para fugir do GIL? | Cada processo carrega o mapa de novo (cerca de 290 MB) e o trânsito deixa de ser compartilhado. Medido: threads 1,80 s, processos 0,74 s para 8 rotas. | `docs/relatorio_rascunho.md`, seção 1.1 |
| Por que o swap não degradou logo? | O swap guarda bem as árvores das viagens paradas; a queda forte vem quando ele acaba e o processo é morto. | gráficos de swap e de erros |
| A carga foi gerada de fora da VM? | Sim, k6 no hospedeiro, pela porta 8080. | `experiments/run_level.sh` |
| Como sabem que o processo morreu por falta de memória? | Reinícios do systemd e mensagens do OOM killer no log do kernel, contados em cada nível. | `results/resumo.csv`, colunas `reinicios` e `mensagens_oom` |
