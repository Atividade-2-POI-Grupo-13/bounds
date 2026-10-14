# io-bound

Aplicação I/O bound da Atividade 2 de POI: um produtor e um consumidor trocando jobs por um buffer, cada um num app Spring Boot, conversando por HTTP.

| App | Porta | O que faz |
| --- | --- | --- |
| `buffer` | 8080 | Guarda até 10 jobs, cada um num arquivo gravado com `fsync`. |
| `produtor` | 8081 | `POST /produzir?jobs=N`: manda N jobs de 100 KB ao buffer. |
| `consumidor` | 8082 | `POST /consumir?jobs=N`: tira N jobs do buffer. |

Se o buffer está cheio ou vazio, ele recusa na hora, e quem pediu espera 100 ms e tenta de novo. Cada job passa duas vezes pela rede e é gravado, lido e apagado no disco. A CPU quase não trabalha.

## Rodar o experimento

Só precisa do Docker. Um comando compila tudo, sobe os três apps num container limitado, roda o stress test, mede e gera os gráficos:

```bash
./experimento.sh C1
```

| Cenário | CPUs | Memória | Disco |
| --- | --- | --- | --- |
| C1 (referência) | 1 | 1 GB | sem limite |
| C2 (disco lento) | 1 | 1 GB | 5 MB/s |
| C3 (mais CPU) | 2 | 1 GB | sem limite |
| C4 (mais memória) | 1 | 2 GB | sem limite |

Ou com valores escolhidos na mão (`./experimento.sh --help` lista tudo):

```bash
./experimento.sh --cpus 2 --memoria 512m --disco 20mb --clientes 100 --jobs 50
```

## Resultados

Cada rodada vira uma pasta em `resultados/<data>_<hora>/`, com:

- `graficos.png`: disco, rede e CPU ao longo da rodada;
- os CSVs da medição, um ponto por segundo: `sistema.csv` (vmstat), `disco.csv` (iostat), `rede.csv` (sar), `processos.csv` (pidstat) e `conexoes.csv` (ss);
- `eventos.csv`, `info.txt`, `saida_comando.txt` e os logs dos apps.

A cada rodada também são refeitos `resultados/comparacao.png` (os cenários lado a lado) e `resultados/resumo.csv` (os números de cada rodada). Para refazê-los sem rodar de novo: `python3 plotar.py`.

## Rodar sem Docker

Precisa de Java 21 e Maven. Suba os apps em três terminais, o buffer primeiro:

```bash
mvn -pl buffer spring-boot:run
```

```bash
mvn -pl produtor spring-boot:run
```

```bash
mvn -pl consumidor spring-boot:run
```

E rode o stress test medindo (só no Linux, com `sudo apt install sysstat procps iproute2 curl`):

```bash
./monitorar.sh ./stress.sh 50 100
```

## Arquivos

| Arquivo | O que é |
| --- | --- |
| `buffer/`, `produtor/`, `consumidor/` | Os três apps. As opções de cada um estão no seu `application.properties`. |
| `experimento.sh` | O experimento completo num container (usa `Dockerfile` e `docker/entrypoint.sh`). |
| `stress.sh` | Dispara N produtores e N consumidores ao mesmo tempo. |
| `monitorar.sh` | Mede a máquina a cada segundo e grava os CSVs. |
| `plotar.py` | Gera os gráficos e o resumo. |
