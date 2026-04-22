FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend ./backend
RUN pip install --upgrade pip && pip install -e ./backend
WORKDIR /app/backend

EXPOSE 8080

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn anvil.main:app --host 0.0.0.0 --port 8080 --workers 1"]
