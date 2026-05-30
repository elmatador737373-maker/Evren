import discord
from discord import app_commands, Interaction
from discord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import os
import threading
import asyncio
from flask import Flask
import datetime 
import string
import time
from discord.ui import View, Button
from discord import app_commands

# ================= CONFIGURAZIONE =================
TOKEN = os.environ.get("TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
RUOLO_STAFF_ID = 1253460150141059198

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= DATABASE SETUP =================

def get_db_connection():
    try:
        url = DATABASE_URL.replace("postgres://", "postgresql://")
        conn = psycopg2.connect(url, sslmode='require', connect_timeout=10)
        return conn
    except Exception as e:
        print(f"❌ Errore connessione DB: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: 
        return
    cur = conn.cursor()

    # 1. Creazione Tabelle Base (Usa sempre IF NOT EXISTS)
    cur.execute("CREATE TABLE IF NOT EXISTS items (name TEXT PRIMARY KEY, description TEXT, price INTEGER, role_required TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS inventory (user_id TEXT, item_name TEXT, quantity INTEGER, PRIMARY KEY (user_id, item_name))")
    cur.execute("CREATE TABLE IF NOT EXISTS depositi (role_id TEXT PRIMARY KEY, money INTEGER DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS depositi_items (role_id TEXT, item_name TEXT, quantity INTEGER, PRIMARY KEY (role_id, item_name))")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fatture (
            id_fattura TEXT PRIMARY KEY,
            id_cliente TEXT,
            id_azienda TEXT,
            descrizione TEXT,
            prezzo INTEGER,
            data TEXT,
            stato TEXT DEFAULT 'Pendente'
        )
    """)

    # 2. Aggiornamento tabelle esistenti (ALTER TABLE)
    # Usiamo blocchi try/except separati per ogni colonna così se una esiste già non blocca l'altra
    
    # Aggiunta ore_lavorate a users
    try:
        cur.execute("ALTER TABLE users ADD COLUMN ore_lavorate REAL DEFAULT 0")
        conn.commit()
    except Exception:
        conn.rollback() # Ignora se la colonna esiste già

    # Aggiunta ruolo a turni
    try:
        cur.execute("ALTER TABLE turni ADD COLUMN ruolo TEXT")
        conn.commit()
    except Exception:
        conn.rollback() # Ignora se la colonna esiste già

def inizializza_db_fatture():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Crea la tabella se non esiste con i nomi delle colonne corretti
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fatture (
                id_fattura TEXT PRIMARY KEY,
                id_cliente TEXT NOT NULL,
                id_azienda TEXT NOT NULL,
                descrizione TEXT,
                prezzo BIGINT,
                data TEXT,
                stato TEXT DEFAULT 'Pendente'
            );
        """)
        
        # Questo comando aggiunge la colonna 'stato' se la tabella esiste già ma è vecchia
        cur.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name='fatture' AND column_name='stato') THEN 
                    ALTER TABLE fatture ADD COLUMN stato TEXT DEFAULT 'Pendente';
                END IF;
            END $$;
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database Fatture sincronizzato con successo!")
    except Exception as e:
        print(f"❌ Errore inizializzazione tabella: {e}")

# RICORDA: Nel tuo evento @bot.event async def on_ready():
# aggiungi una riga con: inizializza_db_fatture()


    # Chiudiamo tutto correttamente
    cur.close()
    conn.close()
    print("✅ Database inizializzato correttamente!")

# Chiama la funzione
init_db()

# ================= HELPER FUNCTIONS =================

def get_user_data(user_id):
    conn = get_db_connection()
    if not conn: return {"wallet": 0, "bank": 0}
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE user_id = %s", (str(user_id),))
    user = cur.fetchone()
    if not user:
        cur.execute("INSERT INTO users (user_id, wallet, bank) VALUES (%s, 1500, 0) RETURNING *", (str(user_id),))
        user = cur.fetchone()
        conn.commit()
    cur.close(); conn.close()
    return user

def is_staff(interaction: discord.Interaction):
    return any(role.id == RUOLO_STAFF_ID for role in interaction.user.roles)

async def get_miei_ruoli_fazione(interaction: Interaction):
    conn = get_db_connection()
    if not conn: return []
    cur = conn.cursor()
    cur.execute("SELECT role_id FROM depositi")
    registrati = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return [r for r in interaction.user.roles if str(r.id) in registrati]

