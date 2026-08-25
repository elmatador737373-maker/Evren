const express = require('express');
const puppeteer = require('puppeteer-core');
const chromium = require('@sparticuz/chromium');

const app = express();

app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));

const USER_ID = process.env.API_USER_ID || "Evren";
const API_KEY = process.env.API_KEY || "Evren";

// CODA SEQUENZIALE: Esegue una sola richiesta di rendering alla volta per evitare picchi di RAM
let activeRenderPromise = Promise.resolve();

function enqueueRender(task) {
  const result = activeRenderPromise.then(task, task);
  activeRenderPromise = result.catch(() => {}); 
  return result;
}

// Inizializzazione browser ultra-leggero
async function getBrowser() {
  return await puppeteer.launch({
    args: [
      ...chromium.args,
      '--single-process',                  // Esegue tutto su un solo processo
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--no-sandbox',
      '--no-zygote',
      '--disable-extensions',
      '--disable-background-networking',
      '--disable-syntax-highlighting',
      '--disable-spell-checking',
      '--js-flags="--max-old-space-size=256"' // Impedisce al motore JS di superare 256MB di RAM
    ],
    defaultViewport: chromium.defaultViewport,
    executablePath: await chromium.executablePath(),
    headless: chromium.headless,
  });
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

// Logica di rendering dell'immagine
async function processRender(req, res) {
  let browser = null;
  let page = null;

  try {
    const { 
      html = '', 
      css = '', 
      viewport_width = 820, 
      viewport_height = 520, 
      device_scale = 1 // Valore predefinito a 1 per risparmiare fino a 4x di RAM
    } = req.body;

    if (!html) {
      return res.status(400).json({ error: 'Il campo HTML è obbligatorio.' });
    }

    browser = await getBrowser();
    page = await browser.newPage();

    // Intercetta e blocca risorse inutili in background
    await page.setRequestInterception(true);
    page.on('request', (req) => {
      const type = req.resourceType();
      if (['media', 'other'].includes(type)) {
        req.abort();
      } else {
        req.continue();
      }
    });

    await page.setViewport({
      width: parseInt(viewport_width, 10),
      height: parseInt(viewport_height, 10),
      deviceScaleFactor: parseFloat(device_scale)
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

    // Timeout rigido a 15 secondi per evitare che pagine difettose blocchino il server
    await page.setContent(fullContent, { 
      waitUntil: 'domcontentloaded',
      timeout: 15000 
    });

    const imageBuffer = await page.screenshot({ type: 'png' });

    res.setHeader('Content-Type', 'image/png');
    res.send(imageBuffer);

  } catch (error) {
    console.error('❌ Errore durante il rendering:', error.message);
    res.status(500).json({ error: 'Errore durante il rendering dell\'immagine o Timeout superato.' });
  } finally {
    // Pulizia garantita delle risorse aperte
    if (page) await page.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});

    // Invocazione esplicita del Garbage Collector per liberare RAM immediatamente
    if (global.gc) {
      global.gc();
    }
  }
}

// Endpoint principale con gestione in coda
app.post('/v1/image', authenticate, (req, res) => {
  enqueueRender(() => processRender(req, res));
});

// Endpoint di Health Check per UptimeRobot o monitoraggio
app.get('/health', (req, res) => {
  res.json({ status: 'OK' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`🚀 Server in ascolto sulla porta ${PORT}`);
});
