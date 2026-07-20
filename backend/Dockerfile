FROM python:3.10-slim

WORKDIR /app

# curl only (healthcheck). No compilers: every dependency installs from a
# prebuilt wheel (psycopg2-binary bundles libpq).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create a non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -r -u 10001 -g appgroup -m -d /home/appuser -s /bin/bash appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000
