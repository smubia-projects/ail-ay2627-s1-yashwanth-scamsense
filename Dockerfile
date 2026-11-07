# ScamSense web API (FastAPI) for Cloud Run. Build context: repo root.
# The Telegram bot (bot/) is phase 2 and is excluded from this image (see .dockerignore).
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health', timeout=5)" || exit 1

CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
