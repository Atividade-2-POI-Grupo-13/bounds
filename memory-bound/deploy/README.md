# Deploy na VM

Roteiro do professor aplicado à máquina do LCC3. `VBoxManage`, `scp` e os testes marcados "no hospedeiro" rodam na máquina do LCC3. O resto roda dentro da VM.

## 1. Criar a VM

```
cp /local/uasc/images/ubuntu_serve_2204_poi.vdi /tmp/
```

VirtualBox > Novo: nome `vm-rotas`, pasta `/tmp`, tipo Linux, Ubuntu (64-bit), 1 CPU, 1024 MB, disco existente `/tmp/ubuntu_serve_2204_poi.vdi`.

Equivalente em linha de comando:

```
VBoxManage createvm --name vm-rotas --ostype Ubuntu_64 --basefolder /tmp --register
VBoxManage modifyvm vm-rotas --cpus 1 --memory 1024 --nic1 nat
VBoxManage storagectl vm-rotas --name SATA --add sata --controller IntelAhci
VBoxManage storageattach vm-rotas --storagectl SATA --port 0 --device 0 --type hdd \
  --medium /tmp/ubuntu_serve_2204_poi.vdi
```

Erro de UUID repetido (imagem já usada nessa máquina): `VBoxManage internalcommands sethduuid /tmp/ubuntu_serve_2204_poi.vdi`.

Ligar a VM e entrar com `osboxes` / `osboxes.org`.

## 2. Testar a rede com nginx (passos 5 a 8 do roteiro)

Prova de que o redirecionamento de portas funciona antes do deploy da aplicação.

Na VM:

```
sudo apt install nginx
sudo systemctl status nginx
curl localhost:80
```

Sem internet na VM, `sudo python3 -m http.server 80` serve uma página na mesma porta.

No hospedeiro, `curl localhost:80` falha: ainda não há redirecionamento.

Desligar a VM (`sudo poweroff`) e criar as regras em Configurações > Rede > Avançado > Redirecionamento de portas:

| nome | hospedeiro | VM | uso |
|---|---|---|---|
| nginx | 8088 | 80 | teste de rede |
| app | 8080 | 8000 | aplicação |
| monitor | 8081 | 8001 | monitor da VM |
| ssh | 2222 | 22 | cópia do projeto e coleta |

O roteiro usa a porta 80 no hospedeiro. No Linux, um usuário sem root não abre porta abaixo de 1024, por isso o hospedeiro usa 8088.

Equivalente em linha de comando:

```
VBoxManage modifyvm vm-rotas --natpf1 "nginx,tcp,,8088,,80"
VBoxManage modifyvm vm-rotas --natpf1 "app,tcp,,8080,,8000"
VBoxManage modifyvm vm-rotas --natpf1 "monitor,tcp,,8081,,8001"
VBoxManage modifyvm vm-rotas --natpf1 "ssh,tcp,,2222,,22"
VBoxManage startvm vm-rotas --type headless
```

No hospedeiro, com a VM ligada: `curl localhost:8088` devolve a página do nginx.

Depois do teste, desligar o nginx para ele não ocupar memória nos cenários: `sudo systemctl disable --now nginx`.

`experiments/cenario.sh` recria a regra `monitor` a cada troca de cenário.

## 3. Copiar o projeto

De um clone do repositório no hospedeiro:

```
scp -P 2222 -r memory-bound-rotas osboxes@localhost:~/
```

Sem ssh na VM: `deploy/servir_projeto.sh` no hospedeiro serve o projeto na porta 8099 e imprime o comando para o console da VM (baixa de `10.0.2.2`, descompacta e roda o `install.sh`).

## 4. Instalar

```
ssh -p 2222 osboxes@localhost
cd memory-bound-rotas
./deploy/install.sh
```

O `install.sh`:

- tenta instalar com apt o que faltar entre `python3-venv`, `sysstat` e `openssh-server`;
- cria `.venv` e instala as dependências de `deploy/wheels/`, sem internet;
- sem `python3-venv`, descompacta as wheels em `.pacotes/` e usa no `PYTHONPATH`;
- instala e liga os serviços systemd `rotas` (porta 8000, `Restart=always`) e `rotas-monitor` (porta 8001);
- espera `/health`, confere o monitor, mostra `free -h` e `swapon --show` e diz se a VM tem ssh.

## 5. Verificar

Na VM: `systemctl status rotas` e `curl localhost:8000/health`.

No hospedeiro: `curl localhost:8080/health` e `curl localhost:8081`.

Resposta do `/health`: `{"status":"ok","nodes":214373,"edges":565101}`.

## 6. Comandos para o relatório

- Memória e swap: `free -h` e `swapon --show`.
- Reinícios do serviço: `systemctl show rotas -p NRestarts`.
- OOM killer: `journalctl -k | grep -i -E "oom|killed process"`.
- Log da aplicação: `journalctl -u rotas -f`.

## 7. Configuração do serviço

`deploy/rotas.service` usa os padrões do `README.md`, seção 3, com duas mudanças: `MAP_FILE=data/paraiba.map.gz` e `PERMITIR_REINICIO=1`. Depois de editar, rodar `./deploy/install.sh` de novo.

## 8. Ensaio no Mac com UTM

A VDI é x86_64 e roda emulada no Apple Silicon. Serve só para ensaiar os passos.

1. `qemu-img convert -f vdi -O qcow2 ubuntu_serve_2204_poi.vdi ubuntu.qcow2`
2. UTM: modo Emular, x86_64, 1 CPU, 1024 MB, disco `ubuntu.qcow2`.
3. Rede Emulated VLAN com 8080 para 8000 e 2222 para 22.
4. Seguir as seções 3 a 5.

## 9. Atualizar as wheels

Numa máquina com internet: `PIP="uvx --python 3.10 pip" deploy/baixar_wheels.sh`.
