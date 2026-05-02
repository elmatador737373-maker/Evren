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

# --- CONFIGURAZIONE FLASK (Per mantenere il bot attivo su Render) ---
app = Flask('')

@app.route('/')
def home():
    return "Sistema CAD Polizia Online!"

def run():
    # Render usa solitamente la porta 8080 o quella definita dall'ambiente
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- CARICAMENTO SEGRETI ---
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- CONFIGURAZIONE MULTI-SERVER AGGIORNATA ---
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
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    except Exception as e:
        print(f"❌ Errore connessione DB: {e}")
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
def get_cfg(guild_id): return SERVER_CONFIG.get(guild_id)

def is_polizia(interaction: Interaction):
    cfg = get_cfg(interaction.guild_id)
    return cfg and any(role.id == cfg["ruolo_polizia"] for role in interaction.user.roles)

async def invia_log(interaction, tipo_log_key, embed):
    cfg = get_cfg(interaction.guild_id)
    if not cfg: return
    channel = interaction.guild.get_channel(cfg.get(tipo_log_key))
    if channel: await channel.send(embed=embed)

# --- COMANDI BASE ---

@bot.tree.command(name="arresto", description="Registra un arresto nel database")
async def arresto(interaction: Interaction, utente: discord.Member, tempo_minuti: int, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, %s, %s)",
                (str(utente.id), str(interaction.user.id), motivo, tempo_minuti, datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="⚖️ VERBALE DI ARRESTO", color=discord.Color.dark_blue()); emb.add_field(name="Soggetto", value=utente.mention); emb.add_field(name="Pena", value=f"{tempo_minuti}m")
    await invia_log(interaction, "canale_log_arresti", emb)
    await interaction.followup.send(f"🚨 Arresto registrato per {utente.mention}.")

@bot.tree.command(name="multa", description="Emetti sanzione amministrativa")
async def multa(interaction: Interaction, utente: discord.Member, ammontare: int, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    cfg = get_cfg(interaction.guild_id); id_m = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO multe (id_multa, user_id, ammontare, id_azienda, motivo, data) VALUES (%s, %s, %s, %s, %s, %s)",
                (id_m, str(utente.id), ammontare, str(cfg["ruolo_polizia"]), motivo, datetime.datetime.now().strftime("%d/%m/%Y")))
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="🚨 MULTA EMESSA", color=discord.Color.red()); emb.add_field(name="Soggetto", value=utente.mention); emb.add_field(name="Importo", value=f"{ammontare}$")
    await invia_log(interaction, "canale_log_multe", emb)
    await interaction.followup.send(f"✅ Multa emessa (ID: {id_m}).")

@bot.tree.command(name="denuncia", description="Registra una denuncia penale")
async def denuncia(interaction: Interaction, cittadino: discord.Member, descrizione: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO arresti (user_id, agente_id, motivo, tempo, data) VALUES (%s, %s, %s, 0, %s)",
                (str(cittadino.id), str(interaction.user.id), f"[DENUNCIA] {descrizione}", datetime.datetime.now().strftime("%d/%m/%Y")))
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="📂 DENUNCIA", color=discord.Color.orange()); emb.add_field(name="Soggetto", value=cittadino.mention); emb.add_field(name="Nota", value=descrizione)
    await invia_log(interaction, "canale_log_denunce", emb)
    await interaction.response.send_message(f"✅ Denuncia salvata.")

