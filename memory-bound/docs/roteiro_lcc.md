# Roteiro no LCC3

Passos do dia no laboratório: preparar a VM, mostrar a aplicação, rodar a demonstração e salvar o disco.

## 1. Antes de ir

- [ ] Ensaiar o deploy no Mac com UTM (`deploy/README.md`, seção 8). Conferir se o ssh da imagem responde, quanto `free -m` mostra e se a aplicação sobe com 512 MB.
- [ ] Levar o repositório num pendrive. O mapa e as wheels já estão dentro, então a instalação funciona sem internet.
- [ ] Levar um `~/bin/k6` para Linux x86_64 no pendrive. Ele sai de `experiments/instalar_k6.sh`, rodado numa máquina Linux.

## 2. Sequência do dia

1. Criar a VM (`deploy/README.md`, seção 1). 10 min.
2. Testar a rede com o nginx e o redirecionamento de portas (seção 2). 10 min.
3. Copiar, instalar e verificar a aplicação (seções 3 a 5). 10 min.
4. `export K6=~/bin/k6`.
5. Se a VM tem ssh, `ssh-copy-id -p 2222 osboxes@localhost`.
6. Mostrar a demonstração rápida (seção 4 abaixo). 5 min.
7. `experiments/teste_fumaca.sh`. 6 min.
8. `results/fumaca/comando.sh`, gerado pelo teste de fumaça com os valores recomendados. Leva 2h08 com 2 repetições e 3h13 com 3.
9. Durante o passo 8, em outro terminal, `experiments/acompanhar.sh`.
10. Copiar `results/raw/` para o pendrive ou fazer `git push`.
11. Salvar o disco da VM (seção 5). 10 min.

Se o `run_all.sh` parar, rodar o mesmo comando retoma do nível interrompido. Cada repetição termina em todos os cenários antes de a próxima começar.

## 3. Prints

Todos vão para `docs/relatorio_rascunho.md`, na seção indicada.

Seção 2.1:

- [ ] `cp` da imagem para `/tmp`
- [ ] Criação da VM (nome, Ubuntu 64-bit, pasta `/tmp`)
- [ ] 1 CPU e 1024 MB
- [ ] Disco existente
- [ ] Console com o login `osboxes`
- [ ] `systemctl status nginx` e `curl localhost:80` na VM
- [ ] `curl localhost:80` falhando no hospedeiro
- [ ] Redirecionamento de portas com as 4 regras
- [ ] `curl localhost:8088` no hospedeiro devolvendo a página do nginx

Seção 2.3:

- [ ] Cópia do projeto (`git clone` ou `deploy/servir_projeto.sh`)
- [ ] Fim da saída do `./deploy/install.sh`
- [ ] `systemctl status rotas` na VM
- [ ] `curl localhost:8080/health` no hospedeiro

Seções 3.2 e 3.3:

- [ ] Saída do `teste_fumaca.sh`
- [ ] Início do `run_all.sh`, com o tempo estimado
- [ ] `acompanhar.sh` num nível de C1 com o swap subindo

## 4. Demonstração (5 min)

A VM fica em C2 (1 CPU, 1 GB). Use dois terminais no hospedeiro.

1. No VirtualBox, mostre CPU, memória e redirecionamento de portas da VM.
2. No terminal 1, mostre a aplicação respondendo:

   ```
   curl localhost:8080/health
   curl -X POST "localhost:8080/viagens?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
   curl "localhost:8080/viagens/1/rota?posicao=-7.2000,-35.5000"
   ```

   No terceiro comando use o número da viagem que o segundo devolveu. A abertura devolve 134 km e `memoria_arvore_mb` perto de 13. O recálculo devolve `arvore_nova: false`.
3. No terminal 2, rode `experiments/acompanhar.sh` e deixe à vista.
4. No terminal 1, rode `experiments/demo_rapido.sh`. São dois níveis de cerca de 1,5 min cada, 5 usuários e depois 20.

   No terminal 2 a memória sobe com os usuários. Na última medição, com 5 usuários o p95 do início ficou em 1,4 s e o swap em 0 MB. Com 20 usuários o p95 foi de 12,4 s e o swap chegou a 247 MB.
5. Abra os gráficos do experimento completo (`results/graficos/viagem_comparacao.png` e `viagem_p95_inicio.png`) para mostrar as outras configurações.

## 5. Salvar o disco da VM

1. Desligar a VM e voltar para 1 CPU e 1 GB:

   ```
   VBoxManage controlvm vm-rotas acpipowerbutton
   VBoxManage modifyvm vm-rotas --cpus 1 --memory 1024
   ```

2. Enviar `/tmp/ubuntu_serve_2204_poi.vdi` para o Drive pelo navegador. São alguns GB, então comece cedo.
3. Opcionalmente exportar a VM com `VBoxManage export vm-rotas -o /tmp/vm-rotas.ova` e enviar o `.ova`, que guarda também CPU, memória e portas.

O `/tmp` pode ser limpo quando a máquina reinicia. Só saia do laboratório com o envio concluído.

## 6. Se perguntarem

- **Por que memory-bound?** Em todos os cenários da prova local a CPU média ficou abaixo de 55%. No experimento na VM, mais RAM (C3) adiou o swap de 20 para 60 usuários, e mais CPU (C4) não ajudou. Dados em `docs/perfil_local.md`.
- **Por que guardar a árvore por viagem?** Recalcular pela árvore custa 1,5 ms. Uma busca nova custa cerca de 250 ms. A memória paga essa diferença (`docs/calibracao.md`, seção 4).
- **Por que um processo só?** Cada processo carregaria o mapa de novo (290 MB) e o trânsito deixaria de ser compartilhado (`docs/calibracao.md`, seção 3).
- **O processo chegou a ser morto por falta de memória?** Nas 56 execuções do experimento completo, não. O swap segurou o processo, que ficou lento, e os erros foram timeouts de 30 s do k6. A contagem de reinícios e de mensagens do OOM killer fica em `results/resumo.csv` (colunas `reinicios` e `mensagens_oom`).
- **O swap de 12 GiB da imagem não atrapalha?** Ele impediria qualquer morte por falta de memória. O serviço `rotas` por isso roda com `MemoryMax=80%` e `MemorySwapMax=1G` (`deploy/rotas.service`). O swap da VM continua o mesmo.
- **A carga veio de fora da VM?** Sim. O k6 roda no hospedeiro e entra pela porta 8080 (`experiments/run_level.sh`).
