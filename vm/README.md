# VDI do grupo: as 3 aplicações numa VM só

O VDI final traz `cpu-bound`, `memory-bound` e `io-bound` em `/home/osboxes`, cada uma com `up.sh` e `down.sh`. **Nenhuma sobe no boot.** Do hospedeiro, `./rodar_experimento.sh` escolhe o experimento, reconfigura a VM e sobe só a aplicação certa.

Ordem: preparar o VDI (seções 1 a 4), compactar e exportar (seção 5), e só então rodar experimentos (seção 6) numa **cópia** do VDI.

## 1. Criar a VM (no hospedeiro)

```
cp /local/uasc/images/ubuntu_serve_2204_poi.vdi /tmp/
VBoxManage createvm --name vm-poi-exp --ostype Ubuntu_64 --basefolder /tmp --register
VBoxManage modifyvm vm-poi-exp --cpus 1 --memory 1024 --nic1 nat --ioapic on
VBoxManage storagectl vm-poi-exp --name SATA --add sata --controller IntelAhci
VBoxManage storageattach vm-poi-exp --storagectl SATA --port 0 --device 0 --type hdd --medium /tmp/ubuntu_serve_2204_poi.vdi
vm/configurar_vm.sh
```

`configurar_vm.sh` cria as portas abaixo e desliga o cache de I/O do hospedeiro (a io-bound precisa). O `rodar_experimento.sh` roda esse script sozinho na primeira vez.

| nome | hospedeiro | VM | uso |
|---|---|---|---|
| ssh | 2222 | 22 | automação |
| nginx | 8088 | 80 | teste de rede |
| app | 8080 | 8080 | cpu-bound |
| rotas | 8000 | 8000 | memory-bound |
| monitor | 8001 | 8001 | memory-bound, monitor |
| io-buffer / io-produtor / io-consumidor | 18080 / 18081 / 18082 | 8080 / 8081 / 8082 | io-bound |

Dentro da VM as portas da cpu-bound e da io-bound se repetem (8080, 8081). Não tem problema, porque só uma roda por vez.

## 2. Pacotes (na VM, uma vez, com internet)

```
sudo systemctl disable --now unattended-upgrades
sudo apt update
sudo apt install -y openjdk-21-jre-headless python3-venv python3-matplotlib sysstat procps iproute2 curl openssh-server
sudo apt clean
```

O Java 21 serve para a cpu-bound (feita para 17) e para a io-bound (virtual threads).

## 3. Levar os projetos

No hospedeiro: `vm/empacotar.sh` e `cd vm && python3 -m http.server 8099 --bind 127.0.0.1`.

Na VM:

```
cd ~ && curl -fsO http://10.0.2.2:8099/bounds.tar.gz && tar xzf bounds.tar.gz && rm bounds.tar.gz
cd ~/cpu-bound && ./deploy/install.sh && cd ~
cd ~/io-bound && ./deploy/install.sh && cd ~
cd ~/memory-bound && ./deploy/install.sh && cd ~
```

Cada `install.sh` instala o que faltar com apt, compila a aplicação se o `.jar` não existir, instala o serviço fora do boot e testa subindo e derrubando a aplicação. O da memory-bound instala os serviços `rotas` e `rotas-monitor` e é ele que "mexe na VM" pela memory-bound: o serviço `rotas` roda com `MemoryMax=80%` e `MemorySwapMax=1G`, porque a imagem tem 12 GiB de swap e, sem esse limite, a VM trava em vez de matar o processo. O swap da VM não muda.

## 4. Conferir cada aplicação e deixar tudo parado

```
sudo ~/cpu-bound/up.sh && sudo ~/cpu-bound/down.sh
sudo ~/memory-bound/up.sh && sudo ~/memory-bound/down.sh
sudo ~/io-bound/up.sh && sudo ~/io-bound/down.sh
systemctl is-enabled app-cpu rotas rotas-monitor io-bound@buffer   # todos "disabled"
```

## 5. Limpar e exportar

Na VM:

```
rm -rf ~/io-bound/data /tmp/coleta ~/.ssh/authorized_keys
sudo journalctl --vacuum-time=1s
history -c && rm -f ~/.bash_history
sudo poweroff
```

No hospedeiro, com a VM desligada:

```
cp /tmp/ubuntu_serve_2204_poi.vdi ~/bounds.vdi
```

Não zere o espaço livre (`dd if=/dev/zero`) para compactar: o disco virtual do professor tem 500 GB, e o VDI cresceria até esse tamanho no hospedeiro. A instalação acrescenta menos de 1 GB ao VDI original.

Este `bounds.vdi` é o entregável. Não ligue a VM com ele de novo.

## 6. Rodar os experimentos (numa cópia)

Cada escrita na VM aumenta o VDI. Para o entregável não crescer, os experimentos rodam numa cópia descartável:

```
cp ~/bounds.vdi /tmp/exp.vdi
VBoxManage internalcommands sethduuid /tmp/exp.vdi
```

Crie a `vm-poi-exp` com `/tmp/exp.vdi` (seção 1) e siga [COMANDOS.md](../COMANDOS.md).
