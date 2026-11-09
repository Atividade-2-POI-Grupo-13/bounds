# Relatório da Atividade de POI: Conteinerização com Docker

Grupo 13-L

- Bruno Grangeiro Bonifácio
- Kayky Fidelis Serafim
- Wendell Tomé Marinho Oliveira

## Resumo

Nesta atividade, as três aplicações do grupo (CPU-bound, memory-bound e IO-bound) passaram a rodar em containers Docker.
Criamos uma imagem por aplicação, publicamos as três no Docker Hub e fizemos o deploy na VM `vm-grupo-13-L` com um único `docker-compose.yml`.
O balanceador `poi-atividades` continua com os mesmos listeners da atividade anterior, porque os containers publicam as mesmas portas que os serviços do systemd usavam.

O caminho de uma requisição externa é este:

1. O cliente acessa o IP `150.165.85.77` do balanceador, em uma porta de 1301 a 1304.
2. O listener daquela porta encaminha a conexão para a VM `10.5.11.200`, na mesma porta.
3. O Docker publica essa porta da VM e entrega a conexão ao container da aplicação.

| Porta | Container | Imagem | Porta interna |
|---|---|---|---|
| 1301 | `cpu-bound` | `wendelltmo/poi-cpu-bound:1.0` | 8080 |
| 1302 | `memory-bound` | `wendelltmo/poi-memory-bound:1.0` | 8000 |
| 1303 | `io-produtor` | `wendelltmo/poi-io-bound:1.0` | 8081 |
| 1304 | `io-consumidor` | `wendelltmo/poi-io-bound:1.0` | 8082 |
| sem porta externa | `io-buffer` | `wendelltmo/poi-io-bound:1.0` | 8080 |

São três imagens e cinco containers. A IO-bound tem três processos (buffer, produtor e consumidor), então uma única imagem carrega os três jars e cada container escolhe o seu pelo campo `command` do compose.
O buffer só recebe tráfego do produtor e do consumidor, pela rede interna do compose, e por isso não tem porta publicada.

## 1. Preparação dos repositórios

As três aplicações vivem no mesmo repositório da atividade anterior, `Atividade-2-POI-Grupo-13/bounds`, cada uma em uma pasta (`cpu-bound`, `memory-bound` e `io-bound`).
Criamos a branch `containerizacao-docker` a partir da `main`, e todas as alterações desta atividade estão nela.

```
git checkout -b containerizacao-docker
```

Figura 1: Criação da branch `containerizacao-docker`.

![Figura 1](img/fig01-branch.png)

## 2. Dockerfile de cada aplicação

### 2.1 CPU-bound

A `cpu-bound` já tinha um Dockerfile, usado nos testes locais da atividade anterior. Aproveitamos o arquivo e o transformamos em build de dois estágios (`cpu-bound/Dockerfile`):

- O primeiro estágio usa `eclipse-temurin:17-jdk`, compila o `App.java` e gera o `app-cpu.jar`.
- O segundo estágio usa `eclipse-temurin:17-jre` e copia só o jar. A imagem final tem 449 MB, contra 709 MB da versão de um estágio, porque o compilador fica no primeiro estágio.
- A JVM sobe com `-Xms128m -Xmx128m`, as mesmas opções da unidade systemd, e escuta na porta 8080 definida por `PORT`.

### 2.2 Memory-bound

O `memory-bound/Dockerfile` também já existia e foi mantido sem mudança:

- Base `python:3.10-slim`, a mesma versão de Python da VM.
- O `requirements.txt` é copiado e instalado antes do código, para o cache de camadas reaproveitar a instalação quando só o código muda.
- A imagem leva o mapa `data/paraiba.map.gz` (5,4 MB) e escuta na porta 8000.

### 2.3 IO-bound

A `io-bound` ganhou um Dockerfile novo (`io-bound/Dockerfile`), em dois estágios:

- O primeiro estágio usa `maven:3.9-eclipse-temurin-21` e roda `mvn package` na raiz do projeto, que compila os três módulos.
- O segundo estágio usa `eclipse-temurin:21-jre` e copia os jars `buffer`, `produtor` e `consumidor`.
- As opções da JVM da unidade `io-bound@.service` (`-Xmx64m -XX:+UseSerialGC` e as demais) foram para a variável `JAVA_TOOL_OPTIONS`. Os três Java precisam caber juntos na VM de 2 GB.
- O `io-bound/.dockerignore` deixa de fora `target/`, `data/` e `resultados/`, para o contexto de build ficar pequeno.

