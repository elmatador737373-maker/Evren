import os
import discord
from discord import app_commands, Interaction
import datetime
import random
import string
import psycopg2
from psycopg2.extras import RealDictCursor

# --- CARICAMENTO CONFIGURAZIONE DI SICUREZZA (Render Env Vars) ---
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- CONFIGURAZIONE MULTI-SERVER ---
# Inserisci gli ID corretti per i tuoi due server
SERVER_CONFIG = {
    1233353915559313478: {  # ID SERVER 1
        "ruolo_polizia": 1363487988570521670,
        "canale_log_arresti": 1496978741442773063,
        "canale_log_multe": 1482757565145288754,
        "canale_log_denunce": 1459560041563816129,
        "canale_log_sequestri": 1482753448951681214
    },
    1499394373270507701: {  # ID SERVER 2
        "ruolo_polizia": 1499394715634761789,
        "canale_log_arresti": 1499398686067658897,
        "canale_log_multe": 1499398731504685207,
        "canale_log_denunce": 1499398857979727872,
        "canale_log_sequestri": 1499398820851744799
    }
}

# --- CONNESSIONE DATABASE ---
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        print(f"❌ Errore connessione Database: {e}")
        return None

# --- SETUP BOT ---
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# --- UTILS ---
def get_cfg(guild_id): 
    return SERVER_CONFIG.get(guild_id)

def is_polizia(interaction: Interaction):
    cfg = get_cfg(interaction.guild_id)
    return cfg and any(role.id == cfg["ruolo_polizia"] for role in interaction.user.roles)

async def invia_log(interaction, tipo_log_key, embed):
    cfg = get_cfg(interaction.guild_id)
    if not cfg: return
    channel_id = cfg.get(tipo_log_key)
    channel = interaction.guild.get_channel(channel_id)
    if channel: await channel.send(embed=embed)

# --- COMANDI POLIZIA ---

@bot.tree.command(name="arresto", description="Registra un arresto nel database")
async def arresto(interaction: Interaction, utente: discord.Member, tempo_minuti: int, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Accesso negato.", ephemeral=True)
    
    await interaction.response.defer()
    data_attuale = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    conn = get_db_connection()
    if not conn: return await interaction.followup.send("❌ Database offline.")
    
    cur = conn.cursor()
    cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, %s, %s)",
                (str(utente.id), str(interaction.user.id), motivo, tempo_minuti, data_attuale))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="⚖️ VERBALE DI ARRESTO", color=discord.Color.dark_blue(), timestamp=discord.utils.utcnow())
    emb.add_field(name="👤 Detenuto", value=utente.mention, inline=True)
    emb.add_field(name="⏳ Pena", value=f"{tempo_minuti} minuti", inline=True)
    emb.add_field(name="👮 Agente", value=interaction.user.mention, inline=False)
    emb.add_field(name="📝 Motivo", value=motivo, inline=False)

    await invia_log(interaction, "canale_log_arresti", emb)
    await interaction.followup.send(content=f"🚨 Arresto registrato per {utente.mention}.", embed=emb)

@bot.tree.command(name="denuncia", description="Registra una denuncia penale")
async def denuncia(interaction: Interaction, cittadino: discord.Member, descrizione: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Solo Polizia.", ephemeral=True)
    
    data_attuale = datetime.datetime.now().strftime("%d/%m/%Y")
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, 0, %s)",
                (str(cittadino.id), str(interaction.user.id), f"[DENUNCIA] {descrizione}", data_attuale))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="📂 NUOVA DENUNCIA", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
    emb.add_field(name="Cittadino", value=cittadino.mention)
    emb.add_field(name="Descrizione", value=descrizione, inline=False)
    
    await invia_log(interaction, "canale_log_denunce", emb)
    await interaction.response.send_message(f"✅ Denuncia registrata per {cittadino.mention}.")

@bot.tree.command(name="multa", description="Emetti una sanzione amministrativa")
async def multa(interaction: Interaction, utente: discord.Member, ammontare: int, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Solo Polizia.", ephemeral=True)
    
    await interaction.response.defer()
    cfg = get_cfg(interaction.guild_id)
    id_m = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    data_attuale = datetime.datetime.now().strftime("%d/%m/%Y")

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO multe (id_multa, user_id, ammontare, id_azienda, motivo, data) VALUES (%s, %s, %s, %s, %s, %s)",
                (id_m, str(utente.id), ammontare, str(cfg["ruolo_polizia"]), motivo, data_attuale))
    conn.commit(); cur.close(); conn.close()

    emb = discord.Embed(title="🚨 MULTA EMESSA", color=discord.Color.red())
    emb.add_field(name="Soggetto", value=utente.mention)
    emb.add_field(name="Importo", value=f"{ammontare}$")
    emb.set_footer(text=f"ID Multa: {id_m}")

    await invia_log(interaction, "canale_log_multe", emb)
    await interaction.followup.send(f"✅ Multa notificata a {utente.mention}.", embed=emb)

@bot.tree.command(name="sequestra_mezzo", description="Metti sotto sequestro un veicolo")
async def sequestra_mezzo(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Accesso negato.", ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE veicoli SET sequestrato = TRUE WHERE targa = %s RETURNING modello, owner_id", (targa.upper(),))
    v = cur.fetchone()
    if not v:
        cur.close(); conn.close()
        return await interaction.response.send_message("❌ Targa non trovata.")
    
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="🚔 SEQUESTRO MEZZO", color=discord.Color.dark_red())
    emb.add_field(name="Veicolo", value=f"{v['modello']} ({targa.upper()})")
    emb.add_field(name="Proprietario", value=f"<@{v['owner_id']}>")

    await invia_log(interaction, "canale_log_sequestri", emb)
    await interaction.response.send_message(f"🚫 Veicolo **{v['modello']}** ({targa.upper()}) sequestrato.")

@bot.tree.command(name="registra_arma", description="Registra un'arma nel registro matricole")
async def registra_arma(interaction: Interaction, utente: discord.Member, modello: str, matricola: str, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ Solo Polizia.", ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO registro_armi (user_id, modello, matricola, motivo) VALUES (%s, %s, %s, %s)",
                    (str(utente.id), modello, matricola.upper(), motivo))
        conn.commit()
        await interaction.response.send_message(f"✅ Arma `{modello}` ({matricola.upper()}) registrata.")
    except:
        await interaction.response.send_message("❌ Errore: Matricola già esistente.")
    finally:
        cur.close(); conn.close()

@bot.tree.command(name="pagamulta", description="Saldare l'ultima multa pendente")
async def pagamulta(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM multe WHERE user_id = %s LIMIT 1", (str(interaction.user.id),))
    m = cur.fetchone()
    if not m: return await interaction.followup.send("✅ Non hai multe pendenti.")

    cur.execute("SELECT wallet FROM users WHERE user_id = %s", (str(interaction.user.id),))
    w = cur.fetchone()
    if not w or w['wallet'] < m['ammontare']: 
        return await interaction.followup.send(f"❌ Wallet insufficiente ({m['ammontare']}$).")

    # Transazione
    cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (m['ammontare'], str(interaction.user.id)))
    cur.execute("INSERT INTO depositi (role_id, money) VALUES (%s, %s) ON CONFLICT (role_id) DO UPDATE SET money = depositi.money + EXCLUDED.money", 
                (m['id_azienda'], m['ammontare']))
    cur.execute("DELETE FROM multe WHERE id_multa = %s", (m['id_multa'],))
    
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send("✅ Multa pagata correttamente.")

# --- AVVIO ---
bot.run(TOKEN)
