# Deploy na VM

Passo a passo do roteiro do professor, para a máquina do LCC3 (Linux com VirtualBox). Os comandos `VBoxManage` e `scp` rodam no hospedeiro. O `install.sh` roda dentro da VM.

## 1. Criar a VM

Copiar a imagem para `/tmp` (o `/tmp` pode ser apagado quando a máquina reinicia):

```
cp /local/uasc/images/ubuntu_serve_2204_poi.vdi /tmp/
```

Pela interface do VirtualBox: nome `vm-rotas`, pasta `/tmp`, tipo Linux, Ubuntu (64-bit), 1 CPU, 1024 MB, usar o disco existente `/tmp/ubuntu_serve_2204_poi.vdi`.

Os comandos equivalentes:

```
VBoxManage createvm --name vm-rotas --ostype Ubuntu_64 --basefolder /tmp --register
VBoxManage modifyvm vm-rotas --cpus 1 --memory 1024 --nic1 nat
VBoxManage storagectl vm-rotas --name SATA --add sata --controller IntelAhci
VBoxManage storageattach vm-rotas --storagectl SATA --port 0 --device 0 --type hdd \
  --medium /tmp/ubuntu_serve_2204_poi.vdi
```

Se o VirtualBox reclamar que o UUID do disco já existe (imagem usada antes nessa máquina), gerar um UUID novo:

```
VBoxManage internalcommands sethduuid /tmp/ubuntu_serve_2204_poi.vdi
```

## 2. Redirecionar portas (NAT)

Hospedeiro 8080 para a aplicação (8000 na VM) e hospedeiro 2222 para o ssh (22 na VM):

```
VBoxManage modifyvm vm-rotas --natpf1 "app,tcp,,8080,,8000"
VBoxManage modifyvm vm-rotas --natpf1 "ssh,tcp,,2222,,22"
VBoxManage startvm vm-rotas --type headless
```

Login: `osboxes`, senha `osboxes.org`.

## 3. Copiar o projeto para a VM

No hospedeiro, a partir de um clone do repositório (um clone novo não tem `.venv`):

```
scp -P 2222 -r memory-bound-rotas osboxes@localhost:~/
```

Se a VM tiver internet, também dá para clonar direto dentro dela com `git clone`.

## 4. Instalar

```
ssh -p 2222 osboxes@localhost
cd memory-bound-rotas
./deploy/install.sh
```

O script:

- tenta instalar `python3-venv` e `sysstat` com apt;
- cria a `.venv` e instala as dependências a partir de `deploy/wheels/`, sem precisar de internet;
- sem `python3-venv` e sem internet, descompacta as wheels em `.pacotes/` e usa essa pasta no `PYTHONPATH`;
- instala e liga o serviço `rotas` no systemd;
- espera `/health` responder;
- mostra a memória e o swap da VM.

Testado numa Ubuntu 22.04 x86_64 limpa (container com systemd), com internet e sem internet.

## 5. Verificar

Dentro da VM:

```
systemctl status rotas
curl localhost:8000/health
```

No hospedeiro:

```
curl localhost:8080/health
```

Resposta esperada: `{"status":"ok","nodes":214373,"edges":565101}`.

## 6. Registrar para o relatório

- Memória e swap da VM em cada cenário: `free -h` e `swapon --show`. O swap fica igual em todos os cenários.
- Reinícios do serviço (processo morto por falta de memória): `systemctl show rotas -p NRestarts`.
- Mensagens do OOM killer: `journalctl -k | grep -i -E "oom|killed process"`.
- Log da aplicação: `journalctl -u rotas -f`.

## 7. Configuração do serviço

As variáveis ficam em `deploy/rotas.service`. Depois de mudar, rodar `./deploy/install.sh` de novo.

| variável | valor | o que faz |
|---|---|---|
| `MAP_FILE` | `data/paraiba.map.gz` | mapa carregado |
| `PORT` | `8000` | porta da aplicação |
| `MAX_CONCURRENT` | `0` | limite de cálculos ao mesmo tempo (0 = sem limite) |
| `MAX_ALCANCE_MIN` | `60` | minutos máximos do `/alcance` |
| `CAPACIDADE_VIA` | `2` | veículos por aresta antes de o trânsito pesar |
| `ARVORE_VALIDADE_S` | `60` | idade máxima da árvore de uma viagem antes de refazer |
| `VIAGEM_EXPIRA_S` | `300` | viagem sem uso por esse tempo é encerrada |

## 8. Ensaio no Mac com UTM

A VDI é x86_64, então no Mac com Apple Silicon ela roda emulada (lenta). Serve para ensaiar estes passos. Os números de desempenho vêm só do LCC3.

1. Converter o disco: `qemu-img convert -f vdi -O qcow2 ubuntu_serve_2204_poi.vdi ubuntu.qcow2`.
2. No UTM: nova VM em modo "Emular", arquitetura x86_64, 1 CPU, 1024 MB, usando `ubuntu.qcow2`.
3. Rede em modo "Emulated VLAN", com redirecionamento 8080 para 8000 e 2222 para 22.
4. Seguir as seções 3 a 5.

## 9. Sem internet na VM

As wheels de `deploy/wheels/` já estão no repositório. Para atualizar (numa máquina com internet):

```
PIP="uvx --python 3.10 pip" deploy/baixar_wheels.sh
```
