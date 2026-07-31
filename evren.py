import os
import random
import string
import threading
import io
import json
import asyncio
import aiohttp
from flask import Flask, jsonify
import discord
from discord import app_commands, ui
from discord.ext import commands
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.async_api import async_playwright
import imageio_ffmpeg

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

# --- CONFIGURAZIONE RUOLI SPECIFICI ---
RUOLO_STAFF_ID = 1253460150141059198           # Permesso per /crea_item
RUOLO_BANCOMAT_ID = 1374264699331543140        # Permesso per accedere al Bancomat (opzionale)
RUOLO_ARMERIA_ID = 1253460200300478474        # Permesso per registrare ed emettere armi
RUOLO_MOTORIZZAZIONE_ID = 1253460178305679433  # Permesso per registrare veicoli e patenti
RUOLO_POLIZIA_ID = 1359569600198611104         # Permesso per CAD Polizia e Porto d'Armi
RUOLO_IMMOBILIARE_ID = 1260308281302454533     # Permesso per registrare le case/immobili
RUOLO_RICHIESTO_ID = 1521209331423383702
RUOLO_FBI_ID = None
# Mettilo in cima al file, prima delle funzioni audio
FFMPEG_PATH = None  # Lasciandolo a None, discord.py cercherà ffmpeg automaticamente nel PATH del container

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True  # <-- Fondamentale per far funzionare get_channel()

bot = commands.Bot(command_prefix="!", intents=intents)


# --- SERVER FLASK PER KEEP-ALIVE ---

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "online", "server": "Evren City RP Bot"})

def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


# --- FUNZIONI DI SUPPORTO & UTILITY ---

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
            "max_weight": 10.0  # Limite peso base
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

def genera_codice_fiscale(nome: str, cognome: str) -> str:
    letters = string.ascii_uppercase
    cf_parte1 = "".join(random.choices(letters, k=6))
    cf_parte2 = "".join(random.choices(string.digits, k=2))
    cf_parte3 = "".join(random.choices(letters, k=1))
    cf_parte4 = "".join(random.choices(string.digits, k=3))
    cf_parte5 = "".join(random.choices(letters, k=1))
    return f"{cf_parte1}{cf_parte2}{cf_parte3}{cf_parte4}{cf_parte5}"

def genera_num_documento() -> str:
    prefisso = "".join(random.choices(string.ascii_uppercase, k=2))
    numero = "".join(random.choices(string.digits, k=7))
    return f"{prefisso}{numero}"

def genera_matricola_arma() -> str:
    parte1 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
    parte2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
    return f"{parte1}-{parte2}"

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
            else:
                raise Exception(f"Errore ImgBB status code: {response.status}")

# URL diretti dei tuoi file su GitHub
URL_SQUILLO = "https://raw.githubusercontent.com/elmatador737373-maker/Evren/main/squillo.mp3"
URL_RIFIUTO = "https://raw.githubusercontent.com/elmatador737373-maker/Evren/main/rifiuto.mp3"

async def riproduci_audio_canale(channel: discord.VoiceChannel, audio_url: str, loop: bool = False):
    vc = None
    try:
        # Si connette al canale vocale creato
        vc = await channel.connect()

        while vc and vc.is_connected():
            fatto = asyncio.Event()

            def after_play(error):
                if error:
                    print(f"Errore riproduzione audio: {error}")
                vc.loop.call_soon_threadsafe(fatto.set)

            # Legge lo stream audio direttamente dall'URL raw di GitHub
            source = discord.FFmpegPCMAudio(audio_url)

            if not vc.is_playing():
                vc.play(source, after=after_play)
                await fatto.wait()

            if not loop:
                break
            
            await asyncio.sleep(0.5)

    except Exception as e:
        print(f"❌ Errore audio: {e}")
    finally:
        if vc and vc.is_connected():
            try:
                await vc.disconnect()
            except Exception:
                pass

    # =======================================================
#  SECONDO MODULO: DETTAGLI FISICI E SALVATAGGIO
# =======================================================
class CreaDocumentiStep2Modal(ui.Modal, title="🪪 ┃ ʀᴇɢɪsᴛʀᴏ (2/2: Dati Fisici)"):
    def __init__(self, nome, cognome, data_nascita, luogo_nascita):
        super().__init__()
        self.nome = nome
        self.cognome = cognome
        self.data_nascita = data_nascita
        self.luogo_nascita = luogo_nascita

        self.colore_occhi = ui.TextInput(label="ᴄᴏʟᴏʀᴇ ᴏᴄᴄʜɪ", placeholder="Es. Marroni / Verdi", required=True, max_length=30)
        self.colore_capelli = ui.TextInput(label="ᴄᴏʟᴏʀᴇ ᴄᴀᴘᴇʟʟɪ", placeholder="Es. Castani / Neri", required=True, max_length=30)
        self.segni_particolari = ui.TextInput(label="sᴇɢɴɪ ᴘᴀʀᴛɪᴄᴏʟᴀʀɪ", placeholder="Es. Cicatrice o Nessuno", required=False, max_length=100)

        self.add_item(self.colore_occhi)
        self.add_item(self.colore_capelli)
        self.add_item(self.segni_particolari)

    async def on_submit(self, interaction: discord.Interaction):
        occhi_val = self.colore_occhi.value.strip()
        capelli_val = self.colore_capelli.value.strip()
        segni_val = self.segni_particolari.value.strip() or "Nessuno"

        user_id = str(interaction.user.id)

        try:
            cf_temporaneo = f"EVREN-{user_id[-6:]}"
            doc_numero = f"DOC-{user_id[-5:]}"

            data = {
                "discord_id": user_id,
                "name": self.nome,
                "surname": self.cognome,
                "birth_date": self.data_nascita,
                "birth_place": self.luogo_nascita,
                "eye_color": occhi_val,
                "hair_color": capelli_val,
                "distinct_marks": segni_val,
                "cf": cf_temporaneo,
                "doc_number": doc_numero,
                "photo_url": None
            }

            supabase.table("documents").insert(data).execute()

            await interaction.response.send_message(
                "✅ **ᴅᴀᴛɪ ᴀɴᴀɢʀᴀꜰɪᴄɪ sᴀʟᴠᴀᴛɪ ᴄᴏɴ sᴜᴄᴄᴇss!**\n"
                "Ora utilizza il comando `/carica_foto_documento` allegando la tua foto per completare la carta d'identità.",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Si è verificato un errore durante il salvataggio dei dati: {e}",
                ephemeral=True
            )


# ==========================================
# ⚙️ CONFIGURAZIONE GLOBALE
# ==========================================
PANIC_CHANNEL_ID = 1519418659821584384  # ID del canale dove arriva l'allarme
ROLE_POLIZIA_ID = 1359569600198611104  # ID del ruolo Polizia autorizzato
ROLE_FBI_ID = 1531970242329317520  # ID del ruolo FBI autorizzato

# Lista dei ruoli/tag da menzionare nell'allarme (puoi ripeterli se vuoi taggare più volte)
ROLES_TO_TAG = [
    "<@&1363487988570521670>",
    "<@&1259234623230181396>",
]

import asyncio

# ==========================================


# ==========================================
# 🚨 COMANDO SLASH: /panicbutton
# ==========================================
@bot.tree.command(
    name="panicbutton",
    description="[EMERGENZA] Attiva il Panic Button d'emergenza sulla radio con notifiche ripetute.",
)
async def panicbutton(interaction: discord.Interaction):
  user_roles = [role.id for role in interaction.user.roles]

  # Controllo che l'utente possieda almeno uno dei ruoli autorizzati
  if ROLE_POLIZIA_ID not in user_roles and ROLE_FBI_ID not in user_roles:
    await interaction.response.send_message(
        "❌ Non sei autorizzato a utilizzare il Panic Button!", ephemeral=True
    )
    return

  channel = bot.get_channel(PANIC_CHANNEL_ID)
  if not channel:
    await interaction.response.send_message(
        "❌ Canale Panic Button non trovato o non configurato correttamente.",
        ephemeral=True,
    )
    return

  # Risposta pubblica immediata in chat con l'azione richiesta
  public_response = (
      f"* L'agente {interaction.user.mention} preme il panic button sulla radio,"
      " inviando una richiesta di soccorso immediata a tutte le unità *"
  )
  await interaction.response.send_message(content=public_response)

  # Unisce tutti i tag configurati
  tags_string = " ".join(ROLES_TO_TAG)

  # Funzione interna asincrona per inviare i messaggi ripetuti con intervallo di 4 secondi
  async def send_repeated_alerts():
    for i in range(1, 4):  # Invia altri 3 messaggi di richiamo (totale 4 ondate)
      await asyncio.sleep(4)
      repeat_msg = (
          f"🚨 **DISPATCH: SOS EMERGENZA (RICHIAMO #{i})** 🚨\n"
          f"> L'operatore **{interaction.user.mention}** *richiede assistenza urgente, segnale ancora attivo!*\n\n"
          f"📍 **Posizione in tempo reale di:** {interaction.user.mention}\n\n"
          f"{tags_string}"
      )
      try:
        await channel.send(content=repeat_msg)
      except Exception as e:
        print(f"Errore nell'invio del richiamo Panic Button: {e}")

  # Avvia il loop in background senza bloccare il bot
  bot.loop.create_task(send_repeated_alerts())

  # Primo messaggio di allarme immediato nel canale dedicato
  panic_msg = (
      f"🚨 **DISPATCH: SOS EMERGENZA CRITICA!** 🚨\n"
      f"> L'operatore **{interaction.user.mention}** *preme il panic button sulla radio, inviando una richiesta di soccorso immediata a tutte le unità*\n\n"
      f"📍 **Posizione in tempo reale di:** {interaction.user.mention}\n\n"
      f"{tags_string}"
  )
  await channel.send(content=panic_msg)

# =======================================================
#  VIEW CON IL PULSANTE PER APRIRE IL SECONDO MODULO
# =======================================================
class ApriStep2View(ui.View):
    def __init__(self, nome, cognome, data_nascita, luogo_nascita):
        super().__init__(timeout=180)  # Il pulsante scade dopo 3 minuti
        self.nome = nome
        self.cognome = cognome
        self.data_nascita = data_nascita
        self.luogo_nascita = luogo_nascita

    @ui.button(label="Continua con i Dati Fisici (2/2)", style=discord.ButtonStyle.primary, emoji="➡️")
    async def apri_secondo_modulo(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(
            CreaDocumentiStep2Modal(self.nome, self.cognome, self.data_nascita, self.luogo_nascita)
        )


# =======================================================
#  PRIMO MODULO: DATI ANAGRAFICI
# =======================================================
class CreaDocumentiStep1Modal(ui.Modal, title="🪪 ┃ ʀᴇɢɪsᴛʀᴏ (1/2: Anagrafica)"):
    def __init__(self):
        super().__init__()

        self.nome = ui.TextInput(label="ɴᴏᴍᴇ", placeholder="Es. Mario", required=True, max_length=50)
        self.cognome = ui.TextInput(label="ᴄᴏɢɴᴏᴍᴇ", placeholder="Es. Rossi", required=True, max_length=50)
        self.data_nascita = ui.TextInput(label="ᴅᴀᴛᴀ ᴅɪ ɴᴀsᴄɪᴛᴀ", placeholder="Es. 15/05/1998", required=True, max_length=20)
        self.luogo_nascita = ui.TextInput(label="ʟᴜᴏɢᴏ ᴅɪ ɴᴀsᴄɪᴛᴀ", placeholder="Es. Los Angeles", required=True, max_length=50)

        self.add_item(self.nome)
        self.add_item(self.cognome)
        self.add_item(self.data_nascita)
        self.add_item(self.luogo_nascita)

    async def on_submit(self, interaction: discord.Interaction):
        nome_val = self.nome.value.strip()
        cognome_val = self.cognome.value.strip()
        data_val = self.data_nascita.value.strip()
        luogo_val = self.luogo_nascita.value.strip()

        # Invia un messaggio effimero con il pulsante per procedere al secondo modulo
        view = ApriStep2View(nome_val, cognome_val, data_val, luogo_val)
        await interaction.response.send_message(
            "📌 **Primo step completato con successo!**\n"
            "Clicca sul pulsante sottostante per inserire i dati fisici e completare la registrazione.",
            view=view,
            ephemeral=True
        )


# =======================================================
#  VIEW PERSISTENTE PER IL PANNELLO ANAGRAFE
# =======================================================
class PannelloAnagrafeView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Compila Anagrafica",
        style=discord.ButtonStyle.green,
        emoji="🪪",
        custom_id="anagrafe_apri_modal",
    )
    async def apri_modal(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)

        # Controllo preventivo: blocca se l'utente ha già un documento registrato
        existing = supabase.table("documents").select("discord_id").eq("discord_id", user_id).execute()

        if existing.data:
            await interaction.response.send_message(
                "❌ **Hai già completato la tua registrazione anagrafica!**\n"
                "Non è possibile creare un nuovo documento.",
                ephemeral=True
            )
            return

        # Apre il primo modulo
        await interaction.response.send_modal(CreaDocumentiStep1Modal())