# --- 1. COMANDO: SEQUESTRA OGGETTO ---
@bot.tree.command(name="sequestra_oggetto", description="Sposta item da inventory a sequestri_oggetti")
async def sequestra_oggetto(interaction: Interaction, utente: discord.Member, nome_oggetto: str, quantita: int):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Controllo usando 'item_name' e 'quantity'
    cur.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (str(utente.id), nome_oggetto))
    res = cur.fetchone()
    
    if not res or res['quantity'] < quantita:
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Il cittadino non ha abbastanza `{nome_oggetto}`.")

    # Rimozione dall'inventario (inventory)
    cur.execute("UPDATE inventory SET quantity = quantity - %s WHERE user_id = %s AND item_name = %s", (quantita, str(utente.id), nome_oggetto))
    cur.execute("DELETE FROM inventory WHERE quantity <= 0")
    
    # Inserimento nella tabella sequestri dedicata
    cur.execute("""INSERT INTO sequestri_oggetti (guild_id, item_id, amount, agente_id, data) 
                   VALUES (%s, %s, %s, %s, %s)""", 
                (str(interaction.guild_id), nome_oggetto, quantita, str(interaction.user.id), datetime.datetime.now().strftime("%d/%m/%Y %H:%M")))
    
    conn.commit(); cur.close(); conn.close()
    
    emb = discord.Embed(title="📦 OGGETTO SEQUESTRATO", color=discord.Color.dark_orange())
    emb.add_field(name="Soggetto", value=utente.mention); emb.add_field(name="Item", value=f"{quantita}x {nome_oggetto}")
    
    await invia_log(interaction, "canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Sequestro di **{quantita}x {nome_oggetto}** a {utente.mention} completato.")

# --- 2. COMANDO: PRENDI DAL DEPOSITO ---
@bot.tree.command(name="prendi_sequestro", description="Preleva oggetti dal deposito sequestri e mettili nel tuo inventario")
async def prendi_sequestro(interaction: Interaction, nome_oggetto: str, quantita: int):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Verifica disponibilità nel deposito del server
    cur.execute("SELECT SUM(amount) as totale FROM sequestri_oggetti WHERE guild_id = %s AND item_id = %s", (str(interaction.guild_id), nome_oggetto))
    res = cur.fetchone()
    
    if not res or not res['totale'] or res['totale'] < quantita:
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Deposito insufficiente per `{nome_oggetto}`.")

    # Rimozione dalla tabella sequestri
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

    # Riconsegna all'agente (inventory) usando user_id, item_name, quantity
    cur.execute("""INSERT INTO inventory (user_id, item_name, quantity) VALUES (%s, %s, %s)
                   ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity""",
                (str(interaction.user.id), nome_oggetto, quantita))
    
    conn.commit(); cur.close(); conn.close()
    
    emb = discord.Embed(title="📤 RITIRO SEQUESTRO", color=discord.Color.blue())
    emb.add_field(name="Agente", value=interaction.user.mention); emb.add_field(name="Item", value=f"{quantita}x {nome_oggetto}")
    
    await invia_log(interaction, "canale_log_sequestri", emb)
    await interaction.followup.send(f"✅ Hai ritirato **{quantita}x {nome_oggetto}** dal deposito.")

