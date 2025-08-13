# syntax=docker/dockerfile:1.7
FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Madrid \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Dependencias del sistema (incluye tzdata)
RUN apt-get update && apt-get install -y --no-install-recommends \
      tzdata ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar deps primero para aprovechar cache
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copiar el resto del código
COPY . /app

# Usuario no root por seguridad
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Arranque por defecto (API)
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]