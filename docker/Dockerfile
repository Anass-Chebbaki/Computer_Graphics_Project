FROM python:3.11-slim

LABEL maintainer="your@email.com"
LABEL description="NL2Scene3D pipeline — senza Blender (solo LLM + parsing)"

# Dipendenze sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e installa dipendenze Python
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

# Copia il resto del progetto
COPY config/ ./config/
COPY scripts/ ./scripts/

# Variabili d'ambiente configurabili
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://host.docker.internal:11434/api/tags || exit 1

ENTRYPOINT ["python", "scripts/run_pipeline.py"]
CMD ["--interactive"]