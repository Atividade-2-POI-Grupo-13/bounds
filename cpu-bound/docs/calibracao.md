# Calibração

O parâmetro `iteracoes` controla quanto processador cada pedido gasta, e o custo é proporcional a ele. Antes de qualquer medição, ajustar o valor na própria máquina onde a aplicação vai rodar:

1. Fazer uns 30 pedidos para aquecer a JVM. Os primeiros são mais lentos porque o código ainda não foi otimizado.
2. Fazer vários pedidos e ler `tempo_ms`. Usar a mediana, não um pedido só.
3. Ajustar por regra de três e repetir até chegar ao tempo desejado.

A capacidade esperada é aproximadamente `processadores / tempo por pedido`.

Todos os números abaixo são de medições reais. Valem só para a máquina em que foram feitos.

## Notebook (Intel i7-1255U, 12 CPUs lógicas, Java 21)

O i7-1255U é híbrido: 2 núcleos de desempenho (P-cores, CPUs 0 a 3 com hyperthreading) e 8 de eficiência (E-cores, CPUs 4 a 11). O mesmo pedido leva tempos diferentes conforme o núcleo, então os testes fixam os núcleos com `taskset` ou `--cpuset-cpus`.

Aquecimento, pedidos isolados com 100 mil iterações, sem fixar núcleo:

| pedido | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| `tempo_ms` | 109,4 | 24,6 | 32,7 | 18,6 | 19,1 |

Depois de aquecida, 100 mil iterações levaram cerca de 19 ms e 200 mil, entre 34,2 e 40,7 ms (5 pedidos, média 36,7 ms). O custo dobra com o dobro de iterações.

Num E-core (`taskset -c 4,5`), 100 mil iterações levaram cerca de 20 a 21 ms.

## VM de ensaio (VirtualBox 7.0 no mesmo notebook, 1 vCPU, 1 GB)

10 pedidos com 100 mil iterações, feitos do hospedeiro:

| 54,0 | 54,2 | 54,8 | 55,0 | 55,9 | 56,7 | 56,8 | 62,6 | 64,3 | 100,9 |
|---|---|---|---|---|---|---|---|---|---|

Mediana de cerca de 56 ms, cerca de 3 vezes o tempo no notebook direto. Para 50 ms nessa VM: cerca de 90 mil iterações.

## Saturação

Gerador `load/Carga.java`, taxa acima da capacidade, 100 mil iterações.

| onde | recursos | vazão máxima (respostas/s) |
|---|---|---|
| Notebook, `taskset -c 4,5` | 2 threads em 2 E-cores | 97,8 |
| Docker, `--cpus` | 1 CPU | 45,3 |
| Docker, `--cpus` | 2 CPUs | 62,7 |
| Docker, `--cpuset-cpus=4` | 1 E-core | 41,9 |
| Docker, `--cpuset-cpus=6,7` | 2 E-cores | 68,2 |

Com `--cpus`, o Docker limita o tempo de CPU, mas não escolhe os núcleos; as threads caem em P-cores e E-cores misturados. Com `--cpuset-cpus`, a comparação é entre núcleos iguais. Mesmo assim, 2 E-cores renderam 1,63 vez 1 E-core no Docker, e não 2. A causa não foi investigada.
