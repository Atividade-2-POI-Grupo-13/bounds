# Imagem para testar localmente com limites de CPU e memória.
# Mesmo Java da VM (17). Compila dentro da imagem, então não precisa do .jar pronto.
#   docker build -t app-cpu .
#   docker run --rm -p 8080:8080 --cpuset-cpus=4 app-cpu
FROM eclipse-temurin:17-jdk
WORKDIR /app
COPY app/ app/
RUN javac --release 17 -d out app/cpubound/App.java \
 && jar --create --file app-cpu.jar --main-class cpubound.App -C out . \
 && rm -rf out app
ENV PORT=8080
EXPOSE 8080
CMD ["java", "-Xms128m", "-Xmx128m", "-jar", "app-cpu.jar"]