# =======================================================
#  COMANDO /PANNELLO_DOCUMENTI (PER GLI ADMIN)
# =======================================================
@bot.tree.command(
    name="pannello_documenti",
    description="Invia il pannello interattivo permanente per la creazione dei documenti"
)
@app_commands.default_permissions(administrator=True)
async def pannello_documenti(interaction: discord.Interaction):
    server_name = interaction.guild.name
    server_icon = interaction.guild.icon.url if interaction.guild.icon else None

    embed = discord.Embed(
        title="🏛️ ┃ ᴜꜰꜰɪᴄɪᴏ ᴀɴᴀɢʀᴀꜰᴇ ᴄɪᴛᴛᴀᴅɪɴᴏ",
        description=(
            f"📋 **sᴘᴏʀᴛᴇʟʟᴏ ᴜꜰꜰɪᴄɪᴀʟᴇ ʀɪʟᴀsᴄɪᴏ ᴅᴏᴄᴜᴍᴇɴᴛɪ**\n"
            f"# ✦ ɢᴇɴᴇʀᴀᴢɪᴏɴᴇ ɪᴅᴇɴᴛɪᴛÀ\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 **ɢᴜɪᴅᴀ ʀᴀᴘɪᴅᴀ ᴀʟʟᴀ ᴄᴏᴍᴘɪʟᴀᴢɪᴏɴᴇ:**\n"
            f"1️⃣ Clicca sul pulsante **Compila Anagrafica** qui sotto.\n"
            f"2️⃣ Inserisci i tuoi dati anagrafici reali o RP nel modulo.\n"
            f"3️⃣ Segui le istruzioni successive per allegare la foto tessera.\n"
            f"4️⃣ Il sistema registrerà automaticamente il tuo codice fiscale.\n\n"
            f"⚠️ *Nota bene: È consentito un solo documento attivo per cittadino.*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=discord.Color.from_rgb(30, 144, 255)
    )

    if server_icon:
        embed.set_author(name=f"ᴄᴏᴍᴜɴᴇ ᴅɪ {server_name.upper()}", icon_url=server_icon)
    else:
        embed.set_author(name=f"ᴀɴᴀɢʀᴀꜰᴇ ᴄɪᴛᴛᴀᴅɪɴᴀ")

    embed.set_footer(
        text=f"⚖️ Servizi Demografici Ufficiali | {server_name}™",
        icon_url=server_icon
    )

    await interaction.channel.send(
        embed=embed,
        view=PannelloAnagrafeView()
    )

    await interaction.response.send_message(
        "✅ **ᴘᴀɴɴᴇʟʟᴏ ɪɴᴠɪᴀᴛᴏ.** L'interfaccia anagrafica persistente è stata pubblicata con successo.",
        ephemeral=True
    )

# --- VIEW CON BOTTONI REINDIRIZZAMENTO (LINK) ---

class WelcomeButtonsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        self.add_item(ui.Button(
            label="Bottone N1", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1500844219424706581"
        ))
        
        self.add_item(ui.Button(
            label="Bottone N2", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1252225171553652787"
        ))
        
        self.add_item(ui.Button(
            label="Bottone N3", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1374421195163963553"
        ))

        self.add_item(ui.Button(
            label="Bottone N4", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1519623994591019189"
        ))

        self.add_item(ui.Button(
            label="Bottone N5", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1252225106785337355"
        ))

        self.add_item(ui.Button(
            label="Bottone N6", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1503750254028390580"
        ))


import discord
from discord import app_commands


import discord
from discord import app_commands

import datetime
import discord
from discord import app_commands

import discord
from discord import app_commands


@bot.tree.command(
    name="911", description="Invia una richiesta di emergenza alle autorità"
)
@app_commands.describe(
    motivo="Specifica il motivo dell'emergenza (es. Incendio, Rapina, Incidente...)",
    fdo="Seleziona quale corpo di emergenza richiedere",
)
@app_commands.choices(
    fdo=[
        app_commands.Choice(
            name="🚨 Forze dell'Ordine", value="Forze dell'Ordine"
        ),
        app_commands.Choice(name="🚑 E.M.S. (Medici)", value="E.M.S."),
        app_commands.Choice(name="🚒 Firefighter (Pompieri)", value="Firefighter"),
    ]
)
async def emergenza_911(
    interaction: discord.Interaction, motivo: str, fdo: str
):
  # 1. ID del canale delle emergenze
  ID_CANALE_EMERGENZA = 1519418659821584384  # <--- INSERISCI L'ID DEL CANALE QUI

  # 2. Inserisci qui gli ID dei tre ruoli differenti da taggare in ogni chiamata
  ID_RUOLO_FDO = 1363487988570521670  # ID Ruolo Forze dell'Ordine
  ID_RUOLO_EMS = 1254146971535544471  # ID Ruolo EMS / Medici
  ID_RUOLO_FIRE = 1436420396726616210  # ID Ruolo Firefighter / Pompieri

  # Tenta di recuperare il canale (prima dalla cache, poi dalle API di Discord)
  canale_emergenza = bot.get_channel(ID_CANALE_EMERGENZA)
  if not canale_emergenza:
    try:
      canale_emergenza = await bot.fetch_channel(ID_CANALE_EMERGENZA)
    except Exception:
      canale_emergenza = None

  if not canale_emergenza:
    await interaction.response.send_message(
        "❌ Canale delle emergenze non configurato correttamente dal bot.",
        ephemeral=True,
    )
    return


  await interaction.response.defer(thinking=True, ephemeral=True)

  # 3. Tagga tutti e tre i ruoli contemporaneamente ad ogni chiamata
  content_ping = (
      f"<@&{ID_RUOLO_FDO}> & <@&{ID_RUOLO_EMS}> & <@&{ID_RUOLO_FIRE}>"
      " **Emergenza®**"
  )

  # 4. Costruzione dell'Embed della chiamata
  embed = discord.Embed(
      title="<a:ice:1262031849257959434> 911 ┃ Chiamata d'Emergenza <a:Poli:1262031800029544478>",
      description=(
          f"{interaction.user.mention} **ha richiesto assistenza immediata!**\n\n"
          f"🏢 **Corpo Richiesto:** `{fdo}`\n"
          f"⚠️ **Motivo:** `{motivo}`\n\n"
          "_La prima unità disponibile sarà subito da te_"
      ),
      color=discord.Color.from_rgb(220, 20, 60),
  )
  embed.set_footer(text="EvrenCity® Roleplay シ • OG Edition")

  # 5. Invio del messaggio pubblico nel canale specifico
  await canale_emergenza.send(content=content_ping, embed=embed)

  # 6. Conferma privata all'utente
  await interaction.followup.send(
      "✅ **Chiamata d'emergenza inviata con successo!** Tutti i dipartimenti"
      " sono stati allertati.",
      ephemeral=True,
  )

@bot.tree.command(
    name="anonimo", description="Invia un messaggio criptato sulla rete segreta"
)
@app_commands.describe(
    messaggio="Il testo del messaggio segreto",
    nickname=(
        "Il tuo alias segreto (obbligatorio solo la prima volta o per cambiarlo)"
    ),
)
async def anonimo(
    interaction: discord.Interaction, messaggio: str, nickname: str = None
):
  await interaction.response.defer(ephemeral=True)

  try:
    user_id = str(interaction.user.id)

    # 1. Controlla se l'utente ha già un nickname salvato su Supabase
    res = (
        supabase.table("utenti_anonimi")
        .select("nickname")
        .eq("user_id", user_id)
        .execute()
    )

    if not res.data and not nickname:
      return await interaction.followup.send(
          "❌ Devi specificare un `nickname` la prima volta!", ephemeral=True
      )

    alias_da_usare = nickname if nickname else res.data[0]["nickname"]

    # 2. Se viene fornito un nuovo nickname, esegue l'upsert
    if nickname:
      supabase.table("utenti_anonimi").upsert(
          {"user_id": user_id, "nickname": nickname}
      ).execute()

    desc_testo = (
        f"```\n"
        f"SISTEMA: Connessione Criptata\n"
        f"MITTENTE: {alias_da_usare}\n"
        f"```\n"
        f"**MESSAGGIO RICEVUTO:**\n"
        f"> {messaggio}"
    )

    embed = discord.Embed(
        title="🔐 █▓▒░ ＥＮＣＲＹＰＴＥＤ ＮＥＴＷＯＲＫ ░▒▓█ 🔐",
        description=desc_testo,
        color=discord.Color.dark_theme(),
        timestamp=datetime.datetime.now(),
    )
    embed.set_footer(text="Tracciamento IP: Fallito • Rete Anonima")

    # Invio del messaggio in chiaro nel canale
    msg_inviato = await interaction.channel.send(embed=embed)

    # 3. Salva il legame tra message_id e user_id su Supabase
    supabase.table("messaggi_anonimi").insert(
        {"message_id": str(msg_inviato.id), "user_id": user_id}
    ).execute()

    await interaction.followup.send(
        "✅ Messaggio inviato in totale anonimato.", ephemeral=True
    )

  except Exception as e:
    print(f"Errore anonimo: {e}")
    await interaction.followup.send(
        "❌ Errore critico nel sistema di criptazione.", ephemeral=True
    )


@bot.event
async def on_raw_reaction_add(payload):
  # 1. Configurazione ID Ruolo Staff
  ID_RUOLO_STAFF = 1253460150141059198

  # 2. Filtro: solo l'emoji corretta e non il bot stesso
  if str(payload.emoji) != "❓" or payload.user_id == bot.user.id:
    return

  # 3. Recupero Server e Membro
  guild = bot.get_guild(payload.guild_id)
  if not guild:
    return
  member = guild.get_member(payload.user_id)
  if not member:
    return

  # 4. Controllo Permessi Staff
  is_staff = any(
      r.id == ID_RUOLO_STAFF for r in member.roles
  ) or member.guild_permissions.administrator

  if is_staff:
    try:
      # Interroga Supabase per risalire all'autore del messaggio anonimo
      res = (
          supabase.table("messaggi_anonimi")
          .select("user_id")
          .eq("message_id", str(payload.message_id))
          .execute()
      )

      if res.data:
        utente_id = int(res.data[0]["user_id"])
        utente = await bot.fetch_user(utente_id)

        # Invio il DM allo staffer
        info_embed = discord.Embed(
            title="🔍 Identità Svelata", color=discord.Color.red()
        )
        info_embed.add_field(
            name="Messaggio ID", value=f"`{payload.message_id}`", inline=False
        )
        info_embed.add_field(
            name="Autore", value=f"{utente.mention} ({utente.name})", inline=True
        )
        info_embed.add_field(
            name="ID Utente", value=f"`{utente_id}`", inline=True
        )

        await member.send(embed=info_embed)

        # --- RIMOZIONE REAZIONE ---
        channel = bot.get_channel(payload.channel_id)
        if channel:
          msg = await channel.fetch_message(payload.message_id)
          await msg.remove_reaction(payload.emoji, member)

    except Exception as e:
      print(f"Errore durante la rimozione o l'invio DM: {e}")

@bot.tree.command(
    name="carica_foto_documento",
    description="Carica la foto del tuo documento su ImgBB e la aggiorna nel database",
)
@app_commands.describe(documento="Seleziona la foto del documento da caricare")
async def carica_foto_documento(
    interaction: discord.Interaction, documento: discord.Attachment
):
    # Controllo che il file allegato sia un'immagine
    if not documento.content_type or not documento.content_type.startswith("image/"):
        await interaction.response.send_message(
            "⚠️ Per favore, allega un file immagine valido.", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        discord_id = str(interaction.user.id)

        # 1. Verifica preventiva: l'utente ha compilato prima la modale?
        existing = supabase.table("documents").select("discord_id").eq("discord_id", discord_id).execute()
        
        if not existing.data:
            await interaction.followup.send(
                "❌ **Nessuna anagrafica trovata!**\n"
                "Prima di caricare la foto, devi compilare il modulo anagrafico tramite il pannello.",
                ephemeral=True
            )
            return

        # 2. Carica la foto su ImgBB usando la tua funzione
        photo_url = await upload_to_imgbb(documento)

        # 3. Aggiorna unicamente il campo photo_url per quell'utente nel database
        supabase.table("documents").update({"photo_url": photo_url}).eq("discord_id", discord_id).execute()

        await interaction.followup.send(
            f"✅ **Foto del documento caricata e associata con successo!**\n🔗 **URL:** {photo_url}",
            ephemeral=True,
        )

    except Exception as e:
        await interaction.followup.send(
            f"❌ Si è verificato un errore durante il caricamento: {e}",
            ephemeral=True,
        )

# --- SHOP OS ---

class ShopCategorySelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Armi", description="Acquista armi e munizioni", emoji="🔫", value="armi"),
            discord.SelectOption(label="Mediche", description="Kit medici e bende", emoji="💊", value="mediche"),
            discord.SelectOption(label="Generale", description="Oggetti vari e utility", emoji="🎒", value="generale"),
        ]
        super().__init__(placeholder="📂 Seleziona una categoria...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        categoria = self.values[0]
        
        res = supabase.table("custom_items").select("*").eq("category", categoria).execute()
        items = res.data if res.data else []

        embed = discord.Embed(
            title=f"🛒 Evren Shop - Categoria: {categoria.capitalize()}",
            description="Ecco gli articoli disponibili in questa categoria. Usa il comando `/compra [nome_item]` per acquistarli.",
            color=discord.Color.blue()
        )

        if not items:
            embed.add_field(name="Vuoto", value="Non ci sono oggetti in questa categoria al momento.", inline=False)
        else:
            for item in items:
                nome = item.get("name", "Oggetto")
                prezzo = item.get("price", 0)
                ruolo_req = item.get("required_role_id", "Nessuno")
                embed.add_field(
                    name=f"🔹 {nome}",
                    value=f"💰 Prezzo: **€ {prezzo:,.2f}**\n🔒 Ruolo richiesto: `{ruolo_req}`",
                    inline=False
                )

        embed.set_footer(text="Evren City OS • Economia")
        await interaction.response.edit_message(embed=embed, view=self.view)


class ShopView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ShopCategorySelect())


@bot.tree.command(name="shop", description="Visualizza lo store di Evren City OS e naviga tra le categorie.")
async def shop(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 Evren City OS - Negozio Generale",
        description="Benvenuto nello shop ufficiale. Seleziona una categoria dal menu sottostante per visualizzare gli articoli in vendita.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Evren City OS • Economia")
    
    view = ShopView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def shop_item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("custom_items").select("name").ilike("name", f"%{current}%").limit(25).execute()
    items = res.data if res.data else []
    return [app_commands.Choice(name=i["name"], value=i["name"]) for i in items]


import random
import string

import discord
from discord import app_commands


@bot.tree.command(
    name="me", description="Esegui un'azione in roleplay (stile /me)"
)
@app_commands.describe(azione="Descrivi l'azione che stai compiendo")
async def me(interaction: discord.Interaction, azione: str):
  # Elimina l'interazione in modo che l'utente non veda il messaggio "Ephemeral" o il caricamento prolungato
  await interaction.response.defer(thinking=True)
  await interaction.delete_original_response()

  # Costruisce l'embed identico allo stile dell'immagine
  embed = discord.Embed(
      description=f"🎬 **Azione** <a:attesa:1349897098258284594>\n\n{interaction.user.mention} = {azione}",
      color=discord.Color.from_rgb(
          40, 40, 45
      ),  # Sfumatura scura pulita in stile Discord
  )

  # Footer con il nome del server o del progetto roleplay
  embed.set_footer(text="EvrenCity® Roleplay シ • OG Edition")

  # Invia il messaggio direttamente nel canale in cui è stato eseguito il comando
  await interaction.channel.send(embed=embed)

@bot.tree.command(name="compra", description="Acquista un oggetto dallo shop verificando fondi e requisiti.")
@app_commands.describe(item="Nome dell'oggetto da acquistare")
@app_commands.autocomplete(item=shop_item_autocomplete)
async def compra(interaction: discord.Interaction, item: str):
    user = interaction.user
    user_id = str(user.id)

    res_item = supabase.table("custom_items").select("*").ilike("name", item).execute()
    if not res_item.data:
        await interaction.response.send_message("❌ L'oggetto selezionato non esiste nello shop.", ephemeral=True)
        return

    item_data = res_item.data[0]
    prezzo = item_data.get("price", 0)
    required_role_id = item_data.get("required_role_id")
    item_name = item_data.get("name")
    category = item_data.get("category", "Generale")
    weight = item_data.get("weight", 0.1)

    if required_role_id:
        if not any(r.id == int(required_role_id) for r in user.roles):
            await interaction.response.send_message(f"❌ Non possiedi il ruolo richiesto per poter acquistare **{item_name}**.", ephemeral=True)
            return

    res_user = supabase.table("users").select("wallet").eq("discord_id", user_id).execute()
    contanti_attuali = res_user.data[0].get("wallet", 0) if res_user.data else 0

    if contanti_attuali < prezzo:
        await interaction.response.send_message(
            f"❌ Fondi insufficienti! Hai **€ {contanti_attuali:,.2f}**, ma l'oggetto costa **€ {prezzo:,.2f}**.",
            ephemeral=True
        )
        return
    
    nome_finale_oggetto = item_name
    matricola_testo = ""

    # Usiamo direttamente 'category' (con la c minuscola) che hai definito all'inizio della funzione
    if category.lower() in ["armi", "arma"]:
        parte1 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
        parte2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
        matricola = f"{parte1}-{parte2}"
        
        nome_finale_oggetto = f"{item_name} [{matricola}]"
        matricola_testo = f"\nMatricola: **{matricola}**"

    nuovo_saldo = contanti_attuali - prezzo
    supabase.table("users").update({"wallet": nuovo_saldo}).eq("discord_id", user_id).execute()

    supabase.table("inventory").insert({
        "discord_id": user_id,
        "item_name": nome_finale_oggetto,
        "category": category,
        "weight": weight,
        "quantity": 1
    }).execute()

    await interaction.response.send_message(
        f"✅ Acquisto effettuato con successo!\n"
        f"Hai comprato: **{nome_finale_oggetto}** per **€ {prezzo:,.2f}**."
        f"{matricola_testo}\n"
        f"Nuovo saldo contanti: **€ {nuovo_saldo:,.2f}**",
        ephemeral=True
    )

import discord
from discord import ui
import asyncio
import random

# Assicurati che 'supabase', 'bot', 'RUOLO_RICHIESTO_ID' e 'riproduci_audio_canale' siano già definiti nel tuo progetto principale.

# ==========================================
# 📱 TELEFONO E RUBRICA
# ==========================================

class AggiungiContattoModal(ui.Modal, title="Nuovo Contatto - Evren City OS"):
    nome_contatto = ui.TextInput(
        label="Nome del Contatto",
        placeholder="Es. Mario Rossi",
        required=True,
        max_length=50
    )
    numero_contatto = ui.TextInput(
        label="Numero di Telefono",
        placeholder="Es. 3331234567",
        required=True,
        max_length=15
    )

    def __init__(self, phone_view):
        super().__init__()
        self.phone_view = phone_view

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        try:
            supabase.table("contacts").insert({
                "owner_id": user_id,
                "name": self.nome_contatto.value.strip(),
                "phone_number": self.numero_contatto.value.strip()
            }).execute()

            # Aggiorna la vista del telefono in tempo reale
            self.phone_view.aggiorna_selettori()
            await interaction.response.edit_message(view=self.phone_view)
            
            await interaction.followup.send(
                f"✅ Contatto **{self.nome_contatto.value}** (`{self.numero_contatto.value}`) salvato con successo!",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore durante il salvataggio del contatto: {e}", ephemeral=True)


# ==========================================
# 💬 WHATSAPP - CHAT PERSISTENTE AL 100%
# ==========================================

class WhatsAppMessageModal(ui.Modal, title="WhatsApp - Invia Messaggio"):
    testo_messaggio = ui.TextInput(
        label="Messaggio",
        placeholder="Scrivi qui il messaggio...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    def __init__(self, user_phone: str, target_phone: str, target_name: str, chat_view):
        super().__init__()
        self.user_phone = user_phone
        self.target_phone = target_phone
        self.target_name = target_name
        self.chat_view = chat_view

    async def on_submit(self, interaction: discord.Interaction):
        testo = self.testo_messaggio.value.strip()
        
        try:
            supabase.table("whatsapp_messages").insert({
                "sender_phone": self.user_phone,
                "receiver_phone": self.target_phone,
                "message": testo
            }).execute()

            await self.chat_view.aggiorna_embed_chat(interaction)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore nell'invio del messaggio: {e}", ephemeral=True)


class WhatsAppChatView(ui.View):
    def __init__(self, user_phone: str, target_phone: str, target_name: str):
        super().__init__(timeout=300)
        self.user_phone = user_phone
        self.target_phone = target_phone
        self.target_name = target_name

    @ui.button(label="Invia Messaggio", style=discord.ButtonStyle.green, emoji="💬")
    async def invia_messaggio(self, interaction: discord.Interaction, button: ui.Button):
        modal = WhatsAppMessageModal(self.user_phone, self.target_phone, self.target_name, self)
        await interaction.response.send_modal(modal)

    @ui.button(label="Aggiorna Chat", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def aggiorna_chat(self, interaction: discord.Interaction, button: ui.Button):
        await self.aggiorna_embed_chat(interaction)

    async def aggiorna_embed_chat(self, interaction: discord.Interaction):
        user_clean = "".join(filter(str.isdigit, self.user_phone))
        target_clean = "".join(filter(str.isdigit, self.target_phone))

        res = supabase.table("whatsapp_messages").select("*").order("created_at", desc=False).limit(50).execute()
        
        tutti_messaggi = res.data if res.data else []
        messaggi = []

        for m in tutti_messaggi:
            s_clean = "".join(filter(str.isdigit, m["sender_phone"]))
            r_clean = "".join(filter(str.isdigit, m["receiver_phone"]))
            
            if (s_clean == user_clean and r_clean == target_clean) or (s_clean == target_clean and r_clean == user_clean):
                messaggi.append(m)

        messaggi = messaggi[-10:]
        
        descrizione = f"*Cronologia messaggi con **{self.target_name}** (`{self.target_phone}`)*\n\n"
        if not messaggi:
            descrizione += "_Nessun messaggio in questa chat. Inizia a scrivere!_"
        else:
            for m in messaggi:
                m_sender_clean = "".join(filter(str.isdigit, m["sender_phone"]))
                mittente = "Tu" if m_sender_clean == user_clean else self.target_name
                descrizione += f"**{mittente}:** {m['message']}\n"

        embed = discord.Embed(
            title=f"💬 WhatsApp — Chat con {self.target_name}",
            description=descrizione,
            color=discord.Color.from_rgb(37, 211, 102)
        )
        
        if interaction.response.is_done():
            await interaction.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

# ==========================================
# 🌐 SOCIAL MEDIA INTEGRATI (EvrenGram / EvrenBird)
# ==========================================

class CreaPostSocialModal(ui.Modal, title="Crea un Post sui Social"):
    contenuto_post = ui.TextInput(
        label="A cosa stai pensando?",
        placeholder="Scrivi il tuo post...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=280
    )

    def __init__(self, social_view, platform_name: str):
        super().__init__()
        self.social_view = social_view
        self.platform_name = platform_name

    async def on_submit(self, interaction: discord.Interaction):
        user_name = interaction.user.display_name
        user_id = str(interaction.user.id)
        
        try:
            supabase.table("social_posts").insert({
                "platform": self.platform_name,
                "author_id": user_id,
                "author_name": user_name,
                "content": self.contenuto_post.value.strip()
            }).execute()

            await self.social_view.aggiorna_feed(interaction)
            await interaction.followup.send("✅ Post pubblicato con successo nel feed!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore durante la pubblicazione: {e}", ephemeral=True)


class SocialMediaView(ui.View):
    def __init__(self, user_id: str, platform_name: str = "EvrenGram"):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.platform_name = platform_name

    @ui.button(label="EvrenGram 📸", style=discord.ButtonStyle.secondary)
    async def switch_gram(self, interaction: discord.Interaction, button: ui.Button):
        self.platform_name = "EvrenGram"
        await self.aggiorna_feed(interaction)

    @ui.button(label="EvrenBird 🐦", style=discord.ButtonStyle.secondary)
    async def switch_bird(self, interaction: discord.Interaction, button: ui.Button):
        self.platform_name = "EvrenBird"
        await self.aggiorna_feed(interaction)

    @ui.button(label="Nuovo Post ✍️", style=discord.ButtonStyle.success, row=1)
    async def nuovo_post(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreaPostSocialModal(self, self.platform_name))

    async def aggiorna_feed(self, interaction: discord.Interaction):
        res = supabase.table("social_posts") \
            .select("*") \
            .eq("platform", self.platform_name) \
            .order("created_at", desc=True) \
            .limit(5) \
            .execute()
        
        posts = res.data if res.data else []
        
        embed = discord.Embed(
            title=f"🌐 Social Network — {self.platform_name}",
            description=f"*Esplora gli ultimi post condivisi dai cittadini su {self.platform_name}.*",
            color=discord.Color.blue() if self.platform_name == "EvrenGram" else discord.Color.from_rgb(29, 161, 242)
        )

        if not posts:
            embed.add_field(name="Feed Vuoto", value="Nessun post recente. Sii il primo a scriverne uno!", inline=False)
        else:
            for p in posts:
                embed.add_field(
                    name=f"@{p['author_name']}",
                    value=p["content"],
                    inline=False
                )

        if interaction.response.is_done():
            await interaction.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ==========================================
# 📞 GESTIONE CHIAMATE E INTERFACCIA PRINCIPALE
# ==========================================

class RispondiChiamataView(ui.View):
    def __init__(self, chiamante: discord.Member, destinatario: discord.Member, channel: discord.VoiceChannel, task_squillo: asyncio.Task):
        super().__init__(timeout=120)
        self.chiamante = chiamante
        self.destinatario = destinatario
        self.channel = channel
        self.task_squillo = task_squillo
        self.risposta_data = False

    @ui.button(label="Rispondi", style=discord.ButtonStyle.green, emoji="📞")
    async def rispondi(self, interaction: discord.Interaction, button: ui.Button):
        self.risposta_data = True
        self.stop()
        
        if not self.task_squillo.done():
            self.task_squillo.cancel()
        
        voice_link = self.channel.jump_url
        
        await interaction.response.edit_message(
            content=f"✅ Hai accettato la chiamata con **{self.chiamante.display_name}**.\n\n🔊 **Entra subito nel canale vocale:** {voice_link}", 
            view=None
        )
        
        try:
            await self.chiamante.send(f"📞 **{self.destinatario.display_name}** ha risposto alla chiamata!\n🔊 Entra nel canale vocale: {voice_link}")
        except Exception:
            pass

    @ui.button(label="Rifiuta", style=discord.ButtonStyle.red, emoji="❌")
    async def rifiuta(self, interaction: discord.Interaction, button: ui.Button):
        self.risposta_data = False
        self.stop()
        
        if not self.task_squillo.done():
            self.task_squillo.cancel()
        
        await interaction.response.edit_message(
            content=f"❌ Hai rifiutato la chiamata da **{self.chiamante.display_name}**.", 
            view=None
        )
        
        try:
            await self.chiamante.send(f"❌ **{self.destinatario.display_name}** ha rifiutato la chiamata.")
        except Exception:
            pass

        await riproduci_audio_canale(self.channel, "rifiuto.mp3", loop=False)
        try:
            await self.channel.delete()
        except Exception:
            pass

    async def on_timeout(self):
        if not self.risposta_data:
            if not self.task_squillo.done():
                self.task_squillo.cancel()
            try:
                await riproduci_audio_canale(self.channel, "rifiuto.mp3", loop=False)
                await self.chiamante.send(f"⌛ La chiamata a **{self.destinatario.display_name}** è scaduta (nessuna risposta).")
                await self.channel.delete()
            except Exception:
                pass

class EvrenPhoneView(ui.View):
    def __init__(self, user_id: str, phone_number: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.phone_number = phone_number
        self.aggiorna_selettori()

    def aggiorna_selettori(self):
        self.clear_items()
        
        res = supabase.table("contacts").select("*").eq("owner_id", self.user_id).execute()
        contacts = res.data if res.data else []

        btn_aggiungi = ui.Button(label="Nuovo Contatto", style=discord.ButtonStyle.blurple, emoji="➕", row=0)
        btn_aggiungi.callback = self.apri_modal_contatto
        self.add_item(btn_aggiungi)

        btn_social = ui.Button(label="Apri Social", style=discord.ButtonStyle.secondary, emoji="🌐", row=0)
        btn_social.callback = self.apri_social_callback
        self.add_item(btn_social)

        if contacts:
            options = [
                discord.SelectOption(
                    label=c["name"], 
                    description=c["phone_number"], 
                    value="".join(filter(str.isdigit, c["phone_number"]))
                ) 
                for c in contacts[:25]
            ]
            
            select_chiama = ui.Select(placeholder="📞 Seleziona contatto da chiamare", options=options, row=1)
            select_chiama.callback = self.avvia_chiamata_callback
            self.add_item(select_chiama)

            select_wa = ui.Select(placeholder="💬 Apri chat WhatsApp", options=options, row=2)
            select_wa.callback = self.apri_whatsapp_callback
            self.add_item(select_wa)

    async def apri_modal_contatto(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AggiungiContattoModal(self))

    async def apri_social_callback(self, interaction: discord.Interaction):
        social_view = SocialMediaView(self.user_id)
        res = supabase.table("social_posts").select("*").eq("platform", "EvrenGram").order("created_at", desc=True).limit(5).execute()
        posts = res.data if res.data else []
        
        embed = discord.Embed(
            title="🌐 Social Network — EvrenGram",
            description="*Esplora gli ultimi post condivisi dai cittadini.*",
            color=discord.Color.blue()
        )
        if not posts:
            embed.add_field(name="Feed Vuoto", value="Nessun post recente.", inline=False)
        else:
            for p in posts:
                embed.add_field(name=f"@{p['author_name']}", value=p["content"], inline=False)

        await interaction.response.send_message(embed=embed, view=social_view, ephemeral=True)

    async def avvia_chiamata_callback(self, interaction: discord.Interaction):
        numero = interaction.data["values"][0]
        await interaction.response.defer(ephemeral=True)
        await avvia_chiamata_vocale(interaction, numero)

    async def apri_whatsapp_callback(self, interaction: discord.Interaction):
        numero_selezionato = interaction.data["values"][0]
        numero_pulito = "".join(filter(str.isdigit, numero_selezionato))

        res = supabase.table("contacts").select("phone_number, name").eq("owner_id", self.user_id).execute()
        
        nome_destinatario = numero_selezionato
        target_phone = numero_selezionato
        
        if res.data:
            for c in res.data:
                if "".join(filter(str.isdigit, c["phone_number"])) == numero_pulito:
                    nome_destinatario = c["name"]
                    target_phone = c["phone_number"]
                    break

        view = WhatsAppChatView(self.phone_number, target_phone, nome_destinatario)
        await view.aggiorna_embed_chat(interaction)


async def avvia_chiamata_vocale(interaction: discord.Interaction, numero_destinatario: str):
    guild = interaction.guild
    chiamante = interaction.user

    numero_pulito = "".join(filter(str.isdigit, numero_destinatario))

    res = supabase.table("user_phones").select("discord_id, phone_number").execute()
    
    target_discord_id = None
    if res.data:
        for row in res.data:
            if "".join(filter(str.isdigit, row["phone_number"])) == numero_pulito:
                target_discord_id = row["discord_id"]
                break

    if not target_discord_id:
        await interaction.followup.send("❌ Il numero digitato non è attivo o non appartiene a nessun cittadino registrato.", ephemeral=True)
        return

    destinatario = guild.get_member(int(target_discord_id))
    
    if not destinatario:
        await interaction.followup.send("❌ L'utente chiamato non è reperibile nel server.", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False),
        chiamante: discord.PermissionOverwrite(connect=True, speak=True),
        destinatario: discord.PermissionOverwrite(connect=True, speak=True)
    }
    
    nome_canale = f"Chiamata ({chiamante.display_name}) -> ({destinatario.display_name})"
    categoria = interaction.channel.category if hasattr(interaction.channel, 'category') else None
    
    voice_channel = await guild.create_voice_channel(name=nome_canale, category=categoria, overwrites=overwrites)
    voice_link = voice_channel.jump_url

    # Task dello squillo in background (indentato correttamente)
    task_squillo = asyncio.create_task(riproduci_audio_canale(voice_channel, URL_SQUILLO, loop=True))

    view = RispondiChiamataView(chiamante, destinatario, voice_channel, task_squillo)
    
    try:
        await destinatario.send(
            f"📱 **CHIAMATA IN ARRIVO**\nStai ricevendo una chiamata da **{chiamante.display_name}**.\nHai 2 minuti per rispondere:",
            view=view
        )
    except Exception:
        if not task_squillo.done():
            task_squillo.cancel()
        await voice_channel.delete()
        await interaction.followup.send("❌ Impossibile inviare il DM al destinatario (potrebbe averli chiusi).", ephemeral=True)
        return

    await interaction.followup.send(
        f"📞 Squillo in corso verso **{destinatario.display_name}**...\n🔊 **Entra nel canale vocale per attendere:** {voice_link}", 
        ephemeral=True
    )



@bot.tree.command(name="telefono", description="Apre lo schermo del tuo smartphone di Evren City OS.")
async def telefono(interaction: discord.Interaction):
    if RUOLO_RICHIESTO_ID is not None:
        ruolo = interaction.guild.get_role(RUOLO_RICHIESTO_ID)
        if not ruolo or ruolo not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ **Accesso Negato:** Non possiedi il ruolo necessario per utilizzare lo smartphone.", 
                ephemeral=True
            )
            return

    user_id = str(interaction.user.id)
    res = supabase.table("user_phones").select("phone_number").eq("discord_id", user_id).execute()
    
    if not res.data or len(res.data) == 0:
        while True:
            area_code = random.randint(200, 999)
            central_office = random.randint(200, 999)
            line_number = random.randint(1000, 9999)
            numero_casuale = f"+1 ({area_code}) {central_office}-{line_number}"
            
            check_exist = supabase.table("user_phones").select("phone_number").eq("phone_number", numero_casuale).execute()
            if not check_exist.data or len(check_exist.data) == 0:
                break
        
        try:
            supabase.table("user_phones").insert({
                "discord_id": user_id,
                "phone_number": numero_casuale
            }).execute()
            phone_number = numero_casuale
        except Exception:
            phone_number = "Errore di generazione"
    else:
        phone_number = res.data[0]["phone_number"]

    view = EvrenPhoneView(user_id, phone_number)
    
    embed = discord.Embed(
        title="📱 Evren City OS — Smartphone",
        description="*Benvenuto nel tuo terminale personale. Gestisci contatti, chatta su WhatsApp e naviga sui Social Network.*",
        color=discord.Color.from_rgb(40, 167, 69)
    )
    embed.add_field(name="📞 Il tuo Numero", value=f"`{phone_number}`", inline=False)
    embed.set_footer(text=f"Utente: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --- RICONOSCIMENTO BIOMETRICO ---

@bot.tree.command(name="cerca_foto", description="[Riservato Polizia] Riconosce un cittadino dalla foto tramite scansione AI remota.")
@app_commands.describe(foto="Carica la foto o il documento da analizzare")
async def cerca_foto(interaction: discord.Interaction, foto: discord.Attachment):
    ruolo_polizia = interaction.guild.get_role(RUOLO_POLIZIA_ID)
    
    if not ruolo_polizia or ruolo_polizia not in interaction.user.roles:
        await interaction.response.send_message(
            "❌ **Accesso Negato:** Questo comando è riservato esclusivamente alle Forze dell'Ordine.", 
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    url_foto_utente = foto.url
    sito_vercel = "https://bot-kiwonuwy1-elmatador737373-makers-projects.vercel.app"
    url_target = f"{sito_vercel}/?url={url_foto_utente}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(url_target, wait_until="networkidle")

            try:
                await page.wait_for_selector("#result", timeout=60000)
                await page.wait_for_function(
                    "document.getElementById('result').innerText.startsWith('{') || document.getElementById('status').innerText.includes('❌')",
                    timeout=50000
                )
            except Exception:
                await interaction.followup.send("❌ **Tempo scaduto:** L'analisi biometrica e il confronto su Supabase hanno impiegato troppo tempo.", ephemeral=True)
                await browser.close()
                return

            contenuto_div = await page.inner_text("#result")
            status_div = await page.inner_text("#status")
            await browser.close()

        if "❌" in status_div and not contenuto_div.startswith("{"):
            await interaction.followup.send(f"❌ Errore dal server biometrico: {status_div}", ephemeral=True)
            return

        dati_risultato = json.loads(contenuto_div)

    except Exception as e:
        await interaction.followup.send(f"❌ Errore di comunicazione con il motore biometrico: {e}", ephemeral=True)
        return

    status = dati_risultato.get("status")

    if status == "not_found":
        await interaction.followup.send("❌ **Riconoscimento fallito:** Nessun volto rilevato nell'immagine caricata.", ephemeral=True)
        return
    
    if status == "not_matched":
        await interaction.followup.send("❌ **Nessun riscontro:** Il volto non corrisponde a nessun cittadino registrato nel database.", ephemeral=True)
        return

    if status == "error":
        msg_err = dati_risultato.get("message", "Errore sconosciuto")
        await interaction.followup.send(f"❌ Errore interno del motore IA: {msg_err}", ephemeral=True)
        return

    if status == "success":
        match = dati_risultato.get("match", {})
        distanza = dati_risultato.get("distance", 0)

        nome_cittadino = match.get("name", "Sconosciuto")
        codice_fiscale = match.get("fiscal_code", match.get("id", "N/D"))

        embed = discord.Embed(
            title="🔍 Esito Scansione Biometrica",
            description="**Match trovato nel database centrale di Evren City!**",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Cittadino Identificato", value=f"`{nome_cittadino}`", inline=False)
        embed.add_field(name="📄 Riferimento / ID", value=f"`{codice_fiscale}`", inline=True)
        embed.add_field(name="📊 Affidabilità Match", value=f"`{round((1 - distanza) * 100, 1)}%`", inline=True)
        embed.set_footer(text="Evren City OS — Sicurezza e Giustizia")

        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    await interaction.followup.send("❌ Risposta imprevista dal server biometrico.", ephemeral=True)


@bot.event
async def on_member_join(member: discord.Member):
    welcome_text = (
        "✦ **BENVENUTO SU EVREN!** ✦\n"
        "Ecco i passaggi fondamentali per iniziare la tua avventura:\n\n"
        "> 🔓 **1. Sblocco Canali**\n"
        "> Se non vedi tutti i canali, segui la guida iniziale premendo **Bottone N1** per sbloccarli.\n> \n"
        "> 📜 **2. Regolamenti**\n"
        "> Leggi le linee guida nei canali associati a **Bottone N2**, **Bottone N3** e **Bottone N4** per conoscere le regole del server.\n> \n"
        "> 📝 **3. Background**\n"
        "> Scrivi la storia del tuo personaggio seguendo i modelli nella sezione **Bottone N5**.\n> \n"
        "> 🛡️ **4. Whitelist (WL)**\n"
        "> Invia la tua richiesta di WL nel canale **Bottone N6** per completare l'accesso e iniziare a giocare.\n> \n"
        "Hai dubbi o domande? Lo staff è sempre a tua disposizione. Buon divertimento! ✨"
    )

    try:
        await member.send(content=welcome_text, view=WelcomeButtonsView())
    except discord.Forbidden:
        print(f"⚠️ Impossibile inviare il DM di benvenuto a {member.display_name} (DM chiusi).")
    except Exception as e:
        print(f"❌ Errore durante l'invio del messaggio di benvenuto: {e}")


@bot.tree.command(name="registra_fazione", description="[STAFF] Registra una nuova fazione e il suo ruolo autorizzato.")
@app_commands.describe(
    fazione="Nome della fazione da registrare",
    ruolo="Ruolo di Discord associato alla fazione"
)
@app_commands.checks.has_permissions(administrator=True)
async def registra_fazione(interaction: discord.Interaction, fazione: str, ruolo: discord.Role):
    
    # 1. Verifica se la fazione esiste già nel database
    check_res = supabase.table("faction_roles").select("faction_name").eq("faction_name", fazione).execute()
    
    if check_res.data:
        await interaction.response.send_message(f"❌ La fazione **{fazione}** risulta già registrata nel sistema.", ephemeral=True)
        return

    try:
        # 2. Inserisce la fazione e il role_id nella tabella faction_roles
        supabase.table("faction_roles").insert({
            "faction_name": fazione,
            "role_id": str(ruolo.id)
        }).execute()

        # 3. Inizializza anche il deposito vuoto nella tabella faction_vaults
        supabase.table("faction_vaults").upsert({
            "faction_name": fazione,
            "cash_balance": 0.0,
            "items_list": "Deposito vuoto."
        }).execute()

        await interaction.response.send_message(f"✅ Fazione **{fazione}** registrata con successo! Ruolo associato: {ruolo.mention}", ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Si è verificato un errore durante la registrazione: `{e}`", ephemeral=True)

# Gestione dell'errore se un utente senza permessi prova ad usarlo
@registra_fazione.error
async def registra_fazione_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Non hai i permessi necessari per utilizzare questo comando.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Errore imprevisto: `{error}`", ephemeral=True)

async def fazione_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
  try:
    # Interroga la tabella per ottenere tutte le fazioni registrate
    res = supabase.table("faction_roles").select("faction_name").execute()

    if not res.data:
      return []

    # Estrae i nomi unici delle fazioni
    fazioni = list(set(row["faction_name"] for row in res.data))

    # Filtra le fazioni in base a ciò che l'utente sta digitando (current)
    filtered = [f for f in fazioni if current.lower() in f.lower()]

    # Restituisce le scelte formattate per Discord (massimo 25)
    return [app_commands.Choice(name=f, value=f) for f in filtered[:25]]
  except Exception:
    return []

# --- PORTAFOGLIO ED OGGETTI ---

@bot.tree.command(name="portafoglio", description="Visualizza i contanti e lo stato del tuo portafoglio su Evren City OS.")
async def portafoglio(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    # Assicura che l'utente esista nel database
    get_or_create_user(user_id, interaction.user.name)
    
    res = supabase.table("users").select("wallet").eq("discord_id", user_id).execute()
    
    contanti = 0
    if res.data and len(res.data) > 0:
        contanti = res.data[0].get("wallet", 0)

    embed = discord.Embed(
        title="💼 Portafoglio - Evren City OS",
        description="Ecco il riepilogo del tuo denaro contante.",
        color=discord.Color.green()
    )
    embed.add_field(name="💵 Contanti", value=f"**€ {contanti:,.2f}**", inline=False)
    embed.set_footer(text="Evren City OS • Sistema Finanziario")

    await interaction.response.send_message(embed=embed, ephemeral=True)

import discord
from difflib import get_close_matches


# --- MODALS PER I INPUT UTENTE ---
class DepositCashModal(discord.ui.Modal, title="Deposita Denaro in Cassa"):

  amount = discord.ui.TextInput(
      label="Importo da depositare (€)",
      placeholder="Es. 5000",
      required=True,
  )

  def __init__(self, fazione: str):
    super().__init__()
    self.fazione = fazione

  async def on_submit(self, interaction: discord.Interaction):
    try:
      valore = float(self.amount.value)
      if valore <= 0:
        raise ValueError()
    except ValueError:
      await interaction.response.send_message(
          "❌ Inserisci un importo valido.", ephemeral=True
      )
      return

    discord_id = str(interaction.user.id)

    user_res = (
        supabase.table("users")
        .select("wallet")
        .eq("discord_id", discord_id)
        .execute()
    )
    if not user_res.data or user_res.data[0]["wallet"] < valore:
      await interaction.response.send_message(
          "❌ Non hai abbastanza denaro nel portafoglio.", ephemeral=True
      )
      return

    nuovo_wallet = user_res.data[0]["wallet"] - valore
    supabase.table("users").update({"wallet": nuovo_wallet}).eq(
        "discord_id", discord_id
    ).execute()

    vault_res = (
        supabase.table("faction_vaults")
        .select("cash_balance")
        .ilike("faction_name", self.fazione)
        .execute()
    )
    vecchio_saldo = (
        vault_res.data[0]["cash_balance"] if vault_res.data else 0.0
    )
    nuovo_saldo = vecchio_saldo + valore
    supabase.table("faction_vaults").upsert(
        {"faction_name": self.fazione, "cash_balance": nuovo_saldo},
        on_conflict="faction_name",
    ).execute()

    await interaction.response.send_message(
        f"✅ Hai depositato **€ {valore:,.2f}** nella cassa della fazione"
        f" **{self.fazione}**.",
        ephemeral=True,
    )


class WithdrawCashModal(discord.ui.Modal, title="Preleva Denaro dalla Cassa"):

  amount = discord.ui.TextInput(
      label="Importo da prelevare (€)",
      placeholder="Es. 5000",
      required=True,
  )

  def __init__(self, fazione: str):
    super().__init__()
    self.fazione = fazione

  async def on_submit(self, interaction: discord.Interaction):
    try:
      valore = float(self.amount.value)
      if valore <= 0:
        raise ValueError()
    except ValueError:
      await interaction.response.send_message(
          "❌ Inserisci un importo valido.", ephemeral=True
      )
      return

    vault_res = (
        supabase.table("faction_vaults")
        .select("cash_balance")
        .ilike("faction_name", self.fazione)
        .execute()
    )
    if not vault_res.data or vault_res.data[0]["cash_balance"] < valore:
      await interaction.response.send_message(
          "❌ La fazione non ha abbastanza fondi in cassa.", ephemeral=True
      )
      return

    vecchio_saldo = vault_res.data[0]["cash_balance"]
    nuovo_saldo = vecchio_saldo - valore

    supabase.table("faction_vaults").update(
        {"cash_balance": nuovo_saldo}
    ).ilike("faction_name", self.fazione).execute()

    discord_id = str(interaction.user.id)
    user_res = (
        supabase.table("users")
        .select("wallet")
        .eq("discord_id", discord_id)
        .execute()
    )
    wallet_attuale = user_res.data[0]["wallet"] if user_res.data else 0.0
    supabase.table("users").update({"wallet": wallet_attuale + valore}).eq(
        "discord_id", discord_id
    ).execute()

    await interaction.response.send_message(
        f"✅ Hai prelevato **€ {valore:,.2f}** dalla cassa della fazione"
        f" **{self.fazione}**.",
        ephemeral=True,
    )


class DepositItemModal(discord.ui.Modal, title="Deposita Oggetto"):

  item_name = discord.ui.TextInput(
      label="Nome dell'oggetto", placeholder="Es. Pistola", required=True
  )
  quantity = discord.ui.TextInput(
      label="Quantità", placeholder="1", required=True, default="1"
  )

  def __init__(self, fazione: str):
    super().__init__()
    self.fazione = fazione

  async def on_submit(self, interaction: discord.Interaction):
    q_str = self.quantity.value
    input_item = self.item_name.value.strip()

    try:
      quantita = int(q_str)
      if quantita <= 0:
        raise ValueError()
    except ValueError:
      await interaction.response.send_message(
          "❌ Quantità non valida.", ephemeral=True
      )
      return

    discord_id = str(interaction.user.id)

    user_items = (
        supabase.table("inventory")
        .select("*")
        .eq("discord_id", discord_id)
        .execute()
    )
    if not user_items.data:
      await interaction.response.send_message(
          "❌ Il tuo inventario è vuoto.", ephemeral=True
      )
      return

    nomi_disponibili = [row["item_name"] for row in user_items.data]
    simili = get_close_matches(
        input_item, nomi_disponibili, n=1, cutoff=0.4
    )

    if not simili:
      await interaction.response.send_message(
          f"❌ Non possiedi alcun oggetto simile a **{input_item}**.",
          ephemeral=True,
      )
      return

    nome_effettivo = simili[0]
    item_data = next(
        r for r in user_items.data if r["item_name"].lower() == nome_effettivo.lower()
    )

    if item_data["quantity"] < quantita:
      await interaction.response.send_message(
          f"❌ Ne possiedi solo {item_data['quantity']}x di **{nome_effettivo}**.",
          ephemeral=True,
      )
      return

    nuova_q_utente = item_data["quantity"] - quantita
    if nuova_q_utente <= 0:
      supabase.table("inventory").delete().eq("id", item_data["id"]).execute()
    else:
      supabase.table("inventory").update({"quantity": nuova_q_utente}).eq(
          "id", item_data["id"]
      ).execute()

    f_inv = (
        supabase.table("faction_inventory")
        .select("*")
        .ilike("faction_name", self.fazione)
        .ilike("item_name", nome_effettivo)
        .execute()
    )
    if f_inv.data:
      q_esistente = f_inv.data[0]["quantity"]
      supabase.table("faction_inventory").update(
          {"quantity": q_esistente + quantita}
      ).eq("id", f_inv.data[0]["id"]).execute()
    else:
      supabase.table("faction_inventory").insert({
          "faction_name": self.fazione,
          "item_name": item_data["item_name"],
          "category": item_data["category"],
          "weight": item_data["weight"],
          "quantity": quantita,
      }).execute()

    msg = f"✅ Hai depositato **{quantita}x {item_data['item_name']}**"
    if input_item.lower() != nome_effettivo.lower():
      msg += f" *(cercando '{input_item}', trovato '{nome_effettivo}')*"
    await interaction.response.send_message(msg, ephemeral=True)


class WithdrawItemModal(discord.ui.Modal, title="Preleva Oggetto"):

  item_name = discord.ui.TextInput(
      label="Nome dell'oggetto", placeholder="Es. Pistola", required=True
  )
  quantity = discord.ui.TextInput(
      label="Quantità", placeholder="1", required=True, default="1"
  )

  def __init__(self, fazione: str):
    super().__init__()
    self.fazione = fazione

  async def on_submit(self, interaction: discord.Interaction):
    q_str = self.quantity.value
    input_item = self.item_name.value.strip()

    try:
      quantita = int(q_str)
      if quantita <= 0:
        raise ValueError()
    except ValueError:
      await interaction.response.send_message(
          "❌ Quantità non valida.", ephemeral=True
      )
      return

    faction_items = (
        supabase.table("faction_inventory")
        .select("*")
        .ilike("faction_name", self.fazione)
        .execute()
    )
    if not faction_items.data:
      await interaction.response.send_message(
          "❌ Il deposito della fazione è vuoto.", ephemeral=True
      )
      return

    nomi_disponibili = [row["item_name"] for row in faction_items.data]
    simili = get_close_matches(
        input_item, nomi_disponibili, n=1, cutoff=0.4
    )

    if not simili:
      await interaction.response.send_message(
          f"❌ Nessun oggetto simile a **{input_item}** nel deposito della"
          " fazione.",
          ephemeral=True,
      )
      return

    nome_effettivo = simili[0]
    f_item = next(
        r for r in faction_items.data if r["item_name"].lower() == nome_effettivo.lower()
    )

    if f_item["quantity"] < quantita:
      await interaction.response.send_message(
          f"❌ La fazione possiede solo {f_item['quantity']}x di"
          f" **{nome_effettivo}**.",
          ephemeral=True,
      )
      return

    nuova_q_fazione = f_item["quantity"] - quantita
    if nuova_q_fazione <= 0:
      supabase.table("faction_inventory").delete().eq(
          "id", f_item["id"]
      ).execute()
    else:
      supabase.table("faction_inventory").update(
          {"quantity": nuova_q_fazione}
      ).eq("id", f_item["id"]).execute()

    discord_id = str(interaction.user.id)
    u_inv = (
        supabase.table("inventory")
        .select("*")
        .eq("discord_id", discord_id)
        .ilike("item_name", nome_effettivo)
        .execute()
    )
    if u_inv.data:
      q_u_esistente = u_inv.data[0]["quantity"]
      supabase.table("inventory").update(
          {"quantity": q_u_esistente + quantita}
      ).eq("id", u_inv.data[0]["id"]).execute()
    else:
      supabase.table("inventory").insert({
          "discord_id": discord_id,
          "item_name": f_item["item_name"],
          "category": f_item["category"],
          "weight": f_item["weight"],
          "quantity": quantita,
      }).execute()

    msg = f"✅ Hai prelevato **{quantita}x {f_item['item_name']}**"
    if input_item.lower() != nome_effettivo.lower():
      msg += f" *(cercando '{input_item}', trovato '{nome_effettivo}')*"
    await interaction.response.send_message(msg, ephemeral=True)


class FactionVaultView(discord.ui.View):

  def __init__(self, fazione: str):
    super().__init__(timeout=None)
    self.fazione = fazione

  @discord.ui.button(
      label="Deposita Soldi",
      style=discord.ButtonStyle.green,
      emoji="💰",
      row=0,
  )
  async def deposit_cash(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(DepositCashModal(self.fazione))

  @discord.ui.button(
      label="Preleva Soldi",
      style=discord.ButtonStyle.red,
      emoji="💸",
      row=0,
  )
  async def withdraw_cash(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(WithdrawCashModal(self.fazione))

  @discord.ui.button(
      label="Deposita Item",
      style=discord.ButtonStyle.blurple,
      emoji="📦",
      row=1,
  )
  async def deposit_item(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(DepositItemModal(self.fazione))

  @discord.ui.button(
      label="Preleva Item",
      style=discord.ButtonStyle.blurple,
      emoji="📤",
      row=1,
  )
  async def withdraw_item(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(WithdrawItemModal(self.fazione))


@bot.tree.command(
    name="deposito_fazione",
    description="Accedi al deposito della tua fazione basato sul tuo ruolo.",
)
@app_commands.describe(fazione="Nome della fazione registrata")
@app_commands.autocomplete(fazione=fazione_autocomplete)
async def deposito_fazione(interaction: discord.Interaction, fazione: str):
  user = interaction.user

  res = (
      supabase.table("faction_roles")
      .select("role_id")
      .ilike("faction_name", fazione)
      .execute()
  )

  if not res.data:
    await interaction.response.send_message(
        f"❌ La fazione **{fazione}** non risulta registrata nel sistema.",
        ephemeral=True,
    )
    return

  role_id = int(res.data[0]["role_id"])

  if not any(r.id == role_id for r in user.roles):
    await interaction.response.send_message(
        "❌ Non possiedi il ruolo autorizzato per accedere a questo deposito.",
        ephemeral=True,
    )
    return

  res_vault = (
      supabase.table("faction_vaults")
      .select("cash_balance")
      .ilike("faction_name", fazione)
      .execute()
  )
  saldo_soldi = (
      res_vault.data[0]["cash_balance"]
      if res_vault.data and res_vault.data[0].get("cash_balance") is not None
      else 0.0
  )

  res_inv = (
      supabase.table("faction_inventory")
      .select("item_name, quantity, category")
      .ilike("faction_name", fazione)
      .execute()
  )

  if res_inv.data:
    lista_item = "\n".join(
        [
            f"- {row['item_name']} (Cat: {row['category']}) x{row['quantity']}"
            for row in res_inv.data
        ]
    )
  else:
    lista_item = "Deposito vuoto."

  embed = discord.Embed(
      title=f"🏛️ Deposito Fazione: {fazione}",
      description=(
          "Gestisci le risorse della fazione tramite i pulsanti sottostanti."
      ),
      color=discord.Color.gold(),
  )
  embed.add_field(
      name="💰 Saldo Cassa", value=f"**€ {saldo_soldi:,.2f}**", inline=False
  )
  embed.add_field(
      name="📦 Inventario Item", value=f"```{lista_item}```", inline=False
  )
  embed.set_footer(text="Evren City OS • Gestione Risorse Fazione")

  view = FactionVaultView(fazione)
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="crea_item", description="[STAFF] Crea un nuovo oggetto con meccaniche specifiche.")
@app_commands.choices(categoria=[
    app_commands.Choice(name="⚔️ Arma", value="arma"),
    app_commands.Choice(name="🍕 Cibo", value="cibo"),
    app_commands.Choice(name="🥤 Bevanda", value="bevanda"),
    app_commands.Choice(name="💊 Medicina", value="medicina"),
    app_commands.Choice(name="🌿 Droga", value="droga"),
    app_commands.Choice(name="🔑 Chiavi", value="chiavi"),
    app_commands.Choice(name="🎒 Zaino", value="zaino"),
    app_commands.Choice(name="🔓 Scassinamento", value="scassinamento")
])
@app_commands.describe(
    nome="Nome dell'oggetto",
    categoria="Categoria dell'oggetto",
    peso="Peso dell'oggetto in kg",
    probabilita_riuscita="Probabilità di riuscita (1-100)",
    capienza_zaino="Capienza extra (solo per zaini)",
    ruolo_richiesto="Ruolo Discord necessario per poter acquistare/usare l'oggetto"
)
async def crea_item(
    interaction: discord.Interaction,
    nome: str,
    categoria: app_commands.Choice[str],
    peso: float,
    ruolo_richiesto: discord.Role,
    probabilita_riuscita: int = 100,
    capienza_zaino: float = 0.0
):
    if RUOLO_STAFF_ID:
        staff_role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if staff_role and staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Comando riservato allo Staff!", ephemeral=True)
            return

    if probabilita_riuscita < 1 or probabilita_riuscita > 100:
        await interaction.response.send_message("❌ La probabilità di riuscita deve essere tra 1% e 100%.", ephemeral=True)
        return

    if categoria.value == "zaino" and capienza_zaino <= 0:
        await interaction.response.send_message("❌ Per la categoria **Zaino**, devi specificare una `capienza_zaino` maggiore di 0.", ephemeral=True)
        return

    item_data = {
        "name": nome,
        "category": categoria.value,
        "weight": max(0.0, round(peso, 2)),
        "probability": float(probabilita_riuscita),
        "backpack_capacity": round(capienza_zaino, 2) if categoria.value == "zaino" else 0.0,
        "required_role_id": str(ruolo_richiesto.id)  # Corretto per corrispondere alla colonna SQL
    }

    try:
        supabase.table("custom_items").insert(item_data).execute()
    except Exception as e:
        await interaction.response.send_message(f"❌ Errore durante la creazione! Nome già in uso o errore DB: `{e}`", ephemeral=True)
        return

    embed = discord.Embed(
        title="✨ Nuovo Oggetto Creato",
        description=f"L'oggetto **{nome}** è stato registrato.",
        color=discord.Color.purple()
    )
    embed.add_field(name="🏷️ Categoria", value=f"`{categoria.name}`", inline=True)
    embed.add_field(name="⚖️ Peso", value=f"`{peso} kg`", inline=True)
    embed.add_field(name="🎲 Probabilità Successo", value=f"`{probabilita_riuscita}%`", inline=True)
    embed.add_field(name="🛡️ Ruolo Richiesto", value=f"{ruolo_richiesto.mention}", inline=False)
    
    if categoria.value == "zaino":
        embed.add_field(name="🎒 Capienza Extra", value=f"`+{capienza_zaino} kg`", inline=False)

    await interaction.response.send_message(embed=embed)

class InventoryUseView(ui.View):
    def __init__(self, user_id: int, user_items: list):
        super().__init__(timeout=120)
        self.user_id = user_id
        
        options = []
        for item in user_items[:25]:
            name = item.get("item_name", "Oggetto")
            cat = item.get("category", "N/D")
            w = item.get("weight", 0.0)
            options.append(discord.SelectOption(
                label=f"{name} (x{item.get('quantity', 1)})",
                value=str(item.get("id")),
                description=f"Cat: {cat.capitalize()} | Peso: {w}kg"
            ))
            
        if options:
            self.select = ui.Select(placeholder="Seleziona un oggetto da usare...", options=options)
            self.select.callback = self.use_item_callback
            self.add_item(self.select)

    async def use_item_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: return

        item_inv_id = int(self.select.values[0])
        res = supabase.table("inventory").select("*").eq("id", item_inv_id).execute()
        if not res.data:
            await interaction.response.send_message("❌ Oggetto non trovato.", ephemeral=True)
            return

        inv_item = res.data[0]
        name = inv_item.get("item_name")
        category = inv_item.get("category")
        
        custom_res = supabase.table("custom_items").select("*").eq("name", name).execute()
        rate = 100
        boost = 0.0
        if custom_res.data:
            rate = custom_res.data[0].get("probability", 100.0)
            boost = custom_res.data[0].get("backpack_capacity", 0.0)

        roll = random.randint(1, 100)
        if roll > rate:
            await interaction.response.send_message(f"❌ **Azione Fallita!** Hai usato **{name}**, ma la prova non è riuscita ({roll}% su {rate}%).", ephemeral=True)
            return

        action_msg = ""
        if category == "cibo":
            action_msg = f"🍕 Hai mangiato **{name}**. Fame ripristinata!"
        elif category == "bevanda":
            action_msg = f"🥤 Hai bevuto **{name}**. Sete placata!"
        elif category == "medicina":
            action_msg = f"💊 Hai usato **{name}**. Ti senti in piena salute!"
        elif category == "droga":
            action_msg = f"🌿 Hai consumato **{name}**. Iniziano i primi effetti..."
        elif category == "chiavi":
            action_msg = f"🔑 Hai sbloccato la serratura con **{name}**."
        elif category == "scassinamento":
            action_msg = f"🔓 **Scassinamento riuscito!** Hai aperto il blocco con **{name}**."
        elif category == "arma":
            action_msg = f"⚔️ Hai impugnato **{name}**."
        elif category == "zaino":
            u_data = get_or_create_user(self.user_id, interaction.user.name)
            curr_max = float(u_data.get("max_weight", 10.0))
            new_max = curr_max + boost
            supabase.table("users").update({"max_weight": new_max}).eq("discord_id", str(self.user_id)).execute()
            action_msg = f"🎒 **Zaino Indossato!** Capienza inventario aumentata di **+{boost} kg** (Totale: `{new_max} kg`)."

        qty = inv_item.get("quantity", 1)
        if qty > 1:
            supabase.table("inventory").update({"quantity": qty - 1}).eq("id", item_inv_id).execute()
        else:
            supabase.table("inventory").delete().eq("id", item_inv_id).execute()

        await interaction.response.send_message(f"✅ {action_msg}", ephemeral=True)


@bot.tree.command(name="inventario", description="Visualizza i tuoi oggetti e il limite di peso.")
async def inventario(interaction: discord.Interaction):
    u_data = get_or_create_user(interaction.user.id, interaction.user.name)
    max_weight = float(u_data.get("max_weight", 10.0))
    current_weight = calculate_user_inventory_weight(interaction.user.id)

    res = supabase.table("inventory").select("*").eq("discord_id", str(interaction.user.id)).execute()

    embed = discord.Embed(
        title=f"🎒 Inventario di {interaction.user.display_name}",
        description=f"⚖️ **Peso Trasportato:** `{current_weight} / {max_weight} kg`",
        color=discord.Color.green() if current_weight <= max_weight else discord.Color.red()
    )

    if res.data:
        for row in res.data:
            name = row.get("item_name", "Oggetto")
            q = row.get("quantity", 1)
            w = row.get("weight", 0.1) * q
            cat = row.get("category", "N/D").capitalize()
            embed.add_field(name=f"📦 {name} x{q}", value=f"└ Cat: `{cat}` | Peso: `{w:.1f}kg`", inline=False)
        
        view = InventoryUseView(interaction.user.id, res.data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
    else:
        embed.description += "\n\n*Il tuo inventario è vuoto.*"
        await interaction.response.send_message(embed=embed, ephemeral=False)


# --- BANCOMAT ---

class DepositModal(ui.Modal, title="💵 Deposito Contanti"):
    amount_input = ui.TextInput(label="Importo ($)", placeholder="Es. 500", required=True)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.amount_input.value.strip())
            if val <= 0: raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Inserisci un importo valido!", ephemeral=True)
            return

        user_data = get_or_create_user(self.user_id, interaction.user.name)
        cash = float(user_data.get("wallet", 0.0))

        if cash < val:
            await interaction.response.send_message(f"❌ Contanti insufficienti! Possiedi `${cash:,.2f}`.", ephemeral=True)
            return

        new_cash = cash - val
        new_bank = float(user_data.get("bank", 0.0)) + val
        supabase.table("users").update({"wallet": new_cash, "bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
        log_transaction(str(self.user_id), "DEPOSITO", val, "Deposito contanti allo sportello")

        embed = discord.Embed(title="💵 Deposito Effettuato", description=f"Hai depositato **${val:,.2f}**.\nNuovo Saldo Banca: **${new_bank:,.2f}**", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)


class WithdrawModal(ui.Modal, title="💸 Prelievo Contanti"):
    amount_input = ui.TextInput(label="Importo ($)", placeholder="Es. 200", required=True)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.amount_input.value.strip())
            if val <= 0: raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Inserisci un importo valido!", ephemeral=True)
            return

        user_data = get_or_create_user(self.user_id, interaction.user.name)
        bank = float(user_data.get("bank", 0.0))

        if bank < val:
            await interaction.response.send_message(f"❌ Saldo insufficiente! Saldo in banca: `${bank:,.2f}`.", ephemeral=True)
            return

        new_bank = bank - val
        new_cash = float(user_data.get("wallet", 0.0)) + val
        supabase.table("users").update({"wallet": new_cash, "bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
        log_transaction(str(self.user_id), "PRELIEVO", val, "Prelievo contanti da bancomat")

        embed = discord.Embed(title="💸 Prelievo Effettuato", description=f"Hai prelevato **${val:,.2f}**.\nNuovo Saldo Banca: **${new_bank:,.2f}**", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TransferModal(ui.Modal, title="📲 Bonifico Bancario"):
    amount_input = ui.TextInput(label="Importo ($)", placeholder="Es. 1000", required=True)
    causale_input = ui.TextInput(label="Causale", placeholder="Es. Acquisto auto", required=False, max_length=100)

    def __init__(self, sender_id: int, target_member: discord.Member):
        super().__init__()
        self.sender_id = sender_id
        self.target_member = target_member

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.amount_input.value.strip())
            if val <= 0: raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Importo non valido!", ephemeral=True)
            return

        sender_data = get_or_create_user(self.sender_id, interaction.user.name)
        sender_bank = float(sender_data.get("bank", 0.0))

        if sender_bank < val:
            await interaction.response.send_message(f"❌ Saldo insufficiente per bonifico di `${val:,.2f}`.", ephemeral=True)
            return

        target_data = get_or_create_user(self.target_member.id, self.target_member.name)
        causale = self.causale_input.value.strip() or "Nessuna causale"

        new_sender_bank = sender_bank - val
        new_target_bank = float(target_data.get("bank", 0.0)) + val

        supabase.table("users").update({"bank": new_sender_bank}).eq("discord_id", str(self.sender_id)).execute()
        supabase.table("users").update({"bank": new_target_bank}).eq("discord_id", str(self.target_member.id)).execute()

        log_transaction(str(self.sender_id), "BONIFICO_INVIATO", val, f"A {self.target_member.display_name} | {causale}")
        log_transaction(str(self.target_member.id), "BONIFICO_RICEVUTO", val, f"Da {interaction.user.display_name} | {causale}")

        embed = discord.Embed(
            title="📲 Bonifico Effettuato",
            description=f"Inviati **${val:,.2f}** a {self.target_member.mention}.\nCausale: `{causale}`",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TransferUserSelectView(ui.View):
    def __init__(self, sender_id: int):
        super().__init__(timeout=60)
        self.sender_id = sender_id

    @ui.select(cls=ui.UserSelect, placeholder="Seleziona il destinatario del bonifico...")
    async def select_user(self, interaction: discord.Interaction, select: ui.UserSelect):
        if interaction.user.id != self.sender_id: return
        target_member = select.values[0]
        if target_member.id == self.sender_id:
            await interaction.response.send_message("❌ Non puoi fare un bonifico a te stesso!", ephemeral=True)
            return
        await interaction.response.send_modal(TransferModal(self.sender_id, target_member))


class AtmMenuView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    @ui.button(label="💵 Deposita", style=discord.ButtonStyle.success, row=0)
    async def btn_dep(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.user_id: await interaction.response.send_modal(DepositModal(self.user_id))

    @ui.button(label="💸 Preleva", style=discord.ButtonStyle.danger, row=0)
    async def btn_with(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.user_id: await interaction.response.send_modal(WithdrawModal(self.user_id))

    @ui.button(label="📲 Bonifico", style=discord.ButtonStyle.primary, row=0)
    async def btn_trf(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.user_id:
            await interaction.response.send_message("👤 Seleziona l'utente destinatario:", view=TransferUserSelectView(self.user_id), ephemeral=True)

    @ui.button(label="📜 Storico", style=discord.ButtonStyle.secondary, row=1)
    async def btn_his(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id: return
        res = supabase.table("transactions_log").select("*").eq("discord_id", str(self.user_id)).order("created_at", desc=True).limit(8).execute()
        embed = discord.Embed(title="📜 Storico Transazioni", color=discord.Color.blue())
        if res.data:
            for tx in res.data:
                icon = "🟢" if "RICEVUTO" in tx['type'] or "DEPOSITO" in tx['type'] else "🔴"
                embed.add_field(name=f"{icon} {tx['type']} - ${tx['amount']:,.2f}", value=f"└ `{tx['description']}`", inline=False)
        else:
            embed.description = "Nessuna transazione."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🚪 Esci", style=discord.ButtonStyle.secondary, row=1)
    async def btn_exit(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.user_id:
            self.stop()
            await interaction.response.edit_message(content="🔒 Sessione Bancomat terminata.", embed=None, view=None)


class PinKeypadView(ui.View):
    def __init__(self, user_id: int, user_data: dict, mode: str = "login"):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.user_data = user_data
        self.mode = mode
        self.entered_pin = ""

    async def update_display(self, interaction: discord.Interaction, text: str):
        masked_pin = "*" * len(self.entered_pin) + "_" * (4 - len(self.entered_pin))
        embed = discord.Embed(title="💳 Tastierino Bancomat", description=f"{text}\n\n**PIN:** `{masked_pin}`", color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=self)

    async def handle_digit(self, interaction: discord.Interaction, digit: str):
        if interaction.user.id != self.user_id: return
        if len(self.entered_pin) < 4: self.entered_pin += digit

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
                    await self.update_display(interaction, "❌ **PIN Errato!** Riprova:")
        else:
            await self.update_display(interaction, "Inserisci il PIN:")

    def _get_dashboard(self):
        u = get_or_create_user(self.user_id, "User")
        return discord.Embed(
            title="🏦 𝗦𝗽𝗼𝗿𝘁𝗲𝗹𝗹𝗼 𝗕𝗮𝗻𝗰𝗼𝗺𝗮𝘁",
            description=f"• **Conto N°:** `ACC-{self.user_id}`\n• **Banca:** `${float(u.get('bank', 0)):,.2f}`\n• **Contanti:** `${float(u.get('wallet', 0)):,.2f}`",
            color=discord.Color.green()
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
        if i.user.id == self.user_id: self.entered_pin = ""; await self.update_display(i, "PIN azzerato:")
    @ui.button(label="0", style=discord.ButtonStyle.secondary, row=3)
    async def b0(self, i: discord.Interaction, b: ui.Button): await self.handle_digit(i, "0")
    @ui.button(label="X", style=discord.ButtonStyle.danger, row=3)
    async def cancel(self, i: discord.Interaction, b: ui.Button):
        if i.user.id == self.user_id: self.stop(); await i.response.edit_message(content="❌ Annullato.", embed=None, view=None)


@bot.tree.command(name="bancomat", description="Accedi allo sportello Bancomat tramite PIN.")
async def bancomat(interaction: discord.Interaction):
    if RUOLO_BANCOMAT_ID:
        role = interaction.guild.get_role(RUOLO_BANCOMAT_ID)
        if role and role not in interaction.user.roles:
            await interaction.response.send_message("❌ Non possiedi una carta bancomat.", ephemeral=True)
            return

    user_data = get_or_create_user(interaction.user.id, interaction.user.name)
    mode = "register" if user_data.get("pin") is None else "login"
    view = PinKeypadView(interaction.user.id, user_data, mode=mode)
    embed = discord.Embed(title="💳 Tastierino Bancomat", description="Inserisci il tuo PIN:\n\n**PIN:** `____`", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

import datetime
import difflib
import discord
from discord import app_commands

# ==========================================
import datetime
import difflib
import discord
from discord import app_commands, ui

# ==========================================
# ⚙️ CONFIGURAZIONE CANALI E TAG PER SERVER
# ==========================================
SERVER_CONFIGS = {
    # 🏢 SERVER 1 (Attivo)
    1233353915559313478: {
        "fines": 1519609832372437034,
        "arrests": 1520010488212361337,
        "reports": 1520010488212361337,
        "seized_vehicles": 1520010510828048395,
        "seized_items": 1520010510828048395,
        "role_tag": "<@&1359569600198611104>",
    },
    # 🏢 SERVER 2 (Attivo)
    1499394373270507701: {
        "fines": 1499398731504685207,
        "arrests": 1499398686067658897,
        "reports": 1499398731504685207,
        "seized_vehicles": 1499398820851744799,
        "seized_items": 1499398780481704046,
        "role_tag": "<@&1363487988570521670>",
    },
}


async def send_standardized_log(
    bot: discord.Client,
    guild_id: int,
    log_type: str,
    name: str,
    surname: str,
    birth_date: str,
    articles: str,
    penalty_det: str,
    penalty_pec: str,
    operators: str,
    notes: str,
    photo_url: str = None,
):
  if guild_id not in SERVER_CONFIGS:
    print(
        f"⚠️ Attenzione: Il server con ID {guild_id} non è configurato in"
        " SERVER_CONFIGS."
    )
    return

  config = SERVER_CONFIGS[guild_id]
  channel_id = config.get(log_type)
  role_tag = config.get("role_tag", "")

  if not channel_id:
    return

  now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

  log_text = (
      f"# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎\n"
      f"> • ɴᴏᴍᴇ: {name}\n\n"
      f"> • ᴄᴏɢɴᴏᴍᴇ: {surname}\n\n"
      f"> • ᴅᴀᴛᴀ ᴅɪ ɴᴀsᴄɪᴛᴀ: {birth_date}\n\n"
      f"> • ᴀʀᴛɪᴄᴏʟᴏ/ɪ ᴄᴏɴᴛᴇsᴛᴀᴛᴏ/ɪ: {articles}\n\n"
      f"> • ᴘᴇɴᴀ ᴅᴇᴛᴇɴᴛɪᴠᴀ: {penalty_det}\n\n"
      f"> • sᴀɴᴢɪᴏɴᴇ ᴘᴇᴄᴜɴɪᴀʀɪᴀ: {penalty_pec}\n\n"
      f"> • ᴅᴀᴛᴀ / ᴏʀᴀ: {now_str}\n\n"
      f"> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: {operators}\n\n"
      f"> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: {notes if notes else 'Nessuna'}\n\n"
      f"> • ᴀʟʟᴇɢᴀ ꜰᴏᴛᴏ\n\n"
      f"{role_tag}"
  )

  embed = discord.Embed(
      description=log_text, color=discord.Color.from_rgb(30, 40, 60)
  )
  if photo_url:
    embed.set_image(url=photo_url)

  try:
    channel = bot.get_channel(channel_id)
    if channel:
      await channel.send(embed=embed)
  except Exception as e:
    print(f"Errore invio log embed [{log_type}] al canale {channel_id}: {e}")


# ==========================================
# 🔍 MODALI DI RICERCA
# ==========================================


class CadSearchPlateModal(ui.Modal, title="🔍 Ricerca Veicolo per Targa"):
  plate_input = ui.TextInput(
      label="Inserisci la Targa", placeholder="Es. AB123CD", required=True
  )

  def __init__(self, officer_id: int, bot: discord.Client):
    super().__init__()
    self.officer_id = officer_id
    self.bot = bot

  async def on_submit(self, interaction: discord.Interaction):
    plate_search = self.plate_input.value.strip().upper()
    res = (
        supabase.table("registered_vehicles")
        .select("*")
        .eq("plate", plate_search)
        .execute()
    )

    if not res.data:
      await interaction.response.send_message(
          f"❌ Nessun veicolo trovato con targa `{plate_search}`.",
          ephemeral=True,
      )
      return

    vehicle = res.data[0]
    owner_id = vehicle.get("discord_id")

    seized_res = (
        supabase.table("seized_vehicles")
        .select("*")
        .eq("plate", plate_search)
        .eq("status", "Sequestrato")
        .execute()
    )

    if seized_res.data:
      vehicle_status = (
          "🚨 **SEQUESTRATO** (Motivo:"
          f" `{seized_res.data[0].get('reason')}`)"
      )
      embed_color = discord.Color.red()
    else:
      vehicle_status = "🟢 **REGOLARE / IN CIRCOLAZIONE**"
      embed_color = discord.Color.dark_green()

    doc_res = (
        supabase.table("documents").select("*").eq("discord_id", owner_id).execute()
    )
    owner_name = (
        f"{doc_res.data[0]['name']} {doc_res.data[0]['surname']}"
        if doc_res.data
        else "Sconosciuto (Senza Documenti)"
    )

    embed = discord.Embed(
        title=f"🚔 CAD - Risultato Ricerca Targa: {plate_search}",
        color=embed_color,
    )
    embed.add_field(
        name="🚗 Modello Veicolo", value=f"`{vehicle.get('model')}`", inline=True
    )
    embed.add_field(name="🏷️ Targa", value=f"`{plate_search}`", inline=True)
    embed.add_field(name="📌 Stato Veicolo", value=vehicle_status, inline=False)
    embed.add_field(
        name="👤 Intestatario RP", value=f"`{owner_name}`", inline=False
    )
    embed.add_field(
        name="🌐 Account Discord", value=f"<@{owner_id}>", inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


class CadSearchSerialModal(ui.Modal, title="🔍 Ricerca Arma per Matricola"):
  serial_input = ui.TextInput(
      label="Inserisci la Matricola", placeholder="Es. WPN-9921", required=True
  )

  def __init__(self, officer_id: int, bot: discord.Client):
    super().__init__()
    self.officer_id = officer_id
    self.bot = bot

  async def on_submit(self, interaction: discord.Interaction):
    serial_search = self.serial_input.value.strip()
    res = (
        supabase.table("registered_weapons")
        .select("*")
        .eq("serial_number", serial_search)
        .execute()
    )

    if not res.data:
      await interaction.response.send_message(
          f"❌ Nessuna arma registrata con matricola `{serial_search}`.",
          ephemeral=True,
      )
      return

    weapon = res.data[0]
    owner_id = weapon.get("discord_id")

    doc_res = (
        supabase.table("documents").select("*").eq("discord_id", owner_id).execute()
    )
    owner_name = (
        f"{doc_res.data[0]['name']} {doc_res.data[0]['surname']}"
        if doc_res.data
        else "Sconosciuto (Senza Documenti)"
    )

    embed = discord.Embed(
        title=f"🚔 CAD - Risultato Ricerca Matricola: {serial_search}",
        color=discord.Color.red(),
    )
    embed.add_field(
        name="⚔️ Modello Arma", value=f"`{weapon.get('model')}`", inline=True
    )
    embed.add_field(name="🔢 Matricola", value=f"`{serial_search}`", inline=True)
    embed.add_field(
        name="👤 Intestatario RP", value=f"`{owner_name}`", inline=False
    )
    embed.add_field(
        name="🌐 Account Discord", value=f"<@{owner_id}>", inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


class SmartSearchCitizenModal(ui.Modal, title="🔎 Ricerca Intelligente Cittadino"):
  name_input = ui.TextInput(
      label="Nome e/o Cognome",
      placeholder="Es. Mario Rossi o solo Mar",
      required=True,
  )

  def __init__(self, citizens_list: list, officer_id: int, bot: discord.Client):
    super().__init__()
    self.citizens_list = citizens_list
    self.officer_id = officer_id
    self.bot = bot

  async def on_submit(self, interaction: discord.Interaction):
    query = self.name_input.value.strip().lower()
    matches = []
    full_names = {}

    for c in self.citizens_list:
      full_name = f"{c.get('name')} {c.get('surname')}".lower()
      full_names[full_name] = c
      if query in full_name:
        matches.append(c)

    if not matches:
      closest = difflib.get_close_matches(
          query, full_names.keys(), n=3, cutoff=0.4
      )
      matches = [full_names[match] for match in closest if match in full_names]

    if not matches:
      await interaction.response.send_message(
          f"❌ Nessun cittadino trovato corrispondente a `{query}`.",
          ephemeral=True,
      )
      return

    if len(matches) == 1:
      doc = matches[0]
      view = PoliceCadDetailView(doc, self.officer_id, self.bot)
      embed = discord.Embed(
          title=(
              "🚔 Terminale Polizia - Risultato:"
              f" {doc.get('name')} {doc.get('surname')}"
          ),
          description=(
              "Usa i pulsanti per consultare la scheda o gestire atti/sequestri:"
          ),
          color=discord.Color.blue(),
      )
      await interaction.response.send_message(
          embed=embed, view=view, ephemeral=True
      )
    else:
      view = PoliceCadSelectView(matches, self.officer_id, self.bot)
      embed = discord.Embed(
          title="🔍 Risultati Ricerca Intelligente",
          description=(
              "Trovati più cittadini simili. Seleziona quello corretto dal menu"
              " sottostante:"
          ),
          color=discord.Color.gold(),
      )
      await interaction.response.send_message(
          embed=embed, view=view, ephemeral=True
      )


# ==========================================
# 📝 MODALI DI AZIONE CON 5 CAMPI
# ==========================================


class BaseActionModal(ui.Modal):

  field_1 = ui.TextInput(
      label="1. Nome", placeholder="Es. Mario", required=True
  )
  field_2 = ui.TextInput(
      label="2. Cognome", placeholder="Es. Rossi", required=True
  )
  field_3 = ui.TextInput(
      label="3. Data di Nascita", placeholder="Es. 12/05/1995", required=True
  )
  field_4 = ui.TextInput(
      label="4. Articoli / Motivazione",
      placeholder="Es. Art. 123 - Eccesso di velocità",
      required=True,
  )
  field_5 = ui.TextInput(
      label="5. Note / Dettagli Aggiuntivi",
      placeholder="Eventuali note o link foto",
      required=False,
      style=discord.TextStyle.paragraph,
  )

  def __init__(
      self,
      title: str,
      target_id: str,
      officer_name: str,
      bot: discord.Client,
      log_type: str,
      default_det: str,
      default_pec: str,
  ):
    super().__init__(title=title)
    self.target_id = target_id
    self.officer_name = officer_name
    self.bot = bot
    self.log_type = log_type
    self.default_det = default_det
    self.default_pec = default_pec

  async def on_submit(self, interaction: discord.Interaction):
    name = self.field_1.value.strip()
    surname = self.field_2.value.strip()
    birth_date = self.field_3.value.strip()
    articles = self.field_4.value.strip()
    notes = self.field_5.value.strip()

    await send_standardized_log(
        bot=self.bot,
        guild_id=interaction.guild_id,
        log_type=self.log_type,
        name=name,
        surname=surname,
        birth_date=birth_date,
        articles=articles,
        penalty_det=self.default_det,
        penalty_pec=self.default_pec,
        operators=self.officer_name,
        notes=notes,
    )
    await interaction.response.send_message(
        "✅ Azione registrata e log embed inviati con successo!", ephemeral=True
    )


class FineModal(BaseActionModal):

  def __init__(self, target_id: str, officer_name: str, bot: discord.Client):
    super().__init__(
        title="🚨 Registra Multa",
        target_id=target_id,
        officer_name=officer_name,
        bot=bot,
        log_type="fines",
        default_det="Nessuna",
        default_pec="Specificata nel verbale",
    )


class ArrestModal(BaseActionModal):

  def __init__(self, target_id: str, officer_name: str, bot: discord.Client):
    super().__init__(
        title="🔒 Registra Arresto",
        target_id=target_id,
        officer_name=officer_name,
        bot=bot,
        log_type="arrests",
        default_det="Detenzione Carceraria",
        default_pec="Non Prevista / Cauzione",
    )


class ReportModal(BaseActionModal):

  def __init__(self, target_id: str, officer_name: str, bot: discord.Client):
    super().__init__(
        title="📝 Registra Verbale",
        target_id=target_id,
        officer_name=officer_name,
        bot=bot,
        log_type="reports",
        default_det="A discrezione del giudice",
        default_pec="A discrezione del giudice",
    )


class SeizeVehicleModal(BaseActionModal):

  def __init__(self, target_id: str, officer_name: str, bot: discord.Client):
    super().__init__(
        title="🚗 Sequestro Veicolo",
        target_id=target_id,
        officer_name=officer_name,
        bot=bot,
        log_type="seized_vehicles",
        default_det="Sequestro Veicolare",
        default_pec="Sequestro Amministrativo",
    )


class SeizeItemModal(BaseActionModal):

  def __init__(self, target_id: str, officer_name: str, bot: discord.Client):
    super().__init__(
        title="📦 Sequestro Oggetto / Arma",
        target_id=target_id,
        officer_name=officer_name,
        bot=bot,
        log_type="seized_items",
        default_det="Confisca Materiale",
        default_pec="Nessuna",
    )


# ==========================================
# 🔓 GESTIONE DISSEQUESTRO
# ==========================================


class SeizedVehicleSelect(ui.Select):

  def __init__(self, options, bot):
    super().__init__(
        placeholder="Seleziona veicolo da dissequestrare...", options=options
    )
    self.bot = bot

  async def callback(self, interaction: discord.Interaction):
    v_id = int(self.values[0].split("_")[1])
    supabase.table("seized_vehicles").update({"status": "Dissequestrato"}).eq(
        "id", v_id
    ).execute()
    await interaction.response.send_message(
        "🔓 Veicolo dissequestrato con successo!", ephemeral=True
    )


class SeizedItemSelect(ui.Select):

  def __init__(self, options, bot):
    super().__init__(
        placeholder="Seleziona oggetto da dissequestrare...", options=options
    )
    self.bot = bot

  async def callback(self, interaction: discord.Interaction):
    i_id = int(self.values[0].split("_")[1])
    supabase.table("seized_items").update({"status": "Dissequestrato"}).eq(
        "id", i_id
    ).execute()
    await interaction.response.send_message(
        "🔓 Oggetto dissequestrato con successo!", ephemeral=True
    )


class SeizureManagementView(ui.View):

  def __init__(self, target_id: str, officer_id: int, bot: discord.Client):
    super().__init__(timeout=180)
    self.target_id = target_id
    self.officer_id = officer_id
    self.bot = bot
    self.update_components()

  def update_components(self):
    self.clear_items()
    v_res = (
        supabase.table("seized_vehicles")
        .select("*")
        .eq("discord_id", self.target_id)
        .eq("status", "Sequestrato")
        .execute()
    )
    i_res = (
        supabase.table("seized_items")
        .select("*")
        .eq("discord_id", self.target_id)
        .eq("status", "Sequestrato")
        .execute()
    )

    if v_res.data:
      options = [
          discord.SelectOption(
              label=f"Veicolo: {v['model']} ({v['plate']})",
              value=f"veh_{v['id']}",
              description=f"Motivo: {v['reason'][:50]}",
          )
          for v in v_res.data[:25]
      ]
      self.add_item(SeizedVehicleSelect(options, self.bot))

    if i_res.data:
      options = [
          discord.SelectOption(
              label=f"Oggetto: {v['item_name']} (Qtà: {v['quantity']})",
              value=f"item_{v['id']}",
              description=f"Motivo: {v['reason'][:50]}",
          )
          for v in i_res.data[:25]
      ]
      self.add_item(SeizedItemSelect(options, self.bot))


# ==========================================
# 🖥️ VISTE E MENU PRINCIPALI DEL CAD
# ==========================================


class PoliceCadDetailView(ui.View):

  def __init__(self, citizen_doc: dict, officer_id: int, bot: discord.Client):
    super().__init__(timeout=180)
    self.doc = citizen_doc
    self.officer_id = officer_id
    self.bot = bot
    self.target_id_str = citizen_doc.get("discord_id")

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.officer_id:
      await interaction.response.send_message(
          "❌ Questo terminale CAD non è intestato a te!", ephemeral=True
      )
      return False
    return True

  @ui.button(label="📋 Generalità", style=discord.ButtonStyle.primary, row=0)
  async def btn_gen(self, interaction: discord.Interaction, button: ui.Button):
    photo_url = self.doc.get("photo_url")
    embed = discord.Embed(
        title=(
            "🚔 Scheda Anagrafica: "
            f"{self.doc.get('name')} {self.doc.get('surname')}"
        ),
        description=(
            "• **Nome & Cognome:**"
            f" `{self.doc.get('name')} {self.doc.get('surname')}`\n• **Data di"
            " Nascita:**"
            f" `{self.doc.get('birth_date', 'N/D')} a"
            f" {self.doc.get('birth_place', 'N/D')}`\n• **Codice Fiscale:**"
            f" `{self.doc.get('cf', 'N/D')}`\n• **N° Documento:**"
            f" `{self.doc.get('doc_number', 'N/D')}`\n\n### 🧬 Caratteristiche"
            f" Fisiche:\n• **Occhi:** `{self.doc.get('eye_color', 'N/D')}`\n•"
            f" **Capelli:** `{self.doc.get('hair_color', 'N/D')}`\n• **Segni"
            f" Particolari:** `{self.doc.get('distinct_marks', 'Nessuno')}`\n\n•"
            f" **Discord User:** `<@{self.target_id_str}>`"
        ),
        color=discord.Color.dark_blue(),
    )
    if photo_url:
      embed.set_thumbnail(url=photo_url)
    await interaction.response.edit_message(embed=embed, view=self)

  @ui.button(label="🚗 Proprietà", style=discord.ButtonStyle.success, row=0)
  async def btn_prop(self, interaction: discord.Interaction, button: ui.Button):
    v_res = (
        supabase.table("registered_vehicles")
        .select("*")
        .eq("discord_id", self.target_id_str)
        .execute()
    )
    h_res = (
        supabase.table("registered_properties")
        .select("*")
        .eq("discord_id", self.target_id_str)
        .execute()
    )
    s_v_res = (
        supabase.table("seized_vehicles")
        .select("*")
        .eq("discord_id", self.target_id_str)
        .eq("status", "Sequestrato")
        .execute()
    )

    v_text = (
        "\n".join(
            [f"• **{v['model']}** - Targa: `{v['plate']}`" for v in v_res.data]
        )
        if v_res.data
        else "*Nessun veicolo.*"
    )
    h_text = (
        "\n".join(
            [f"• **{h['address']}** ({h['property_type']})" for h in h_res.data]
        )
        if h_res.data
        else "*Nessun immobile.*"
    )
    s_v_text = (
        "\n".join(
            [
                f"• 🚨 **{v['model']}** (Targa: `{v['plate']}`) - Motivo:"
                f" `{v['reason']}`"
                for v in s_v_res.data
            ]
        )
        if s_v_res.data
        else "*Nessun veicolo sequestrato.*"
    )

    embed = discord.Embed(
        title=(
            "🚘 Veicoli & Case - "
            f"{self.doc.get('name')} {self.doc.get('surname')}"
        ),
        description=(
            f"### 🚗 Veicoli Registrati:\n{v_text}\n\n### 🚨 Veicoli"
            f" Sequestrati:\n{s_v_text}\n\n### 🏠 Immobili:\n{h_text}"
        ),
        color=discord.Color.dark_green(),
    )
    await interaction.response.edit_message(embed=embed, view=self)

  @ui.button(label="📦 Oggetti Sequestrati", style=discord.ButtonStyle.secondary, row=0)
  async def btn_seized_items(self, interaction: discord.Interaction, button: ui.Button):
    i_res = (
        supabase.table("seized_items")
        .select("*")
        .eq("discord_id", self.target_id_str)
        .eq("status", "Sequestrato")
        .execute()
    )
    i_text = (
        "\n".join(
            [
                f"• **{i['item_name']}** (Qtà: `{i['quantity']}`) - Motivo:"
                f" `{i['reason']}`"
                for i in i_res.data
            ]
        )
        if i_res.data
        else "*Nessun oggetto sequestrato.*"
    )

    embed = discord.Embed(
        title=(
            "📦 Deposito Oggetti Sequestrati - "
            f"{self.doc.get('name')} {self.doc.get('surname')}"
        ),
        description=f"### 📦 Oggetti in Custodia:\n{i_text}",
        color=discord.Color.dark_orange(),
    )
    await interaction.response.edit_message(embed=embed, view=self)

  @ui.button(label="➕ Multa", style=discord.ButtonStyle.danger, row=1)
  async def add_fine(self, interaction: discord.Interaction, button: ui.Button):
    await interaction.response.send_modal(
        FineModal(self.target_id_str, interaction.user.display_name, self.bot)
    )

  @ui.button(label="➕ Arresto", style=discord.ButtonStyle.secondary, row=1)
  async def add_arrest(self, interaction: discord.Interaction, button: ui.Button):
    await interaction.response.send_modal(
        ArrestModal(self.target_id_str, interaction.user.display_name, self.bot)
    )

  @ui.button(label="➕ Verbale", style=discord.ButtonStyle.primary, row=1)
  async def add_report(self, interaction: discord.Interaction, button: ui.Button):
    await interaction.response.send_modal(
        ReportModal(self.target_id_str, interaction.user.display_name, self.bot)
    )

  @ui.button(label="🔒 Sequestra Veicolo", style=discord.ButtonStyle.danger, row=2)
  async def seize_veh(self, interaction: discord.Interaction, button: ui.Button):
    await interaction.response.send_modal(
        SeizeVehicleModal(
            self.target_id_str, interaction.user.display_name, self.bot
        )
    )

  @ui.button(label="📦 Sequestra Oggetto", style=discord.ButtonStyle.danger, row=2)
  async def seize_item(self, interaction: discord.Interaction, button: ui.Button):
    await interaction.response.send_modal(
        SeizeItemModal(
            self.target_id_str, interaction.user.display_name, self.bot
        )
    )

  @ui.button(label="🔓 Gestione Dissequestro", style=discord.ButtonStyle.success, row=2)
  async def manage_seizure(self, interaction: discord.Interaction, button: ui.Button):
    view = SeizureManagementView(self.target_id_str, self.officer_id, self.bot)
    await interaction.response.send_message(
        "Seleziona l'elemento da dissequestrare:", view=view, ephemeral=True
    )


class CitizenSelectMenu(ui.Select):

  def __init__(self, citizens_list: list, officer_id: int, bot: discord.Client):
    options = []
    for c in citizens_list[:25]:
      options.append(
          discord.SelectOption(
              label=f"{c.get('name')} {c.get('surname')}",
              value=c.get("discord_id"),
              description=f"CF: {c.get('cf')} | Doc: {c.get('doc_number')}",
          )
      )
    super().__init__(
        placeholder="Seleziona cittadino...",
        min_values=1,
        max_values=1,
        options=options,
    )
    self.citizens_list = citizens_list
    self.officer_id = officer_id
    self.bot = bot

  async def callback(self, interaction: discord.Interaction):
    if interaction.user.id != self.officer_id:
      await interaction.response.send_message(
          "❌ Questo terminale non è intestato a te!", ephemeral=True
      )
      return
    selected_id = self.values[0]
    doc = next(
        (c for c in self.citizens_list if c.get("discord_id") == selected_id),
        None,
    )
    if doc:
      view = PoliceCadDetailView(doc, self.officer_id, self.bot)
      embed = discord.Embed(
          title=(
              "🚔 Terminale Polizia - "
              f"{doc.get('name')} {doc.get('surname')}"
          ),
          description=(
              "Usa i pulsanti per consultare la scheda o registrare nuovi"
              " atti:"
          ),
          color=discord.Color.blue(),
      )
      await interaction.response.edit_message(embed=embed, view=view)


class PoliceCadSelectView(ui.View):

  def __init__(self, citizens_list: list, officer_id: int, bot: discord.Client):
    super().__init__(timeout=120)
    self.officer_id = officer_id
    self.citizens_list = citizens_list
    self.bot = bot
    self.add_item(CitizenSelectMenu(citizens_list, officer_id, bot))

  async def interaction_check(self, interaction: discord.Interaction) -> bool:
    if interaction.user.id != self.officer_id:
      await interaction.response.send_message(
          "❌ Questo terminale non è intestato a te!", ephemeral=True
      )
      return False
    return True

  @ui.button(
      label="🔍 Cerca Targa", style=discord.ButtonStyle.success, row=1
  )
  async def btn_search_plate(
      self, interaction: discord.Interaction, button: ui.Button
  ):
    await interaction.response.send_modal(
        CadSearchPlateModal(self.officer_id, self.bot)
    )

  @ui.button(
      label="🔍 Cerca Matricola", style=discord.ButtonStyle.danger, row=1
  )
  async def btn_search_serial(
      self, interaction: discord.Interaction, button: ui.Button
  ):
    await interaction.response.send_modal(
        CadSearchSerialModal(self.officer_id, self.bot)
    )

  @ui.button(
      label="🔍 Ricerca Smart Cittadino",
      style=discord.ButtonStyle.primary,
      row=2,
  )
  async def btn_smart_search(
      self, interaction: discord.Interaction, button: ui.Button
  ):
    await interaction.response.send_modal(
        SmartSearchCitizenModal(self.citizens_list, self.officer_id, self.bot)
    )

# ==========================================
# 🚀 COMANDI SLASH (FBI & POLIZIA)
# ==========================================


@bot.tree.command(
    name="cad_fbi",
    description=(
        "[FBI] Terminale operativo federale per ricerche anagrafiche, targhe e"
        " matricole."
    ),
)
@app_commands.checks.has_role(RUOLO_FBI_ID)
async def cad_fbi(interaction: discord.Interaction):
  res = (
      supabase.table("documents")
      .select("*")
      .order("name", desc=False)
      .execute()
  )
  if not res.data:
    await interaction.response.send_message(
        "❌ Nessun cittadino presente nel database.", ephemeral=True
    )
    return

  view = PoliceCadSelectView(res.data, interaction.user.id, bot)
  embed = discord.Embed(
      title="🕵️‍♂️ CAD FBI - Centrale Operativa Federale",
      description=(
          "Seleziona un **cittadino** dal menu a tendina oppure premi i bottoni"
          " sottostanti per ricerche avanzate."
      ),
      color=discord.Color.from_rgb(20, 35, 60),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@cad_fbi.error
async def cad_fbi_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.MissingRole):
    await interaction.response.send_message(
        "❌ Riservato agli agenti dell'FBI!", ephemeral=True
    )


@bot.tree.command(
    name="cad_polizia",
    description=(
        "[POLIZIA] Terminale operativo per ricerche anagrafiche, targhe e"
        " matricole."
    ),
)
@app_commands.checks.has_role(RUOLO_POLIZIA_ID)
async def cad_polizia(interaction: discord.Interaction):
  res = (
      supabase.table("documents")
      .select("*")
      .order("name", desc=False)
      .execute()
  )
  if not res.data:
    await interaction.response.send_message(
        "❌ Nessun cittadino presente nel database.", ephemeral=True
    )
    return

  view = PoliceCadSelectView(res.data, interaction.user.id, bot)
  embed = discord.Embed(
      title="🚔 CAD Polizia di Stato - Centrale Operativa",
      description=(
          "Seleziona un **cittadino** dal menu a tendina oppure premi i bottoni"
          " sottostanti per ricerche avanzate."
      ),
      color=discord.Color.dark_blue(),
  )
  await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@cad_polizia.error
async def cad_polizia_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
  if isinstance(error, app_commands.MissingRole):
    await interaction.response.send_message(
        "❌ Riservato alle Forze dell'Ordine!", ephemeral=True
    )

class FinePaySelectView(ui.View):
    def __init__(self, user_id: int, fines_list: list):
        super().__init__(timeout=120)
        self.user_id = user_id

        options = []
        for fine in fines_list[:25]:
            options.append(discord.SelectOption(
                label=f"Multa #{fine['id']} - ${fine['amount']:,.2f}",
                value=str(fine['id']),
                description=f"Causale: {fine['reason'][:50]}"
            ))

        if options:
            self.select = ui.Select(placeholder="Seleziona la multa da pagare...", options=options)
            self.select.callback = self.pay_fine_callback
            self.add_item(self.select)

    async def pay_fine_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id: 
            return

        fine_id = int(self.select.values[0])
        res = supabase.table("police_fines").select("*").eq("id", fine_id).execute()

        if not res.data:
            await interaction.response.send_message("❌ Multa non trovata.", ephemeral=True)
            return

        fine = res.data[0]
        if fine["status"] == "Pagata":
            await interaction.response.send_message("❌ Questa multa è già stata pagata!", ephemeral=True)
            return

        amount = float(fine["amount"])
        u_data = get_or_create_user(self.user_id, interaction.user.name)
        bank_balance = float(u_data.get("bank", 0.0))

        if bank_balance < amount:
            await interaction.response.send_message(f"❌ Saldo in banca insufficiente! Ti servono **${amount:,.2f}**.", ephemeral=True)
            return

        new_bank = bank_balance - amount
        supabase.table("users").update({"bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
        supabase.table("police_fines").update({"status": "Pagata"}).eq("id", fine_id).execute()

        log_transaction(str(self.user_id), "PAGAMENTO_MULTA", amount, f"Pagata multa #{fine_id}")

        embed = discord.Embed(
            title="✅ Multa Pagata con Successo",
            description=f"• **ID Multa:** `#{fine_id}`\n• **Importo Detratto:** `${amount:,.2f}`\n• **Nuovo Saldo Banca:** `${new_bank:,.2f}`\n• **Stato Sanzione:** `Pagata`",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="paga_multa", description="Visualizza e paga le tue multe pendenti scalando i soldi dal conto in banca.")
async def paga_multa(interaction: discord.Interaction):
    user_id_str = str(interaction.user.id)
    res = supabase.table("police_fines").select("*").eq("discord_id", user_id_str).eq("status", "Da Pagare").execute()

    if not res.data:
        embed = discord.Embed(
            title="🎉 Nessuna Multa Pendente",
            description="Non hai sanzioni da pagare al momento.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    total_due = sum([float(f['amount']) for f in res.data])
    embed = discord.Embed(
        title="💳 Gestione Multe Pendenti",
        description=f"Hai **{len(res.data)}** multa/e da saldare per un totale di **${total_due:,.2f}**.\nSeleziona una multa dal menu sottostante per pagarla:",
        color=discord.Color.orange()
    )

    view = FinePaySelectView(interaction.user.id, res.data)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --- DOCUMENTI IDENTIFICATIVI ---
async def genera_carta_identita(nome, cognome, birth_date, birth_place, cf, doc_number, photo_url, colore_occhi, colore_capelli, segni_particolari):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                width: 780px;
                height: 500px;
                background: #f8fafc;
                font-family: 'Segoe UI', Arial, sans-serif;
                border: 3px solid #1e3a8a;
                box-sizing: border-box;
                position: relative;
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #1e3a8a 0%, #1d4ed8 100%);
                color: white;
                padding: 14px 24px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 4px solid #f59e0b;
            }}
            .header-left h1 {{
                margin: 0;
                font-size: 21px;
                letter-spacing: 1.5px;
                font-weight: 800;
                text-transform: uppercase;
            }}
            .header-left span {{
                font-size: 11px;
                letter-spacing: 2px;
                color: #93c5fd;
                text-transform: uppercase;
                font-weight: 600;
            }}
            .header-right {{
                text-align: right;
                font-size: 13px;
                font-weight: bold;
                letter-spacing: 1px;
                color: #fde047;
                background: rgba(0, 0, 0, 0.2);
                padding: 4px 10px;
                border-radius: 4px;
            }}
            .body-content {{
                padding: 22px 26px;
                display: flex;
                gap: 25px;
            }}
            .foto-container {{
                width: 165px;
                height: 215px;
                border: 3px solid #1e3a8a;
                background: #fff;
                box-shadow: 0 4px 10px rgba(0,0,0,0.15);
                flex-shrink: 0;
            }}
            .foto-container img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}
            .info-grid {{
                flex-grow: 1;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 12px 18px;
            }}
            .field {{
                display: flex;
                flex-direction: column;
                border-bottom: 2px solid #cbd5e1;
                padding-bottom: 4px;
            }}
            .field.full {{
                grid-column: span 2;
            }}
            .label {{
                font-size: 11px;
                text-transform: uppercase;
                color: #475569;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            .value {{
                font-size: 17px;
                font-weight: 700;
                color: #0f172a;
                margin-top: 2px;
            }}
            .footer {{
                position: absolute;
                bottom: 14px;
                left: 26px;
                right: 26px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 14px;
                color: #1e293b;
                border-top: 2px solid #cbd5e1;
                padding: 10px 15px;
                background: #e2e8f0;
                border-radius: 4px;
            }}
            .footer span b {{
                color: #1e3a8a;
                font-size: 15px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-left">
                <h1>CITTÀ DI LOS ANGELES</h1>
                <span>CALIFORNIA — CARTA D'IDENTITÀ</span>
            </div>
            <div class="header-right">
                <span>IDENTIFICATION CARD</span>
            </div>
        </div>
        
        <div class="body-content">
            <div class="foto-container">
                <img src="{photo_url}" />
            </div>
            
            <div class="info-grid">
                <div class="field">
                    <span class="label">Cognome / Surname</span>
                    <span class="value">{cognome.upper()}</span>
                </div>
                <div class="field">
                    <span class="label">Nome / Given Name</span>
                    <span class="value">{nome.capitalize()}</span>
                </div>
                <div class="field full">
                    <span class="label">Data e Luogo di Nascita / Date & Place of Birth</span>
                    <span class="value">{birth_date} — {birth_place}</span>
                </div>
                <div class="field">
                    <span class="label">Occhi / Eyes</span>
                    <span class="value">{colore_occhi}</span>
                </div>
                <div class="field">
                    <span class="label">Capelli / Hair</span>
                    <span class="value">{colore_capelli}</span>
                </div>
                <div class="field full">
                    <span class="label">Segni Particolari / Distinctive Marks</span>
                    <span class="value">{segni_particolari}</span>
                </div>
            </div>
        </div>

        <div class="footer">
            <span>Codice Fiscale: <b>{cf}</b></span>
            <span>N. Documento: <b>{doc_number}</b></span>
        </div>
    </body>
    </html>
    """
    return html_content


    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 780, "height": 500})
        await page.set_content(html_content)
        await page.wait_for_load_state("networkidle")
        screenshot_bytes = await page.screenshot(type="png")
        await browser.close()

    buffer = io.BytesIO(screenshot_bytes)
    buffer.seek(0)
    return discord.File(buffer, filename="carta_identita.png")

import io
from playwright.async_api import async_playwright

async def genera_fattura_html(
    invoice_id,
    azienda,
    emittente,
    destinatario,
    importo,
    causale,
    data_emissione,
    stato="DA PAGARE",
):
  colore_badge_bg = "#ffeeee" if stato.upper() == "DA PAGARE" else "#e6f4ea"
  colore_badge_text = "#c5221f" if stato.upper() == "DA PAGARE" else "#137333"
  colore_border = "#f28b82" if stato.upper() == "DA PAGARE" else "#81c995"

  html_content = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                margin: 0;
                padding: 30px 40px;
                width: 780px;
                height: 520px;
                background: #ffffff;
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                color: #202124;
                box-sizing: border-box;
                position: relative;
                border: 1px solid #dadce0;
            }}
            .invoice-header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                border-bottom: 2px solid #202124;
                padding-bottom: 15px;
                margin-bottom: 20px;
            }}
            .company-info h1 {{
                margin: 0;
                font-size: 22px;
                font-weight: 700;
                color: #202124;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            .company-info span {{
                font-size: 11px;
                color: #5f6368;
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 600;
            }}
            .invoice-meta {{
                text-align: right;
            }}
            .invoice-meta h2 {{
                margin: 0 0 5px 0;
                font-size: 18px;
                color: #1a73e8;
            }}
            .invoice-meta p {{
                margin: 2px 0;
                font-size: 12px;
                color: #5f6368;
            }}
            .details-section {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 25px;
                font-size: 13px;
                background: #f8f9fa;
                padding: 12px 15px;
                border-radius: 6px;
                border: 1px solid #e8eaed;
            }}
            .detail-block h4 {{
                margin: 0 0 4px 0;
                font-size: 11px;
                text-transform: uppercase;
                color: #5f6368;
                letter-spacing: 0.5px;
            }}
            .detail-block p {{
                margin: 0;
                font-weight: 600;
                color: #202124;
                font-size: 14px;
            }}
            .status-badge {{
                display: inline-block;
                padding: 4px 10px;
                background-color: {colore_badge_bg};
                color: {colore_badge_text};
                border: 1px solid {colore_border};
                border-radius: 4px;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .invoice-table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }}
            .invoice-table th {{
                background-color: #f1f3f4;
                color: #3c4043;
                font-size: 11px;
                text-transform: uppercase;
                text-align: left;
                padding: 8px 12px;
                border-bottom: 2px solid #bdc1c6;
                letter-spacing: 0.5px;
            }}
            .invoice-table td {{
                padding: 12px;
                font-size: 13px;
                border-bottom: 1px solid #e8eaed;
                color: #202124;
            }}
            .invoice-table td.amount {{
                text-align: right;
                font-weight: 700;
            }}
            .invoice-footer {{
                position: absolute;
                bottom: 25px;
                left: 40px;
                right: 40px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-top: 1px solid #dadce0;
                padding-top: 12px;
                font-size: 11px;
                color: #5f6368;
            }}
            .total-row {{
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: 15px;
                margin-top: 5px;
                font-size: 15px;
            }}
            .total-row span.label {{
                font-weight: 600;
                color: #5f6368;
                font-size: 12px;
                text-transform: uppercase;
            }}
            .total-row span.value {{
                font-weight: 700;
                color: #1a73e8;
                font-size: 18px;
            }}
        </style>
    </head>
    <body>
        <div class="invoice-header">
            <div class="company-info">
                <h1>{azienda.upper()}</h1>
                <span>Documento Fiscale Ufficiale</span>
            </div>
            <div class="invoice-meta">
                <h2>FATTURA #{invoice_id}</h2>
                <p>Data: <b>{data_emissione}</b></p>
                <div style="margin-top: 6px;">
                    <span class="status-badge">{stato.upper()}</span>
                </div>
            </div>
        </div>
        
        <div class="details-section">
            <div class="detail-block">
                <h4>Emittente</h4>
                <p>{emittente}</p>
            </div>
            <div class="detail-block">
                <h4>Destinatario / Cliente</h4>
                <p>{destinatario}</p>
            </div>
            <div class="detail-block" style="text-align: right;">
                <h4>Sistema Fiscale</h4>
                <p>Evren City OS</p>
            </div>
        </div>

        <table class="invoice-table">
            <thead>
                <tr>
                    <th style="width: 70%;">Descrizione / Causale</th>
                    <th style="width: 30%; text-align: right;">Importo</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{causale}</td>
                    <td class="amount">€ {importo:,.2f}</td>
                </tr>
            </tbody>
        </table>

        <div class="total-row">
            <span class="label">Totale da pagare:</span>
            <span class="value">€ {importo:,.2f}</span>
        </div>

        <div class="invoice-footer">
            <span>Documento generato digitalmente tramite Evren City OS</span>
            <span>Pagina 1 di 1</span>
        </div>
    </body>
    </html>
    """
  return html_content

# --- FUNZIONE PER CONVERTIRE L'HTML IN IMMAGINE ---
async def renderizza_fattura_immagine(fattura):
  html = await genera_fattura_html(
      invoice_id=fattura["id"],
      azienda=fattura["azienda"],
      emittente=fattura["emittente"],
      destinatario=fattura["destinatario"],
      importo=fattura["importo"],
      causale=fattura["causale"],
      data_emissione=fattura["data"],
      stato=fattura["status"]
  )
  
  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 780, "height": 480})
    await page.set_content(html)
    screenshot_bytes = await page.screenshot(type="png")
    await browser.close()
    
  return io.BytesIO(screenshot_bytes)


@bot.tree.command(
    name="emetti_fattura", description="Emetti una nuova fattura aziendale."
)
@app_commands.describe(
    azienda="Nome dell'azienda emittente",
    utente="Il cittadino destinatario della fattura",
    importo="Importo in denaro",
    causale="Motivo della fattura",
)
async def emetti_fattura(
    interaction: discord.Interaction,
    azienda: str,
    utente: discord.Member,
    importo: float,
    causale: str,
):
  # 1. Rispondi subito a Discord per evitare lo scadere dei 3 secondi
  await interaction.response.defer(ephemeral=False)

  data_oggi = datetime.datetime.now().strftime("%d/%m/%Y")
  emittente_nome = interaction.user.display_name

  # 2. Inserimento nel database
  res = (
      supabase.table("invoices")
      .insert({
          "discord_id": str(utente.id),
          "destinatario": utente.display_name,
          "emittente": emittente_nome,
          "azienda": azienda,
          "importo": importo,
          "causale": causale,
          "data": data_oggi,
          "status": "Da Pagare",
      })
      .execute()
  )

  if not res.data:
    await interaction.followup.send(
        "❌ Errore durante la creazione della fattura nel database.",
        ephemeral=True,
    )
    return

  nuova_fattura = res.data[0]

  # 3. Generazione dell'immagine della fattura
  img_io = await renderizza_fattura_immagine(nuova_fattura)
  file = discord.File(img_io, filename=f"fattura_{nuova_fattura['id']}.png")

  embed = discord.Embed(
      title="📑 Nuova Fattura Emessa",
      description=f"Fattura emessa con successo per {utente.mention} a nome dell'azienda **{azienda}**!",
      color=discord.Color.from_rgb(15, 23, 42),
  )
  embed.set_image(url=f"attachment://fattura_{nuova_fattura['id']}.png")
  embed.set_footer(text="Evren City OS • Sistema Fiscale")

  # 4. Invia l'anteprima nel canale pubblico
  await interaction.followup.send(embed=embed, file=file)

  # 5. Invia un messaggio privato (DM) al destinatario
  try:
    dm_embed = discord.Embed(
        title="💳 Nuova Fattura Ricevuta",
        description=(
            f"Ti è stata emessa una nuova fattura a nome dell'azienda **{azienda}** "
            f"per un importo di **€ {importo:,.2f}**.\n\n"
            f"💬 **Causale:** {causale}\n\n"
            f"Usa il comando </mie_fatture:0> in città per visualizzare l'anteprima "
            f"dettagliata ed effettuare il pagamento."
        ),
        color=discord.Color.from_rgb(220, 38, 38),
    )
    dm_embed.set_footer(text="Evren City OS • Sistema Fiscale")
    await utente.send(embed=dm_embed)
  except discord.Forbidden:
    # Gestisce il caso in cui l'utente ha i DM chiusi o ha bloccato il bot
    pass

# --- INTERFACCIA PER IL PAGAMENTO DELLE FATTURE ---
class PagaFatturaSelect(discord.ui.Select):

  def __init__(self, fatture):
    options = []
    for f in fatture:
      if f["status"].lower() == "da pagare":
        options.append(
            discord.SelectOption(
                label=f"Fattura #{f['id']} - € {f['importo']:,.2f}",
                description=f"Azienda: {f['azienda']} | {f['causale'][:40]}",
                value=str(f["id"]),
                emoji="💳",
            )
        )

    if not options:
      options.append(
          discord.SelectOption(
              label="Nessuna fattura da pagare",
              value="none",
              description="Sei in regola con i pagamenti!",
          )
      )

    super().__init__(
        placeholder="Seleziona una fattura da pagare...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    if self.values[0] == "none":
      await interaction.response.send_message(
          "Non hai fatture in sospeso da pagare.", ephemeral=True
      )
      return

    invoice_id = int(self.values[0])
    user_id_str = str(interaction.user.id)

    inv_res = (
        supabase.table("invoices")
        .select("*")
        .eq("id", invoice_id)
        .execute()
    )
    if not inv_res.data:
      await interaction.response.send_message(
          "❌ Fattura non trovata.", ephemeral=True
      )
      return

    fattura = inv_res.data[0]
    importo_dovuto = fattura["importo"]

    user_res = (
        supabase.table("users").select("bank, wallet").eq("discord_id", user_id_str).execute()
    )
    if not user_res.data:
      await interaction.response.send_message(
          "❌ Non risulti registrato anagraficamente in città.", ephemeral=True
      )
      return

    banca = user_res.data[0].get("bank", 0.0) or 0.0
    portafoglio = user_res.data[0].get("wallet", 0.0) or 0.0

    if banca >= importo_dovuto:
      nuovo_saldo = banca - importo_dovuto
      supabase.table("users").update({"bank": nuovo_saldo}).eq(
          "discord_id", user_id_str
      ).execute()
      metodo_pagamento = "Conto Bancario"
    elif portafoglio >= importo_dovuto:
      nuovo_saldo = portafoglio - importo_dovuto
      supabase.table("users").update({"wallet": nuovo_saldo}).eq(
          "discord_id", user_id_str
      ).execute()
      metodo_pagamento = "Contanti (Wallet)"
    else:
      await interaction.response.send_message(
          f"❌ Fondi insufficienti! Ti servono **€ {importo_dovuto:,.2f}** (Banca:"
          f" € {banca:,.2f} | Contanti: € {portafoglio:,.2f}).",
          ephemeral=True,
      )
      return

    supabase.table("invoices").update({"status": "Pagata"}).eq(
        "id", invoice_id
    ).execute()

    supabase.table("transactions_log").insert({
        "discord_id": user_id_str,
        "type": "Pagamento Fattura",
        "amount": -importo_dovuto,
        "description": (
            f"Pagamento fattura #{invoice_id} - Azienda: {fattura['azienda']}"
        ),
    }).execute()

    await interaction.response.send_message(
        f"✅ Fattura **#{invoice_id}** pagata con successo tramite"
        f" **{metodo_pagamento}** per un importo di **€"
        f" {importo_dovuto:,.2f}**!",
        ephemeral=True,
    )


class FabbricaFattureView(discord.ui.View):

  def __init__(self, fatture):
    super().__init__(timeout=180)
    self.add_item(PagaFatturaSelect(fatture))

@bot.tree.command(
    name="mie_fatture", description="Visualizza e paga le tue fatture in sospeso."
)
async def mie_fatture(interaction: discord.Interaction):
  # 1. Impedisce il timeout di Discord
  await interaction.response.defer(ephemeral=False)

  res = (
      supabase.table("invoices")
      .select("*")
      .eq("discord_id", str(interaction.user.id))
      .order("id", desc=True)
      .execute()
  )

  if not res.data:
    await interaction.followup.send(
        "❌ Non hai alcuna fattura registrata a tuo carico.", ephemeral=True
    )
    return

  fatture = res.data
  ultima = fatture[0]

  # 2. Generazione dell'immagine con Playwright
  img_io = await renderizza_fattura_immagine(ultima)
  file = discord.File(img_io, filename=f"fattura_{ultima['id']}.png")

  embed = discord.Embed(
      title="📑 Gestione Fatture Personali",
      description=(
          "Ecco l'anteprima della tua fattura più recente. Usa il menu sotto"
          " per pagare quelle in sospeso."
      ),
      color=discord.Color.from_rgb(15, 23, 42),
  )
  embed.set_image(url=f"attachment://fattura_{ultima['id']}.png")

  if len(fatture) > 1:
    storico_testo = ""
    for f in fatture[1:]:
      storico_testo += (
          f"• **#{f['id']}** | {f['azienda']} | € {f['importo']:,.2f} |"
          f" `{f['status']}`\n"
      )
    if len(storico_testo) > 1024:
      storico_testo = storico_testo[:1021] + "..."
    embed.add_field(
        name="📜 Storico Fatture Precedenti",
        value=storico_testo,
        inline=False,
    )

  embed.set_footer(text="Evren City OS • Sistema Fiscale")

  view = FabbricaFattureView(fatture)
  
  # 3. Invio tramite followup
  await interaction.followup.send(embed=embed, file=file, view=view)


import io
from playwright.async_api import async_playwright


async def renderizza_html_in_immagine(html_content: str) -> discord.File:
  async with async_playwright() as p:
    # Avvia Chromium in background
    browser = await p.chromium.launch(
        headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"]
    )
    # Imposta la pagina con le dimensioni esatte della carta (780x500)
    page = await browser.new_page(viewport={"width": 780, "height": 500})

    # Carica l'HTML
    await page.set_content(html_content)

    # Cattura lo screenshot della carta come byte PNG
    screenshot_bytes = await page.screenshot(type="png", full_page=False)
    await browser.close()

  # Converte i byte in un file utilizzabile da Discord
  buffer = io.BytesIO(screenshot_bytes)
  buffer.seek(0)
  return discord.File(buffer, filename="carta_identita.png")


@bot.tree.command(
    name="mostra_documento",
    description="Mostra la tua carta d'identità ufficiale in chat.",
)
async def mostra_documento(interaction: discord.Interaction):
  await interaction.response.defer(ephemeral=False)

  user_id = str(interaction.user.id)
  response = (
      supabase.table("documents").select("*").eq("discord_id", user_id).execute()
  )

  if not response.data:
    await interaction.followup.send(
        "❌ Non possiedi ancora un documento registrato! Usa `/crea_documenti`"
        " per crearlo.",
        ephemeral=True,
    )
    return

  doc = response.data[0]

  # 1. Ottiene il codice HTML tramite la tua funzione
  html_content = await genera_carta_identita(
      nome=doc["name"],
      cognome=doc["surname"],
      birth_date=doc["birth_date"],
      birth_place=doc["birth_place"],
      cf=doc["cf"],
      doc_number=doc["doc_number"],
      photo_url=doc["photo_url"],
      colore_occhi=doc["eye_color"],
      colore_capelli=doc["hair_color"],
      segni_particolari=doc["distinct_marks"],
  )

  # 2. Converte l'HTML in un'immagine tramite Playwright
  file_documento = await renderizza_html_in_immagine(html_content)

  # 3. Invia il file immagine su Discord (rimuovi ephemeral=True se vuoi che sia visibile a tutti in chat pubblica)
  await interaction.followup.send(file=file_documento)

# --- COMANDI REGISTRAZIONE ISTITUZIONALE ---

@bot.tree.command(name="registra_veicolo", description="[MOTORIZZAZIONE] Registra un veicolo con targa.")
async def registra_veicolo(interaction: discord.Interaction, proprietario: discord.Member, modello: str, targa: str):
    if RUOLO_MOTORIZZAZIONE_ID and interaction.guild.get_role(RUOLO_MOTORIZZAZIONE_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato alla Motorizzazione!")
        return

    supabase.table("registered_vehicles").insert({"discord_id": str(proprietario.id), "model": modello, "plate": targa.upper()}).execute()
    embed = discord.Embed(title="🚗 Veicolo Immatricolato", description=f"• Proprietario: {proprietario.mention}\n• Modello: `{modello}`\n• Targa: `{targa.upper()}`", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="registra_patente", description="[MOTORIZZAZIONE] Rilascia una patente di guida.")
async def registra_patente(interaction: discord.Interaction, cittadino: discord.Member, tipo_patente: str):
    if RUOLO_MOTORIZZAZIONE_ID and interaction.guild.get_role(RUOLO_MOTORIZZAZIONE_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato alla Motorizzazione!")
        return

    supabase.table("driver_licenses").insert({"discord_id": str(cittadino.id), "license_type": tipo_patente.upper(), "status": "Attiva"}).execute()
    embed = discord.Embed(title="💳 Patente Rilasciata", description=f"• Cittadino: {cittadino.mention}\n• Tipo Patente: `{tipo_patente.upper()}`", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="registra_arma", description="[ARMERIA] Registra una matricola d'arma a un cittadino.")
async def registra_arma(interaction: discord.Interaction, acquirente: discord.Member, matricola: str, modello: str):
    if RUOLO_ARMERIA_ID and interaction.guild.get_role(RUOLO_ARMERIA_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato all'Armeria!")
        return

    supabase.table("registered_weapons").insert({"discord_id": str(acquirente.id), "model": modello, "serial_number": matricola}).execute()
    embed = discord.Embed(title="📜 Arma Registrata", description=f"• Intestatario: {acquirente.mention}\n• Modello: `{modello}`\n• Matricola: `{matricola}`", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="registra_porto_darmi", description="[POLIZIA] Rilascia un porto d'armi.")
async def registra_porto_darmi(interaction: discord.Interaction, cittadino: discord.Member, tipo_licenza: str):
    if RUOLO_POLIZIA_ID and interaction.guild.get_role(RUOLO_POLIZIA_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato alla Polizia!")
        return

    supabase.table("gun_licenses").insert({"discord_id": str(cittadino.id), "license_type": tipo_licenza, "status": "Attivo"}).execute()
    embed = discord.Embed(title="🛡️ Porto d'Armi Registrato", description=f"• Intestatario: {cittadino.mention}\n• Licenza: `{tipo_licenza}`", color=discord.Color.dark_blue())
    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="registra_casa", description="[IMMOBILIARE] Registra un immobile.")
async def registra_casa(interaction: discord.Interaction, proprietario: discord.Member, indirizzo: str, tipologia: str):
    if RUOLO_IMMOBILIARE_ID and interaction.guild.get_role(RUOLO_IMMOBILIARE_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato all'Agenzia Immobiliare!")
        return

    supabase.table("registered_properties").insert({"discord_id": str(proprietario.id), "address": indirizzo, "property_type": tipologia}).execute()
    embed = discord.Embed(title="🏠 Immobile Registrato", description=f"• Proprietario: {proprietario.mention}\n• Indirizzo: `{indirizzo}`\n• Categoria: `{tipologia}`", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)


# --- EVENTO READY E AVVIO ---

@bot.event
async def on_ready():
    await bot.tree.sync()
    bot.add_view(PannelloAnagrafeView())
    
    print(f"✅ Bot online come {bot.user}")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.run(DISCORD_TOKEN)
