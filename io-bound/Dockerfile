# Imagem unica da io-bound. Traz os tres jars (buffer, produtor, consumidor);
# o docker-compose.yml escolhe qual rodar em cada container pelo "command".
#   docker build -t poi-io-bound io-bound
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
COPY buffer/ buffer/
COPY produtor/ produtor/
COPY consumidor/ consumidor/
RUN mvn -q -B package -Dmaven.test.skip=true

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/buffer/target/buffer-0.1.0.jar /src/produtor/target/produtor-0.1.0.jar /src/consumidor/target/consumidor-0.1.0.jar ./
# Mesmas opcoes da JVM da unidade systemd: os tres Java precisam caber juntos na VM.
ENV MALLOC_ARENA_MAX=2 \
    JAVA_TOOL_OPTIONS="-Xmx64m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -XX:MaxMetaspaceSize=80m -XX:ReservedCodeCacheSize=24m -XX:MaxDirectMemorySize=32m -Xss256k"
EXPOSE 8080 8081 8082
CMD ["java", "-jar", "buffer-0.1.0.jar"]
