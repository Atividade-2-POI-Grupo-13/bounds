# Prova local (Docker)

Ensaio feito antes dos experimentos na VM, com `experiments/perfil_local.sh`, no notebook do grupo (Intel i7-1255U). A aplicação ficou presa a E-cores com `--cpuset-cpus` e o gerador de carga em outros E-cores.

| cenário | núcleos | memória |
|---|---|---|
| L1 | 1 | 256 MB |
| L2 | 2 | 256 MB |
| L3 | 1 | 512 MB |
| L4 | 2 | 512 MB |

Taxas de 10 e 30 pedidos/s, 253 mil iterações (`calibracao.txt`), 10 s de aquecimento, 30 s medidos, 3 repetições.

Rodado com o notebook na tomada e sem a VM ligada. Uma rodada anterior, na bateria, foi descartada: o processador reduziu a frequência no meio do L4.

`tabela.md`, `tabela.csv` e `graficos/` são gerados por `python3 analysis/analisar.py results/local`.
