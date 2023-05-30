# Imagem base
FROM python:3.11.3-slim-buster

# Definir o diretório de trabalho dentro do container
WORKDIR /app

# Copiar os arquivos necessários para o diretório de trabalho
COPY requirements.txt .
COPY ./app/main.py .

# Instalar as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Expor a porta em que a API estará rodando
EXPOSE 8000

# Comando para iniciar a API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]