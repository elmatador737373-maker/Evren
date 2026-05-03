import os
import discord
from discord import app_commands, Interaction
import datetime
import random
import string
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask
from threading import Thread

# --- CONFIGURAZIONE FLASK ---
app = Flask('')
@app.route('/')
def home(): return "CAD Globale Online"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CONFIGURAZIONE CORE ---
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

SERVER_CONFIG = {
    1233353915559313478: {
        "ruolo_polizia": 1363487988570521670,
        "canale_log_arresti": 1496978741442773063,
        "canale_log_multe": 1482757565145288754,
        "canale_log_denunce": 1459560041563816129,
        "canale_log_sequestri": 1482753448951681214
    },
    1499394373270507701: {
        "ruolo_polizia": 1499394715634761789,
        "canale_log_arresti": 1499398686067658897,
        "canale_log_multe": 1499398731504685207,
        "canale_log_denunce": 1499398857979727872,
        "canale_log_sequestri": 1499398820851744799
    }
}

def get_db_connection():
    try: return psycopg2.connect(DATABASE_URL, sslmode='require')
    except: return None

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
    async def setup_hook(self): await self.tree.sync()

bot = MyBot()

# --- UTILS ---
def is_polizia(interaction: Interaction):
    cfg = SERVER_CONFIG.get(interaction.guild_id)
    return cfg and any(role.id == cfg["ruolo_polizia"] for role in interaction.user.roles)

async def invia_log_globale(tipo_log_key, embed):
    for guild_id, cfg in SERVER_CONFIG.items():
        guild = bot.get_guild(guild_id)
        if guild:
            channel = guild.get_channel(cfg.get(tipo_log_key))
            ruolo_id = cfg.get("ruolo_polizia")
            if channel:
                try: await channel.send(content=f"<@&{ruolo_id}>", embed=embed)
                except: pass

# --- COMANDI OPERATIVI ---

