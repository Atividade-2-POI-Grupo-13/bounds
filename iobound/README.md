# io-bound

Aplicação I/O bound da Atividade 2 de POI: um produtor e um consumidor trocando jobs por um buffer, cada um num app Spring Boot, conversando por HTTP.

| App | Porta | O que faz |
| --- | --- | --- |
| `buffer` | 8080 | Guarda até 10 jobs, cada um num arquivo gravado com `fsync`. |
| `produtor` | 8081 | `POST /produzir?jobs=N`: manda N jobs de 100 KB ao buffer. |
| `consumidor` | 8082 | `POST /consumir?jobs=N`: tira N jobs do buffer. |

Se o buffer está cheio ou vazio, ele recusa na hora, e quem pediu espera 100 ms e tenta de novo. Cada job passa duas vezes pela rede e é gravado, lido e apagado no disco. A CPU quase não trabalha.

## Preparar a VM

Na VM do roteiro (Ubuntu 22.04), instale as dependências e baixe o código:

```bash
sudo apt update && sudo apt install -y git openjdk-21-jdk-headless sysstat procps iproute2 curl python3-matplotlib
```

```bash
git clone https://github.com/Atividade-2-POI-Grupo-13/io-bound.git && cd io-bound
```

No VirtualBox, deixe desmarcado "Use Host I/O Cache" no controlador do disco, senão o disco quase não pesa. Para ver os apps do hospedeiro, redirecione as portas 18080, 18081 e 18082 do hospedeiro para 8080, 8081 e 8082 da VM.

## Rodar o experimento

Configure a VM no VirtualBox (com ela desligada), ligue e rode o cenário. Um comando compila os apps (só na primeira vez), sobe os três, roda o stress test, mede e gera os gráficos:

| Cenário | VM | Comando |
| --- | --- | --- |
| V1 (referência) | 1 CPU, 1024 MB | `./experimento.sh V1` |
| V2 (disco lento) | 1 CPU, 1024 MB, disco a 5 MB/s | `./experimento.sh V2` |
| V3 (mais CPU) | 2 CPUs, 1024 MB | `./experimento.sh V3` |
| V4 (menos memória) | 1 CPU, 768 MB | `./experimento.sh V4` |

Durante o experimento, `curl localhost:18080/estado` no hospedeiro mostra o buffer trabalhando.

O disco do V2 é limitado pelo VirtualBox, no terminal do hospedeiro, com a VM desligada. Troque `minha_vm` pelo nome da VM e `SATA` pelo nome do controlador (aparece em Configurações → Armazenamento):

```bash
VBoxManage bandwidthctl minha_vm add Disco --type disk --limit 5M
```

```bash
VBoxManage storageattach minha_vm --storagectl SATA --port 0 --device 0 --type hdd --medium /tmp/ubuntu_serve_2204_poi.vdi --bandwidthgroup Disco
```

Para tirar o limite depois, repita o segundo comando com `--bandwidthgroup none`.

## Resultados

Cada rodada vira uma pasta em `resultados/<data>_<hora>/`, com:

- `graficos.png`: disco, rede e CPU ao longo da rodada;
- os CSVs da medição, um ponto por segundo: `sistema.csv` (vmstat), `disco.csv` (iostat), `rede.csv` (sar), `processos.csv` (pidstat) e `conexoes.csv` (ss);
- `eventos.csv`, `info.txt`, `saida_comando.txt` e os logs dos apps.

A cada rodada também são refeitos `resultados/comparacao.png` (os cenários lado a lado) e `resultados/resumo.csv` (os números de cada rodada). Para refazê-los sem rodar de novo: `python3 plotar.py`.

## Arquivos

| Arquivo | O que é |
| --- | --- |
| `buffer/`, `produtor/`, `consumidor/` | Os três apps. As opções de cada um estão no seu `application.properties`. |
| `experimento.sh` | O experimento completo: sobe os apps, mede, roda a carga e gera os gráficos. |
| `stress.sh` | Dispara N produtores e N consumidores ao mesmo tempo. |
| `monitorar.sh` | Mede a máquina a cada segundo e grava os CSVs. |
| `plotar.py` | Gera os gráficos e o resumo. |
| `mvnw` | Baixa a versão certa do Maven e compila os apps. |
