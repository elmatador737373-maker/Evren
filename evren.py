import os
import json
import math
import threading
import urllib.request
from collections import defaultdict

import aiohttp
import discord
from discord.ext import commands, tasks
from flask import Flask, request, jsonify, render_template_string

# =====================================================================
# CONFIGURAZIONE AMBIENTE (RENDER)
# =====================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
PORT = int(os.getenv("PORT", 8080))

VOICE_CAT_NAME = "⫷༺ 🔊 𝐕𝐎𝐂𝐄 𝐏𝐑𝐎𝐒𝐒𝐈𝐌𝐈𝐓𝐀̀ 𝐃𝐈𝐍𝐀𝐌𝐈𝐂𝐀 ༻⫸"
LOBBY_NAME = "〔🔊〕・ʟᴏʙʙʏ-ᴠᴏᴄᴀʟᴇ-ᴘʀᴏꜱꜱɪᴍɪᴛᴀ̀"
TEMP_PREFIX = "〔🎙️〕・ᴘʀᴏꜱꜱɪᴍɪᴛᴀ̀-"

# =====================================================================
# SERVER WEB FLASK: UPTIMEROBOT + MINIMAPPA / MAPPA ESPANDIBILE GPS
# =====================================================================
app = Flask(__name__)

GPS_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Mine Roleplay — Tactical GPS & Minimappa</title>
<style>
  :root {
    --bg: #090b10;
    --panel: rgba(16, 20, 30, 0.90);
    --border: rgba(0, 229, 255, 0.30);
    --accent: #00e5ff;
    --red: #ff1744;
    --blue: #2979ff;
    --orange: #ff9100;
    --text: #eef2f7;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { background: var(--bg); color: var(--text); height: 100dvh; overflow: hidden; display: flex; flex-direction: column; }

  #login-overlay {
    position: fixed; inset: 0; background: radial-gradient(circle at center, #131926 0%, #07090d 100%);
    display: flex; align-items: center; justify-content: center; z-index: 100; padding: 20px;
  }
  .login-card {
    background: var(--panel); backdrop-filter: blur(14px); border: 1px solid var(--border);
    border-radius: 18px; padding: 28px; width: 100%; max-width: 380px; text-align: center;
    box-shadow: 0 20px 50px rgba(0,0,0,0.75);
  }
  .login-card h1 { font-size: 1.35rem; letter-spacing: 1px; color: var(--accent); margin-bottom: 6px; }
  .login-card p { font-size: 0.85rem; color: #94a3b8; margin-bottom: 18px; }
  .login-card input {
    width: 100%; padding: 13px 15px; border-radius: 10px; border: 1px solid #334155;
    background: #0f172a; color: #fff; font-size: 1rem; margin-bottom: 14px; outline: none;
  }
  .login-card input:focus { border-color: var(--accent); }
  .btn-primary {
    width: 100%; padding: 13px; border: none; border-radius: 10px;
    background: linear-gradient(135deg, #00b8d4, #00e5ff); color: #05080f;
    font-weight: 800; font-size: 0.95rem; cursor: pointer; letter-spacing: 0.5px;
  }

  header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--border);
    z-index: 20;
  }
  .brand { font-weight: 800; font-size: 0.95rem; color: var(--accent); display: flex; align-items: center; gap: 8px; }
  .badge-duty {
    padding: 4px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 800;
    background: #1e293b; color: #94a3b8; border: 1px solid #334155;
  }
  .badge-duty.MRPD { background: rgba(41,121,255,0.2); color: #60a5fa; border-color: #2979ff; }
  .badge-duty.MREMS { background: rgba(255,23,68,0.2); color: #f87171; border-color: #ff1744; }
  .badge-duty.MRFD { background: rgba(255,145,0,0.2); color: #fbbf24; border-color: #ff9100; }

  #stage {
    flex: 1; position: relative; display: flex; align-items: center; justify-content: center;
    background: #07090e;
  }
  #map-wrapper {
    position: relative; width: 315px; height: 315px; border-radius: 24px;
    border: 2px solid var(--accent); overflow: hidden;
    box-shadow: 0 0 35px rgba(0, 229, 255, 0.22);
    transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
  }
  #map-wrapper.expanded {
    width: 100%; height: 100%; border-radius: 0; border: none; box-shadow: none;
  }
  canvas { width: 100%; height: 100%; display: block; background: #0c1017; }

  .controls-top-right {
    position: absolute; top: 14px; right: 14px; display: flex; flex-direction: column; gap: 8px; z-index: 15;
  }
  .ctrl-btn {
    background: var(--panel); backdrop-filter: blur(10px); color: #fff;
    border: 1px solid var(--border); border-radius: 10px; padding: 9px 12px;
    font-size: 0.8rem; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 6px;
  }
  .ctrl-btn:active { transform: scale(0.96); }

  .hud-bottom {
    position: absolute; bottom: 14px; left: 14px; right: 14px;
    background: var(--panel); backdrop-filter: blur(12px); border: 1px solid var(--border);
    border-radius: 14px; padding: 10px 14px; display: flex; justify-content: space-between;
    align-items: center; gap: 10px; z-index: 15; flex-wrap: wrap;
  }
  select {
    background: #0f172a; color: #fff; border: 1px solid #334155; border-radius: 8px;
    padding: 7px 10px; font-size: 0.82rem; outline: none;
  }
  .coords { font-family: monospace; font-size: 0.82rem; color: #94a3b8; }
</style>
</head>
<body>

<div id="login-overlay">
  <div class="login-card">
    <h1>MINE ROLEPLAY GPS</h1>
    <p>Inserisci il tuo Nickname Minecraft (es. <b>Elmatador</b> o <b>.Elmatador</b>) per avviare la minimappa live.</p>
    <input type="text" id="mc-input" placeholder="Nickname Minecraft..." autocomplete="off">
    <button class="btn-primary" onclick="connectGPS()">AVVIA MINIMAPPA LIVE</button>
  </div>
</div>

<header>
  <div class="brand">🛰️ MINE ROLEPLAY <span style="color:#fff;font-weight:400;">GPS</span></div>
  <div id="duty-badge" class="badge-duty">CITTADINO (PRIVATO)</div>
</header>

<div id="stage">
  <div id="map-wrapper">
    <canvas id="radarCanvas"></canvas>

    <div class="controls-top-right">
      <button class="ctrl-btn" id="expand-btn" onclick="toggleExpand()">⛶ ESPANDI MAPPA</button>
      <button class="ctrl-btn" onclick="changeZoom(1.25)">➕ ZOOM IN</button>
      <button class="ctrl-btn" onclick="changeZoom(0.8)">➖ ZOOM OUT</button>
      <button class="ctrl-btn" onclick="logoutGPS()">🔄 CAMBIA NICK</button>
    </div>

    <div class="hud-bottom">
      <div>
        <div style="font-size:0.72rem;color:#94a3b8;">DESTINAZIONE GPS</div>
        <select id="poi-select" onchange="setDestination()">
          <option value="">Nessuna destinazione</option>
          <option value="0,0">🏙️ Piazza Centrale / Municipio</option>
          <option value="80,-60">🚔 Centrale MRPD</option>
          <option value="-90,-50">🚑 Ospedale MREMS 911</option>
          <option value="95,75">🚒 Caserma MRFD</option>
          <option value="-75,80">🏦 Banca Nazionale</option>
          <option value="30,110">⛽ Benzinaio & MR Motors</option>
        </select>
      </div>
      <div class="coords" id="coords-label">X: 0 | Z: 0</div>
    </div>
  </div>
</div>

<script>
  let myMcName = localStorage.getItem("mr_mc_name") || "";
  let isExpanded = false;
  let zoom = 1.8;
  let me = null;
  let units = [];
  let dest = null;
  let pollTimer = null;

  const POIS = [
    { name: "MUNICIPIO", x: 0, z: 0, color: "#00e5ff" },
    { name: "MRPD", x: 80, z: -60, color: "#2979ff" },
    { name: "MREMS 911", x: -90, z: -50, color: "#ff1744" },
    { name: "MRFD", x: 95, z: 75, color: "#ff9100" },
    { name: "BANCA", x: -75, z: 80, color: "#ffd600" },
    { name: "MR MOTORS", x: 30, z: 110, color: "#00e676" }
  ];

  if (myMcName) {
    document.getElementById("mc-input").value = myMcName;
  }

  function connectGPS() {
    const val = document.getElementById("mc-input").value.trim();
    if (!val) return;
    myMcName = val;
    localStorage.setItem("mr_mc_name", val);
    document.getElementById("login-overlay").style.display = "none";
    fetchRadar();
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(fetchRadar, 1800);
  }

  function logoutGPS() {
    document.getElementById("login-overlay").style.display = "flex";
  }

  function toggleExpand() {
    isExpanded = !isExpanded;
    const wrap = document.getElementById("map-wrapper");
    const btn = document.getElementById("expand-btn");
    if (isExpanded) {
      wrap.classList.add("expanded");
      btn.innerHTML = "🗗 RIDUCI MINIMAPPA";
      zoom = 1.2;
    } else {
      wrap.classList.remove("expanded");
      btn.innerHTML = "⛶ ESPANDI MAPPA";
      zoom = 1.8;
    }
    resizeCanvas();
  }

  function changeZoom(factor) {
    zoom = Math.max(0.4, Math.min(5.0, zoom * factor));
  }

  function setDestination() {
    const val = document.getElementById("poi-select").value;
    if (!val) { dest = null; return; }
    const [x, z] = val.split(",").map(Number);
    dest = { x, z };
  }

  async function fetchRadar() {
    try {
      const res = await fetch(`/api/gps_data?mc_name=${encodeURIComponent(myMcName)}`);
      const data = await res.json();
      if (!data.me) return;
      me = data.me;
      units = data.units || [];

      document.getElementById("coords-label").innerText =
        `X: ${Math.round(me.x)} | Z: ${Math.round(me.z)}`;

      const badge = document.getElementById("duty-badge");
      if (me.servizio) {
        badge.className = `badge-duty ${me.servizio}`;
        badge.innerText = `IN SERVIZIO: ${me.servizio} (${units.length} UNITA')`;
      } else {
        badge.className = "badge-duty";
        badge.innerText = "CITTADINO (PRIVATO)";
      }
    } catch (e) {}
  }

  const canvas = document.getElementById("radarCanvas");
  const ctx = canvas.getContext("2d");

  function resizeCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
  }
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  function draw() {
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    const px = me ? me.x : 0;
    const pz = me ? me.z : 0;
    const yawRad = me ? ((me.yaw + 180) * Math.PI / 180) : 0;

    ctx.save();
    ctx.translate(cx, cy);
    if (!isExpanded && me) {
      ctx.rotate(-yawRad);
    }

    const blockStep = 40 * zoom * window.devicePixelRatio;
    const offsetX = (-px * zoom * window.devicePixelRatio) % blockStep;
    const offsetY = (-pz * zoom * window.devicePixelRatio) % blockStep;

    ctx.strokeStyle = "#1b2433";
    ctx.lineWidth = 6 * zoom;
    for (let gx = offsetX - w; gx < w * 2; gx += blockStep) {
      ctx.beginPath(); ctx.moveTo(gx, -h * 2); ctx.lineTo(gx, h * 2); ctx.stroke();
    }
    for (let gy = offsetY - h; gy < h * 2; gy += blockStep) {
      ctx.beginPath(); ctx.moveTo(-w * 2, gy); ctx.lineTo(w * 2, gy); ctx.stroke();
    }

    if (dest && me) {
      const dx = (dest.x - px) * zoom * window.devicePixelRatio;
      const dz = (dest.z - pz) * zoom * window.devicePixelRatio;
      ctx.strokeStyle = "#ffd600";
      ctx.lineWidth = 4;
      ctx.setLineDash([10, 8]);
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(dx, dz); ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = "#ffd600";
      ctx.beginPath(); ctx.arc(dx, dz, 7 * window.devicePixelRatio, 0, Math.PI * 2); ctx.fill();
    }

    POIS.forEach(poi => {
      const sx = (poi.x - px) * zoom * window.devicePixelRatio;
      const sz = (poi.z - pz) * zoom * window.devicePixelRatio;
      ctx.fillStyle = poi.color;
      ctx.beginPath(); ctx.arc(sx, sz, 5 * window.devicePixelRatio, 0, Math.PI * 2); ctx.fill();
      if (isExpanded) {
        ctx.fillStyle = "#cbd5e1";
        ctx.font = `bold ${11 * window.devicePixelRatio}px sans-serif`;
        ctx.fillText(poi.name, sx + 8, sz + 4);
      }
    });

    units.forEach(u => {
      if (me && u.mc_name.toLowerCase() === me.mc_name.toLowerCase()) return;
      const ux = (u.x - px) * zoom * window.devicePixelRatio;
      const uz = (u.z - pz) * zoom * window.devicePixelRatio;
      let col = "#2979ff";
      if (u.servizio === "MREMS") col = "#ff1744";
      else if (u.servizio === "MRFD") col = "#ff9100";

      ctx.fillStyle = col;
      ctx.beginPath(); ctx.arc(ux, uz, 7 * window.devicePixelRatio, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = "#ffffff";
      ctx.font = `bold ${11 * window.devicePixelRatio}px sans-serif`;
      ctx.fillText(`[${u.servizio}] ${u.nome_ic || u.mc_name}`, ux + 10, uz + 4);
    });

    ctx.restore();

    ctx.save();
    ctx.translate(cx, cy);
    if (isExpanded && me) {
      ctx.rotate(yawRad);
    }
    ctx.fillStyle = "#00e5ff";
    ctx.beginPath();
    ctx.moveTo(0, -11 * window.devicePixelRatio);
    ctx.lineTo(8 * window.devicePixelRatio, 9 * window.devicePixelRatio);
    ctx.lineTo(0, 4 * window.devicePixelRatio);
    ctx.lineTo(-8 * window.devicePixelRatio, 9 * window.devicePixelRatio);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    requestAnimationFrame(draw);
  }
  draw();
</script>
</body>
</html>
"""

@app.route("/")
@app.route("/health")
def health():
    return jsonify({"status": "online", "service": "Mine Roleplay Core & GPS"}), 200

@app.route("/gps")
def gps_page():
    return render_template_string(GPS_HTML_TEMPLATE)

@app.route("/api/gps_data")
def api_gps_data():
    mc_name = request.args.get("mc_name", "").strip()
    if not mc_name or not SUPABASE_URL or not SUPABASE_KEY:
        return jsonify({"me": None, "units": []})

    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/mr_voice_sync?select=*",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return jsonify({"me": None, "units": []})

    me = next((r for r in rows if r.get("mc_name", "").lower() == mc_name.lower()), None)
    if not me:
        return jsonify({"me": None, "units": []})

    # Privacy totale: i cittadini vedono solo se stessi; FDO/EMS/VVF in servizio vedono i colleghi
    if me.get("servizio") in ("MRPD", "MREMS", "MRFD"):
        units = [r for r in rows if r.get("servizio") in ("MRPD", "MREMS", "MRFD")]
    else:
        units = []

    return jsonify({"me": me, "units": units})

def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

# =====================================================================
# BOT DISCORD: VOCE PROSSIMITA' DINAMICA + SICUREZZA 2FA/OTP + CAD
# =====================================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def sb_headers(upsert: bool = False):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    if upsert:
        h["Prefer"] = "resolution=merge-duplicates"
    return h

# --- PULSANTI APPROVAZIONE 2FA IN DM ---
class AuthApprovalView(discord.ui.View):
    def __init__(self, mc_name: str, pending_ip: str):
        super().__init__(timeout=180)
        self.mc_name = mc_name
        self.pending_ip = pending_ip

    async def update_supabase(self, payload: dict):
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{SUPABASE_URL}/rest/v1/mr_auth_links?mc_name=ilike.{self.mc_name}",
                headers=sb_headers(upsert=True),
                json=payload
            )

    @discord.ui.button(label="✅ AUTORIZZA ACCESSO", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_supabase({
            "mc_name": self.mc_name,
            "authorized_ip": self.pending_ip,
            "pending_ip": "",
            "status": "approved"
        })
        await interaction.response.edit_message(
            content=f"✅ **Accesso autorizzato per `{self.mc_name}`!** Puoi giocare su Mine Roleplay.",
            view=None
        )

    @discord.ui.button(label="❌ BLOCCA INTRUSO", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_supabase({
            "mc_name": self.mc_name,
            "pending_ip": "",
            "status": "denied"
        })
        await interaction.response.edit_message(
            content=f"🚨 **Tentativo di accesso bloccato per `{self.mc_name}`!** Il giocatore è stato espulso dal server.",
            view=None
        )

# --- COMANDI DISCORD ---
@bot.command(name="collega")
async def collega_mc(ctx, codice: str):
    """Collega l'account Minecraft tramite il codice OTP a 6 cifre mostrato in gioco."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        await ctx.send("❌ Database Supabase non configurato.")
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{SUPABASE_URL}/rest/v1/mr_auth_links?link_code=eq.{codice.strip()}&status=eq.unlinked&select=*",
            headers=sb_headers()
        ) as resp:
            if resp.status != 200:
                await ctx.send("❌ Errore di connessione al database.")
                return
            rows = await resp.json()

        if not rows:
            await ctx.send("❌ Codice non valido o scaduto! Entra sul server Minecraft per leggere il tuo codice a 6 cifre.")
            return

        row = rows[0]
        mc_name = row["mc_name"]
        pending_ip = row.get("pending_ip", "")

        await session.post(
            f"{SUPABASE_URL}/rest/v1/mr_auth_links?mc_name=ilike.{mc_name}",
            headers=sb_headers(upsert=True),
            json={
                "mc_name": mc_name,
                "discord_id": ctx.author.id,
                "authorized_ip": pending_ip,
                "pending_ip": "",
                "link_code": "",
                "status": "approved"
            }
        )

    await ctx.send(
        f"✅ {ctx.author.mention}, account Minecraft **`{mc_name}`** collegato e sbloccato! Ora sei dentro **Mine Roleplay**."
    )

@bot.command(name="mio_id")
async def mio_id(ctx):
    await ctx.send(
        f"🪪 {ctx.author.mention}, il tuo ID Discord è **`{ctx.author.id}`**.\n"
        f"Scrivi su Minecraft: **`/collegadiscord {ctx.author.id}`** ed entra in **{LOBBY_NAME}** per la chat vocale di prossimità!"
    )

@bot.command(name="cittadino")
async def info_cittadino(ctx, *, query: str):
    """Consulta l'anagrafica IC di un cittadino da Supabase."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{SUPABASE_URL}/rest/v1/mr_cittadini?or=(mc_name.ilike.*{query}*,nome_ic.ilike.*{query}*)&select=*",
            headers=sb_headers()
        ) as resp:
            rows = await resp.json() if resp.status == 200 else []

    if not rows:
        await ctx.send(f"🔍 Nessun cittadino trovato per **`{query}`**.")
        return

    c = rows[0]
    embed = discord.Embed(title=f"🪪 USA STATE ID — {c.get('nome_ic', 'N/D')}", color=0x00E5FF)
    embed.add_field(name="Account MC", value=f"`{c.get('mc_name')}`", inline=True)
    embed.add_field(name="Età / Sesso", value=f"{c.get('eta', 25)} anni ({c.get('sesso', 'Uomo')})", inline=True)
    embed.add_field(name="Provenienza", value=c.get("origine", "Los Santos"), inline=True)
    embed.add_field(name="Fazione / Lavoro", value=f"{c.get('fazione', 'Nessuna')} ({c.get('lavoro', 'Disoccupato')})", inline=True)
    embed.add_field(name="Patente / Porto d'Armi", value=f"Patente: {'✅' if c.get('patente_auto') else '❌'} | Armi: {'✅' if c.get('porto_armi') else '❌'}", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="ricercati")
async def lista_ricercati(ctx):
    """Mostra i ricercati attivi sul terminale MRPD CAD."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{SUPABASE_URL}/rest/v1/mr_cad_reati?tipo=eq.RICERCATO&attivo=eq.true&select=*",
            headers=sb_headers()
        ) as resp:
            rows = await resp.json() if resp.status == 200 else []

    if not rows:
        await ctx.send("🚓 **MRPD CAD:** Nessun soggetto ricercato attivo in città al momento.")
        return

    embed = discord.Embed(title="🚨 MRPD CAD — BOLLETTINO RICERCATI ATTIVI", color=0xFF1744)
    for r in rows[:10]:
        embed.add_field(
            name=f"👤 {r.get('cittadino_nome_ic')} ({r.get('cittadino_mc')})",
            value=f"**Reato:** {r.get('reato')} | **Agente:** {r.get('agente_nome')}",
            inline=False
        )
    await ctx.send(embed=embed)

# --- TASK 1: INVIO RICHIESTE 2FA IN DM ---
@tasks.loop(seconds=2.5)
async def check_auth_requests():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{SUPABASE_URL}/rest/v1/mr_auth_links?status=eq.waiting_dm&select=*",
                headers=sb_headers()
            ) as resp:
                if resp.status != 200:
                    return
                rows = await resp.json()

            for row in rows:
                mc_name = row["mc_name"]
                discord_id = row.get("discord_id")
                if not discord_id:
                    continue
                pending_ip = row.get("pending_ip", "Sconosciuto")

                await session.post(
                    f"{SUPABASE_URL}/rest/v1/mr_auth_links?mc_name=ilike.{mc_name}",
                    headers=sb_headers(upsert=True),
                    json={"mc_name": mc_name, "status": "notified"}
                )

                user = bot.get_user(int(discord_id)) or await bot.fetch_user(int(discord_id))
                if user:
                    try:
                        await user.send(
                            f"🔐 **Richiesta di Accesso su Mine Roleplay**\n"
                            f"Qualcuno sta entrando con il tuo nickname **`{mc_name}`**.\n"
                            f"Sei tu? Premi il pulsante qui sotto per autorizzare l'ingresso:",
                            view=AuthApprovalView(mc_name, pending_ip)
                        )
                    except discord.Forbidden:
                        pass
    except Exception:
        pass