@bot.tree.command(name="arresto", description="[POLIZIA] Registra un arresto nel database globale")
@app_commands.describe(
    utente="Seleziona il cittadino", nome="Nome IC", cognome="Cognome IC", nascita="Data di nascita", 
    articoli="Articoli violati", pena="Mesi di carcere", sanzione="Ammontare multa", 
    foto="Carica foto segnaletica", note="Annotazioni aggiuntive"
)
async def arresto(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, nascita: str, articoli: str, pena: str, sanzione: int, foto: discord.Attachment, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, %s, %s)",
                (str(utente.id), str(interaction.user.id), f"Arresto: {articoli}", 0, datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐀𝐑𝐑𝐄𝐒𝐓𝐎", color=discord.Color.dark_blue())
    emb.description = f"""> • ɴᴏᴍᴇ: **{nome}**
> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**
> • ᴅᴀᴛᴀ ᴅɪ ɴᴀsᴄɪᴛᴀ: **{nascita}**
> • ᴀʀᴛɪᴄᴏʟᴏ/ɪ ᴄᴏɴᴛᴇsᴛᴀᴛᴏ/ɪ: **{articoli}**
> • ᴘᴇɴᴀ ᴅᴇᴛᴇɴᴛɪᴠᴀ: **{pena}**
> • sᴀɴᴢɪᴏɴᴇ ᴘᴇᴄᴜɴɪᴀʀɪᴀ: **{sanzione}$**
> • ᴅᴀᴛᴀ / ᴏʀᴀ: **{datetime.datetime.now().strftime("%d/%m/%Y %H:%M")}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**
> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: **{note}**"""
    emb.set_image(url=foto.url)
    await invia_log_globale("canale_log_arresti", emb)
    await interaction.followup.send("✅ Verbale di arresto registrato globalmente.")
from PIL import Image, ImageDraw, ImageFont
import io
import requests
import datetime

# --- COMANDI TESSERINI ---

def is_admin(interaction: discord.Interaction):
    return interaction.user.guild_permissions.administrator

# --- COMANDI TESSERINI (VERSIONE CON FOTO E ALLINEAMENTO SX) ---

@bot.tree.command(name="crea_tesserino", description="[ADMIN] Crea/Aggiorna il tesserino ufficiale di un agente")
@app_commands.describe(
    utente="L'agente a cui assegnare il tesserino",
    nome="Nome e Cognome IC (es. M.Rossi)",
    grado="Grado (Rank)",
    badge="Numero di Matricola (Badge #)",
    unita="Unità (Unit)",
    id_personale="ID Personale (ID #)",
    nascita="Data di nascita (D.O.B.)",
    scadenza="Data di scadenza (1 mese dalla creazione) (Expires)",
    foto="Carica la foto dell'agente",
    firma="Firma Dell'agente a cui viene emesso"
)
async def crea_tesserino(
    interaction: discord.Interaction, 
    utente: discord.Member, nome: str, grado: str, badge: str, 
    unita: str, id_personale: str, nascita: str, scadenza: str, 
    foto: discord.Attachment, firma: str
):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Solo gli Admin possono creare tesserini.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    
    data_emissione = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%d/%m/%Y")
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO tesserini (user_id, nome_completo, grado, badge_num, unita, id_num, data_nascita, data_emissione, data_scadenza, foto_url, firma_ufficiale)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET 
        nome_completo=EXCLUDED.nome_completo, grado=EXCLUDED.grado, badge_num=EXCLUDED.badge_num, 
        unita=EXCLUDED.unita, id_num=EXCLUDED.id_num, data_nascita=EXCLUDED.data_nascita, 
        data_emissione=EXCLUDED.data_emissione, data_scadenza=EXCLUDED.data_scadenza, 
        foto_url=EXCLUDED.foto_url, firma_ufficiale=EXCLUDED.firma_ufficiale
    """, (str(utente.id), nome, grado, badge, unita, id_personale, nascita, data_emissione, scadenza, foto.url, firma))
    conn.commit(); cur.close(); conn.close()
    
    await interaction.followup.send(f"✅ Tesserino per {utente.mention} registrato con successo.")


@bot.tree.command(name="mostra_tesserino", description="Visualizza il tuo tesserino LAPD ufficiale")
async def mostra_tesserino(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
    except:
        return

    user_id = str(interaction.user.id)
    
    try:
        # 1. Recupero dati completi dal database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT nome_completo, grado, badge_num, unita, id_num, data_nascita, 
                   data_emissione, data_scadenza, foto_url, firma_ufficiale 
            FROM tesserini WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if not row:
            return await interaction.followup.send("⚠️ Tesserino non trovato. Chiedi a un Admin di crearlo.")

        # Assegnazione variabili
        nome, grado, badge, unita, id_pers, nascita, emissione, scadenza, foto_url, firma = row

        # 2. Carica il template principale
        tesserino = Image.open("IMG_0418.png").convert("RGBA")
        draw = ImageDraw.Draw(tesserino)

              # 3. CARICAMENTO E INSERIMENTO FOTO AGENTE
        # Calibrato sui punti: P15(46,95), P18(48,381), P20(281,384), P21(286,90)
        try:
            response = requests.get(foto_url)
            foto_agente = Image.open(io.BytesIO(response.content)).convert("RGBA")
            
            # Ridimensioniamo la foto per coprire perfettamente l'area blu
            # Larghezza: 240px, Altezza: 286px
            foto_agente = foto_agente.resize((374, 460), Image.Resampling.LANCZOS)
            
            # Incolliamo la foto al punto P15 (46, 95)
            # Usiamo foto_agente come maschera per gestire eventuali trasparenze
            tesserino.paste(foto_agente, (59, 142), foto_agente)
            
        except Exception as e:
            print(f"Errore caricamento foto: {e}")

        # 4. SCRITTURA DEI TESTI SUL TESSERINO
        try:
            font_testo = ImageFont.truetype("arial.ttf", 25)
            font_firma = ImageFont.truetype("Serenity PersonalUseOnly.ttf", 20) # Puoi usare un font corsivo se disponibile
        except:
            font_testo = ImageFont.load_default()
            font_firma = ImageFont.load_default()

        # Coordinate basate sui tuoi screenshot precedenti (P7, P10, P18, ecc.)
        # Ho aggiunto un piccolo offset per allinearli alle righe del tuo template
        campi = [
            (nome.upper(),      (605, 137)),   # NAME
            (grado.upper(),     (607, 187)),  # RANK
            (str(badge),        (650, 237)),  # BADGE #
            (unita.upper(),     (582, 288)),  # UNIT
            (str(id_pers),      (585, 337)),  # ID #
            (nascita,           (616, 395)),  # D.O.B.
            (emissione,         (640, 438)),  # ISSUED
            (scadenza,          (642, 484)),  # EXPIRES
            (firma,             (433, 632))   # OFFICER SIGNATURE (sotto la foto)
        ]

        for testo, pos in campi:
            if testo == firma:
                draw.text(pos, str(testo), font=font_firma, fill=(0, 0, 0))
            else:
                draw.text(pos, str(testo), font=font_testo, fill=(0, 0, 0))

        # 5. INVIO DEL RISULTATO
        with io.BytesIO() as img_bin:
            tesserino.save(img_bin, 'PNG')
            img_bin.seek(0)
            await interaction.followup.send(
                content=f"Tesserino identificativo: **{nome}**",
                file=discord.File(img_bin, filename=f"tesserino_{user_id}.png")
            )

    except Exception as e:
        print(f"Errore: {e}")
        await interaction.followup.send(f"❌ Errore durante la generazione: {e}")


# --- FINE COMANDO MOSTRA_TESSERINO ---

@bot.tree.command(name="elimina_tesserino", description="[ADMIN] Elimina un tesserino dal database")
async def elimina_tesserino(interaction: discord.Interaction, utente: discord.Member):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Solo gli Admin possono farlo.", ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM tesserini WHERE user_id = %s", (str(utente.id),))
    conn.commit(); cur.close(); conn.close()
    
    await interaction.response.send_message(f"🗑️ Tesserino di {utente.mention} eliminato.", ephemeral=True)

@bot.tree.command(name="pattuglia", description="[POLIZIA] Registra l'uscita di una pattuglia nel canale corrente")
@app_commands.describe(
    nominativo="Seleziona il nominativo radio dell'unità",
    numero="Inserisci il numero identificativo della pattuglia",
    capo_pattuglia="Ufficiale a capo dell'unità",
    nome_cp="Nome IC Capo Pattuglia",
    cognome_cp="Cognome IC Capo Pattuglia",
    guidatore="Agente alla guida",
    nome_g="Nome IC Guidatore",
    cognome_g="Cognome IC Guidatore",
    operatore_3="Eventuale terzo operatore",
    operatore_4="Eventuale quarto operatore",
    note="Annotazioni (es. Veicolo utilizzato)"
)
@app_commands.choices(nominativo=[
    app_commands.Choice(name="Alfa (Pattuglia Standard)", value="Alfa"),
    app_commands.Choice(name="India (Monopattuglia)", value="India"),
    app_commands.Choice(name="Bravo (Pattuglia Rinforzata)", value="Bravo"),
    app_commands.Choice(name="Delta (Unità Tattica GIS)", value="Delta"),
    app_commands.Choice(name="Charlie (Polizia Giudiziaria)", value="Charlie"),
    app_commands.Choice(name="Eagle (Unità Aerea)", value="Eagle"),
    app_commands.Choice(name="K9 (Unità Cinofila)", value="K9"),
    app_commands.Choice(name="Mike (Unità Motociclistica)", value="Mike"),
    app_commands.Choice(name="Frank (Supervisori)", value="Frank"),
    app_commands.Choice(name="Romeo (Nucleo Radiomobile)", value="Romeo"),
    app_commands.Choice(name="Sierra (Unità Navale)", value="Sierra")
])
async def pattuglia(
    interaction: Interaction, 
    nominativo: str,
    numero: str,
    capo_pattuglia: discord.Member, nome_cp: str, cognome_cp: str,
    guidatore: discord.Member, nome_g: str, cognome_g: str,
    operatore_3: discord.Member = None, 
    operatore_4: discord.Member = None,
    note: str = "N/A"
):
    if not is_polizia(interaction): 
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    # Conferma immediata invisibile agli altri
    await interaction.response.send_message("✅ Pattuglia registrata.", ephemeral=True)
    
    # Correzione Orario (+2 ore per fuso orario italiano)
    ora_corretta = datetime.datetime.now() + datetime.timedelta(hours=2)
    ora_uscita = ora_corretta.strftime("%H:%M")
    
    # Gestione menzioni operatori extra
    op_3_str = operatore_3.mention if operatore_3 else "N/A"
    op_4_str = operatore_4.mention if operatore_4 else "N/A"

    # Creazione Embed Grafico (Struttura Originale)
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐑𝐕𝐈𝐙𝐈𝐎 𝐏𝐀𝐓𝐓𝐔𝐆𝐋𝐈𝐀", color=discord.Color.blue())
    emb.description = f"""> • ɴᴏᴍɪɴᴀᴛɪᴠᴏ ᴜɴɪᴛᴀ̀: **{nominativo} {numero}**
> 
> • ᴄᴀᴘᴏ ᴘᴀᴛᴛᴜɢʟɪᴀ: {capo_pattuglia.mention} (**{nome_cp} {cognome_cp}**)
> 
> • ɢᴜɪᴅᴀᴛᴏʀᴇ: {guidatore.mention} (**{nome_g} {cognome_g}**)
> 
> • ᴛᴇʀᴢᴏ ᴏᴘᴇʀᴀᴛᴏʀᴇ: {op_3_str}
> 
> • ǫᴜᴀʀᴛᴏ ᴏᴘᴇʀᴀᴛᴏʀᴇ: {op_4_str}
> 
> • ᴏʀᴀʀɪᴏ ᴅɪ ᴜsᴄɪᴛᴀ: **{ora_uscita}**
> 
> • ɴᴏᴛᴇ: **{note}**"""

    # Invio SOLO nel canale dove è stato usato il comando
    await interaction.channel.send(embed=emb)
# --- FUNZIONE LOG MULTI-SERVER ---
async def invia_log_multi(tipo, embed):
    mappa_canali = {
        "Multa": "canale_log_multe",
        "Arresto": "canale_log_arresti",
        "Sequestro": "canale_log_sequestri",
        "Denuncia": "canale_log_denunce"
    }
    chiave = mappa_canali.get(tipo)
    if not chiave: return

    for guild_id, config in SERVER_CONFIG.items():
        guild = bot.get_guild(guild_id)
        if guild:
            channel_id = config.get(chiave)
            channel = guild.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)

# --- VIEW TABLET (HOME) ---
class TabletView(ui.View):
    def __init__(self, agente):
        super().__init__(timeout=None)
        self.agente = agente

    def embed_base(self, titolo, desc):
        embed = discord.Embed(title=f"📟 GN-OS | {titolo}", description=desc, color=0x2b2d31)
        embed.set_author(name=f"Operatore: {self.agente['nome_completo']} ({self.agente['grado']})")
        embed.set_footer(text=f"📡 Connessione Sicura | {datetime.datetime.now().strftime('%H:%M')}")
        return embed

    @ui.button(label="DATABASE CIVILE", style=discord.ButtonStyle.primary, emoji="👤", row=0)
    async def db_civile(self, interaction: discord.Interaction, button: ui.Button):
        # Query dinamica sui cittadini (Tabella documenti)
        cittadini = await db.fetch("SELECT user_id, nome, cognome FROM documenti ORDER BY nome LIMIT 25")
        if not cittadini:
            return await interaction.response.send_message("❌ Database anagrafico vuoto.", ephemeral=True)
        
        view = ViewSelezioneCittadino(self, cittadini)
        await interaction.response.edit_message(embed=self.embed_base("Database", "Seleziona un profilo per il fascicolo completo:"), view=view)

    @ui.button(label="RICERCA TARGA", style=discord.ButtonStyle.primary, emoji="🚘", row=0)
    async def search_plate(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModalRicercaTarga(self))

    @ui.button(label="AREA VERBALI", style=discord.ButtonStyle.secondary, emoji="⚖️", row=1)
    async def verbali(self, interaction: discord.Interaction, button: ui.Button):
        view = ViewVerbali(self)
        await interaction.response.edit_message(embed=self.embed_base("Gestione Atti", "Seleziona il tipo di verbale da redigere:"), view=view)

    @ui.button(label="SPEGNI DISPOSITIVO", style=discord.ButtonStyle.danger, emoji="📴", row=2)
    async def off(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="**GN-OS:** Sessione terminata correttamente. Arrivederci.", embed=None, view=None)

# --- RICERCA CITTADINI DINAMICA ---
class ViewSelezioneCittadino(ui.View):
    def __init__(self, tablet_view, cittadini):
        super().__init__()
        self.tablet = tablet_view
        options = [discord.SelectOption(label=f"{c['nome']} {c['cognome']}", value=c['user_id'], description=f"ID: {c['user_id']}") for c in cittadini]
        self.add_item(SelectCittadino(options, tablet_view))

    @ui.button(label="TORNA ALLA HOME", style=discord.ButtonStyle.gray, emoji="🏠")
    async def back(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=self.tablet.embed_base("Home", "Sistema Operativo Pronto."), view=self.tablet)

class SelectCittadino(ui.Select):
    def __init__(self, options, tablet_view):
        self.tablet = tablet_view
        super().__init__(placeholder="Scegli un cittadino...", options=options)

    async def callback(self, interaction: discord.Interaction):
        user_id = self.values[0]
        # Query incrociate su tabelle: documenti, patenti_registrate, licenze_armi
        doc = await db.fetchrow("SELECT * FROM documenti WHERE user_id = $1", user_id)
        patenti = await db.fetch("SELECT tipo FROM patenti_registrate WHERE user_id = $1", user_id)
        licenze = await db.fetch("SELECT tipo FROM licenze_armi WHERE user_id = $1", user_id)
        
        embed = discord.Embed(title=f"👤 Fascicolo: {doc['nome']} {doc['cognome']}", color=discord.Color.blue())
        embed.set_thumbnail(url=interaction.user.guild.icon.url if interaction.user.guild.icon else None)
        embed.add_field(name="Generalità", value=f"Nascita: {doc['data_nascita']}\nGenere: {doc['genere']}\nAltezza: {doc['altezza']}cm", inline=True)
        embed.add_field(name="Stato Patenti", value=", ".join([p['tipo'] for p in patenti]) if patenti else "Nessuna", inline=False)
        embed.add_field(name="Licenze Armi", value=", ".join([l['tipo'] for l in licenze]) if licenze else "Nessuna", inline=False)
        embed.set_footer(text=f"Consultazione di {self.tablet.agente['nome_completo']}")
        
        await interaction.response.send_message(embed=embed) # Pubblico, No Log

# --- GESTIONE VERBALI (CON LOG MULTI-SERVER) ---
class ViewVerbali(ui.View):
    def __init__(self, tablet_view):
        super().__init__()
        self.tablet = tablet_view

    @ui.button(label="Multa", style=discord.ButtonStyle.secondary, emoji="💰")
    async def m1(self, it: discord.Interaction, b: ui.Button): await it.response.send_modal(ModalLog("Multa", self.tablet))
    
    @ui.button(label="Arresto", style=discord.ButtonStyle.danger, emoji="⛓️")
    async def m2(self, it: discord.Interaction, b: ui.Button): await it.response.send_modal(ModalLog("Arresto", self.tablet))

    @ui.button(label="Sequestro", style=discord.ButtonStyle.secondary, emoji="🚜")
    async def m3(self, it: discord.Interaction, b: ui.Button): await it.response.send_modal(ModalLog("Sequestro", self.tablet))

    @ui.button(label="Denuncia", style=discord.ButtonStyle.secondary, emoji="📂")
    async def m4(self, it: discord.Interaction, b: ui.Button): await it.response.send_modal(ModalLog("Denuncia", self.tablet))

    @ui.button(label="INDIETRO", style=discord.ButtonStyle.gray, emoji="⬅️")
    async def back(self, it: discord.Interaction, b: ui.Button):
        await it.response.edit_message(embed=self.tablet.embed_base("Home", "Sistema Pronto."), view=self.tablet)

class ModalLog(ui.Modal):
    def __init__(self, tipo, tablet_view):
        self.tipo, self.tablet = tipo, tablet_view
        super().__init__(title=f"Compilazione {tipo}")

    sog = ui.TextInput(label="Cittadino / Oggetto", placeholder="Nome Cognome o Targa")
    mot = ui.TextInput(label="Motivazione", style=discord.TextStyle.paragraph)
    det = ui.TextInput(label="Dati Tecnici", placeholder="Importo, Minuti, o Merce sequestrata")

    async def on_submit(self, interaction: discord.Interaction):
        log_embed = discord.Embed(title=f"🚨 REGISTRAZIONE {self.tipo.upper()}", color=discord.Color.red())
        log_embed.add_field(name="Agente Responsabile", value=f"{self.tablet.agente['nome_completo']} ({self.tablet.agente['grado']})")
        log_embed.add_field(name="Server di Attività", value=interaction.guild.name)
        log_embed.add_field(name="Bersaglio/Soggetto", value=self.sog.value)
        log_embed.add_field(name="Motivazione", value=self.mot.value, inline=False)
        log_embed.add_field(name="Parametri Atto", value=self.det.value)
        log_embed.timestamp = datetime.datetime.now()

        await invia_log_multi(self.tipo, log_embed)
        await interaction.response.send_message(f"✅ Documento archiviato correttamente in centrale e inviato ai log multi-server.")

# --- RICERCA VEICOLI DINAMICA ---
class ModalRicercaTarga(ui.Modal, title="MCTC - Controllo Veicolo"):
    t = ui.TextInput(label="Inserisci Targa", placeholder="Es: AB123CD")
    def __init__(self, tablet):
        super().__init__()
        self.tablet = tablet

    async def on_submit(self, interaction: discord.Interaction):
        v = await db.fetchrow("SELECT v.*, d.nome, d.cognome FROM veicoli v LEFT JOIN documenti d ON v.owner_id = d.user_id WHERE v.targa = $1", self.t.value.upper())
        if not v: 
            return await interaction.response.send_message(f"❌ La targa `{self.t.value.upper()}` non risulta registrata.")
        
        emb = discord.Embed(title=f"🚘 Veicolo Targa: {v['targa']}", color=discord.Color.gold())
        emb.add_field(name="Modello", value=v['modello'] or "Non specificato")
        emb.add_field(name="Proprietario Anagrafico", value=f"{v['nome']} {v['cognome']}" if v['nome'] else "Sconosciuto")
        emb.add_field(name="Stato Amministrativo", value="⛔ SEQUESTRATO" if v['sequestrato'] else "✅ REGOLARE")
        emb.set_footer(text=f"Interrogazione di: {self.tablet.agente['nome_completo']}")
        
        await interaction.response.send_message(embed=emb) # Pubblico, No Log

# --- COMANDO SLASH /TABLET ---
@bot.tree.command(name="tablet", description="Sincronizza il Tablet Tattico GN-OS")
async def tablet(interaction: discord.Interaction):
    conf = SERVER_CONFIG.get(interaction.guild_id)
    
    # 1. Check Ruolo Polizia Configurato
    if not conf or interaction.guild.get_role(conf['ruolo_polizia']) not in interaction.user.roles:
        return await interaction.response.send_message("❌ Errore Critico: Modulo criptato non accessibile ai civili.", ephemeral=True)

    # 2. Check Database Tesserini
    agente = await db.fetchrow("SELECT nome_completo, grado FROM tesserini_polizia WHERE user_id = $1", str(interaction.user.id))
    if not agente: 
        return await interaction.response.send_message("⚠️ Identità non trovata nel database della Guardia Nacional.", ephemeral=True)

    view = TabletView(agente)
    await interaction.response.send_message(embed=view.embed_base("Home", "Benvenuto Agente. Sistema GN-OS online e pronto all'uso."), view=view, ephemeral=True)

@bot.tree.command(name="multa", description="[POLIZIA] Emetti una sanzione amministrativa")
@app_commands.describe(
    utente="Seleziona il cittadino", nome="Nome IC", cognome="Cognome IC", nascita="Data di nascita",
    motivo="Descrizione infrazione", sanzione="Ammontare da pagare", note="Annotazioni aggiuntive"
)
async def multa(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, nascita: str, motivo: str, sanzione: int, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    await interaction.response.defer()
    
    id_m = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO multe (id_multa, user_id, ammontare, motivo, data) VALUES (%s, %s, %s, %s, %s)",
                (id_m, str(utente.id), sanzione, motivo, datetime.datetime.now().strftime("%d/%m/%Y")))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐀𝐍𝐙𝐈𝐎𝐍𝐄", color=discord.Color.red())
    emb.description = f"""> • ɴᴏᴍᴇ: **{nome}**
> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**
> • ᴅᴀᴛᴀ ᴅɪ ɴᴀsᴄɪᴛᴀ: **{nascita}**
> • ᴍᴏᴛɪᴠᴏ sᴀɴᴢɪᴏɴᴇ: **{motivo}**
> • sᴀɴᴢɪᴏɴᴇ ᴘᴇᴄᴜɴɪᴀʀɪᴀ: **{sanzione}$**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**
> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: **{note}**"""
    await invia_log_globale("canale_log_multe", emb)
    await interaction.followup.send(f"✅ Sanzione emessa (ID: {id_m}).")

@bot.tree.command(name="sequestra_oggetto", description="[POLIZIA] Confisca item o armi")
@app_commands.describe(
    utente="Cittadino a cui sequestrare", nome="Nome IC", cognome="Cognome IC", 
    oggetto="Nome dell'oggetto", quantita="Numero di pezzi", motivo="Motivo del sequestro", 
    foto="Foto della refurtiva", note="Note extra"
)
async def sequestra_oggetto(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, oggetto: str, quantita: int, motivo: str, foto: discord.Attachment, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO sequestri_oggetti (guild_id, item_id, amount, agente_id, data) VALUES (%s, %s, %s, %s, %s)",
                (str(interaction.guild_id), oggetto, quantita, str(interaction.user.id), datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐐𝐔𝐄𝐒𝐓𝐑𝐎 𝐎𝐆𝐆𝐄𝐓𝐓𝐈", color=discord.Color.orange())
    emb.description = f"""> • ɴᴏᴍᴇ: **{nome}**
> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**
> • ᴏɢɢᴇᴛᴛᴏ sᴇǫᴜᴇsᴛʀᴀᴛᴏ: **{oggetto}**
> • ǫᴜᴀɴᴛɪᴛᴀ̀: **{quantita}**
> • ᴍᴏᴛɪᴠᴏ sᴇǫᴜᴇsᴛʀᴏ: **{motivo}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**
> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: **{note}**"""
    emb.set_image(url=foto.url)
    await invia_log_globale("canale_log_sequestri", emb)
    await interaction.followup.send("✅ Oggetto aggiunto al magazzino sequestri globale.")

@bot.tree.command(name="sequestra_veicolo", description="[POLIZIA] Confisca un veicolo a motore")
@app_commands.describe(nome="Nome IC proprietario", cognome="Cognome IC proprietario", targa="Targa del veicolo", motivo="Motivo del sequestro", foto="Foto del veicolo", note="Note extra")
async def sequestra_veicolo(interaction: Interaction, nome: str, cognome: str, targa: str, motivo: str, foto: discord.Attachment, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE veicoli SET sequestrato = TRUE WHERE targa = %s", (targa.upper(),))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐐𝐔𝐄𝐒𝐓𝐑𝐎 𝐕𝐄𝐈𝐂𝐎𝐋𝐎", color=discord.Color.dark_red())
    emb.description = f"""> • ɴᴏᴍᴇ: **{nome}**
> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**
> • ᴛᴀʀɢᴀ ᴠᴇɪᴄᴏʟᴏ sᴇǫᴜᴇsᴛʀᴀᴛᴏ: **{targa.upper()}**
> • ᴍᴏᴛɪᴠᴏ sᴇǫᴜᴇsᴛʀᴏ: **{motivo}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**
> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: **{note}**
> • sᴛᴀᴛᴏ ᴠᴇɪᴄᴏʟᴏ: **🛑 SEQUESTRATO**"""
    emb.set_image(url=foto.url)
    await invia_log_globale("canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Veicolo {targa.upper()} rimosso dalla circolazione.")

@bot.tree.command(name="visualizza_sequestri", description="[POLIZIA] Consulta il magazzino sequestri centrale")
async def visualizza_sequestri(interaction: Interaction):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT item_id, SUM(amount) as totale FROM sequestri_oggetti GROUP BY item_id HAVING SUM(amount) > 0")
    items = cur.fetchall()
    cur.close(); conn.close()
    
    emb = discord.Embed(title="# 𝐌𝐀𝐆𝐀𝐙𝐙𝐈𝐍𝐎 𝐒𝐄𝐐𝐔𝐄𝐒𝐓𝐑𝐈 𝐂𝐄𝐍𝐓𝐑𝐀𝐋𝐄", color=discord.Color.blue())
    if not items:
        emb.description = "📦 Il magazzino è attualmente vuoto."
    else:
        lista = "\n".join([f"> • **{x['item_id']}**: {x['totale']} unità" for x in items])
        emb.description = f"Elenco degli oggetti confiscati in tutta la rete:\n\n{lista}"
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="preleva_sequestro", description="[POLIZIA] Preleva o distruggi oggetti dal magazzino")
@app_commands.describe(oggetto="Nome dell'oggetto", quantita="Quantità da prelevare", motivo="Destinazione (es. Distruzione/Restituzione)")
async def preleva_sequestro(interaction: Interaction, oggetto: str, quantita: int, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT SUM(amount) as totale FROM sequestri_oggetti WHERE item_id = %s", (oggetto,))
    res = cur.fetchone()
    
    if not res or res['totale'] is None or res['totale'] < quantita:
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Quantità insufficiente. Disponibili in rete: {res['totale'] if res else 0}")

    cur.execute("INSERT INTO sequestri_oggetti (guild_id, item_id, amount, agente_id, data) VALUES (%s, %s, %s, %s, %s)",
                (str(interaction.guild_id), oggetto, -quantita, str(interaction.user.id), f"PRELIEVO: {motivo}"))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐏𝐑𝐄𝐋𝐈𝐄𝐕𝐎 𝐌𝐀𝐆𝐀𝐙𝐙𝐈𝐍𝐎", color=discord.Color.dark_green())
    emb.description = f"""> • ᴏɢɢᴇᴛᴛᴏ: **{oggetto}**
> • ǫᴜᴀɴᴛɪᴛᴀ̀ ᴘʀᴇʟᴇᴠᴀᴛᴀ: **{quantita}**
> • ᴍᴏᴛɪᴠᴏ ᴘʀᴇʟɪᴇᴠᴏ: **{motivo}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**"""
    
    await invia_log_globale("canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Prelievo registrato.")

@bot.tree.command(name="denuncia", description="[POLIZIA] Registra una querela ufficiale")
@app_commands.describe(nome_denunciante="Nome di chi denuncia", cognome_denunciante="Cognome di chi denuncia", nome_segnalato="Nome del denunciato", cognome_segnalato="Cognome del denunciato", fatti="Descrizione dell'accaduto", note="Annotazioni")
async def denuncia(interaction: Interaction, nome_denunciante: str, cognome_denunciante: str, nome_segnalato: str, cognome_segnalato: str, fatti: str, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐐𝐔𝐄𝐑𝐄𝐋𝐀", color=discord.Color.light_grey())
    emb.description = f"""> • ᴅᴇɴᴜɴᴄɪᴀɴᴛᴇ: **{nome_denunciante} {cognome_denunciante}**
> • sᴇɢɴᴀʟᴀᴛᴏ: **{nome_segnalato} {cognome_segnalato}**
> • ꜰᴀᴛᴛɪ: **{fatti}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**
> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: **{note}**"""
    await invia_log_globale("canale_log_denunce", emb)
    await interaction.response.send_message("✅ Querela registrata globalmente.")

@bot.tree.command(name="cerca_cittadino", description="[POLIZIA] Visualizza il profilo penale e civile completo")
@app_commands.describe(utente="Seleziona il cittadino da controllare")
async def cerca_cittadino(interaction: Interaction, utente: discord.Member):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT modello, targa, sequestrato FROM veicoli WHERE user_id = %s", (str(utente.id),))
    veicoli = cur.fetchall()
    cur.execute("SELECT ammontare, motivo, data FROM multe WHERE user_id = %s", (str(utente.id),))
    multe = cur.fetchall()
    cur.execute("SELECT motivo, data FROM arresti WHERE user_id = %s", (str(utente.id),))
    precedenti = cur.fetchall()
    cur.close(); conn.close()
    
    emb = discord.Embed(title=f"👤 DATABASE GLOBALE: {utente.display_name}", color=discord.Color.blue())
    v = "\n".join([f"> • {x['modello']} ({x['targa']}) {'🛑' if x['sequestrato'] else '✅'}" for x in veicoli]) or "Nessuno"
    m = "\n".join([f"> • {x['ammontare']}$ - {x['motivo']}" for x in multe]) or "Nessuna"
    p = "\n".join([f"> • {x['data']} - {x['motivo']}" for x in precedenti]) or "Incensurato"
    
    emb.add_field(name="🚗 𝐕𝐄𝐈𝐂𝐎𝐋𝐈 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐀𝐓𝐈", value=v, inline=False)
    emb.add_field(name="📜 𝐒𝐀𝐍𝐙𝐈𝐎𝐍𝐈 𝐏𝐄𝐍𝐃𝐄𝐍𝐓𝐈", value=m, inline=False)
    emb.add_field(name="⚖️ 𝐅𝐄𝐃𝐈𝐍𝐀 𝐏𝐄𝐍𝐀𝐋𝐄", value=p, inline=False)
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="pagamulta", description="Saldare una sanzione pendente")
async def pagamulta(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM multe WHERE user_id = %s LIMIT 1", (str(interaction.user.id),))
    m = cur.fetchone()
    if not m: return await interaction.followup.send("✅ Nessuna multa pendente.")
    
    cur.execute("SELECT wallet FROM users WHERE user_id = %s", (str(interaction.user.id),))
    u = cur.fetchone()
    if not u or u['wallet'] < m['ammontare']: return await interaction.followup.send("❌ Fondi insufficienti nel portafoglio.")
    
    cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (m['ammontare'], str(interaction.user.id)))
    cur.execute("DELETE FROM multe WHERE id_multa = %s", (m['id_multa'],))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"✅ Multa di {m['ammontare']}$ pagata con successo.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
