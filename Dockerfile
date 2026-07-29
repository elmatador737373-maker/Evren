# Usa un'immagine ufficiale Python basata su Debian (ottima compatibilità)
FROM python:3.11-slim

# Evita prompt interattivi durante l'installazione
ENV DEBIAN_FRONTEND=noninteractive

# Installa le dipendenze di sistema richieste da Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgconf-2-4 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libdamages1 \
    libxi6 \
    libxtst6 \
    libappindicator3-1 \
    libnss3 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Imposta la cartella di lavoro nel container
WORKDIR /app

# Copia i file dei requisiti e installa le librerie Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installa i binari di Playwright per Chromium (senza bisogno di root extra)
RUN playwright install chromium

# Copia tutto il resto del codice del bot nel container
COPY . .

# Comando per avviare il bot
CMD ["python", "evren.py"]
