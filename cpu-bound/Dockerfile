# Imagem da cpu-bound. Mesmo Java da VM (17). Compila dentro da imagem, entao nao precisa do .jar pronto.
#   docker build -t app-cpu .
#   docker run --rm -p 8080:8080 --cpuset-cpus=4 app-cpu
FROM eclipse-temurin:17-jdk AS build
WORKDIR /src
COPY app/ app/
RUN javac --release 17 -d out app/cpubound/App.java \
 && jar --create --file app-cpu.jar --main-class cpubound.App -C out .

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/app-cpu.jar .
ENV PORT=8080
EXPOSE 8080
CMD ["java", "-Xms128m", "-Xmx128m", "-jar", "app-cpu.jar"]
