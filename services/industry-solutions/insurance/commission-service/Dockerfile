FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "fastapi>=0.110,<1" \
    "uvicorn[standard]>=0.29,<1" \
    "pydantic>=2.6,<3" \
    "pydantic-settings>=2.2,<3" \
    "oracledb>=2.4,<4"
COPY app ./app

RUN useradd -r -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=30 CMD python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