# --- TASK 2: MOTORE VOCALE DINAMICO DI PROSSIMITA' ---
@tasks.loop(seconds=2.5)
async def proximity_voice_engine():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SUPABASE_URL}/rest/v1/mr_voice_sync?select=*", headers=sb_headers()) as resp:
                if resp.status != 200:
                    return
                rows = await resp.json()
    except Exception:
        return

    players = [r for r in rows if r.get("discord_id") and int(r["discord_id"]) > 0]

    adj = defaultdict(set)
    for i in range(len(players)):
        p1 = players[i]
        id1 = int(p1["discord_id"])
        for j in range(i + 1, len(players)):
            p2 = players[j]
            id2 = int(p2["discord_id"])

            same_call = p1.get("call_partner") and (
                p1["call_partner"] == p2["mc_name"] or p2.get("call_partner") == p1["mc_name"]
            )
            same_radio = p1.get("radio_freq") and p1["radio_freq"] == p2.get("radio_freq")
            same_world = p1.get("world") == p2.get("world")

            in_range = False
            if same_world:
                dist = math.sqrt(
                    (p1["x"] - p2["x"]) ** 2 +
                    (p1["y"] - p2["y"]) ** 2 +
                    (p1["z"] - p2["z"]) ** 2
                )
                max_r = max(p1.get("voice_range", 18), p2.get("voice_range", 18))
                if dist <= max_r:
                    in_range = True

            if same_call or same_radio or in_range:
                adj[id1].add(id2)
                adj[id2].add(id1)

    visited = set()
    clusters = []
    for p in players:
        uid = int(p["discord_id"])
        if uid not in visited:
            comp = []
            stack = [uid]
            visited.add(uid)
            while stack:
                curr = stack.pop()
                comp.append(curr)
                for nxt in adj[curr]:
                    if nxt not in visited:
                        visited.add(nxt)
                        stack.append(nxt)
            clusters.append(comp)

    for guild in bot.guilds:
        cat = discord.utils.get(guild.categories, name=VOICE_CAT_NAME)
        if not cat:
            cat = await guild.create_category(VOICE_CAT_NAME)

        lobby = discord.utils.get(cat.voice_channels, name=LOBBY_NAME)
        if not lobby:
            lobby = await guild.create_voice_channel(LOBBY_NAME, category=cat)

        active_members = {}
        for vc in cat.voice_channels:
            for m in vc.members:
                active_members[m.id] = m

        temp_channels = [vc for vc in cat.voice_channels if vc.name.startswith(TEMP_PREFIX)]

        for cluster in clusters:
            connected = [active_members[uid] for uid in cluster if uid in active_members]
            if len(connected) >= 2:
                target_vc = None
                for m in connected:
                    if m.voice and m.voice.channel and m.voice.channel.name.startswith(TEMP_PREFIX):
                        target_vc = m.voice.channel
                        break

                if not target_vc:
                    num = len(temp_channels) + 1
                    target_vc = await guild.create_voice_channel(f"{TEMP_PREFIX}{num}", category=cat)
                    temp_channels.append(target_vc)

                for m in connected:
                    if m.voice and m.voice.channel != target_vc:
                        try:
                            await m.move_to(target_vc)
                        except Exception:
                            pass
            elif len(connected) == 1:
                m = connected[0]
                if m.voice and m.voice.channel != lobby:
                    try:
                        await m.move_to(lobby)
                    except Exception:
                        pass

        # Elimina subito tutte le stanze vocali temporanee rimaste vuote
        for vc in list(cat.voice_channels):
            if vc.name.startswith(TEMP_PREFIX) and len(vc.members) == 0:
                try:
                    await vc.delete()
                except Exception:
                    pass

@bot.event
async def on_ready():
    print(f"Bot connesso come {bot.user} | Mine Roleplay Core attivo!")
    if not check_auth_requests.is_running():
        check_auth_requests.start()
    if not proximity_voice_engine.is_running():
        proximity_voice_engine.start()

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot.run(DISCORD_TOKEN)
