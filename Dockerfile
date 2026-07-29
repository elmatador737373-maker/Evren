FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Copia i requisiti e installa le librerie Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installa automaticamente le dipendenze di sistema e il browser Chromium tramite Playwright
RUN playwright install-deps chromium && playwright install chromium

# Copia il resto del codice
COPY . .

CMD ["python", "evren.py"]
