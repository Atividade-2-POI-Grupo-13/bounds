# Deploy na VM

Roteiro do professor aplicado à aplicação CPU-bound. Os comandos marcados "no hospedeiro" rodam na máquina física. O resto roda dentro da VM.

Ensaiado num notebook com VirtualBox 7.0. No LCC, refazer os mesmos passos e tirar os prints de cada etapa.

## No LCC: roteiro do dia

O VDI já vem com os projetos instalados (passos 1 a 6 abaixo, feitos uma vez em casa). Os comandos com `$` rodam **no terminal do computador do LCC**, dentro da pasta `cpu-bound` (do `git clone` ou do pendrive). Só os marcados "na VM" rodam dentro dela.

1. Copiar o VDI para `/tmp`. Se o VirtualBox recusar o disco por já conhecer outro com o mesmo identificador (UUID): `VBoxManage internalcommands sethduuid /tmp/<arquivo>.vdi`.
2. Criar a VM `vm-poi-exp` com esse disco, 1 CPU e 1024 MB (passo 1). Com outro nome, rode os scripts com `VM=nome-da-vm`.
3. Criar as regras de porta: app 8080 → 8080, ssh 2222 → 22, nginx 8088 → 80 (passo 2).
4. Ligar a VM e, na VM: `sudo ~/cpu-bound/up.sh`. No hospedeiro: `curl localhost:8080/health` deve mostrar `"processadores":1`.
5. Copiar a chave ssh do computador do LCC para a VM (passo 7):

   ```
   ssh-keygen -t ed25519                  # só se a conta do LCC ainda não tiver chave
   ssh-copy-id -p 2222 osboxes@localhost  # pede a senha osboxes.org uma vez
   ```

6. Calibrar (menos de 1 minuto) e copiar o valor sugerido para `ITERACOES` em `experiments/comum.sh`:

   ```
   tools/calibrar_vm.sh
   ```

7. Rodar os quatro cenários (cerca de 3 minutos cada; o script desliga, reconfigura e religa a VM sozinho):

   ```
   experiments/vm_todos_os_cenarios.sh
   ```

   Para acompanhar ao vivo, em outro terminal: `ssh -p 2222 osboxes@localhost` e `curl localhost:8081/metrics` ou `top`.
8. Gerar tabelas e gráficos: `python3 analysis/analisar.py results/vm`.
9. Limpar a VM (passo 8), desligar (passo 9) e copiar o `.vdi` para o Drive.

## 1. Criar a VM

No hospedeiro:

```
cp /local/uasc/images/ubuntu_serve_2204_poi.vdi /tmp/
```

VirtualBox > Novo: tipo Linux, Ubuntu (64-bit), 1 CPU, 1024 MB, disco existente `/tmp/ubuntu_serve_2204_poi.vdi`.

Cuidados no assistente do VirtualBox 7:

- Escolher o tipo **depois** de digitar o nome. Ao mudar o nome, o assistente tenta adivinhar o sistema e troca o tipo.
- Ao voltar telas, o assistente pode trocar o disco para "criar um disco novo". Conferir no resumo que o disco é o `.vdi` do professor.

Ligar a VM e entrar com `osboxes` / `osboxes.org`. Conferir os recursos:

```
nproc
free -h
```

## 2. Redirecionamento de portas

Settings > Network > Adapter 1 (NAT) > Advanced > Port Forwarding:

| nome | protocolo | hospedeiro | VM |
|---|---|---|---|
| app | TCP | 8080 | 8080 |
| ssh | TCP | 2222 | 22 (opcional) |
| nginx | TCP | 8088 | 80 (teste de rede do roteiro) |

O `/metrics` da aplicação (porta 8081 da VM) é lido de dentro da VM pelo ssh e não precisa de regra. Para olhar do hospedeiro, acrescente `metrics`, TCP, 8082 → 8081.

A imagem já vem com o servidor SSH ativo.

## 3. Instalar o Java

Na VM:

```
sudo apt update
sudo apt install -y openjdk-17-jre-headless
java -version
```

Na primeira vez que a VM ganha internet, o `unattended-upgrades` (atualização automática) segura o apt por vários minutos ("Waiting for cache lock"). Esperar ou parar com:

```
sudo systemctl stop unattended-upgrades
sudo dpkg --configure -a
```

