FROM node:18-slim

# Installa Chromium e solo le dipendenze essenziali di sistema
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-liberation \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Configura le variabili d'ambiente per usare Chromium di sistema
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXEC_PATH=/usr/bin/chromium

WORKDIR /usr/src/app

# Copia i file delle dipendenze
COPY package*.json ./

# Usa npm install con --omit=dev (sostituisce npm ci e la flag deprecata --only=production)
RUN npm install --omit=dev

# Copia il codice sorgente
COPY . .

EXPOSE 3000

# Avvia l'applicazione tramite lo script "start" definito nel package.json
CMD ["npm", "start"]
