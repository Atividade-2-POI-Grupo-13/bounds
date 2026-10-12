# Dia no LCC3

Anotações para o dia do experimento e da demonstração.

## 1. Antes de ir

- [ ] Ensaio no Mac com UTM (`deploy/README.md`, seção 8). Ver se o ssh da VDI responde, quanto `free -m` mostra e se a aplicação sobe com 512 MB.
- [ ] Pendrive com o repositório. O mapa e as wheels já estão dentro.
- [ ] `~/bin/k6` para Linux x86_64 no pendrive. Gerar com `experiments/instalar_k6.sh` numa máquina Linux.

## 2. Sequência

1. Criar a VM (`deploy/README.md`, seção 1). 10 min.
2. Testar a rede com o nginx e o redirecionamento de portas (seção 2). 10 min.
3. Copiar, instalar e verificar a aplicação (seções 3 a 5). 10 min.
4. `export K6=~/bin/k6`.
5. Se a VM tem ssh: `ssh-copy-id -p 2222 osboxes@localhost`.
6. `experiments/teste_fumaca.sh`. 6 min.
7. Colar o comando que o teste de fumaça imprimir (`... experiments/run_all.sh`). 2h08 com 2 repetições, 3h13 com 3.
8. Em outro terminal, durante o passo 7: `experiments/acompanhar.sh`.
9. Copiar `results/raw/` para o pendrive ou fazer `git push`.
10. Salvar o disco da VM (seção 5 abaixo). 10 min.

Se o `run_all.sh` parar, rodar o mesmo comando retoma do nível interrompido. Cada repetição termina em todos os cenários antes de a próxima começar.

## 3. Prints

Todos vão para `docs/relatorio_rascunho.md`, na seção indicada.

Seção 2.1:

- [ ] `cp` da VDI para `/tmp`
- [ ] Criação da VM (nome, Ubuntu 64-bit, pasta `/tmp`)
- [ ] 1 CPU e 1024 MB
- [ ] Disco existente
- [ ] Console com o login `osboxes`
- [ ] `systemctl status nginx` e `curl localhost:80` na VM
- [ ] `curl localhost:80` falhando no hospedeiro
- [ ] Redirecionamento de portas com as 4 regras
- [ ] `curl localhost:8088` no hospedeiro devolvendo a página do nginx

Seção 2.3:

- [ ] Cópia do projeto (`scp` ou `deploy/servir_projeto.sh`)
- [ ] Fim da saída do `./deploy/install.sh`
- [ ] `systemctl status rotas` na VM
- [ ] `curl localhost:8080/health` no hospedeiro

Seções 3.2 e 3.3:

- [ ] Saída do `teste_fumaca.sh`
- [ ] Início do `run_all.sh` com o tempo estimado
- [ ] `acompanhar.sh` num nível de C1 com swap subindo ou "REINICIOU"

## 4. Demonstração (5 min)

VM em C2 (1 CPU, 1 GB). Três terminais no hospedeiro.

1. VirtualBox: mostrar CPU, memória e redirecionamento de portas.
2. Terminal 1:

   ```
   curl localhost:8080/health
   curl -X POST "localhost:8080/viagens?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
   curl "localhost:8080/viagens/1/rota?posicao=-7.2000,-35.5000"
   ```

   No terceiro comando, usar o número da viagem devolvido pelo segundo. A abertura devolve 134 km e `memoria_arvore_mb` perto de 13. O recálculo devolve `arvore_nova: false`.
3. Terminal 2: `experiments/acompanhar.sh`.
4. Terminal 3:

   ```
   BASE_URL=http://localhost:8080 DURATION=60s load/rodar.sh viagem 5 /tmp/demo5
   BASE_URL=http://localhost:8080 DURATION=90s load/rodar.sh viagem 40 /tmp/demo40
   ```

   No terminal 2 a memória da VM sobe com os usuários. Na prova local, C2 com 40 usuários entrou em swap com a CPU em 43%.
5. Abrir `results/graficos/viagem_comparacao.png`.

## 5. Salvar o disco da VM

1. Desligar e voltar para 1 CPU e 1 GB:

   ```
   VBoxManage controlvm vm-rotas acpipowerbutton
   VBoxManage modifyvm vm-rotas --cpus 1 --memory 1024
   ```

2. Enviar `/tmp/ubuntu_serve_2204_poi.vdi` para o Drive pelo navegador. São alguns GB, então começar cedo.
3. Opcional: `VBoxManage export vm-rotas -o /tmp/vm-rotas.ova` e enviar o `.ova`, que guarda também CPU, memória e portas.

O `/tmp` pode ser limpo quando a máquina reinicia. Só sair do laboratório com o envio terminado.

## 6. Se perguntarem

- **Por que memory-bound?** Na prova local a CPU ficou abaixo de 55% em todos os níveis. C3 (mais RAM) zerou os erros com 60 usuários e C4 (mais CPU) ficou como C2. Dados em `docs/perfil_local.md`.
- **Por que guardar a árvore por viagem?** Recalcular pela árvore custa 1,5 ms e uma busca nova custa cerca de 250 ms. A memória paga essa diferença (`docs/calibracao.md`, seção 4).
- **Por que um processo só?** Cada processo carregaria o mapa (290 MB) e o trânsito não seria mais compartilhado (`docs/calibracao.md`, seção 3).
- **Por que o swap não degradou logo?** Ele guarda as árvores das viagens paradas. A queda grande vem quando o swap acaba e o processo é morto.
- **A carga veio de fora da VM?** Veio. O k6 roda no hospedeiro e entra pela porta 8080 (`experiments/run_level.sh`).
- **Como sabem que o processo morreu por memória?** Pelos reinícios do systemd e pelas mensagens do OOM killer, contados por nível em `results/resumo.csv` (colunas `reinicios` e `mensagens_oom`).
