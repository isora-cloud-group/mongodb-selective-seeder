# Declarar argumentos globales sin valor por defecto obliga a recibir versiones desde .env.
ARG MONGO_VERSION
ARG PYTHON_VERSION

FROM mongo:${MONGO_VERSION} AS mongo-tools

FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Instalar libgssapi-krb5-2 porque mongorestore y bsondump oficiales enlazan dinámicamente con Kerberos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*

# Copiar herramientas oficiales compiladas desde la imagen mongo para evitar parsear binarios en Python.
COPY --from=mongo-tools /usr/bin/mongorestore /usr/local/bin/mongorestore
COPY --from=mongo-tools /usr/bin/bsondump /usr/local/bin/bsondump

# Verificar en tiempo de construcción que las librerías compartidas resuelven correctamente.
RUN mongorestore --version && bsondump --version

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENTRYPOINT ["python", "-m", "src.main"]
