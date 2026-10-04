const express = require('express');
const puppeteer = require('puppeteer-core');
const chromium = require('@sparticuz/chromium');

const app = express();

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

const USER_ID = process.env.API_USER_ID || "Evren";
const API_KEY = process.env.API_KEY || "Evren";

// --- GESTIONE CODA AVANZATA E LIMITI DI CARICO ---
const MAX_QUEUE_SIZE = 10;
const requestQueue = [];
let isProcessing = false;

// --- GESTIONE BROWSER PERSISTENTE ---
let globalBrowser = null;
let rendersCount = 0;
const MAX_RENDERS_BEFORE_RESTART = 50; // Riavvia il browser ogni 50 render per svuotare la RAM

async function initBrowser() {
  if (globalBrowser) return globalBrowser;

  console.log("🚀 Avvio nuova istanza persistente di Chromium...");
  globalBrowser = await puppeteer.launch({
    args: [
      ...chromium.args,
      '--single-process',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--no-sandbox',
      '--no-zygote',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-web-security', // Disabilita CORS per velocizzare il caricamento locale
      '--js-flags="--max-old-space-size=256"'
    ],
    defaultViewport: chromium.defaultViewport,
    executablePath: await chromium.executablePath(),
    headless: chromium.headless,
  });

  // Se Chromium crasha internamente, scarta l'istanza per farla riavviare
  globalBrowser.on('disconnected', () => {
    console.warn("⚠️ Browser disconnesso. Verrà riavviato alla prossima richiesta.");
    globalBrowser = null;
  });

  return globalBrowser;
}

async function closeBrowser() {
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

// --- LOGICA DI ELABORAZIONE CODA ---
async function processQueue() {
  if (isProcessing || requestQueue.length === 0) return;
  isProcessing = true;

  while (requestQueue.length > 0) {
    const { req, res } = requestQueue.shift();

    // OTTIMIZZAZIONE: Se il client si è disconnesso nel frattempo, non fare il rendering
    if (req.destroyed) {
      console.log("⏭️ Client disconnesso prima del render, salto la richiesta.");
      continue;
    }

    await executeRender(req, res);
  }

  isProcessing = false;
}

// Logica di rendering dell'immagine
async function executeRender(req, res) {
  let context = null;
  let page = null;

  try {
    // 1. Manutenzione preventiva per memory leaks
    rendersCount++;
    if (rendersCount > MAX_RENDERS_BEFORE_RESTART) {
      console.log("🔄 Riavvio programmato del browser per liberare RAM...");
      await closeBrowser();
      rendersCount = 0;
      if (global.gc) global.gc(); // Forza il Garbage Collector di Node
    }

    const browser = await initBrowser();
    
    // 2. Isolamento: usa un contesto incognito per ogni rendering (più leggero di una nuova finestra)
    context = await browser.createIncognitoBrowserContext();
    page = await context.newPage();

    // Intercetta e blocca risorse inutili in background
    await page.setRequestInterception(true);
    page.on('request', (request) => {
      const type = request.resourceType();
      // Blocchiamo immagini esterne (se non richieste dal tuo HTML), font e media
      if (['media', 'other', 'websocket'].includes(type)) {
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

    await page.setViewport({
      width: parseInt(viewport_width, 10) || 820,
      height: parseInt(viewport_height, 10) || 520,
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

    // Timeout ridotto a 10s: se l'HTML locale non si carica in 10s, c'è un problema
    await page.setContent(fullContent, { 
      waitUntil: 'domcontentloaded',
      timeout: 10000 
    });

    const imageBuffer = await page.screenshot({ type: 'png' });

    if (!res.headersSent) {
      res.setHeader('Content-Type', 'image/png');
      res.send(imageBuffer);
    }

  } catch (error) {
    console.error('❌ Errore durante il rendering:', error.message);
    if (!res.headersSent) {
      res.status(500).json({ error: 'Errore durante il rendering o Timeout superato.' });
    }
  } finally {
    // Chiusura garantita della tab e del contesto isolato
    if (page) await page.close().catch(() => {});
    if (context) await context.close().catch(() => {});
  }
}

// Endpoint principale
app.post('/', authenticate, (req, res) => {
  if (!req.body.html) {
    return res.status(400).json({ error: 'Il campo HTML è obbligatorio.' });
  }

  // Se la coda è troppo lunga, rifiuta per proteggere il server
  if (requestQueue.length >= MAX_QUEUE_SIZE) {
    return res.status(429).json({ error: 'Server troppo occupato. Riprova tra poco.' });
  }

  requestQueue.push({ req, res });
  processQueue(); // Avvia l'elaborazione se non è già in corso
});

// Endpoint di Health Check per UptimeRobot
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'OK', queueSize: requestQueue.length, memoryLimit: 'Stable' });
});

const PORT = process.env.PORT || 10000;

app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 Server in ascolto su 0.0.0.0:${PORT}`);
});
