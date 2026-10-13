# Prova local do perfil memory-bound

Prova feita com Docker no Mac, antes de a VM existir. Serviu para escolher cenários e níveis. Os resultados do relatório vêm da VM (`README.md`, seção 5.4).

- Comandos: `experiments/perfil_local.sh` e `python analysis/perfil_local.py`. Dados em `results/local/`.
- Carga: `load/viagem.js` com `PAUSA_S=3`. Cada usuário abre uma viagem, recalcula 6 vezes e encerra (21 s por viagem).
- Nível: container recém-criado, 60 s de k6 (21 s de aquecimento, 39 s de medição), uma repetição.
- Limites de memória: 400 MB (C1), 900 MB (C2 e C4), 1.900 MB (C3). Ficam 112 a 148 MB abaixo da VM equivalente, a parte que o Ubuntu ocuparia.
- Swap extra de 1 GB em todos. CPU em % de 1 núcleo.

![Resultados por cenário](img/perfil_local.png)

## 1. Resumo

| cenário | 1º nível com swap | 1º nível com erros | p95 do início com 60 usuários | erros com 60 usuários | CPU no 1º nível com swap |
|---|---|---|---|---|---|
| C1 (1 CPU, 512 MB) | 5 usuários | 20 usuários | 30 s (timeout do k6) | 100% | 8% |
| C2 (1 CPU, 1 GB) | 40 usuários | 60 usuários | 7,5 s | 25% | 43% |
| C3 (1 CPU, 2 GB) | 60 usuários | nenhum | 2,2 s | 0% | 53% |
| C4 (2 CPU, 1 GB) | 40 usuários | 60 usuários | 4,1 s | 28% | 39% |

- Em C3 a memória vai de 341 MB (1 usuário) a 1.981 MB (60 usuários).
- C1 entra em swap com 5 usuários. Com 10, o p95 do início sobe de 355 ms para 1,2 s com CPU em 15%. Com 40 e 60, o processo é morto por falta de memória.
- C2 para C3 (dobro de RAM): erros com 60 usuários de 25% para 0%, p95 do início de 7,5 s para 2,2 s.
- C2 para C4 (dobro de CPU): swap e erros parecidos (28% contra 25%).
- A CPU média fica abaixo de 55% em todos os níveis.

## 2. Pontos de atenção

- C3 com 40 usuários tem p95 de 2,2 s sem swap, com CPU média de 41%. A causa provável são inícios de viagem simultâneos disputando a CPU.
- C2 com 40 usuários usou 939 MB de swap e teve p95 parecido com o de C3 (2,1 s contra 2,2 s). A queda forte vem quando o swap acaba e o processo é morto. O tamanho do swap da VM muda esse ponto e precisa ser registrado.
- Os tempos de CPU na VM devem ser maiores que no Mac. O teste de fumaça mede o custo do início de viagem no LCC3.

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
