import os
import random
import string
import threading
import io
import json
import asyncio
import datetime
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import re
import difflib

import aiohttp
from flask import Flask, jsonify
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.async_api import async_playwright
import wavelink

# ==========================================
# ⚙️ CONFIGURAZIONE E VARIABILI D'AMBIENTE
# ==========================================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Ruoli e permessi
RUOLO_STAFF_ID = 1549740413454254090
RUOLO_BANCOMAT_ID = 1549740436002967572
RUOLO_ARMERIA_ID = 1549740503074078841
RUOLO_MOTORIZZAZIONE_ID = 1549740497218834462
RUOLO_POLIZIA_ID = 1549740476007972997
RUOLO_IMMOBILIARE_ID = 1549740511731130588
RUOLO_FBI_ID = 1549740475202670642
ID_RUOLO_EDILIZIA = None
RUOLI_MECCANICI_IDS = [1549740517242310676]
RUOLO_ECONOMIA_STAFF_ID = 1549740407905067150

# Canali log e operativi
ID_CANALE_LOGS = 1255868935790657587
ID_CANALE_LOG_AGGIUNTI = 1478146946198667505
ID_CANALE_LOG_RIMOSSI = 1478146969464471762
CANALE_STIPENDI_ID = 1459566404100686009
PANIC_CHANNEL_ID = 1519418659821584384
ID_CANALE_EMERGENZA = 1519418659821584384
ID_RUOLO_FDO = 1363487988570521670
ID_RUOLO_EMS = 1254146971535544471
ID_RUOLO_FIRE = 1436420396726616210

# Fazioni e audio
NOME_FAZIONE_EDILIZIA = "Edilizia"
TOLLERANZA_MINUTI = 15
URL_SQUILLO = "https://youtu.be/56hYHf58hdc"
URL_RIFIUTO = "https://youtu.be/_FhnSWY9-JI"

SERVER_CONFIGS = {
    1233353915559313478: {
        "fines": 1519609832372437034,
        "arrests": 1520010488212361337,
        "reports": 1520010488212361337,
        "seized_vehicles": 1520010510828048395,
        "seized_items": 1520010510828048395,
        "role_tag": "<@&1359569600198611104>",
    },
    1499394373270507701: {
        "fines": 1499398731504685207,
        "arrests": 1499398686067658897,
        "reports": 1499398731504685207,
        "seized_vehicles": 1499398820851744799,
        "seized_items": 1499398780481704046,
        "role_tag": "<@&1363487988570521670>",
    },
}

ROLES_TO_TAG = [
    "<@&1363487988570521670>",
    "<@&1259234623230181396>",
]

# Configurazione materiali miniera
MATERIALS_DATA = {
    "Sabbia": {"emoji": "🏖️", "time_min": 15, "qty_kg": 70},
    "Pietra": {"emoji": "🪨", "time_min": 15, "qty_kg": 60},
    "Legno": {"emoji": "🪵", "time_min": 8, "qty_kg": 50},
    "Mattoni": {"emoji": "🧱", "time_min": 20, "qty_kg": 40},
    "Cemento": {"emoji": "🏗️", "time_min": 20, "qty_kg": 30},
    "Vetro": {"emoji": "🪟", "time_min": 12, "qty_kg": 25},
    "Tegole": {"emoji": "🏠", "time_min": 14, "qty_kg": 20},
    "Ferro": {"emoji": "⚙️", "time_min": 20, "qty_kg": 15},
}

LISTA_MATERIALI_DISPONIBILI = list(MATERIALS_DATA.keys())

# ==========================================
# 🎨 EMERALD DESIGN SYSTEM (COLORI EMBED)
# ==========================================
class EmeraldColor:
    MAIN = discord.Color.from_rgb(46, 204, 113)       # Verde Smeraldo principale
    DARK = discord.Color.from_rgb(22, 160, 133)      # Smeraldo scuro
    ACCENT = discord.Color.from_rgb(39, 174, 96)     # Verde brillante
    NAVY = discord.Color.from_rgb(30, 41, 59)        # Slate Blue scuro
    RED = discord.Color.from_rgb(231, 76, 60)        # Rosso sanzioni/allarmi
    GOLD = discord.Color.from_rgb(241, 196, 15)      # Oro economia/lavori
    BLUE = discord.Color.from_rgb(52, 152, 219)      # Blu informativo/CAD

# ==========================================
# 🤖 BOT SETUP & INTENTS
# ==========================================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.bans = True
intents.emojis = True
intents.integrations = True
intents.webhooks = True
intents.invites = True
intents.voice_states = True
intents.presences = True
intents.messages = True
intents.guild_messages = True
intents.guild_reactions = True
intents.guild_typing = True
intents.dm_messages = True
intents.dm_reactions = True
intents.dm_typing = True
intents.message_content = True
intents.guild_scheduled_events = True
intents.auto_moderation_configuration = True
intents.auto_moderation_execution = True
intents.polls = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# 🎵 WAVELINK HOOK
# ==========================================
async def my_setup_hook():
    node = wavelink.Node(
        uri="https://bot-rp-iro0.onrender.com",
        password="youshallnotpass"
    )
    try:
        await wavelink.Pool.connect(nodes=[node], client=bot)
        print("✅ [WAVELINK] Nodo audio Emerald RP collegato!")
    except Exception as e:
        print(f"❌ [WAVELINK] Errore di connessione: {e}")

bot.setup_hook = my_setup_hook

@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload) -> None:
    print(f"🎉 Emerald Audio Node online! URI: {payload.node.uri} | ID: {payload.session_id}")

# ==========================================
# 🌐 FLASK KEEP-ALIVE
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "online", "server": "Emerald RP Infrastructure"})

