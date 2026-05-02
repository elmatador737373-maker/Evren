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
def home(): return "Sistema CAD Polizia Globale Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CONFIGURAZIONE ---
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

# --- NUOVI COMANDI GESTIONE MAGAZZINO SEQUESTRI ---

@bot.tree.command(name="visualizza_sequestri", description="[GLOBALE] Visualizza tutti gli oggetti presenti nel magazzino sequestri")
async def visualizza_sequestri(interaction: Interaction):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT item_id, SUM(amount) as totale FROM sequestri_oggetti GROUP BY item_id")
    items = cur.fetchall()
    cur.close(); conn.close()
    
    if not items: return await interaction.followup.send("📦 Il magazzino sequestri è attualmente vuoto.")
    
    emb = discord.Embed(title="📦 MAGAZZINO SEQUESTRI CENTRALE", color=discord.Color.blue())
    lista = "\n".join([f"• **{x['item_id']}**: {x['totale']} unità" for x in items])
    emb.description = f"Elenco globale degli oggetti confiscati:\n\n{lista}"
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="preleva_sequestro", description="[GLOBALE] Preleva un oggetto dal magazzino sequestri")
@app_commands.describe(oggetto="ID dell'oggetto da prelevare", quantita="Quantità da rimuovere", motivo="Motivo del prelievo (es. Distruzione/Restituzione)")
async def preleva_sequestro(interaction: Interaction, oggetto: str, quantita: int, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT SUM(amount) as totale FROM sequestri_oggetti WHERE item_id = %s", (oggetto,))
    res = cur.fetchone()
    
    if not res or res['totale'] is None or res['totale'] < quantita:
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Quantità insufficiente o oggetto non trovato. Disponibili: {res['totale'] if res else 0}")

    # Sottraiamo dal magazzino (inserendo un record negativo o eliminando)
    cur.execute("INSERT INTO sequestri_oggetti (guild_id, item_id, amount, agente_id, data) VALUES (%s, %s, %s, %s, %s)",
                (str(interaction.guild_id), oggetto, -quantita, str(interaction.user.id), f"PRELIEVO: {motivo}"))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐏𝐑𝐄𝐋𝐈𝐄𝐕𝐎 𝐌𝐀𝐆𝐀𝐙𝐙𝐈𝐍𝐎", color=discord.Color.dark_green())
    emb.description = f"""> • ᴏɢɢᴇᴛᴛᴏ: **{oggetto}**
> • ǫᴜᴀɴᴛɪᴛᴀ̀ ᴘʀᴇʟᴇᴠᴀᴛᴀ: **{quantita}**
> • ᴍᴏᴛɪᴠᴏ ᴘʀᴇʟɪᴇᴠᴏ: **{motivo}**
> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: **{interaction.user.mention}**"""
    
    await invia_log_globale("canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Hai prelevato {quantita}x {oggetto} dal magazzino.")

# --- COMANDI OPERATIVI ESISTENTI (SINTESI) ---

@bot.tree.command(name="arresto", description="[GLOBALE] Registra un arresto")
async def arresto(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, nascita: str, articoli: str, pena: str, sanzione: int, foto: discord.Attachment, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, %s, %s)",
                (str(utente.id), str(interaction.user.id), f"Arresto: {articoli}", 0, datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐀𝐑𝐑𝐄𝐒𝐓𝐎", color=discord.Color.dark_blue())
    emb.description = f"> • ɴᴏᴍᴇ: **{nome}**\n> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**\n> • ᴅᴀᴛᴀ ᴅɪ ɴᴀsᴄɪᴛᴀ: **{nascita}**\n> • ᴀʀᴛɪᴄᴏʟᴏ/ɪ: **{articoli}**\n> • ᴘᴇɴᴀ: **{pena}**\n> • sᴀɴᴢɪᴏɴᴇ: **{sanzione}$**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: **{interaction.user.mention}**"
    emb.set_image(url=foto.url)
    await invia_log_globale("canale_log_arresti", emb)
    await interaction.followup.send(f"✅ Arresto registrato.")

@bot.tree.command(name="multa", description="[GLOBALE] Emetti una sanzione")
async def multa(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, nascita: str, motivo: str, sanzione: int, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    id_m = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO multe (id_multa, user_id, ammontare, motivo, data) VALUES (%s, %s, %s, %s, %s)",
                (id_m, str(utente.id), sanzione, motivo, datetime.datetime.now().strftime("%d/%m/%Y")))
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐀𝐍𝐙𝐈𝐎𝐍𝐄", color=discord.Color.red())
    emb.description = f"> • ɴᴏᴍᴇ: **{nome}**\n> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**\n> • ᴍᴏᴛɪᴠᴏ: **{motivo}**\n> • sᴀɴᴢɪᴏɴᴇ: **{sanzione}$**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: **{interaction.user.mention}**"
    await invia_log_globale("canale_log_multe", emb)
    await interaction.followup.send(f"✅ Sanzione ID: {id_m} emessa.")

@bot.tree.command(name="sequestra_oggetto", description="[GLOBALE] Sequestra item/armi")
async def sequestra_oggetto(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, oggetto: str, quantita: int, motivo: str, foto: discord.Attachment, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor()
    # Togliamo l'item dall'inventario dell'utente
    cur.execute("UPDATE inventory SET quantity = quantity - %s WHERE user_id = %s AND item_name = %s", (quantita, str(utente.id), oggetto))
    cur.execute("DELETE FROM inventory WHERE quantity <= 0")
    # Aggiungiamo al magazzino sequestri
    cur.execute("INSERT INTO sequestri_oggetti (guild_id, item_id, amount, agente_id, data) VALUES (%s, %s, %s, %s, %s)",
                (str(interaction.guild_id), oggetto, quantita, str(interaction.user.id), datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐐𝐔𝐄𝐒𝐓𝐑𝐎", color=discord.Color.orange())
    emb.description = f"> • ɴᴏᴍᴇ: **{nome}**\n> • ᴄᴏɢɴᴏᴍᴇ: **{cognome}**\n> • ᴏɢɢᴇᴛᴛᴏ: **{oggetto}**\n> • ǫᴜᴀɴᴛɪᴛᴀ̀: **{quantita}**\n> • ᴍᴏᴛɪᴠᴏ: **{motivo}**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: **{interaction.user.mention}**"
    emb.set_image(url=foto.url)
    await invia_log_globale("canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Oggetto sequestrato e inserito in magazzino.")

@bot.tree.command(name="sequestra_veicolo", description="[GLOBALE] Sequestra mezzo")
async def sequestra_veicolo(interaction: Interaction, nome: str, cognome: str, targa: str, motivo: str, foto: discord.Attachment, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE veicoli SET sequestrato = TRUE WHERE targa = %s", (targa.upper(),))
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐒𝐄𝐐𝐔𝐄𝐒𝐓𝐑𝐎", color=discord.Color.dark_red())
    emb.description = f"> • ᴛᴀʀɢᴀ ᴠᴇɪᴄᴏʟᴏ: **{targa.upper()}**\n> • ᴍᴏᴛɪᴠᴏ sᴇǫᴜᴇsᴛʀᴏ: **{motivo}**\n> • sᴛᴀᴛᴏ ᴠᴇɪᴄᴏʟᴏ: **🛑 SEQUESTRATO**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: **{interaction.user.mention}**"
    emb.set_image(url=foto.url)
    await invia_log_globale("canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Veicolo {targa.upper()} sequestrato.")

@bot.tree.command(name="cerca_cittadino", description="[GLOBALE] Ricerca profilo")
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
    emb = discord.Embed(title=f"👤 DATABASE GLOBALE: {utente.display_name}", color=discord.Color.blue())
    v = "\n".join([f"• {x['modello']} ({x['targa']}) {'🛑' if x['sequestrato'] else '✅'}" for x in veicoli]) or "Nessuno"
    m = "\n".join([f"• {x['ammontare']}$ - {x['motivo']}" for x in multe]) or "Nessuna"
    p = "\n".join([f"• {x['data']} - {x['motivo']}" for x in precedenti]) or "Incensurato"
    emb.add_field(name="🚗 Veicoli", value=v, inline=False); emb.add_field(name="📜 Sanzioni", value=m, inline=False); emb.add_field(name="⚖️ Fedina", value=p, inline=False)
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="denuncia", description="[GLOBALE] Querela ufficiale")
async def denuncia(interaction: Interaction, nome_denunciante: str, cognome_denunciante: str, nome_segnalato: str, cognome_segnalato: str, fatti: str, note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    emb = discord.Embed(title="# 𝐑𝐄𝐆𝐈𝐒𝐓𝐑𝐎 𝐐𝐔𝐄𝐑𝐄𝐋𝐀", color=discord.Color.light_grey())
    emb.description = f"> • ᴅᴇɴᴜɴᴄɪᴀɴᴛᴇ: **{nome_denunciante} {cognome_denunciante}**\n> • sᴇɢɴᴀʟᴀᴛᴏ: **{nome_segnalato} {cognome_segnalato}**\n> • ꜰᴀᴛᴛɪ: **{fatti}**\n> • ᴏᴘᴇʀᴀᴛᴏʀᴇ: **{interaction.user.mention}**"
    await invia_log_globale("canale_log_denunce", emb)
    await interaction.response.send_message("✅ Querela registrata.")

@bot.tree.command(name="pagamulta", description="Paga sanzione")
async def pagamulta(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM multe WHERE user_id = %s LIMIT 1", (str(interaction.user.id),))
    m = cur.fetchone()
    if not m: return await interaction.followup.send("✅ Nessuna multa pendente.")
    cur.execute("SELECT wallet FROM users WHERE user_id = %s", (str(interaction.user.id),))
    u = cur.fetchone()
    if not u or u['wallet'] < m['ammontare']: return await interaction.followup.send("❌ Fondi insufficienti.")
    cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (m['ammontare'], str(interaction.user.id)))
    cur.execute("DELETE FROM multe WHERE id_multa = %s", (m['id_multa'],))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"✅ Multa di {m['ammontare']}$ pagata.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