Figura 2: Dockerfiles das três aplicações.

![Figura 2](img/fig02-dockerfiles.png)

## 3. Build das imagens

Antes de publicar, construímos as três imagens no computador do grupo para testá-las.

```
docker build -t local/poi-cpu-bound:1.0 cpu-bound
docker build -t local/poi-memory-bound:1.0 memory-bound
docker build -t local/poi-io-bound:1.0 io-bound
docker images
```

Figura 3: Build das três imagens e listagem com `docker images`.

![Figura 3](img/fig03-build.png)

## 4. Teste local com Docker Compose

O `docker-compose.yml` fica na raiz do repositório. Para o teste local, trocamos `wendelltmo` por `local` e subimos a pilha:

```
docker compose -p poitest up -d
docker compose -p poitest ps
```

Em seguida chamamos as quatro portas. Todas responderam:

- `GET localhost:1301/health` devolveu `{"status":"ok","processadores":10,"threads":10}`.
- `GET localhost:1302/health` devolveu `{"status":"ok","nodes":214373,"edges":565101}`.
- `POST localhost:1303/produzir?jobs=5` devolveu `{"pedidos":5,"concluidos":5,"vezesCheio":0,...}`.
- `POST localhost:1304/consumir?jobs=5` devolveu `{"pedidos":5,"concluidos":5,"vezesVazio":0,...}`.
- `GET localhost:1302/rota?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450` devolveu uma rota de cerca de 133,8 km entre Campina Grande e João Pessoa.

O produtor e o consumidor só concluem os 5 jobs porque enxergam o buffer em `http://io-buffer:8080`. As variáveis `PRODUTOR_BUFFER_URL` e `CONSUMIDOR_BUFFER_URL` do compose sobrescrevem o `localhost:8080` do `application.properties`, sem alterar o código.

Figura 4: `docker compose ps` com os cinco containers no ar.

![Figura 4](img/fig04-compose-local.png)

Figura 5: Requisições às quatro portas no teste local.

![Figura 5](img/fig05-curl-local.png)

Ao final, `docker compose -p poitest down` removeu a pilha de teste.

## 5. Publicação no Docker Hub

O Docker Hub guarda as imagens em repositórios no formato `usuario/nome`. Usamos a conta `wendelltmo`, com um repositório público por aplicação.

O computador do grupo tem processador ARM e a VM do LSD usa x86_64. Por isso construímos as imagens publicadas com `--platform linux/amd64`, para que o container rode na VM.

```
docker login
docker buildx build --platform linux/amd64 -t wendelltmo/poi-cpu-bound:1.0 --push cpu-bound
docker buildx build --platform linux/amd64 -t wendelltmo/poi-memory-bound:1.0 --push memory-bound
docker buildx build --platform linux/amd64 -t wendelltmo/poi-io-bound:1.0 --push io-bound
```

Figura 6: Login e push das três imagens.

![Figura 6](img/fig06-push.png)

Figura 7: Os três repositórios no Docker Hub.

![Figura 7](img/fig07-dockerhub.png)

## 6. Acesso à VM e instalação do Docker

Acessamos a VM pelo balanceador, como na atividade anterior:

```
ssh -i ~/.ssh/grupo-13-L -p 1300 ubuntu@150.165.85.77
uname -m
```

O `uname -m` deve mostrar `x86_64`, a arquitetura das imagens publicadas.

Instalamos o Docker Engine pelo repositório apt oficial, seguindo a documentação do Docker para Ubuntu:

```
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
```

Depois de sair e entrar de novo na sessão (para o grupo `docker` valer), testamos:

```
docker run --rm hello-world
docker compose version
```

Figura 8: Docker instalado na VM, com o `hello-world` rodando.

![Figura 8](img/fig08-docker-vm.png)

## 7. Desligar os serviços do systemd

As aplicações da atividade anterior rodam como serviços do systemd nas portas 1301 a 1304. Os containers usam as mesmas portas, então os serviços precisam parar antes.
Também os desabilitamos para que não voltem no boot e disputem a porta com os containers.

```
sudo systemctl disable --now app-cpu rotas rotas-monitor io-bound@buffer io-bound@produtor io-bound@consumidor
sudo ss -ltnp | grep -E ':(1301|1302|1303|1304)\b'
```