async def cerca_item_smart(interaction: Interaction, nome_input: str, modo="items", target_user_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if modo == "items":
        cur.execute("SELECT name FROM items WHERE name ILIKE %s", (f"%{nome_input}%",))
    elif modo == "inventory":
        uid = str(target_user_id) if target_user_id else str(interaction.user.id)
        cur.execute("SELECT item_name FROM inventory WHERE user_id = %s AND item_name ILIKE %s", (uid, f"%{nome_input}%"))
    else:
        role_id = modo.replace("fazione_", "")
        cur.execute("SELECT item_name FROM depositi_items WHERE role_id = %s AND item_name ILIKE %s", (role_id, f"%{nome_input}%"))
    
    risultati = list(set([r[0] for r in cur.fetchall()]))
    cur.close(); conn.close()
    
    if not risultati:
        # Usiamo un messaggio normale (non ephemeral forzato se il comando base non lo è, 
        # o lo lasciamo ephemeral se preferisci, ma followup.send si adatta al defer del comando principale)
        await interaction.followup.send(f"❌ Nessun oggetto trovato per '{nome_input}'.")
        return None
    if len(risultati) == 1: 
        return risultati[0]

    view = discord.ui.View()
    select = discord.ui.Select(options=[discord.SelectOption(label=n) for n in risultati[:25]])
    
    async def callback(i: Interaction):
        # 1. Deferiamo l'interazione del Select per dare tempo al comando principale di finire senza timeout
        await i.response.defer()
        
        # 2. Disabilitiamo il menu a tendina per evitare doppi click
        for item in view.children: 
            item.disabled = True
            
        # 3. Aggiorniamo il messaggio del Select usando edit_original_response
        await i.edit_original_response(view=view)
        
        # 4. Salviamo il valore e sblocchiamo la view
        view.value = select.values[0]
        view.stop()
        
    select.callback = callback
    view.add_item(select); view.value = None
    
    # Inviamo il menu a tendina
    msg = await interaction.followup.send("🤔 Più risultati, seleziona quello corretto:", view=view, ephemeral=True)
    
    # Attendiamo che l'utente clicchi un'opzione
    await view.wait()
    
    # Se il tempo scade o chiudono la view senza selezionare nulla
    if view.value is None:
        return None
        
    return view.value

@bot.tree.command(name="say", description="[ADMIN] Invia un messaggio tramite il bot")
@app_commands.describe(
    messaggio="Il testo da far dire al bot",
    canale="Il canale dove inviare il messaggio (opzionale)",
    titolo="Aggiungi un titolo per creare un Embed (opzionale)",
    colore="Colore dell'Embed in HEX (es: #ff0000) (opzionale)"
)
async def say(
    interaction: discord.Interaction, 
    messaggio: str, 
    canale: discord.TextChannel = None, 
    titolo: str = None,
    colore: str = None
):
    # 1. Controllo Permessi Admin
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Non hai i permessi per usare questo comando.", ephemeral=True)

    # 2. Definizione del canale di destinazione
    target_channel = canale if canale else interaction.channel

    # 3. Gestione del colore (Default: Blu se non specificato)
    embed_color = discord.Color.blue()
    if colore:
        try:
            # Converte il codice HEX in colore discord
            embed_color = discord.Color.from_str(colore)
        except ValueError:
            return await interaction.response.send_message("❌ Formato colore HEX non valido! Usa ad esempio `#ff0000`.", ephemeral=True)

    # 4. Creazione del messaggio (Embed o Testo Semplice)
    if titolo:
        # Se c'è un titolo, creiamo un Embed
        embed = discord.Embed(
            title=titolo,
            description=messaggio.replace("\\n", "\n"), # Permette di usare \n per andare a capo
            color=embed_color
        )
        await target_channel.send(embed=embed)
    else:
        # Altrimenti invia testo semplice
        await target_channel.send(messaggio.replace("\\n", "\n"))

    # 5. Risposta all'admin (visibile solo a lui)
    await interaction.response.send_message(f"✅ Messaggio inviato correttamente in {target_channel.mention}!", ephemeral=True)
import discord
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import io
import requests
from datetime import datetime

# --- HELPER: CALCOLO DATE ---
# Calcola l'emissione (oggi) e la scadenza (compleanno tra 10 anni)
def calcola_date_id(data_nascita_str):
    oggi = datetime.now()
    data_emissione = oggi.strftime("%d/%m/%Y")
    
    try:
        # Prende GG/MM dalla nascita (primi 5 caratteri)
        giorno_mese = data_nascita_str[:5] 
        anno_scadenza = oggi.year + 10
        data_scadenza = f"{giorno_mese}/{anno_scadenza}"
    except:
        data_scadenza = "DATA ERRATA"
    
    return data_emissione, data_scadenza
    
from menu_bellevue import MENU_DATI

# --- COMANDO ADMIN PER IL SYNC (!) ---
# Questo serve per forzare Discord a vedere i nuovi comandi /
@bot.command(name="syncbot")
@commands.has_permissions(administrator=True)
async def sync(ctx):
    try:
        print("Tentativo di sincronizzazione dei comandi...")
        synced = await bot.tree.sync()
        print(f"Sincronizzati {len(synced)} comandi slash.")
        await ctx.send(f"✅ Sincronizzati {len(synced)} comandi slash globalmente!")
    except Exception as e:
        print(f"Errore durante il sync: {e}")
        await ctx.send(f"❌ Errore durante il sync: {e}")


from discord import app_commands


from datetime import datetime  # <--- ASSICURATI CHE CI SIA QUESTO
import discord
from discord import app_commands
from psycopg2.extras import RealDictCursor
# --- FUNZIONE AUTOCOMPLETE PER LE TARGHE (SOLO VEICOLI PROPRI) ---
import discord
from discord import app_commands
from datetime import datetime
# Assicurati di aver importato RealDictCursor se usi psycopg2
# from psycopg2.extras import RealDictCursor 

# --- AUTOCOMPLETE DELLA TARGA ---
async def targa_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        # Usiamo il context manager (with) per essere sicuri che il cursore si chiuda
        with conn.cursor() as cur:
            # Filtra per targa SIMILE e che appartiene all'owner_id di chi usa il comando
            cur.execute(
                "SELECT targa FROM public.veicoli WHERE owner_id = %s AND targa ILIKE %s LIMIT 25", 
                (str(interaction.user.id), f"%{current}%")
            )
            rows = cur.fetchall()
        conn.close()
        
        # Ritorna la lista delle sole targhe dell'utente
        return [app_commands.Choice(name=row[0].upper(), value=row[0]) for row in rows]
    except Exception as e:
        print(f"⚠️ Errore nell'autocomplete privato della targa: {e}")
        return []

# --- COMANDO LIBRETTO ---
@bot.tree.command(name="libretto", description="Mostra il libretto di un tuo veicolo")
@app_commands.describe(targa="Inserisci o seleziona la targa del tuo veicolo")
@app_commands.autocomplete(targa=targa_autocomplete)
async def libretto(interaction: discord.Interaction, targa: str):
    # Deferiamo subito per evitare il timeout di 3 secondi di Discord
    await interaction.response.defer()
    
    targa_pulita = targa.upper().strip()
    
    try:
        # Recupero dei dati dal database
        with interaction.client.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM public.veicoli WHERE targa = %s", (targa_pulita,))
            row = cur.fetchone()

        if not row:
            return await interaction.followup.send(f"❌ Nessun veicolo trovato con targa: `{targa_pulita}`")

        # Controllo di sicurezza: il veicolo deve appartenere a chi esegue il comando
        if str(row['owner_id']) != str(interaction.user.id):
            return await interaction.followup.send("❌ Questo veicolo non ti appartiene.")

        # --- VERIFICA DINAMICA STATO ASSICURAZIONE/REVISIONE ---
        oggi = datetime.now().date()
        scad_ass = row['data_scadenza_assicurazione']  # Tipo 'date' nel DB
        scad_rev = row['data_scadenza_revisione']      # Tipo 'date' nel DB

        if scad_ass:
            if scad_ass > oggi:
                stato_assicurazione = f"🟢 ATTIVA (Scadenza: {scad_ass.strftime('%d/%m/%Y')})"
            else:
                stato_assicurazione = f"🔴 SCADUTA ({scad_ass.strftime('%d/%m/%Y')})"
        else:
            stato_assicurazione = "🔴 NON ASSICURATO"

        if scad_rev:
            if scad_rev > oggi:
                stato_revisione = f"🟢 VALIDA (Scadenza: {scad_rev.strftime('%d/%m/%Y')})"
            else:
                stato_revisione = f"🔴 SCADUTA ({scad_rev.strftime('%d/%m/%Y')})"
        else:
            stato_revisione = "🔴 NON REVISIONATO"

        # --- LETTURA MODIFICHE INSTALLATE ---
        modifiche_installate = row['modifiche'] if row.get('modifiche') and row['modifiche'].strip() else "Nessuna modifica installata"

        # Costruzione dell'Embed grafico
        colore = discord.Color.red() if row['sequestrato'] else discord.Color.green()
        embed = discord.Embed(
            title=f"🚗 Libretto Veicolo: {targa_pulita}",
            color=colore,
            timestamp=datetime.now()
        )

        embed.add_field(name="📦 Modello", value=row['modello'] if row['modello'] else "N/D", inline=True)
        embed.add_field(name="👤 Intestatario", value=f"<@{row['owner_id']}>", inline=True)
        
        # Gestione della data di vendita (Trattata come testo/stringa come da DB)
        embed.add_field(name="📅 Data Vendita", value=row['data_vendita'] if row['data_vendita'] else "N/D", inline=True)
        
        # Stato amministrativo e scadenze stradali
        stato_legale = "❌ SEQUESTRATO / FERMO AMMINISTRATIVO" if row['sequestrato'] else "✅ REGOLARE"
        embed.add_field(name="🚦 Stato Amministrativo", value=stato_legale, inline=False)
        embed.add_field(name="🛡️ Assicurazione", value=stato_assicurazione, inline=True)
        embed.add_field(name="🔧 Revisione Statale", value=stato_revisione, inline=True)
        
        embed.add_field(name="⚙️ Modifiche Apportate", value=f"```\n{modifiche_installate}\n```", inline=False)


        embed.set_footer(text="Motorizzazione Civile - Dipartimento Trasporti")

        # Invio finale del messaggio alla chat di Discord
        await interaction.followup.send(
            content=f"**{interaction.user.display_name}** mostra il libretto di circolazione:",
            embed=embed
        )
        
    except Exception as e:
        print(f"--- ERRORE CRITICO NEL COMANDO LIBRETTO ---")
        import traceback
        traceback.print_exc() 
        print(f"--------------------------------------------")
        
        try:
            await interaction.followup.send("❌ Si è verificato un errore tecnico nel recupero del libretto.")
        except Exception:
            pass

import discord
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import io
import requests
import datetime
@app_commands.command(name="bonifico", description="Invia denaro dal tuo conto bancario a un altro cittadino")
@app_commands.describe(destinatario="Il cittadino che riceve i soldi", ammontare="La cifra da inviare")
async def bonifico(interaction: discord.Interaction, destinatario: discord.Member, ammontare: int):
    # Validazione base
    if ammontare <= 0:
        return await interaction.response.send_message("❌ L'importo deve essere superiore a 0€.", ephemeral=True)
    
    if destinatario.id == interaction.user.id:
        return await interaction.response.send_message("❌ Non puoi inviare denaro a te stesso.", ephemeral=True)

    if destinatario.bot:
        return await interaction.response.send_message("❌ Non puoi inviare denaro ai bot.", ephemeral=True)

    user_id = str(interaction.user.id)
    dest_id = str(destinatario.id)

    # Inviamo un "defer" così Discord sa che stiamo lavorando ed evitiamo il timeout di 3 secondi
    await interaction.response.defer(ephemeral=False)

    try:
        # Utilizziamo i context manager 'with' per una gestione sicura della connessione
        with psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as cur:
                
                # 1. Recupero fondi con FOR UPDATE per evitare exploit di clonazione (Race Condition)
                cur.execute("SELECT bank FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                result = cur.fetchone()

                # Se l'utente non esiste nel DB o ha fondi insufficienti
                if not result or result['bank'] < ammontare:
                    saldo_attuale = result['bank'] if result else 0
                    return await interaction.followup.send(
                        f"❌ Fondi insufficienti in banca. Saldo attuale: **{saldo_attuale}€**", 
                        ephemeral=True
                    )

                # 2. Transazione
                # Sottraiamo dal mittente
                cur.execute("UPDATE users SET bank = bank - %s WHERE user_id = %s", (ammontare, user_id))

                # Aggiungiamo al destinatario (con creazione record se non esiste)
                cur.execute("""
                    INSERT INTO users (user_id, bank, wallet) VALUES (%s, %s, 0)
                    ON CONFLICT (user_id) DO UPDATE SET bank = users.bank + EXCLUDED.bank
                """, (dest_id, ammontare))

                # Il commit viene fatto in automatico all'uscita del blochetti 'with' se non ci sono errori,
                # ma farlo esplicitamente prima dell'output visivo è una buona pratica.
                conn.commit()

        # 3. Output grafico (Utilizziamo followup perché abbiamo usato defer)
        embed = discord.Embed(
            title="🏦 Bonifico Bancario Confermato",
            description=(
                f"**Mittente:** {interaction.user.mention}\n"
                f"**Destinatario:** {destinatario.mention}\n"
                f"**Importo:** {ammontare}€\n\n"
                "I fondi sono stati trasferiti con successo tra i conti bancari."
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Evren City Banking System")
        
        await interaction.followup.send(embed=embed)

        # Notifica DM al destinatario
        try:
            await destinatario.send(f"🏦 Hai ricevuto un bonifico bancario di **{ammontare}€** da {interaction.user.name}!")
        except discord.Forbidden:
            pass  # L'utente ha i DM disabilitati, ignoriamo l'errore in silenzio

    except Exception as e:
        print(f"Errore critico bonifico: {e}")
        # Se interaction non è ancora stata risposta a causa del defer fallito (raro)
        try:
            await interaction.followup.send("❌ Errore tecnico durante il trasferimento bancario.", ephemeral=True)
        except:
            pass


# --- CONFIGURAZIONE ---
ID_CANALE_ARCHIVIO = 1510190622638739567 

# --- FUNZIONE CALCOLO DATE (Indispensabile per far funzionare il comando) ---
def calcola_date_id(data_nascita):
    """Calcola data emissione (oggi) e scadenza (fra 10 anni)"""
    try:
        oggi = datetime.date.today()
        emissione = oggi.strftime("%d/%m/%Y")
        # Scadenza standard: +10 anni
        scadenza = (oggi.replace(year=oggi.year + 10)).strftime("%d/%m/%Y")
        return emissione, scadenza
    except Exception as e:
        print(f"[LOG ERROR] Errore nel calcolo date: {e}")
        # Ritorno date di emergenza per non bloccare il comando
        return "07/05/2026", "07/05/2036"
        
        
@bot.tree.command(name="crea_documento", description="Registra la tua carta d'identità messicana")
@app_commands.choices(sesso=[
    app_commands.Choice(name="Maschio", value="Maschio"),
    app_commands.Choice(name="Femmina", value="Femmina")
])
async def crea_documento(
    interaction: discord.Interaction, 
    nome: str, 
    cognome: str, 
    data_nascita: str, 
    luogo_nascita: str,
    nazionalita: str,
    sesso: app_commands.Choice[str],
    foto: discord.Attachment
):
    # PRIMA riga: segnaliamo a Discord che stiamo lavorando
    await interaction.response.defer(ephemeral=True)
    
    try:
        if not foto.content_type or not foto.content_type.startswith("image/"):
            return await interaction.followup.send("❌ Devi allegare un'immagine valida!", ephemeral=True)

        # 1. ARCHIVIAZIONE FOTO
        message_id_salvato = None
        foto_url_permanente = foto.url

        try:
            canale_archivio = bot.get_channel(ID_CANALE_ARCHIVIO) or await bot.fetch_channel(ID_CANALE_ARCHIVIO)
            file_da_inviare = await foto.to_file()
            msg = await canale_archivio.send(
                content=f"📌 Archivio Foto ID: **{nome} {cognome}** (Utente: {interaction.user.id})", 
                file=file_da_inviare
            )
            foto_url_permanente = msg.attachments[0].url
            message_id_salvato = str(msg.id)
        except Exception as e:
            print(f"[LOG ERROR] Fallimento archivio foto: {e}")

        # 2. CALCOLO DATE
        emissione, scadenza = calcola_date_id(data_nascita)

        # 3. SALVATAGGIO DATABASE
        conn = get_db_connection()
        cur = conn.cursor()
        
        valori_documento = (
            str(interaction.user.id), nome, cognome, data_nascita, luogo_nascita, 
            sesso.value, nazionalita, emissione, scadenza, 
            foto_url_permanente, "CARTA DI IDENTITÀ", message_id_salvato
        )

        cur.execute("""
            INSERT INTO documenti (
                user_id, nome, cognome, data_nascita, luogo_nascita, 
                sesso, nazionalita, data_emissione, data_scadenza, 
                foto_url, tipo_documento, message_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                nome=EXCLUDED.nome, cognome=EXCLUDED.cognome, data_nascita=EXCLUDED.data_nascita,
                luogo_nascita=EXCLUDED.luogo_nascita, sesso=EXCLUDED.sesso, nazionalita=EXCLUDED.nazionalita,
                data_emissione=EXCLUDED.data_emissione, data_scadenza=EXCLUDED.data_scadenza,
                foto_url=EXCLUDED.foto_url, tipo_documento=EXCLUDED.tipo_documento, 
                message_id=EXCLUDED.message_id
        """, valori_documento)
        
        conn.commit()
        cur.close(); conn.close()

        # Gestione Ruoli (con controllo errori)
        try:
            member = interaction.guild.get_member(interaction.user.id)
            if member:
                await member.add_roles(discord.Object(id=1278673173172453418))
                await member.remove_roles(discord.Object(id=1278680093044113469))
        except: pass

        await interaction.followup.send("✅ Documento registrato con successo!", ephemeral=True)
        
    except Exception as e:
        print(f"[LOG ERROR] Errore generale: {e}")
        # Usiamo sempre followup dopo il defer
        await interaction.followup.send(f"❌ Errore durante l'operazione: {e}", ephemeral=True)

@bot.tree.command(name="mostra_documento", description="Mostra il tuo documento in formato testo")
async def mostra_documento(interaction: discord.Interaction, cittadino: discord.Member = None):
    # Defer immediato (non ephemeral così gli altri vedono il documento)
    await interaction.response.defer()
    
    target = cittadino if cittadino else interaction.user

    try:
        conn = get_db_connection()
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM documenti WHERE user_id = %s", (str(target.id),))
        doc = cur.fetchone()
        cur.close(); conn.close()

        if not doc:
            return await interaction.followup.send(f"❌ {target.display_name} non ha un documento registrato.")

        # Creazione dell'Embed di Discord
        embed = discord.Embed(
            title=f"🪪 DOCUMENTO DI IDENTITÀ ({doc['tipo_documento'].upper()})",
            color=discord.Color.blue()
        )
        
        # Organizzazione dei dati in colonne/campi puliti
        embed.add_field(name="👤 Cognome", value=doc['cognome'].upper(), inline=True)
        embed.add_field(name="✍️ Nome", value=doc['nome'].upper(), inline=True)
        embed.add_field(name="🧬 Sesso", value=str(doc['sesso']).upper(), inline=True)
        
        embed.add_field(name="📅 Data di Nascita", value=str(doc['data_nascita']), inline=True)
        embed.add_field(name="📍 Luogo di Nascita", value=str(doc['luogo_nascita']).upper(), inline=True)
        embed.add_field(name="🌍 Nazionalità", value=str(doc['nazionalita']).upper(), inline=True)
        
        embed.add_field(name="📆 Data Emissione", value=str(doc['data_emissione']), inline=True)
        embed.add_field(name="⏳ Data Scadenza", value=str(doc['data_scadenza']), inline=True)
        embed.add_field(name="🏢 Stato", value="MESSICO", inline=True)

        # GESTIONE FOTO (Viene impostata come Thumbnail laterale dell'embed)
        foto_url = doc['foto_url']
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        try:
            # Controllo validità URL (mantenendo la tua logica di fallback sul canale archivio)
            foto_res = requests.get(foto_url, headers=headers, timeout=5)
            
            if foto_res.status_code != 200 and doc.get('message_id'):
                canale_archivio = bot.get_channel(ID_CANALE_ARCHIVIO) or await bot.fetch_channel(ID_CANALE_ARCHIVIO)
                msg = await canale_archivio.fetch_message(int(doc['message_id']))
                foto_url = msg.attachments[0].url
            
            # Imposta la foto del cittadino nell'embed
            embed.set_thumbnail(url=foto_url)
            
        except Exception as e:
            print(f"[DEBUG] Errore recupero foto utente per Embed: {e}")
            # Fallback: se la foto del database fallisce, usa l'avatar di Discord dell'utente
            embed.set_thumbnail(url=target.display_avatar.url)

        # Footer e dettagli estetici
        embed.set_footer(text=f"ID Utente: {target.id}")

        # Invio Finale dell'Embed
        await interaction.followup.send(
            content=f"***{interaction.user.display_name}** mostra il documento di {target.mention}*", 
            embed=embed
        )

    except Exception as e:
        print(f"[LOG ERROR] Errore generale mostra_documento: {e}")
        try:
            await interaction.followup.send(f"❌ Errore imprevisto nella generazione dell'embed: {e}")
        except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    # ID del canale vocale da monitorare
    VC_TARGET_ID = 1252225096827928607
    # ID del canale testuale dove inviare la notifica
    LOG_CHANNEL_ID = 1411290694257213440
    # ID del ruolo da taggare
    ROLE_ID = 1253634976243646527

    # Controllo: l'utente è entrato nel VC target?
    # (before.channel != after.channel assicura che non si attivi se muta solo il microfono)
    if after.channel and after.channel.id == VC_TARGET_ID and before.channel != after.channel:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if channel:
            # Invio del messaggio con i tag richiesti
            await channel.send(f"<@&{ROLE_ID}> è entrato {member.mention} in <#{VC_TARGET_ID}>")

# --- COMANDO SETUP (ADMIN) ---
@bot.tree.command(name="setup_polizia", description="[ADMIN] Imposta il ruolo che può gestire i tesserini")
async def setup_polizia(interaction: discord.Interaction, ruolo: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo un Amministratore può farlo.", ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO config_polizia (guild_id, ruolo_creazione) VALUES (%s, %s)
        ON CONFLICT (guild_id) DO UPDATE SET ruolo_creazione = EXCLUDED.ruolo_creazione
    """, (str(interaction.guild.id), str(ruolo.id)))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Ruolo autorizzato impostato su: {ruolo.mention}", ephemeral=True)

import asyncio
import datetime

# --- VIEW PER LA CONFERMA ---
class ConfirmDMView(discord.ui.View):
    def __init__(self, interaction, members, messaggio, delay, immagine_url):
        super().__init__(timeout=60) # Scade dopo 60 secondi
        self.interaction = interaction
        self.members = members
        self.messaggio = messaggio
        self.delay = delay
        self.immagine_url = immagine_url
        self.value = None

    @discord.ui.button(label="Conferma ed Invia", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("❌ Solo chi ha lanciato il comando può confermare.", ephemeral=True)
        self.value = True
        self.stop()
        await interaction.response.edit_message(content="🚀 Invio confermato! Sto partendo...", view=None, embed=None)

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.edit_message(content="❌ Operazione annullata. Nessun DM inviato.", view=None, embed=None)
# Classe per il menu di selezione dei permessi
class CategoryPermsSelect(discord.ui.Select):
    def __init__(self, role: discord.Role, category: discord.CategoryChannel):
        self.role = role
        self.category = category
        
        # Lista dei permessi principali tra cui scegliere
        options = [
            discord.SelectOption(label="Visualizzare Canali", value="view_channel", description="Permette di vedere la categoria"),
            discord.SelectOption(label="Inviare Messaggi", value="send_messages", description="Permette di scrivere nei canali testo"),
            discord.SelectOption(label="Gestire Canali", value="manage_channels", description="Permette di modificare i canali"),
            discord.SelectOption(label="Collegarsi", value="connect", description="Permette di entrare nei canali vocali"),
            discord.SelectOption(label="Parlare", value="speak", description="Permette di parlare nei canali vocali"),
            discord.SelectOption(label="Allegare File", value="attach_files", description="Permette di inviare immagini/file"),
            discord.SelectOption(label="Aggiungere Reazioni", value="add_reactions", description="Permette di aggiungere emoji"),
            discord.SelectOption(label="Menzionare Everyone", value="mention_everyone", description="Permette di usare tag globali")
        ]

        super().__init__(
            placeholder="Scegli i permessi (min 1, max 5)...",
            min_values=1,
            max_values=5,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Creiamo il dizionario dei permessi (True per quelli selezionati)
        overwrites_dict = {perm: True for perm in self.values}
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Applica i permessi alla categoria
            await self.category.set_permissions(self.role, **overwrites_dict)
            
            # Sincronizza i canali interni alla categoria
            for channel in self.category.channels:
                await channel.set_permissions(self.role, **overwrites_dict)
            
            await interaction.followup.send(
                f"✅ Configurazione completata!\n**Ruolo:** {self.role.mention}\n**Categoria:** {self.category.name}\n**Permessi:** `{', '.join(self.values)}`",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ Non ho i permessi necessari per modificare questo ruolo o categoria.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Errore: {e}", ephemeral=True)

# Classe View che contiene il menu
class CategoryPermsView(discord.ui.View):
    def __init__(self, role: discord.Role, category: discord.CategoryChannel):
        super().__init__(timeout=60)
        self.add_item(CategoryPermsSelect(role, category))

# COMANDO SLASH
@bot.tree.command(name="set_category_perms", description="Configura i permessi di una categoria per un ruolo (Max 5)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(categoria_id="Inserisci l'ID della categoria", ruolo="Seleziona il ruolo")
async def set_category_perms(interaction: discord.Interaction, categoria_id: str, ruolo: discord.Role):
    # Verifica validità ID categoria
    try:
        cat_id = int(categoria_id)
        category = interaction.guild.get_channel(cat_id)
    except ValueError:
        return await interaction.response.send_message("L'ID fornito non è un numero valido.", ephemeral=True)

    if not category or not isinstance(category, discord.CategoryChannel):
        return await interaction.response.send_message("ID non trovato o non corrisponde a una Categoria.", ephemeral=True)

    # Invia la View con il menu di selezione
    view = CategoryPermsView(ruolo, category)
    await interaction.response.send_message(
        f"Seleziona quali permessi concedere a {ruolo.mention} nella categoria **{category.name}**:",
        view=view,
        ephemeral=True
    )

# --- COMANDO PRINCIPALE ---
@bot.tree.command(name="dm_all", description="[ADMIN] Invia DM di massa con conferma e stima")
@app_commands.describe(
    messaggio="Il testo dell'annuncio",
    delay="Secondi di attesa (consigliato 2.0+)",
    ruolo="Invia solo a chi ha questo ruolo (opzionale)",
    immagine_url="Link opzionale a un'immagine"
)
async def dm_all_safe(
    interaction: discord.Interaction, 
    messaggio: str, 
    delay: float = 2.0, 
    ruolo: discord.Role = None, 
    immagine_url: str = None
):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Non hai i permessi per questa operazione.", ephemeral=True)

    if delay < 1.0:
        return await interaction.response.send_message("⚠️ Il delay minimo è 1.0.", ephemeral=True)

    await interaction.response.defer(ephemeral=False)

    # Selezione Membri
    if ruolo:
        members = [m for m in ruolo.members if not m.bot]
        filtro_testo = f"del ruolo **@{ruolo.name}**"
    else:
        members = [m for m in interaction.guild.members if not m.bot]
        filtro_testo = "di **tutto il server**"

    totale = len(members)
    if totale == 0:
        return await interaction.followup.send("❌ Nessun membro trovato.")

    # Calcolo Stima e Rischio
    secondi_totali = totale * delay
    minuti_stima = secondi_totali / 60
    rischio = "Basso 🟢" if delay >= 2.0 else ("Moderato 🟡" if delay >= 1.5 else "Alto 🔴")

    # Riepilogo prima della conferma
    conferma_embed = discord.Embed(title="🚨 CONFERMA INVIO MASSIO", color=discord.Color.orange())
    conferma_embed.add_field(name="Destinatari", value=f"`{totale}` membri {filtro_testo}", inline=False)
    conferma_embed.add_field(name="Tempo Stimato", value=f"`{minuti_stima:.1f}` minuti", inline=True)
    conferma_embed.add_field(name="Rischio Bot", value=rischio, inline=True)
    conferma_embed.set_footer(text="Clicca Conferma per iniziare l'invio.")
    
    view = ConfirmDMView(interaction, members, messaggio, delay, immagine_url)
    msg_conferma = await interaction.followup.send(embed=conferma_embed, view=view)

    # Aspetta la risposta dai bottoni
    await view.wait()

    if view.value is None:
        await interaction.followup.send("⌛ Tempo scaduto. Operazione annullata.", ephemeral=True)
    elif view.value is True:
        # --- PARTE INVIO (Solo se confermato) ---
        status_msg = await interaction.followup.send("⏳ Inviando...", ephemeral=True)
        
        embed_dm = discord.Embed(
            title=f"📢 Annuncio da {interaction.guild.name}",
            description=messaggio,
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now()
        )
        if immagine_url: embed_dm.set_image(url=immagine_url)
        
        successi = 0
        falliti = 0

        for i, member in enumerate(members):
            try:
                await member.send(embed=embed_dm)
                successi += 1
            except:
                falliti += 1

            if (i + 1) % 5 == 0 or (i + 1) == totale:
                percentuale = ((i + 1) / totale) * 100
                try:
                    await status_msg.edit(content=f"🔄 **Progresso:** `{percentuale:.1f}%` ({i+1}/{totale})\n✅ OK: `{successi}` | ❌ NO: `{falliti}`")
                except: pass

            await asyncio.sleep(delay)

        await status_msg.edit(content=f"✅ **Operazione completata con successo!**")


# --- COMANDO CLONA / INVIA (Solo Admin) ---
@bot.tree.command(name="clona_messaggio", description="Copia un messaggio esistente e lo reinvia come nuovo")
@discord.app_commands.checks.has_permissions(administrator=True)
async def clona_messaggio(interaction: discord.Interaction, id_messaggio: str):
    # Usiamo il defer con ephemeral=True così l'utente vede il caricamento, 
    # ma il comando finale non apparirà come una risposta pubblica.
    await interaction.response.defer(ephemeral=True)

    try:
        canale = interaction.channel
        messaggio_vecchio = await canale.fetch_message(int(id_messaggio))
        
        # 1. Recuperiamo gli Embed
        embeds_da_copiare = messaggio_vecchio.embeds
        
        # 2. Recuperiamo i Bottoni (View)
        nuova_view = discord.ui.View()
        ha_bottoni = False
        
        if messaggio_vecchio.components:
            for riga in messaggio_vecchio.components:
                for comp in riga.children:
                    # Copiamo ogni bottone link esistente
                    nuova_view.add_item(discord.ui.Button(
                        label=comp.label, 
                        url=comp.url, 
                        emoji=comp.emoji,
                        style=comp.style
                    ))
                    ha_bottoni = True

        # 3. Invio del nuovo messaggio nel canale
        # Se non ci sono bottoni, passiamo None alla view
        await canale.send(
            embeds=embeds_da_copiare, 
            view=nuova_view if ha_bottoni else None
        )

        # Conferma solo a te che l'operazione è riuscita
        await interaction.followup.send("✅ Messaggio clonato e inviato correttamente!", ephemeral=True)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Errore durante la clonazione: {e}", ephemeral=True)

# Gestione errore permessi
@clona_messaggio.error
async def clona_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.ChecksFailure):
        await interaction.response.send_message("❌ Non hai i permessi per clonare messaggi.", ephemeral=True)
@bot.tree.command(name="esito_bando", description="[STAFF] Invia l'email ufficiale di esito candidatura")
@app_commands.choices(esito=[
    app_commands.Choice(name="✅ Accettata", value="Accettata"),
    app_commands.Choice(name="❌ Rifiutata", value="Rifiutata")
])
@app_commands.describe(
    utente="Il cittadino che riceverà l'email",
    esito="L'esito della valutazione",
    ruolo_lavoro="La posizione lavorativa per cui si è candidato",
    motivo="Note aggiuntive o dettagli per il cittadino"
)
async def esito_bando(
    interaction: discord.Interaction, 
    utente: discord.Member, 
    esito: str, 
    ruolo_lavoro: discord.Role,
    motivo: str = "Nessun dettaglio aggiuntivo"
):
    # Controllo permessi Staff
    staff_role = interaction.guild.get_role(RUOLO_STAFF_ID)
    if staff_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Non hai i permessi per gestire le assunzioni.", ephemeral=True)

    await interaction.response.defer()

    colore_email = discord.Color.green() if esito == "Accettata" else discord.Color.red()
    
    # Costruzione dell'Embed Email con il TUO messaggio
    embed_email = discord.Embed(
        title="📧 COMUNICAZIONE UFFICIALE",
        description=(
            f"**Oggetto:** Esito candidatura per **{ruolo_lavoro.name}**\n"
            f"**Da:** Risorse Umane - {interaction.guild.name}\n"
            "──────────────────────────────"
        ),
        color=colore_email,
        timestamp=discord.utils.utcnow()
    )

    # IL TUO MESSAGGIO PRE-IMPOSTATO
    corpo_email = (
        f"Gentile **{utente.display_name}**,\n\n"
        f"la contattiamo per l’offerta di lavoro mandata come **{ruolo_lavoro.name}**: "
        f"le comunico che è stata **{esito}** da questo incarico, la informeremo presto per i dettagli.\n\n"
        f"**Note:** {motivo}\n\n"
        "Cordiali saluti,\n"
        f"**{interaction.user.display_name}**"
    )

    embed_email.add_field(name="✉️ Messaggio", value=corpo_email, inline=False)
    embed_email.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
    embed_email.set_footer(text="Email Certificata - Dipartimento Risorse Umane")

    # --- LOGICA OPERATIVA ---
    if esito == "Accettata":
        try:
            await utente.add_roles(ruolo_lavoro)
        except:
            pass

    # 1. Invio in DM all'utente
    try:
        await utente.send(embed=embed_email)
        dm_info = "✅ Inviata anche in DM."
    except:
        dm_info = "⚠️ DM chiusi, inviata solo qui."

    # 2. Invio nel canale (Pubblico)
    await interaction.followup.send(content=f"{utente.mention}", embed=embed_email)
    
    # 3. Risposta allo Staff
    await interaction.followup.send(content=f"📫 **Email inviata.** {dm_info}", ephemeral=True)

import discord
from discord import app_commands
from discord.ext import commands

# --- LOGICHE AUTOCOMPLETE ---

async def item_inventario_autocomplete(interaction: discord.Interaction, current: str):
    conn = get_db_connection()
    cur = conn.cursor()
    # Filtriamo già per quantity > 0, ma la pulizia del DB renderà tutto più veloce
    cur.execute(
        "SELECT item_name FROM inventory WHERE user_id = %s AND item_name ILIKE %s AND quantity > 0", 
        (str(interaction.user.id), f"%{current}%")
    )
    items = cur.fetchall()
    cur.close(); conn.close()
    return [app_commands.Choice(name=i[0], value=i[0]) for i in items][:25]

async def item_nascosti_autocomplete(interaction: discord.Interaction, current: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT item_name FROM item_nascosti WHERE user_id = %s AND item_name ILIKE %s", 
        (str(interaction.user.id), f"%{current}%")
    )
    items = cur.fetchall()
    cur.close(); conn.close()
    return [app_commands.Choice(name=i[0], value=i[0]) for i in items][:25]


# --- COMANDO NASCONDI (PULIZIA x0 INCLUSA) ---

@bot.tree.command(name="nascondi", description="Nascondi un oggetto in un punto della mappa")
@app_commands.autocomplete(item=item_inventario_autocomplete)
@app_commands.describe(item="Oggetto da nascondere", quantita="Quantità da rimuovere", foto="Foto del nascondiglio")
async def nascondi(interaction: discord.Interaction, item: str, quantita: int, foto: discord.Attachment):
    if quantita <= 0: 
        return await interaction.response.send_message("❌ Inserisci una quantità valida.", ephemeral=True)
    
    if not foto.content_type or not foto.content_type.startswith('image'):
        return await interaction.response.send_message("❌ Devi allegare una foto del nascondiglio!", ephemeral=True)

    await interaction.response.defer(ephemeral=False)
    
    conn = get_db_connection(); cur = conn.cursor()
    
    cur.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (str(interaction.user.id), item))
    res = cur.fetchone()
    
    if not res or res[0] < quantita:
        cur.close(); conn.close()
        return await interaction.followup.send("❌ Non hai abbastanza oggetti nel tuo inventario.")

    try:
        # 1. Sottrai la quantità
        cur.execute("UPDATE inventory SET quantity = quantity - %s WHERE user_id = %s AND item_name = %s", (quantita, str(interaction.user.id), item))
        
        # 2. PULIZIA: Se la quantità è 0 o meno, elimina la riga dall'inventario
        cur.execute("DELETE FROM inventory WHERE user_id = %s AND item_name = %s AND quantity <= 0", (str(interaction.user.id), item))
        
        # 3. Inserisci nei nascosti
        cur.execute("INSERT INTO item_nascosti (user_id, item_name, quantita, foto_nascosto) VALUES (%s, %s, %s, %s)", 
                    (str(interaction.user.id), item, quantita, foto.url))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Errore durante l'operazione: {e}")

    cur.close(); conn.close()
    
    embed = discord.Embed(
        title="📦 NUOVO OGGETTO NASCOSTO", 
        description=f"{interaction.user.mention} ha nascosto qualcosa in città!",
        color=discord.Color.dark_grey(), 
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="👤 Segnalante", value=interaction.user.display_name, inline=True)
    embed.add_field(name="📦 Contenuto", value=f"**{quantita}x {item}**", inline=True)
    embed.set_image(url=foto.url)
    embed.set_footer(text="Usa /riprendi se trovi il posto corretto.")
    
    await interaction.followup.send(embed=embed)


# --- COMANDO RIPRENDI ---

@bot.tree.command(name="riprendi", description="Recupera un oggetto nascosto")
@app_commands.autocomplete(item=item_nascosti_autocomplete)
@app_commands.describe(item="Seleziona l'item nascosto", prova_posizione="Foto che prova la tua posizione attuale")
async def riprendi(interaction: discord.Interaction, item: str, prova_posizione: discord.Attachment):
    if not prova_posizione.content_type or not prova_posizione.content_type.startswith('image'):
        return await interaction.response.send_message("❌ Devi allegare una foto come prova del recupero!", ephemeral=True)

    await interaction.response.defer(ephemeral=False)
    
    conn = get_db_connection(); cur = conn.cursor()
    
    cur.execute("SELECT id, quantita, foto_nascosto FROM item_nascosti WHERE user_id = %s AND item_name = %s ORDER BY data_nascosto DESC LIMIT 1", (str(interaction.user.id), item))
    res = cur.fetchone()
    
    if not res:
        cur.close(); conn.close()
        return await interaction.followup.send("❌ Non risultano oggetti di questo tipo nascosti da te.")

    h_id, h_qty, h_foto = res[0], res[1], res[2]
    
    try:
        cur.execute("""
            INSERT INTO inventory (user_id, item_name, quantity) VALUES (%s, %s, %s) 
            ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
        """, (str(interaction.user.id), item, h_qty))
        
        cur.execute("DELETE FROM item_nascosti WHERE id = %s", (h_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Errore durante il recupero: {e}")

    cur.close(); conn.close()

    embed = discord.Embed(
        title="🔎 OGGETTO RECUPERATO", 
        description=f"{interaction.user.mention} ha recuperato il suo bottino!",
        color=discord.Color.green(), 
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="👤 Cittadino", value=interaction.user.display_name, inline=True)
    embed.add_field(name="📦 Oggetto", value=f"**{h_qty}x {item}**", inline=True)
    embed.add_field(name="🔗 Foto Originale", value=f"[Link del vecchio nascondiglio]({h_foto})", inline=False)
    embed.set_image(url=prova_posizione.url)
    
    await interaction.followup.send(embed=embed)

# --- COMANDO INSTAGRAM POST (FOTO & VIDEO) ---
@bot.tree.command(name="instagram", description="Crea un post in stile Instagram (Foto o Video)")
@app_commands.describe(
    titolo="Il titolo del post",
    descrizione="Il testo del post (facoltativo)",
    tag="Tag o Hashtag (facoltativo)",
    media="Allega la foto o il video del post"
)
async def instagram(
    interaction: discord.Interaction, 
    titolo: str, 
    media: discord.Attachment, 
    descrizione: str = None, 
    tag: str = None
):
    # Supportiamo immagini, gif e video
    formati_ammessi = ['image', 'video', 'gif']
    if not media.content_type or not any(x in media.content_type for x in formati_ammessi):
        return await interaction.response.send_message("❌ Puoi allegare solo Foto, GIF o Video!", ephemeral=True)

    await interaction.response.defer()

    # Creazione Embed
    embed = discord.Embed(
        title=f"📸 New Post from {interaction.user.display_name}",
        description=f"### {titolo}",
        color=discord.Color.from_rgb(225, 48, 108)
    )

    if descrizione:
        embed.description += f"\n\n{descrizione}"
    
    if tag:
        embed.add_field(name="📌 Tags", value=tag, inline=False)

    embed.set_footer(text="Instagram • Like to support")
    embed.timestamp = discord.utils.utcnow()

    # GESTIONE MEDIA
    is_video = 'video' in media.content_type or media.filename.endswith(('.mp4', '.mov', '.webm'))

    if is_video:
        # Se è un video, lo mandiamo come content per l'autoplay, l'embed sta sotto
        message = await interaction.followup.send(content=f"{media.url}", embed=embed)
    else:
        # Se è una foto/gif, la mettiamo dentro l'embed
        embed.set_image(url=media.url)
        message = await interaction.followup.send(embed=embed)
    
    # Aggiunta reazione
    await message.add_reaction("❤️")
import discord
from discord import app_commands
import datetime
import asyncio

# --- COMANDO PUBBLICO: 911 MESSICO ---
@bot.tree.command(name="911", description="📞 Effettua una chiamata d'emergenza ai servizi messicani")
@app_commands.choices(servizio=[
    app_commands.Choice(name="Guardia Nacional (Sicurezza)", value="gn"),
    app_commands.Choice(name="Cruz Roja (Ambulanza)", value="cruz_roja"),
    app_commands.Choice(name="Bomberos (Vigili del Fuoco)", value="bomberos")
])
@app_commands.describe(
    servizio="Seleziona il servizio di emergenza da contattare",
    nominativo="Inserisci il tuo Nome e Cognome (IC)",
    motivo="Descrivi brevemente l'emergenza",
    posizione="Indica la via o la zona dell'evento",
    messaggio="Dettagli aggiuntivi per le unità (opzionale)"
)
async def chiamata_911(
    interaction: discord.Interaction, 
    servizio: str, 
    nominativo: str, 
    motivo: str, 
    posizione: str, 
    messaggio: str = "Nessun dettaglio aggiuntivo"
):
    await interaction.response.defer(ephemeral=True)

    # Recupero dati dal Database
    conn = get_db_connection()
    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT canale_id, ruolo_id FROM setup_911 WHERE servizio = %s", (servizio,))
    config = cur.fetchone()
    cur.close(); conn.close()

    if not config:
        return await interaction.followup.send("❌ Questo servizio non è ancora stato configurato dall'amministrazione.", ephemeral=True)

    canale_dest = interaction.guild.get_channel(int(config['canale_id']))
    ruolo_tag = interaction.guild.get_role(int(config['ruolo_id']))

    if not canale_dest:
        return await interaction.followup.send("❌ Errore: Canale di ricezione non trovato.", ephemeral=True)

    # Configurazione Colori e Nomi Display
    nomi_servizi = {
        "gn": {"nome": "Guardia Nacional", "color": discord.Color.from_rgb(31, 55, 45)}, # Verde Messico
        "cruz_roja": {"nome": "Cruz Roja Mexicana", "color": discord.Color.red()},
        "bomberos": {"nome": "Bomberos (Protección Civil)", "color": discord.Color.orange()}
    }
    
    info = nomi_servizi.get(servizio)
    
    # Creazione Embed Dispatcher
    embed = discord.Embed(
        title=f"🇲🇽 CENTRALE OPERATIVA: {info['nome']}",
        color=info['color'],
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(name="👤 Segnalante", value=f"**{nominativo}**", inline=True)
    embed.add_field(name="📍 Posizione", value=f"**{posizione}**", inline=True)
    embed.add_field(name="⚠️ Emergenza", value=f"**{motivo}**", inline=False)
    embed.add_field(name="💬 Dettagli Report", value=messaggio, inline=False)
    
    embed.set_footer(text="Sistema Nazionale di Emergenza 911 • Messico")

    # Tag del ruolo configurato
    menzione = ruolo_tag.mention if ruolo_tag else "@everyone"
    
    await canale_dest.send(
        content=f"🚨 **NUOVA CHIAMATA PER {menzione}**", 
        embed=embed
    )

    await interaction.followup.send(f"✅ La tua segnalazione è stata inoltrata con successo alla **{info['nome']}**.")

# --- COMANDO ADMIN: SETUP 911 ---
@bot.tree.command(name="setup_911", description="[ADMIN] Configura i canali e i ruoli per il 911")
@app_commands.choices(servizio=[
    app_commands.Choice(name="Guardia Nacional", value="gn"),
    app_commands.Choice(name="Cruz Roja", value="cruz_roja"),
    app_commands.Choice(name="Bomberos", value="bomberos")
])
@app_commands.describe(
    servizio="Il dipartimento da configurare",
    canale="Il canale dove verranno inviati i messaggi di emergenza",
    ruolo="Il ruolo che riceverà il tag (notifica) per ogni chiamata"
)
async def setup_911(
    interaction: discord.Interaction, 
    servizio: str, 
    canale: discord.TextChannel, 
    ruolo: discord.Role
):
    # Controllo permessi
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Non hai i permessi necessari per configurare il sistema.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO setup_911 (servizio, canale_id, ruolo_id) 
        VALUES (%s, %s, %s)
        ON CONFLICT (servizio) 
        DO UPDATE SET 
            canale_id = EXCLUDED.canale_id, 
            ruolo_id = EXCLUDED.ruolo_id
    """, (servizio, str(canale.id), str(ruolo.id)))
    
    conn.commit(); cur.close(); conn.close()

    embed = discord.Embed(
        title="✅ CONFIGURAZIONE COMPLETATA",
        description=f"Il servizio **{servizio.upper()}** è stato configurato correttamente.",
        color=discord.Color.green()
    )
    embed.add_field(name="Canale Operativo", value=canale.mention, inline=True)
    embed.add_field(name="Ruolo Notificato", value=ruolo.mention, inline=True)

    await interaction.followup.send(embed=embed)

# --- 1. COMANDO CREA ---
@bot.tree.command(name="crea", description="Invia l'embed base con immagine")
@discord.app_commands.checks.has_permissions(administrator=True)
async def crea(interaction: discord.Interaction, testo: str, url_immagine: str):
    embed = discord.Embed(description=testo, color=0x2b2d31)
    embed.set_image(url=url_immagine)
    await interaction.response.send_message(embed=embed)
    
    
    
# --- HELPER: RECUPERO MEDIA E CONTROLLO PERMESSI ---

def get_media(tipo):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT media_url FROM media_stati WHERE tipo_stato = %s", (tipo,))
    res = cur.fetchone()
    cur.close(); conn.close()
    return res['media_url'] if res else None

async def check_stato_permission(interaction: discord.Interaction, tipo):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Cerca il role_id associato alla categoria (whitelist, assistenza, bandi)
    cur.execute("SELECT role_id FROM permessi_stati WHERE tipo_stato = %s", (tipo,))
    res = cur.fetchone()
    cur.close(); conn.close()
    if not res: return False
    # Verifica se l'utente ha il ruolo salvato nel DB
    return any(role.id == int(res['role_id']) for role in interaction.user.roles)

# --- COMANDI ADMIN (CONFIGURAZIONE) ---

@bot.tree.command(name="set_permessi_stato", description="[ADMIN] Imposta quale ruolo può usare i comandi stato")
@app_commands.choices(tipo=[
    app_commands.Choice(name="Whitelist", value="whitelist"),
    app_commands.Choice(name="Assistenza", value="assistenza"),
    app_commands.Choice(name="Bandi", value="bandi")
])
async def set_permessi_stato(interaction: discord.Interaction, tipo: str, ruolo: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Solo un admin può farlo.", ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO permessi_stati (tipo_stato, role_id) VALUES (%s, %s)
        ON CONFLICT (tipo_stato) DO UPDATE SET role_id = EXCLUDED.role_id
    """, (tipo, str(ruolo.id)))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Permessi `{tipo}` impostati per: {ruolo.mention}", ephemeral=True)

@bot.tree.command(name="set_media_stato", description="Imposta la GIF permanente per uno stato")
@app_commands.describe(tipo="Chiave dello stato", file_gif="GIF da archiviare")
@app_commands.choices(tipo=[
    app_commands.Choice(name="WL Online", value="whitelist_on"),
    app_commands.Choice(name="WL Offline", value="whitelist_off"),
    app_commands.Choice(name="Assistenza Online", value="assistenza_on"),
    app_commands.Choice(name="Assistenza Offline", value="assistenza_off"),
    app_commands.Choice(name="Bandi Aperti", value="bandi_on"),
    app_commands.Choice(name="Bandi Chiusi", value="bandi_off")
])
async def set_media_stato(interaction: discord.Interaction, tipo: str, file_gif: discord.Attachment):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Non hai i permessi.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    
    # Strada C: Archiviazione permanente
    canale_archivio = bot.get_channel(1498308854633594890) 
    msg_backup = await canale_archivio.send(content=f"📂 Backup: `{tipo}`", file=await file_gif.to_file())
    url_stabile = msg_backup.attachments[0].url

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO media_stati (tipo_stato, media_url) VALUES (%s, %s) 
        ON CONFLICT (tipo_stato) DO UPDATE SET media_url = EXCLUDED.media_url
    """, (tipo, url_stabile))
    conn.commit(); cur.close(); conn.close()

    await interaction.followup.send(f"✅ GIF per `{tipo}` salvata permanentemente!")

# --- LOGICA DI INVIO PUBBLICA ---

async def invia_embed_stato(interaction: discord.Interaction, tipo_chiave, titolo, descrizione, colore):
    # Controllo permessi basato sulla categoria (es. "whitelist")
    categoria = tipo_chiave.split('_')[0]
    if not await check_stato_permission(interaction, categoria):
        return await interaction.response.send_message("❌ Non hai il ruolo autorizzato per questo comando.", ephemeral=True)

    # Defer pubblico per l'annuncio
    await interaction.response.defer(ephemeral=False)

    url_media = get_media(tipo_chiave)
    if not url_media:
        return await interaction.followup.send(f"❌ GIF non configurata per `{tipo_chiave}`.")

    embed = discord.Embed(title=titolo, description=descrizione, color=colore, timestamp=discord.utils.utcnow())
    embed.set_image(url=url_media)
    embed.set_footer(text=f"Gestito da: {interaction.user.display_name}")
    
    await interaction.followup.send(embed=embed)

# --- COMANDI STATO OPERATIVI ---

@bot.tree.command(name="stato_whitelist", description="Cambia stato Whitelist")
@app_commands.choices(stato=[app_commands.Choice(name="Online", value="on"), app_commands.Choice(name="Offline", value="off")])
async def stato_whitelist(interaction: discord.Interaction, stato: str):
    if stato == "on":
        await invia_embed_stato(interaction, "whitelist_on", "🟢 WHITELIST ONLINE", "Le Whitelist sono ora **APERTE**!", discord.Color.green())
    else:
        await invia_embed_stato(interaction, "whitelist_off", "🔴 WHITELIST OFFLINE", "Le Whitelist sono ora **CHIUSE**.", discord.Color.red())

@bot.tree.command(name="stato_assistenza", description="Cambia stato Assistenza")
@app_commands.choices(stato=[app_commands.Choice(name="Online", value="on"), app_commands.Choice(name="Offline", value="off")])
async def stato_assistenza(interaction: discord.Interaction, stato: str):
    if stato == "on":
        await invia_embed_stato(interaction, "assistenza_on", "🛠️ ASSISTENZA ATTIVA", "Lo staff è disponibile nei vocali!", discord.Color.blue())
    else:
        await invia_embed_stato(interaction, "assistenza_off", "💤 ASSISTENZA CHIUSA", "Al momento l'assistenza è chiusa.", discord.Color.dark_grey())

@bot.tree.command(name="stato_bandi", description="Cambia stato Bandi")
@app_commands.choices(stato=[app_commands.Choice(name="Aperti", value="on"), app_commands.Choice(name="Chiusi", value="off")])
async def stato_bandi(interaction: discord.Interaction, stato: str):
    if stato == "on":
        await invia_embed_stato(interaction, "bandi_on", "📝 BANDI APERTI", "Inviate la vostra candidatura!", discord.Color.gold())
    else:
        await invia_embed_stato(interaction, "bandi_off", "🚫 BANDI CHIUSI", "Le candidature sono terminate.", discord.Color.dark_red())

    

import discord
from discord import app_commands
from psycopg2.extras import RealDictCursor
import datetime

# --- 1. SETUP ADMIN PER I RUOLI LAVORATORI ---
@bot.tree.command(name="setup_documenti", description="[ADMIN] Imposta i ruoli che possono usare i comandi documenti")
@app_commands.checks.has_permissions(administrator=True)
async def setup_documenti(interaction: discord.Interaction, 
                           ruolo_patenti: discord.Role, 
                           ruolo_medico: discord.Role, 
                           ruolo_porto_armi: discord.Role, 
                           ruolo_registrazione_armi: discord.Role):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO public.docs_config (guild_id, role_id_patenti, role_id_medico, role_id_porto_armi, role_id_registro_armi) 
        VALUES (%s, %s, %s, %s, %s) ON CONFLICT (guild_id) DO UPDATE SET 
        role_id_patenti=EXCLUDED.role_id_patenti, 
        role_id_medico=EXCLUDED.role_id_medico, 
        role_id_porto_armi=EXCLUDED.role_id_porto_armi, 
        role_id_registro_armi=EXCLUDED.role_id_registro_armi
    """, (str(interaction.guild.id), str(ruolo_patenti.id), str(ruolo_medico.id), str(ruolo_porto_armi.id), str(ruolo_registrazione_armi.id)))
    conn.commit()
    cur.close()
    conn.close()
    await interaction.response.send_message("✅ Ruoli lavoratori configurati con successo nel database!", ephemeral=True)

# --- 2. LOGICA DI REGISTRAZIONE UNIVERSALE ---
async def execute_doc_registration(interaction, cittadino, titolo, dettagli_testo, costo, motivo, config_key, colore, emoji, tipo_db, extra_data=None):
    # Connessione per controllo permessi
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM public.docs_config WHERE guild_id = %s", (str(interaction.guild.id),))
    config = cur.fetchone()

    # Controllo se il ruolo dell'utente coincide con quello configurato
    if not config or str(config[config_key]) not in [str(r.id) for r in interaction.user.roles]:
        cur.close(); conn.close()
        return await interaction.response.send_message(f"❌ Non sei autorizzato (Ruolo richiesto non configurato o mancante).", ephemeral=True)

    try:
        # --- INSERIMENTO NEL DATABASE ---
        if tipo_db == 'patente':
            cur.execute("INSERT INTO public.patenti_registrate (user_id, tipo, costo, motivo) VALUES (%s, %s, %s, %s)",
                        (str(cittadino.id), extra_data['tipo'], costo, motivo))
        elif tipo_db == 'medico':
            cur.execute("INSERT INTO public.certificati_medici (user_id, esito, costo, motivo) VALUES (%s, %s, %s, %s)",
                        (str(cittadino.id), extra_data['esito'], costo, motivo))
        elif tipo_db == 'porto_armi':
            cur.execute("INSERT INTO public.licenze_armi (user_id, tipo, motivo) VALUES (%s, %s, %s)",
                        (str(cittadino.id), extra_data['tipo'], motivo))
        elif tipo_db == 'arma':
            cur.execute("INSERT INTO public.registro_armi (user_id, modello, matricola, motivo, costo) VALUES (%s, %s, %s, %s, %s)",
                        (str(cittadino.id), extra_data['modello'], extra_data['matricola'], motivo, costo))

        conn.commit()
        
        # --- CREAZIONE EMBED ---
        embed = discord.Embed(
            title=f"{emoji} {titolo}",
            description=f"Documentazione ufficiale registrata per il cittadino {cittadino.mention}.",
            color=colore,
            timestamp=datetime.datetime.now()
        )
        embed.set_thumbnail(url=cittadino.display_avatar.url)
        embed.add_field(name="👤 Soggetto", value=cittadino.mention, inline=True)
        embed.add_field(name="👔 Operatore", value=interaction.user.mention, inline=True)
        embed.add_field(name="💰 Costo", value=f"**{costo}**", inline=True)
        embed.add_field(name="📋 Info", value=dettagli_testo, inline=False)
        embed.add_field(name="📝 Motivo", value=motivo, inline=False)
        embed.set_footer(text=f"Sistema Documentale Evren City")

        await interaction.response.send_message(content=f"📑 Registrazione completata per {cittadino.mention}", embed=embed)

    except Exception as e:
        print(f"Errore DB: {e}")
        await interaction.response.send_message("❌ Errore durante il salvataggio dei dati.", ephemeral=True)
    finally:
        cur.close(); conn.close()

# --- 3. COMANDI OPERATIVI ---

@bot.tree.command(name="patente", description="Registra una patente a un cittadino")
async def patente(interaction: discord.Interaction, cittadino: discord.Member, tipo: str, costo: str, motivo: str):
    await execute_doc_registration(interaction, cittadino, "Patente di Guida", 
                                  f"**Categoria:** {tipo}", costo, motivo, 
                                  'role_id_patenti', discord.Color.blue(), "🪪",
                                  tipo_db='patente', extra_data={'tipo': tipo})

@bot.tree.command(name="certificato", description="Rilascia certificato medico a un cittadino")
async def certificato(interaction: discord.Interaction, cittadino: discord.Member, esito: str, costo: str, motivo: str):
    await execute_doc_registration(interaction, cittadino, "Certificato Medico", 
                                  f"**Esito:** {esito}", costo, motivo, 
                                  'role_id_medico', discord.Color.red(), "⚕️",
                                  tipo_db='medico', extra_data={'esito': esito})

@bot.tree.command(name="porto_darmi", description="Registra licenza porto d'armi")
async def porto_darmi(interaction: discord.Interaction, cittadino: discord.Member, tipo_licenza: str, costo: str, motivo: str):
    await execute_doc_registration(interaction, cittadino, "Porto d'Armi", 
                                  f"**Licenza:** {tipo_licenza}", costo, motivo, 
                                  'role_id_porto_armi', discord.Color.dark_grey(), "🔫",
                                  tipo_db='porto_armi', extra_data={'tipo': tipo_licenza})

@bot.tree.command(name="registra_arma", description="Registra matricola arma a un cittadino")
async def registra_arma(interaction: discord.Interaction, cittadino: discord.Member, modello: str, matricola: str, costo: str, motivo: str):
    await execute_doc_registration(interaction, cittadino, "Registrazione Arma", 
                                  f"**Modello:** {modello}\n**Matricola:** `{matricola}`", 
                                  costo, motivo, 'role_id_registro_armi', discord.Color.dark_red(), "⚙️",
                                  tipo_db='arma', extra_data={'modello': modello, 'matricola': matricola})

# --- 3. COMANDI LAVORATORI ---
@bot.tree.command(name="give_money", description="[STAFF] Accredita soldi a un cittadino")
@app_commands.choices(tipo=[
    app_commands.Choice(name="Contanti", value="wallet"),
    app_commands.Choice(name="Banca", value="bank")
])
async def give_money(interaction: Interaction, utente: discord.Member, importo: int, tipo: str):
    # Controllo Ruolo Staff
    if not any(role.id == RUOLO_STAFF_ID for role in interaction.user.roles):
        return await interaction.response.send_message("❌ Permessi insufficienti: non sei un membro dello Staff.", ephemeral=True)
    
    if importo <= 0:
        return await interaction.response.send_message("❌ Inserisci un importo superiore a 0.", ephemeral=True)

    # Aggiornamento Database
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET {tipo} = {tipo} + %s WHERE user_id = %s", (importo, str(utente.id)))
    conn.commit()
    cur.close()
    conn.close()
    
    await interaction.response.send_message(f"✅ Accreditati **{importo}$** in **{tipo}** a {utente.mention}.")
    
    # Log Finanziario
    emb = discord.Embed(title="🎁 ACCREDITO STAFF", color=discord.Color.purple(), timestamp=discord.utils.utcnow())
    emb.add_field(name="Staffer", value=interaction.user.mention)
    emb.add_field(name="Ricevente", value=utente.mention)
    emb.add_field(name="Importo", value=f"{importo}$ ({tipo})")
    await invia_log_finanziario(interaction.guild, emb)


@bot.tree.command(name="remove_money", description="[STAFF] Rimuovi soldi a un cittadino")
@app_commands.choices(tipo=[
    app_commands.Choice(name="Contanti", value="wallet"),
    app_commands.Choice(name="Banca", value="bank")
])
async def remove_money(interaction: Interaction, utente: discord.Member, importo: int, tipo: str):
    # Controllo Ruolo Staff
    if not any(role.id == RUOLO_STAFF_ID for role in interaction.user.roles):
        return await interaction.response.send_message("❌ Permessi insufficienti: non sei un membro dello Staff.", ephemeral=True)
    
    if importo <= 0:
        return await interaction.response.send_message("❌ Inserisci un importo superiore a 0.", ephemeral=True)

    # Aggiornamento Database
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET {tipo} = {tipo} - %s WHERE user_id = %s", (importo, str(utente.id)))
    conn.commit()
    cur.close()
    conn.close()
    
    await interaction.response.send_message(f"⚠️ Rimossi **{importo}$** dai **{tipo}** di {utente.mention}.")
    
    # Log Finanziario
    emb = discord.Embed(title="🚫 RIMOZIONE STAFF", color=discord.Color.dark_grey(), timestamp=discord.utils.utcnow())
    emb.add_field(name="Staffer", value=interaction.user.mention)
    emb.add_field(name="Soggetto", value=utente.mention)
    emb.add_field(name="Importo", value=f"{importo}$ ({tipo})")
    await invia_log_finanziario(interaction.guild, emb)


# --- 2. COMANDO AGGIUNGI BOTTONE ---
@bot.tree.command(name="aggiungi", description="Aggiunge un bottone link a un messaggio esistente")
@discord.app_commands.checks.has_permissions(administrator=True)
async def aggiungi(interaction: discord.Interaction, id_messaggio: str, testo_bottone: str, link: str, emoji: str = None):
    try:
        messaggio = await interaction.channel.fetch_message(int(id_messaggio))
        view = discord.ui.View()

        if messaggio.components:
            for row in messaggio.components:
                for comp in row.children:
                    if isinstance(comp, discord.Button):
                        view.add_item(discord.ui.Button(label=comp.label, url=comp.url, emoji=comp.emoji, style=discord.ButtonStyle.link))

        view.add_item(discord.ui.Button(label=testo_bottone, url=link, emoji=emoji, style=discord.ButtonStyle.link))
        await messaggio.edit(view=view)
        await interaction.response.send_message(f"✅ Bottone '{testo_bottone}' aggiunto!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
# --- LOGICA STAFF: VIEW E MODAL PER APPROVAZIONE ---

import discord
from discord.ext import commands
import psycopg2
from psycopg2.extras import RealDictCursor




# Funzione Helper per inviare i log finanziari nel canale settato
async def invia_log_finanziario(guild, embed):
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT setting_value FROM server_settings WHERE setting_name = 'log_finanze'")
        res = cur.fetchone()
        cur.close(); conn.close()
        if res:
            canale = guild.get_channel(int(res['setting_value']))
            if canale: await canale.send(embed=embed)
    except Exception as e:
        print(f"Errore log finanziario: {e}")

# --- COMANDI AMMINISTRATIVI ---

@bot.tree.command(name="set_log_finanze", description="[ADMIN] Imposta il canale per i log economici del server")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_finanze(interaction: Interaction, canale: discord.TextChannel):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO server_settings (setting_name, setting_value) 
        VALUES ('log_finanze', %s) 
        ON CONFLICT (setting_name) DO UPDATE SET setting_value = EXCLUDED.setting_value
    """, (str(canale.id),))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Canale log finanziari impostato su {canale.mention}", ephemeral=True)

# --- ECONOMIA PERSONALE (PORTAFOGLIO E BANCA) ---

@bot.tree.command(name="deposita", description="Sposta i tuoi contanti in banca")
async def deposita(interaction: discord.Interaction, importo: int):
    # Controllo immediato dell'input
    if importo <= 0:
        return await interaction.response.send_message("❌ Inserisci un importo valido.", ephemeral=True)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Iniziamo la transazione atomica
        cur.execute("BEGIN;")

        # Eseguiamo lo spostamento solo se i contanti (wallet) sono sufficienti
        cur.execute("""
            UPDATE users 
            SET wallet = wallet - %s, bank = bank + %s 
            WHERE user_id = %s AND wallet >= %s
        """, (importo, importo, str(interaction.user.id), importo))

        # Se rowcount è 0, l'utente non aveva abbastanza contanti nel database
        if cur.rowcount == 0:
            conn.rollback()
            return await interaction.response.send_message("❌ Non hai abbastanza contanti nel portafoglio.", ephemeral=True)

        conn.commit()
        await interaction.response.send_message(f"🏦 **{interaction.user.display_name}** ha depositato **{importo}$** nel proprio conto bancario.")

        # LOG FINANZIARIO
        emb = discord.Embed(
            title="📥 LOG DEPOSITO PERSONALE", 
            color=discord.Color.light_grey(), 
            timestamp=discord.utils.utcnow()
        )
        emb.add_field(name="Utente", value=interaction.user.mention)
        emb.add_field(name="Importo", value=f"{importo}$")
        await invia_log_finanziario(interaction.guild, emb)

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Fallimento deposito per {interaction.user.id}: {e}")
        await interaction.response.send_message("❌ Errore tecnico durante l'operazione bancaria.", ephemeral=True)
    finally:
        cur.close(); conn.close()

@bot.tree.command(name="preleva", description="Preleva soldi dal tuo conto bancario")
async def preleva(interaction: discord.Interaction, importo: int):
    if importo <= 0:
        return await interaction.response.send_message("❌ Inserisci un importo valido.", ephemeral=True)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Inizio transazione
        cur.execute("BEGIN;")

        # Eseguiamo l'operazione solo se il saldo in banca è sufficiente
        cur.execute("""
            UPDATE users 
            SET bank = bank - %s, wallet = wallet + %s 
            WHERE user_id = %s AND bank >= %s
        """, (importo, importo, str(interaction.user.id), importo))

        # Se rowcount è 0, significa che la condizione 'bank >= importo' non era soddisfatta
        if cur.rowcount == 0:
            conn.rollback()
            return await interaction.response.send_message("❌ Fondi bancari insufficienti per completare il prelievo.", ephemeral=True)

        conn.commit()
        await interaction.response.send_message(f"💸 **{interaction.user.display_name}** ha prelevato **{importo}$** dal proprio conto.")

        # LOGS
        emb = discord.Embed(
            title="📤 LOG PRELIEVO PERSONALE", 
            color=discord.Color.orange(), 
            timestamp=discord.utils.utcnow()
        )
        emb.add_field(name="Utente", value=interaction.user.mention)
        emb.add_field(name="Importo", value=f"{importo}$")
        await invia_log_finanziario(interaction.guild, emb)

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Errore prelievo per {interaction.user.id}: {e}")
        await interaction.response.send_message("❌ Errore tecnico durante il prelievo.", ephemeral=True)
    finally:
        cur.close(); conn.close()

@bot.tree.command(name="paga", description="Consegna contanti a un altro cittadino (mano a mano)")
async def paga(interaction: discord.Interaction, utente: discord.Member, importo: int):
    if utente.id == interaction.user.id: 
        return await interaction.response.send_message("❌ Non puoi pagare te stesso.", ephemeral=True)
    if importo <= 0: 
        return await interaction.response.send_message("❌ L'importo deve essere positivo.", ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Iniziamo una transazione: o tutto o niente
        cur.execute("BEGIN;")

        # Sottraiamo i soldi solo SE il wallet è sufficiente (AND wallet >= %s)
        # Questo previene il negativo anche se il bot lagga
        cur.execute("""
            UPDATE users 
            SET wallet = wallet - %s 
            WHERE user_id = %s AND wallet >= %s
        """, (importo, str(interaction.user.id), importo))

        # Controlliamo se la riga è stata effettivamente aggiornata
        if cur.rowcount == 0:
            conn.rollback() # Annulla tutto
            return await interaction.response.send_message("❌ Non hai abbastanza contanti nel portafoglio.", ephemeral=True)

        # Se il mittente ha pagato, aggiungiamo al destinatario
        cur.execute("UPDATE users SET wallet = wallet + %s WHERE user_id = %s", (importo, str(utente.id)))
        
        conn.commit() # Confermiamo l'operazione
        await interaction.response.send_message(f"🤝 **{interaction.user.display_name}** ha consegnato **{importo}$** a **{utente.mention}**.")

        # LOGS
        emb = discord.Embed(title="💵 LOG SCAMBIO CONTANTI", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        emb.add_field(name="Mittente", value=interaction.user.mention)
        emb.add_field(name="Destinatario", value=utente.mention)
        emb.add_field(name="Importo", value=f"{importo}$")
        await invia_log_finanziario(interaction.guild, emb)

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Errore durante il pagamento: {e}")
        await interaction.response.send_message("❌ Errore tecnico durante la transazione.", ephemeral=True)
    finally:
        cur.close(); conn.close()

@bot.tree.command(name="deposita_soldi_fazione", description="Deposita contanti nel fondo della fazione")
async def deposita_soldi_fazione(interaction: Interaction, importo: int):
    await interaction.response.defer()
    miei_ruoli = await get_miei_ruoli_fazione(interaction)
    if not miei_ruoli: return await interaction.followup.send("❌ Non fai parte di nessuna fazione autorizzata.")
    u = get_user_data(interaction.user.id)
    if importo <= 0 or u['wallet'] < importo: return await interaction.followup.send("❌ Non hai abbastanza contanti nel portafoglio.")

    async def procedi(inter, rid):
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (importo, str(inter.user.id)))
        cur.execute("UPDATE depositi SET money = money + %s WHERE role_id = %s", (importo, rid))
        conn.commit(); cur.close(); conn.close()
        r_obj = inter.guild.get_role(int(rid))
        await inter.followup.send(f"✅ Hai depositato **{importo}$** nel fondo di: **{r_obj.name}**.")
        
        emb = discord.Embed(title="🏢 LOG DEPOSITO FAZIONE", color=discord.Color.dark_green(), timestamp=discord.utils.utcnow())
        emb.add_field(name="Utente", value=inter.user.mention); emb.add_field(name="Fazione", value=r_obj.name); emb.add_field(name="Importo", value=f"{importo}$")
        await invia_log_finanziario(inter.guild, emb)

    if len(miei_ruoli) == 1: 
        await procedi(interaction, str(miei_ruoli[0].id))
    else:
        view = discord.ui.View()
        sel = discord.ui.Select(options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in miei_ruoli])
        
        async def call(i):
            # Disabilita il menu e aggiorna il messaggio originale
            sel.disabled = True
            await i.response.edit_message(view=view)
            # Esegue la transazione
            await procedi(i, sel.values[0])
            
        sel.callback = call; view.add_item(sel)
        await interaction.followup.send("In quale fazione desideri depositare?", view=view, ephemeral=True)

@bot.tree.command(name="preleva_soldi_fazione", description="Preleva soldi dal fondo della fazione")
async def preleva_soldi_fazione(interaction: Interaction, importo: int):
    await interaction.response.defer()
    miei_ruoli = await get_miei_ruoli_fazione(interaction)
    if not miei_ruoli: return await interaction.followup.send("❌ Non hai i permessi fazione necessari.")

    async def procedi(inter, rid):
        conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT money FROM depositi WHERE role_id = %s", (rid,))
        res = cur.fetchone()
        if not res or res['money'] < importo: return await inter.followup.send("❌ Il fondo fazione non dispone di tale cifra.")
        cur.execute("UPDATE depositi SET money = money - %s WHERE role_id = %s", (importo, rid))
        cur.execute("UPDATE users SET wallet = wallet + %s WHERE user_id = %s", (importo, str(inter.user.id)))
        conn.commit(); cur.close(); conn.close()
        r_obj = inter.guild.get_role(int(rid))
        await inter.followup.send(f"💸 Hai prelevato **{importo}$** dal fondo di: **{r_obj.name}**.")
        
        emb = discord.Embed(title="🏢 LOG PRELIEVO FAZIONE", color=discord.Color.dark_red(), timestamp=discord.utils.utcnow())
        emb.add_field(name="Utente", value=inter.user.mention); emb.add_field(name="Fazione", value=r_obj.name); emb.add_field(name="Importo", value=f"{importo}$")
        await invia_log_finanziario(inter.guild, emb)

    if len(miei_ruoli) == 1: 
        await procedi(interaction, str(miei_ruoli[0].id))
    else:
        view = discord.ui.View()
        sel = discord.ui.Select(options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in miei_ruoli])
        
        async def call(i):
            # Disabilita il menu e aggiorna il messaggio originale
            sel.disabled = True
            await i.response.edit_message(view=view)
            # Esegue la transazione
            await procedi(i, sel.values[0])
            
        sel.callback = call; view.add_item(sel)
        await interaction.followup.send("Da quale fazione desideri prelevare?", view=view, ephemeral=True)

# --- PAGAMENTO SANZIONI E FATTURE ---

# --- VIEW PERSISTENTE ---
class RapinaStaffView(discord.ui.View):
    def __init__(self, rapina_id=None):
        super().__init__(timeout=None)
        
        # Se passiamo un ID quando creiamo il messaggio, personalizziamo i custom_id
        if rapina_id is not None:
            self.conferma_btn.custom_id = f"rapina_conf:{rapina_id}"
            self.annulla_btn.custom_id = f"rapina_ann:{rapina_id}"
            self.modifica_btn.custom_id = f"rapina_mod:{rapina_id}"

    # Helper recupero dati dal database
    async def get_data(self, button_custom_id):
        try:
            rapina_id = int(button_custom_id.split(":")[1])
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
            cur = conn.cursor()
            cur.execute("SELECT * FROM rapine_pendenti WHERE id = %s", (rapina_id,))
            res = cur.fetchone()
            cur.close()
            conn.close()
            return res, rapina_id
        except Exception as e:
            print(f"Errore get_data: {e}")
            return None, None

    # Bottone Conferma
    @discord.ui.button(label="Conferma", style=discord.ButtonStyle.success, custom_id="rapina_conf:default")
    async def conferma_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data, r_id = await self.get_data(button.custom_id)
        if not data:
            return await interaction.response.send_message("❌ Errore: Rapina non trovata o già processata.", ephemeral=True)

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE users SET wallet = wallet + %s WHERE user_id = %s", (data['ammontare'], str(data['user_id'])))
        cur.execute("DELETE FROM rapine_pendenti WHERE id = %s", (r_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        # Aggiorna il messaggio originale dell'utente con i dati completi
        await self.aggiorna_originale(interaction, data, "✅ **APPROVATA**", discord.Color.green(), staff_member=interaction.user)
        await self.notificami(interaction, data['user_id'], f"✅ Il tuo bottino per la rapina a **{data['luogo']}** è stato approvato! Ricevuti: **{data['ammontare']}€**")
        await interaction.response.edit_message(content=f"✅ **APPROVATA**: {data['ammontare']}€ a <@{data['user_id']}>.", embed=None, view=None)

    # Bottone Annulla
    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.danger, custom_id="rapina_ann:default")
    async def annulla_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data, r_id = await self.get_data(button.custom_id)
        if not data:
            return await interaction.response.send_message("❌ Errore: Rapina non trovata.", ephemeral=True)

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM rapine_pendenti WHERE id = %s", (r_id,))
        conn.commit()
        cur.close()
        conn.close()

        # Aggiorna il messaggio originale dell'utente come rifiutato
        await self.aggiorna_originale(interaction, data, "❌ **RESPINTA / ANNULLATA**", discord.Color.red(), staff_member=interaction.user)
        await self.notificami(interaction, data['user_id'], f"❌ La tua rapina a **{data['luogo']}** è stata annullata dallo staff.")
        await interaction.response.edit_message(content=f"❌ **RIFIUTATA**: Colpo di <@{data['user_id']}> invalidato.", embed=None, view=None)

    # Bottone Modifica Importo
    @discord.ui.button(label="Modifica Importo", style=discord.ButtonStyle.secondary, custom_id="rapina_mod:default")
    async def modifica_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data, r_id = await self.get_data(button.custom_id)
        if not data:
            return await interaction.response.send_message("❌ Errore: Rapina non trovata.", ephemeral=True)
        
        await interaction.response.send_modal(ModificaBottinoModal(data, r_id))

    # NUOVO HELPER: Riscrive l'embed finale dell'utente con tutti i dettagli
    async def aggiorna_originale(self, interaction, data, esito, colore, staff_member):
        try:
            canale = interaction.guild.get_channel(int(data['canale_utente_id']))
            msg = await canale.fetch_message(int(data['msg_utente_id']))
            
            # Creiamo un nuovissimo embed ricco di informazioni da sostituire a quello vecchio
            embed_esito = discord.Embed(
                title="📊 RESOCONTO FINALE RAPINA",
                color=colore
            )
            embed_esito.add_field(name="👤 Cittadino", value=f"<@{data['user_id']}>", inline=True)
            embed_esito.add_field(name="📍 Luogo Colpo", value=str(data['luogo']).upper(), inline=True)
            embed_esito.add_field(name="💰 Bottino Guadagnato", value=f"**{data['ammontare']}€**", inline=False)
            embed_esito.add_field(name="🛡️ Stato Richiesta", value=esito, inline=True)
            embed_esito.add_field(name="👨‍✈️ Gestito da", value=staff_member.mention, inline=True)
            
            # Modifica il messaggio rimuovendo anche la dicitura "Allerta Ruolo" se presente nel content
            await msg.edit(content=None, embed=embed_esito)
        except Exception as e:
            print(f"Errore aggiorna_originale: {e}")

    async def notificami(self, interaction, user_id, testo):
        try:
            user = await interaction.guild.get_channel(int(user_id)) # Fallback se cercato in cache
            user = await interaction.guild.fetch_member(int(user_id))
            if not user: 
                user = await interaction.client.fetch_user(int(user_id))
            await user.send(testo)
        except Exception as e:
            print(f"Errore DM notifica: {e}")


# --- AUTOCOMPLETE ---
async def rapina_autocomplete(interaction: discord.Interaction, current: str):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT nome FROM rapine_config WHERE nome ILIKE %s LIMIT 25", (f'%{current}%',))
    choices = [app_commands.Choice(name=row[0].upper(), value=row[0]) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return choices



# ==========================================
# COMMAND TREE: INIZIA RAPINA (COMPLETO)
# ==========================================
@bot.tree.command(name="inizia_rapina", description="Inizia lo scasso in un luogo configurato")
@app_commands.describe(luogo="Scegli il luogo in cui avviare lo scasso")
@app_commands.autocomplete(luogo=rapina_autocomplete)
async def inizia_rapina(interaction: discord.Interaction, luogo: str):
    await interaction.response.defer()
    
    # Tentativo di connessione al database
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cur = conn.cursor()
    except Exception as db_init_err:
        print(f"[ERROR] Impossibile connettersi al database: {db_init_err}")
        return await interaction.followup.send("❌ Errore tecnico di connessione al database.", ephemeral=True)
    
    try:
        # 1. Recupera Config Rapina e Canale Staff
        cur.execute("SELECT * FROM rapine_config WHERE nome = %s", (luogo.lower(),))
        config = cur.fetchone()
        
        cur.execute("SELECT setting_value FROM server_settings WHERE setting_name = 'canale_rapine'")
        res_canale = cur.fetchone()
        
        if not config:
            cur.close()
            conn.close()
            return await interaction.followup.send("❌ Luogo non configurato.")
        
        if not res_canale:
            cur.close()
            conn.close()
            return await interaction.followup.send("❌ Canale staff rapine non impostato nel DB.")

        # Estrazione delle variabili dalla query
        canale_staff_id = int(res_canale['setting_value'])
        tempo_rimanente = config['tempo_scasso']
        paga_casuale = random.randint(config['paga_min'], config['paga_max'])
        
        RUOLO_NOTIFICA_ID = 1363487988570521670

        # Creazione dell'Embed Iniziale (Rosso per rapina in corso)
        embed = discord.Embed(
            title="🚨 RAPINA IN CORSO", 
            description=f"Sede: **{luogo.upper()}**", 
            color=discord.Color.red()
        )
        embed.add_field(name="Progresso", value=f"⏳ Scasso in corso: `{tempo_rimanente}s`")

        # Configura le menzioni consentite per permettere il ping di questo ruolo
        allowed_mentions = discord.AllowedMentions(roles=[discord.Object(id=RUOLO_NOTIFICA_ID)])

        # Invio del primo messaggio con l'embed e la menzione dello staff
        msg = await interaction.followup.send(
            content=f"⚠️ Allerta <@&{RUOLO_NOTIFICA_ID}>!", 
            embed=embed,
            allowed_mentions=allowed_mentions
        )

        # Loop Timer Scasso (aggiornamento ogni 5 secondi)
        while tempo_rimanente > 0:
            await asyncio.sleep(5)
            tempo_rimanente -= 5
            if tempo_rimanente < 0: 
                tempo_rimanente = 0
                
            embed.set_field_at(0, name="Progresso", value=f"⏳ Scasso in corso: `{tempo_rimanente}s`")
            try:
                # Mantieni allowed_mentions anche nell'edit per preservare la struttura
                await msg.edit(embed=embed)
            except Exception:
                # Se l'utente cancella il messaggio o si verifica un errore nell'edit, chiude le connessioni ed esce
                cur.close()
                conn.close()
                return

        # ==========================================
        # SCASSO COMPLETATO - GESTIONE FINE TIMER
        # ==========================================
        # 1. Creiamo l'embed arancione di attesa approvazione per l'utente/canale rapina
        embed_attesa = discord.Embed(
            title="🚨 SCASSO COMPLETATO",
            description=f"Lo scasso presso **{luogo.upper()}** è stato completato con successo da {interaction.user.mention}.\nIl sistema è ora in attesa di una revisione da parte dello staff.",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed_attesa.add_field(name="📍 Sede Colpita", value=f"**{luogo.upper()}**", inline=True)
        embed_attesa.add_field(name="💰 Bottino Stimato", value=f"**{paga_casuale:,.2f}$**", inline=True)
        embed_attesa.add_field(name="📊 Stato Richiesta", value="⏳ In attesa di approvazione dello Staff", inline=False)
        embed_attesa.set_footer(text="Sistema Rapine Automatico")

        # Aggiorna il messaggio originale rimuovendo la menzione testuale iniziale
        try:
            await msg.edit(content=None, embed=embed_attesa)
        except Exception as msg_err:
            print(f"[ERROR] Impossibile aggiornare il messaggio di rapina: {msg_err}")

        # 2. Invio della richiesta di approvazione nel canale Staff configurato
        canale_staff = interaction.guild.get_channel(canale_staff_id)
        if not canale_staff:
            try:
                canale_staff = await interaction.guild.fetch_channel(canale_staff_id)
            except Exception:
                canale_staff = None

        if canale_staff:
            embed_staff = discord.Embed(
                title="📋 NUOVA RAPINA DA APPROVARE",
                description=f"L'utente {interaction.user.mention} ha terminato lo scasso e richiede l'erogazione del bottino.",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            embed_staff.add_field(name="👤 Autore", value=interaction.user.mention, inline=True)
            embed_staff.add_field(name="📍 Luogo", value=f"**{luogo.upper()}**", inline=True)
            embed_staff.add_field(name="💵 Somma da Erogare", value=f"**{paga_casuale:,.2f}$**", inline=True)
            embed_staff.set_footer(text=f"ID Utente: {interaction.user.id} | Approva manualmente nel database o tramite comando")

            await canale_staff.send(embed=embed_staff)
        else:
            print(f"[WARNING] Canale staff rapine (ID: {canale_staff_id}) non trovato nel server Discord.")

        # Chiudiamo le risorse del database in modo sicuro al termine del successo
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Errore generale nel comando inizia_rapina: {e}")
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
        try:
            await interaction.followup.send("❌ Si è verificato un errore tecnico durante lo scasso.", ephemeral=True)
        except Exception:
            pass





# --- COMANDO ADMIN: CREA CONFIGURAZIONE RAPINA ---
@bot.tree.command(name="crea_rapina", description="Configura una nuova rapina (Solo Admin)")
@app_commands.describe(
    nome="Nome del luogo (es: Banca, Market)", 
    tempo="Secondi necessari per lo scasso", 
    paga_min="Guadagno minimo", 
    paga_max="Guadagno massimo"
)
async def crea_rapina(interaction: discord.Interaction, nome: str, tempo: int, paga_min: int, paga_max: int):
    # Controllo permessi Admin/Staff
    if not any(role.id == RUOLO_STAFF_ID for role in interaction.user.roles):
        return await interaction.response.send_message("❌ Permessi insufficienti per configurare rapine.", ephemeral=True)

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Inserisce o aggiorna se il nome esiste già (ON CONFLICT)
        cur.execute("""
            INSERT INTO rapine_config (nome, tempo_scasso, paga_min, paga_max)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (nome) DO UPDATE SET 
            tempo_scasso = EXCLUDED.tempo_scasso, 
            paga_min = EXCLUDED.paga_min, 
            paga_max = EXCLUDED.paga_max
        """, (nome.lower(), tempo, paga_min, paga_max))
        
        conn.commit()
        cur.close()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ Configurazione completata!\n"
            f"📍 Luogo: **{nome.upper()}**\n"
            f"⏳ Tempo: `{tempo}s`\n"
            f"💰 Range: `{paga_min}€` - `{paga_max}€`"
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Errore durante il salvataggio nel Database: {e}", ephemeral=True)

# --- 3. COMANDO AGGIORNA CONTENUTO ---
@bot.tree.command(name="aggiorna", description="Modifica testo o immagine dell'embed")
@discord.app_commands.checks.has_permissions(administrator=True)
async def aggiorna(interaction: discord.Interaction, id_messaggio: str, nuovo_testo: str = None, nuova_img: str = None):
    try:
        messaggio = await interaction.channel.fetch_message(int(id_messaggio))
        if not messaggio.embeds:
            return await interaction.response.send_message("❌ Nessun embed trovato!", ephemeral=True)

        embed = messaggio.embeds[0]
        if nuovo_testo: embed.description = nuovo_testo
        if nuova_img: embed.set_image(url=nuova_img)
            
        await messaggio.edit(embed=embed)
        await interaction.response.send_message("✅ Contenuto aggiornato!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)

# --- GESTORE ERRORI ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message("❌ Non hai i permessi di Amministratore!", ephemeral=True)

@bot.tree.command(name="lista_anonimi", description="Mostra la lista di tutti i nickname anonimi associati agli utenti")
async def lista_anonimi(interaction: discord.Interaction):
    # Controllo se l'utente è staff o admin per evitare che tutti vedano i nomi
    ID_RUOLO_STAFF =  1253460150141059198 # tuo ID ruolo staff
    is_staff = any(r.id == ID_RUOLO_STAFF for r in interaction.user.roles) or interaction.user.guild_permissions.administrator
    
    if not is_staff:
        return await interaction.response.send_message("❌ Non hai i permessi per vedere questa lista.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Recuperiamo tutti gli utenti registrati
        cur.execute("SELECT user_id, nickname FROM utenti_anonimi")
        rows = cur.fetchall()
        
        cur.close()
        conn.close()

        if not rows:
            return await interaction.followup.send("📭 Non ci sono utenti registrati nel database anonimo.", ephemeral=True)

        # Creiamo la stringa della tabella
        testo_lista = "## 📋 DATABASE IDENTITÀ ANONIME\n\n"
        for row in rows:
            user_mention = f"<@{row['user_id']}>"
            nickname = row['nickname']
            testo_lista += f"{user_mention} = **{nickname}**\n"

        # Creiamo un embed per renderlo più ordinato
        embed = discord.Embed(
            title="🕵️ Registro Alias Segreti",
            description=testo_lista,
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Accesso riservato allo Staff")

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"Errore lista_anonimi: {e}")
        await interaction.followup.send("❌ Errore nel recupero del database.", ephemeral=True)


@bot.tree.command(name="me", description="Esegui un'azione in gioco (Roleplay)")
@app_commands.describe(azione="Descrivi l'azione che stai compiendo")
async def me(interaction: discord.Interaction, azione: str):
    # Creazione dell'Embed con i parametri richiesti
    embed = discord.Embed(
        title="🎬 𝐀𝐳𝐢𝐨𝐧𝐞 🎦",
        description=f"{interaction.user.mention} : {azione}",
        color=discord.Color.from_rgb(170, 142, 214) # Un viola elegante per le azioni RP
    )
    
    # Invia il messaggio nel canale in cui è stato usato il comando
    await interaction.response.send_message(embed=embed)
# --- COMANDO SETUP WL (Solo Admin) ---
@bot.tree.command(name="setup_wl", description="[ADMIN] Configura il sistema WL")
@app_commands.describe(
    ruolo_passata="Ruolo per chi passa",
    ruolo_rifiutata="Ruolo per chi viene bocciato",
    ruolo_staff_display="Ruolo visualizzato nell'embed (es. @Responsabile)",
    ruolo_per_fare_esito="Il ruolo che lo staffer DEVE AVERE per usare il comando /esito-wl"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_wl(
    interaction: discord.Interaction, 
    ruolo_passata: discord.Role, 
    ruolo_rifiutata: discord.Role,
    ruolo_staff_display: discord.Role,
    ruolo_per_fare_esito: discord.Role
):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO wl_config (guild_id, ruolo_passata, ruolo_rifiutata, ruolo_staff, ruolo_abilitato_esito) 
        VALUES (%s, %s, %s, %s, %s) 
        ON CONFLICT (guild_id) DO UPDATE SET 
        ruolo_passata = EXCLUDED.ruolo_passata, 
        ruolo_rifiutata = EXCLUDED.ruolo_rifiutata,
        ruolo_staff = EXCLUDED.ruolo_staff,
        ruolo_abilitato_esito = EXCLUDED.ruolo_abilitato_esito
    """, (str(interaction.guild.id), str(ruolo_passata.id), str(ruolo_rifiutata.id), 
          str(ruolo_staff_display.id), str(ruolo_per_fare_esito.id)))
    conn.commit()
    cur.close(); conn.close()
    
    await interaction.response.send_message(f"✅ Configurazione WL salvata correttamente!", ephemeral=True)

# --- COMANDO ESITO WL ---
@bot.tree.command(name="esito-wl", description="Invia l'esito della Whitelist")
@app_commands.choices(esito=[
    app_commands.Choice(name="✅ Passata", value="accettato"),
    app_commands.Choice(name="❌ Rifiutata", value="rifiutato")
])
async def esito_wl(interaction: discord.Interaction, utente: discord.Member, esito: app_commands.Choice[str], errori: int):
    # --- CONFIGURAZIONE RUOLI FISSI ---
    RUOLO_STAFF_ID = 1253634976243646527
    
    # Ruoli da aggiungere se PASSATA
    RUOLI_PASSATA = [
        1346490158505263183, # Tutti
        1253463763471040550, # Approvad member
        1359878894840447066, # Disoccupato
        1278680093044113469, # No documentado
        1253752632820895817,
        1253460170969976925
    ]
    
    # Ruoli da rimuovere se PASSATA
    RUOLI_DA_RIMUOVERE = [
        1502380869938315284, # Landing
        1421433939574132746, # Bienvenido
        1421434530283126805,
        1253460158617620573
    ]

    # --- CONTROLLO PERMESSO STAFF ---
    ruolo_staff = interaction.guild.get_role(RUOLO_STAFF_ID)
    if ruolo_staff not in interaction.user.roles:
        return await interaction.response.send_message(
            f"❌ Non hai i permessi necessari ({ruolo_staff.mention}) per usare questo comando.", 
            ephemeral=True
        )

    await interaction.response.defer()

    # --- LOGICA DB (Mantenuta per ruoli dinamici se presenti) ---
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM wl_config WHERE guild_id = %s", (str(interaction.guild.id),))
    config = cur.fetchone()
    cur.close(); conn.close()

    # --- GESTIONE RUOLI UTENTE ---
    if esito.value == "accettato":
        # Aggiunta ruoli lista fissa + eventuale ruolo dal DB
        for r_id in RUOLI_PASSATA:
            r = interaction.guild.get_role(r_id)
            if r: await utente.add_roles(r)
        
        if config and config.get('ruolo_passata'):
            r_db = interaction.guild.get_role(int(config['ruolo_passata']))
            if r_db: await utente.add_roles(r_db)

        # Rimozione ruoli specificati
        for r_id in RUOLI_DA_RIMUOVERE:
            r = interaction.guild.get_role(r_id)
            if r: await utente.remove_roles(r)

    else:
        # Se rifiutato, aggiunge solo il ruolo rifiutato dal DB se configurato
        if config and config.get('ruolo_rifiutata'):
            r_fail = interaction.guild.get_role(int(config['ruolo_rifiutata']))
            if r_fail: await utente.add_roles(r_fail)

    # --- CREAZIONE ESTETICA EMBED ---
    color = discord.Color.green() if esito.value == "accettato" else discord.Color.red()
    emoji_status = "🟩" if esito.value == "accettato" else "🟥"
    
    display_staff_role = ruolo_staff.mention if ruolo_staff else "@Staffer"

    embed = discord.Embed(title=f"{emoji_status} | Approval notices", color=color)
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
    
    embed.add_field(name="Evrenians ❯❯", value=utente.mention, inline=False)
    embed.add_field(name="Esito ❯❯", value=f"**{esito.name}**", inline=True)
    embed.add_field(name="Errori ❯❯", value=f"**{errori}**", inline=True)
    embed.add_field(name="━━━━━━━━━━━━━━━━━━━━", value=" ", inline=False)
    embed.add_field(name=f"Da {display_staff_role} :", value=interaction.user.mention, inline=False)
    
    embed.set_footer(text=f"Evren City RP • {discord.utils.utcnow().strftime('%d/%m/%Y')}")

    await interaction.followup.send(content=utente.mention, embed=embed)

#A DM E COMANDO SLASH CON AUTOCOMPLETE ---

YOUR_USER_ID =  1191824316376043580 #Inserisci il tuo ID

# 1. Evento Notifica DM
@bot.event
async def on_guild_join(guild):
    user = await bot.fetch_user(YOUR_USER_ID)
    if user:
        link = "Nessun permesso per l'invito"
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).create_instant_invite:
                inv = await channel.create_invite(max_age=300)
                link = inv.url
                break
        await user.send(f"✅ **Nuovo Server**: {guild.name}\n🔗 **Link**: {link}")

# 2. Autocomplete per la lista dei server
async def server_autocomplete(interaction: discord.Interaction, current: str):
    # Mostra solo i server che contengono il testo scritto dall'utente
    return [
        discord.app_commands.Choice(name=guild.name, value=str(guild.id))
        for guild in bot.guilds
        if current.lower() in guild.name.lower()
    ][:25] # Massimo 25 suggerimenti consentiti da Discord

# 3. Comando Slash per uscire
@bot.tree.command(name="lascia_server", description="Fa uscire il bot da un server specifico")
@discord.app_commands.autocomplete(server_id=server_autocomplete)
async def lascia_server(interaction: discord.Interaction, server_id: str):
    # Controllo sicurezza: Solo tu puoi eseguire il comando
    if interaction.user.id != YOUR_USER_ID:
        return await interaction.response.send_message("❌ Non hai i permessi!", ephemeral=True)

    guild = bot.get_guild(int(server_id))
    if guild:
        await guild.leave()
        await interaction.response.send_message(f"✅ Ho lasciato il server: **{guild.name}**", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Server non trovato.", ephemeral=True)

# Ricordati di sincronizzare i comandi slash nel tuo evento on_ready:
# await bot.tree.sync()
import random

import random
import discord

import random
import discord

# --- COMANDO ADMIN: AGGIUNGI TRAMITE ALLEGATO ---
@bot.tree.command(name="peter_add", description="Aggiunge una GIF caricando un file (Solo Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def peter_add(interaction: discord.Interaction, file: discord.Attachment):
    # Controllo tipo file
    if not file.content_type or not any(x in file.content_type for x in ["image", "video"]):
        return await interaction.response.send_message("❌ Carica un file valido (GIF, PNG, MP4)!", ephemeral=True)

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            # Inseriamo l'URL dell'allegato nella tabella peter_gifs
            cur.execute("INSERT INTO peter_gifs (url) VALUES (%s)", (file.url,))
            conn.commit()
            cur.close()
            conn.close()
            await interaction.response.send_message(f"✅ GIF aggiunta al database PostgreSQL!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore database: {e}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Errore connessione al database!", ephemeral=True)


@bot.tree.command(name="petergriffin", description="Invia una gif casuale di Peter")
async def petergriffin(interaction: discord.Interaction):
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT url FROM peter_gifs")
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if not rows:
                return await interaction.response.send_message("⚠️ Il database è vuoto!", ephemeral=True)

            # Scegliamo l'URL dal database
            gif_url = random.choice(rows)[0]
            
            # Creiamo l'Embed
            embed = discord.Embed(color=discord.Color.from_rgb(255, 255, 255))
            
            # TRUCCO: Se l'URL è un link diretto del CDN di Discord, 
            # lo impostiamo come immagine dell'embed. 
            # Se il file è un formato compatibile, Discord nasconderà l'URL.
            embed.set_image(url=gif_url)
            embed.set_footer(text="Ringraziate Killer")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Errore connessione DB!", ephemeral=True)

# Ho inserito i tuoi link originali. 
@bot.tree.command(name="clear", description="Elimina un numero specifico di messaggi da questo canale")
@app_commands.describe(quantita="Numero di messaggi da eliminare (max 100)")
async def clear(interaction: discord.Interaction, quantita: int):
    # ID del ruolo autorizzato
    ID_RUOLO_AUTORIZZATO = 1253460150141059198
    
    # Controllo se l'utente ha il ruolo richiesto
    role = interaction.guild.get_role(RUOLO_STAFF_ID)
    if role not in interaction.user.roles:
        return await interaction.response.send_message(
            "❌ Non hai i permessi necessari (Staff) per usare questo comando.", 
            ephemeral=True
        )

    # Controllo che la quantità sia valida
    if quantita < 1 or quantita > 100:
        return await interaction.response.send_message(
            "⚠️ Puoi eliminare da 1 a 100 messaggi alla volta.", 
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    try:
        # Elimina i messaggi
        deleted = await interaction.channel.purge(limit=quantita)
        
        # Crea un embed di conferma
        embed = discord.Embed(
            description=f"✅ Pulizia completata: eliminati **{len(deleted)}** messaggi.",
            color=discord.Color.green()
        )
        
        # Invia la conferma (visibile solo a chi ha usato il comando)
        await interaction.followup.send(embed=embed)
        
    except discord.Forbidden:
        await interaction.followup.send("❌ Il bot non ha i permessi di 'Gestire i messaggi' in questo canale.", ephemeral=True)
    except Exception as e:
        print(f"Errore comando clear: {e}")
        await interaction.followup.send("❌ Si è verificato un errore durante la pulizia.", ephemeral=True)
# Sostituisci con l'ID reale del tuo ruolo Staff
 
import asyncio
import random

@bot.tree.command(name="scassina", description="Tenta di scassinare una serratura (10 secondi)")
async def scassina(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    item_nome = "Grimaldello"
    
    # 1. Controllo immediato dell'oggetto (senza defer per rispondere subito)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (user_id, item_nome))
    res = cur.fetchone()
    
    if not res or res[0] <= 0:
        cur.close(); conn.close()
        return await interaction.response.send_message(f"❌ Non hai un **{item_nome}**!", ephemeral=True)

    # 2. Risposta iniziale e inizio countdown
    await interaction.response.send_message(f"🛠️ {interaction.user.mention} ha iniziato a manomettere la serratura...")
    msg = await interaction.original_response()

    # --- FASE DI ATTESA (10 SECONDI) ---
    tempo_attesa = 10
    while tempo_attesa > 0:
        await asyncio.sleep(2) # Aggiorniamo ogni 2 secondi per non sovraccaricare Discord
        tempo_attesa -= 2
        if tempo_attesa > 0:
            await interaction.edit_original_response(content=f"🛠️ {interaction.user.mention} sta scassinando... `{tempo_attesa}s` rimanenti.")

    # 3. Fine attesa: Consumo oggetto e calcolo successo
    cur.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = %s", (user_id, item_nome))
    cur.execute("DELETE FROM inventory WHERE quantity <= 0")
    conn.commit()
    
    successo = random.random() < 0.60
    
    # 4. Embed finale
    embed = discord.Embed(
        title="Scassinamento eseguito",
        description=f"{interaction.user.mention} ha terminato il tentativo.",
        color=0xE91E63 if not successo else 0x2ECC71 # Rosa se fallisce, Verde se riesce
    )
    embed.set_thumbnail(url="https://i.imgur.com/8Nn3vC9.png")

    if successo:
        embed.add_field(name="Risultato:", value="✅ **SUCCESSO!** La serratura è stata forzata.", inline=False)
    else:
        embed.add_field(name="Risultato:", value="• **FALLITO!** Il grimaldello si è spezzato.\n• Hai consumato 1x Grimaldello", inline=False)

    embed.set_footer(text="Evren City RP - Sistema Sicurezza")
    
    # Modifica il messaggio finale trasformandolo nell'Embed del risultato
    await interaction.edit_original_response(content=None, embed=embed)
    
    cur.close()
    conn.close()


# --- 1. VIEW PER IL BACKGROUND (ESITO STAFF) ---
class BackgroundStaffView(discord.ui.View):
    def __init__(self, user_id=None, psn_id=None):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.psn_id = psn_id

    @discord.ui.button(label="ACCETTA", style=discord.ButtonStyle.success, emoji="✅", custom_id="bg_accept_fixed")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # Se il bot è stato riavviato, recuperiamo l'ID dal footer e il PSN dal campo specifico
        try:
            u_id = self.user_id or int(interaction.message.embeds[0].footer.text.split(": ")[1])
            # Cerchiamo il PSN ID nel secondo campo dell'embed (🎮 PSN ID)
            p_id = self.psn_id or interaction.message.embeds[0].fields[1].value.replace("`", "")
            
            member = await interaction.guild.fetch_member(u_id)
            
            # 1. Invio DM (Esito)
            embed_dm = discord.Embed(
                title="✅ Background Accettato!",
                description=f"Il tuo background per **Evren City** è stato approvato.\nIl tuo nick è stato impostato su: `{p_id}`.",
                color=discord.Color.green()
            )
            try: await member.send(embed=embed_dm)
            except: pass # DM Chiusi

            # 2. Cambio Nickname
            try: await member.edit(nick=p_id)
            except: pass # Permessi insufficienti

            await interaction.edit_original_response(content=f"✅ Accettato da {interaction.user.mention}", view=None)
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Errore: Utente non trovato o dati persi. ({e})", view=None)

    @discord.ui.button(label="RIFIUTA", style=discord.ButtonStyle.danger, emoji="❌", custom_id="bg_reject_fixed")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            u_id = self.user_id or int(interaction.message.embeds[0].footer.text.split(": ")[1])
            member = await interaction.guild.fetch_member(u_id)
            
            embed_dm = discord.Embed(
                title="❌ Background Rifiutato",
                description="Il tuo background non è stato approvato. Riprova seguendo meglio il regolamento.",
                color=discord.Color.red()
            )
            try: await member.send(embed=embed_dm)
            except: pass

            await interaction.edit_original_response(content=f"❌ Rifiutato da {interaction.user.mention}", view=None)
        except:
            await interaction.edit_original_response(content="❌ Errore nell'invio del rifiuto.", view=None)


# --- 3. COMANDO SETUP BACKGROUND (ADMIN) ---
@bot.tree.command(name="setup_background", description="[ADMIN] Configura il sistema Background")
@app_commands.checks.has_permissions(administrator=True)
async def setup_background(interaction: discord.Interaction, canale_staff: discord.TextChannel, ruolo_richiesto: discord.Role):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO background_config (guild_id, staff_channel_id, required_role_id) 
        VALUES (%s, %s, %s) 
        ON CONFLICT (guild_id) DO UPDATE SET 
        staff_channel_id = EXCLUDED.staff_channel_id, 
        required_role_id = EXCLUDED.required_role_id
    """, (str(interaction.guild.id), str(canale_staff.id), str(ruolo_richiesto.id)))
    conn.commit()
    cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Background configurato: {canale_staff.mention}", ephemeral=True)

# --- 4. COMANDO BACKGROUND (UTENTI) ---
@bot.tree.command(name="background", description="Invia il tuo background PG per la revisione")
@app_commands.describe(
    nome="Inserisci il tuo nome reale o di gioco",
    eta="Inserisci la tua età",
    psn_id="Il tuo ID PlayStation Network",
    esperienze="Descrivi le tue precedenti esperienze nel Roleplay",
    storia="Scrivi la storia dettagliata del tuo personaggio",
    paure="Quali sono le paure più grandi del tuo PG?",
    obiettivi="Quali sono gli obiettivi del tuo PG in città?",
    regolamento="Hai letto e accettato il regolamento del server?"
)
@app_commands.choices(regolamento=[
    app_commands.Choice(name="Sì, accetto il regolamento", value="Sì"),
    app_commands.Choice(name="No, non accetto il regolamento", value="No")
])
async def background(
    interaction: discord.Interaction, 
    nome: str, 
    eta: str, 
    psn_id: str, 
    esperienze: str, 
    storia: str, 
    paure: str, 
    obiettivi: str, 
    regolamento: str
):
    await interaction.response.defer(ephemeral=True)

    # Controllo immediato sul regolamento
    if regolamento == "No":
        return await interaction.followup.send("❌ Non puoi inviare il background se non accetti il regolamento.", ephemeral=True)

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM background_config WHERE guild_id = %s", (str(interaction.guild.id),))
    config = cur.fetchone()
    cur.close(); conn.close()

    if not config:
        return await interaction.followup.send("❌ Sistema non configurato dallo staff.", ephemeral=True)

    # Controllo Ruolo
    role_req = interaction.guild.get_role(int(config['required_role_id']))
    if role_req not in interaction.user.roles:
        return await interaction.followup.send(f"❌ Devi avere il ruolo {role_req.mention} per inviare il background!", ephemeral=True)

    # --- CREAZIONE EMBED ORDINATO ---
    embed = discord.Embed(
        title="📂 NUOVA RICHIESTA BACKGROUND",
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(name=f"{interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    
    # Sezione Info Personali
    embed.add_field(name="👤 Informazioni OOC", value=f"**Nome:** {nome}\n**Età:** {eta}\n**PSN ID:** `{psn_id}`", inline=False)
    
    # Sezione Esperienze
    embed.add_field(name="📚 Esperienze Roleplay", value=f"```{esperienze}```", inline=False)
    
    # Sezione Storia
    embed.add_field(name="📖 Storia del Personaggio", value=storia, inline=False)
    
    # Sezione Psicologia
    embed.add_field(name="😨 Paure", value=paure, inline=True)
    embed.add_field(name="🎯 Obiettivi", value=obiettivi, inline=True)
    
    # Sezione Regolamento (Dato che ora è una scelta Sì/No)
    embed.add_field(name="📜 Regolamento", value="✅ L'utente ha dichiarato di aver letto e accettato il regolamento.", inline=False)

    embed.set_footer(text=f"ID Utente: {interaction.user.id} • Sistema Background")
    embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)

    # Invio Staff
    staff_chan = interaction.guild.get_channel(int(config['staff_channel_id']))
    if staff_chan:
        # Tag dell'utente per notificare lo staff
        content_staff = f"🔔 **Nuovo background ricevuto da:** {interaction.user.mention}"
        
        view = BackgroundStaffView(user_id=interaction.user.id, psn_id=psn_id)
        await staff_chan.send(content=content_staff, embed=embed, view=view)
        
        # Invio copia DM all'utente
        try: 
            copy_embed = embed.copy()
            copy_embed.title = "📄 COPIA DEL TUO BACKGROUND"
            copy_embed.color = discord.Color.green()
            await interaction.user.send(content="**Ecco un riepilogo del background che hai inviato:**", embed=copy_embed)
        except: 
            pass

        await interaction.followup.send("✅ Background inviato correttamente! Lo staff lo revisionerà al più presto.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Errore critico: Canale staff non configurato.", ephemeral=True)

# --- COMANDI RP LEGA/SLEGA (SOLO TESTUALI) ---
@bot.tree.command(name="lega", description="Azione RP: Lega un utente")
async def lega(interaction: discord.Interaction, utente: discord.Member):
    embed = discord.Embed(description=f"⛓️ **{interaction.user.display_name}** ha legato **{utente.mention}**.", color=discord.Color.dark_gray())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="slega", description="Azione RP: Slega un utente")
async def slega(interaction: discord.Interaction, utente: discord.Member):
    embed = discord.Embed(description=f"🔓 **{interaction.user.display_name}** ha slegato **{utente.mention}**.", color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

# --- COMANDO STAFF: AGGIUNGI DROGA ---
@bot.tree.command(name="crea_droga", description="Configura una nuova droga (Solo Staff)")
@app_commands.describe(nome="Nome della droga", quantita="Quanti pezzi si raccolgono al minuto")
async def crea_droga(interaction: discord.Interaction, nome: str, quantita: int):
    # Controllo Ruolo Staff
    if not any(role.id == RUOLO_STAFF_ID for role in interaction.user.roles):
        return await interaction.response.send_message("❌ Non hai i permessi per usare questo comando.", ephemeral=True)

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO droghe_config (nome, quantita_al_minuto)
            VALUES (%s, %s)
            ON CONFLICT (nome) DO UPDATE SET quantita_al_minuto = EXCLUDED.quantita_al_minuto
        """, (nome.lower(), quantita))
        conn.commit()
        cur.close()
        conn.close()
        
        await interaction.response.send_message(f"✅ Droga **{nome}** configurata: {quantita} pezzi/minuto.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Errore DB: {e}", ephemeral=True)

# --- AUTOCOMPLETE PER IL COMANDO INIZIA ---
async def droga_autocomplete(interaction: discord.Interaction, current: str):
    conn = get_db_connection()
    cur = conn.cursor()
    # Cerca le droghe esistenti nella tabella droghe_config
    cur.execute("SELECT nome FROM droghe_config WHERE nome ILIKE %s LIMIT 25", (f'%{current}%',))
    choices = [app_commands.Choice(name=row[0].capitalize(), value=row[0]) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return choices

# --- COMANDO INIZIA RACCOLTA ---
@bot.tree.command(name="inizia_raccolta", description="Inizia la raccolta di una droga specifica")
@app_commands.autocomplete(cosa=droga_autocomplete)
async def inizia_raccolta(interaction: discord.Interaction, cosa: str):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifica se la droga scelta esiste effettivamente nella config
        cur.execute("SELECT nome FROM droghe_config WHERE nome = %s", (cosa,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return await interaction.followup.send("❌ Questa droga non è configurata. Usa una delle opzioni suggerite.", ephemeral=True)

        cur.execute("""
            INSERT INTO sessioni_raccolta (user_id, cosa_raccoglie, inizio_timestamp)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                cosa_raccoglie = EXCLUDED.cosa_raccoglie,
                inizio_timestamp = NOW()
        """, (str(interaction.user.id), cosa))
        
        conn.commit()
        cur.close()
        conn.close()
        
        embed = discord.Embed(title="🌿 RACCOLTA AVVIATA", color=discord.Color.blue())
        embed.description = f"Hai iniziato a raccogliere: **{cosa.capitalize()}**\nUsa `/finisci_raccolta` per terminare."
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Errore inizia_raccolta: {e}")
        await interaction.followup.send("❌ Errore tecnico nel database.", ephemeral=True)

# --- COMANDO FINISCI RACCOLTA ---
@bot.tree.command(name="finisci_raccolta", description="Termina la raccolta e ricevi i prodotti")
async def finisci_raccolta(interaction: discord.Interaction):
    await interaction.response.defer()
    
    try:
        conn = get_db_connection()
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Join tra sessione attiva e configurazione per calcolare il guadagno
        cur.execute("""
            SELECT s.cosa_raccoglie, d.quantita_al_minuto,
            EXTRACT(EPOCH FROM (NOW() - s.inizio_timestamp)) / 60 AS minuti
            FROM sessioni_raccolta s
            JOIN droghe_config d ON s.cosa_raccoglie = d.nome
            WHERE s.user_id = %s
        """, (str(interaction.user.id),))
        
        res = cur.fetchone()
        
        if not res:
            cur.close()
            conn.close()
            return await interaction.followup.send("❌ Non hai sessioni di raccolta attive.", ephemeral=True)

        minuti_passati = int(res['minuti'])
        quantita_guadagnata = minuti_passati * res['quantita_al_minuto']
        item = res['cosa_raccoglie']
        
        # 1. Elimina la sessione
        cur.execute("DELETE FROM sessioni_raccolta WHERE user_id = %s", (str(interaction.user.id),))
        
        # 2. Aggiungi all'inventario se ha raccolto almeno qualcosa
        if quantita_guadagnata > 0:
            cur.execute("""
                INSERT INTO inventory (user_id, item_name, quantity)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, item_name) DO UPDATE SET
                quantity = inventory.quantity + EXCLUDED.quantity
            """, (str(interaction.user.id), item, quantita_guadagnata))
        
        conn.commit()
        cur.close()
        conn.close()
        
        embed = discord.Embed(title="📦 RACCOLTA COMPLETATA", color=discord.Color.green())
        embed.add_field(name="Cittadino", value=interaction.user.mention, inline=True)
        embed.add_field(name="Prodotto", value=item.capitalize(), inline=True)
        embed.add_field(name="Tempo", value=f"{minuti_passati} minuti", inline=True)
        embed.add_field(name="Quantità Ricevuta", value=f"**x{quantita_guadagnata}**", inline=False)
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        print(f"Errore finisci_raccolta: {e}")
        await interaction.followup.send("❌ Errore nel processare la fine della raccolta.", ephemeral=True)


# --- COMANDO AGGIORNATO ---
@bot.tree.command(name="anonimo", description="Invia un messaggio criptato sulla rete segreta")
@app_commands.describe(
    messaggio="Il testo del messaggio segreto",
    nickname="Il tuo alias segreto (obbligatorio solo la prima volta o per cambiarlo)"
)
async def anonimo(interaction: discord.Interaction, messaggio: str, nickname: str = None):
    await interaction.response.defer(ephemeral=True)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT nickname FROM utenti_anonimi WHERE user_id = %s", (str(interaction.user.id),))
        res = cur.fetchone()
        
        if not res and not nickname:
            cur.close()
            conn.close()
            return await interaction.followup.send("❌ Devi specificare un `nickname` la prima volta!", ephemeral=True)
        
        alias_da_usare = nickname if nickname else res['nickname']
        
        if nickname:
            cur.execute("""
                INSERT INTO utenti_anonimi (user_id, nickname)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET nickname = EXCLUDED.nickname
            """, (str(interaction.user.id), nickname))
            conn.commit()
            
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
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Tracciamento IP: Fallito • Rete Anonima")
        
        # Invio e salvataggio ID messaggio per futura investigazione
        msg_inviato = await interaction.channel.send(embed=embed)
        
        # Logghiamo il legame tra messaggio e utente nel DB
        cur.execute("INSERT INTO messaggi_anonimi (message_id, user_id) VALUES (%s, %s)", 
                    (str(msg_inviato.id), str(interaction.user.id)))
        conn.commit()
            
        cur.close()
        conn.close()
        
        await interaction.followup.send("✅ Messaggio inviato in totale anonimato.", ephemeral=True)

    except Exception as e:
        print(f"Errore anonimo: {e}")
        await interaction.followup.send("❌ Errore critico nel sistema di criptazione.", ephemeral=True)


@bot.event
async def on_raw_reaction_add(payload):
    # 1. Configurazione ID Ruolo Staff
    ID_RUOLO_STAFF = 1253460150141059198
     
    
    # 2. Filtro: solo l'emoji corretta e non il bot stesso
    if str(payload.emoji) != "❓" or payload.user_id == bot.user.id:
        return

    # 3. Recupero Server e Membro
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    member = guild.get_member(payload.user_id)
    if not member: return

    # 4. Controllo Permessi Staff
    is_staff = any(r.id == ID_RUOLO_STAFF for r in member.roles) or member.guild_permissions.administrator

    if is_staff:
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT user_id FROM messaggi_anonimi WHERE message_id = %s", (str(payload.message_id),))
            res = cur.fetchone()
            
            if res:
                utente_id = int(res['user_id'])
                utente = await bot.fetch_user(utente_id)
                
                # Invio il DM allo staffer
                info_embed = discord.Embed(title="🔍 Identità Svelata", color=discord.Color.red())
                info_embed.add_field(name="Messaggio ID", value=f"`{payload.message_id}`", inline=False)
                info_embed.add_field(name="Autore", value=f"{utente.mention} ({utente.name})", inline=True)
                info_embed.add_field(name="ID Utente", value=f"`{utente_id}`", inline=True)
                
                await member.send(embed=info_embed)

                # --- RIMOZIONE REAZIONE (Il punto critico) ---
                channel = bot.get_channel(payload.channel_id)
                if channel:
                    # Usiamo fetch_message perché il messaggio potrebbe non essere in cache
                    msg = await channel.fetch_message(payload.message_id)
                    await msg.remove_reaction(payload.emoji, member)
            
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Errore durante la rimozione o l'invio DM: {e}")


# --- VIEW PER IL BOTTONE DI VERIFICA ---
# Questa classe gestisce il comportamento del bottone dopo che è stato #
import discord
from discord import app_commands
import datetime

# --- CLASSE VIEW PERSISTENTE AGGIORNATA ---
class VerificaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verificati", 
        style=discord.ButtonStyle.success, 
        custom_id="btn_verifica_universale"
    )
    # Aggiungi "button" tra gli argomenti qui sotto:
    async def verifica_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        ID_RUOLO_DA_TOGLIERE = 1254059448771809341
        ID_RUOLO_DA_AGGIUNGERE = 1502380869938315284
        
        try:
            ruolo_vecchio = interaction.guild.get_role(ID_RUOLO_DA_TOGLIERE)
            ruolo_nuovo = interaction.guild.get_role(ID_RUOLO_DA_AGGIUNGERE)
            
            if ruolo_nuovo:
                await interaction.user.add_roles(ruolo_nuovo)
            
            if ruolo_vecchio and ruolo_vecchio in interaction.user.roles:
                await interaction.user.remove_roles(ruolo_vecchio)
                
            await interaction.followup.send("✅ Verifica completata!", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Errore: {e}", ephemeral=True)

import os
import discord
from discord import app_commands

@bot.tree.command(name="rpon", description="Segnala che l'RP è ONLINE")
@app_commands.checks.has_role(1253707509399683202)
@app_commands.describe(psn_id="Inserisci il tuo ID PlayStation Network")
async def rpon(interaction: discord.Interaction, psn_id: str):
    # Risposta immediata per evitare che il comando scada durante il caricamento del file
    await interaction.response.defer()
    
    try:
        # Recupera il percorso della cartella in cui si trova questo file di script (.py)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        nome_file = "61C2B877-EED6-4FFB-A7AA-363D91B1F49D.png"
        
        # Unisce la cartella dello script con il nome del file per trovarlo nella repository
        percorso_file = os.path.join(base_dir, nome_file)

        # Verifica se il file esiste nella repository prima di procedere
        if not os.path.exists(percorso_file):
            await interaction.followup.send(f"❌ Errore: Il file `{nome_file}` non è stato trovato nella repository.")
            return

        # Prepara il file per l'invio su Discord
        file_immagine = discord.File(percorso_file, filename=nome_file)

        # Creazione dell'embed con focus su Status, Utente e PSN
        embed = discord.Embed(
            title="Server Status",
            description=f"***Roleplay On da :*** {interaction.user.mention}",
            color=discord.Color.blue()
        )
        
        # Campo dedicato all'ID PSN
        embed.add_field(name="🎮 ID PSN", value=f"**{psn_id}**", inline=False)
        
        # Footer opzionale per dare un tocco professionale
        embed.set_footer(text="Evren City RP • Sessione Aperta")
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        # Imposta l'immagine dell'embed usando il file allegato preso dalla repository
        embed.set_image(url=f"attachment://{nome_file}")

        # Invia l'embed con il file immagine allegato usando followup (necessario dopo il defer)
        await interaction.followup.send(embed=embed, file=file_immagine)

    except Exception as e:
        # Gestione errori in caso di problemi di permessi o file mancanti
        await interaction.followup.send(f"❌ Si è verificato un errore: {e}")

import os
import discord
from discord import app_commands

@bot.tree.command(name="sondaggio", description="Crea un sondaggio per l'orario dell'RP")
@app_commands.describe(ora="Inserisci l'orario (es. 21:30)")
@app_commands.checks.has_role(1253707509399683202)
async def sondaggio(interaction: discord.Interaction, ora: str):
    # Risposta immediata per confermare la ricezione del comando
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Recupera il percorso della cartella in cui si trova questo file di script (.py)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        nome_file = "A952433E-3432-46B5-9200-1E2FB62E4231.png"
        
        # Unisce la cartella dello script con il nome del file per trovarlo nella repository
        percorso_file = os.path.join(base_dir, nome_file)

        # Verifica se il file esiste effettivamente nella repository prima di procedere
        if not os.path.exists(percorso_file):
            await interaction.followup.send(f"❌ Errore: Il file `{nome_file}` non è stato trovato nella repository.")
            return

        # Prepara il file per l'invio su Discord
        file_immagine = discord.File(percorso_file, filename=nome_file)

        # 1. Creazione dell'Embed per il canale
        embed = discord.Embed(
            title="🏙️ EVREN CITY RP - SESSIONE PROGRAMMATA",
            description=f"È stata pianificata una nuova sessione!\n\n"
                        f"⏰ Orario: **{ora}**\n"
                        f"📍 Canale: {interaction.channel.mention}\n\n"
                        "Confermate la vostra presenza tramite le reazioni qui sotto:",
            color=discord.Color.gold()
        )
        embed.add_field(name="✅ Si", value="Presente", inline=True)
        embed.add_field(name="❌ No", value="Assente", inline=True)
        embed.add_field(name="🕒 Ritardo", value="In ritardo", inline=True)
        embed.set_footer(text="Evren City RP Staff")
        
        # Imposta l'immagine dell'embed usando il file allegato
        embed.set_image(url=f"attachment://{nome_file}")
        
        # 2. Invio del messaggio nel canale con menzione @everyone e il file preso dalla repository
        messaggio = await interaction.channel.send(content="@everyone", embed=embed, file=file_immagine)
        
        # 3. Aggiunta delle reazioni per il voto
        await messaggio.add_reaction("✅")
        await messaggio.add_reaction("❌")
        await messaggio.add_reaction("🕒")

        # Messaggio di conferma visibile solo a chi ha eseguito il comando
        await interaction.followup.send("✅ Sondaggio creato con successo nel canale!")

    except Exception as e:
        # Gestione errori in caso di problemi di permessi o altro
        await interaction.followup.send(f"❌ Si è verificato un errore: {e}")
import os
import discord
from discord import app_commands

# --- COMANDO RP OFF ---
@bot.tree.command(name="rpoff", description="Segnala che l'RP è OFFLINE")
@app_commands.checks.has_role(1253707509399683202)
async def rpoff(interaction: discord.Interaction):
    # Risposta immediata per evitare il timeout di Discord durante il caricamento del file
    await interaction.response.defer()
    
    try:
        # Recupera il percorso della cartella della repository
        base_dir = os.path.dirname(os.path.abspath(__file__))
        nome_file = "AF86A47D-A6D1-4512-94EC-E87BFDDFFCD4.png"
        percorso_file = os.path.join(base_dir, nome_file)

        # Verifica se il file esiste nella repository prima di procedere
        if not os.path.exists(percorso_file):
            await interaction.followup.send(f"❌ Errore: Il file `{nome_file}` non è stato trovato nella repository.")
            return

        # Prepara il file per l'invio su Discord
        file_immagine = discord.File(percorso_file, filename=nome_file)

        # Creazione dell'embed
        embed = discord.Embed(
            title="🔴 RP OFFLINE",
            description="La sessione di Roleplay è terminata. Grazie a tutti per aver partecipato!",
            color=discord.Color.red()
        )
        
        # Imposta l'immagine dell'embed usando il file preso dalla repository
        embed.set_image(url=f"attachment://{nome_file}")

        # Invia l'embed con il file immagine allegato
        await interaction.followup.send(embed=embed, file=file_immagine)

    except Exception as e:
        # Gestione errori in caso di problemi imprevisti
        await interaction.followup.send(f"❌ Si è verificato un errore: {e}")

from discord import app_commands

# --- GESTORE ERRORI GLOBALE PER I COMANDI SLASH ---
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Controlla se l'errore è dovuto alla mancanza di un ruolo
    if isinstance(error, app_commands.MissingRole) or isinstance(error, app_commands.MissingAnyRole):
        # Messaggio personalizzato se l'utente non ha il ruolo
        return await interaction.response.send_message(
            content=f"❌ **Accesso Negato**: Non hai i permessi necessari (Staff) per usare questo comando.",
            ephemeral=True
        )
    
    # Gestione di altri tipi di errori (opzionale)
    elif isinstance(error, app_commands.CommandOnCooldown):
        return await interaction.response.send_message(
            content=f"⏳ Comando in cooldown. Riprova tra {error.retry_after:.1f} secondi.",
            ephemeral=True
        )
    
    # Se è un errore imprevisto, stampalo nei log del bot
    else:
        print(f"[LOG ERROR] Errore imprevisto: {error}")
        # Se l'interazione non ha ancora ricevuto risposta, inviane una di cortesia
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Si è verificato un errore imprevisto durante l'esecuzione del comando.", ephemeral=True)

@bot.tree.command(name="portafoglio", description="Visualizza i contanti nel wallet")
async def portafoglio(interaction: discord.Interaction):
    # 1. Diciamo subito a Discord di attendere (impedisce il crash dopo 3 secondi)
    await interaction.response.defer(ephemeral=False)
    
    try:
        # Recupero dei dati dal database
        u = get_user_data(interaction.user.id)
        
        # Assicuriamoci che se per qualche errore è negativo, mostri almeno 0 a video
        saldo = max(0, u['wallet'])
        
        embed = discord.Embed(
            title="💵 PORTAFOGLIO PERSONALE",
            description=f"Al momento porti con te:\n## **{saldo:,}$**",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        # 2. Usiamo followup per inviare la risposta finale
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"❌ Errore nel comando portafoglio: {e}")
        # In caso di errore invia un messaggio di avviso pulito
        await interaction.followup.send("❌ Si è verificato un errore nel recupero del tuo portafoglio.", ephemeral=True)

@bot.tree.command(name="conto", description="Visualizza il tuo saldo in banca")
async def conto(interaction: discord.Interaction):
    RUOLO_BANCA_ID = 1374264699331543140
    if not any(r.id == RUOLO_BANCA_ID for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Non hai un conto aperto.", ephemeral=True)

    u = get_user_data(interaction.user.id)
    saldo_banca = max(0, u['bank'])
    
    embed = discord.Embed(
        title="💳 CONTO BANCARIO",
        description=f"Saldo disponibile:\n## **{saldo_banca:,}$**",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# --- MODAL PER MODIFICA STIPENDIO ---
class ModificaStipendioModal(discord.ui.Modal, title="Modifica Stipendio Turno"):
    nuovo_importo = discord.ui.TextInput(label="Nuovo Totale (€)", placeholder="Inserisci la cifra corretta...")

    def __init__(self, user_id, ore, ruolo_nome):
        super().__init__()
        self.user_id = user_id
        self.ore = ore
        self.ruolo_nome = ruolo_nome

    async def on_submit(self, interaction: discord.Interaction):
        try:
            valore = int(self.nuovo_importo.value)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE users SET bank = bank + %s, ore_lavorate = ore_lavorate + %s 
                WHERE user_id = %s
            """, (valore, self.ore, str(self.user_id)))
            conn.commit()
            cur.close(); conn.close()
            
            await interaction.response.edit_message(
                content=f"✍️ **STIPENDIO MODIFICATO**: Accreditati **{valore}€** a <@{self.user_id}> (Ruolo: {self.ruolo_nome}).", 
                embed=None, view=None
            )
        except ValueError:
            await interaction.response.send_message("❌ Inserisci un numero valido!", ephemeral=True)

# --- VIEW PER LO STAFF (Persistente) ---
class TurnoStaffView(discord.ui.View):
    def __init__(self):
        # Fondamentale per la persistenza
        super().__init__(timeout=None)

    def parse_data_from_embed(self, embed):
        """Estrae i dati dal footer dell'embed dello staff"""
        try:
            footer = embed.footer.text
            parts = footer.split(" | ")
            return {
                "user_id": int(parts[0].replace("ID: ", "")),
                "stipendio": int(parts[1].replace("Stipendio: ", "")),
                "ore": float(parts[2].replace("Ore: ", "")),
                "ruolo": parts[3].replace("Ruolo: ", "")
            }
        except Exception:
            return None

    @discord.ui.button(label="Approva", style=discord.ButtonStyle.success, custom_id="turno_staff_approva")
    async def approva_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        d = self.parse_data_from_embed(interaction.message.embeds[0])
        if not d: 
            return await interaction.response.send_message("❌ Errore critico: Dati non trovati nell'embed.", ephemeral=True)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET bank = bank + %s, ore_lavorate = ore_lavorate + %s WHERE user_id = %s", 
                   (d['stipendio'], d['ore'], str(d['user_id'])))
        conn.commit()
        cur.close(); conn.close()
        
        await interaction.response.edit_message(content=f"✅ **APPROVATO**: {d['stipendio']}€ accreditati a <@{d['user_id']}>.", embed=None, view=None)

    @discord.ui.button(label="Rifiuta", style=discord.ButtonStyle.danger, custom_id="turno_staff_rifiuta")
    async def rifiuta_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ **RIFIUTATO**: Richiesta di stipendio annullata.", embed=None, view=None)

    @discord.ui.button(label="Modifica Importo", style=discord.ButtonStyle.secondary, custom_id="turno_staff_modifica")
    async def modifica_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        d = self.parse_data_from_embed(interaction.message.embeds[0])
        if not d: 
            return await interaction.response.send_message("❌ Errore recupero dati.", ephemeral=True)
        
        await interaction.response.send_modal(ModificaStipendioModal(d['user_id'], d['ore'], d['ruolo']))
@bot.tree.command(name="finisci_turno", description="Termina il turno e richiedi stipendio")
async def finisci_turno(interaction: discord.Interaction):
    await interaction.response.defer()
    
    conn = get_db_connection()
    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Recupero turno
    cur.execute("""
        SELECT *, EXTRACT(EPOCH FROM (NOW() - inizio)) / 3600 AS ore 
        FROM turni WHERE user_id = %s
    """, (str(interaction.user.id),))
    turno = cur.fetchone()
    
    if not turno:
        cur.close(); conn.close()
        return await interaction.followup.send("❌ Non hai un turno attivo da terminare.")

    # Parsing dati
    try:
        dati = turno['ruolo'].split('|')
        nome_ruolo = dati[0]
        paga_h = int(dati[1])
    except (IndexError, ValueError):
        cur.close(); conn.close()
        return await interaction.followup.send("❌ Errore nei dati del ruolo.")

    ore_lavorate = round(float(turno['ore']), 2)
    stipendio = int(ore_lavorate * paga_h)
    
    # Pulizia Turno
    cur.execute("DELETE FROM turni WHERE user_id = %s", (str(interaction.user.id),))
    conn.commit()
    cur.close(); conn.close()

    # Messaggio Utente
    await interaction.followup.send(f"🏁 Turno terminato! Hai lavorato `{ore_lavorate} ore`. Richiesta di **{stipendio}€** inviata allo staff.")

    # Invio allo STAFF
    ID_CANALE_STAFF = 1459566404100686009 
    canale_staff = interaction.guild.get_channel(ID_CANALE_STAFF) or await interaction.guild.fetch_channel(ID_CANALE_STAFF)

    if canale_staff:
        embed_s = discord.Embed(title="💼 RICHIESTA STIPENDIO", color=discord.Color.blue())
        embed_s.add_field(name="Utente", value=interaction.user.mention, inline=True)
        embed_s.add_field(name="Ruolo", value=nome_ruolo, inline=True)
        embed_s.add_field(name="Ore Totali", value=f"{ore_lavorate}h", inline=True)
        embed_s.add_field(name="Stipendio Calcolato", value=f"**{stipendio}€**", inline=False)
        
        # --- CRUCIALE: Scriviamo i dati nel footer ---
        embed_s.set_footer(text=f"ID: {interaction.user.id} | Stipendio: {stipendio} | Ore: {ore_lavorate} | Ruolo: {nome_ruolo}")
        
        # Chiamata corretta senza argomenti (li prenderà dall'embed al click)
        await canale_staff.send(embed=embed_s, view=TurnoStaffView())
@bot.tree.command(name="inizia_turno", description="Inizia il turno di lavoro")
async def inizia_turno(interaction: discord.Interaction, ruolo: discord.Role, paga_oraria: int):
    await interaction.response.defer()
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Inserisce il turno o lo aggiorna se l'utente ne ha già uno attivo
    cur.execute("""
        INSERT INTO turni (user_id, inizio, ruolo) 
        VALUES (%s, NOW(), %s) 
        ON CONFLICT (user_id) 
        DO UPDATE SET inizio = NOW(), ruolo = EXCLUDED.ruolo
    """, (str(interaction.user.id), f"{ruolo.name}|{paga_oraria}"))
    
    conn.commit()
    cur.close()
    conn.close()
    
    embed = discord.Embed(title="🛠️ TURNO INIZIATO", color=discord.Color.green())
    embed.add_field(name="Ruolo", value=ruolo.mention)
    embed.add_field(name="Paga", value=f"{paga_oraria}€/h")
    
    await interaction.followup.send(embed=embed)


class WipeConfirmView(discord.ui.View):
    def __init__(self, original_interaction):
        super().__init__(timeout=30)
        self.original_interaction = original_interaction

    @discord.ui.button(label="CONFERMA WIPE TOTALE", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica di sicurezza aggiuntiva sul bottone
        is_owner = await bot.is_owner(interaction.user)
        is_guild_owner = interaction.user == interaction.guild.owner
        
        if not (is_owner or is_guild_owner):
            return await interaction.response.send_message("❌ Non sei autorizzato a confermare questa azione.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Elenco di tutte le tabelle da svuotare (TRUNCATE le svuota all'istante)
            tabelle = [
                "users", "inventory", "items", "ricette", "veicoli", 
                "documenti", "fatture", "multe", "arresti", "depositi", 
                "depositi_items", "turni", "sessioni_raccolta"
            ]
            
            # Eseguiamo il reset
            query = f"TRUNCATE TABLE {', '.join(tabelle)} RESTART IDENTITY CASCADE;"
            cur.execute(query)
            
            conn.commit()
            await interaction.followup.send("✅ **WIPE COMPLETATO.** Il database è stato resettato correttamente.", ephemeral=True)
            
            # Log opzionale nel canale log se lo hai configurato
            # await send_log("⚠️ WIPE TOTALE eseguito da " + interaction.user.name)

        except Exception as e:
            await interaction.followup.send(f"❌ Errore durante il wipe: `{e}`", ephemeral=True)
        finally:
            if conn: cur.close(); conn.close()

    @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Operazione annullata.", view=None)

@bot.tree.command(name="wipe_totale", description="ELIMINA TUTTI I DATI (Solo Owner)")
async def wipe_totale(interaction: discord.Interaction):
    # 1. Controllo se è il proprietario del bot o del server
    is_owner = await bot.is_owner(interaction.user)
    is_guild_owner = interaction.user == interaction.guild.owner

    if not (is_owner or is_guild_owner):
        return await interaction.response.send_message("⛔ Solo il proprietario del server o del bot può eseguire questa azione!", ephemeral=True)

    # 2. Messaggio di avvertimento con bottone
    embed = discord.Embed(
        title="⚠️ ATTENZIONE: WIPE TOTALE",
        description=(
            "Stai per eliminare **TUTTI** i dati del server:\n"
            "• Account utenti (Banca e Portafoglio)\n"
            "• Inventari e Veicoli\n"
            "• Catalogo Shop e Ricette\n"
            "• Documenti, Fatture e Multe\n\n"
            "**Questa azione è irreversibile.** Vuoi procedere?"
        ),
        color=discord.Color.red()
    )
    
    view = WipeConfirmView(interaction)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --- COMANDO PER ELIMINARE IL DOCUMENTO (SOLO ADMIN) ---
@bot.tree.command(name="elimina_documento", description="Elimina il documento di un cittadino (Solo Staff)")
@app_commands.describe(cittadino="Il cittadino a cui vuoi cancellare il documento")
async def elimina_documento(interaction: discord.Interaction, cittadino: discord.Member):
    # Controllo se l'utente ha il ruolo richiesto
    if not any(role.id == RUOLO_STAFF_ID for role in interaction.user.roles):
        return await interaction.response.send_message(
            "❌ Non hai i permessi necessari (Ruolo Staff richiesto) per usare questo comando.", 
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Verifichiamo prima se il documento esiste
        cur.execute("SELECT nome, cognome FROM documenti WHERE user_id = %s", (str(cittadino.id),))
        result = cur.fetchone()
        
        if not result:
            cur.close()
            conn.close()
            return await interaction.followup.send(f"❌ Nessun documento trovato per {cittadino.display_name}.", ephemeral=True)
        
        # Eliminazione fisica dalla tabella
        cur.execute("DELETE FROM documenti WHERE user_id = %s", (str(cittadino.id),))
        
        conn.commit()
        cur.close()
        conn.close()
        
        await interaction.followup.send(
            f"✅ Documento di **{result[0]} {result[1]}** ({cittadino.display_name}) eliminato permanentemente dal database.", 
            ephemeral=True
        )
        
    except Exception as e:
        print(f"ERRORE ELIMINAZIONE DOCUMENTO: {e}")
        await interaction.followup.send("❌ Errore tecnico durante l'eliminazione.", ephemeral=True)
        
        
        
# --- CLASSE VIEW PER IL CRAFTING ---
class CraftingView(discord.ui.View):
    def __init__(self, item_risultato, materiali_dict, user_id):
        super().__init__(timeout=None)
        self.item_risultato = item_risultato
        self.materiali_dict = materiali_dict
        self.user_id = user_id

    @discord.ui.button(label="Inizia Crafting (1m)", style=discord.ButtonStyle.success, emoji="🔨")
    async def inizia_craft(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            return await interaction.response.send_message("❌ Questo banco da lavoro non è tuo.", ephemeral=True)

        user_id = self.user_id
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. Verifica disponibilità materiali
        for mat, qta in self.materiali_dict.items():
            cur.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name ILIKE %s", (user_id, mat))
            res = cur.fetchone()
            if not res or res[0] < qta:
                cur.close(); conn.close()
                return await interaction.response.send_message(f"❌ Ti mancano dei materiali: **{mat}**.", ephemeral=True)

        # 2. Avvio processo
        button.disabled = True
        button.label = "🔨 Lavorazione..."
        await interaction.response.edit_message(view=self)

        # 3. Timer di 60 secondi
        tempo_rimanente = 60
        while tempo_rimanente > 0:
            await asyncio.sleep(10)
            tempo_rimanente -= 10
            if tempo_rimanente > 0:
                try:
                    await interaction.edit_original_response(content=f"🔨 Stai assemblando **{self.item_risultato}**... `{tempo_rimanente}s` al termine.")
                except: break

        # 4. Conclusione
        try:
            for mat, qta in self.materiali_dict.items():
                cur.execute("UPDATE inventory SET quantity = quantity - %s WHERE user_id = %s AND item_name ILIKE %s", (qta, user_id, mat))
            
            cur.execute("""
                INSERT INTO inventory (user_id, item_name, quantity) VALUES (%s, %s, 1) 
                ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + 1
            """, (user_id, self.item_risultato))
            
            cur.execute("DELETE FROM inventory WHERE quantity <= 0")
            conn.commit()

            await interaction.edit_original_response(content=f"✅ **CRAFTING COMPLETATO!**\nHai ottenuto: **{self.item_risultato}**.", view=None, embed=None)
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Errore DB: {e}", view=None)
        finally:
            cur.close(); conn.close()

# --- FUNZIONE AUTOCOMPLETE ---
async def ricette_autocomplete(interaction: discord.Interaction, current: str):
    conn = get_db_connection()
    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT item_risultato FROM ricette WHERE item_risultato ILIKE %s LIMIT 25", (f'%{current}%',))
    ricette = cur.fetchall()
    cur.close(); conn.close()
    return [app_commands.Choice(name=r['item_risultato'].title(), value=r['item_risultato']) for r in ricette]

# --- COMANDO STAFF: SET RICETTA ---
@bot.tree.command(name="set_ricetta", description="[STAFF] Crea o modifica una ricetta di crafting")
@app_commands.describe(item_finale="Nome dell'oggetto finale", materiali="Esempio: Ferro:3,Legno:2")
@app_commands.checks.has_role(RUOLO_STAFF_ID)
async def set_ricetta(interaction: discord.Interaction, item_finale: str, materiali: str):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ricette (item_risultato, materiali) 
            VALUES (%s, %s) 
            ON CONFLICT (item_risultato) DO UPDATE SET materiali = EXCLUDED.materiali
        """, (item_finale.lower(), materiali))
        conn.commit()
        cur.close(); conn.close()
        await interaction.response.send_message(f"✅ Ricetta per **{item_finale}** salvata correttamente.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)

# --- COMANDO UTENTE: CRAFTA ---
@bot.tree.command(name="crafta", description="Apri il banco da lavoro per costruire un oggetto")
@app_commands.describe(item="Oggetto da costruire")
@app_commands.autocomplete(item=ricette_autocomplete)
async def crafta(interaction: discord.Interaction, item: str):
    conn = get_db_connection()
    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM ricette WHERE item_risultato = %s", (item.lower(),))
    ricetta = cur.fetchone()
    cur.close(); conn.close()

    if not ricetta:
        return await interaction.response.send_message("❌ Questo oggetto non è craftabile.", ephemeral=True)

    materiali_dict = {}
    testo_materiali = ""
    for m in ricetta['materiali'].split(','):
        nome, qta = m.split(':')
        materiali_dict[nome.strip()] = int(qta)
        testo_materiali += f"• **{nome.strip()}**: x{qta}\n"

    embed = discord.Embed(
        title=f"🛠️ Banco da Lavoro: {item.title()}",
        description=f"Per procedere sono necessari i seguenti materiali:\n\n{testo_materiali}\n*Tempo richiesto: 60 secondi.*",
        color=0x2C3E50
    )

    view = CraftingView(item.title(), materiali_dict, str(interaction.user.id))
    await interaction.response.send_message(embed=embed, view=view)

# --- GESTORE ERRORE RUOLO ---
@set_ricetta.error
async def set_ricetta_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("❌ Solo lo Staff può gestire le ricette.", ephemeral=True)

POLIZIA_ROLE_ID = 1363487988570521670

# --- FUNZIONE DI CONTROLLO POLIZIA ---
def is_polizia(interaction: discord.Interaction):
    return any(role.id == POLIZIA_ROLE_ID for role in interaction.user.roles)
# Sostituisci con l'ID reale del ruolo Polizia


# --- COMANDI FISICI: AMMANETTA, SMANETTA, ARRESTO ---
@bot.tree.command(name="ammanetta", description="Metti le manette a un cittadino")
async def ammanetta(interaction: discord.Interaction, utente: discord.Member):
    if not is_polizia(interaction):
        return await interaction.response.send_message("❌ Solo la Polizia può usare le manette.", ephemeral=True)
    await interaction.response.send_message(f"🔗 **{interaction.user.display_name}** ha ammanettato **{utente.display_name}**.")

@bot.tree.command(name="smanetta", description="Togli le manette a un cittadino")
async def smanetta(interaction: discord.Interaction, utente: discord.Member):
    if not is_polizia(interaction):
        return await interaction.response.send_message("❌ Non hai le chiavi delle manette.", ephemeral=True)
    await interaction.response.send_message(f"🔓 **{interaction.user.display_name}** ha rimosso le manette a **{utente.display_name}**.")@bot.tree.command(name="arresto", description="Porta un cittadino in cella e registra l'arresto")
async def arresto(interaction: discord.Interaction, utente: discord.Member, tempo_minuti: int, motivo: str):
    if not is_polizia(interaction):
        return await interaction.response.send_message("❌ Non sei un agente.", ephemeral=True)
    
    await interaction.response.defer()
    data_attuale = datetime.datetime.now().strftime("%d/%m/%Y")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO arresti (user_id, agente_id, motivo, tempo, data)
            VALUES (%s, %s, %s, %s, %s)
        """, (str(utente.id), str(interaction.user.id), motivo, tempo_minuti, data_attuale))
        conn.commit()
        cur.close()
        conn.close()

        embed = discord.Embed(title="⚖️ Verbale di Arresto", color=discord.Color.dark_blue())
        embed.add_field(name="Detenuto", value=utente.mention, inline=True)
        embed.add_field(name="Tempo", value=f"{tempo_minuti} minuti", inline=True)
        embed.add_field(name="Agente", value=interaction.user.mention, inline=False)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"Errore arresto: {e}")
        await interaction.followup.send("❌ Errore nel salvataggio dell'arresto.")
# --- CLASSE PER IL MENU DI SCELTA CITTADINO ---
class CitizenSelect(discord.ui.Select):
    def __init__(self, options, original_interaction):
        super().__init__(placeholder="Seleziona il cittadino corretto...", options=options)
        self.original_interaction = original_interaction

    async def callback(self, interaction: discord.Interaction):
        # Quando l'utente seleziona qualcuno dal menu, richiamiamo la visualizzazione del fascicolo
        await interaction.response.defer()
        target_id = self.values[0]
        # Funzione helper per mostrare il fascicolo (definita sotto)
        await mostra_fascicolo(interaction, target_id, self.original_interaction)

class CitizenView(discord.ui.View):
    def __init__(self, options, original_interaction):
        super().__init__(timeout=60)
        self.add_item(CitizenSelect(options, original_interaction))





# ================= COMANDI INVENTARIO =================

@bot.tree.command(name="inventario", description="Mostra i tuoi oggetti")
async def inventario(interaction: Interaction):
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT item_name, quantity FROM inventory WHERE user_id = %s", (str(interaction.user.id),))
    items = cur.fetchall()
    cur.close(); conn.close()
    emb = discord.Embed(title=f"🎒 Zaino di {interaction.user.display_name}", color=discord.Color.blue())
    desc = "\n".join([f"📦 **{i['item_name']}** x{i['quantity']}" for i in items]) if items else "*Vuoto.*"
    emb.description = desc
    await interaction.followup.send(embed=emb)

# --- FUNZIONE AUTOCOMPLETE (Suggerimenti dinamici) ---
async def inventory_autocomplete(interaction: discord.Interaction, current: str):
    """Suggerisce all'utente solo gli oggetti che possiede realmente nel DB"""
    conn = get_db_connection()
    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Cerca gli item dell'utente filtrando per quello che sta scrivendo (case-insensitive)
    cur.execute("""
        SELECT item_name 
        FROM inventory 
        WHERE user_id = %s AND item_name ILIKE %s 
        LIMIT 25
    """, (str(interaction.user.id), f'%{current}%'))
    
    items = cur.fetchall()
    cur.close()
    conn.close()
    
    # Genera la lista di scelte per Discord
    return [app_commands.Choice(name=f"{item['item_name']}", value=item['item_name']) for item in items]

# --- COMANDO: DAI ITEM ---
@bot.tree.command(name="passa", description="Passa un oggetto dal tuo inventario a un altro utente")
@app_commands.describe(
    utente="L'utente a cui dare l'oggetto", 
    nome="Seleziona l'oggetto dal tuo inventario", 
    quantita="Quante unità vuoi passare"
)
@app_commands.autocomplete(nome=inventory_autocomplete) # Attiva la selezione suggerita
async def dai_item(interaction: discord.Interaction, utente: discord.Member, nome: str, quantita: int = 1):
    # Controllo di base: non dare a se stessi
    if utente.id == interaction.user.id: 
        return await interaction.response.send_message("❌ Non puoi passare oggetti a te stesso.", ephemeral=True)
    
    if quantita <= 0:
        return await interaction.response.send_message("❌ Inserisci una quantità valida (minimo 1).", ephemeral=True)

    await interaction.response.defer()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Verifica se il mittente ha l'oggetto e ne ha abbastanza
    cur.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (str(interaction.user.id), nome))
    res = cur.fetchone()
    
    if not res or res[0] < quantita:
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Non hai abbastanza **{nome}** (Posseduti: {res[0] if res else 0}).")

    try:
        # 2. Sottrae gli oggetti al mittente
        cur.execute("UPDATE inventory SET quantity = quantity - %s WHERE user_id = %s AND item_name = %s", (quantita, str(interaction.user.id), nome))
        
        # 3. Aggiunge gli oggetti al destinatario (Gestisce la creazione se non esiste)
        cur.execute("""
            INSERT INTO inventory (user_id, item_name, quantity) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (user_id, item_name) 
            DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
        """, (str(utente.id), nome, quantita))
        
        # 4. Pulizia automatica: elimina righe con quantità zero
        cur.execute("DELETE FROM inventory WHERE quantity <= 0")
        
        conn.commit()
        await interaction.followup.send(f"📦 **{interaction.user.display_name}** ha passato {quantita}x **{nome}** a **{utente.mention}**.")
    
    except Exception as e:
        print(f"Errore comando dai_item: {e}")
        await interaction.followup.send("❌ Si è verificato un errore durante lo scambio.")
    finally:
        cur.close(); conn.close()

# --- COMANDO: USA ---
@bot.tree.command(name="usa", description="Usa un oggetto dal tuo inventario")
@app_commands.describe(nome="Seleziona l'oggetto da usare")
@app_commands.autocomplete(nome=inventory_autocomplete) # Attiva la selezione suggerita
async def usa(interaction: discord.Interaction, nome: str):
    await interaction.response.defer()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Verifica se l'utente possiede l'oggetto selezionato
    cur.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (str(interaction.user.id), nome))
    res = cur.fetchone()
    
    if not res or res[0] <= 0:
        cur.close(); conn.close()
        return await interaction.followup.send(f"❌ Non possiedi l'oggetto **{nome}**.")

    try:
        # 2. Sottrae 1 unità dall'inventario
        cur.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = %s", (str(interaction.user.id), nome))
        
        # 3. Elimina l'oggetto se la quantità è arrivata a zero
        cur.execute("DELETE FROM inventory WHERE quantity <= 0")
        
        conn.commit()
        await interaction.followup.send(f"✨ **{interaction.user.display_name}** ha usato **{nome}**!")
        
    except Exception as e:
        print(f"Errore comando usa: {e}")
        await interaction.followup.send("❌ Errore durante l'uso dell'oggetto.")
    finally:
        cur.close(); conn.close()

# 1. DEFINIZIONE DELLA CLASSE (Deve stare sopra il comando)
# ==========================================
# ==========================================
# 2. COMANDO PER EMETTERE FATTURA (/fattura)
# ==========================================
@bot.tree.command(name="fattura", description="Emetti una fattura a un cittadino")
async def fattura(interaction: discord.Interaction, cliente: discord.Member, azienda: discord.Role, descrizione: str, prezzo: int):
    await interaction.response.defer()
    
    id_f = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    data_attuale = datetime.datetime.now().strftime("%d/%m/%Y")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # IMPORTANTE: Salviamo azienda.id (stringa) per matchare la tabella depositi
        cur.execute("""
            INSERT INTO fatture (id_fattura, id_cliente, id_azienda, descrizione, prezzo, data, stato) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (id_f, str(cliente.id), str(azienda.id), descrizione, prezzo, data_attuale, 'Pendente'))
        
        conn.commit()
        cur.close()
        conn.close()

        embed = discord.Embed(title="📑 Fattura Emessa", color=discord.Color.gold())
        embed.add_field(name="🏢 Azienda Emittente", value=azienda.mention, inline=True)
        embed.add_field(name="👤 Cliente", value=cliente.mention, inline=True)
        embed.add_field(name="💰 Importo", value=f"**{prezzo}$**", inline=True)
        embed.add_field(name="📝 Causale", value=descrizione, inline=False)
        embed.set_footer(text=f"ID Unico: {id_f}")
        
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"ERRORE SQL FATTURA: {e}")
        await interaction.followup.send("❌ Errore nel salvataggio della fattura.", ephemeral=True)

# ==========================================
# 3. COMANDO PER VISUALIZZARE FATTURE (/pagafattura)
# ==========================================


# ==========================================
# 1. CLASSE PER IL PAGAMENTO (PagaFatturaView)
# ==========================================
class PagaFatturaView(discord.ui.View):
    def __init__(self, user_id, fatture):
        super().__init__(timeout=180)
        self.user_id = user_id
        
        options = []
        for f in fatture:
            # Salviamo: ID Fattura | Prezzo | ID Azienda (Ruolo)
            options.append(discord.SelectOption(
                label=f"Fattura {f['id_fattura']}",
                description=f"Importo: {f['prezzo']}$",
                value=f"{f['id_fattura']}|{f['prezzo']}|{f['id_azienda']}"
            ))
            
        self.select = discord.ui.Select(placeholder="Scegli la fattura da saldare...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        # Spacchettiamo i dati
        data = self.select.values[0].split('|')
        id_f = data[0]
        prezzo = int(data[1])
        id_azienda = data[2] # Questo è l'ID numerico del ruolo

        try:
            conn = get_db_connection()
            from psycopg2.extras import RealDictCursor
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # 1. Controllo se il cittadino ha i soldi nel wallet
            cur.execute("SELECT wallet FROM users WHERE user_id = %s", (str(interaction.user.id),))
            user_data = cur.fetchone()
            
            if not user_data or user_data['wallet'] < prezzo:
                cur.close()
                conn.close()
                return await interaction.followup.send("❌ Non hai abbastanza contanti nel wallet!", ephemeral=True)

            # --- TRANSAZIONE ECONOMICA ---
            # A. Sottrazione soldi al cittadino
            cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (prezzo, str(interaction.user.id)))
            
            # B. Accredito nel deposito fazione (Usa l'ID del ruolo)
            cur.execute("""
                INSERT INTO depositi (role_id, money) 
                VALUES (%s, %s) 
                ON CONFLICT (role_id) 
                DO UPDATE SET money = depositi.money + EXCLUDED.money
            """, (str(id_azienda), prezzo))
            
            # C. Aggiornamento stato fattura
            cur.execute("UPDATE fatture SET stato = 'Pagata' WHERE id_fattura = %s", (id_f,))
            
            conn.commit()
            cur.close()
            conn.close()

            self.select.disabled = True
            await interaction.edit_original_response(
                content=f"✅ Fattura `{id_f}` pagata! **{prezzo}$** accreditati nel deposito fazione dell'azienda.", 
                view=self
            )

        except Exception as e:
            print(f"ERRORE SQL PAGAMENTO: {e}")
            await interaction.followup.send("❌ Errore durante il trasferimento dei fondi.", ephemeral=True)

# ==========================================
# 3. COMANDO PER VISUALIZZARE FATTURE (/pagafattura)
# ==========================================
@bot.tree.command(name="pagafattura", description="Paga le tue fatture pendenti")
async def pagafattura(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    try:
        conn = get_db_connection()
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM fatture WHERE id_cliente = %s AND stato = 'Pendente'", (str(interaction.user.id),))
        mie_fatture = cur.fetchall()
        cur.close()
        conn.close()

        if not mie_fatture:
            return await interaction.followup.send("✅ Non hai fatture in sospeso.", ephemeral=False)

        view = PagaFatturaView(interaction.user.id, mie_fatture)
        await interaction.followup.send("Seleziona la fattura da pagare:", view=view, ephemeral=False)
    except Exception as e:
        print(f"ERRORE CARICAMENTO: {e}")
        await interaction.followup.send("❌ Errore nel caricamento dei dati.", ephemeral=True)



ID_RUOLO_CONCESSIONARIO = 1253460178305679433

@bot.tree.command(name="registra_veicolo", description="Registra la vendita e salva i dati nel database motorizzazione")
@app_commands.checks.has_any_role(ID_RUOLO_CONCESSIONARIO)
async def registra_veicolo(
    interaction: discord.Interaction, 
    acquirente: discord.Member, 
    marca_modello: str, 
    targa: str, 
    concessionaria: discord.Role
):
    await interaction.response.defer()

    data_ora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    targa_maiuscola = targa.upper().replace(" ", "") # Puliamo la targa da spazi
    nome_item_chiavi = f"<:emoji_2:1503415723974987837> | Chiavi {marca_modello} [{targa_maiuscola}]"

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # 1. SALVATAGGIO NELLA MOTORIZZAZIONE (Tabella veicoli)
        # Usiamo ON CONFLICT così se la targa esiste già (es. auto usata rivenduta), aggiorna il proprietario
        cur.execute("""
            INSERT INTO veicoli (targa, modello, owner_id, data_vendita) 
            VALUES (%s, %s, %s, %s) 
            ON CONFLICT (targa) 
            DO UPDATE SET 
                owner_id = EXCLUDED.owner_id,
                modello = EXCLUDED.modello,
                data_vendita = EXCLUDED.data_vendita
        """, (targa_maiuscola, marca_modello, str(acquirente.id), data_ora))

        # 2. AGGIUNTA CHIAVI NELL'INVENTARIO (Tabella inventory)
        cur.execute("""
            INSERT INTO inventory (user_id, item_name, quantity) 
            VALUES (%s, %s, 1) 
            ON CONFLICT (user_id, item_name) 
            DO UPDATE SET quantity = inventory.quantity + 1
        """, (str(acquirente.id), nome_item_chiavi))
        
        conn.commit()
        cur.close()
        conn.close()

        # 3. Embed del Contratto
        embed = discord.Embed(title="📝 CONTRATTO DI VENDITA", color=discord.Color.green())
        embed.add_field(name="🏛️ CONCESSIONARIA", value=concessionaria.mention, inline=True)
        embed.add_field(name="👤 ACQUIRENTE", value=f"{acquirente.mention}\nID: `{acquirente.id}`", inline=True)
        embed.add_field(name="🚘 VEICOLO", value=f"**Modello:** {marca_modello}\n**Targa:** `{targa_maiuscola}`", inline=False)
        embed.set_footer(text=f"Registrato in Motorizzazione il {data_ora}")
        
        await interaction.followup.send(content=f"✅ Vendita completata! Veicolo registrato a nome di {acquirente.mention}.", embed=embed)

    except Exception as e:
        print(f"Errore registrazione veicolo: {e}")
        await interaction.followup.send("❌ Errore durante la registrazione nel database.", ephemeral=True)



# ================= COMANDI FAZIONE =================

@bot.tree.command(name="deposito_fazione", description="Visualizza il deposito di fazione")
async def deposito_fazione(interaction: Interaction):
    await interaction.response.defer()
    miei_ruoli = await get_miei_ruoli_fazione(interaction)
    if not miei_ruoli: return await interaction.followup.send("❌ Non sei in una fazione.")

    async def mostra(inter, rid):
        conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT money FROM depositi WHERE role_id = %s", (rid,))
        m = cur.fetchone()['money']
        cur.execute("SELECT item_name, quantity FROM depositi_items WHERE role_id = %s", (rid,))
        it = cur.fetchall()
        r_obj = inter.guild.get_role(int(rid))
        emb = discord.Embed(title=f"🏦 Deposito {r_obj.name}", color=discord.Color.dark_blue())
        emb.add_field(name="Soldi", value=f"{m}$", inline=False)
        lista = "\n".join([f"📦 {i['item_name']} x{i['quantity']}" for i in it]) if it else "Vuoto"
        emb.add_field(name="Oggetti", value=lista, inline=False)
        await inter.followup.send(embed=emb); cur.close(); conn.close()

    if len(miei_ruoli) == 1: await mostra(interaction, str(miei_ruoli[0].id))
    else:
        view = discord.ui.View()
        sel = discord.ui.Select(options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in miei_ruoli])
        async def call(i): 
            for it in view.children: it.disabled = True
            await i.response.edit_message(view=view); await mostra(i, sel.values[0])
        sel.callback = call; view.add_item(sel)
        await interaction.followup.send("Quale deposito vuoi aprire?", view=view, ephemeral=True)


@bot.tree.command(name="deposita_item_fazione", description="Metti un item in fazione")
async def deposita_item_fazione(interaction: Interaction, nome: str, quantita: int = 1):
    await interaction.response.defer()
    miei_ruoli = await get_miei_ruoli_fazione(interaction)
    if not miei_ruoli: return await interaction.followup.send("❌ No Fazione.")
    
    nome_e = await cerca_item_smart(interaction, nome, "inventory")
    if not nome_e: 
        return await interaction.followup.send("❌ Item non trovato nel tuo inventario.")

    async def procedi(inter, rid):
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE inventory SET quantity = quantity - %s WHERE user_id = %s AND item_name = %s", (quantita, str(inter.user.id), nome_e))
        cur.execute("INSERT INTO depositi_items (role_id, item_name, quantity) VALUES (%s, %s, %s) ON CONFLICT (role_id, item_name) DO UPDATE SET quantity = depositi_items.quantity + %s", (rid, nome_e, quantita, quantita))
        cur.execute("DELETE FROM inventory WHERE quantity <= 0")
        conn.commit(); cur.close(); conn.close()
        r_obj = inter.guild.get_role(int(rid))
        await inter.followup.send(f"✅ **{inter.user.display_name}** ha messo {quantita}x **{nome_e}** in **{r_obj.name}**.")

    if len(miei_ruoli) == 1: 
        await procedi(interaction, str(miei_ruoli[0].id))
    else:
        view = discord.ui.View()
        sel = discord.ui.Select(options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in miei_ruoli])
        
        async def call(i: Interaction):
            # Deferiamo subito l'interazione del Select per evitare il timeout
            await i.response.defer()
            for it in view.children: it.disabled = True
            # Aggiorniamo il messaggio originale usando edit_original_response
            await i.edit_original_response(view=view)
            await procedi(i, sel.values[0])
            
        sel.callback = call; view.add_item(sel)
        await interaction.followup.send("In quale magazzino depositi?", view=view, ephemeral=True)

@bot.tree.command(name="preleva_item_fazione", description="Preleva un item dalla fazione")
async def preleva_item_fazione(interaction: Interaction, nome: str, quantita: int = 1):
    await interaction.response.defer()
    miei_ruoli = await get_miei_ruoli_fazione(interaction)
    if not miei_ruoli: return await interaction.followup.send("❌ No Fazione.")

    async def procedi(inter, rid):
        nome_e = await cerca_item_smart(inter, nome, f"fazione_{rid}")
        if not nome_e: return await inter.followup.send("❌ Item non trovato.")
        
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT quantity FROM depositi_items WHERE role_id = %s AND item_name = %s", (rid, nome_e))
        res = cur.fetchone()
        if not res or res[0] < quantita: 
            cur.close(); conn.close()
            return await inter.followup.send("❌ Magazzino fazione insufficiente.")
            
        cur.execute("UPDATE depositi_items SET quantity = quantity - %s WHERE role_id = %s AND item_name = %s", (quantita, rid, nome_e))
        cur.execute("INSERT INTO inventory (user_id, item_name, quantity) VALUES (%s, %s, %s) ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + %s", (str(inter.user.id), nome_e, quantita, quantita))
        cur.execute("DELETE FROM depositi_items WHERE quantity <= 0")
        conn.commit(); cur.close(); conn.close()
        
        r_obj = inter.guild.get_role(int(rid))
        await inter.followup.send(f"📦 **{inter.user.display_name}** ha prelevato {quantita}x **{nome_e}** da **{r_obj.name}**.")

    if len(miei_ruoli) == 1: 
        await procedi(interaction, str(miei_ruoli[0].id))
    else:
        view = discord.ui.View()
        sel = discord.ui.Select(options=[discord.SelectOption(label=r.name, value=str(r.id)) for r in miei_ruoli])
        
        async def call(i: Interaction):
            # Deferiamo subito l'interazione del Select per evitare il timeout
            await i.response.defer()
            for it in view.children: it.disabled = True
            # Aggiorniamo il messaggio originale usando il followup visto che l'interazione è ora deferita
            await i.edit_original_response(view=view)
            await procedi(i, sel.values[0])
            
        sel.callback = call; view.add_item(sel)
        await interaction.followup.send("Da quale magazzino prelevi?", view=view, ephemeral=True)


# ================= SHOP & LAVORO =================
class ShopPaginationView(discord.ui.View):
    def __init__(self, items, interaction_user):
        super().__init__(timeout=120)
        self.items = items
        self.user = interaction_user
        self.current_page = 0
        self.items_per_page = 5
        self.create_buttons()

    def create_buttons(self):
        self.clear_items()
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        current_items = self.items[start:end]

        for item in current_items:
            self.add_item(ShopBuyButton(item))

        if len(self.items) > self.items_per_page:
            prev_btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0))
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)

            next_btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary, disabled=(end >= len(self.items)))
            next_btn.callback = self.next_page
            self.add_item(next_btn)

    def create_embed(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_items = self.items[start:end]
        total_pages = (len(self.items) - 1) // self.items_per_page + 1
        
        embed = discord.Embed(
            title="🛒 Catalogo Evren City",
            description=f"Pagina `{self.current_page + 1}/{total_pages}`\nUsa i bottoni verdi per acquistare.",
            color=0x2ECC71
        )
        
        for i in page_items:
            # Sincronizzato con colonna role_required
            role_id = i.get('role_required')
            req = f"\n🛡️ *Richiede: <@&{role_id}>*" if role_id and str(role_id).lower() != "none" else ""
            
            embed.add_field(
                name=f"📦 {i['name']}", 
                value=f"{i.get('description', 'Nessuna descrizione')}{req}\n━━━━━━━━━━━━━━", 
                inline=False
            )
        embed.set_footer(text="Evren City RP - Il tuo destino ti aspetta")
        return embed

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("❌ Non puoi farlo.", ephemeral=True)
        self.current_page -= 1
        self.create_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("❌ Non puoi farlo.", ephemeral=True)
        self.current_page += 1
        self.create_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

class ShopBuyButton(discord.ui.Button):
    def __init__(self, item):
        self.item_nome = item['name']
        self.prezzo = item['price']
        self.ruolo_req = item.get('role_required')
        super().__init__(label=f"$ {self.prezzo} - {self.item_nome}", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        # Controllo Ruolo
        if self.ruolo_req and str(self.ruolo_req).lower() != "none":
            if not any(str(r.id) == str(self.ruolo_req) for r in interaction.user.roles):
                return await interaction.response.send_message(f"❌ Non hai il ruolo richiesto!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Controllo Soldi su colonna 'bank'
            cur.execute("SELECT bank FROM users WHERE user_id = %s", (str(interaction.user.id),))
            res = cur.fetchone()

            if not res or res['bank'] < self.prezzo:
                return await interaction.followup.send("❌ Fondi insufficienti in Banca!", ephemeral=True)

            # Transazione
            cur.execute("UPDATE users SET bank = bank - %s WHERE user_id = %s", (self.prezzo, str(interaction.user.id)))
            cur.execute("""
                INSERT INTO inventory (user_id, item_name, quantity) 
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, item_name) 
                DO UPDATE SET quantity = inventory.quantity + 1
            """, (str(interaction.user.id), self.item_nome))
            
            conn.commit()
            await interaction.followup.send(f"✅ Acquisto completato: **{self.item_nome}**!", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"⚠️ Errore: {e}", ephemeral=True)
        finally:
            if conn: cur.close(); conn.close()

@bot.tree.command(name="shop", description="Apri il catalogo")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer()
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Sincronizzato con tabella items
        cur.execute("SELECT name, description, price, role_required FROM items ORDER BY price ASC")
        items = cur.fetchall()
        
        if not items:
            return await interaction.followup.send("🛒 Il catalogo è vuoto.")

        view = ShopPaginationView(items, interaction.user)
        await interaction.followup.send(embed=view.create_embed(), view=view)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Errore: `{e}`")
    finally:
        if conn: cur.close(); conn.close()

@bot.tree.command(name="compra", description="Compra un oggetto")
async def compra(interaction: Interaction, nome: str, quantita: int = 1):
    await interaction.response.defer()
    nome_e = await cerca_item_smart(interaction, nome, "items")
    if not nome_e: return
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM items WHERE name = %s", (nome_e,))
    item = cur.fetchone()
    u = get_user_data(interaction.user.id)
    prezzo_totale = item['price'] * quantita
    if item['role_required'] != "None" and not any(str(r.id) == item['role_required'] for r in interaction.user.roles):
        return await interaction.followup.send("❌ Grado fazione mancante.")
    if u['wallet'] < prezzo_totale: return await interaction.followup.send("❌ Soldi insufficienti.")
    cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (prezzo_totale, str(interaction.user.id)))
    cur.execute("INSERT INTO inventory (user_id, item_name, quantity) VALUES (%s, %s, %s) ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + %s", (str(interaction.user.id), nome_e, quantita, quantita))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"🛍️ **{interaction.user.display_name}** ha comprato {quantita}x **{nome_e}**!")



# --- CLASSE VIEW PER I BOTTONI ---

# --- CLASSE VIEW PER I BOTTONI (Corretta e Reattiva) ---
class BlackjackView(discord.ui.View):
    def __init__(self, interaction, somma, mano_p, mano_b):
        super().__init__(timeout=60) # Il gioco scade dopo 60 secondi di inattività
        self.interaction = interaction
        self.somma = somma
        self.mano_p = mano_p
        self.mano_b = mano_b

    def get_tot(self, mano):
        tot = sum(mano)
        as_count = mano.count(11)
        while tot > 21 and as_count > 0:
            tot -= 10
            as_count -= 1
        return tot

    @discord.ui.button(label="Carta 🃏", style=discord.ButtonStyle.green)
    async def carta(self, inter: discord.Interaction, button: discord.ui.Button):
        # Controllo che solo chi ha iniziato la partita possa giocare
        if inter.user.id != self.interaction.user.id:
            return await inter.response.send_message("❌ Questa non è la tua partita!", ephemeral=True)
        
        self.mano_p.append(random.randint(2, 11))
        
        if self.get_tot(self.mano_p) > 21:
            await self.concludi(inter, "sballato")
        else:
            await self.update_msg(inter)

    @discord.ui.button(label="Stai ✋", style=discord.ButtonStyle.red)
    async def stai(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.interaction.user.id:
            return await inter.response.send_message("❌ Questa non è la tua partita!", ephemeral=True)
        
        # Logica del Banco
        while self.get_tot(self.mano_b) < 17:
            self.mano_b.append(random.randint(2, 11))
        
        tot_p = self.get_tot(self.mano_p)
        tot_b = self.get_tot(self.mano_b)
        
        if tot_b > 21 or tot_p > tot_b:
            esito = "vinto"
        elif tot_p < tot_b:
            esito = "perso"
        else:
            esito = "pareggio"
            
        await self.concludi(inter, esito)

    async def update_msg(self, inter):
        # Usiamo edit_message per aggiornare l'interfaccia senza inviare nuovi messaggi
        emb = discord.Embed(title="🃏 Blackjack - In Corso", color=discord.Color.gold())
        emb.add_field(name="La tua mano 👤", value=f"{self.mano_p}\n**Totale: {self.get_tot(self.mano_p)}**", inline=True)
        emb.add_field(name="Banco 🏛️", value=f"[{self.mano_b[0]}, ?]\n**Totale: ?**", inline=True)
        emb.set_footer(text=f"Puntata: {self.somma}$")
        await inter.response.edit_message(embed=emb, view=self)

    async def concludi(self, inter, esito):
        self.stop() # Disattiva i bottoni immediatamente
        tot_p = self.get_tot(self.mano_p)
        tot_b = self.get_tot(self.mano_b)
        
        # Connessione al database per pagare/sottrarre
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            if esito == "vinto":
                # Paga il premio (raddoppio)
                cur.execute("UPDATE users SET wallet = wallet + %s WHERE user_id = %s", (self.somma, str(self.interaction.user.id)))
                txt = f"🏆 **Hai vinto!** Ti sono stati accreditati **{self.somma}$**."
                colore = discord.Color.green()
            elif esito == "pareggio":
                txt = "🤝 **Pareggio!** Non hai perso nulla."
                colore = discord.Color.light_gray()
            else:
                # Sottrae la scommessa
                cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (self.somma, str(self.interaction.user.id)))
                txt = f"💀 **Hai perso {self.somma}$**. Il banco vince."
                colore = discord.Color.red()
            
            conn.commit()
        except Exception as e:
            print(f"Errore DB Blackjack: {e}")
        finally:
            cur.close()
            conn.close()

        emb = discord.Embed(title="🃏 Blackjack - Risultato Finale", color=colore)
        emb.add_field(name="Tu 👤", value=f"{self.mano_p} (Tot: {tot_p})", inline=True)
        emb.add_field(name="Banco 🏛️", value=f"{self.mano_b} (Tot: {tot_b})", inline=True)
        emb.add_field(name="Esito", value=txt, inline=False)
        
        await inter.response.edit_message(embed=emb, view=None)

# --- COMANDO SLASH ---
@bot.tree.command(name="blackjack", description="Gioca a Blackjack contro il banco")
async def blackjack(interaction: discord.Interaction, somma: int):
    # Recupero dati per controllo fondi
    u = get_user_data(interaction.user.id)
    
    if somma <= 0:
        return await interaction.response.send_message("❌ Inserisci una somma valida!", ephemeral=True)
    if u['wallet'] < somma:
        return await interaction.response.send_message(f"❌ Non hai abbastanza contanti! Hai solo {u['wallet']}$.", ephemeral=True)

    # Carte iniziali
    mano_p = [random.randint(2, 11), random.randint(2, 11)]
    mano_b = [random.randint(2, 11)]
    
    view = BlackjackView(interaction, somma, mano_p, mano_b)
    
    emb = discord.Embed(title="🃏 Blackjack", color=discord.Color.gold())
    emb.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    emb.add_field(name="La tua mano 👤", value=f"{mano_p}\n**Totale: {view.get_tot(mano_p)}**", inline=True)
    emb.add_field(name="Banco 🏛️", value=f"[{mano_b[0]}, ?]\n**Totale: ?**", inline=True)
    emb.set_footer(text=f"Puntata: {somma}$")

    await interaction.response.send_message(embed=emb, view=view)



@bot.tree.command(name="roulette", description="Punta i tuoi soldi alla roulette (Attesa 10s)")
@app_commands.choices(puntata=[
    app_commands.Choice(name="🔴 Rosso (x2)", value="rosso"),
    app_commands.Choice(name="⚫ Nero (x2)", value="nero"),
    app_commands.Choice(name="🟢 Numero Singolo (x36)", value="numero")
])
async def roulette(interaction: discord.Interaction, puntata: str, somma: int, numero_scelto: int = None):
    u = get_user_data(interaction.user.id)
    if somma <= 0:
        return await interaction.response.send_message("❌ Inserisci una cifra valida!", ephemeral=True)
    if u['wallet'] < somma:
        return await interaction.response.send_message(f"❌ Non hai abbastanza contanti! (Hai {u['wallet']}$)", ephemeral=True)

    if puntata == "numero" and (numero_scelto is None or numero_scelto < 0 or numero_scelto > 36):
        return await interaction.response.send_message("❌ Se punti su un numero, scegline uno tra 0 e 36!", ephemeral=True)

    await interaction.response.send_message(f"🎰 **{interaction.user.display_name}** ha puntato **{somma}$** su **{puntata.upper()}**...\n*La pallina sta girando...* 🎡")
    
    await asyncio.sleep(10) # Attesa per creare suspense
    
    risultato = random.randint(0, 36)
    rossi = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    colore_uscito = "rosso" if risultato in rossi else "nero" if risultato != 0 else "verde"
    emoji = "🔴" if colore_uscito == "rosso" else "⚫" if colore_uscito == "nero" else "🟢"

    vinto = False
    moltiplicatore = 2
    if puntata == "rosso" and colore_uscito == "rosso": vinto = True
    elif puntata == "nero" and colore_uscito == "nero": vinto = True
    elif puntata == "numero" and numero_scelto == risultato: 
        vinto = True
        moltiplicatore = 36

    conn = get_db_connection()
    cur = conn.cursor()
    
    if vinto:
        # Guadagno Netto: se punti 100 e vinci x2, ricevi +100 (totale 200)
        vincita_netta = somma * (moltiplicatore - 1)
        cur.execute("UPDATE users SET wallet = wallet + %s WHERE user_id = %s", (vincita_netta, str(interaction.user.id)))
        testo = f"✅ RISULTATO: **{risultato} {emoji}**. Hai vinto! Ti sono stati accreditati **{somma * moltiplicatore}$** 🎉"
    else:
        # Perdita: ti vengono sottratti i soldi puntati
        cur.execute("UPDATE users SET wallet = wallet - %s WHERE user_id = %s", (somma, str(interaction.user.id)))
        testo = f"💀 RISULTATO: **{risultato} {emoji}**. Hai perso **{somma}$**. La casa vince! 🏛️"
    
    conn.commit()
    cur.close(); conn.close()
    await interaction.channel.send(f"🎰 **{interaction.user.mention}**\n{testo}")


# ================= COMANDI STAFF =================

@bot.tree.command(name="staff_vedi_portafoglio", description="STAFF - Bilancio utente")
async def staff_vedi_portafoglio(interaction: Interaction, utente: discord.Member):
    if not is_staff(interaction): return await interaction.response.send_message("❌ No Staff.")
    u = get_user_data(utente.id)
    await interaction.response.send_message(f"💰 {utente.name}: Wallet {u['wallet']}$ | Bank {u['bank']}$")

@bot.tree.command(name="staff_vedi_inventario", description="STAFF - Inventario utente")
async def staff_vedi_inventario(interaction: Interaction, utente: discord.Member):
    if not is_staff(interaction): return await interaction.response.send_message("❌ No Staff.")
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT item_name, quantity FROM inventory WHERE user_id = %s", (str(utente.id),))
    items = cur.fetchall()
    cur.close(); conn.close()
    desc = "\n".join([f"{i['item_name']} x{i['quantity']}" for i in items]) if items else "Vuoto."
    await interaction.response.send_message(f"🎒 Inventario {utente.name}:\n{desc}")

@bot.tree.command(name="staff_vedi_deposito", description="STAFF - Vedi un deposito fazione")
async def staff_vedi_deposito(interaction: Interaction):
    if not is_staff(interaction): return await interaction.response.send_message("❌ No Staff.")
    await interaction.response.defer()
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT role_id FROM depositi"); fazioni_id = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    
    async def mostra_staff(inter, rid):
        conn_i = get_db_connection(); cur_i = conn_i.cursor(cursor_factory=RealDictCursor)
        cur_i.execute("SELECT money FROM depositi WHERE role_id = %s", (rid,))
        m = cur_i.fetchone()['money']
        cur_i.execute("SELECT item_name, quantity FROM depositi_items WHERE role_id = %s", (rid,))
        it = cur_i.fetchall()
        r_obj = inter.guild.get_role(int(rid))
        emb = discord.Embed(title=f"🏦 Ispezione: {r_obj.name if r_obj else rid}", color=discord.Color.red())
        emb.add_field(name="Soldi", value=f"{m}$", inline=False)
        lista = "\n".join([f"📦 {i['item_name']} x{i['quantity']}" for i in it]) if it else "Vuoto"
        emb.add_field(name="Oggetti", value=lista, inline=False)
        await inter.followup.send(embed=emb); cur_i.close(); conn_i.close()

    view = discord.ui.View()
    options = [discord.SelectOption(label=interaction.guild.get_role(int(rid)).name if interaction.guild.get_role(int(rid)) else rid, value=rid) for rid in fazioni_id]
    sel = discord.ui.Select(options=options[:25])
    async def call(i): 
        for it in view.children: it.disabled = True
        await i.response.edit_message(view=view); await mostra_staff(i, sel.values[0])
    sel.callback = call; view.add_item(sel)
    await interaction.followup.send("Quale deposito ispezioni?", view=view, ephemeral=True)

# ================= COMANDI ADMIN =================

# Funzione di supporto per pulire il codice (opzionale ma consigliata)
def is_staff(interaction: discord.Interaction):
    return any(role.id == RUOLO_STAFF_ID for role in interaction.user.roles)
@bot.tree.command(name="aggiungi_item", description="STAFF - Regala item")
async def aggiungi_item(interaction: Interaction, utente: discord.Member, nome: str, quantita: int = 1):
    if not is_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    # Avviamo il deferramento per dare tempo alla ricerca smart di elaborare
    await interaction.response.defer()
    
    # Cerca tra tutti gli item globali esistenti nel gioco
    nome_e = await cerca_item_smart(interaction, nome, "items")
    if not nome_e: 
        return await interaction.followup.send("❌ Item non trovato nella ricerca globale.")
        
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO inventory (user_id, item_name, quantity) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + %s", 
        (str(utente.id), nome_e, quantita, quantita)
    )
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"✅ Admin ha dato {quantita}x **{nome_e}** a {utente.mention}")


@bot.tree.command(name="rimuovi_item", description="STAFF - Togli item")
async def rimuovi_item(interaction: Interaction, utente: discord.Member, nome: str, quantita: int = 1):
    if not is_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    # Avviamo il deferramento per dare tempo alla ricerca smart di elaborare
    await interaction.response.defer()
    
    # SMART FIX: Cerca solo nell'inventario dell'utente a cui stiamo per togliere l'item!
    nome_e = await cerca_item_smart(interaction, nome, "inventory", target_user_id=utente.id)
    if not nome_e: 
        return await interaction.followup.send(f"❌ Item non trovato nell'inventario di {utente.display_name}.")
        
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(
        "UPDATE inventory SET quantity = GREATEST(0, quantity - %s) WHERE user_id = %s AND item_name = %s", 
        (quantita, str(utente.id), nome_e)
    )
    cur.execute("DELETE FROM inventory WHERE quantity <= 0")
    conn.commit(); cur.close(); conn.close()
    
    await interaction.followup.send(f"✅ Admin ha rimosso {quantita}x **{nome_e}** a {utente.mention}")

@bot.tree.command(name="crea_item_shop", description="STAFF - Crea item shop")
async def crea_item_shop(interaction: Interaction, nome: str, descrizione: str, prezzo: int, ruolo: discord.Role = None):
    if not is_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    rid = str(ruolo.id) if ruolo else "None"
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO items (name, description, price, role_required) VALUES (%s,%s,%s,%s) ON CONFLICT (name) DO UPDATE SET price=EXCLUDED.price, description=EXCLUDED.description, role_required=EXCLUDED.role_required", (nome, descrizione, prezzo, rid))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Item **{nome}** creato/aggiornato nello shop.")

@bot.tree.command(name="elimina_item_shop", description="STAFF - Elimina definitivamente item dallo shop")
async def elimina_item_shop(interaction: Interaction, nome: str):
    if not is_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    await interaction.response.defer()
    nome_e = await cerca_item_smart(interaction, nome, "items")
    if not nome_e: return
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE name = %s", (nome_e,))
    conn.commit(); cur.close(); conn.close()
    await interaction.followup.send(f"🗑️ L'item **{nome_e}** è stato rimosso dallo shop.")

# --- UTILITY ADMIN ---

@bot.tree.command(name="registra_fazione", description="STAFF - Registra ruolo fazione")
async def registra_fazione(interaction: Interaction, ruolo: discord.Role):
    if not is_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO depositi (role_id, money) VALUES (%s, 0) ON CONFLICT DO NOTHING", (str(ruolo.id),))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"✅ Fazione **{ruolo.name}** registrata nel sistema.")

@bot.command()
@commands.is_owner()
async def sync(ctx):
    fmt = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"🔄 Sincronizzati {len(fmt)} comandi in questo server!")

@bot.tree.command(name="wipe_utente", description="STAFF - Reset totale utente")
async def wipe_utente(interaction: Interaction, utente: discord.Member):
    if not is_staff(interaction):
        return await interaction.response.send_message("❌ Permessi insufficienti.", ephemeral=True)
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE users SET wallet = 500, bank = 0 WHERE user_id = %s", (str(utente.id),))
    cur.execute("DELETE FROM inventory WHERE user_id = %s", (str(utente.id),))
    conn.commit(); cur.close(); conn.close()
    await interaction.response.send_message(f"🧹 Reset totale per **{utente.name}**.")
import discord
from discord.ext import commands

# Decoratore per il controllo del ruolo Polizia
def is_polizia():
    async def predicate(ctx):
        # Verifica se l'utente ha il ruolo specifico
        return any(role.name == "POLIZIA_ROLE_ID" for role in ctx.author.roles)
    return commands.check(predicate)

class PoliziaCittadini(discord.ui.Select):
    def __init__(self, citizens, pool):
        options = [
            discord.SelectOption(label=f"{c['nome']} {c['cognome']}", description=f"ID: {c['user_id']}", value=c['user_id'])
            for c in citizens
        ]
        super().__init__(placeholder="Seleziona un cittadino da controllare...", options=options)
        self.pool = pool

    async def callback(self, interaction: discord.Interaction):
        user_id = self.values[0]
        
        async with self.pool.acquire() as conn:
            # Query per dossier completo
            doc = await conn.fetchrow("SELECT * FROM documenti WHERE user_id = $1", user_id)
            veicoli = await conn.fetch("SELECT modello, targa FROM veicoli WHERE owner_id = $1", user_id)
            multe = await conn.fetch("SELECT motivo, ammontare FROM multe WHERE user_id = $1 ORDER BY data DESC LIMIT 3", user_id)
            arresti = await conn.fetch("SELECT motivo, tempo FROM arresti WHERE user_id = $1 ORDER BY data DESC LIMIT 3", user_id)

        embed = discord.Embed(title=f"📁 Dossier: {doc['nome']} {doc['cognome']}", color=0x0047AB)
        embed.add_field(name="🧬 Info", value=f"**Genere:** {doc['genere']}\n**Altezza:** {doc['altezza']}cm\n**Nato il:** {doc['data_nascita']}", inline=True)
        
        v_list = "\n".join([f"🚘 {v['modello']} ({v['targa']})" for v in veicoli]) or "Nessun veicolo"
        embed.add_field(name="🚘 Veicoli", value=v_list, inline=False)

        m_list = "\n".join([f"📜 {m['motivo']} (${m['ammontare']})" for m in multe]) or "Nessuna multa"
        embed.add_field(name="📜 Ultime Multe", value=m_list, inline=True)

        a_list = "\n".join([f"⚖️ {a['motivo']} ({a['tempo']} min)" for a in arresti]) or "Fedina pulita"
        embed.add_field(name="⚖️ Precedenti", value=a_list, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

class PoliziaView(discord.ui.View):
    def __init__(self, citizens, pool):
        super().__init__()
        self.add_item(PoliziaCittadini(citizens, pool))

@bot.command(name="centrale")
@is_polizia()
async def centrale(ctx):
    """Mostra la lista dei cittadini e permette il controllo dettagliato"""
    async with bot.db_pool.acquire() as conn:
        # Recuperiamo i primi 25 cittadini per il menu a tendina
        citizens = await conn.fetch("SELECT user_id, nome, cognome FROM documenti ORDER BY cognome ASC LIMIT 25")
        
    if not citizens:
        return await ctx.send("Nessun cittadino registrato nel database.")

    view = PoliziaView(citizens, bot.db_pool)
    await ctx.send("👮 **Database Centrale Polizia**: Seleziona un soggetto per il dossier.", view=view)

# ================= WEB SERVER & START =================

# Lista dei server autorizzati
ALLOWED_GUILDS = [1383905374092005376, 1233353915559313478, 1392825183915610205]

@bot.event
async def on_ready():
    print(f'{"="*40}')
    print(f'🤖 LOG IN: {bot.user}')
    
    # 1. Caricamento View Persistenti
    # Inizializza tutte le classi necessarie per mantenere i bottoni attivi al riavvio
    try:
        bot.add_view(VerificaView())
        bot.add_view(RapinaStaffView())
        bot.add_view(TurnoStaffView())
        bot.add_view(BackgroundStaffView())
        print('✅ Persistenza caricata: Verifica, Rapine e Turni.')
    except Exception as e:
        print(f"⚠️ Errore nel caricamento delle View: {e}")

    # 2. Sincronizzazione Comandi Slash
    try:
        print("🔄 Sincronizzazione comandi slash...")
        synced = await bot.tree.sync()
        print(f"🔄 Sincronizzati {len(synced)} comandi!")
    except Exception as e:
        print(f"❌ Errore durante la sincronizzazione: {e}")

    # 3. Check finale
    print(f"✅ Bot Online e pronto all'uso!")
    print(f'{"="*40}')

# --- Controllo autorizzazione server ---
@bot.tree.interaction_check
async def check_guild(interaction: discord.Interaction):
    if interaction.guild_id not in ALLOWED_GUILDS:
        await interaction.response.send_message("❌ Questo bot non è autorizzato in questo server.", ephemeral=True)
        return False
    return True

# --- Configurazione Flask per Render ---
app = Flask("")

@app.route("/")
def home(): 
    return "Bot Online"

def run(): 
    # Render usa la porta 10000 di default, os.environ.get la recupera correttamente
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Avvio del Web Server in un thread separato
threading.Thread(target=run, daemon=True).start()

# Avvio finale del Bot
bot.run(TOKEN)