# --- 3. COMANDO: VISUALIZZA DEPOSITO ---
@bot.tree.command(name="deposito_sequestri", description="Mostra tutti gli oggetti in deposito")
async def deposito_sequestri(interaction: Interaction):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""SELECT item_id, SUM(amount) as totale 
                   FROM sequestri_oggetti 
                   WHERE guild_id = %s 
                   GROUP BY item_id 
                   HAVING SUM(amount) > 0""", (str(interaction.guild_id),))
    items = cur.fetchall(); cur.close(); conn.close()

    if not items: return await interaction.followup.send("📦 Il deposito sequestri è attualmente vuoto.")
    
    emb = discord.Embed(title=f"📂 ARCHIVIO SEQUESTRI - {interaction.guild.name}", color=discord.Color.blue())
    desc = "\n".join([f"• **{i['item_id']}**: {i['totale']}" for i in items])
    emb.description = desc
    
    await interaction.followup.send(embed=emb)
@bot.tree.command(name="dissequestra_mezzo", description="Rimuove il sequestro da un veicolo tramite targa")
@app_commands.describe(targa="La targa del veicolo da dissequestrare")
async def dissequestra_mezzo(interaction: Interaction, targa: str):
    if not is_polizia(interaction): 
        return await interaction.response.send_message("❌ Non hai i permessi per dissequestrare veicoli.", ephemeral=True)
    
    await interaction.response.defer()
    
    conn = get_db_connection()
    if not conn: 
        return await interaction.followup.send("❌ Database non raggiungibile.")
    
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 1. Verifica se il veicolo esiste ed è effettivamente sequestrato
        cur.execute("SELECT modello, sequestrato FROM veicoli WHERE targa = %s", (targa.upper(),))
        veicolo = cur.fetchone()

        if not veicolo:
            return await interaction.followup.send(f"❌ Nessun veicolo trovato con targa `{targa.upper()}`.")
        
        if not veicolo['sequestrato']:
            return await interaction.followup.send(f"⚠️ Il veicolo con targa `{targa.upper()}` non risulta essere sotto sequestro.")

        # 2. Aggiorna lo stato nel database
        cur.execute("UPDATE veicoli SET sequestrato = FALSE WHERE targa = %s", (targa.upper(),))
        conn.commit()

        # LOG - Inviato nel canale log sequestri
        emb = discord.Embed(
            title="🔓 DISSEQUESTRO MEZZO", 
            color=discord.Color.green(), 
            timestamp=discord.utils.utcnow()
        )
        emb.add_field(name="Veicolo", value=veicolo['modello'], inline=True)
        emb.add_field(name="Targa", value=targa.upper(), inline=True)
        emb.add_field(name="Agente", value=interaction.user.mention, inline=False)
        emb.set_footer(text=f"ID Server: {interaction.guild_id}")

        await invia_log(interaction, "canale_log_sequestri", emb)
        await interaction.followup.send(f"✅ Il veicolo **{veicolo['modello']}** (Targa: `{targa.upper()}`) è stato dissequestrato con successo.")

    except Exception as e:
        print(f"Errore dissequestro: {e}")
        await interaction.followup.send("❌ Errore durante l'aggiornamento del database.")
    finally:
        cur.close(); conn.close()

@bot.tree.command(name="sequestra_mezzo", description="Sequestra un veicolo tramite targa")
async def sequestra_mezzo(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE veicoli SET sequestrato = TRUE WHERE targa = %s RETURNING modello", (targa.upper(),))
    v = cur.fetchone()
    if not v: return await interaction.response.send_message("❌ Targa inesistente.")
    conn.commit(); cur.close(); conn.close()
    emb = discord.Embed(title="🚔 SEQUESTRO MEZZO", color=discord.Color.dark_red()); emb.add_field(name="Targa", value=targa.upper())
    await invia_log(interaction, "canale_log_sequestri", emb)
    await interaction.response.send_message(f"🚫 Veicolo sequestrato.")

# --- COMANDI CITTADINI ---
# --- 1. COMANDO: RICERCA CITTADINO ---
@bot.tree.command(name="cerca_cittadino", description="Visualizza il profilo completo, le multe e i precedenti di un cittadino")
async def cerca_cittadino(interaction: Interaction, utente: discord.Member):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Recupera info utente e wallet
    cur.execute("SELECT wallet, bank FROM users WHERE user_id = %s", (str(utente.id),))
    info = cur.fetchone()
    
    # Recupera veicoli
    cur.execute("SELECT modello, targa, sequestrato FROM veicoli WHERE user_id = %s", (str(utente.id),))
    veicoli = cur.fetchall()
    
    # Recupera multe pendenti
    cur.execute("SELECT ammontare, motivo, data FROM multe WHERE user_id = %s", (str(utente.id),))
    multe = cur.fetchall()
    
    # Recupera precedenti penali (arresti)
    cur.execute("SELECT motivo, tempo, data FROM arresti WHERE user_id = %s", (str(utente.id),))
    precedenti = cur.fetchall()
    
    cur.close(); conn.close()

    emb = discord.Embed(title=f"👤 DATABASE CITTADINO: {utente.display_name}", color=discord.Color.blue())
    emb.set_thumbnail(url=utente.display_avatar.url)

    # Sezione Veicoli
    val_veicoli = "\n".join([f"• {v['modello']} (`{v['targa']}`) {'🛑' if v['sequestrato'] else '✅'}" for v in veicoli]) if veicoli else "Nessun veicolo"
    emb.add_field(name="🚗 Veicoli", value=val_veicoli, inline=False)

    # Sezione Multe
    val_multe = "\n".join([f"• {m['ammontare']}$ - {m['motivo']} ({m['data']})" for m in multe]) if multe else "Nessuna multa pendente"
    emb.add_field(name="📜 Multe Pendenti", value=val_multe, inline=False)

    # Sezione Precedenti
    val_precedenti = "\n".join([f"• {p['data']} - {p['motivo']} ({p['tempo']} min)" for p in precedenti]) if precedenti else "Cittadino incensurato"
    emb.add_field(name="⚖️ Fedina Penale", value=val_precedenti, inline=False)

    await interaction.followup.send(embed=emb)

# --- 2. COMANDO: RICERCA TARGA ---
@bot.tree.command(name="cerca_targa", description="Risale al proprietario di un veicolo tramite la targa")
async def cerca_targa(interaction: Interaction, targa: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    await interaction.response.defer()
    
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Cerca il veicolo e il proprietario
    cur.execute("SELECT user_id, modello, sequestrato FROM veicoli WHERE targa = %s", (targa.upper(),))
    mezzo = cur.fetchone()
    
    if not mezzo:
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Nessun veicolo trovato con targa `{targa.upper()}`.")

    # Recupera il nome del proprietario da Discord
    proprietario = await bot.fetch_user(int(mezzo['user_id']))
    nome_proprietario = proprietario.mention if proprietario else "Sconosciuto"
    
    cur.close(); conn.close()

    emb = discord.Embed(title=f"🔎 RISULTATO RICERCA TARGA: {targa.upper()}", color=discord.Color.dark_grey())
    emb.add_field(name="Modello", value=mezzo['modello'], inline=True)
    emb.add_field(name="Stato", value="🛑 SEQUESTRATO" if mezzo['sequestrato'] else "✅ REGOLARE", inline=True)
    emb.add_field(name="Proprietario", value=nome_proprietario, inline=False)
    
    await interaction.followup.send(embed=emb)

@bot.tree.command(name="pagamulta", description="Paga la tua multa più vecchia")
async def pagamulta(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM multe WHERE user_id = %s LIMIT 1", (str(interaction.user.id),))
    m = cur.fetchone()
    if not m: return await interaction.followup.send("✅ Nessuna multa pendente.")
    cur.execute("SELECT wallet FROM users WHERE user_id = %s", (str(interaction.user.id),))
    u = cur.fetchone()
    if not u or u['wallet'] < m['ammontare']: return await interaction.followup.send("❌ Contanti insufficienti.")
    cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (m['ammontare'], str(interaction.user.id)))
    cur.execute("INSERT INTO depositi (role_id, money) VALUES (%s, %s) ON CONFLICT (role_id) DO UPDATE SET money = depositi.money + EXCLUDED.money", (m['id_azienda'], m['ammontare']))
    cur.execute("DELETE FROM multe WHERE id_multa = %s", (m['id_multa'],))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"✅ Multa di {m['ammontare']}$ pagata.")

# --- REGISTRO ARMI ---
@bot.tree.command(name="registra_arma", description="Registra un'arma nel database matricole")
async def registra_arma(interaction: Interaction, utente: discord.Member, modello: str, matricola: str, motivo: str):
    if not is_polizia(interaction): return await interaction.response.send_message("❌ No Permessi.", ephemeral=True)
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO registro_armi (user_id, modello, matricola, motivo) VALUES (%s, %s, %s, %s)",
                    (str(utente.id), modello, matricola.upper(), motivo))
        conn.commit()
        await interaction.response.send_message(f"✅ Arma {matricola.upper()} registrata.")
    except:
        await interaction.response.send_message("❌ Errore: Matricola già presente.")
    finally:
        cur.close(); conn.close()

# --- AVVIO ---
if __name__ == "__main__":
    keep_alive() # Avvia il server Flask per Render
    bot.run(TOKEN)