Antes de medir desempenho, desligar de vez: `sudo systemctl disable --now unattended-upgrades`. Senão ele disputa a CPU com a aplicação.

## 4. Levar o .jar para a VM

No hospedeiro, compilar e servir só o `.jar`. Na rede NAT do VirtualBox, a VM enxerga o hospedeiro no endereço `10.0.2.2`.

```
./build.sh
mkdir -p ~/envio-vm && cp app-cpu.jar ~/envio-vm/
cd ~/envio-vm && python3 -m http.server 8000 --bind 127.0.0.1
```

Na VM:

```
curl -O http://10.0.2.2:8000/app-cpu.jar
ls -l app-cpu.jar
```

Encerrar o servidor do hospedeiro com Ctrl+C.

O teclado da VM está no padrão americano. Num teclado ABNT2, os dois-pontos saem com Shift + Ç.

## 5. Executar e testar

Na VM:

```
java -Xms128m -Xmx128m -jar app-cpu.jar
```

No hospedeiro:

```
curl "http://localhost:8080/health"
```

A resposta deve trazer `"processadores":1`. É a prova de que quem respondeu foi a VM.

## 6. Instalar na pasta pessoal da VM

O VDI do grupo guarda os três projetos na pasta pessoal (`/home/osboxes`), cada um com o seu `up.sh` e o seu `down.sh` na raiz. Nenhuma aplicação sobe sozinha no boot. Durante as medições de uma, as outras ficam paradas.

```
/home/osboxes/
├── cpu-bound/      este projeto, com app-cpu.jar, up.sh e down.sh
├── memory-bound/   projeto do Wendell, com o seu up.sh e down.sh
└── io-bound/       projeto IO-bound, com o seu up.sh e down.sh
```

No hospedeiro, compilar, empacotar e servir:

```
./build.sh
tar czf ~/cpu-bound.tar.gz --exclude=results -C .. cpu-bound
cd ~ && python3 -m http.server 8000 --bind 127.0.0.1
```

Na VM:

```
cd ~ && curl -fsO http://10.0.2.2:8000/cpu-bound.tar.gz && tar xzf cpu-bound.tar.gz
cd ~/cpu-bound && ./deploy/install.sh
```

O `install.sh` instala o Java se faltar, compila o `.jar` se não existir, instala o serviço `app-cpu` fora do boot e testa subindo e derrubando a aplicação (deve mostrar `cpu-bound no ar`). Para parar: `sudo ~/cpu-bound/down.sh`.

Se a VM tiver a instalação antiga (`/opt/app-cpu`, serviço habilitado no boot), antes: `sudo systemctl disable --now app-cpu && sudo rm -rf /opt/app-cpu`.

## 7. Permitir a automação (para os scripts de experimento)

Os scripts `experiments/vm_*.sh` religam a VM a cada cenário e, pelo ssh, rodam o `down.sh` de todos os projetos e o `up.sh` da CPU-bound. Para entrar sem digitar senha, copiar a chave ssh do hospedeiro para a VM, uma vez por computador (pede a senha `osboxes.org`):

```
ssh-copy-id -p 2222 osboxes@localhost
```

A senha do `sudo` os scripts passam sozinhos, como no repositório do Wendell (`SENHA_VM` em `experiments/comum.sh`, padrão `osboxes.org`). A VM não precisa de nenhuma configuração extra.

Teste, no hospedeiro: `ssh -p 2222 osboxes@localhost true` deve voltar sem pedir senha.

## 8. Limpar antes de entregar o VDI

Depois dos experimentos e antes de desligar a VM pela última vez, tirar a chave usada na automação e os arquivos da instalação. Na VM:

```
sudo ~/cpu-bound/down.sh
rm -f ~/.ssh/authorized_keys ~/cpu-bound.tar.gz
rm -rf /tmp/coleta
history -c && rm -f ~/.bash_history
```

Isso tira a chave ssh do hospedeiro, o pacote da instalação, a coleta dos experimentos e o histórico de comandos. O projeto em `~/cpu-bound` e o serviço `app-cpu` continuam. Os logs do sistema (logins, por exemplo) ficam, como em qualquer servidor.

## 9. Encerrar

```
sudo poweroff
```

Só copiar o `.vdi` depois de a VM desligar. Copiar o arquivo com a VM ligada pode gerar um disco corrompido.
