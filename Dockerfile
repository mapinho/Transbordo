FROM python:3.11-slim

WORKDIR /app

# Dependências instaladas a partir de requirements.txt (versões fixadas)
# em uma camada separada, para o cache de build do Docker só reinstalar
# tudo quando requirements.txt mudar -- não a cada alteração de código.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TZ=America/Sao_Paulo

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.enableCORS=false", \
     "--server.enableXSRF=false"]
