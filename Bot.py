import os
import discord
import discord
from discord import ui, app_commands
from discord import app_commands, Interaction
import datetime
import random
import string
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask
from threading import Thread
import discord
from discord.ext import commands
from discord import app_commands # Utile se usi gli Slash Commands
import psycopg2
from psycopg2.extras import RealDictCursor

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
    1493606036949700608: {
        "ruolo_polizia": 1502710682561282148,
        "canale_log_arresti": 1493606413224775862,
        "canale_log_multe": 1493606409881911366,
        "canale_log_denunce": 1493606408640397473,
        "canale_log_sequestri": 1493606411882598410
    },
    1233353915559313478: {
        "ruolo_polizia": 1363487988570521670,
        "canale_log_arresti": 1496978741442773063,
        "canale_log_multe": 1482757565145288754,
        "canale_log_denunce": 1459560041563816129,
        "canale_log_sequestri": 1482753448951681214
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


# --- VIEW CONTROLLO (CHIUSURA) ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chiudi Ticket", style=discord.ButtonStyle.danger, custom_id="persistent_close_btn")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Chiusura del ticket in corso...")
        await interaction.channel.delete()

# --- SELECT MENU DINAMICO ---
class DynamicTicketSelect(discord.ui.Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        options = self.load_options(guild_id)
        super().__init__(
            placeholder="Cliccami e Scegli Una Opzione",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"ticket_select:{guild_id}"
        )

    def load_options(self, guild_id):
        rows = db_query("SELECT label, emoji, description, value_id FROM ticket_options WHERE guild_id = %s", (guild_id,), fetch=True)
        if not rows:
            return [discord.SelectOption(label="Nessuna opzione", value="none")]
        return [discord.SelectOption(label=r['label'], emoji=r['emoji'], description=r['description'], value=r['value_id']) for r in rows]

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none": return
        await interaction.response.defer(ephemeral=True)

        config = db_query("SELECT * FROM ticket_settings WHERE guild_id = %s", (interaction.guild.id,), fetch=True)[0]
        opt_info = db_query("SELECT label, mention_role_id FROM ticket_options WHERE guild_id = %s AND value_id = %s", 
                             (interaction.guild.id, self.values[0]), fetch=True)[0]

        category = interaction.guild.get_channel(config['category_id'])
        staff_role = interaction.guild.get_role(config['staff_role_id'])
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await interaction.guild.create_text_channel(
            name=f"{self.values[0]}-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        mention = ""
        if opt_info['mention_role_id']:
            m_role = interaction.guild.get_role(opt_info['mention_role_id'])
            if m_role: mention = m_role.mention

        embed = discord.Embed(title=f"Ticket: {opt_info['label']}", description=f"Benvenuto {interaction.user.mention}\nLo staff ti assisterà a breve.", color=discord.Color.blue())
        await channel.send(content=f"{mention} {interaction.user.mention}", embed=embed, view=TicketControlView())
        await interaction.followup.send(f"✅ Ticket aperto: {channel.mention}", ephemeral=True)

# --- VIEW PRINCIPALE ---
class TicketMainView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.add_item(DynamicTicketSelect(guild_id))

# --- COG COMANDI ---
class TicketSystem(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @bot.tree.command(name="setup_ticket")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction, categoria: discord.CategoryChannel, ruolo_staff: discord.Role, titolo: str, descrizione: str):
        db_query("""INSERT INTO ticket_settings (guild_id, category_id, staff_role_id, embed_title, embed_description) 
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT (guild_id) DO UPDATE SET 
                   category_id=EXCLUDED.category_id, staff_role_id=EXCLUDED.staff_role_id, 
                   embed_title=EXCLUDED.embed_title, embed_description=EXCLUDED.embed_description""", 
                   (interaction.guild.id, categoria.id, ruolo_staff.id, titolo, descrizione))
        
        embed = discord.Embed(title=titolo, description=descrizione, color=discord.Color.blue())
        await interaction.channel.send(embed=embed, view=TicketMainView(interaction.guild.id))
        await interaction.response.send_message("✅ Setup completato!", ephemeral=True)

    @bot.tree.command(name="add_ticket_type")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_type(self, interaction: discord.Interaction, label: str, id_univoco: str, emoji: str, descrizione: str, ruolo_notifica: discord.Role = None):
        role_id = ruolo_notifica.id if ruolo_notifica else None
        db_query("INSERT INTO ticket_options (guild_id, label, value_id, emoji, description, mention_role_id) VALUES (%s, %s, %s, %s, %s, %s)",
                 (interaction.guild.id, label, id_univoco, emoji, descrizione, role_id))
        await interaction.response.send_message(f"✅ Opzione `{label}` aggiunta! (Riesegui setup per aggiornare l'embed)", ephemeral=True)

# --- NEL MAIN DEL BOT (PER PERSISTENZA) ---

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

ID_CANALE_ARCHIVIO= 1503535784613904404
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
    
    # --- LOGICA ARCHIVIO FOTO ---
    message_id_salvato = None
    foto_url_archivio = foto.url

    try:
        canale_archivio = bot.get_channel(ID_CANALE_ARCHIVIO) or await bot.fetch_channel(ID_CANALE_ARCHIVIO)
        file_da_inviare = await foto.to_file()
        msg = await canale_archivio.send(
            content=f"📑 **Tesserino LAPD**: {nome} (Agente: {utente.id})", 
            file=file_da_inviare
        )
        foto_url_archivio = msg.attachments[0].url
        message_id_salvato = str(msg.id)
    except Exception as e:
        print(f"[LOG ERROR] Fallimento archivio tesserino: {e}")

    data_emissione = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%d/%m/%Y")
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO tesserini (user_id, nome_completo, grado, badge_num, unita, id_num, data_nascita, data_emissione, data_scadenza, foto_url, firma_ufficiale, message_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET 
        nome_completo=EXCLUDED.nome_completo, grado=EXCLUDED.grado, badge_num=EXCLUDED.badge_num, 
        unita=EXCLUDED.unita, id_num=EXCLUDED.id_num, data_nascita=EXCLUDED.data_nascita, 
        data_emissione=EXCLUDED.data_emissione, data_scadenza=EXCLUDED.data_scadenza, 
        foto_url=EXCLUDED.foto_url, firma_ufficiale=EXCLUDED.firma_ufficiale,
        message_id=EXCLUDED.message_id
    """, (str(utente.id), nome, grado, badge, unita, id_personale, nascita, data_emissione, scadenza, foto_url_archivio, firma, message_id_salvato))
    conn.commit(); cur.close(); conn.close()
    
    await interaction.followup.send(f"✅ Tesserino per {utente.mention} registrato e archiviato con successo.")

@bot.tree.command(name="mostra_tesserino", description="Visualizza il tuo tesserino LAPD ufficiale")
async def mostra_tesserino(interaction: discord.Interaction):
    await interaction.response.defer()
    user_id = str(interaction.user.id)
    
    try:
        conn = get_db_connection()
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM tesserini WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close(); conn.close()

        if not row:
            return await interaction.followup.send("⚠️ Tesserino non trovato. Chiedi a un Admin di crearlo.")

        # Carica il template
        tesserino = Image.open("IMG_0418.png").convert("RGBA")
        draw = ImageDraw.Draw(tesserino)

        # --- GESTIONE FOTO CON RECOVERY ---
        foto_url = row['foto_url']
        headers = {'User-Agent': 'Mozilla/5.0'}
        foto_res = requests.get(foto_url, headers=headers)

        if foto_res.status_code != 200 and row.get('message_id'):
            try:
                print(f"[DEBUG] Foto tesserino scaduta, rinfresco...")
                canale_archivio = bot.get_channel(ID_CANALE_ARCHIVIO) or await bot.fetch_channel(ID_CANALE_ARCHIVIO)
                msg = await canale_archivio.fetch_message(int(row['message_id']))
                foto_url = msg.attachments[0].url
                foto_res = requests.get(foto_url, headers=headers)
            except Exception as e:
                print(f"Errore rinfresco foto tesserino: {e}")

        if foto_res.status_code == 200:
            foto_agente = Image.open(io.BytesIO(foto_res.content)).convert("RGBA")
            foto_agente = foto_agente.resize((374, 460), Image.Resampling.LANCZOS)
            tesserino.paste(foto_agente, (59, 142), foto_agente)

        # --- SCRITTURA TESTI ---
        try:
            font_testo = ImageFont.truetype("arial.ttf", 25)
            font_firma = ImageFont.truetype("Serenity PersonalUseOnly.ttf", 35) 
        except:
            font_testo = ImageFont.load_default()
            font_firma = ImageFont.load_default()

        campi = [
            (row['nome_completo'].upper(), (605, 137)),
            (row['grado'].upper(),          (607, 187)),
            (str(row['badge_num']),        (650, 237)),
            (row['unita'].upper(),          (582, 288)),
            (str(row['id_num']),            (585, 337)),
            (row['data_nascita'],          (616, 395)),
            (row['data_emissione'],        (640, 438)),
            (row['data_scadenza'],         (642, 484)),
            (row['firma_ufficiale'],       (433, 632))
        ]

        for testo, pos in campi:
            fill_color = (0, 0, 0)
            f = font_firma if pos == (433, 632) else font_testo
            draw.text(pos, str(testo), font=f, fill=fill_color)

        # Invio
        with io.BytesIO() as img_bin:
            tesserino.save(img_bin, 'PNG')
            img_bin.seek(0)
            await interaction.followup.send(
                content=f"***{interaction.user.display_name}** mostra il proprio tesserino LAPD.*",
                file=discord.File(img_bin, filename=f"tesserino_{user_id}.png")
            )

    except Exception as e:
        print(f"Errore: {e}")
        await interaction.followup.send(f"❌ Errore durante la generazione: {e}")

@bot.tree.command(name="elimina_tesserino", description="[ADMIN] Elimina un tesserino dal database")
@app_commands.describe(utente="L'agente a cui revocare il tesserino")
async def elimina_tesserino(interaction: discord.Interaction, utente: discord.Member):
    if not is_admin(interaction):
        return await interaction.response.send_message("❌ Solo gli Admin possono farlo.", ephemeral=True)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Elimina il record
        cur.execute("DELETE FROM tesserini WHERE user_id = %s", (str(utente.id),))
        conn.commit()
        
        # Verifica se esisteva
        if cur.rowcount > 0:
            msg = f"🗑️ Tesserino di **{utente.display_name}** eliminato."
        else:
            msg = f"⚠️ Nessun tesserino trovato per {utente.display_name}."
            
        cur.close(); conn.close()
        await interaction.response.send_message(msg, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)



import discord
from discord import app_commands
import datetime

import discord
from discord import app_commands
import datetime
# ==========================================
# COMMAND TREE: RICERCA CITTADINO
# ==========================================
@bot.tree.command(name="ricerca_cittadino", description="Interroga l'archivio anagrafico completo")
@app_commands.describe(nome="Nome del cittadino", cognome="Cognome del cittadino")
async def ricerca_cittadino(interaction: discord.Interaction, nome: str, cognome: str):
    # Controllo autorizzazione
    ALLOWED_ROLE_ID = 1363487988570521670
    if not any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles):
        return await interaction.response.send_message("❌ Accesso negato: Solo personale autorizzato.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=False)

    try:
        conn = get_db_connection()
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query corretta basata sul tuo schema
        query = """
            SELECT d.*, 
                   (SELECT STRING_AGG(modello || ' [' || targa || ']', chr(10)) FROM public.veicoli WHERE owner_id = d.user_id) as lista_veicoli,
                   (SELECT STRING_AGG(tipo, ', ') FROM public.patenti_registrate WHERE user_id = d.user_id) as lista_patenti,
                   (SELECT STRING_AGG(tipo, ', ') FROM public.licenze_armi WHERE user_id = d.user_id) as porto_armi,
                   (SELECT STRING_AGG(modello || ' (Matr: ' || matricola || ')', chr(10)) FROM public.registro_armi WHERE user_id = d.user_id) as registro_armi,
                   (SELECT esito FROM public.certificati_medici WHERE user_id = d.user_id ORDER BY data_registrazione DESC LIMIT 1) as esito_medico
            FROM public.documenti d
            WHERE d.nome ILIKE %s AND d.cognome ILIKE %s
        """
        cur.execute(query, (nome, cognome))
        res = cur.fetchone()
        cur.close()
        conn.close()

        if not res:
            return await interaction.followup.send(f"⚠️ Nessun cittadino trovato con il nome: **{nome} {cognome}**")

        embed = discord.Embed(
            title=f"📂 FASCICOLO ANAGRAFICO: {res['nome']} {res['cognome']}", 
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Foto profilo (usa foto_url dalla tabella documenti)
        if res.get('foto_url'): 
            embed.set_thumbnail(url=res['foto_url'])

        # Info Generali
        info_civili = (
            f"**ID:** `{res['user_id']}`\n"
            f"**Nascita:** {res['data_nascita']} ({res['luogo_nascita']})\n"
            f"**Dati Fisici:** {res['altezza']}cm | {res['sesso']}\n"
            f"**Nazionalità:** {res['nazionalita']}"
        )
        embed.add_field(name="📌 Informazioni Civili", value=info_civili, inline=False)

        # Documentazione Legale
        patenti = res['lista_patenti'] if res['lista_patenti'] else "Nessuna"
        licenze = res['porto_armi'] if res['porto_armi'] else "Nessuna"
        
        # Patenti e Licenze (Risolti gli a capo interrotti che causavano il SyntaxError)
        embed.add_field(name="🪪 Patenti", value=f"```\n{patenti}\n
```", inline=True) 
        embed.add_field(name="🔫 Licenze Armi", value=f"```\n{licenze}\n```", inline=True)

        # Salute
        salute = res['esito_medico'] if res['esito_medico'] else "Nessun dato"
        embed.add_field(name="🏥 Ultimo Esito Medico", value=f"`{salute}`", inline=False)

        # Armi e Veicoli
        armi = res['registro_armi'] if res['registro_armi'] else "Nessuna arma registrata"
        veicoli = res['lista_veicoli'] if res['lista_veicoli'] else "Nessun veicolo intestato"
        
        # Registro Armi (Risolto l'a capo interrotto che causavano il SyntaxError)
        embed.add_field(name="📦 Registro Armi (Matricole)", value=f"```\n{armi}\n
```", inline=False)
        
        # Veicoli
        embed.add_field(name="🚘 Veicoli Intestati", value=f"```\n{veicoli}\n```", inline=False)
        
        embed.set_footer(text=f"Richiesto da: {interaction.user.display_name} | Database Centrale")
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"Errore ricerca cittadino: {e}")
        try:
            await interaction.followup.send("❌ Errore durante l'interrogazione del database.")
        except Exception:
            pass


# ==========================================
# COMMAND TREE: RICERCA TARGA
# ==========================================
@bot.tree.command(name="ricerca_targa", description="Controlla i dati di un veicolo tramite targa")
@app_commands.describe(targa="Inserisci la targa (es. AA123BB)")
async def ricerca_targa(interaction: discord.Interaction, targa: str):
    # Controllo autorizzazione
    ALLOWED_ROLE_ID = 1363487988570521670
    if not any(role.id == ALLOWED_ROLE_ID for role in interaction.user.roles):
        return await interaction.response.send_message("❌ Accesso negato.", ephemeral=True)
    
    await interaction.response.defer()
    targa_clean = targa.upper().strip()

    try:
        conn = get_db_connection()
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query che unisce veicoli (inclusi i nuovi campi) e documenti del proprietario
        cur.execute("""
            SELECT v.*, d.nome, d.cognome 
            FROM public.veicoli v
            LEFT JOIN public.documenti d ON v.owner_id = d.user_id
            WHERE UPPER(v.targa) = %s
        """, (targa_clean,))
        
        res = cur.fetchone()
        cur.close()
        conn.close()

        if not res:
            return await interaction.followup.send(f"⚠️ La targa `{targa_clean}` non è presente nei registri.")

        # Logica colore e stato sequestro
        is_sequestrato = res['sequestrato']
        colore = discord.Color.red() if is_sequestrato else discord.Color.green()
        stato = "🛑 SEQUESTRATO / FERMO" if is_sequestrato else "✅ REGOLARE"

        # --- INTEGRAZIONE NUOVI STATI VEICOLO ---
        if res.get('assicurato'):
            stato_assicurazione = f"🟢 ATTIVA (Scadenza: {res['data_scadenza_assicurazione']})"
        else:
            stato_assicurazione = "🔴 NON ASSICURATO"

        if res.get('revisionato'):
            stato_revisione = f"🟢 VALIDA (Scadenza: {res['data_scadenza_revisione']})"
        else:
            stato_revisione = "🔴 SCADUTA / NON REVISIONATO"
        # ----------------------------------------

        embed = discord.Embed(
            title="🔍 RISULTATO MOTORIZZAZIONE", 
            color=colore,
            timestamp=datetime.now()
        )
        
        # Mostra tutti i dati, inclusi i due nuovi stati richiesti
        info_veicolo = (
            f"**Modello:** {res['modello'] or 'N/D'}\n"
            f"**Targa:** `{res['targa']}`\n"
            f"**Stato Sequestro:** `{stato}`\n"
            f"**Assicurazione:** {stato_assicurazione}\n"
            f"**Revisione Statale:** {stato_revisione}"
        )
        embed.add_field(name="🚘 Dati Veicolo", value=info_veicolo, inline=False)
        
        owner_info = f"{res['nome']} {res['cognome']}" if res['nome'] else "Proprietario non identificato"
        embed.add_field(
            name="👤 Proprietario", 
            value=f"**Nominativo:** {owner_info}\n**ID:** `{res['owner_id']}`", 
            inline=False
        )
        
        if res.get('data_vendita'):
            embed.add_field(name="📅 Immatricolazione", value=f"`{res['data_vendita']}`", inline=True)
        
        embed.set_footer(text=f"Agente: {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"Errore ricerca targa: {e}")
        try:
            await interaction.followup.send("❌ Errore tecnico nel database veicoli.")
        except Exception:
            pass

import discord
from discord import app_commands
from discord import Interaction
import datetime

# Tabella di riferimento interna per i codici 7M
# Inserisci qui gli ID dei ruoli corrispondenti ai gradi
TABELLA_GRADI = {
    1502711637331677335: "7M-10",
    1502711751878119676: "7M-15",
    1502721934553518130: "7M-20",
    1502722124916199464: "7M-25",
    1502722222618316800: "7M-30",
    1502722310900027472: "7M-35",
    1502722374343200988: "7M-40",
    1502722456954212474: "7M-45",
    1502723337996992632: "7M-50",
    1502723425087520919: "7M-55",
    1502723585666584576: "7M-60",
    1502723688259391581: "7M-65"
}

def check_radio_code(member: discord.Member):
    """Cerca il codice radio più alto tra i ruoli posseduti dall'utente"""
    for role in member.roles:
        if role.id in TABELLA_GRADI:
            return TABELLA_GRADI[role.id]
    return "7M-XX"

@bot.tree.command(name="pattuglia", description="[POLIZIA] Registra l'uscita di una pattuglia")
@app_commands.describe(
    unita="Tipo di unità",
    numero="ID numerico (es. 01, 05)",
    capo_pattuglia="Ufficiale responsabile",
    nome_cp="Nome IC Capo Pattuglia",
    cognome_cp="Cognome IC Capo Pattuglia",
    operatore_2="Secondo operatore (obbligatorio per UP/UM)",
    operatore_3="Terzo operatore (obbligatorio per UM)",
    note="Veicolo o note aggiuntive"
)
@app_commands.choices(unita=[
    app_commands.Choice(name="UP (Unità Patrulla - 2 Op.)", value="UP"),
    app_commands.Choice(name="UM (Unità Motorizzata - 3 Op.)", value="UM"),
    app_commands.Choice(name="UT (Unità Tattica - 1 Op.)", value="UT")
])
async def pattuglia(
    interaction: Interaction, 
    unita: str,
    numero: str,
    capo_pattuglia: discord.Member, nome_cp: str, cognome_cp: str,
    operatore_2: discord.Member = None, 
    operatore_3: discord.Member = None,
    note: str = "N/A"
):
    if not is_polizia(interaction): 
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    # Validazione rapida dei requisiti minimi
    if unita == "UP" and not operatore_2:
        return await interaction.response.send_message("❌ L'unità UP richiede 2 operatori.", ephemeral=True)
    if unita == "UM" and (not operatore_2 or not operatore_3):
        return await interaction.response.send_message("❌ L'unità UM richiede 3 operatori.", ephemeral=True)

    await interaction.response.send_message("✅ Registro inviato.", ephemeral=True)
    
    ora_uscita = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%H:%M")
    
    # Recupero automatico dei prefissi radio
    prefisso_cp = check_radio_code(capo_pattuglia)
    prefisso_op2 = check_radio_code(operatore_2) if operatore_2 else ""
    prefisso_op3 = check_radio_code(operatore_3) if operatore_3 else ""

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐑𝐕𝐈𝐙𝐈𝐎 𝐏𝐀𝐓𝐓𝐔𝐆𝐋𝐈𝐀", color=discord.Color.blue())
    
    # Composizione dinamica dei campi
    desc = f"""> • ɴᴏᴍɪɴᴀᴛɪᴠᴏ ᴜɴɪᴛᴀ̀: **{unita} {numero}** (Radio: **{prefisso_cp}**)
> 
> • ᴄᴀᴘᴏ ᴘᴀᴛᴛᴜɢʟɪᴀ: {capo_pattuglia.mention} (**{nome_cp} {cognome_cp}**)"""

    if operatore_2:
        desc += f"\n> • sᴇᴄᴏɴᴅᴏ ᴏᴘᴇʀᴀᴛᴏʀᴇ: {operatore_2.mention} [**{prefisso_op2}**]"
    
    if operatore_3:
        desc += f"\n> • ᴛᴇʀᴢᴏ ᴏᴘᴇʀᴀᴛᴏʀᴇ: {operatore_3.mention} [**{prefisso_op3}**]"

    desc += f"""
> 
> • ᴏʀᴀʀɪᴏ ᴅɪ ᴜsᴄɪᴛᴀ: **{ora_uscita}**
> 
> • ɴᴏᴛᴇ: **{note}**"""

    emb.description = desc
    emb.set_footer(text=f"Servizio registrato da {interaction.user.display_name}")

    await interaction.channel.send(embed=emb)

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
# --- LOGICA TABLET GN-OS (RICERCA INTELLIGENTE + TESSERINI) ---

class TabletView(ui.View):
    def __init__(self, agente_data):
        super().__init__(timeout=None)
        self.agente = agente_data

    def embed_base(self, titolo, desc):
        embed = discord.Embed(title=f"📟 GN-OS | {titolo}", description=desc, color=0x2b2d31)
        embed.set_author(name=f"Operatore: {self.agente['nome_completo']} ({self.agente['grado']})")
        embed.set_footer(text=f"📡 Connessione Sicura | {datetime.datetime.now().strftime('%H:%M')}")
        return embed

    @ui.button(label="RICERCA INTELLIGENTE", style=discord.ButtonStyle.primary, emoji="🔍", row=0)
    async def smart_search(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ModalRicercaIntelligente(self))

    @ui.button(label="AREA VERBALI", style=discord.ButtonStyle.secondary, emoji="⚖️", row=0)
    async def verbali(self, interaction: discord.Interaction, button: ui.Button):
        view = ViewVerbali(self)
        await interaction.response.edit_message(embed=self.embed_base("Gestione Atti", "Seleziona il tipo di verbale:"), view=view)

    @ui.button(label="SPEGNI", style=discord.ButtonStyle.danger, emoji="📴", row=1)
    async def off(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="**GN-OS:** Sessione terminata.", embed=None, view=None)

# --- MODAL RICERCA INTELLIGENTE (CITTADINI E TARGHE) ---
class ModalRicercaIntelligente(ui.Modal, title="GN-OS | Ricerca Globale"):
    query = ui.TextInput(label="Cosa cerchi?", placeholder="Inserisci Nome, Cognome o Targa (anche parziale)...")

    def __init__(self, tablet):
        super().__init__()
        self.tablet = tablet

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        q = f"%{self.query.value}%"
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # 1. CERCA TRA I CITTADINI (Documenti)
        cur.execute("SELECT * FROM documenti WHERE nome ILIKE %s OR cognome ILIKE %s LIMIT 3", (q, q))
        cittadini = cur.fetchall()
        
        # 2. CERCA TRA LE TARGHE (Veicoli)
        cur.execute("SELECT * FROM veicoli WHERE targa ILIKE %s LIMIT 3", (q,))
        veicoli_trovati = cur.fetchall()

        if not cittadini and not veicoli_trovati:
            cur.close(); conn.close()
            return await interaction.followup.send("❌ Nessun risultato trovato nel Database Nazionale.", ephemeral=True)

        emb = discord.Embed(title=f"🔎 RISULTATI PER: {self.query.value.upper()}", color=0x2b2d31)

        # Sezione Cittadini
        if cittadini:
            for c in cittadini:
                # Per ogni cittadino cerchiamo i dati correlati
                cur.execute("SELECT COUNT(*) as tot FROM arresti WHERE user_id = %s", (c['user_id'],))
                prec = cur.fetchone()['tot']
                cur.execute("SELECT COUNT(*) as tot FROM veicoli WHERE owner_id = %s", (c['user_id'],))
                veic = cur.fetchone()['tot']
                
                info = f"🆔 ID: `{c['user_id']}`\n🎂 Nascita: `{c['data_nascita']}`\n⚖️ Precedenti: `{prec}` | 🚗 Veicoli: `{veic}`"
                emb.add_field(name=f"👤 {c['nome']} {c['cognome']}", value=info, inline=False)

        # Sezione Veicoli
        if veicoli_trovati:
            for v in veicoli_trovati:
                cur.execute("SELECT nome, cognome FROM documenti WHERE user_id = %s", (v['owner_id'],))
                prop = cur.fetchone()
                owner_name = f"{prop['nome']} {prop['cognome']}" if prop else "Sconosciuto"
                
                stato = "🛑 SEQUESTRATO" if v['sequestrato'] else "✅ REGOLARE"
                info_v = f"🚘 Modello: `{v['modello']}`\n👤 Prop: `{owner_name}`\n🛡️ Stato: {stato}"
                emb.add_field(name=f"🎫 TARGA: {v['targa']}", value=info_v, inline=False)

        cur.close(); conn.close()
        await interaction.followup.send(embed=emb)

# --- AREA VERBALI ---
class ViewVerbali(ui.View):
    def __init__(self, tablet_view):
        super().__init__(); self.tablet = tablet_view

    @ui.button(label="Arresto", style=discord.ButtonStyle.danger, emoji="⛓️")
    async def arresto(self, it: discord.Interaction, b: ui.Button): await it.response.send_modal(ModalTabletLog("Arresto", self.tablet))

    @ui.button(label="Multa", style=discord.ButtonStyle.secondary, emoji="💰")
    async def multa(self, it: discord.Interaction, b: ui.Button): await it.response.send_modal(ModalTabletLog("Multa", self.tablet))

    @ui.button(label="Sequestro", style=discord.ButtonStyle.secondary, emoji="🚜")
    async def sequestro(self, it: discord.Interaction, b: ui.Button): await it.response.send_modal(ModalTabletLog("Sequestro", self.tablet))

    @ui.button(label="INDIETRO", style=discord.ButtonStyle.gray)
    async def back(self, it: discord.Interaction, b: ui.Button):
        await it.response.edit_message(embed=self.tablet.embed_base("Home", "Sistema Pronto."), view=self.tablet)

class ModalTabletLog(ui.Modal):
    def __init__(self, tipo, tablet_view):
        self.tipo, self.tablet = tipo, tablet_view
        super().__init__(title=f"Redazione {tipo}")

    user_id = ui.TextInput(label="ID Discord Soggetto")
    nome_cognome = ui.TextInput(label="Nome Cognome IC")
    motivo = ui.TextInput(label="Motivazione", style=discord.TextStyle.paragraph)
    dato = ui.TextInput(label="Sanzione/Pena/Targa")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        data_ora = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%d/%m/%Y %H:%M")
        conn = get_db_connection(); cur = conn.cursor()

        if self.tipo == "Arresto":
            cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, %s, %s)",
                        (self.user_id.value, str(interaction.user.id), self.motivo.value, 0, data_ora))
            emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐀𝐑𝐑𝐄𝐒𝐓𝐎", color=discord.Color.dark_blue())
            emb.description = f"> • ɴᴏᴍᴇ: **{self.nome_cognome.value}**\n> • ᴍᴏᴛɪᴠᴏ: **{self.motivo.value}**\n> • ᴘᴇɴᴀ: **{self.dato.value}**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: {interaction.user.mention}"
            await invia_log_globale_tablet("canale_log_arresti", emb)

        elif self.tipo == "Multa":
            id_m = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            cur.execute("INSERT INTO multe (id_multa, user_id, ammontare, motivo, data) VALUES (%s, %s, %s, %s, %s)",
                        (id_m, self.user_id.value, int(self.dato.value), self.motivo.value, data_ora.split()[0]))
            emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐀𝐍𝐙𝐈𝐎𝐍𝐄", color=discord.Color.red())
            emb.description = f"> • ɴᴏᴍᴇ: **{self.nome_cognome.value}**\n> • ᴍᴏᴛɪᴠᴏ: **{self.motivo.value}**\n> • sᴀɴᴢɪᴏɴᴇ: **{self.dato.value}$**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: {interaction.user.mention}"
            await invia_log_globale_tablet("canale_log_multe", emb)

        elif self.tipo == "Sequestro":
            cur.execute("UPDATE veicoli SET sequestrato = TRUE WHERE UPPER(targa) = UPPER(%s)", (self.dato.value,))
            emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐐𝐔𝐄𝐒𝐓𝐑𝐎 𝐕𝐄𝐈𝐂𝐎𝐋𝐎", color=discord.Color.dark_red())
            emb.description = f"> • ɴᴏᴍᴇ: **{self.nome_cognome.value}**\n> • ᴛᴀʀɢᴀ: **{self.dato.value.upper()}**\n> • sᴛᴀᴛᴏ: **🛑 SEQUESTRATO**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: {interaction.user.mention}"
            await invia_log_globale_tablet("canale_log_sequestri", emb)

        conn.commit(); cur.close(); conn.close()
        await interaction.followup.send(f"✅ Inviato ai log di sistema.", ephemeral=True)

# --- COMANDO /TABLET ---
@bot.tree.command(name="tablet", description="Accendi il Tablet Tattico GN-OS")
async def tablet(interaction: discord.Interaction):
    if not is_polizia(interaction):
        return await interaction.response.send_message("❌ Accesso negato.", ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT nome_completo, grado FROM tesserini WHERE user_id = %s", (str(interaction.user.id),))
    agente = cur.fetchone()
    cur.close(); conn.close()

    if not agente:
        return await interaction.response.send_message("⚠️ Tesserino non trovato. Crealo con /crea_tesserino", ephemeral=True)

    await interaction.response.send_message(embed=TabletView(agente).embed_base("Home", "Sistema Pronto."), view=TabletView(agente), ephemeral=True)

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

@bot.event
async def on_ready():
    bot.add_view(TicketControlView())
    configs = db_query("SELECT guild_id FROM ticket_settings", fetch=True)
    for conf in configs:
        bot.add_view(TicketMainView(conf['guild_id']))
    print("Ticket System Online")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
