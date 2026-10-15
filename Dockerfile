FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# fonts for the conversation-map image; tesseract only needed for the optional screenshot OCR path
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pytesseract

COPY . .
RUN useradd -m app && chown -R app /app
USER app

# polling by default; set WEBHOOK_URL (and expose $PORT) for webhook mode
CMD ["python", "-m", "bot.app"]
