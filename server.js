const express = require('express');
const puppeteer = require('puppeteer');

const app = express();
app.use(express.json({ limit: '10mb' }));

// Credenziali configurabili tramite variabili d'ambiente di Render (con fallback di sicurezza)
const USER_ID = process.env.API_USER_ID || "mio_user_id";
const API_KEY = process.env.API_KEY || "mia_api_key_segreta";

let browser;

// Inizializzazione istanza globale di Chromium Headless
async function initBrowser() {
  try {
    browser = await puppeteer.launch({
      executablePath: process.env.PUPPETEER_EXEC_PATH || null,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--no-first-run',
        '--no-zygote'
      ]
    });
    console.log('✅ Browser Chromium Headless avviato con successo.');
  } catch (err) {
    console.error('❌ Errore durante l\'avvio di Chromium:', err);
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

// Endpoint principale di rendering compatibile con il payload di HCTI
app.post('/v1/image', authenticate, async (req, res) => {
  let page = null;
  try {
    const { 
      html = '', 
      css = '', 
      viewport_width = 820, 
      viewport_height = 520, 
      device_scale = 2 
    } = req.body;

    if (!html) {
      return res.status(400).json({ error: 'Il campo HTML è obbligatorio.' });
    }

    if (!browser) {
      return res.status(500).json({ error: 'Il motore di rendering non è pronto.' });
    }

    // Apri una nuova scheda nel browser condiviso
    page = await browser.newPage();

    // Configura le dimensioni del viewport e la risoluzione (scale factor)
    await page.setViewport({
      width: parseInt(viewport_width, 10),
      height: parseInt(viewport_height, 10),
      deviceScaleFactor: parseFloat(device_scale)
    });

    // Costruisci la struttura HTML completa includendo il CSS personalizzato
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

    // Carica il contenuto e attendi il caricamento di risorse e font esterni
    await page.setContent(fullContent, { waitUntil: 'networkidle0' });

    // Cattura lo screenshot in memoria (buffer PNG)
    const imageBuffer = await page.screenshot({ type: 'png' });

    // Chiudi la scheda per liberare memoria
    await page.close();

    // Invia direttamente i byte dell'immagine PNG
    res.setHeader('Content-Type', 'image/png');
    res.send(imageBuffer);

  } catch (error) {
    if (page) await page.close().catch(() => {});
    console.error('❌ Errore durante il rendering:', error);
    res.status(500).json({ error: 'Errore interno durante il rendering dell\'immagine.' });
  }
});

// Endpoint di Health Check per monitoraggio
app.get('/health', (req, res) => {
  res.json({ status: 'OK', browserConnected: !!browser });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
  await initBrowser();
  console.log(`🚀 Server in ascolto sulla porta ${PORT}`);
});
