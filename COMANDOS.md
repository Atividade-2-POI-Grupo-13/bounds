# Comandos dos experimentos

## Antes: criar a VM (uma vez por computador)

1. Copiar o VDI do grupo para `/tmp`:

   ```
   cp ~/bounds.vdi /tmp/
   ```

2. No VirtualBox, criar a VM: nome `vm-poi-exp`, Linux, Ubuntu 22.04 LTS (64-bit), 1 CPU, 1024 MB e o disco existente `/tmp/bounds.vdi`. Se o assistente não mostrar a opção de disco existente, crie sem disco e adicione o VDI em Configurações → Armazenamento → Controlador SATA.

Se o VirtualBox recusar o disco por UUID repetido (o VDI já foi usado nesse computador):

```
VBoxManage internalcommands sethduuid /tmp/bounds.vdi
```

Não precisa ligar a VM nem configurar portas: na primeira execução, o `rodar_experimento.sh` configura as portas, desliga o cache de disco, liga a VM, copia a chave ssh e instala o k6.

Requisitos no hospedeiro: VirtualBox, Java 17 ou mais novo (gerador de carga da CPU-bound) e Python 3.

Antes de reiniciar o computador, guarde o VDI fora do `/tmp`: o Ubuntu apaga o `/tmp` no boot.

## Rodar

Na raiz do repositório.

## CPU-bound

```
./rodar_experimento.sh cpu calibrar
./rodar_experimento.sh cpu V1
./rodar_experimento.sh cpu V2
./rodar_experimento.sh cpu V3
./rodar_experimento.sh cpu V4
./rodar_experimento.sh cpu analisar
```

Depois do `calibrar`, copiar o valor sugerido para `ITERACOES` em `cpu-bound/experiments/comum.sh`.

## Memory-bound

```
./rodar_experimento.sh memory calibrar
./rodar_experimento.sh memory C1
./rodar_experimento.sh memory C2
./rodar_experimento.sh memory C3
./rodar_experimento.sh memory C4
./rodar_experimento.sh memory analisar
```

## IO-bound

```
./rodar_experimento.sh io calibrar
./rodar_experimento.sh io V1
./rodar_experimento.sh io V2
./rodar_experimento.sh io V3
./rodar_experimento.sh io V4
./rodar_experimento.sh io analisar
```

## Atalhos

```
./rodar_experimento.sh cpu todos        # os 4 cenários em sequência (igual para memory e io)
./rodar_experimento.sh memory demo      # demonstração de ~3 min
./rodar_experimento.sh subir io         # só deixa a aplicação no ar
./rodar_experimento.sh parar            # derruba as três
```
