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
@bot.tree.command(name="pattuglia", description="[POLIZIA] Registra l'uscita di una pattuglia nel canale corrente")
@app_commands.describe(
    nominativo="Seleziona il nominativo radio dell'unità",
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
    app_commands.Choice(name="7-Eagle (Unità Aerea)", value="7-Eagle (E)"),
    app_commands.Choice(name="7-K9 (Unità Cinofila)", value="7-K9"),
    app_commands.Choice(name="7-Mary (Unità Motociclistica)", value="7-Mary (M)"),
    app_commands.Choice(name="7-Frank (Supervisori)", value="7-Frank (F)"),
    app_commands.Choice(name="7-Tango (Traffic Division)", value="7-Tango (T)"),
    app_commands.Choice(name="7-Ocean (Pattugliamento Marittimo)", value="7-Ocean (O)")
])
async def pattuglia(
    interaction: Interaction, 
    nominativo: str, 
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

    # Creazione Embed Grafico
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐑𝐕𝐈𝐙𝐈𝐎 𝐏𝐀𝐓𝐓𝐔𝐆𝐋𝐈𝐀", color=discord.Color.blue())
    emb.description = f"""> • ɴᴏᴍɪɴᴀᴛɪᴠᴏ ᴜɴɪᴛᴀ̀: **{nominativo}**
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
