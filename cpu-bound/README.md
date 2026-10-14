# Hash de senhas

Aplicação CPU-bound da Atividade 2 de Provisionamento e Operação de Infraestrutura (UFCG).

É um serviço que calcula hashes de senha com PBKDF2 (HMAC-SHA256), o mesmo algoritmo que sistemas de login usam para guardar senhas. Escrito em Java 17, sem dependências, usando o servidor HTTP que acompanha o JDK.

O PBKDF2 repete uma função criptográfica milhares de vezes de propósito, para encarecer ataques de força bruta. Por isso cada pedido gasta só processador: não lê disco, não acessa rede e não guarda nada entre pedidos. O custo é proporcional ao parâmetro `iteracoes`:

```
tempo por pedido ∝ iteracoes        capacidade ≈ processadores / tempo por pedido
```

O servidor tem uma thread de trabalho por processador. Pedidos que chegam com todas as threads ocupadas esperam numa fila sem limite, e é essa fila que faz o tempo de resposta crescer quando a demanda passa da capacidade.

As medições de tempo e vazão estão em `docs/calibracao.md`.

## 1. Rodar

Precisa de um JDK 17 ou mais novo para compilar e de Java 17 ou mais novo para executar.

```
./build.sh
java -Xms128m -Xmx128m -jar app-cpu.jar
```

A memória da JVM fica fixa em 128 MB, para que mudar a RAM da máquina não altere o comportamento da aplicação.

Com Docker, a imagem compila e roda a aplicação:

```
docker build -t app-cpu .
docker run --rm -p 8080:8080 --cpuset-cpus=4 app-cpu
```

`--cpuset-cpus` escolhe os núcleos que o container pode usar, e a aplicação abre uma thread por núcleo. Em processadores com núcleos de tipos diferentes, prefira `--cpuset-cpus` a `--cpus` (ver `docs/calibracao.md`).

## 2. Endpoints

Todas as rotas usam GET. Parâmetro ausente ou inválido devolve 400, rota inexistente devolve 404 e outro método devolve 405.

| método | caminho | o que faz |
|---|---|---|
| GET | `/health` | processadores vistos pela aplicação e threads de trabalho |
| GET | `/hash?senha=&iteracoes=` | sorteia um salt e calcula o hash da senha |
| GET | `/verificar?senha=&salt=&hash=&iteracoes=` | recalcula o hash com o salt informado e diz se confere |

Monitoramento, num servidor separado na porta 8081, com uma thread própria, para responder mesmo com a fila de hashes cheia:

| método | caminho | o que faz |
|---|---|---|
| GET | `/metrics` (porta 8081) | fila, threads ocupadas, pedidos atendidos, erros, CPU do processo (100% = 1 núcleo), memória do processo (RSS) e da JVM |

`iteracoes` vai de 1 a 10.000.000 (padrão 100.000). As respostas trazem `tempo_ms`, o tempo só do cálculo.

```
curl "localhost:8080/health"
curl "localhost:8080/hash?senha=segredo123&iteracoes=100000"
curl "localhost:8080/verificar?senha=segredo123&salt=<salt>&hash=<hash>&iteracoes=100000"
```

O salt é sorteado a cada pedido, por isso a mesma senha gera hashes diferentes. Para conferir, o `/verificar` usa o salt guardado junto com o hash.

## 3. Variáveis de ambiente

| variável | padrão | o que faz |
|---|---|---|
| `PORT` | `8080` | porta |
| `THREADS` | número de processadores | threads de trabalho (pedidos calculados ao mesmo tempo) |
| `MONITOR_PORT` | `8081` | porta do `/metrics` |

## 4. Pastas

| pasta | conteúdo |
|---|---|
| `app/` | o servidor (`app/cpubound/App.java`) |
| `load/` | gerador de carga em laço aberto (`load/Carga.java`), explicado em `load/README.md` |
| `deploy/` | instalação na VM, passo a passo em `deploy/README.md` e a unidade systemd |

Na raiz, `up.sh` e `down.sh` sobem e derrubam a aplicação dentro da VM (`sudo ~/cpu-bound/up.sh`).
| `tools/` | calibração no Docker (`calibrar_local.sh`) e na VM (`calibrar_vm.sh`) |
| `experiments/` | scripts que rodam no hospedeiro: prova local com Docker (`perfil_local.sh`) e experimento na VM (`vm_*.sh`) |
| `analysis/` | tabelas e gráficos a partir dos resultados (`analisar.py`) |
| `results/` | dados brutos, tabelas e gráficos: `local/` (prova com Docker) e `vm/` (experimento na VM) |
| `docs/` | calibração e prints do ensaio de deploy |

### Experimento

Prova local, antes da VM (cerca de 25 min):

```
experiments/perfil_local.sh
python3 analysis/analisar.py results/local
```

Na VM, com a aplicação instalada como serviço (`deploy/README.md`). Cada script desliga a VM, ajusta vCPUs e RAM, liga e roda as duas taxas uma vez (cerca de 3,5 min cada; `REPETICOES=3` para repetir):

| script | vCPUs | RAM | resultado |
|---|---|---|---|
| `experiments/vm_1cpu_1gb.sh` | 1 | 1 GB | `results/vm/V1` |
| `experiments/vm_2cpu_1gb.sh` | 2 | 1 GB | `results/vm/V2` |
| `experiments/vm_1cpu_2gb.sh` | 1 | 2 GB | `results/vm/V3` |
| `experiments/vm_2cpu_2gb.sh` | 2 | 2 GB | `results/vm/V4` |

`experiments/vm_todos_os_cenarios.sh` roda os quatro. Depois, `python3 analysis/analisar.py results/vm`.

## 5. Carga e monitoramento

O gerador `load/Carga.java` roda fora da aplicação e manda pedidos a uma taxa constante, sem esperar as respostas (laço aberto). Quando a taxa passa da capacidade, os pedidos se acumulam na fila e o tempo de resposta cresce. Não precisa compilar:

```
java load/Carga.java "url=http://localhost:8080/hash?senha=x&iteracoes=100000" taxa=20 duracao=60
```

Ele mede vazão, tempo de resposta (média, p50, p95, p99) e erros, descartando os primeiros segundos de aquecimento da JVM.

O consumo de CPU e memória é medido em três lugares:

- **de fora**: no Docker, `docker stats`; na VM, `VBoxManage metrics` no hospedeiro. O `CPU/Load` do VirtualBox sai como percentual do hospedeiro inteiro (num hospedeiro de 12 CPUs, 1 vCPU ocupada aparece como cerca de 8,5%); a análise converte para "100% = 1 vCPU";
- **de dentro da VM**, pelo ssh: `vmstat 1` (CPU, memória usada e swap vistos pelo Ubuntu);
- **pela própria aplicação**: `/metrics`, lido a cada segundo dentro da VM (fila, threads ocupadas e memória do processo).

## 6. Limitações

- A senha vai na URL para simplificar os testes de carga. Num sistema real, ela iria no corpo de um POST, sobre HTTPS.
- Não há armazenamento: o serviço calcula e devolve, sem guardar usuários.
