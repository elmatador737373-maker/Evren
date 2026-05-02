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

# --- CONFIGURAZIONE FLASK (KEEP ALIVE PER RENDER) ---
app = Flask('')
@app.route('/')
def home(): return "Sistema CAD Polizia Globale Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CARICAMENTO SEGRETI E DATABASE ---
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- CONFIGURAZIONE MULTI-SERVER ---
SERVER_CONFIG = {
    1233353915559313478: {  # SERVER 1
        "ruolo_polizia": 1363487988570521670,
        "canale_log_arresti": 1496978741442773063,
        "canale_log_multe": 1482757565145288754,
        "canale_log_denunce": 1459560041563816129,
        "canale_log_sequestri": 1482753448951681214
    },
    1499394373270507701: {  # SERVER 2
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

# --- UTILS & LOG GLOBALE ---
def is_polizia(interaction: Interaction):
    cfg = SERVER_CONFIG.get(interaction.guild_id)
    return cfg and any(role.id == cfg["ruolo_polizia"] for role in interaction.user.roles)

async def invia_log_globale(tipo_log_key, embed):
    """Invia il log a tutti i server configurati e tagga il rispettivo ruolo polizia."""
    for guild_id, cfg in SERVER_CONFIG.items():
        guild = bot.get_guild(guild_id)
        if guild:
            channel = guild.get_channel(cfg.get(tipo_log_key))
            ruolo_id = cfg.get("ruolo_polizia")
            if channel:
                try:
                    await channel.send(content=f"<@&{ruolo_id}>", embed=embed)
                except: pass

# --- 1. REGISTRO ARRESTO ---
@bot.tree.command(name="arresto", description="Registra un arresto nel database e nei log globali")
async def arresto(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, nascita: str, articoli: str, pena: str, sanzione: int, foto: str = "N/A", note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
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
> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: **{note}**
> • ᴀʟʟᴇɢᴀ ꜰᴏᴛᴏ: **{foto}**"""
    await invia_log_globale("canale_log_arresti", emb)
    await interaction.followup.send(f"✅ Arresto registrato globalmente.")

# --- 2. REGISTRO SANZIONE ---
@bot.tree.command(name="multa", description="Emetti una sanzione amministrativa")
async def multa(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, nascita: str, motivo: str, sanzione: int, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    cfg = SERVER_CONFIG.get(interaction.guild_id)
    id_m = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO multe (id_multa, user_id, ammontare, id_azienda, motivo, data) VALUES (%s, %s, %s, %s, %s, %s)",
                (id_m, str(utente.id), sanzione, str(cfg["ruolo_polizia"]), motivo, datetime.datetime.now().strftime("%d/%m/%Y")))
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

# --- 3. REGISTRO SEQUESTRO OGGETTO ---
@bot.tree.command(name="sequestra_oggetto", description="Sequestra item dal cittadino al magazzino globale")
async def sequestra_oggetto(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, oggetto: str, quantita: int, motivo: str, foto: str = "N/A", note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE inventory SET quantity = quantity - %s WHERE user_id = %s AND item_name = %s", (quantita, str(utente.id), oggetto))
    cur.execute("DELETE FROM inventory WHERE quantity <= 0")
    cur.execute("INSERT INTO sequestri_oggetti (guild_id, item_id, amount, agente_id, data) VALUES (%s, %s, %s, %s, %s)",
                (str(interaction.guild_id), oggetto, quantita, str(interaction.user.id), datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐐𝐔𝐄𝐒𝐓𝐑𝐎", color=discord.Color.orange())
    emb.description = f"""> • ɴᴏᴍᴇ: **{nome}**
> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**
> • ᴏɢɢᴇᴛᴛᴏ ᴅᴇʟ sᴇǫᴜᴇsᴛʀᴏ: **{oggetto}**
> • ǫᴜᴀɴᴛɪᴛᴀ̀: **{quantita}**
> • ᴍᴏᴛɪᴠᴏ sᴇǫᴜᴇsᴛʀᴏ: **{motivo}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**
> • ɴᴏᴛᴇ [ sᴇ ᴘʀᴇsᴇɴᴛɪ ]: **{note}**
> • ᴀʟʟᴇɢᴀ ꜰᴏᴛᴏ: **{foto}**"""
    await invia_log_globale("canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Sequestro di {oggetto} completato.")

# --- 4. REGISTRO QUERELA (DENUNCIA) ---
@bot.tree.command(name="denuncia", description="Registra una querela ufficiale")
async def denuncia(interaction: Interaction, nome_denunciante: str, cognome_denunciante: str, nome_segnalato: str, cognome_segnalato: str, fatti: str, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐐𝐔𝐄𝐑𝐄𝐋𝐀", color=discord.Color.light_grey())
    emb.description = f"""> • ɴᴏᴍᴇ ᴅᴇɴᴜɴᴄɪᴀɴᴛᴇ: **{nome_denunciante}**
> • ᴄᴏɢɴᴏᴍᴇ: **{cognome_denunciante}**
> • ɴᴏᴍᴇ sᴇɢɴᴀʟᴀᴛᴏ: **{nome_segnalato}**
> • ᴄᴏɢɴᴏᴍᴇ: **{cognome_segnalato}**
> • ᴅᴇsᴄʀɪᴢɪᴏɴᴇ ᴅᴇɪ ꜰᴀᴛᴛɪ: **{fatti}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ/ɪ: **{interaction.user.mention}**
> • ɴᴏᴛᴇ: **{note}**"""
    await invia_log_globale("canale_log_denunce", emb)
    await interaction.response.send_message("✅ Querela registrata globalmente.")

# --- 5. RICERCA CITTADINO & TARGA ---
@bot.tree.command(name="cerca_cittadino", description="Profilo investigativo completo")
async def cerca_cittadino(interaction: Interaction, utente: discord.Member):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT modello, targa, sequestrato FROM veicoli WHERE user_id = %s", (str(utente.id),))
    veicoli = cur.fetchall()
    cur.execute("SELECT ammontare, motivo, data FROM multe WHERE user_id = %s", (str(utente.id),))
    multe = cur.fetchall()
    cur.execute("SELECT motivo, data FROM arresti WHERE user_id = %s", (str(utente.id),))
    precedenti = cur.fetchall()
    cur.close(); conn.close()
    
    emb = discord.Embed(title=f"👤 DATABASE: {utente.display_name}", color=discord.Color.blue())
    v = "\n".join([f"• {x['modello']} ({x['targa']}) {'🛑' if x['sequestrato'] else '✅'}" for x in veicoli]) or "Nessuno"
    m = "\n".join([f"• {x['ammontare']}$ - {x['motivo']}" for x in multe]) or "Nessuna"
    p = "\n".join([f"• {x['data']} - {x['motivo']}" for x in precedenti]) or "Incensurato"
    emb.add_field(name="🚗 Veicoli", value=v, inline=False); emb.add_field(name="📜 Sanzioni", value=m, inline=False); emb.add_field(name="⚖️ Fedina", value=p, inline=False)
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="cerca_targa", description="Ricerca proprietario da targa")
async def cerca_targa(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id, modello, sequestrato FROM veicoli WHERE targa = %s", (targa.upper(),))
    res = cur.fetchone()
    if not res: return await interaction.response.send_message("❌ Targa inesistente.")
    p = await bot.fetch_user(int(res['user_id']))
    emb = discord.Embed(title=f"🔎 TARGA: {targa.upper()}", color=discord.Color.dark_grey())
    emb.add_field(name="Proprietario", value=p.mention); emb.add_field(name="Modello", value=res['modello']); emb.add_field(name="Stato", value="🛑 SEQUESTRATO" if res['sequestrato'] else "✅ REGOLARE")
    cur.close(); conn.close()
    await interaction.response.send_message(embed=emb)

# --- 6. GESTIONE VEICOLI & ARMI ---
@bot.tree.command(name="sequestra_mezzo", description="Blocca un veicolo")
async def sequestra_mezzo(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE veicoli SET sequestrato = TRUE WHERE targa = %s", (targa.upper(),))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"🚫 Veicolo {targa.upper()} sequestrato.")

@bot.tree.command(name="registra_arma", description="Registra matricola")
async def registra_arma(interaction: Interaction, utente: discord.Member, modello: str, matricola: str, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO registro_armi (user_id, modello, matricola, motivo) VALUES (%s, %s, %s, %s)",
                    (str(utente.id), modello, matricola.upper(), motivo))
        conn.commit(); await interaction.response.send_message("✅ Arma registrata.")
    except: await interaction.response.send_message("❌ Matricola già esistente.")
    finally: cur.close(); conn.close()

# --- 7. PAGAMULTA (PER TUTTI) ---
@bot.tree.command(name="pagamulta", description="Paga una sanzione pendente")
async def pagamulta(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM multe WHERE user_id = %s LIMIT 1", (str(interaction.user.id),))
    m = cur.fetchone()
    if not m: return await interaction.followup.send("✅ Nessuna multa pendente.")
    cur.execute("SELECT wallet FROM users WHERE user_id = %s", (str(interaction.user.id),))
    u = cur.fetchone()
    if not u or u['wallet'] < m['ammontare']: return await interaction.followup.send("❌ Soldi insufficienti.")
    cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (m['ammontare'], str(interaction.user.id)))
    cur.execute("DELETE FROM multe WHERE id_multa = %s", (m['id_multa'],))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"✅ Multa di {m['ammontare']}$ pagata.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
