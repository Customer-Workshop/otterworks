FROM python:3.12-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir poetry==1.8.2
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.in-project true && poetry install --no-root --no-dev

FROM python:3.12-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8083
HEALTHCHECK --interval=10s --timeout=3s CMD curl -f http://localhost:8083/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083"]
