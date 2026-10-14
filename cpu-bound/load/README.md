# load: gerador de carga em laço aberto

Manda pedidos HTTP a uma taxa constante e mede o tempo de resposta e a vazão.
Roda no hospedeiro, nunca dentro da VM, para não disputar CPU com a aplicação.

Um arquivo só, sem dependências. Precisa de Java 17 ou mais novo e não precisa
ser compilado: o `java` compila e executa o arquivo na hora.

## Por que laço aberto

O pedido número *i* sai no instante *i / taxa*, tenha o servidor respondido
ou não os anteriores. Quando a demanda passa da capacidade, os pedidos se
acumulam na fila do servidor e o tempo de resposta cresce, que é o efeito que o
experimento quer medir.

Um gerador em laço fechado (N usuários, cada um esperando a resposta antes de
mandar o próximo pedido) desaceleraria junto com o servidor e esconderia essa
degradação.

## Uso

```bash
java Carga.java "url=http://localhost:8080/hash?senha=x&iteracoes=100000" taxa=20 duracao=60
```

As aspas em volta do `url=...` são obrigatórias, porque o `&` tem significado
especial no terminal.

| Argumento     | Padrão | Significado |
|---------------|--------|-------------|
| `url`         |        | Endereço chamado em todos os pedidos (obrigatório) |
| `taxa`        |        | Pedidos por segundo (obrigatório; aceita decimais) |
| `duracao`     | 60     | Segundos medidos |
| `aquecimento` | 10     | Segundos iniciais enviados na mesma taxa, mas fora das estatísticas |
| `timeout`     | 60     | Segundos até um pedido sem resposta contar como erro |
| `saida`       |        | CSV com uma linha por pedido |
| `resumo`      |        | CSV ao qual se acrescenta uma linha com as estatísticas do teste |

## Modo contínuo

Para simular um site que recebe usuários o tempo todo, sem um teste com começo e fim:

```bash
java Carga.java "url=http://localhost:8080/hash?senha=x&iteracoes=100000" taxa=20 modo=continuo
```

Ele envia sem prazo, até Ctrl+C, e mostra uma linha a cada 5 segundos (`intervalo=S` muda isso). Não grava arquivos.

```
hora       enviados/s  respostas/s    p50 ms    p95 ms   erros    fila
11:49:23         60.2         46.6     613.3    1074.2       0      68
11:49:28         59.8         48.2    1614.1    2054.3       0     126
11:49:33         60.0         47.0    2659.9    3059.3       0     191
```

(Exemplo com o servidor num container de 1 núcleo, que aguenta cerca de 46 pedidos/s.)

- **respostas/s**: respostas que chegaram no intervalo.
- **p50 e p95**: tempo de resposta das respostas que chegaram no intervalo.
- **fila**: pedidos enviados ainda sem resposta. Parado perto de zero, o servidor dá conta. Crescendo a cada linha, a demanda passou da capacidade.

Ao parar, ele mostra o total. Os pedidos que ficaram na fila continuam sendo processados pelo servidor por alguns segundos, então espere antes de iniciar outro teste.

## O que ele mostra

```
Taxa enviada:        40.0 pedidos/s
Vazao obtida:        37.7 respostas/s
Pedidos medidos:     800 (800 ok, 0 com erro)
Tempo de resposta:   media 1010.1 ms | p50 1093.8 | p95 1506.8 | p99 1539.6 | max 1567.9
Sem resposta ao fim: 60 pedidos
Atraso max. do gerador: 0.4 ms
```

(Exemplo de um teste num notebook, só para ilustrar o formato.)

- **Taxa enviada**: a demanda, ou seja, quantos pedidos por segundo foram mandados.
- **Vazão obtida**: respostas bem-sucedidas que chegaram durante a janela
  medida, por segundo. Abaixo da capacidade, é igual à taxa enviada. Acima,
  fica parada na capacidade do servidor.
- **Tempo de resposta**: do envio até a resposta, só dos pedidos medidos que
  deram certo. p95 é o valor abaixo do qual ficam 95% dos tempos.
- **Sem resposta ao fim**: pedidos enviados que ainda esperavam resposta quando
  a janela terminou. Perto de zero, o servidor dava conta da demanda. Grande,
  havia fila crescendo.
- **Atraso máximo do gerador**: o quanto algum envio saiu depois do instante
  previsto. Se passar de 10 ms, o gerador avisa: o hospedeiro pode estar
  sobrecarregado e a taxa pode não ter sido mantida.

O gerador só termina depois de receber todas as respostas, ou de elas
estourarem o `timeout`. Assim, a fila do servidor já está vazia quando o
próximo teste começa. Se houver erros de timeout, espere alguns segundos antes
do próximo teste, porque o servidor ainda pode estar processando pedidos
abandonados.

## Arquivos gerados

`saida` (um pedido por linha):

```
numero,envio_ms,latencia_ms,status,fase,erro
0,0.002,103.744,200,aquecimento,
1,100.124,53.458,200,aquecimento,
```

`envio_ms` conta a partir do início do teste. `status` é -1 quando não houve
resposta, e então a coluna `erro` diz o motivo (por exemplo `ConnectException`
ou `HttpTimeoutException`).

`resumo` (um teste por linha, para os gráficos):

```
data_hora,url,aquecimento_s,duracao_s,taxa,enviados,ok,erros,vazao,media_ms,p50_ms,p95_ms,p99_ms,max_ms,sem_resposta_no_fim,atraso_max_ms
```
