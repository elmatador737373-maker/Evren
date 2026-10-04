const express = require('express');
const puppeteer = require('puppeteer-core');
const chromium = require('@sparticuz/chromium');

const app = express();

// Limite aumentato per gestire HTML/CSS corposi e immagini base64
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

const USER_ID = process.env.API_USER_ID || "Evren";
const API_KEY = process.env.API_KEY || "Evren";

// --- GESTIONE CODA & RISORSE ---
const MAX_QUEUE_SIZE = 10;
const requestQueue = [];
let isProcessing = false;

// --- GESTIONE BROWSER PERSISTENTE (SINGLETON) ---
let globalBrowser = null;
let rendersCount = 0;
const MAX_RENDERS_BEFORE_RECYCLE = 40; // Ricicla il browser ogni 40 render per prevenire leak di RAM

async function initBrowser() {
  if (globalBrowser && globalBrowser.isConnected()) {
    return globalBrowser;
  }

  // Flag ottimizzati: disabilitano audio, animazioni inutili e riducono l'overhead a monte
  globalBrowser = await puppeteer.launch({
    args: [
      ...chromium.args,
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--no-zygote',
      '--single-process',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-component-update',
      '--mute-audio',
      '--no-default-browser-check',
      '--disable-breakpad',
      '--js-flags="--max-old-space-size=256"'
    ],
    defaultViewport: chromium.defaultViewport,
    executablePath: await chromium.executablePath(),
    headless: chromium.headless,
  });

  globalBrowser.on('disconnected', () => {
    console.warn("⚠️ Browser Chromium disconnesso.");
    globalBrowser = null;
  });

  return globalBrowser;
}

async function recycleBrowser() {
  if (globalBrowser) {
    await globalBrowser.close().catch(() => {});
    globalBrowser = null;
  }
}

// Middleware di autenticazione HTTP Basic Auth
function authenticate(req, res, next) {
  const authHeader = req.headers.authorization;
  if (!authHeader || !authHeader.startsWith('Basic ')) {
    return res.status(401).json({ error: 'Autenticazione richiesta. Utilizza Basic Auth.' });
  }

  const credentials = Buffer.from(authHeader.split(' ')[1], 'base64').toString('utf-8');
  const [user, key] = credentials.split(':');

  if (user === USER_ID && key === API_KEY) {
    return next();
  }
  return res.status(403).json({ error: 'Credenziali non valide.' });
}

// Elaborazione sequenziale della coda
async function processQueue() {
  if (isProcessing || requestQueue.length === 0) return;
  isProcessing = true;

  while (requestQueue.length > 0) {
    const { req, res } = requestQueue.shift();

    // Se il bot/client ha chiuso la connessione nel frattempo, salta il lavoro
    if (req.destroyed) {
      continue;
    }

    await executeRender(req, res);
  }

  isProcessing = false;
}

// Logica di rendering ultra-veloce
async function executeRender(req, res) {
  let page = null;

  try {
    rendersCount++;
    if (rendersCount > MAX_RENDERS_BEFORE_RECYCLE) {
      await recycleBrowser();
      rendersCount = 0;
      if (global.gc) global.gc();
    }

    const browser = await initBrowser();
    page = await browser.newPage();

    // BLOCCO SELETTIVO: permette immagini (per la fototessera), CSS e font inline
    // Blocca video, audio, analytics e websocket che rallenterebbero l'esecuzione
    await page.setRequestInterception(true);
    page.on('request', (request) => {
      const resourceType = request.resourceType();
      if (['media', 'websocket', 'manifest', 'other'].includes(resourceType)) {
        request.abort();
      } else {
        request.continue();
      }
    });

    const { 
      html = '', 
      css = '', 
      viewport_width = 820, 
      viewport_height = 520, 
      device_scale = 1 
    } = req.body;

    const width = parseInt(viewport_width, 10) || 820;
    const height = parseInt(viewport_height, 10) || 520;

    await page.setViewport({
      width: width,
      height: height,
      deviceScaleFactor: parseFloat(device_scale) || 1
    });

    const fullContent = `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8">
          <style>
            * { box-sizing: border-box; }
            body { margin: 0; padding: 0; }
            ${css}
          </style>
        </head>
        <body>
          ${html}
        </body>
      </html>
    `;

    // 'domcontentloaded' è fino a 3 volte più veloce di 'load' o 'networkidle0'
    await page.setContent(fullContent, { 
      waitUntil: 'domcontentloaded',
      timeout: 15000 
    });

    // Ottimizzazioni screenshot: clip esatto del viewport e cattura buffer PNG rapida
    const imageBuffer = await page.screenshot({ 
      type: 'png',
      clip: { x: 0, y: 0, width: width, height: height },
      optimizeForSpeed: true 
    });

    if (!res.headersSent) {
      res.setHeader('Content-Type', 'image/png');
      res.setHeader('Cache-Control', 'no-store');
      res.send(imageBuffer);
    }

  } catch (error) {
    console.error('❌ Errore rendering dettagliato:', error.stack || error.message);
    if (!res.headersSent) {
      res.status(500).json({ error: `Errore rendering: ${error.message}` });
    }
  } finally {
    if (page) {
      await page.close().catch(() => {});
    }
    // Esecuzione Garbage Collector a fine operazione se avviato con --expose-gc
    if (global.gc) {
      global.gc();
    }
  }
}

// Endpoint Principale POST
app.post('/', authenticate, (req, res) => {
  if (!req.body.html) {
    return res.status(400).json({ error: 'Il campo HTML è obbligatorio.' });
  }

  if (requestQueue.length >= MAX_QUEUE_SIZE) {
    return res.status(429).json({ error: 'Server occupato: troppe richieste in coda. Riprova tra poco.' });
  }

  requestQueue.push({ req, res });
  processQueue();
});

// Endpoint di Health Check leggero per UptimeRobot / Render
app.get(['/', '/health'], (req, res) => {
  res.status(200).json({ 
    status: 'OK', 
    queue: requestQueue.length,
    renders: rendersCount
  });
});

// Avvio del server su tutte le interfacce di rete (0.0.0.0) per Render
const PORT = process.env.PORT || 10000;
app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Server in ascolto su 0.0.0.0:${PORT}`);
});
