# Prova local do perfil memory-bound (etapa 3)

Docker no Mac no lugar da VM. Cada nível começa com o container recém-criado.

- Comando: `experiments/perfil_local.sh`, depois `python analysis/perfil_local.py`.
- Carga: `load/viagem.js`. Cada usuário inicia uma viagem, recalcula 6 vezes com 3 s de direção entre os recálculos e avisa a chegada (viagem de 21 s).
- Cada nível dura 60 s: 21 s de aquecimento e 39 s de medição.
- Limites do container: 400 MB (C1), 900 MB (C2 e C4) e 1.900 MB (C3), cerca de 120 MB abaixo da VM equivalente. Swap extra de 1 GB em todos.
- Uma repetição por nível.

![Resultados por cenário](img/perfil_local.png)

## 1. Resultado

| cenário | 1º nível com swap | 1º nível com erros | p95 do início com 60 usuários | erros com 60 usuários | CPU média no 1º nível com swap |
|---|---|---|---|---|---|
| C1 (1 CPU, 512 MB) | 5 usuários | 20 usuários | 30 s (timeout) | 100% | 8% |
| C2 (1 CPU, 1 GB) | 40 usuários | 60 usuários | 7,5 s | 25% | 43% |
| C3 (1 CPU, 2 GB) | 60 usuários | nenhum | 2,2 s | 0% | 53% |
| C4 (2 CPU, 1 GB) | 40 usuários | 60 usuários | 4,1 s | 28% | 39% |

- A memória cresce com os usuários: em C3, de 341 MB (1 usuário) a 1.981 MB (60 usuários).
- Em C1 a memória acaba com 5 usuários. Com 10 usuários o p95 do início sobe de 355 ms para 1,2 s, com a CPU em 15%. Com 40 e 60, o processo é morto por falta de memória.
- Dobrar a RAM (C2 para C3) elimina os erros com 60 usuários (de 25% para 0%) e reduz o p95 de 7,5 s para 2,2 s.
- Dobrar a CPU (C2 para C4) mantém o swap e os erros iguais (28% contra 25%).
- A CPU média fica abaixo de 55% em todos os níveis. A memória chega ao limite antes da CPU.

## 2. Pontos de atenção

- Com 40 usuários, C3 tem p95 de 2,2 s sem swap. Esse aumento vem de rajadas de início de viagem disputando a CPU (média de 41%). Os erros e as mortes por falta de memória aparecem só nos cenários com pouca RAM.
- O swap absorve bem as árvores das viagens paradas: C2 usou 939 MB de swap com 40 usuários e ficou com p95 parecido com o de C3. A queda forte vem quando o swap também acaba e o processo é morto. Na VM, o tamanho do swap muda esse ponto, então ele precisa ser registrado (etapa 5).
- A CPU do Mac é 2 a 3 vezes mais rápida que a do LCC3. Na VM, a CPU média deve ficar mais alta nos mesmos níveis.

## 3. Tabela completa

| cenário | usuários | p95 início ms | p95 recálculo ms | req/s | erros % | RAM máx MB | swap máx MB | CPU média % | reinícios |
|---|---|---|---|---|---|---|---|---|---|
| C1 | 1 | 355 | 18 | 0.4 | 0.0 | 324 | 0 | 2 | 0 |
| C1 | 2 | 350 | 29 | 0.8 | 0.0 | 378 | 0 | 4 | 0 |
| C1 | 5 | 470 | 27 | 2.3 | 0.0 | 419 | 247 | 8 | 0 |
| C1 | 10 | 1199 | 99 | 4.9 | 0.0 | 419 | 538 | 15 | 0 |
| C1 | 20 | 10609 | 2575 | 8.5 | 0.3 | 419 | 615 | 28 | 0 |
| C1 | 40 | 30001 | 11816 | 5.6 | 56.9 | 419 | 1066 | 34 | 1 |
| C1 | 60 | 30001 | 30001 | 2.6 | 100.0 | 419 | 1031 | 31 | 1 |
| C2 | 1 | 345 | 17 | 0.6 | 0.0 | 346 | 0 | 3 | 0 |
| C2 | 2 | 345 | 25 | 1.0 | 0.0 | 360 | 0 | 4 | 0 |
| C2 | 5 | 339 | 20 | 2.3 | 0.0 | 409 | 0 | 6 | 0 |
| C2 | 10 | 505 | 22 | 4.7 | 0.0 | 542 | 0 | 13 | 0 |
| C2 | 20 | 457 | 30 | 9.7 | 0.0 | 856 | 0 | 22 | 0 |
| C2 | 40 | 2129 | 581 | 18.4 | 0.0 | 944 | 939 | 43 | 0 |
| C2 | 60 | 7454 | 3498 | 22.3 | 25.4 | 944 | 1039 | 50 | 1 |
| C3 | 1 | 330 | 15 | 0.6 | 0.0 | 341 | 0 | 2 | 0 |
| C3 | 2 | 327 | 16 | 0.9 | 0.0 | 356 | 0 | 4 | 0 |
| C3 | 5 | 375 | 23 | 2.3 | 0.0 | 445 | 0 | 8 | 0 |
| C3 | 10 | 413 | 22 | 4.7 | 0.0 | 653 | 0 | 15 | 0 |
| C3 | 20 | 704 | 55 | 9.6 | 0.0 | 856 | 0 | 22 | 0 |
| C3 | 40 | 2215 | 466 | 18.5 | 0.0 | 1655 | 0 | 41 | 0 |
| C3 | 60 | 2157 | 1491 | 26.3 | 0.0 | 1981 | 571 | 53 | 0 |
| C4 | 1 | 341 | 17 | 0.4 | 0.0 | 336 | 0 | 3 | 0 |
| C4 | 2 | 399 | 29 | 1.0 | 0.0 | 395 | 0 | 5 | 0 |
| C4 | 5 | 569 | 35 | 2.3 | 0.0 | 472 | 0 | 8 | 0 |
| C4 | 10 | 466 | 29 | 5.1 | 0.0 | 568 | 0 | 13 | 0 |
| C4 | 20 | 874 | 108 | 9.6 | 0.0 | 870 | 0 | 24 | 0 |
| C4 | 40 | 1734 | 425 | 19.2 | 0.0 | 944 | 817 | 39 | 0 |
| C4 | 60 | 4094 | 2113 | 23.3 | 27.7 | 944 | 1061 | 53 | 1 |