O `ss` não deve listar nenhuma das quatro portas.

Figura 9: Serviços parados e portas livres.

![Figura 9](img/fig09-systemd-parado.png)

## 8. Deploy com Docker Compose

Na VM, o repositório do grupo já está clonado na pasta `bounds`. Atualizamos para a branch da atividade e subimos a pilha:

```
cd ~/bounds
git fetch origin
git checkout containerizacao-docker
docker compose up -d
docker compose ps
```

O Compose baixa as três imagens do Docker Hub e cria uma rede própria, onde `io-produtor` e `io-consumidor` resolvem o nome `io-buffer`.
A opção `restart: always` faz o Docker religar qualquer container que caia, o mesmo papel do `Restart=always` das unidades systemd.

Figura 10: `docker compose up -d` baixando as imagens e criando os containers.

![Figura 10](img/fig10-compose-up.png)

Figura 11: `docker compose ps` na VM com os cinco containers `Up` e as portas 1301 a 1304 publicadas.

![Figura 11](img/fig11-compose-ps.png)

## 9. Balanceador de carga

O balanceador `poi-atividades` já tem, da atividade anterior, um listener, um pool, um health monitor e um member para cada porta de 1301 a 1304, todos apontando para `10.5.11.200`.
Os containers publicam as mesmas portas, então nenhum listener precisou mudar.
Conferimos que os members continuam saudáveis:

```
openstack loadbalancer pool list
openstack loadbalancer member list <pool>
```

O health monitor de cada pool faz uma requisição HTTP real. A rota `/health` da cpu-bound e da memory-bound e a rota `/actuator/health` do produtor e do consumidor continuam respondendo 200 nos containers, e por isso os members ficam com `operating_status` `ONLINE`.

Figura 12: Pools e members do balanceador com `operating_status` `ONLINE`.

![Figura 12](img/fig12-lb.png)

## 10. Validação remota

De uma máquina fora da nuvem, chamamos o IP do balanceador:

```
curl http://150.165.85.77:1301/health
curl http://150.165.85.77:1302/health
curl "http://150.165.85.77:1301/hash?senha=teste"
curl "http://150.165.85.77:1302/rota?origem=-7.2307,-35.8817&destino=-7.1195,-34.8450"
curl -X POST "http://150.165.85.77:1303/produzir?jobs=5"
curl -X POST "http://150.165.85.77:1304/consumir?jobs=5"
```

Figura 13: Requisições externas às quatro portas, passando pelo balanceador.

![Figura 13](img/fig13-curl-externo.png)

## 11. Versionamento e pull request

Commitamos os arquivos novos na branch `containerizacao-docker`:

- `docker-compose.yml`
- `io-bound/Dockerfile` e `io-bound/.dockerignore`
- `cpu-bound/Dockerfile` (build em dois estágios)
- `docs/conteinerizacao.md` (este relatório)

Depois abrimos um pull request da branch para a `main`.

```
git push -u origin containerizacao-docker
gh pr create --base main --head containerizacao-docker
```

Figura 14: Pull request aberto no GitHub.

![Figura 14](img/fig14-pr.png)

## 12. Informações de entrega

| Campo | Valor |
|---|---|
| ID da VM | `<openstack server show vm-grupo-13-L -f value -c id>` |
| IP da VM | `10.5.11.200` (privado) e `150.165.85.77` (balanceador) |
| Repositório das aplicações 1, 2 e 3 | `https://github.com/Atividade-2-POI-Grupo-13/bounds/tree/containerizacao-docker` |
| URL da aplicação 1 (cpu-bound) | `http://150.165.85.77:1301/health` |
| URL da aplicação 2 (memory-bound) | `http://150.165.85.77:1302/health` |
| URL da aplicação 3 (io-bound) | `http://150.165.85.77:1303/actuator/health` (produtor) e `http://150.165.85.77:1304/actuator/health` (consumidor) |
| Imagem da aplicação 1 | `https://hub.docker.com/r/wendelltmo/poi-cpu-bound` |
| Imagem da aplicação 2 | `https://hub.docker.com/r/wendelltmo/poi-memory-bound` |
| Imagem da aplicação 3 | `https://hub.docker.com/r/wendelltmo/poi-io-bound` |
| Arquivo do Docker Compose | `https://github.com/Atividade-2-POI-Grupo-13/bounds/blob/containerizacao-docker/docker-compose.yml` |
