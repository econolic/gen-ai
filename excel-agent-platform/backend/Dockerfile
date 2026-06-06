FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend
ENV POETRY_VERSION=2.1.4

COPY backend/pyproject.toml backend/poetry.lock* /app/backend/
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"
RUN cd /app/backend \
    && poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi --no-root

COPY backend /app/backend
COPY mcp_servers /app/mcp_servers

WORKDIR /app/backend