def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 🛠️ HELPER GENERALI
# ==========================================
def ha_ruolo_staff(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    return any(r.id == RUOLO_STAFF_ID for r in interaction.user.roles) or interaction.user.guild_permissions.administrator

def ha_ruolo_meccanico():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        user_role_ids = [role.id for role in interaction.user.roles]
        return any(role_id in user_role_ids for role_id in RUOLI_MECCANICI_IDS)
    return app_commands.check(predicate)

def get_or_create_user(user_id: int, username: str):
    response = supabase.table("users").select("*").eq("discord_id", str(user_id)).execute()
    if response.data:
        return response.data[0]
    else:
        new_user = {
            "discord_id": str(user_id),
            "username": username,
            "wallet": 500.0,
            "bank": 1500.0,
            "pin": None,
            "max_weight": 10.0
        }
        insert_res = supabase.table("users").insert(new_user).execute()
        return insert_res.data[0]

def log_transaction(user_id: str, trans_type: str, amount: float, details: str):
    supabase.table("transactions_log").insert({
        "discord_id": str(user_id),
        "type": trans_type,
        "amount": round(amount, 2),
        "description": details
    }).execute()

def genera_num_documento() -> str:
    prefisso = "".join(random.choices(string.ascii_uppercase, k=2))
    numero = "".join(random.choices(string.digits, k=7))
    return f"{prefisso}{numero}"

def calculate_user_inventory_weight(user_id: str) -> float:
    res = supabase.table("inventory").select("quantity, weight").eq("discord_id", str(user_id)).execute()
    total_weight = 0.0
    if res.data:
        for row in res.data:
            q = row.get("quantity", 1)
            w = row.get("weight", 0.1)
            total_weight += q * w
    return round(total_weight, 2)

async def upload_to_imgbb(foto: discord.Attachment) -> str:
    url = "https://api.imgbb.com/1/upload"
    foto_bytes = await foto.read()
    data = aiohttp.FormData()
    data.add_field("key", IMGBB_API_KEY)
    data.add_field("image", foto_bytes, filename="foto.png", content_type="image/png")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as response:
            if response.status == 200:
                res_json = await response.json()
                return res_json["data"]["url"]
            raise Exception(f"ImgBB HTTP {response.status}")

def format_tempo_rimanente(secondi: int) -> str:
    if secondi <= 0:
        return "Completato"
    ore, resto = divmod(secondi, 3600)
    minuti, sec = divmod(resto, 60)
    if ore > 0:
        return f"{ore}h {minuti}m"
    elif minuti > 0:
        return f"{minuti}m {sec}s"
    return f"{sec}s"

def get_val(data: dict, key: str, fallback: str = "Nessuna") -> str:
    if not data:
        return fallback
    val = data.get(key)
    if val is None or str(val).strip() == "":
        return fallback
    return str(val)

def estrai_tariffa_da_nome_ruolo(nome_ruolo: str) -> float | None:
    match = re.search(r'\[\s*(\d+(?:[\.,]\d+)?)\s*[\$€]?\s*\]', nome_ruolo)
    if match:
        valore_str = match.group(1).replace('.', '').replace(',', '.')
        try:
            return float(valore_str)
        except ValueError:
            pass
    return None

async def notifica_utente_dm(bot_client: commands.Bot, user_id: int, embed: discord.Embed):
    try:
        utente = bot_client.get_user(user_id) or await bot_client.fetch_user(user_id)
        if utente:
            await utente.send(embed=embed)
    except Exception:
        pass

# ==========================================
# 🔍 AUTOCOMPLETE FUNCTIONS
# ==========================================
async def fazione_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("faction_roles").select("faction_name").execute()
    fazioni = list(set(row["faction_name"] for row in (res.data or [])))
    return [app_commands.Choice(name=f, value=f) for f in fazioni if current.lower() in f.lower()][:25]

async def oggetto_custom_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("custom_items").select("name").ilike("name", f"%{current}%").limit(25).execute()
    return [app_commands.Choice(name=row["name"], value=row["name"]) for row in (res.data or [])]

async def shop_item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("custom_items").select("name").ilike("name", f"%{current}%").limit(25).execute()
    return [app_commands.Choice(name=i["name"], value=i["name"]) for i in (res.data or [])]

async def veicoli_trasferimento_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("registered_vehicles").select("plate, model").eq("discord_id", str(interaction.user.id)).execute()
    choices = []
    for v in (res.data or []):
        display = f"{v.get('model', 'Veicolo')} [{v.get('plate', 'N/A')}]"
        if current.lower() in display.lower():
            choices.append(app_commands.Choice(name=display, value=v.get("plate")))
    return choices[:25]

async def sender_inventory_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("inventory").select("item_name, quantity").eq("discord_id", str(interaction.user.id)).gt("quantity", 0).ilike("item_name", f"%{current}%").limit(25).execute()
    return [app_commands.Choice(name=f"{r['item_name']} (x{r['quantity']})", value=r["item_name"]) for r in (res.data or [])]

async def target_user_inventory_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    target = interaction.namespace.utente
    if not target:
        return []
    res = supabase.table("inventory").select("item_name, quantity").eq("discord_id", str(target.id)).gt("quantity", 0).ilike("item_name", f"%{current}%").limit(25).execute()
    return [app_commands.Choice(name=f"{r['item_name']} (x{r['quantity']})", value=r["item_name"]) for r in (res.data or [])]

async def elimina_veicolo_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    target_id = interaction.namespace.utente
    if not target_id:
        return []
    res = supabase.table("registered_vehicles").select("plate, model").eq("discord_id", str(target_id)).execute()
    choices = []
    for v in (res.data or []):
        display = f"{v.get('model', 'Veicolo')} [{v.get('plate', 'N/A')}]"
        if current.lower() in display.lower():
            choices.append(app_commands.Choice(name=display, value=v.get("plate")))
    return choices[:25]

async def item_id_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("custom_items").select("id, name").ilike("name", f"%{current}%").limit(25).execute()
    return [app_commands.Choice(name=i["name"], value=str(i["id"])) for i in (res.data or [])]


# ==========================================
# 🪪 ANAGRAFE E DOCUMENTI (STEPPING MODALS)
# ==========================================
class CreaDocumentiStep2Modal(ui.Modal, title="🪪 Dati Fisici — Emerald RP"):
    def __init__(self, nome, cognome, data_nascita, luogo_nascita):
        super().__init__()
        self.nome = nome
        self.cognome = cognome
        self.data_nascita = data_nascita
        self.luogo_nascita = luogo_nascita

        self.colore_occhi = ui.TextInput(label="Colore Occhi", placeholder="Es. Marroni, Verdi, Azzurri", required=True, max_length=30)
        self.colore_capelli = ui.TextInput(label="Colore Capelli", placeholder="Es. Castani, Neri, Biondi", required=True, max_length=30)
        self.segni_particolari = ui.TextInput(label="Segni Particolari", placeholder="Es. Cicatrice sul mento o Nessuno", required=False, max_length=100)

        self.add_item(self.colore_occhi)
        self.add_item(self.colore_capelli)
        self.add_item(self.segni_particolari)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        cf_temporaneo = f"EMRLD-{user_id[-6:]}"
        doc_numero = f"DOC-{user_id[-5:]}"

        data = {
            "discord_id": user_id,
            "name": self.nome,
            "surname": self.cognome,
            "birth_date": self.data_nascita,
            "birth_place": self.luogo_nascita,
            "eye_color": self.colore_occhi.value.strip(),
            "hair_color": self.colore_capelli.value.strip(),
            "distinct_marks": self.segni_particolari.value.strip() or "Nessuno",
            "cf": cf_temporaneo,
            "doc_number": doc_numero,
            "photo_url": None
        }

        try:
            supabase.table("documents").insert(data).execute()
            embed = discord.Embed(
                title="✅ Identità Registrata!",
                description="I tuoi dati anagrafici sono stati salvati su **Emerald Database**.\nUsa `/carica_foto_documento` per inserire la foto tessera.",
                color=EmeraldColor.MAIN
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore durante il salvataggio dei dati: `{e}`", ephemeral=True)

class ApriStep2View(ui.View):
    def __init__(self, nome, cognome, data_nascita, luogo_nascita):
        super().__init__(timeout=180)
        self.nome = nome
        self.cognome = cognome
        self.data_nascita = data_nascita
        self.luogo_nascita = luogo_nascita

    @ui.button(label="Passo 2: Dati Fisici", style=discord.ButtonStyle.success, emoji="➡️")
    async def apri_secondo_modulo(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(
            CreaDocumentiStep2Modal(self.nome, self.cognome, self.data_nascita, self.luogo_nascita)
        )

class CreaDocumentiStep1Modal(ui.Modal, title="🪪 Anagrafe — Emerald RP (1/2)"):
    nome = ui.TextInput(label="Nome", placeholder="Es. Alessandro", required=True, max_length=50)
    cognome = ui.TextInput(label="Cognome", placeholder="Es. Moretti", required=True, max_length=50)
    data_nascita = ui.TextInput(label="Data di Nascita", placeholder="Es. 14/08/1995", required=True, max_length=20)
    luogo_nascita = ui.TextInput(label="Luogo di Nascita", placeholder="Es. Los Angeles", required=True, max_length=50)

    self.add_item(nome)
    self.add_item(cognome)
    self.add_item(data_nascita)
    self.add_item(luogo_nascita)

    async def on_submit(self, interaction: discord.Interaction):
        nome_val = self.nome.value.strip()
        cognome_val = self.cognome.value.strip()
        data_val = self.data_nascita.value.strip()
        luogo_val = self.luogo_nascita.value.strip()

        view = ApriStep2View(nome_val, cognome_val, data_val, luogo_val)
        await interaction.response.send_message(
            "📌 **Dati preliminari salvati.**\nPremi il bottone qui sotto per proseguire con i dettagli somatici.",
            view=view,
            ephemeral=True
        )

class PannelloAnagrafeView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Compila Anagrafica", style=discord.ButtonStyle.success, emoji="🪪", custom_id="emerald_anagrafe_apri")
    async def apri_modal(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)
        existing = await asyncio.to_thread(lambda: supabase.table("documents").select("discord_id").eq("discord_id", user_id).execute())
        if existing and existing.data:
            return await interaction.response.send_message("❌ **Hai già un'identità registrata su Emerald RP!**", ephemeral=True)
        await interaction.response.send_modal(CreaDocumentiStep1Modal())

def build_id_embed(doc: dict, discord_id: int, user_roles: list = None) -> discord.Embed:
    doc_number = doc.get("doc_number") or genera_num_documento()

    # Licenze
    d_res = supabase.table("driver_licenses").select("license_type, status").eq("discord_id", str(discord_id)).execute()
    g_res = supabase.table("gun_licenses").select("license_type, status").eq("discord_id", str(discord_id)).execute()

    patenti = "\n".join([f"• {l['license_type']} (`{l['status']}`)" for l in (d_res.data or [])]) or "• *Nessuna patente registrata*"
    porti = "\n".join([f"• {l['license_type']} (`{l['status']}`)" for l in (g_res.data or [])]) or "• *Nessun porto d'armi registrato*"

    embed = discord.Embed(
        title="🏛️ CERTIFICATO DI IDENTITÀ UFFICIALE",
        description="**Documento Ufficiale di Riconoscimento**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=EmeraldColor.MAIN
    )
    if doc.get("photo_url"):
        embed.set_thumbnail(url=doc["photo_url"])

    embed.add_field(name="👤 Cognome e Nome", value=f"**{doc.get('surname', '').upper()}** {doc.get('name', '').capitalize()}", inline=True)
    embed.add_field(name="📅 Nascita", value=f"{doc.get('birth_date')} a {doc.get('birth_place')}", inline=True)
    embed.add_field(name="📑 N° Documento", value=f"`{doc_number}`", inline=False)
    embed.add_field(name="🔢 Codice Fiscale", value=f"`{doc.get('cf')}`", inline=True)
    embed.add_field(name="🧬 Tratti Fisici", value=f"Occhi: **{doc.get('eye_color')}**\nCapelli: **{doc.get('hair_color')}**\nSegni: *{doc.get('distinct_marks')}*", inline=True)
    embed.add_field(name="🚗 Abilitazioni Guida", value=patenti, inline=False)
    embed.add_field(name="🛡️ Porti d'Arma", value=porti, inline=False)
    embed.set_footer(text="Emerald State Identification • Sistema Centrale Anagrafico")
    return embed

# ==========================================
# 🚗 LIBRETTO VEICOLO EMBED
# ==========================================
def build_vehicle_title_embed(proprietario: str, targa: str, modello: str, sequestrato: bool, modifiche: list) -> discord.Embed:
    stato_testo = "🚨 VEICOLO SOTTO SEQUESTRO" if sequestrato else "🟢 REGOLARE PER LA CIRCOLAZIONE"
    stato_colore = EmeraldColor.RED if sequestrato else EmeraldColor.MAIN

    mods_list = "\n".join([f"• **{m.get('mod_type', 'Modifica')}**: {m.get('details', 'Nessun dettaglio')}" for m in modifiche]) if modifiche else "*Configurazione di serie (Nessuna modifica registrata).*"

    embed = discord.Embed(
        title="📑 CERTIFICATO DI IMMATRICOLAZIONE E PROPRIETÀ",
        description="**Department of Motor Vehicles — Emerald State**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=stato_colore
    )
    embed.add_field(name="👤 Intestatario Registrato", value=f"**{proprietario}**", inline=False)
    embed.add_field(name="🚘 Modello", value=f"`{modello}`", inline=True)
    embed.add_field(name="🏷️ Targa Ufficiale", value=f"**`{targa}`**", inline=True)
    embed.add_field(name="🔢 VIN Seriale", value=f"`1EMRLD{targa[:3]}92837`", inline=True)
    embed.add_field(name="📌 Stato Amministrativo", value=f"**{stato_testo}**", inline=False)
    embed.add_field(name="🔧 Modifiche Omologate", value=mods_list, inline=False)
    embed.set_footer(text="Emerald DMV • Registro Pubblico Veicoli Automotori")
    return embed

# ==========================================
# 🧾 FATTURA DIGITALE EMBED
# ==========================================
def build_invoice_embed(f: dict) -> discord.Embed:
    stato = f.get("status", "Da Pagare")
    is_paid = stato.lower() == "pagata"
    color = EmeraldColor.MAIN if is_paid else EmeraldColor.RED
    badge = "🟢 PAGATA" if is_paid else "🔴 DA SALDARE"

    embed = discord.Embed(
        title=f"🧾 FATTURA COMMERCIALE #{f.get('id')}",
        description=f"Emessa da: **{f.get('azienda')}**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        color=color
    )
    embed.add_field(name="👤 Cliente", value=f.get("destinatario", "N/D"), inline=True)
    embed.add_field(name="✍️ Operatore Emittente", value=f.get("emittente", "N/D"), inline=True)
    embed.add_field(name="📅 Data Emissione", value=f.get("data", "N/D"), inline=True)
    embed.add_field(name="📦 Descrizione / Causale", value=f"```{f.get('causale', 'Nessuna causale specificata')}```", inline=False)
    embed.add_field(name="💰 Totale Dovuto", value=f"### € {float(f.get('importo', 0.0)):,.2f}", inline=True)
    embed.add_field(name="📌 Stato Fiscale", value=f"**{badge}**", inline=True)
    embed.set_footer(text="Emerald RP Financial Department • Fatturazione Elettronica")
    return embed

# ==========================================
# ⛏️ MINATORE & CANTIERE LOOPS
# ==========================================
def generate_cantiere_embed(cantiere: dict) -> discord.Embed:
    materiali_list = cantiere.get("materiali", [])
    if isinstance(materiali_list, str):
        try:
            materiali_list = json.loads(materiali_list)
        except Exception:
            materiali_list = []

    tot_richiesti = sum(mat.get("totale", 0) for mat in materiali_list)
    tot_consumati = sum(mat.get("consumati", 0) for mat in materiali_list)
    progresso = min(100, int((tot_consumati / tot_richiesti) * 100)) if tot_richiesti > 0 else 100

    is_paused = cantiere.get("paused", False)
    tempo_rimanente = cantiere.get("tempo_rimanente", 0)

    if not is_paused and cantiere.get("end_time"):
        try:
            end_dt = datetime.fromisoformat(cantiere["end_time"])
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            tempo_rimanente = max(0, int((end_dt - datetime.now(timezone.utc)).total_seconds()))
        except Exception:
            pass

    tempo_str = format_tempo_rimanente(tempo_rimanente)

    embed = discord.Embed(
        title="🏗️ CANTIERE EDILIZIA EMERALD",
        description=f"Avanzamento lavori: **{progresso}%**\n`[{'█' * (progresso // 10)}{'░' * (10 - (progresso // 10))}]`",
        color=EmeraldColor.GOLD if not is_paused else EmeraldColor.RED
    )
    embed.add_field(name="🏢 Impresa Appaltatrice", value=cantiere["azienda"], inline=True)
    embed.add_field(name="📍 Indirizzo Progetto", value=cantiere["address"], inline=True)

    mat_text = ""
    for mat in materiali_list:
        status = "✅" if mat.get("consumati", 0) >= mat.get("totale", 0) else "📦"
        mat_text += f"{status} **{mat['nome']}**: `{mat.get('consumati', 0)}/{mat['totale']}` impiegati\n"

    embed.add_field(name="🧱 Risorse Richieste dal Deposito", value=mat_text or "Nessun materiale", inline=False)
    embed.add_field(name="👷 Capocantiere", value=f"<@{cantiere['builder_id']}>", inline=True)
    embed.add_field(name="⏳ Tempo Residuo", value=f"`{tempo_str}`", inline=True)

    if is_paused:
        embed.set_footer(text="⚠️ CANTIERE SOSPESO: Risorse mancanti nel deposito della fazione Edilizia!")
    else:
        embed.set_footer(text="🔨 Lavori attivi. Prelievi regolari effettuati ogni 60 secondi.")
    return embed

@tasks.loop(seconds=60)
async def gestore_cantieri_loop():
    res_cantieri = supabase.table("cantieri").select("*").execute()
    if not res_cantieri.data:
        return

    now_dt = datetime.now(timezone.utc)

    for cantiere in res_cantieri.data:
        msg_id = cantiere["message_id"]
        channel_id = int(cantiere.get("channel_id", 0))
        if not channel_id:
            continue

        channel = bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception:
                continue

        try:
            msg = await channel.fetch_message(int(msg_id))
        except Exception:
            continue

        materiali_list = cantiere["materiali"]
        if isinstance(materiali_list, str):
            try:
                materiali_list = json.loads(materiali_list)
            except Exception:
                materiali_list = []

        operai_ids = cantiere.get("operai_ids", [])
        if isinstance(operai_ids, str):
            try:
                operai_ids = json.loads(operai_ids)
            except Exception:
                operai_ids = []

        num_lavoratori = 1 + len(operai_ids)
        tutti_completati = True
        mancano_materiali = False

        for mat in materiali_list:
            consumati = mat.get("consumati", 0)
            totale = mat.get("totale", 0)

            if consumati < totale:
                tutti_completati = False
                mancanti = totale - consumati
                qta_da_prelevare = min(mancanti, max(1, num_lavoratori))

                inv_res = supabase.table("faction_inventory").select("*").eq("faction_name", NOME_FAZIONE_EDILIZIA).ilike("item_name", f"%{mat['nome']}%").execute()

                if inv_res.data and inv_res.data[0]["quantity"] > 0:
                    item_deposito = inv_res.data[0]
                    disponibile = item_deposito["quantity"]
                    prelevabili = min(qta_da_prelevare, disponibile)
                    nuova_qta = disponibile - prelevabili

                    if nuova_qta > 0:
                        supabase.table("faction_inventory").update({"quantity": nuova_qta}).eq("id", item_deposito["id"]).execute()
                    else:
                        supabase.table("faction_inventory").delete().eq("id", item_deposito["id"]).execute()

                    mat["consumati"] = consumati + prelevabili
                    if prelevabili < qta_da_prelevare:
                        mancano_materiali = True
                else:
                    mancano_materiali = True

        if tutti_completati:
            supabase.table("registered_properties").insert({
                "discord_id": cantiere["builder_id"],
                "address": cantiere["address"],
                "property_type": f"Edificio ({cantiere['grandezza'].capitalize()})",
            }).execute()

            supabase.table("cantieri").delete().eq("message_id", msg_id).execute()

            try:
                user = await bot.fetch_user(int(cantiere["builder_id"]))
                if user:
                    dm_embed = discord.Embed(
                        title="🎉 Costruzione Completata!",
                        description=f"L'opera presso **{cantiere['address']}** è terminata ed è stata accatastata!",
                        color=EmeraldColor.MAIN
                    )
                    await user.send(embed=dm_embed)
            except Exception:
                pass

            cantiere["materiali"] = materiali_list
            embed_completato = generate_cantiere_embed(cantiere)
            embed_completato.title = "🎉 Cantiere Terminato con Successo!"
            embed_completato.color = EmeraldColor.MAIN
            try:
                await msg.edit(embed=embed_completato, view=None)
            except Exception:
                pass
            continue

        was_paused = cantiere.get("paused", False)
        end_time_str = cantiere.get("end_time")

        if mancano_materiali:
            if not was_paused and end_time_str:
                try:
                    end_dt = datetime.fromisoformat(end_time_str)
                    tempo_rimanente = max(0, int((end_dt - now_dt).total_seconds()))
                except Exception:
                    tempo_rimanente = cantiere.get("tempo_rimanente", 0)

                supabase.table("cantieri").update({"materiali": materiali_list, "paused": True, "tempo_rimanente": tempo_rimanente}).eq("message_id", msg_id).execute()
                cantiere["paused"] = True
                cantiere["tempo_rimanente"] = tempo_rimanente
            else:
                supabase.table("cantieri").update({"materiali": materiali_list}).eq("message_id", msg_id).execute()
        else:
            if was_paused:
                tempo_rimanente = cantiere.get("tempo_rimanente", 0)
                nuovo_end_dt = datetime.now(timezone.utc) + timedelta(seconds=tempo_rimanente)
                supabase.table("cantieri").update({"materiali": materiali_list, "paused": False, "end_time": nuovo_end_dt.isoformat(), "tempo_rimanente": tempo_rimanente}).eq("message_id", msg_id).execute()
                cantiere["paused"] = False
                cantiere["end_time"] = nuovo_end_dt.isoformat()
            else:
                supabase.table("cantieri").update({"materiali": materiali_list}).eq("message_id", msg_id).execute()

        try:
            await msg.edit(embed=generate_cantiere_embed(cantiere))
        except Exception:
            pass

# ==========================================
# 💼 GESTIONE TURNI & STIPENDI
# ==========================================
async def invia_richiesta_stipendio(bot_client: commands.Bot, utente: discord.Member, turno: dict, motivo: str = "Fine Turno"):
    ora_inizio = datetime.fromisoformat(turno["ora_inizio"])
    ora_fine = datetime.now(timezone.utc)
    durata_secondi = (ora_fine - ora_inizio).total_seconds()
    durata_minuti = max(0, int(durata_secondi // 60))

    if durata_minuti < TOLLERANZA_MINUTI:
        embed_annullato = discord.Embed(
            title="⚠️ Turno Annullato",
            description=f"Il tuo turno di **{durata_minuti} min** è inferiore al limite minimo di **{TOLLERANZA_MINUTI} minuti**.",
            color=EmeraldColor.RED
        )
        await notifica_utente_dm(bot_client, utente.id, embed_annullato)
        return

    tariffa = float(turno.get("tariffa", 0.0))
    ore_lavorate = durata_secondi / 3600.0
    importo_calcolato = round(ore_lavorate * tariffa, 2)
    tempo_str = f"{durata_minuti // 60}h {durata_minuti % 60}m" if durata_minuti >= 60 else f"{durata_minuti} minuti"

    canale_stipendi = bot_client.get_channel(CANALE_STIPENDI_ID) or await bot_client.fetch_channel(CANALE_STIPENDI_ID)
    if not canale_stipendi:
        return

    embed_staff = discord.Embed(
        title="📑 Richiesta Liquidazione Turno",
        color=EmeraldColor.GOLD,
        timestamp=datetime.now()
    )
    embed_staff.add_field(name="👤 Lavoratore", value=f"{utente.mention}\n`{utente.name}`", inline=True)
    embed_staff.add_field(name="💰 Spettanza", value=f"```fix\n€ {importo_calcolato:,.2f}```", inline=True)
    embed_staff.add_field(name="💼 Mansione", value=f"`{turno.get('role_name', 'N/D')}`", inline=False)
    embed_staff.add_field(name="⏱️ Durata Lavoro", value=f"**{tempo_str}**", inline=True)
    embed_staff.add_field(name="💵 Tariffa Oraria", value=f"**€ {tariffa:,.2f}/h**", inline=True)
    embed_staff.add_field(name="📌 Chiusura", value=f"*{motivo}*", inline=False)
    embed_staff.set_thumbnail(url=utente.display_avatar.url)
    embed_staff.set_footer(text=f"ID Dipendente: {utente.id} • Emerald Work Central")

    view = ApprovazioneStipendioView(dipendente_id=utente.id, importo_calcolato=importo_calcolato)
    await canale_stipendi.send(embed=embed_staff, view=view)

    embed_dm = discord.Embed(
        title="🏁 Turno Concluso con Successo",
        description=f"Hai terminato il turno come **{turno.get('role_name')}**.\nRichiesta stipendio inoltrata all'amministrazione.",
        color=EmeraldColor.MAIN
    )
    embed_dm.add_field(name="Tempo", value=tempo_str, inline=True)
    embed_dm.add_field(name="Importo Stimato", value=f"€ {importo_calcolato:,.2f}", inline=True)
    await notifica_utente_dm(bot_client, utente.id, embed_dm)

class TariffaManualeModal(ui.Modal, title="💵 Configura Tariffa Oraria"):
    tariffa_input = ui.TextInput(label="Tariffa Oraria (€)", placeholder="Es. 350.00", required=True, max_length=10)

    def __init__(self, ruolo: discord.Role):
        super().__init__()
        self.ruolo = ruolo

    async def on_submit(self, interaction: discord.Interaction):
        try:
            tariffa = float(self.tariffa_input.value.replace(',', '.'))
            if tariffa <= 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Inserisci una cifra valida superiore a zero.", ephemeral=True)
        await avvia_turno_database(interaction, self.ruolo, tariffa)

async def avvia_turno_database(interaction: discord.Interaction, ruolo: discord.Role, tariffa: float):
    now_iso = datetime.now(timezone.utc).isoformat()
    supabase.table("turni_attivi").upsert({
        "user_id": str(interaction.user.id),
        "role_id": str(ruolo.id),
        "role_name": ruolo.name,
        "tariffa": tariffa,
        "ora_inizio": now_iso
    }).execute()

    embed = discord.Embed(
        title="⏱️ Turno Lavorativo Avviato",
        description=f"Buon turno, {interaction.user.mention}!",
        color=EmeraldColor.MAIN,
        timestamp=datetime.now()
    )
    embed.add_field(name="💼 Mansione", value=f"```{ruolo.name}```", inline=False)
    embed.add_field(name="💵 Compenso Concordato", value=f"**€ {tariffa:,.2f}/h**", inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=False)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=False)

class SelezioneRuoloSelect(ui.Select):
    def __init__(self, ruoli: list[discord.Role]):
        options = []
        for ruolo in ruoli[:25]:
            tariffa = estrai_tariffa_da_nome_ruolo(ruolo.name)
            desc = f"Tariffa rilevata: € {tariffa:,.2f}/h" if tariffa is not None else "Tariffa manuale richiesta"
            options.append(discord.SelectOption(label=ruolo.name[:100], value=str(ruolo.id), description=desc, emoji="💼"))
        super().__init__(placeholder="Scegli la qualifica per il turno...", options=options)

    async def callback(self, interaction: discord.Interaction):
        ruolo = interaction.guild.get_role(int(self.values[0]))
        tariffa = estrai_tariffa_da_nome_ruolo(ruolo.name)
        if tariffa is not None:
            await avvia_turno_database(interaction, ruolo, tariffa)
        else:
            await interaction.response.send_modal(TariffaManualeModal(ruolo))

class SelezioneRuoloView(ui.View):
    def __init__(self, ruoli: list[discord.Role]):
        super().__init__(timeout=60)
        self.add_item(SelezioneRuoloSelect(ruoli))

class ModificaImportoModal(ui.Modal, title="Modifica Spettanza"):
    nuovo_importo = ui.TextInput(label="Nuovo Totale (€)", placeholder="Es. 1200.00", required=True, max_length=15)

    def __init__(self, parent_view: "ApprovazioneStipendioView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            valore = float(self.nuovo_importo.value.replace(",", "."))
            if valore < 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Inserisci una somma valida.", ephemeral=True)

        self.parent_view.importo_calcolato = valore
        embed = interaction.message.embeds[0]
        embed.set_field_at(1, name="💰 Spettanza Ricalcolata", value=f"```fix\n€ {valore:,.2f}```", inline=True)
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(f"✅ Valore modificato a **€ {valore:,.2f}**.", ephemeral=True)

class ApprovazioneStipendioView(ui.View):
    def __init__(self, dipendente_id: int = None, importo_calcolato: float = None):
        super().__init__(timeout=None)
        self.dipendente_id = dipendente_id
        self.importo_calcolato = importo_calcolato

    def _get_data(self, message: discord.Message):
        embed = message.embeds[0]
        dip_id = self.dipendente_id or int(embed.footer.text.split("ID Dipendente: ")[1].split()[0])
        importo = self.importo_calcolato
        if importo is None:
            raw_val = embed.fields[1].value.replace("```fix", "").replace("```", "").replace("€", "").replace(",", "").strip()
            importo = float(raw_val)
        return dip_id, importo, embed

    @ui.button(label="Accredita", style=discord.ButtonStyle.success, emoji="✅", custom_id="emerald_stipendio_approva")
    async def approva(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        dip_id, importo, embed = self._get_data(interaction.message)

        u = supabase.table("users").select("bank").eq("discord_id", str(dip_id)).execute()
        saldo = u.data[0].get("bank", 0.0) if u.data else 0.0
        supabase.table("users").update({"bank": saldo + importo}).eq("discord_id", str(dip_id)).execute()

        log_transaction(str(dip_id), "Stipendio", importo, f"Turno autorizzato da {interaction.user.display_name}")

        for item in self.children:
            item.disabled = True

        embed.color = EmeraldColor.MAIN
        embed.title = "✅ Richiesta Stipendio Accreditata"
        embed.add_field(name="📌 Esito", value=f"Pagato da {interaction.user.mention} per **€ {importo:,.2f}**", inline=False)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send(f"✅ Bonifico di **€ {importo:,.2f}** accreditato a <@{dip_id}>.", ephemeral=True)

    @ui.button(label="Rettifica", style=discord.ButtonStyle.primary, emoji="✏️", custom_id="emerald_stipendio_modifica")
    async def modifica(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModificaImportoModal(self))

    @ui.button(label="Nega", style=discord.ButtonStyle.danger, emoji="❌", custom_id="emerald_stipendio_rifiuta")
    async def rifiuta(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        dip_id, importo, embed = self._get_data(interaction.message)

        for item in self.children:
            item.disabled = True

        embed.color = EmeraldColor.RED
        embed.title = "❌ Liquidazione Respinta"
        embed.add_field(name="📌 Esito", value=f"Rifiutato da {interaction.user.mention}", inline=False)
        await interaction.message.edit(embed=embed, view=self)
        await interaction.followup.send("❌ Richiesta respinta.", ephemeral=True)

# ==========================================
# 📞 EMERALD OS: TELEFONO & VOCALE
# ==========================================
async def riproduci_audio_canale(channel: discord.VoiceChannel, audio_url: str, loop: bool = False):
    player = None
    try:
        player = await asyncio.wait_for(channel.connect(cls=wavelink.Player), timeout=10.0)
        tracks = await wavelink.Playable.search(audio_url)
        if tracks:
            track = tracks[0]
            await player.play(track)
            await player.set_volume(70)
            while loop and player and player.connected:
                if not player.playing:
                    await player.play(track)
                await asyncio.sleep(1)
    except Exception as e:
        print(f"❌ [AUDIO ERRORE]: {e}")
    finally:
        if player and player.connected:
            try:
                await player.disconnect()
            except Exception:
                pass

async def avvia_chiamata_vocale(interaction: discord.Interaction, numero_destinatario: str):
    guild = interaction.guild
    chiamante = interaction.user
    numero_pulito = "".join(filter(str.isdigit, numero_destinatario))

    res = supabase.table("user_phones").select("discord_id, phone_number").execute()
    target_discord_id = None
    for row in (res.data or []):
        if "".join(filter(str.isdigit, row["phone_number"])) == numero_pulito:
            target_discord_id = row["discord_id"]
            break

    if not target_discord_id:
        return await interaction.followup.send("❌ Numero non registrato o inesistente.", ephemeral=True)

    destinatario = guild.get_member(int(target_discord_id))
    if not destinatario:
        return await interaction.followup.send("❌ L'utente non si trova nel server.", ephemeral=True)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False),
        chiamante: discord.PermissionOverwrite(connect=True, speak=True),
        destinatario: discord.PermissionOverwrite(connect=True, speak=True)
    }

    voice_channel = await guild.create_voice_channel(
        name=f"📞 {chiamante.display_name} ➔ {destinatario.display_name}",
        category=interaction.channel.category if hasattr(interaction.channel, 'category') else None,
        overwrites=overwrites
    )

    task_squillo = asyncio.create_task(riproduci_audio_canale(voice_channel, URL_SQUILLO, loop=True))
    view = RispondiChiamataView(chiamante, destinatario, voice_channel, task_squillo)

    try:
        await destinatario.send(
            f"📱 **CHIAMATA IN ARRIVO — Emerald OS**\n**{chiamante.display_name}** ti sta telefonando.\nHai 2 minuti per rispondere:",
            view=view
        )
    except Exception:
        task_squillo.cancel()
        await voice_channel.delete()
        return await interaction.followup.send("❌ Impossibile inviare il DM all'utente (DM chiusi).", ephemeral=True)

    await interaction.followup.send(f"📞 Chiamata verso **{destinatario.display_name}** in corso!\n🔊 Attendi nel canale: {voice_channel.jump_url}", ephemeral=True)

class RispondiChiamataView(ui.View):
    def __init__(self, chiamante: discord.Member, destinatario: discord.Member, channel: discord.VoiceChannel, task_squillo: asyncio.Task):
        super().__init__(timeout=120)
        self.chiamante = chiamante
        self.destinatario = destinatario
        self.channel = channel
        self.task_squillo = task_squillo
        self.risposto = False

    @ui.button(label="Rispondi", style=discord.ButtonStyle.success, emoji="📞")
    async def rispondi(self, interaction: discord.Interaction, button: ui.Button):
        self.risposto = True
        self.stop()
        if not self.task_squillo.done():
            self.task_squillo.cancel()
        await interaction.response.edit_message(content=f"✅ Chiamata accettata!\n🔊 **Entra nel canale:** {self.channel.jump_url}", view=None)

    @ui.button(label="Rifiuta", style=discord.ButtonStyle.danger, emoji="❌")
    async def rifiuta(self, interaction: discord.Interaction, button: ui.Button):
        self.risposto = False
        self.stop()
        if not self.task_squillo.done():
            self.task_squillo.cancel()
        await interaction.response.edit_message(content="❌ Chiamata rifiutata.", view=None)
        await riproduci_audio_canale(self.channel, URL_RIFIUTO, loop=False)
        try:
            await self.channel.delete()
        except Exception:
            pass

    async def on_timeout(self):
        if not self.risposto:
            if not self.task_squillo.done():
                self.task_squillo.cancel()
            try:
                await self.channel.delete()
            except Exception:
                pass

class AggiungiContattoModal(ui.Modal, title="Nuovo Contatto — Emerald OS"):
    nome = ui.TextInput(label="Nome Contatto", placeholder="Es. Agente Smith", required=True, max_length=50)
    numero = ui.TextInput(label="Numero Telefonico", placeholder="Es. 555123456", required=True, max_length=20)

    def __init__(self, phone_view):
        super().__init__()
        self.phone_view = phone_view

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("contacts").insert({
            "owner_id": str(interaction.user.id),
            "name": self.nome.value.strip(),
            "phone_number": self.numero.value.strip()
        }).execute()
        self.phone_view.aggiorna_selettori()
        await interaction.response.edit_message(view=self.phone_view)
        await interaction.followup.send(f"✅ Contatto **{self.nome.value}** salvato!", ephemeral=True)

class WhatsAppMessageModal(ui.Modal, title="Emerald Chat — Nuovo Messaggio"):
    testo = ui.TextInput(label="Messaggio", placeholder="Scrivi...", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, sender_phone, target_phone, target_name, chat_view):
        super().__init__()
        self.sender_phone = sender_phone
        self.target_phone = target_phone
        self.target_name = target_name
        self.chat_view = chat_view

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("whatsapp_messages").insert({
            "sender_phone": self.sender_phone,
            "receiver_phone": self.target_phone,
            "message": self.testo.value.strip()
        }).execute()
        await self.chat_view.aggiorna_embed(interaction)

class WhatsAppChatView(ui.View):
    def __init__(self, user_phone: str, target_phone: str, target_name: str):
        super().__init__(timeout=300)
        self.user_phone = user_phone
        self.target_phone = target_phone
        self.target_name = target_name

    @ui.button(label="Invia", style=discord.ButtonStyle.success, emoji="💬")
    async def invia(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(WhatsAppMessageModal(self.user_phone, self.target_phone, self.target_name, self))

    @ui.button(label="Aggiorna", style=discord.ButtonStyle.primary, emoji="🔄")
    async def aggiorna(self, interaction: discord.Interaction, button: ui.Button):
        await self.aggiorna_embed(interaction)

    async def aggiorna_embed(self, interaction: discord.Interaction):
        u_clean = "".join(filter(str.isdigit, self.user_phone))
        t_clean = "".join(filter(str.isdigit, self.target_phone))

        res = supabase.table("whatsapp_messages").select("*").order("created_at", desc=False).limit(50).execute()
        chat_lines = []
        for m in (res.data or []):
            s_c = "".join(filter(str.isdigit, m["sender_phone"]))
            r_c = "".join(filter(str.isdigit, m["receiver_phone"]))
            if (s_c == u_clean and r_c == t_clean) or (s_c == t_clean and r_c == u_clean):
                sender = "Tu" if s_c == u_clean else self.target_name
                chat_lines.append(f"**{sender}:** {m['message']}")

        desc = "\n".join(chat_lines[-10:]) if chat_lines else "*Nessun messaggio presente.*"
        embed = discord.Embed(title=f"💬 Chat con {self.target_name} ({self.target_phone})", description=desc, color=EmeraldColor.MAIN)

        if interaction.response.is_done():
            await interaction.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

class CreaPostSocialModal(ui.Modal, title="Nuovo Post"):
    contenuto = ui.TextInput(label="Testo", placeholder="A cosa stai pensando?", style=discord.TextStyle.paragraph, required=True, max_length=280)

    def __init__(self, view, platform_name):
        super().__init__()
        self.social_view = view
        self.platform_name = platform_name

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("social_posts").insert({
            "platform": self.platform_name,
            "author_id": str(interaction.user.id),
            "author_name": interaction.user.display_name,
            "content": self.contenuto.value.strip()
        }).execute()
        await self.social_view.aggiorna_feed(interaction)
        await interaction.followup.send("✅ Post pubblicato!", ephemeral=True)

class SocialMediaView(ui.View):
    def __init__(self, user_id: str, platform_name: str = "EmeraldGram"):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.platform_name = platform_name

    @ui.button(label="EmeraldGram 📸", style=discord.ButtonStyle.secondary)
    async def switch_gram(self, interaction: discord.Interaction, button: ui.Button):
        self.platform_name = "EmeraldGram"
        await self.aggiorna_feed(interaction)

    @ui.button(label="EmeraldBird 🐦", style=discord.ButtonStyle.secondary)
    async def switch_bird(self, interaction: discord.Interaction, button: ui.Button):
        self.platform_name = "EmeraldBird"
        await self.aggiorna_feed(interaction)

    @ui.button(label="Pubblica ✍️", style=discord.ButtonStyle.success)
    async def nuovo(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreaPostSocialModal(self, self.platform_name))

    async def aggiorna_feed(self, interaction: discord.Interaction):
        res = supabase.table("social_posts").select("*").eq("platform", self.platform_name).order("created_at", desc=True).limit(5).execute()
        embed = discord.Embed(title=f"🌐 {self.platform_name}", color=EmeraldColor.BLUE if self.platform_name == "EmeraldBird" else EmeraldColor.MAIN)
        if res.data:
            for p in res.data:
                embed.add_field(name=f"@{p['author_name']}", value=p["content"], inline=False)
        else:
            embed.description = "*Nessun post pubblicato.*"

        if interaction.response.is_done():
            await interaction.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

class EmeraldPhoneView(ui.View):
    def __init__(self, user_id: str, phone_number: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.phone_number = phone_number
        self.aggiorna_selettori()

    def aggiorna_selettori(self):
        self.clear_items()
        res = supabase.table("contacts").select("*").eq("owner_id", self.user_id).execute()
        contacts = res.data or []

        btn_add = ui.Button(label="Aggiungi Contatto", style=discord.ButtonStyle.primary, emoji="➕", row=0)
        btn_add.callback = self.apri_modal_contatto
        self.add_item(btn_add)

        btn_social = ui.Button(label="Social Hub", style=discord.ButtonStyle.secondary, emoji="🌐", row=0)
        btn_social.callback = self.apri_social
        self.add_item(btn_social)

        if contacts:
            opts = [discord.SelectOption(label=c["name"], description=c["phone_number"], value="".join(filter(str.isdigit, c["phone_number"]))) for c in contacts[:25]]
            call_sel = ui.Select(placeholder="📞 Effettua chiamata...", options=opts, row=1)
            call_sel.callback = self.chiama_cb
            self.add_item(call_sel)

            wa_sel = ui.Select(placeholder="💬 Apri chat privata...", options=opts, row=2)
            wa_sel.callback = self.wa_cb
            self.add_item(wa_sel)

    async def apri_modal_contatto(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AggiungiContattoModal(self))

    async def apri_social(self, interaction: discord.Interaction):
        v = SocialMediaView(self.user_id)
        embed = discord.Embed(title="🌐 Social Feed — EmeraldGram", color=EmeraldColor.MAIN)
        res = supabase.table("social_posts").select("*").eq("platform", "EmeraldGram").order("created_at", desc=True).limit(5).execute()
        if res.data:
            for p in res.data:
                embed.add_field(name=f"@{p['author_name']}", value=p["content"], inline=False)
        else:
            embed.description = "*Nessun post.*"
        await interaction.response.send_message(embed=embed, view=v, ephemeral=True)

    async def chiama_cb(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await avvia_chiamata_vocale(interaction, interaction.data["values"][0])

    async def wa_cb(self, interaction: discord.Interaction):
        target_num = interaction.data["values"][0]
        c_res = supabase.table("contacts").select("name").eq("owner_id", self.user_id).ilike("phone_number", f"%{target_num}%").execute()
        t_name = c_res.data[0]["name"] if c_res.data else target_num
        chat_view = WhatsAppChatView(self.phone_number, target_num, t_name)
        await chat_view.aggiorna_embed(interaction)

# ==========================================
# 💳 BANCOMAT & TASTIERINO PIN INTERATTIVO
# ==========================================
class DepositModal(ui.Modal, title="💵 Versamento Contanti"):
    amount = ui.TextInput(label="Somma (€)", placeholder="Es. 500", required=True)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.amount.value.strip())
            if val <= 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Inserisci una somma valida.", ephemeral=True)

        user_data = get_or_create_user(self.user_id, interaction.user.name)
        cash = float(user_data.get("wallet", 0.0))
        if cash < val:
            return await interaction.response.send_message(f"❌ Contanti insufficienti! Disponibili: € {cash:,.2f}", ephemeral=True)

        new_cash = cash - val
        new_bank = float(user_data.get("bank", 0.0)) + val
        supabase.table("users").update({"wallet": new_cash, "bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
        log_transaction(str(self.user_id), "DEPOSITO BANCOMAT", val, "Versamento allo sportello")

        embed = discord.Embed(title="💵 Deposito Effettuato", description=f"Versati: **€ {val:,.2f}**\nNuovo saldo contabile: **€ {new_bank:,.2f}**", color=EmeraldColor.MAIN)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class WithdrawModal(ui.Modal, title="💸 Prelievo Contanti"):
    amount = ui.TextInput(label="Somma (€)", placeholder="Es. 200", required=True)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.amount.value.strip())
            if val <= 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Inserisci una somma valida.", ephemeral=True)

        user_data = get_or_create_user(self.user_id, interaction.user.name)
        bank = float(user_data.get("bank", 0.0))
        if bank < val:
            return await interaction.response.send_message(f"❌ Fondi bancari insufficienti! Saldo: € {bank:,.2f}", ephemeral=True)

        new_bank = bank - val
        new_cash = float(user_data.get("wallet", 0.0)) + val
        supabase.table("users").update({"wallet": new_cash, "bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
        log_transaction(str(self.user_id), "PRELIEVO BANCOMAT", val, "Prelievo sportello automatico")

        embed = discord.Embed(title="💸 Prelievo Eseguito", description=f"Ritirati: **€ {val:,.2f}**\nSaldo residuo banca: **€ {new_bank:,.2f}**", color=EmeraldColor.GOLD)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TransferModal(ui.Modal, title="📲 Bonifico Diretto"):
    amount = ui.TextInput(label="Somma (€)", placeholder="Es. 1000", required=True)
    causale = ui.TextInput(label="Causale", placeholder="Motivo del bonifico...", required=False, max_length=100)

    def __init__(self, sender_id: int, target_member: discord.Member):
        super().__init__()
        self.sender_id = sender_id
        self.target_member = target_member

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.amount.value.strip())
            if val <= 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Somma non valida.", ephemeral=True)

        s_data = get_or_create_user(self.sender_id, interaction.user.name)
        s_bank = float(s_data.get("bank", 0.0))
        if s_bank < val:
            return await interaction.response.send_message("❌ Saldo bancario insufficiente.", ephemeral=True)

        t_data = get_or_create_user(self.target_member.id, self.target_member.name)
        c_testo = self.causale.value.strip() or "Bonifico ordinario"

        supabase.table("users").update({"bank": s_bank - val}).eq("discord_id", str(self.sender_id)).execute()
        supabase.table("users").update({"bank": float(t_data.get("bank", 0.0)) + val}).eq("discord_id", str(self.target_member.id)).execute()

        log_transaction(str(self.sender_id), "BONIFICO IN USCITA", val, f"A {self.target_member.display_name} | {c_testo}")
        log_transaction(str(self.target_member.id), "BONIFICO IN ENTRATA", val, f"Da {interaction.user.display_name} | {c_testo}")

        embed = discord.Embed(title="📲 Bonifico Eseguito", description=f"Inviati **€ {val:,.2f}** a {self.target_member.mention}\nCausale: `{c_testo}`", color=EmeraldColor.MAIN)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TransferUserSelectView(ui.View):
    def __init__(self, sender_id: int):
        super().__init__(timeout=60)
        self.sender_id = sender_id

    @ui.select(cls=ui.UserSelect, placeholder="Seleziona il beneficiario...")
    async def select_user(self, interaction: discord.Interaction, select: ui.UserSelect):
        if interaction.user.id != self.sender_id:
            return
        destinatario = select.values[0]
        if destinatario.id == self.sender_id:
            return await interaction.response.send_message("❌ Non puoi effettuare bonifici verso te stesso.", ephemeral=True)
        await interaction.response.send_modal(TransferModal(self.sender_id, destinatario))

class AtmMenuView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    @ui.button(label="Deposita", style=discord.ButtonStyle.success, emoji="💵", row=0)
    async def btn_dep(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(DepositModal(self.user_id))

    @ui.button(label="Preleva", style=discord.ButtonStyle.danger, emoji="💸", row=0)
    async def btn_with(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(WithdrawModal(self.user_id))

    @ui.button(label="Bonifico", style=discord.ButtonStyle.primary, emoji="📲", row=0)
    async def btn_trf(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Seleziona il conto destinatario:", view=TransferUserSelectView(self.user_id), ephemeral=True)

    @ui.button(label="Estratto Conto", style=discord.ButtonStyle.secondary, emoji="📜", row=1)
    async def btn_his(self, interaction: discord.Interaction, button: ui.Button):
        res = supabase.table("transactions_log").select("*").eq("discord_id", str(self.user_id)).order("created_at", desc=True).limit(8).execute()
        embed = discord.Embed(title="📜 Registro Movimenti Bancari", color=EmeraldColor.BLUE)
        if res.data:
            for tx in res.data:
                embed.add_field(name=f"{tx['type']} — € {tx['amount']:,.2f}", value=f"`{tx['description']}`", inline=False)
        else:
            embed.description = "*Nessuna transazione recente registrata.*"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Termina Sessione", style=discord.ButtonStyle.secondary, emoji="🚪", row=1)
    async def btn_exit(self, interaction: discord.Interaction, button: ui.Button):
        self.stop()
        await interaction.response.edit_message(content="🔒 Sportello Bancomat bloccato. Buona giornata!", embed=None, view=None)

class PinKeypadView(ui.View):
    def __init__(self, user_id: int, user_data: dict, mode: str = "login"):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.user_data = user_data
        self.mode = mode
        self.entered_pin = ""

    async def update_display(self, interaction: discord.Interaction, text: str):
        masked_pin = "*" * len(self.entered_pin) + "_" * (4 - len(self.entered_pin))
        embed = discord.Embed(title="💳 Tastierino Bancomat — Emerald Bank", description=f"{text}\n\n**PIN:** `{masked_pin}`", color=EmeraldColor.BLUE)
        await interaction.response.edit_message(embed=embed, view=self)

    async def handle_digit(self, interaction: discord.Interaction, digit: str):
        if interaction.user.id != self.user_id:
            return
        if len(self.entered_pin) < 4:
            self.entered_pin += digit

        if len(self.entered_pin) == 4:
            if self.mode == "register":
                supabase.table("users").update({"pin": self.entered_pin}).eq("discord_id", str(self.user_id)).execute()
                embed = self._get_dashboard()
                self.stop()
                await interaction.response.edit_message(embed=embed, view=AtmMenuView(self.user_id))
            elif self.mode == "login":
                if self.entered_pin == self.user_data.get("pin"):
                    embed = self._get_dashboard()
                    self.stop()
                    await interaction.response.edit_message(embed=embed, view=AtmMenuView(self.user_id))
                else:
                    self.entered_pin = ""
                    await self.update_display(interaction, "❌ **PIN errato!** Riprova:")
        else:
            await self.update_display(interaction, "Inserisci il tuo codice di sicurezza a 4 cifre:")

    def _get_dashboard(self):
        u = get_or_create_user(self.user_id, "User")
        return discord.Embed(
            title="🏦 Terminale Finanziario — Emerald Bank",
            description=f"• **Conto N°:** `EMR-{self.user_id}`\n• **Saldo Conto:** `€ {float(u.get('bank', 0)):,.2f}`\n• **Contanti:** `€ {float(u.get('wallet', 0)):,.2f}`",
            color=EmeraldColor.MAIN
        )

    @ui.button(label="1", style=discord.ButtonStyle.secondary, row=0)
    async def b1(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "1")
    @ui.button(label="2", style=discord.ButtonStyle.secondary, row=0)
    async def b2(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "2")
    @ui.button(label="3", style=discord.ButtonStyle.secondary, row=0)
    async def b3(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "3")
    @ui.button(label="4", style=discord.ButtonStyle.secondary, row=1)
    async def b4(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "4")
    @ui.button(label="5", style=discord.ButtonStyle.secondary, row=1)
    async def b5(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "5")
    @ui.button(label="6", style=discord.ButtonStyle.secondary, row=1)
    async def b6(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "6")
    @ui.button(label="7", style=discord.ButtonStyle.secondary, row=2)
    async def b7(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "7")
    @ui.button(label="8", style=discord.ButtonStyle.secondary, row=2)
    async def b8(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "8")
    @ui.button(label="9", style=discord.ButtonStyle.secondary, row=2)
    async def b9(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "9")
    @ui.button(label="C", style=discord.ButtonStyle.danger, row=3)
    async def clear(self, i: discord.Interaction, b: ui.Button):
        self.entered_pin = ""
        await self.update_display(i, "PIN resettato:")
    @ui.button(label="0", style=discord.ButtonStyle.secondary, row=3)
    async def b0(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "0")
    @ui.button(label="X", style=discord.ButtonStyle.danger, row=3)
    async def cancel(self, i: discord.Interaction, b: ui.Button):
        self.stop()
        await i.response.edit_message(content="❌ Operazione annullata.", embed=None, view=None)

# ==========================================
# 🚔 CAD FORZE DELL'ORDINE
# ==========================================
async def send_standardized_log(bot_client: discord.Client, log_type: str, name: str, surname: str, birth_date: str, articles: str, penalty_det: str, penalty_pec: str, operators: str, notes: str):
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    sent = []
    for s_id, conf in SERVER_CONFIGS.items():
        ch_id = conf.get(log_type)
        if not ch_id:
            continue
        embed = discord.Embed(
            title=f"🚨 REGISTRO CENTRALE DI POLIZIA — {log_type.upper()}",
            description=(
                f"• **Soggetto:** {name.capitalize()} {surname.upper()}\n"
                f"• **Data di Nascita:** {birth_date}\n"
                f"• **Addebiti / Articoli:** {articles}\n"
                f"• **Pena Detentiva:** {penalty_det}\n"
                f"• **Sanzione Pecuniaria:** {penalty_pec}\n"
                f"• **Data / Ora:** {now_str}\n"
                f"• **Agenti Procedenti:** {operators}\n"
                f"• **Note:** {notes or 'Nessuna'}"
            ),
            color=EmeraldColor.RED
        )
        ch = bot_client.get_channel(ch_id) or await bot_client.fetch_channel(ch_id)
        if ch:
            msg = await ch.send(content=conf.get("role_tag", ""), embed=embed)
            sent.append(msg)
    return sent[0] if sent else None

class FineModal(ui.Modal, title="🚨 Verbalizza Sanzione"):
    articles = ui.TextInput(label="Articoli Violati", placeholder="Es. Art. 142 CdS", required=True)
    penalty_pec = ui.TextInput(label="Ammontare (€)", placeholder="Es. 500", required=True)
    notes = ui.TextInput(label="Note / Dinamica", placeholder="Dettagli infrazione...", required=False, style=discord.TextStyle.paragraph)

    def __init__(self, doc: dict, officer: str, bot_inst: discord.Client):
        super().__init__()
        self.doc, self.officer, self.bot_inst = doc, officer, bot_inst

    async def on_submit(self, interaction: discord.Interaction):
        await send_standardized_log(self.bot_inst, "fines", self.doc.get("name"), self.doc.get("surname"), self.doc.get("birth_date"), self.articles.value, "Nessuna", self.penalty_pec.value, self.officer, self.notes.value)
        await interaction.response.send_message("✅ Sanzione registrata nel CAD centrale!", ephemeral=True)

class ArrestModal(ui.Modal, title="🔒 Registra Provvedimento di Arresto"):
    articles = ui.TextInput(label="Capi d'Accusa", placeholder="Es. Rapina a mano armata", required=True)
    penalty_det = ui.TextInput(label="Detenzione (Mesi)", placeholder="Es. 15 Mesi", required=True)
    penalty_pec = ui.TextInput(label="Cauzione (€)", placeholder="Es. 5000", required=True)
    notes = ui.TextInput(label="Rapporto d'Arresto", placeholder="Dettagli dell'operazione...", required=False, style=discord.TextStyle.paragraph)

    def __init__(self, doc: dict, officer: str, bot_inst: discord.Client):
        super().__init__()
        self.doc, self.officer, self.bot_inst = doc, officer, bot_inst

    async def on_submit(self, interaction: discord.Interaction):
        await send_standardized_log(self.bot_inst, "arrests", self.doc.get("name"), self.doc.get("surname"), self.doc.get("birth_date"), self.articles.value, self.penalty_det.value, self.penalty_pec.value, self.officer, self.notes.value)
        await interaction.response.send_message("✅ Arresto notificato e archiviato nei server di giustizia!", ephemeral=True)

class PoliceCadDetailView(ui.View):
    def __init__(self, doc: dict, officer_id: int, bot_inst: discord.Client):
        super().__init__(timeout=180)
        self.doc, self.officer_id, self.bot_inst = doc, officer_id, bot_inst
        self.target_id = doc.get("discord_id")

    @ui.button(label="Generalità", style=discord.ButtonStyle.primary, row=0)
    async def btn_gen(self, interaction: discord.Interaction, button: ui.Button):
        roles = [r.id for r in interaction.guild.get_member(int(self.target_id)).roles] if interaction.guild.get_member(int(self.target_id)) else []
        embed = build_id_embed(self.doc, int(self.target_id), roles)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Armi", style=discord.ButtonStyle.secondary, row=0)
    async def btn_arm(self, interaction: discord.Interaction, button: ui.Button):
        res = supabase.table("registered_weapons").select("*").eq("discord_id", self.target_id).execute()
        txt = "\n".join([f"• `{w['model']}` — Matricola: `{w['serial_number']}`" for w in (res.data or [])]) or "*Nessuna arma registrata.*"
        embed = discord.Embed(title=f"🔫 Registro Armi: {self.doc.get('name')} {self.doc.get('surname')}", description=txt, color=EmeraldColor.RED)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Veicoli", style=discord.ButtonStyle.secondary, row=0)
    async def btn_veh(self, interaction: discord.Interaction, button: ui.Button):
        res = supabase.table("registered_vehicles").select("*").eq("discord_id", self.target_id).execute()
        txt = "\n".join([f"• `{v['model']}` — Targa: `{v['plate']}`" for v in (res.data or [])]) or "*Nessun veicolo immatricolato.*"
        embed = discord.Embed(title=f"🚘 Parco Veicoli: {self.doc.get('name')} {self.doc.get('surname')}", description=txt, color=EmeraldColor.BLUE)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Emetti Multa", style=discord.ButtonStyle.danger, row=1)
    async def btn_multa(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(FineModal(self.doc, interaction.user.display_name, self.bot_inst))

    @ui.button(label="Emetti Arresto", style=discord.ButtonStyle.danger, row=1)
    async def btn_arresto(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ArrestModal(self.doc, interaction.user.display_name, self.bot_inst))

class CitizenSelectMenu(ui.Select):
    def __init__(self, citizens: list, officer_id: int, bot_inst: discord.Client):
        options = [discord.SelectOption(label=f"{c.get('name')} {c.get('surname')}", value=c.get("discord_id"), description=f"Doc: {c.get('doc_number')}") for c in citizens[:25]]
        super().__init__(placeholder="Seleziona cittadino dall'elenco...", options=options)
        self.citizens, self.officer_id, self.bot_inst = citizens, officer_id, bot_inst

    async def callback(self, interaction: discord.Interaction):
        selected = next((c for c in self.citizens if c["discord_id"] == self.values[0]), None)
        if selected:
            v = PoliceCadDetailView(selected, self.officer_id, self.bot_inst)
            embed = discord.Embed(title=f"🚔 Scheda Soggetto: {selected.get('name')} {selected.get('surname')}", description="Consulta i dati o verbalizza atti giudiziari:", color=EmeraldColor.BLUE)
            await interaction.response.edit_message(embed=embed, view=v)

class PoliceCadSelectView(ui.View):
    def __init__(self, citizens: list, officer_id: int, bot_inst: discord.Client):
        super().__init__(timeout=120)
        self.add_item(CitizenSelectMenu(citizens, officer_id, bot_inst))

# ==========================================
# 📦 DEPOSITI FAZIONE (SOLDI E OGGETTI)
# ==========================================
class DepositCashModal(ui.Modal, title="Versa Denaro in Fazione"):
    amount = ui.TextInput(label="Somma (€)", placeholder="Es. 2500", required=True)

    def __init__(self, fazione: str):
        super().__init__()
        self.fazione = fazione

    async def on_submit(self, interaction: discord.Interaction):
        try:
            valore = float(self.amount.value)
            if valore <= 0: raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Somma non valida.", ephemeral=True)

        user_id = str(interaction.user.id)
        u_res = supabase.table("users").select("wallet").eq("discord_id", user_id).execute()
        if not u_res.data or u_res.data[0]["wallet"] < valore:
            return await interaction.response.send_message("❌ Non possiedi contanti sufficienti.", ephemeral=True)

        supabase.table("users").update({"wallet": u_res.data[0]["wallet"] - valore}).eq("discord_id", user_id).execute()
        v_res = supabase.table("faction_vaults").select("cash_balance").ilike("faction_name", self.fazione).execute()
        nuovo = (v_res.data[0]["cash_balance"] if v_res.data else 0.0) + valore
        supabase.table("faction_vaults").upsert({"faction_name": self.fazione, "cash_balance": nuovo}, on_conflict="faction_name").execute()

        await interaction.response.send_message(f"✅ Versati **€ {valore:,.2f}** nella cassa della fazione **{self.fazione}**.", ephemeral=True)

class WithdrawCashModal(ui.Modal, title="Preleva Denaro dalla Fazione"):
    amount = ui.TextInput(label="Somma (€)", placeholder="Es. 1000", required=True)

    def __init__(self, fazione: str):
        super().__init__()
        self.fazione = fazione

    async def on_submit(self, interaction: discord.Interaction):
        try:
            valore = float(self.amount.value)
            if valore <= 0: raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Somma non valida.", ephemeral=True)

        v_res = supabase.table("faction_vaults").select("cash_balance").ilike("faction_name", self.fazione).execute()
        disponibili = v_res.data[0]["cash_balance"] if v_res.data else 0.0
        if disponibili < valore:
            return await interaction.response.send_message("❌ La fazione non ha fondi sufficienti.", ephemeral=True)

        user_id = str(interaction.user.id)
        supabase.table("faction_vaults").update({"cash_balance": disponibili - valore}).ilike("faction_name", self.fazione).execute()
        u_res = supabase.table("users").select("wallet").eq("discord_id", user_id).execute()
        supabase.table("users").update({"wallet": (u_res.data[0]["wallet"] if u_res.data else 0.0) + valore}).eq("discord_id", user_id).execute()

        await interaction.response.send_message(f"✅ Ritirati **€ {valore:,.2f}** dalla cassa di **{self.fazione}**.", ephemeral=True)

class DepositItemModal(ui.Modal, title="Deposita Oggetto in Fazione"):
    item_name = ui.TextInput(label="Nome Oggetto", placeholder="Es. Cemento o Pistola", required=True)
    quantity = ui.TextInput(label="Quantità", placeholder="1", default="1", required=True)

    def __init__(self, fazione: str):
        super().__init__()
        self.fazione = fazione

    async def on_submit(self, interaction: discord.Interaction):
        try:
            q = int(self.quantity.value)
            if q <= 0: raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Quantità non valida.", ephemeral=True)

        user_id = str(interaction.user.id)
        inv = supabase.table("inventory").select("*").eq("discord_id", user_id).execute()
        disponibili = [r["item_name"] for r in (inv.data or [])]
        match = difflib.get_close_matches(self.item_name.value.strip(), disponibili, n=1, cutoff=0.4)

        if not match:
            return await interaction.response.send_message("❌ Nessun oggetto corrispondente trovato nel tuo inventario.", ephemeral=True)

        item = next(r for r in inv.data if r["item_name"] == match[0])
        if item["quantity"] < q:
            return await interaction.response.send_message(f"❌ Ne possiedi solo {item['quantity']}x.", ephemeral=True)

        if item["quantity"] == q:
            supabase.table("inventory").delete().eq("id", item["id"]).execute()
        else:
            supabase.table("inventory").update({"quantity": item["quantity"] - q}).eq("id", item["id"]).execute()

        f_inv = supabase.table("faction_inventory").select("*").ilike("faction_name", self.fazione).ilike("item_name", item["item_name"]).execute()
        if f_inv.data:
            supabase.table("faction_inventory").update({"quantity": f_inv.data[0]["quantity"] + q}).eq("id", f_inv.data[0]["id"]).execute()
        else:
            supabase.table("faction_inventory").insert({"faction_name": self.fazione, "item_name": item["item_name"], "category": item["category"], "weight": item["weight"], "quantity": q}).execute()

        await interaction.response.send_message(f"✅ Depositati **{q}x {item['item_name']}** nella fazione **{self.fazione}**.", ephemeral=True)

class WithdrawItemModal(ui.Modal, title="Preleva Oggetto da Fazione"):
    item_name = ui.TextInput(label="Nome Oggetto", placeholder="Es. Cemento", required=True)
    quantity = ui.TextInput(label="Quantità", placeholder="1", default="1", required=True)

    def __init__(self, fazione: str):
        super().__init__()
        self.fazione = fazione

    async def on_submit(self, interaction: discord.Interaction):
        try:
            q = int(self.quantity.value)
            if q <= 0: raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Quantità non valida.", ephemeral=True)

        f_inv = supabase.table("faction_inventory").select("*").ilike("faction_name", self.fazione).execute()
        disponibili = [r["item_name"] for r in (f_inv.data or [])]
        match = difflib.get_close_matches(self.item_name.value.strip(), disponibili, n=1, cutoff=0.4)

        if not match:
            return await interaction.response.send_message("❌ Oggetto assente nel deposito della fazione.", ephemeral=True)

        item = next(r for r in f_inv.data if r["item_name"] == match[0])
        if item["quantity"] < q:
            return await interaction.response.send_message(f"❌ Nel deposito sono presenti solo {item['quantity']}x.", ephemeral=True)

        if item["quantity"] == q:
            supabase.table("faction_inventory").delete().eq("id", item["id"]).execute()
        else:
            supabase.table("faction_inventory").update({"quantity": item["quantity"] - q}).eq("id", item["id"]).execute()

        user_id = str(interaction.user.id)
        u_inv = supabase.table("inventory").select("*").eq("discord_id", user_id).ilike("item_name", item["item_name"]).execute()
        if u_inv.data:
            supabase.table("inventory").update({"quantity": u_inv.data[0]["quantity"] + q}).eq("id", u_inv.data[0]["id"]).execute()
        else:
            supabase.table("inventory").insert({"discord_id": user_id, "item_name": item["item_name"], "category": item["category"], "weight": item["weight"], "quantity": q}).execute()

        await interaction.response.send_message(f"✅ Prelevati **{q}x {item['item_name']}** dal deposito di **{self.fazione}**.", ephemeral=True)

class FactionVaultView(ui.View):
    def __init__(self, fazione: str):
        super().__init__(timeout=None)
        self.fazione = fazione

    @ui.button(label="Deposita Soldi", style=discord.ButtonStyle.green, emoji="💰", row=0)
    async def dep_cash(self, i: discord.Interaction, b: ui.Button): await i.response.send_modal(DepositCashModal(self.fazione))
    @ui.button(label="Preleva Soldi", style=discord.ButtonStyle.red, emoji="💸", row=0)
    async def with_cash(self, i: discord.Interaction, b: ui.Button): await i.response.send_modal(WithdrawCashModal(self.fazione))
    @ui.button(label="Deposita Item", style=discord.ButtonStyle.blurple, emoji="📦", row=1)
    async def dep_it(self, i: discord.Interaction, b: ui.Button): await i.response.send_modal(DepositItemModal(self.fazione))
    @ui.button(label="Preleva Item", style=discord.ButtonStyle.blurple, emoji="📤", row=1)
    async def with_it(self, i: discord.Interaction, b: ui.Button): await i.response.send_modal(WithdrawItemModal(self.fazione))

# ==========================================
# 🎒 INVENTARIO CON MODAL QUANTITÀ
# ==========================================
class QuantityModal(ui.Modal, title="Quantità da Usare"):
    qta = ui.TextInput(label="Quantità", placeholder="1", default="1", min_length=1, max_length=5)

    def __init__(self, user_id: int, inv_item: dict):
        super().__init__()
        self.user_id = user_id
        self.inv_item = inv_item

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.qta.value)
            if qty < 1: raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Inserisci una cifra valida.", ephemeral=True)

        disp = self.inv_item.get("quantity", 1)
        if qty > disp:
            return await interaction.response.send_message(f"❌ Quantità insufficiente. Posseduti: {disp}x.", ephemeral=True)

        name = self.inv_item.get("item_name")
        cat = self.inv_item.get("category")

        if cat == "zaino":
            u = get_or_create_user(self.user_id, interaction.user.name)
            new_max = float(u.get("max_weight", 10.0)) + (5.0 * qty)
            supabase.table("users").update({"max_weight": new_max}).eq("discord_id", str(self.user_id)).execute()
            msg = f"🎒 Zaino equipaggiato! Capienza aumentata di **+{5.0 * qty} kg** (Totale: `{new_max} kg`)."
        else:
            msg = f"✨ Hai utilizzato **{name}** (x{qty})."

        if disp > qty:
            supabase.table("inventory").update({"quantity": disp - qty}).eq("id", self.inv_item["id"]).execute()
        else:
            supabase.table("inventory").delete().eq("id", self.inv_item["id"]).execute()

        await interaction.response.send_message(f"✅ {msg}", ephemeral=True)

class InventoryUseView(ui.View):
    def __init__(self, user_id: int, items: list):
        super().__init__(timeout=120)
        self.user_id = user_id
        options = [discord.SelectOption(label=f"{i['item_name']} (x{i.get('quantity', 1)})", value=str(i["id"]), description=f"Cat: {i.get('category')} | Peso: {i.get('weight', 0.1)}kg") for i in items[:25]]
        if options:
            sel = ui.Select(placeholder="Seleziona oggetto da consumare o equipaggiare...", options=options)
            sel.callback = self.cb
            self.add_item(sel)

    async def cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return
        res = supabase.table("inventory").select("*").eq("id", int(interaction.data["values"][0])).execute()
        if res.data:
            await interaction.response.send_modal(QuantityModal(self.user_id, res.data[0]))

# ==========================================
# 🏥 DISTRIBUTORE BRACCIALETTI OSPEDALIERI
# ==========================================
class DistributoreModal(ui.Modal, title="Distributore Emergenza Sanitaria"):
    doc = ui.TextInput(label="Doc d'Identità / Codice Fiscale", placeholder="Es. DOC-12345 o CF", required=True, min_length=5, max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        u_res = supabase.table("users").select("*").eq("discord_id", user_id).execute()
        if not u_res.data:
            return await interaction.response.send_message("❌ Non risulti registrato nei terminali cittadini.", ephemeral=True)

        role = interaction.guild.get_role(RUOLO_BRACCIALETTO_ID)
        if role and role in interaction.user.roles:
            return await interaction.response.send_message("⚠️ Indossi già il braccialetto medico!", ephemeral=True)

        if role:
            try:
                await interaction.user.add_roles(role, reason="Ritiro braccialetto medico ospedaliero")
            except Exception:
                pass

        supabase.table("users").update({"documento_identita": self.doc.value.strip().upper(), "braccialetto_ritirato": True}).eq("discord_id", user_id).execute()
        log_transaction(user_id, "BRACCIALETTO SOS", 0, "Ritiro braccialetto d'emergenza")

        embed = discord.Embed(title="🏥 Dispositivo Medico Erogato", description=f"{interaction.user.mention} ha ritirato il **Braccialetto Salvavita SOS**.", color=EmeraldColor.MAIN)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class DistributorePannelloView(ui.View):
    def __init__(self, supabase_client=None):
        super().__init__(timeout=None)

    @ui.button(label="Ritira Braccialetto Medico", style=discord.ButtonStyle.success, emoji="🏷️", custom_id="emerald_distributore_braccialetto")
    async def btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(DistributoreModal())

class WelcomeButtonsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="Sblocco Canali", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1500844219424706581"))
        self.add_item(ui.Button(label="Regolamento Cittadino", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1252225171553652787"))
        self.add_item(ui.Button(label="Guide e Comandi", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1374421195163963553"))
        self.add_item(ui.Button(label="Canali Istituzionali", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1519623994591019189"))
        self.add_item(ui.Button(label="Background Personaggio", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1252225106785337355"))
        self.add_item(ui.Button(label="Richiesta Whitelist", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1503750254028390580"))

# ==========================================
# 🚀 COMANDI SLASH (TUTTI I COMANDI RICHIESTI)
# ==========================================
@bot.tree.command(name="wipe", description="Effettua il wipe completo di un utente")
@app_commands.describe(utente="L'utente da resettare")
async def wipe_user(interaction: discord.Interaction, utente: discord.User):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    t_id = str(utente.id)

    supabase.table("users").update({"wallet": 500.0, "bank": 1500.0, "braccialetto_ritirato": False}).eq("discord_id", t_id).execute()
    for tbl in ["documents", "inventory", "driver_licenses", "gun_licenses", "registered_weapons", "registered_vehicles", "registered_properties", "user_phones", "darkweb_users"]:
        supabase.table(tbl).delete().eq("discord_id", t_id).execute()

    embed = discord.Embed(title="🧹 Wipe Eseguito con Successo", description=f"Profilo e averi di {utente.mention} cancellati dal database centrale.", color=EmeraldColor.MAIN)
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="staff_item_deposito", description="Aggiunge o rimuove item dal deposito fazione (Staff).")
@app_commands.choices(azione=[app_commands.Choice(name="Aggiungi", value="aggiungi"), app_commands.Choice(name="Rimuovi", value="rimuovi")])
@app_commands.autocomplete(fazione=fazione_autocomplete, oggetto=oggetto_custom_autocomplete)
async def staff_item_deposito(interaction: discord.Interaction, fazione: str, azione: app_commands.Choice[str], oggetto: str, quantita: int):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    if quantita <= 0:
        return await interaction.response.send_message("❌ Quantità non valida.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    if azione.value == "aggiungi":
        it = supabase.table("custom_items").select("*").eq("name", oggetto).execute()
        if not it.data:
            return await interaction.followup.send("❌ Oggetto non esistente nei cataloghi.")
        cat, w = it.data[0].get("category", "Generale"), it.data[0].get("weight", 0.0)

        inv = supabase.table("faction_inventory").select("*").eq("faction_name", fazione).eq("item_name", oggetto).execute()
        if inv.data:
            supabase.table("faction_inventory").update({"quantity": inv.data[0]["quantity"] + quantita}).eq("id", inv.data[0]["id"]).execute()
        else:
            supabase.table("faction_inventory").insert({"faction_name": fazione, "item_name": oggetto, "category": cat, "weight": w, "quantity": quantita}).execute()
        await interaction.followup.send(f"✅ Inseriti **{quantita}x {oggetto}** nel deposito **{fazione}**.")
    else:
        inv = supabase.table("faction_inventory").select("*").eq("faction_name", fazione).eq("item_name", oggetto).execute()
        if not inv.data or inv.data[0]["quantity"] < quantita:
            return await interaction.followup.send("❌ Quantità insufficiente nel deposito.")
        nuova = inv.data[0]["quantity"] - quantita
        if nuova > 0:
            supabase.table("faction_inventory").update({"quantity": nuova}).eq("id", inv.data[0]["id"]).execute()
        else:
            supabase.table("faction_inventory").delete().eq("id", inv.data[0]["id"]).execute()
        await interaction.followup.send(f"🗑️ Rimossi **{quantita}x {oggetto}** da **{fazione}**.")

@bot.tree.command(name="staff_soldi_deposito", description="Aggiunge o rimuove denaro dal deposito fazione (Staff).")
@app_commands.choices(azione=[app_commands.Choice(name="Aggiungi", value="aggiungi"), app_commands.Choice(name="Rimuovi", value="rimuovi")])
@app_commands.autocomplete(fazione=fazione_autocomplete)
async def staff_soldi_deposito(interaction: discord.Interaction, fazione: str, azione: app_commands.Choice[str], importo: float):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    if importo <= 0:
        return await interaction.response.send_message("❌ Somma non valida.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    v_res = supabase.table("faction_vaults").select("cash_balance").ilike("faction_name", fazione).execute()
    attuale = v_res.data[0]["cash_balance"] if v_res.data else 0.0

    if azione.value == "aggiungi":
        nuovo = attuale + importo
    else:
        if attuale < importo:
            return await interaction.followup.send(f"❌ Fondi fazione insufficienti (Saldo: € {attuale:,.2f}).")
        nuovo = attuale - importo

    supabase.table("faction_vaults").upsert({"faction_name": fazione, "cash_balance": nuovo}, on_conflict="faction_name").execute()
    supabase.table("factions").update({"wallet": nuovo}).eq("name", fazione).execute()
    await interaction.followup.send(f"💵 Bilancio fazione **{fazione}** aggiornato a **€ {nuovo:,.2f}**.")

@bot.tree.command(name="avvia_minatore", description="Inizia la sessione di raccolta in miniera")
@app_commands.describe(materiale="Materiale da estrarre", foto="Foto prova di presenza sul posto")
@app_commands.choices(materiale=[app_commands.Choice(name=f"{v['emoji']} {k} ({v['time_min']} min - {v['qty_kg']} kg)", value=k) for k, v in MATERIALS_DATA.items()])
async def avvia_minatore(interaction: discord.Interaction, materiale: app_commands.Choice[str], foto: discord.Attachment):
    await interaction.response.defer()
    u_id = str(interaction.user.id)

    if supabase.table("minatori_attivi").select("discord_id").eq("discord_id", u_id).execute().data:
        return await interaction.followup.send("⚠️ Hai già un'estrazione in corso! Usa `/fine_minatore`.", ephemeral=True)

    if not foto.content_type.startswith("image/"):
        return await interaction.followup.send("❌ Carica un file immagine valido come prova.", ephemeral=True)

    inv = supabase.table("inventory").select("item_name").eq("discord_id", u_id).ilike("item_name", "%Piccone%").gt("quantity", 0).execute()
    if not inv.data:
        return await interaction.followup.send("❌ Devi avere un **Piccone** nell'inventario per minare!", ephemeral=True)

    info = MATERIALS_DATA[materiale.value]
    full_name = f"{info['emoji']} | {materiale.value}"
    now_utc = datetime.now(timezone.utc)

    supabase.table("minatori_attivi").insert({"discord_id": u_id, "created_at": now_utc.isoformat(), "target_material": full_name}).execute()

    embed = discord.Embed(title="⛏️ ESTRAZIONE AVVIATA", description=f"{interaction.user.mention} ha iniziato a estrarre **{full_name}**.", color=EmeraldColor.GOLD)
    embed.add_field(name="Resa Stimata", value=f"`{info['qty_kg']} kg`", inline=True)
    embed.add_field(name="Tempo Richiesto", value=f"`{info['time_min']} minuti`", inline=True)
    embed.add_field(name="Strumento", value=f"`{inv.data[0]['item_name']}`", inline=False)
    embed.set_thumbnail(url=foto.url)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="fine_minatore", description="Concludi il turno in miniera e raccogli il minerale estratto")
async def fine_minatore(interaction: discord.Interaction):
    await interaction.response.defer()
    u_id = str(interaction.user.id)
    session = supabase.table("minatori_attivi").select("*").eq("discord_id", u_id).execute()
    if not session.data:
        return await interaction.followup.send("❌ Nessuna estrazione attiva trovata.", ephemeral=True)

    data = session.data[0]
    start = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    mat_raw = data["target_material"].split("|")[-1].strip()
    info = MATERIALS_DATA[mat_raw]

    minuti_trascorsi = int((datetime.now(timezone.utc) - start).total_seconds() // 60)
    if minuti_trascorsi < info["time_min"]:
        return await interaction.followup.send(f"⚠️ Estrazione non completata. Mancano ancora **{info['time_min'] - minuti_trascorsi} minuti**.", ephemeral=True)

    supabase.table("minatori_attivi").delete().eq("discord_id", u_id).execute()
    inv = supabase.table("inventory").select("id, quantity").eq("discord_id", u_id).eq("item_name", data["target_material"]).execute()
    if inv.data:
        supabase.table("inventory").update({"quantity": inv.data[0]["quantity"] + info["qty_kg"]}).eq("id", inv.data[0]["id"]).execute()
    else:
        supabase.table("inventory").insert({"discord_id": u_id, "item_name": data["target_material"], "category": "Materiale", "weight": 1.0, "quantity": info["qty_kg"]}).execute()

    embed = discord.Embed(title="⛏️ RACCOLTA COMPLETATA", description=f"Hai estratto **{info['qty_kg']} kg** di **{data['target_material']}**!", color=EmeraldColor.MAIN)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="trasferisci_veicolo", description="Trasferisci un veicolo immatricolato ad un altro cittadino.")
@app_commands.autocomplete(veicolo=veicoli_trasferimento_autocomplete)
async def trasferisci_veicolo(interaction: discord.Interaction, veicolo: str, nuovo_proprietario: discord.Member):
    if interaction.user.id == nuovo_proprietario.id or nuovo_proprietario.bot:
        return await interaction.response.send_message("❌ Destinatario non valido.", ephemeral=True)

    v = supabase.table("registered_vehicles").select("*").eq("discord_id", str(interaction.user.id)).eq("plate", veicolo).execute()
    if not v.data:
        return await interaction.response.send_message("❌ Veicolo non tuo.", ephemeral=True)

    if supabase.table("seized_vehicles").select("id").eq("plate", veicolo).eq("status", "Sequestrato").execute().data:
        return await interaction.response.send_message("❌ Impossibile trasferire: mezzo sotto sequestro!", ephemeral=True)

    supabase.table("registered_vehicles").update({"discord_id": str(nuovo_proprietario.id)}).eq("plate", veicolo).execute()
    embed = discord.Embed(title="📑 PASSAGGIO DI PROPRIETÀ ESEGUITO", color=EmeraldColor.MAIN)
    embed.add_field(name="Mezzo", value=f"**{v.data[0].get('model')}** (`{veicolo}`)", inline=False)
    embed.add_field(name="Cedente", value=interaction.user.mention, inline=True)
    embed.add_field(name="Nuovo Intestatario", value=nuovo_proprietario.mention, inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dai_oggetto", description="Aggiunge un oggetto nell'inventario di un utente (Staff).")
@app_commands.autocomplete(nome_oggetto=oggetto_custom_autocomplete)
async def dai_oggetto(interaction: discord.Interaction, utente: discord.Member, nome_oggetto: str, quantita: int):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    if quantita <= 0:
        return await interaction.response.send_message("❌ Quantità non valida.", ephemeral=True)

    it = supabase.table("custom_items").select("*").eq("name", nome_oggetto).execute()
    if not it.data:
        return await interaction.response.send_message("❌ Oggetto inesistente nel database.", ephemeral=True)

    item = it.data[0]
    inv = supabase.table("inventory").select("*").eq("discord_id", str(utente.id)).eq("item_name", nome_oggetto).execute()
    if inv.data:
        supabase.table("inventory").update({"quantity": inv.data[0]["quantity"] + quantita}).eq("id", inv.data[0]["id"]).execute()
    else:
        supabase.table("inventory").insert({"discord_id": str(utente.id), "item_name": nome_oggetto, "category": item.get("category", "Generale"), "weight": item.get("weight", 0.1), "quantity": quantita}).execute()

    await interaction.response.send_message(f"✅ Dati **{quantita}x {nome_oggetto}** a {utente.mention}.", ephemeral=True)

@bot.tree.command(name="rimuovi_oggetto", description="Rimuove un oggetto dall'inventario di un cittadino (Staff).")
@app_commands.autocomplete(nome_oggetto=target_user_inventory_autocomplete)
async def rimuovi_oggetto(interaction: discord.Interaction, utente: discord.Member, nome_oggetto: str, quantita: int):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    inv = supabase.table("inventory").select("*").eq("discord_id", str(utente.id)).eq("item_name", nome_oggetto).execute()
    if not inv.data:
        return await interaction.response.send_message("❌ L'utente non possiede l'oggetto.", ephemeral=True)

    disp = inv.data[0]["quantity"]
    if quantita >= disp:
        supabase.table("inventory").delete().eq("id", inv.data[0]["id"]).execute()
    else:
        supabase.table("inventory").update({"quantity": disp - quantita}).eq("id", inv.data[0]["id"]).execute()

    await interaction.response.send_message(f"🗑️ Rimossi **{min(quantita, disp)}x {nome_oggetto}** a {utente.mention}.", ephemeral=True)

@bot.tree.command(name="elimina_veicolo", description="Rimuove definitivamente un veicolo dai registri (Staff).")
@app_commands.autocomplete(veicolo=elimina_veicolo_autocomplete)
async def elimina_veicolo(interaction: discord.Interaction, utente: discord.Member, veicolo: str):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    supabase.table("registered_vehicles").delete().eq("discord_id", str(utente.id)).eq("plate", veicolo).execute()
    supabase.table("seized_vehicles").delete().eq("plate", veicolo).execute()
    await interaction.response.send_message(f"🗑️ Targa `{veicolo}` rimossa dal database centrale.", ephemeral=True)

@bot.tree.command(name="staff_info", description="[STAFF] Scheda generale cittadino.")
@app_commands.checks.has_role(RUOLO_STAFF_ID)
async def staff_info(interaction: discord.Interaction, target: discord.User):
    await interaction.response.defer(ephemeral=True)
    doc = supabase.table("documents").select("*").eq("discord_id", str(target.id)).execute()
    if not doc.data:
        return await interaction.followup.send("❌ Nessun profilo anagrafico registrato per questo cittadino.", ephemeral=True)

    d = doc.data[0]
    eco = supabase.table("users").select("wallet, bank").eq("discord_id", str(target.id)).execute()
    cassa, banca = (eco.data[0]["wallet"], eco.data[0]["bank"]) if eco.data else (0, 0)

    embed = discord.Embed(title=f"🛠️ Emerald Staff Dossier — {d.get('name')} {d.get('surname')}", color=EmeraldColor.NAVY)
    embed.add_field(name="Dati", value=f"CF: `{d.get('cf')}` | Doc: `{d.get('doc_number')}`\nNascita: {d.get('birth_date')} a {d.get('birth_place')}", inline=False)
    embed.add_field(name="Economia", value=f"Portafoglio: € {cassa:,.2f} | Banca: € {banca:,.2f}", inline=False)
    if d.get("photo_url"): embed.set_thumbnail(url=d["photo_url"])
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="gestisci_soldi", description="Aggiunge o toglie denaro ad un cittadino (Staff Economia).")
@app_commands.choices(
    azione=[app_commands.Choice(name="Aggiungi", value="add"), app_commands.Choice(name="Rimuovi", value="remove")],
    tipo_conto=[app_commands.Choice(name="Contanti", value="wallet"), app_commands.Choice(name="Banca", value="bank")]
)
async def gestisci_soldi(interaction: discord.Interaction, utente: discord.Member, azione: str, tipo_conto: str, importo: float):
    if not any(r.id == RUOLO_ECONOMIA_STAFF_ID for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Ruolo gestione economia assente.", ephemeral=True)
    if importo <= 0:
        return await interaction.response.send_message("❌ Cifra non valida.", ephemeral=True)

    u = supabase.table("users").select("wallet, bank").eq("discord_id", str(utente.id)).execute()
    if not u.data:
        return await interaction.response.send_message("❌ Utente non registrato.", ephemeral=True)

    curr = u.data[0][tipo_conto]
    nuovo = curr + importo if azione == "add" else curr - importo
    if nuovo < 0:
        return await interaction.response.send_message("❌ L'importo porterebbe il conto in negativo.", ephemeral=True)

    supabase.table("users").update({tipo_conto: nuovo}).eq("discord_id", str(utente.id)).execute()
    await interaction.response.send_message(f"✅ Saldo `{tipo_conto}` di {utente.mention} aggiornato a **€ {nuovo:,.2f}**.", ephemeral=True)

@bot.tree.command(name="update_item", description="Modifica parametri di un oggetto nel catalogo")
@app_commands.autocomplete(item=item_id_autocomplete)
async def update_item(interaction: discord.Interaction, item: str, name: str = None, weight: float = None, price: float = None):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Accesso negato.", ephemeral=True)
    updates = {}
    if name: updates["name"] = name
    if weight is not None: updates["weight"] = weight
    if price is not None: updates["price"] = price

    if not updates:
        return await interaction.response.send_message("⚠️ Nessun parametro indicato.", ephemeral=True)
    supabase.table("custom_items").update(updates).eq("id", int(item)).execute()
    await interaction.response.send_message("✅ Oggetto modificato nel database Emerald.", ephemeral=True)

@bot.tree.command(name="delete_item", description="Elimina un oggetto dal catalogo")
@app_commands.autocomplete(item=item_id_autocomplete)
async def delete_item(interaction: discord.Interaction, item: str, conferma: bool = False):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Accesso negato.", ephemeral=True)
    if not conferma:
        return await interaction.response.send_message("⚠️ Imposta `conferma: True` per eliminare definitivamente.", ephemeral=True)
    supabase.table("custom_items").delete().eq("id", int(item)).execute()
    await interaction.response.send_message("🗑️ Oggetto rimosso.", ephemeral=True)

@bot.tree.command(name="paga", description="Trasferisci contanti ad un cittadino vicino.")
async def paga(interaction: discord.Interaction, destinatario: discord.Member, importo: float):
    if destinatario.id == interaction.user.id or destinatario.bot or importo <= 0:
        return await interaction.response.send_message("❌ Operazione non consentita.", ephemeral=True)

    s_id, d_id = str(interaction.user.id), str(destinatario.id)
    u_s = supabase.table("users").select("wallet").eq("discord_id", s_id).execute()
    if not u_s.data or u_s.data[0]["wallet"] < importo:
        return await interaction.response.send_message("❌ Contanti insufficienti nel portafoglio.", ephemeral=True)

    u_d = supabase.table("users").select("wallet").eq("discord_id", d_id).execute()
    if not u_d.data:
        return await interaction.response.send_message("❌ Destinatario non censito nel database.", ephemeral=True)

    supabase.table("users").update({"wallet": u_s.data[0]["wallet"] - importo}).eq("discord_id", s_id).execute()
    supabase.table("users").update({"wallet": u_d.data[0]["wallet"] + importo}).eq("discord_id", d_id).execute()

    await interaction.response.send_message(f"💸 {interaction.user.mention} ha consegnato **€ {importo:,.2f}** a {destinatario.mention}.")

@bot.tree.command(name="passa", description="Passa un tuo oggetto a un altro cittadino.")
@app_commands.autocomplete(nome_oggetto=sender_inventory_autocomplete)
async def passa(interaction: discord.Interaction, destinatario: discord.Member, nome_oggetto: str, quantita: int = 1):
    if destinatario.id == interaction.user.id or destinatario.bot or quantita <= 0:
        return await interaction.response.send_message("❌ Operazione non valida.", ephemeral=True)

    s_id, d_id = str(interaction.user.id), str(destinatario.id)
    item_res = supabase.table("inventory").select("*").eq("discord_id", s_id).eq("item_name", nome_oggetto).execute()
    if not item_res.data or item_res.data[0]["quantity"] < quantita:
        return await interaction.response.send_message("❌ Non possiedi tale quantità.", ephemeral=True)

    item = item_res.data[0]
    if item["quantity"] == quantita:
        supabase.table("inventory").delete().eq("id", item["id"]).execute()
    else:
        supabase.table("inventory").update({"quantity": item["quantity"] - quantita}).eq("id", item["id"]).execute()

    d_inv = supabase.table("inventory").select("*").eq("discord_id", d_id).eq("item_name", nome_oggetto).execute()
    if d_inv.data:
        supabase.table("inventory").update({"quantity": d_inv.data[0]["quantity"] + quantita}).eq("id", d_inv.data[0]["id"]).execute()
    else:
        supabase.table("inventory").insert({"discord_id": d_id, "item_name": nome_oggetto, "category": item["category"], "weight": item["weight"], "quantity": quantita}).execute()

    await interaction.response.send_message(f"📦 Hai passato **{quantita}x {nome_oggetto}** a {destinatario.mention}.")

@bot.command(name="elimina")
async def delete_message(ctx):
    if not any(r.id == RUOLO_STAFF_ID for r in ctx.author.roles):
        return
    if not ctx.message.reference:
        return await ctx.send("Rispondi al messaggio da eliminare col comando `!elimina`.", delete_after=4)

    target_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    content = target_msg.content or "[Media/Vuoto]"
    author = target_msg.author
    await target_msg.delete()
    await ctx.message.delete()

    log_ch = ctx.guild.get_channel(ID_CANALE_LOGS)
    if log_ch:
        emb = discord.Embed(title="🗑️ Messaggio Rimosso da Moderatore", color=EmeraldColor.RED)
        emb.add_field(name="Autore", value=f"{author.mention} (`{author.id}`)")
        emb.add_field(name="Staffer", value=f"{ctx.author.mention}")
        emb.add_field(name="Contenuto", value=f"```{content[:900]}```", inline=False)
        await log_ch.send(embed=emb)

@bot.tree.command(name="inizia-turno", description="Inizia il turno lavorativo per maturare lo stipendio.")
async def inizia_turno(interaction: discord.Interaction):
    if supabase.table("turni_attivi").select("*").eq("user_id", str(interaction.user.id)).execute().data:
        return await interaction.response.send_message("❌ Hai già un turno attivo!", ephemeral=True)
    ruoli = [r for r in interaction.user.roles if r.name != "@everyone"]
    if not ruoli:
        return await interaction.response.send_message("❌ Non possiedi ruoli lavorativi.", ephemeral=True)
    await interaction.response.send_message("Seleziona la tua mansione:", view=SelezioneRuoloView(ruoli), ephemeral=True)

@bot.tree.command(name="fine-turno", description="Concludi il tuo turno lavorativo.")
async def fine_turno(interaction: discord.Interaction):
    t = supabase.table("turni_attivi").select("*").eq("user_id", str(interaction.user.id)).execute()
    if not t.data:
        return await interaction.response.send_message("❌ Non hai turni in corso.", ephemeral=True)
    data = t.data[0]
    supabase.table("turni_attivi").delete().eq("user_id", str(interaction.user.id)).execute()
    await invia_richiesta_stipendio(bot, interaction.user, data, motivo="Termine Volontario")
    await interaction.response.send_message("🏁 Turno concluso! Notifica inoltrata all'amministrazione.", ephemeral=True)

@bot.tree.command(name="staff-chiudi-turno", description="[STAFF] Chiudi il turno di un dipendente.")
@app_commands.checks.has_role(RUOLO_STAFF_ID)
async def staff_chiudi_turno(interaction: discord.Interaction, utente: discord.Member):
    t = supabase.table("turni_attivi").select("*").eq("user_id", str(utente.id)).execute()
    if not t.data:
        return await interaction.response.send_message("❌ Nessun turno attivo per questo utente.", ephemeral=True)
    data = t.data[0]
    supabase.table("turni_attivi").delete().eq("user_id", str(utente.id)).execute()
    await invia_richiesta_stipendio(bot, utente, data, motivo=f"Chiusura d'ufficio da {interaction.user.display_name}")
    await interaction.response.send_message(f"🔒 Turno di {utente.mention} chiuso d'autorità.", ephemeral=True)

@bot.tree.command(name="staff-chiudi-tutti", description="[STAFF] Chiudi forzatamente tutti i turni attivi.")
@app_commands.checks.has_role(RUOLO_STAFF_ID)
async def staff_chiudi_tutti(interaction: discord.Interaction):
    turni = supabase.table("turni_attivi").select("*").execute().data or []
    for t in turni:
        supabase.table("turni_attivi").delete().eq("user_id", t["user_id"]).execute()
        m = interaction.guild.get_member(int(t["user_id"]))
        if m:
            await invia_richiesta_stipendio(bot, m, t, motivo="Chiusura Collettiva")
    await interaction.response.send_message(f"🚨 Chiusi tutti i **{len(turni)}** turni attivi.", ephemeral=True)

@bot.tree.command(name="item-give", description="Aggiunge un oggetto ad un inventario (Staff)")
@app_commands.autocomplete(item=oggetto_custom_autocomplete)
async def item_give(interaction: discord.Interaction, utente: discord.Member, item: str, quantita: int = 1):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    it = supabase.table("custom_items").select("*").ilike("name", item).execute()
    if not it.data:
        return await interaction.response.send_message("❌ Oggetto non a catalogo.", ephemeral=True)

    info = it.data[0]
    nome_f = info["name"]
    mat_txt = ""
    if info.get("category", "").lower() in ["armi", "arma"]:
        mat = f"{''.join(random.choices(string.digits + string.ascii_uppercase, k=4))}-{''.join(random.choices(string.digits + string.ascii_uppercase, k=4))}"
        nome_f = f"{info['name']} [{mat}]"
        mat_txt = f"\nMatricola: `{mat}`"

    inv = supabase.table("inventory").select("*").eq("discord_id", str(utente.id)).ilike("item_name", nome_f).execute()
    if inv.data:
        supabase.table("inventory").update({"quantity": inv.data[0]["quantity"] + quantita}).eq("id", inv.data[0]["id"]).execute()
    else:
        supabase.table("inventory").insert({"discord_id": str(utente.id), "item_name": nome_f, "category": info.get("category", "Generale"), "weight": info.get("weight", 0.1), "quantity": quantita}).execute()

    await interaction.response.send_message(f"✅ Oggetto **{nome_f}** assegnato a {utente.mention}!{mat_txt}", ephemeral=True)

@bot.tree.command(name="item-remove", description="Rimuove oggetti da un inventario (Staff)")
async def item_remove(interaction: discord.Interaction, utente: discord.Member, item: str, quantita: int = None):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    inv = supabase.table("inventory").select("*").eq("discord_id", str(utente.id)).ilike("item_name", f"%{item}%").execute()
    if not inv.data:
        return await interaction.response.send_message("❌ Nessun oggetto corrispondente trovato.", ephemeral=True)

    it = inv.data[0]
    if quantita is None or quantita >= it["quantity"]:
        supabase.table("inventory").delete().eq("id", it["id"]).execute()
        r = it["quantity"]
    else:
        supabase.table("inventory").update({"quantity": it["quantity"] - quantita}).eq("id", it["id"]).execute()
        r = quantita

    await interaction.response.send_message(f"🗑️ Rimossi **{r}x {it['item_name']}** a {utente.mention}.", ephemeral=True)

@bot.tree.command(name="ruoli", description="Assegna o rimuovi ruoli ad un utente")
@app_commands.choices(azione=[app_commands.Choice(name="Aggiungi", value="add"), app_commands.Choice(name="Rimuovi", value="remove")])
async def ruoli(interaction: discord.Interaction, azione: app_commands.Choice[str], utente: discord.Member, ruolo: discord.Role):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)

    if azione.value == "add":
        await utente.add_roles(ruolo)
        await interaction.response.send_message(f"✅ Ruolo {ruolo.mention} assegnato a {utente.mention}.")
    else:
        await utente.remove_roles(ruolo)
        await interaction.response.send_message(f"✅ Ruolo {ruolo.mention} revocato a {utente.mention}.")

@bot.tree.command(name="costruisci", description="Avvia un cantiere edile")
@app_commands.checks.has_role(ID_RUOLO_EDILIZIA)
@app_commands.choices(grandezza=[app_commands.Choice(name="Piccolo", value="piccolo"), app_commands.Choice(name="Medio", value="medio"), app_commands.Choice(name="Grande", value="grande")])
async def costruisci(interaction: discord.Interaction, azienda: str, address: str, grandezza: app_commands.Choice[str], operaio1: discord.Member = None, operaio2: discord.Member = None):
    await interaction.response.defer()
    cfg = {
        "piccolo": {"durata": 1800, "mat_rng": (10, 30), "num": 2},
        "medio": {"durata": 3600, "mat_rng": (30, 60), "num": 3},
        "grande": {"durata": 7200, "mat_rng": (60, 100), "num": 4}
    }[grandezza.value]

    mats = [{"nome": m, "totale": random.randint(*cfg["mat_rng"]), "consumati": 0} for m in random.sample(LISTA_MATERIALI_DISPONIBILI, cfg["num"])]
    operai = [str(m.id) for m in [operaio1, operaio2] if m]
    end_dt = datetime.now(timezone.utc) + timedelta(seconds=cfg["durata"])

    msg = await interaction.followup.send(embed=discord.Embed(description="Inizializzazione cantiere...", color=EmeraldColor.GOLD))
    c_data = {
        "message_id": str(msg.id), "channel_id": str(msg.channel.id), "builder_id": str(interaction.user.id),
        "azienda": azienda, "address": address, "grandezza": grandezza.value, "tempo_rimanente": cfg["durata"],
        "paused": False, "materiali": mats, "operai_ids": operai, "end_time": end_dt.isoformat()
    }
    supabase.table("cantieri").insert(c_data).execute()
    await msg.edit(embed=generate_cantiere_embed(c_data))

@bot.tree.command(name="panicbutton", description="[EMERGENZA] Invia allarme SOS alle forze dell'ordine.")
async def panicbutton(interaction: discord.Interaction):
    if not any(r.id in [RUOLO_POLIZIA_ID, RUOLO_FBI_ID] for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Autorizzazione negata.", ephemeral=True)
    ch = bot.get_channel(PANIC_CHANNEL_ID)
    if not ch:
        return await interaction.response.send_message("❌ Canale emergenze assente.", ephemeral=True)

    await interaction.response.send_message(f"🚨 **PANIC BUTTON ATTIVATO** da {interaction.user.mention}!")
    for i in range(1, 4):
        await asyncio.sleep(4)
        await ch.send(f"🚨 **EMERALD DISPATCH — SOS AGENTE IN PERICOLO (#{i})** 🚨\nPosizione: {interaction.user.mention}\n{' '.join(ROLES_TO_TAG)}")

@bot.tree.command(name="unbanall", description="Sbanna tutti gli utenti dal server (Owner)")
async def unbanall(interaction: discord.Interaction):
    if interaction.user != interaction.guild.owner:
        return await interaction.response.send_message("❌ Riservato all'Owner.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    bans = [b async for b in interaction.guild.bans()]
    for b in bans:
        try:
            await interaction.guild.unban(b.user)
            await asyncio.sleep(0.3)
        except Exception:
            pass
    await interaction.followup.send(f"✅ Sbannati {len(bans)} utenti.", ephemeral=True)

@bot.tree.command(name="911", description="Invia una richiesta di soccorso immediato")
@app_commands.choices(fdo=[app_commands.Choice(name="Polizia", value="Forze dell'Ordine"), app_commands.Choice(name="Medici (EMS)", value="E.M.S."), app_commands.Choice(name="Vigili del Fuoco", value="Firefighter")])
async def emergenza_911(interaction: discord.Interaction, motivo: str, fdo: app_commands.Choice[str]):
    ch = bot.get_channel(ID_CANALE_EMERGENZA)
    if not ch:
        return await interaction.response.send_message("❌ Canale 911 non disponibile.", ephemeral=True)
    embed = discord.Embed(title="🚨 CHIAMATA D'EMERGENZA 911", description=f"**Segnalatore:** {interaction.user.mention}\n**Reparto:** `{fdo.name}`\n**Motivo:** {motivo}", color=EmeraldColor.RED)
    embed.set_footer(text="Emerald State Emergency Network")
    await ch.send(content=f"<@&{ID_RUOLO_FDO}> <@&{ID_RUOLO_EMS}> <@&{ID_RUOLO_FIRE}>", embed=embed)
    await interaction.response.send_message("✅ Chiamata inoltrata al Dispatch!", ephemeral=True)

@bot.tree.command(name="anonimo", description="Invia un messaggio coperto da crittografia")
async def anonimo(interaction: discord.Interaction, messaggio: str, nickname: str = None):
    await interaction.response.defer(ephemeral=True)
    u_id = str(interaction.user.id)
    reg = supabase.table("utenti_anonimi").select("nickname").eq("user_id", u_id).execute()
    if not reg.data and not nickname:
        return await interaction.followup.send("❌ Scegli un alias per la prima trasmissione.", ephemeral=True)
    alias = nickname if nickname else reg.data[0]["nickname"]
    if nickname:
        supabase.table("utenti_anonimi").upsert({"user_id": u_id, "nickname": alias}).execute()

    embed = discord.Embed(title="🔐 RETE CRITTOGRAFATA ANONIMA", description=f"```fix\nMITTENTE: {alias}\n```\n> {messaggio}", color=EmeraldColor.NAVY)
    embed.set_footer(text="Tracciamento nodo: Fallito • Emerald Darknet")
    msg = await interaction.channel.send(embed=embed)
    supabase.table("messaggi_anonimi").insert({"message_id": str(msg.id), "user_id": u_id}).execute()
    await interaction.followup.send("✅ Messaggio trasmesso.", ephemeral=True)

@bot.tree.command(name="me", description="Esegui un'azione di ruolo")
async def me(interaction: discord.Interaction, azione: str):
    await interaction.response.defer()
    await interaction.delete_original_response()
    embed = discord.Embed(description=f"🎬 **Azione Roleplay**\n\n{interaction.user.mention} {azione}", color=EmeraldColor.NAVY)
    embed.set_footer(text="Emerald RP • Official Action Log")
    await interaction.channel.send(embed=embed)

@bot.tree.command(name="compra", description="Acquista un articolo dal negozio")
@app_commands.autocomplete(item=shop_item_autocomplete)
async def compra(interaction: discord.Interaction, item: str, quantita: int = 1):
    u_id = str(interaction.user.id)
    it = supabase.table("custom_items").select("*").ilike("name", item).execute()
    if not it.data or quantita < 1:
        return await interaction.response.send_message("❌ Prodotto non valido.", ephemeral=True)

    info = it.data[0]
    tot = float(info.get("price", 0)) * quantita
    user = supabase.table("users").select("wallet").eq("discord_id", u_id).execute()
    if not user.data or user.data[0]["wallet"] < tot:
        return await interaction.response.send_message(f"❌ Contanti insufficienti. Totale: € {tot:,.2f}", ephemeral=True)

    supabase.table("users").update({"wallet": user.data[0]["wallet"] - tot}).eq("discord_id", u_id).execute()
    nome_f = info["name"]
    if info.get("category", "").lower() in ["armi", "arma"]:
        mat = f"{''.join(random.choices(string.digits + string.ascii_uppercase, k=4))}-{''.join(random.choices(string.digits + string.ascii_uppercase, k=4))}"
        nome_f = f"{info['name']} [{mat}]"

    supabase.table("inventory").insert({"discord_id": u_id, "item_name": nome_f, "category": info.get("category", "Generale"), "weight": info.get("weight", 0.1) * quantita, "quantity": quantita}).execute()
    await interaction.response.send_message(f"✅ Hai acquistato **{quantita}x {nome_f}** per **€ {tot:,.2f}**.", ephemeral=True)

@bot.tree.command(name="telefono", description="Accedi al tuo smartphone Emerald OS")
async def telefono(interaction: discord.Interaction):
    u_id = str(interaction.user.id)
    p = supabase.table("user_phones").select("phone_number").eq("discord_id", u_id).execute()
    if not p.data:
        num = f"+1 (555) {random.randint(100, 999)}-{random.randint(1000, 9999)}"
        supabase.table("user_phones").insert({"discord_id": u_id, "phone_number": num}).execute()
    else:
        num = p.data[0]["phone_number"]

    embed = discord.Embed(title="📱 Emerald OS — Smartphone", description=f"Terminale personale attivo.\nNumero: `{num}`", color=EmeraldColor.MAIN)
    await interaction.response.send_message(embed=embed, view=EmeraldPhoneView(u_id, num), ephemeral=True)

@bot.tree.command(name="portafoglio", description="Verifica i contanti a portata di mano")
async def portafoglio(interaction: discord.Interaction):
    u = get_or_create_user(interaction.user.id, interaction.user.name)
    embed = discord.Embed(title="💼 Portafoglio Personale", description=f"Contanti disponibili: **€ {float(u.get('wallet', 0)):,.2f}**", color=EmeraldColor.MAIN)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="deposito_fazione", description="Accedi al deposito sicuro della tua fazione")
@app_commands.autocomplete(fazione=fazione_autocomplete)
async def deposito_fazione(interaction: discord.Interaction, fazione: str):
    f_role = supabase.table("faction_roles").select("role_id").ilike("faction_name", fazione).execute()
    if not f_role.data or not any(r.id == int(f_role.data[0]["role_id"]) for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Non autorizzato per questa fazione.", ephemeral=True)

    vault = supabase.table("faction_vaults").select("cash_balance").ilike("faction_name", fazione).execute()
    cassa = vault.data[0]["cash_balance"] if vault.data else 0.0
    inv = supabase.table("faction_inventory").select("item_name, quantity, category").ilike("faction_name", fazione).execute()
    txt = "\n".join([f"• {i['item_name']} (x{i['quantity']})" for i in (inv.data or [])]) or "*Nessun oggetto in deposito.*"

    embed = discord.Embed(title=f"🏛️ Deposito — {fazione}", color=EmeraldColor.GOLD)
    embed.add_field(name="💰 Bilancio Cassa", value=f"**€ {cassa:,.2f}**", inline=False)
    embed.add_field(name="📦 Magazzino", value=f"```{txt}```", inline=False)
    await interaction.response.send_message(embed=embed, view=FactionVaultView(fazione), ephemeral=True)

@bot.tree.command(name="shop", description="Consulta il listino prezzi di Emerald City")
async def shop(interaction: discord.Interaction):
    items = supabase.table("custom_items").select("*").limit(20).execute().data or []
    embed = discord.Embed(title="🛒 Negozio Generale — Emerald City", description="Articoli in vendita:", color=EmeraldColor.BLUE)
    for i in items:
        embed.add_field(name=f"{i['name']}", value=f"Prezzo: `€ {float(i.get('price', 0)):,.2f}` | Cat: `{i.get('category')}`", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="crea_item", description="[STAFF] Crea un nuovo oggetto")
@app_commands.choices(categoria=[app_commands.Choice(name=c, value=c.lower()) for c in ["Arma", "Cibo", "Bevanda", "Medicina", "Zaino", "Utility", "Edilizia", "Altro"]])
async def crea_item(interaction: discord.Interaction, nome: str, categoria: app_commands.Choice[str], peso: float, ruolo_richiesto: discord.Role, prezzo: float = 100.0):
    if not ha_ruolo_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    supabase.table("custom_items").insert({
        "name": nome, "category": categoria.value, "weight": max(0.0, peso), "price": prezzo, "required_role_id": str(ruolo_richiesto.id)
    }).execute()
    embed = discord.Embed(title="✨ Oggetto Creato", description=f"Articolo **{nome}** aggiunto con successo.", color=EmeraldColor.MAIN)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="inventario", description="Apri il tuo inventario")
async def inventario(interaction: discord.Interaction):
    u = get_or_create_user(interaction.user.id, interaction.user.name)
    max_w = float(u.get("max_weight", 10.0))
    curr_w = calculate_user_inventory_weight(str(interaction.user.id))
    inv = supabase.table("inventory").select("*").eq("discord_id", str(interaction.user.id)).execute().data or []

    embed = discord.Embed(title=f"🎒 Inventario di {interaction.user.display_name}", description=f"Peso: `{curr_w:.1f} / {max_w:.1f} kg`", color=EmeraldColor.MAIN)
    for i in inv:
        embed.add_field(name=f"{i['item_name']} x{i['quantity']}", value=f"Cat: `{i['category']}` | Peso unitario: `{i['weight']} kg`", inline=False)
    await interaction.response.send_message(embed=embed, view=InventoryUseView(interaction.user.id, inv) if inv else None)

@bot.tree.command(name="bancomat", description="Accedi al terminale Bancomat")
async def bancomat(interaction: discord.Interaction):
    u = get_or_create_user(interaction.user.id, interaction.user.name)
    mode = "register" if u.get("pin") is None else "login"
    view = PinKeypadView(interaction.user.id, u, mode=mode)
    embed = discord.Embed(title="💳 Terminale Bancomat — Emerald Bank", description="Digita il tuo codice di sicurezza a 4 cifre:\n\n**PIN:** `____`", color=EmeraldColor.BLUE)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="cad_polizia", description="[POLIZIA] Terminale operativo forze dell'ordine")
@app_commands.checks.has_role(RUOLO_POLIZIA_ID)
async def cad_polizia(interaction: discord.Interaction):
    docs = supabase.table("documents").select("*").limit(25).execute().data or []
    if not docs:
        return await interaction.response.send_message("❌ Nessun cittadino censito.", ephemeral=True)
    embed = discord.Embed(title="🚔 CAD POLIZIA DI STATO", description="Seleziona un cittadino per consultare o emettere provvedimenti:", color=EmeraldColor.BLUE)
    await interaction.response.send_message(embed=embed, view=PoliceCadSelectView(docs, interaction.user.id, bot), ephemeral=True)

@bot.tree.command(name="cad_fbi", description="[FBI] Terminale federale d'indagine")
@app_commands.checks.has_role(RUOLO_FBI_ID)
async def cad_fbi(interaction: discord.Interaction):
    docs = supabase.table("documents").select("*").limit(25).execute().data or []
    embed = discord.Embed(title="🕵️‍♂️ CAD FBI — DIVISIONE FEDERALE", description="Seleziona un fascicolo cittadino:", color=EmeraldColor.NAVY)
    await interaction.response.send_message(embed=embed, view=PoliceCadSelectView(docs, interaction.user.id, bot), ephemeral=True)

@bot.tree.command(name="paga_multa", description="Sanzioni personali pendenti")
async def paga_multa(interaction: discord.Interaction):
    u_id = str(interaction.user.id)
    fines = supabase.table("police_fines").select("*").eq("discord_id", u_id).eq("status", "Da Pagare").execute().data or []
    if not fines:
        return await interaction.response.send_message("🎉 Nessuna multa pendente a tuo carico!", ephemeral=True)
    tot = sum([float(f.get("amount", 0)) for f in fines])
    embed = discord.Embed(title="💳 Sanzioni Amministrative", description=f"Hai **{len(fines)}** verbale/i per un totale di **€ {tot:,.2f}**.", color=EmeraldColor.RED)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="perquisci", description="Esegui una perquisizione corporale")
async def perquisci(interaction: discord.Interaction, utente: discord.Member):
    await interaction.response.defer()
    for perc in [30, 70, 100]:
        await asyncio.sleep(0.7)
    t_id = str(utente.id)
    u = supabase.table("users").select("wallet").eq("discord_id", t_id).execute()
    inv = supabase.table("inventory").select("item_name, quantity").eq("discord_id", t_id).execute().data or []
    cassa = u.data[0]["wallet"] if u.data else 0.0

    embed = discord.Embed(title="🔍 ESITO PERQUISIZIONE", color=EmeraldColor.NAVY)
    embed.add_field(name="Soggetto", value=utente.mention, inline=False)
    embed.add_field(name="Contanti Rinvenuti", value=f"**€ {cassa:,.2f}**", inline=True)
    items_txt = "\n".join([f"• {i['item_name']} (x{i['quantity']})" for i in inv]) or "*Tasche vuote.*"
    embed.add_field(name="Oggetti", value=items_txt, inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="registra_veicolo", description="[MOTORIZZAZIONE] Registra un nuovo veicolo")
async def registra_veicolo(interaction: discord.Interaction, proprietario: discord.Member, modello: str, targa: str):
    if not any(r.id == RUOLO_MOTORIZZAZIONE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Riservato alla Motorizzazione.", ephemeral=True)
    supabase.table("registered_vehicles").insert({"discord_id": str(proprietario.id), "model": modello, "plate": targa.upper().strip()}).execute()
    embed = discord.Embed(title="🚗 Immatricolazione Completata", description=f"Veicolo **{modello}** con targa **`{targa.upper().strip()}`** intestato a {proprietario.mention}.", color=EmeraldColor.MAIN)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="registra_modifiche", description="Registra interventi meccanici su un veicolo")
@ha_ruolo_meccanico()
async def registra_modifiche(interaction: discord.Interaction, targa: str, tipo_modifica: str, dettagli: str, costo: float):
    supabase.table("vehicle_modifications").insert({
        "plate": targa.upper().strip(), "mod_type": tipo_modifica, "details": dettagli, "cost": costo, "installed_by": str(interaction.user.id)
    }).execute()
    embed = discord.Embed(title="🔧 Modifica Omologata", description=f"Applicata modifica **{tipo_modifica}** su targa `{targa.upper().strip()}`.", color=EmeraldColor.MAIN)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="registra_patente", description="[MOTORIZZAZIONE] Rilascia una patente")
async def registra_patente(interaction: discord.Interaction, cittadino: discord.Member, tipo_patente: str):
    if not any(r.id == RUOLO_MOTORIZZAZIONE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Riservato alla Motorizzazione.", ephemeral=True)
    supabase.table("driver_licenses").insert({"discord_id": str(cittadino.id), "license_type": tipo_patente.upper(), "status": "Attiva"}).execute()
    await interaction.response.send_message(f"💳 Patente **{tipo_patente.upper()}** assegnata a {cittadino.mention}.")

@bot.tree.command(name="registra_arma", description="[ARMERIA] Registra matricola arma")
async def registra_arma(interaction: discord.Interaction, acquirente: discord.Member, matricola: str, modello: str):
    if not any(r.id == RUOLO_ARMERIA_ID for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Riservato all'Armeria.", ephemeral=True)
    supabase.table("registered_weapons").insert({"discord_id": str(acquirente.id), "model": modello, "serial_number": matricola}).execute()
    await interaction.response.send_message(f"🔫 Arma **{modello}** (`{matricola}`) registrata a {acquirente.mention}.")

@bot.tree.command(name="registra_porto_darmi", description="[POLIZIA] Rilascia porto d'armi")
async def registra_porto_darmi(interaction: discord.Interaction, cittadino: discord.Member, tipo_licenza: str):
    if not any(r.id == RUOLO_POLIZIA_ID for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Riservato alla Polizia.", ephemeral=True)
    supabase.table("gun_licenses").insert({"discord_id": str(cittadino.id), "license_type": tipo_licenza, "status": "Attivo"}).execute()
    await interaction.response.send_message(f"🛡️ Porto d'armi **{tipo_licenza}** concesso a {cittadino.mention}.")

@bot.tree.command(name="registra_casa", description="[IMMOBILIARE] Registra un immobile")
async def registra_casa(interaction: discord.Interaction, proprietario: discord.Member, indirizzo: str, tipologia: str):
    if not any(r.id == RUOLO_IMMOBILIARE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Riservato all'Agenzia Immobiliare.", ephemeral=True)
    supabase.table("registered_properties").insert({"discord_id": str(proprietario.id), "address": indirizzo, "property_type": tipologia}).execute()
    await interaction.response.send_message(f"🏠 Immobile a **{indirizzo}** registrato a nome di {proprietario.mention}.")

# ==========================================
# ⚡ EVENTI BOT (ON_READY, JOIN, REACTION)
# ==========================================
@bot.event
async def on_member_join(member: discord.Member):
    welcome = (
        f"✦ **BENVENUTO SU EMERALD RP!** ✦\n"
        f"Benvenuto nella nostra community, {member.mention}! Consulta i canali guida per iniziare la tua storia.\n"
        f"Il tuo futuro ti aspetta a Emerald City!"
    )
    try:
        await member.send(content=welcome, view=WelcomeButtonsView())
    except Exception:
        pass

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) != "❓" or payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    member = guild.get_member(payload.user_id)
    if not member or not (any(r.id == RUOLO_STAFF_ID for r in member.roles) or member.guild_permissions.administrator):
        return

    res = supabase.table("messaggi_anonimi").select("user_id").eq("message_id", str(payload.message_id)).execute()
    if res.data:
        autore = await bot.fetch_user(int(res.data[0]["user_id"]))
        emb = discord.Embed(title="🔍 IDENTITÀ DE-ANONIMIZZATA", description=f"Autore del messaggio: {autore.mention} (`{autore.id}`)", color=EmeraldColor.RED)
        await member.send(embed=emb)
        ch = bot.get_channel(payload.channel_id)
        if ch:
            m = await ch.fetch_message(payload.message_id)
            await m.remove_reaction(payload.emoji, member)

@bot.event
async def on_ready():
    await bot.tree.sync()
    bot.add_view(PannelloAnagrafeView())
    bot.add_view(DistributorePannelloView())
    bot.add_view(ApprovazioneStipendioView())

    if not gestore_cantieri_loop.is_running():
        gestore_cantieri_loop.start()

    print(f"💎 Emerald RP Bot Online come {bot.user}!")

# ==========================================
# 🏁 AVVIO SERVER E BOT
# ==========================================
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    bot.run(DISCORD_TOKEN)
