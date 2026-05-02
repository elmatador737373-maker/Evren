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
def home(): return "Sistema CAD Polizia Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CARICAMENTO SEGRETI ---
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- CONFIGURAZIONE MULTI-SERVER ---
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

def is_polizia(interaction: Interaction):
    cfg = SERVER_CONFIG.get(interaction.guild_id)
    return cfg and any(role.id == cfg["ruolo_polizia"] for role in interaction.user.roles)

async def invia_log_format(interaction, tipo_log_key, embed):
    cfg = SERVER_CONFIG.get(interaction.guild_id)
    if not cfg: return
    channel = interaction.guild.get_channel(cfg.get(tipo_log_key))
    if channel:
        await channel.send(content=f"<@&{cfg['ruolo_polizia']}>", embed=embed)

# --- 1. REGISTRO ARRESTO ---
@bot.tree.command(name="arresto", description="Registra un arresto (Modulo Completo)")
async def arresto(interaction: Interaction, utente: discord.Member, nome: str, cognome: str, nascita: str, articoli: str, pena: str, sanzione: int, foto: str = "N/A", note: str = "N/A"):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, %s, %s)",
                (str(utente.id), str(interaction.user.id), f"[{articoli}]", 0, datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
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
> • ɴᴏᴛᴇ: **{note}**
> • ᴀʟʟᴇɢᴀ ꜰᴏᴛᴏ: **{foto}**"""
    await invia_log_format(interaction, "canale_log_arresti", emb)
    await interaction.followup.send(f"✅ Arresto registrato per {utente.mention}.")

# --- 2. REGISTRO SANZIONE ---
@bot.tree.command(name="multa", description="Emetti sanzione (Modulo Completo)")
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
> • ɴᴏᴛᴇ: **{note}**"""
    await invia_log_format(interaction, "canale_log_multe", emb)
    await interaction.followup.send(f"✅ Multa emessa (ID: {id_m}).")

# --- 3. REGISTRO SEQUESTRO OGGETTO ---
@bot.tree.command(name="sequestra_oggetto", description="Sequestra item (Modulo Completo)")
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
> • ɴᴏᴛᴇ: **{note}**
> • ᴀʟʟᴇɢᴀ ꜰᴏᴛᴏ: **{foto}**"""
    await invia_log_format(interaction, "canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Sequestro registrato per {utente.mention}.")

# --- 4. REGISTRO QUERELA (DENUNCIA) ---
@bot.tree.command(name="denuncia", description="Registra querela (Modulo Completo)")
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
    await invia_log_format(interaction, "canale_log_denunce", emb)
    await interaction.response.send_message(f"✅ Querela registrata.")

# --- COMANDI INVESTIGATIVI E MAGAZZINO ---

@bot.tree.command(name="prendi_sequestro", description="Ritira oggetti dal deposito")
async def prendi_sequestro(interaction: Interaction, nome_oggetto: str, quantita: int):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT SUM(amount) as totale FROM sequestri_oggetti WHERE guild_id = %s AND item_id = %s", (str(interaction.guild_id), nome_oggetto))
    res = cur.fetchone()
    if not res or not res['totale'] or res['totale'] < quantita:
        cur.close(); conn.close()
        return await interaction.followup.send("❌ Quantità insufficiente in deposito.")
    
    cur.execute("SELECT id, amount FROM sequestri_oggetti WHERE guild_id = %s AND item_id = %s ORDER BY id ASC", (str(interaction.guild_id), nome_oggetto))
    rows = cur.fetchall()
    rimanente = quantita
    for row in rows:
        if rimanente <= 0: break
        if row['amount'] <= rimanente:
            cur.execute("DELETE FROM sequestri_oggetti WHERE id = %s", (row['id'],))
            rimanente -= row['amount']
        else:
            cur.execute("UPDATE sequestri_oggetti SET amount = amount - %s WHERE id = %s", (rimanente, row['id']))
            rimanente = 0

    cur.execute("""INSERT INTO inventory (user_id, item_name, quantity) VALUES (%s, %s, %s)
                   ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity""",
                (str(interaction.user.id), nome_oggetto, quantita))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"✅ Hai ritirato {quantita}x {nome_oggetto}.")

@bot.tree.command(name="cerca_cittadino", description="Database completo cittadino")
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
    v_txt = "\n".join([f"• {v['modello']} ({v['targa']}) {'🛑' if v['sequestrato'] else '✅'}" for v in veicoli]) if veicoli else "Nessuno"
    m_txt = "\n".join([f"• {m['ammontare']}$ - {m['motivo']}" for m in multe]) if multe else "Nessuna"
    p_txt = "\n".join([f"• {p['data']} - {p['motivo']}" for p in precedenti]) if precedenti else "Incensurato"
    
    emb.add_field(name="🚗 Veicoli", value=v_txt, inline=False)
    emb.add_field(name="📜 Sanzioni", value=m_txt, inline=False)
    emb.add_field(name="⚖️ Precedenti", value=p_txt, inline=False)
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="cerca_targa", description="Ricerca per targa")
async def cerca_targa(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id, modello, sequestrato FROM veicoli WHERE targa = %s", (targa.upper(),))
    m = cur.fetchone()
    if not m: return await interaction.followup.send("❌ Targa inesistente.")
    proprietario = await bot.fetch_user(int(m['user_id']))
    emb = discord.Embed(title=f"🔎 TARGA: {targa.upper()}", color=discord.Color.dark_grey())
    emb.add_field(name="Proprietario", value=proprietario.mention); emb.add_field(name="Modello", value=m['modello'])
    emb.add_field(name="Stato", value="🛑 SEQUESTRATO" if m['sequestrato'] else "✅ REGOLARE")
    cur.close(); conn.close()
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="sequestra_mezzo", description="Sequestra un veicolo")
async def sequestra_mezzo(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE veicoli SET sequestrato = TRUE WHERE targa = %s", (targa.upper(),))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Veicolo {targa.upper()} sequestrato.")

@bot.tree.command(name="dissequestra_mezzo", description="Dissequestra un veicolo")
async def dissequestra_mezzo(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE veicoli SET sequestrato = FALSE WHERE targa = %s", (targa.upper(),))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Veicolo {targa.upper()} sbloccato.")

@bot.tree.command(name="pagamulta", description="Paga una multa (Per tutti)")
async def pagamulta(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM multe WHERE user_id = %s LIMIT 1", (str(interaction.user.id),))
    m = cur.fetchone()
    if not m: return await interaction.followup.send("✅ Non hai multe pendenti.")
    cur.execute("SELECT wallet FROM users WHERE user_id = %s", (str(interaction.user.id),))
    u = cur.fetchone()
    if not u or u['wallet'] < m['ammontare']: return await interaction.followup.send("❌ Soldi insufficienti.")
    cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (m['ammontare'], str(interaction.user.id)))
    cur.execute("DELETE FROM multe WHERE id_multa = %s", (m['id_multa'],))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"✅ Hai pagato {m['ammontare']}$.")

@bot.tree.command(name="registra_arma", description="Registra matricola arma")
async def registra_arma(interaction: Interaction, utente: discord.Member, modello: str, matricola: str, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO registro_armi (user_id, modello, matricola, motivo) VALUES (%s, %s, %s, %s)",
                    (str(utente.id), modello, matricola.upper(), motivo))
        conn.commit()
        await interaction.response.send_message(f"✅ Matricola {matricola.upper()} registrata.")
    except: await interaction.response.send_message("❌ Matricola già esistente.")
    finally: cur.close(); conn.close()

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
