FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cria diretório de dados
RUN mkdir -p /data && chmod 777 /data

# Copia código
COPY app.py .

# Porta
EXPOSE 3000

# Comando
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3000"]
