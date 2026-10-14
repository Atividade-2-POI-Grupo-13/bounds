# Imagem para testar localmente com limites de memória e CPU (etapa 3).
# Mesmo Python da VM (3.10) e Linux, como na VM.
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY tools/calibrate.py tools/
COPY data/paraiba.map.gz data/pontos_paraiba.json data/
ENV MAP_FILE=data/paraiba.map.gz PORT=8000
EXPOSE 8000
CMD ["python", "-m", "app.main"]
