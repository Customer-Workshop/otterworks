FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bridge.py .
RUN useradd --system --uid 1001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8097
CMD ["python", "bridge.py"]
