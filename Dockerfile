# Estágio 1: compila os três apps
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY . .
RUN mvn -q -B package -Dmaven.test.skip=true

# Estágio 2: a "máquina" do experimento, com os três apps e as ferramentas de monitoramento
FROM eclipse-temurin:21-jre
RUN apt-get update \
    && apt-get install -y --no-install-recommends sysstat procps iproute2 curl python3-matplotlib \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/buffer/target/buffer-0.1.0.jar \
                  /src/produtor/target/produtor-0.1.0.jar \
                  /src/consumidor/target/consumidor-0.1.0.jar ./
COPY monitorar.sh stress.sh plotar.py docker/entrypoint.sh ./
# Qualquer usuário pode escrever aqui: o container roda com o usuário de quem chamou
RUN chmod 777 /app
CMD ["./entrypoint.sh"]
