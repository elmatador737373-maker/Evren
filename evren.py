import os
import random
import string
import threading
from flask import Flask, jsonify
import discord
from discord import app_commands, ui
from discord.ext import commands
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- CONFIGURAZIONE RUOLI SPECIFICI ---
RUOLO_STAFF_ID = 123456789012345676           # Permesso per /crea_item
RUOLO_BANCOMAT_ID = 123456789012345677        # Permesso per accedere al Bancomat (opzionale)
RUOLO_ARMERIA_ID = 123456789012345678        # Permesso per registrare ed emettere armi
RUOLO_MOTORIZZAZIONE_ID = 123456789012345679  # Permesso per registrare veicoli e patenti
RUOLO_POLIZIA_ID = 1521205969269555351         # Permesso per CAD Polizia e Porto d'Armi
RUOLO_IMMOBILIARE_ID = 123456789012345681     # Permesso per registrare le case/immobili

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

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
            "cash": 500.0,
            "bank": 1500.0,
            "pin": None,
            "max_weight": 10.0  # Limite peso base
        }
        insert_res = supabase.table("users").insert(new_user).execute()
        return insert_res.data[0]

def log_transaction(user_id: str, trans_type: str, amount: float, details: str):
    supabase.table("bank_transactions").insert({
        "discord_id": str(user_id),
        "type": trans_type,
        "amount": round(amount, 2),
        "details": details
    }).execute()

def genera_codice_fiscale(nome: str, cognome: str) -> str:
    cons_cog = "".join([c for c in cognome.upper() if c in "BCDFGHJKLMNPQRSTVWXYZ"]) + "XXX"
    cons_nom = "".join([c for c in nome.upper() if c in "BCDFGHJKLMNPQRSTVWXYZ"]) + "XXX"
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    digits = "".join(random.choices(string.digits, k=5))
    return f"{cons_cog[:3]}{cons_nom[:3]}{digits}{letters}"

def genera_num_documento() -> str:
    letters1 = "".join(random.choices(string.ascii_uppercase, k=2))
    digits = "".join(random.choices(string.digits, k=5))
    letters2 = "".join(random.choices(string.ascii_uppercase, k=2))
    return f"{letters1}{digits}{letters2}"

def genera_matricola_arma() -> str:
    parte1 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
    parte2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
    return f"{parte1}-{parte2}"

def calculate_user_inventory_weight(user_id: str) -> float:
    res = supabase.table("inventory").select("quantity, item_id, master_items(weight)").eq("discord_id", str(user_id)).execute()
    total_weight = 0.0
    if res.data:
        for row in res.data:
            q = row.get("quantity", 1)
            w = row.get("master_items", {}).get("weight", 0.1) if row.get("master_items") else 0.1
            total_weight += q * w
    return round(total_weight, 2)

# --- VIEW CON BOTTONI REINDIRIZZAMENTO (LINK) ---

class WelcomeButtonsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        # Bottone N1 -> Guida Sblocco Canali
        self.add_item(ui.Button(
            label="Bottone N1", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1500844219424706581"
        ))
        
        # Bottone N2 -> Regolamento 1
        self.add_item(ui.Button(
            label="Bottone N2", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1252225171553652787"
        ))
        
        # Bottone N3 -> Regolamento 2
        self.add_item(ui.Button(
            label="Bottone N3", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1374421195163963553"
        ))

        # Bottone N4 -> Regolamento 3
        self.add_item(ui.Button(
            label="Bottone N4", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1519623994591019189"
        ))

        # Bottone N5 -> Background
        self.add_item(ui.Button(
            label="Bottone N5", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1252225106785337355"
        ))

        # Bottone N6 -> Whitelist
        self.add_item(ui.Button(
            label="Bottone N6", 
            style=discord.ButtonStyle.link, 
            url="https://discord.com/channels/1233353915559313478/1503750254028390580"
        ))


# --- EVENTO INVIO MESSAGGIO PRIVATO (DM) ALL'INGRESSO ---

import discord
from discord import app_commands
from discord.ui import View, Button, Select

# --- 1. SELETTORE DELLE CATEGORIE NELLO SHOP ---
class ShopCategorySelect(Select):
    def __init__(self):
        # Definisci qui le categorie disponibili nel tuo shop
        options = [
            discord.SelectOption(label="Armi", description="Acquista armi e munizioni", emoji="🔫", value="armi"),
            discord.SelectOption(label="Mediche", description="Kit medici e bende", emoji="💊", value="mediche"),
            discord.SelectOption(label="Generale", description="Oggetti vari e utility", emoji="🎒", value="generale"),
        ]
        super().__init__(placeholder="📂 Seleziona una categoria...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        categoria = self.values[0]
        
        # Interroga Supabase per prendere gli item della categoria scelta
        res = supabase.table("shop_items").select("*").eq("category", categoria).execute()
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
                ruolo_req = item.get("required_role_name", "Nessuno")
                embed.add_field(
                    name=f"🔹 {nome}",
                    value=f"💰 Prezzo: **€ {prezzo:,.2f}**\n🔒 Ruolo richiesto: `{ruolo_req}`",
                    inline=False
                )

        embed.set_footer(text="Evren City OS • Economia")
        await interaction.response.edit_message(embed=embed, view=self.view)


class ShopView(View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ShopCategorySelect())


# --- 2. COMANDO /SHOP ---
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


# --- 3. FUNZIONE DI AUTOCOMPLETE PER IL COMANDO /COMPRA ---
async def shop_item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("shop_items").select("name").ilike("name", f"%{current}%").limit(25).execute()
    items = res.data if res.data else []
    return [app_commands.Choice(name=i["name"], value=i["name"]) for i in items]


# --- 4. COMANDO /COMPRA ---
@bot.tree.command(name="compra", description="Acquista un oggetto dallo shop verificando fondi e requisiti.")
@app_commands.describe(item="Nome dell'oggetto da acquistare")
@app_commands.autocomplete(item=shop_item_autocomplete)
async def compra(interaction: discord.Interaction, item: str):
    user = interaction.user
    user_id = str(user.id)

    # 1. Cerca l'oggetto nel database dello shop
    res_item = supabase.table("shop_items").select("*").ilike("name", item).execute()
    if not res_item.data:
        await interaction.response.send_message("❌ L'oggetto selezionato non esiste nello shop.", ephemeral=True)
        return

    item_data = res_item.data[0]
    prezzo = item_data.get("price", 0)
    required_role_id = item_data.get("required_role_id") # ID del ruolo Discord (opzionale)
    item_name = item_data.get("name")

    # 2. Verifica se è richiesto un ruolo specifico
    if required_role_id:
        if not any(r.id == int(required_role_id) for r in user.roles): # type: ignore
            await interaction.response.send_message(f"❌ Non possiedi il ruolo richiesto per poter acquistare **{item_name}**.", ephemeral=True)
            return

    # 3. Verifica i contanti dell'utente nel database
    res_user = supabase.table("users").select("cash").eq("discord_id", user_id).execute()
    contanti_attuali = res_user.data[0].get("cash", 0) if res_user.data else 0

    if contanti_attuali < prezzo:
        await interaction.response.send_message(
            f"❌ Fondi insufficienti! Hai **€ {contanti_attuali:,.2f}**, ma l'oggetto costa **€ {prezzo:,.2f}**.",
            ephemeral=True
        )
        return

    # 4. Scala i soldi e aggiunge l'oggetto all'inventario dell'utente
    nuovo_saldo = contanti_attuali - prezzo
    supabase.table("users").update({"cash": nuovo_saldo}).eq("discord_id", user_id).execute()

    # Esempio di aggiunta all'inventario personale (tabella "user_inventory")
    # Puoi adattarla in base alla struttura delle tue tabelle
    supabase.table("user_inventory").insert({
        "discord_id": user_id,
        "item_name": item_name,
        "quantity": 1
    }).execute()

    await interaction.response.send_message(
        f"✅ Acquisto effettuato con successo!\n"
        f"Hai comprato: **{item_name}** per **€ {prezzo:,.2f}**.\n"
        f"Nuovo saldo contanti: **€ {nuovo_saldo:,.2f}**",
        ephemeral=True
    )

import json
import numpy as np
import discord
from discord import app_commands
from playwright.async_api import async_playwright

import asyncio
import os
import discord
from discord import app_commands
from discord.ui import View, Button, Select
import imageio_ffmpeg

# Ottiene il percorso sicuro di FFmpeg compatibile con Render e GitHub
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# --- CONFIGURAZIONE RUOLO ---
# Sostituisci con l'ID numerico del ruolo richiesto per usare il telefono (lascia None se è aperto a tutti)
RUOLO_RICHIESTO_ID = None  # Esempio: 123456789012345678

# --- TASK AUDIO PER RIPRODURRE I SUONI NELLE VOCALI ---
async def riproduci_audio_canale(channel: discord.VoiceChannel, audio_file: str, loop: bool = False):
    vc = None
    try:
        # Verifica che il file audio esista prima di connettersi
        if not os.path.exists(audio_file):
            print(f"❌ File audio non trovato: {audio_file}")
            return

        # Connessione al canale vocale
        vc = await channel.connect()
        
        while vc.is_connected():
            fatto = asyncio.Event()

            def after_play(error):
                if error:
                    print(f"Errore nella riproduzione audio: {error}")
                fatto.set()

            # Configura la sorgente audio (assicurati che FFMPEG_PATH sia corretto o usa None se è nel PATH di sistema)
            kwargs = {"executable": FFMPEG_PATH} if FFMPEG_PATH else {}
            source = discord.FFmpegPCMAudio(audio_file, **kwargs)

            if not vc.is_playing():
                vc.play(source, after=after_play)
                await fatto.wait()

            # Se il loop è disattivato, esce dal ciclo
            if not loop:
                break
            
            # Breve pausa prima di ripetere (se è in loop)
            await asyncio.sleep(0.5)

    except discord.ClientException as ce:
        print(f"Errore di connessione vocale (già connesso?): {ce}")
    except Exception as e:
        print(f"Errore generico audio: {e}")
    finally:
        if vc and vc.is_connected():
            await vc.disconnect()


# --- 1. MODAL PER AGGIUNGERE UN CONTATTO IN RUBRICA ---
class AggiungiContattoModal(discord.ui.Modal, title="Nuovo Contatto - Evren City OS"):
    nome_contatto = discord.ui.TextInput(
        label="Nome del Contatto",
        placeholder="Es. Mario Rossi",
        required=True,
        max_length=50
    )
    numero_contatto = discord.ui.TextInput(
        label="Numero di Telefono",
        placeholder="Es. 3331234567",
        required=True,
        max_length=15
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        supabase.table("contacts").insert({
            "owner_id": user_id,
            "name": self.nome_contatto.value.strip(),
            "phone_number": self.numero_contatto.value.strip()
        }).execute()

        await interaction.response.send_message(
            f"✅ Contatto **{self.nome_contatto.value}** (`{self.numero_contatto.value}`) salvato con successo nella rubrica!",
            ephemeral=True
        )


# --- 2. MENU INTERATTIVO WHATSAPP ---
class WhatsAppChatView(View):
    def __init__(self, destinatario: str):
        super().__init__(timeout=180)
        self.destinatario = destinatario

    @discord.ui.button(label="Invia Messaggio", style=discord.ButtonStyle.green, emoji="💬")
    async def invia_messaggio(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WhatsAppMessageModal(self.destinatario))


class WhatsAppMessageModal(discord.ui.Modal, title="WhatsApp - Invia Messaggio"):
    testo_messaggio = discord.ui.TextInput(
        label="Messaggio",
        placeholder="Scrivi qui il messaggio...",
        style=discord.TextStyle.paragraph,
        required=True
    )

    def __init__(self, destinatario: str):
        super().__init__()
        self.destinatario = destinatario

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"✅ Messaggio inviato a **{self.destinatario}**:\n> {self.testo_messaggio.value}",
            ephemeral=True
        )


# --- 3. VIEW PER RISPONDERE O RIFIUTARE LA CHIAMATA IN DM ---
class RispondiChiamataView(View):
    def __init__(self, chiamante: discord.Member, destinatario: discord.Member, channel: discord.VoiceChannel, task_squillo: asyncio.Task):
        super().__init__(timeout=120)  # 2 minuti di tempo massimo
        self.chiamante = chiamante
        self.destinatario = destinatario
        self.channel = channel
        self.task_squillo = task_squillo
        self.risposta_data = False

    @discord.ui.button(label="Rispondi", style=discord.ButtonStyle.green, emoji="📞")
    async def rispondi(self, interaction: discord.Interaction, button: Button):
        self.risposta_data = True
        self.stop()
        
        # Interrompe lo squillo in corso
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

    @discord.ui.button(label="Rifiuta", style=discord.ButtonStyle.red, emoji="❌")
    async def rifiuta(self, interaction: discord.Interaction, button: Button):
        self.risposta_data = False
        self.stop()
        
        # Interrompe lo squillo
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

        # Riproduce il suono di rifiuto prima di eliminare il canale
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

# --- 4. INTERFACCIA DEL TELEFONO (OS PRINCIPALE) ---
class EvrenPhoneView(View):
    def __init__(self, user_id: str, phone_number: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.phone_number = phone_number
        self.aggiorna_selettori()

    def aggiorna_selettori(self):
        self.clear_items()
        
        res = supabase.table("contacts").select("*").eq("owner_id", self.user_id).execute()
        contacts = res.data if res.data else []

        btn_aggiungi = Button(label="Nuovo Contatto", style=discord.ButtonStyle.blurple, emoji="➕", row=0)
        btn_aggiungi.callback = self.apri_modal_contatto
        self.add_item(btn_aggiungi)

        if contacts:
            options = [discord.SelectOption(label=c["name"], description=c["phone_number"], value=str(c["phone_number"])) for c in contacts[:25]]
            
            select_chiama = Select(placeholder="📞 Seleziona contatto da chiamare", options=options, row=1)
            select_chiama.callback = self.avvia_chiamata_callback
            self.add_item(select_chiama)

            select_wa = Select(placeholder="💬 Apri chat WhatsApp", options=options, row=2)
            select_wa.callback = self.apri_whatsapp_callback
            self.add_item(select_wa)

    async def apri_modal_contatto(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AggiungiContattoModal())

    async def avvia_chiamata_callback(self, interaction: discord.Interaction):
        numero = interaction.data["values"][0] # type: ignore
        await interaction.response.defer(ephemeral=True)
        await avvia_chiamata_vocale(interaction, numero)

    async def apri_whatsapp_callback(self, interaction: discord.Interaction):
        numero = interaction.data["values"][0] # type: ignore
        res = supabase.table("contacts").select("name").eq("owner_id", self.user_id).eq("phone_number", numero).execute()
        nome_destinatario = res.data[0]["name"] if res.data else numero

        view = WhatsAppChatView(nome_destinatario)
        await interaction.response.send_message(
            f"📱 **WhatsApp - Chat con {nome_destinatario}**",
            view=view,
            ephemeral=True
        )


# --- 5. LOGICA DI AVVIO DELLA CHIAMATA VOCALE ---
async def avvia_chiamata_vocale(interaction: discord.Interaction, numero_destinatario: str):
    guild = interaction.guild
    chiamante = interaction.user

    # Cerca il proprietario del numero nella tabella dei numeri univoci degli utenti
    res = supabase.table("user_phones").select("discord_id").eq("phone_number", numero_destinatario).execute()
    
    if not res.data or len(res.data) == 0:
        await interaction.followup.send("❌ Il numero digitato non è attivo o non appartiene a nessun cittadino registrato.", ephemeral=True)
        return

    target_discord_id = res.data[0]["discord_id"]
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

    # Avvia il task audio dello squillo in loop nel canale vocale
    task_squillo = asyncio.create_task(riproduci_audio_canale(voice_channel, "squillo.mp3", loop=True))

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

    await interaction.followup.send(f"📞 Squillo in corso verso **{destinatario.display_name}**...", ephemeral=true


import random

# --- 6. COMANDO /TELEFONO ---
@bot.tree.command(name="telefono", description="Apre lo schermo del tuo smartphone di Evren City OS.")
async def telefono(interaction: discord.Interaction):
    # Controllo del ruolo richiesto (se impostato)
    if RUOLO_RICHIESTO_ID is not None:
        ruolo = interaction.guild.get_role(RUOLO_RICHIESTO_ID)
        if not ruolo or ruolo not in interaction.user.roles:
            await interaction.response.send_message(
                "❌ **Accesso Negato:** Non possiedi il ruolo necessario per utilizzare lo smartphone.", 
                ephemeral=True
            )
            return

    user_id = str(interaction.user.id)

    # Recupera il numero di telefono dell'utente dal database
    res = supabase.table("user_phones").select("phone_number").eq("discord_id", user_id).execute()
    
    if not res.data or len(res.data) == 0:
        # Genera un numero americano univoco
        while True:
            area_code = random.randint(200, 999)
            central_office = random.randint(200, 999)
            line_number = random.randint(1000, 9999)
            numero_casuale = f"+1 ({area_code}) {central_office}-{line_number}"
            
            # Verifica se questo numero esiste già nel database
            check_exist = supabase.table("user_phones").select("phone_number").eq("phone_number", numero_casuale).execute()
            
            # Se il numero non esiste, possiamo usarlo ed uscire dal ciclo
            if not check_exist.data or len(check_exist.data) == 0:
                break
        
        # Salva il nuovo numero univoco nel database associato all'utente
        try:
            supabase.table("user_phones").insert({
                "discord_id": user_id,
                "phone_number": numero_casuale
            }).execute()
            phone_number = numero_casuale
        except Exception as e:
            print(f"Errore durante la generazione automatica del numero: {e}")
            phone_number = "Errore di generazione"
    else:
        phone_number = res.data[0]["phone_number"]

    view = EvrenPhoneView(user_id, phone_number)
    
    # Messaggio abbellito con stile UI smartphone
    embed = discord.Embed(
        title="📱 Evren City OS — Smartphone",
        description="*Benvenuto nel tuo terminale personale. Gestisci la tua rubrica, effettua chiamate vocali e chatta in tempo reale.*",
        color=discord.Color.from_rgb(40, 167, 69)
    )
    embed.add_field(name="📞 Il tuo Numero", value=f"`{phone_number}`", inline=False)
    embed.set_footer(text=f"Utente: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True
    )


@bot.tree.command(name="cerca_foto", description="[Riservato Polizia] Riconosce un cittadino dalla foto tramite scansione AI remota.")
@app_commands.describe(foto="Carica la foto o il documento da analizzare")
async def cerca_foto(interaction: discord.Interaction, foto: discord.Attachment):
    # 1. Controllo se l'utente ha il ruolo di polizia
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
        # 2. Usa Playwright per aprire la pagina, lasciando che Vercel esegua l'IA e interroghi Supabase
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            await page.goto(url_target, wait_until="networkidle")

            try:
                # Attende che il div #result venga popolato con un JSON o che compaia un errore nello status
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

    # 3. Gestione dei risultati restituiti da Vercel
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

        # Estrai i dati del cittadino trovato (modifica i campi in base alle colonne della tua tabella documents)
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
        # Invia il messaggio nei messaggi privati dell'utente con i bottoni associati
        await member.send(content=welcome_text, view=WelcomeButtonsView())
    except discord.Forbidden:
        # L'utente ha i messaggi privati disabilitati
        print(f"⚠️ Impossibile inviare il DM di benvenuto a {member.display_name} (DM chiusi).")
    except Exception as e:
        print(f"❌ Errore durante l'invio del messaggio di benvenuto: {e}")

# --- SISTEMA OGGETTI (COMANDO STAFF /crea_item & INVENTARIO) ---
import discord
from discord import app_commands
from discord.ui import View, Button

# --- SUPPORTO DEPOSITI FAZIONE CON AUTOCOMPLETE ---

# --- MODAL PER DEPOSITARE O PRELEVARE DENARO ---
class FactionCashModal(discord.ui.Modal):
    def __init__(self, faction_name: str, action_type: str):
        title = "Deposita Soldi" if action_type == "deposita" else "Preleva Soldi"
        super().__init__(title=f"{title} - {faction_name}")
        self.faction_name = faction_name
        self.action_type = action_type

        self.quantita = discord.ui.TextInput(
            label="Importo in Denaro (€)",
            placeholder="Es. 5000",
            required=True,
            max_length=12
        )
        self.add_item(self.quantita)

    async def on_submit(self, interaction: discord.Interaction):
        valore = self.quantita.value.strip()
        azione_str = "depositato" if self.action_type == "deposita" else "prelevato"
        
        # Logica di aggiornamento saldo su Supabase (da collegare al tuo DB)
        await interaction.response.send_message(
            f"✅ Hai {azione_str} **€ {valore}** nella cassa della fazione **{self.faction_name}**.",
            ephemeral=True
        )


# --- MODAL INTERATTIVO PER ITEM CON CAMPO LIBERO O SCELTA ---
class FactionItemModal(discord.ui.Modal):
    def __init__(self, faction_name: str, action_type: str, item_scelto: str = ""):
        title = "Deposita Item" if action_type == "deposita" else "Preleva Item"
        super().__init__(title=f"{title} - {faction_name}")
        self.faction_name = faction_name
        self.action_type = action_type

        self.nome_item = discord.ui.TextInput(
            label="Nome dell'Item",
            placeholder="Es. Kit Medico, AK-47...",
            default=item_scelto,
            required=True,
            max_length=50
        )
        self.quantita_item = discord.ui.TextInput(
            label="Quantità",
            placeholder="Es. 1 o 5",
            required=True,
            max_length=5
        )
        self.add_item(self.nome_item)
        self.add_item(self.quantita_item)

    async def on_submit(self, interaction: discord.Interaction):
        item = self.nome_item.value.strip()
        qta = self.quantita_item.value.strip()
        azione_str = "depositato" if self.action_type == "deposita" else "prelevato"

        await interaction.response.send_message(
            f"✅ Hai {azione_str} **{qta}x {item}** per la fazione **{self.faction_name}**.",
            ephemeral=True
        )


# --- VIEW CON I PULSANTI DEL DEPOSITO FAZIONE ---
class FactionVaultView(View):
    def __init__(self, faction_name: str):
        super().__init__(timeout=300)
        self.faction_name = faction_name

    @discord.ui.button(label="Deposita Soldi", style=discord.ButtonStyle.green, emoji="💵", row=0)
    async def dep_soldi(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionCashModal(self.faction_name, "deposita"))

    @discord.ui.button(label="Preleva Soldi", style=discord.ButtonStyle.red, emoji="💸", row=0)
    async def pre_soldi(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionCashModal(self.faction_name, "preleva"))

    @discord.ui.button(label="Deposita Item", style=discord.ButtonStyle.blurple, emoji="📦", row=1)
    async def dep_item(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionItemModal(self.faction_name, "deposita"))

    @discord.ui.button(label="Preleva Item", style=discord.ButtonStyle.grey, emoji="📤", row=1)
    async def pre_item(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionItemModal(self.faction_name, "preleva"))


# --- FUNZIONI DI AUTOCOMPLETE ---
async def fazione_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    # Prende le fazioni registrate da Supabase in base a ciò che digita l'utente
    res = supabase.table("faction_roles").select("faction_name").ilike("faction_name", f"%{current}%").limit(25).execute()
    fazioni = res.data if res.data else []
    return [app_commands.Choice(name=f["faction_name"], value=f["faction_name"]) for f in fazioni]


# --- COMANDO /DEPOSITO_FAZIONE CON AUTOCOMPLETE ---
@bot.tree.command(name="deposito_fazione", description="Accedi al deposito della tua fazione basato sul tuo ruolo.")
@app_commands.describe(fazione="Nome della fazione registrata")
@app_commands.autocomplete(fazione=fazione_autocomplete)
async def deposito_fazione(interaction: discord.Interaction, fazione: str):
    user = interaction.user
    
    # Verifica il ruolo associato alla fazione
    res = supabase.table("faction_roles").select("role_id").eq("faction_name", fazione).execute()
    
    if not res.data:
        await interaction.response.send_message(f"❌ La fazione **{fazione}** non risulta registrata nel sistema.", ephemeral=True)
        return

    role_id = int(res.data[0]["role_id"])
    
    if not any(r.id == role_id for r in user.roles): # type: ignore
        await interaction.response.send_message(f"❌ Non possiedi il ruolo autorizzato per accedere a questo deposito.", ephemeral=True)
        return

    # Recupera dati deposito
    res_vault = supabase.table("faction_vaults").select("cash_balance, items_list").eq("faction_name", fazione).execute()
    saldo_soldi = res_vault.data[0].get("cash_balance", 0) if res_vault.data else 0
    lista_item = res_vault.data[0].get("items_list", "Deposito vuoto.") if res_vault.data else "Deposito vuoto."

    embed = discord.Embed(
        title=f"🏛️ Deposito Fazione: {fazione}",
        description="Gestisci le risorse della fazione tramite i pulsanti sottostanti.",
        color=discord.Color.gold()
    )
    embed.add_field(name="💰 Saldo Cassa", value=f"**€ {saldo_soldi:,.2f}**", inline=False)
    embed.add_field(name="📦 Inventario Item", value=f"```{lista_item}```", inline=False)
    embed.set_footer(text="Evren City OS • Gestione Risorse Fazione")

    view = FactionVaultView(fazione)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

import discord
from discord import app_commands

@bot.tree.command(name="portafoglio", description="Visualizza i contanti e lo stato del tuo portafoglio su Evren City OS.")
async def portafoglio(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    # Interroga Supabase per prendere i contanti dell'utente
    res = supabase.table("users").select("wallet").eq("discord_id", user_id).execute()
    
    contanti = 0
    if res.data and len(res.data) > 0:
        contanti = res.data[0].get("cash", 0)

    embed = discord.Embed(
        title="💼 Portafoglio - Evren City OS",
        description="Ecco il riepilogo del tuo denaro contante.",
        color=discord.Color.green()
    )
    embed.add_field(name="💵 Contanti", value=f"**€ {contanti:,.2f}**", inline=False)
    embed.set_footer(text="Evren City OS • Sistema Finanziario")

    await interaction.response.send_message(embed=embed, ephemeral=True)

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
async def crea_item(
    interaction: discord.Interaction,
    nome: str,
    categoria: app_commands.Choice[str],
    peso: float,
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
        "success_rate": probabilita_riuscita,
        "capacity_boost": round(capienza_zaino, 2) if categoria.value == "zaino" else 0.0
    }

    try:
        supabase.table("master_items").insert(item_data).execute()
    except Exception as e:
        await interaction.response.send_message(f"❌ Errore durante la creazione! Nome già in uso o errore DB.", ephemeral=True)
        return

    embed = discord.Embed(
        title="✨ Nuovo Oggetto Creato",
        description=f"L'oggetto **{nome}** è stato registrato.",
        color=discord.Color.purple()
    )
    embed.add_field(name="🏷️ Categoria", value=f"`{categoria.name}`", inline=True)
    embed.add_field(name="⚖️ Peso", value=f"`{peso} kg`", inline=True)
    embed.add_field(name="🎲 Probabilità Successo", value=f"`{probabilita_riuscita}%`", inline=True)
    if categoria.value == "zaino":
        embed.add_field(name="🎒 Capienza Extra", value=f"`+{capienza_zaino} kg`", inline=False)

    await interaction.response.send_message(embed=embed)


class InventoryUseView(ui.View):
    def __init__(self, user_id: int, user_items: list):
        super().__init__(timeout=120)
        self.user_id = user_id
        
        options = []
        for item in user_items[:25]:
            m = item.get("master_items", {})
            name = m.get("name", "Oggetto")
            cat = m.get("category", "N/D")
            w = m.get("weight", 0.0)
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
        res = supabase.table("inventory").select("*, master_items(*)").eq("id", item_inv_id).execute()
        if not res.data:
            await interaction.response.send_message("❌ Oggetto non trovato.", ephemeral=True)
            return

        inv_item = res.data[0]
        m_item = inv_item.get("master_items", {})
        category = m_item.get("category")
        name = m_item.get("name")
        rate = m_item.get("success_rate", 100)
        boost = float(m_item.get("capacity_boost", 0.0))

        # Test Probabilità di riuscita
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

        # Rimozione/Scalo quantita
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

    res = supabase.table("inventory").select("*, master_items(*)").eq("discord_id", str(interaction.user.id)).execute()

    embed = discord.Embed(
        title=f"🎒 Inventario di {interaction.user.display_name}",
        description=f"⚖️ **Peso Trasportato:** `{current_weight} / {max_weight} kg`",
        color=discord.Color.green() if current_weight <= max_weight else discord.Color.red()
    )

    if res.data:
        for row in res.data:
            m = row.get("master_items", {})
            name = m.get("name", "Oggetto")
            q = row.get("quantity", 1)
            w = (m.get("weight", 0.1) if m else 0.1) * q
            cat = (m.get("category", "N/D") if m else "N/D").capitalize()
            embed.add_field(name=f"📦 {name} x{q}", value=f"└ Cat: `{cat}` | Peso: `{w:.1f}kg`", inline=False)
        
        view = InventoryUseView(interaction.user.id, res.data)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        embed.description += "\n\n*Il tuo inventario è vuoto.*"
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- BANCOMAT CON PIN ---

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
        cash = float(user_data.get("cash", 0.0))

        if cash < val:
            await interaction.response.send_message(f"❌ Contanti insufficienti! Possiedi `${cash:,.2f}`.", ephemeral=True)
            return

        new_cash = cash - val
        new_bank = float(user_data.get("bank", 0.0)) + val
        supabase.table("users").update({"cash": new_cash, "bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
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
        new_cash = float(user_data.get("cash", 0.0)) + val
        supabase.table("users").update({"cash": new_cash, "bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
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
        res = supabase.table("bank_transactions").select("*").eq("discord_id", str(self.user_id)).order("created_at", desc=True).limit(8).execute()
        embed = discord.Embed(title="📜 Storico Transazioni", color=discord.Color.blue())
        if res.data:
            for tx in res.data:
                icon = "🟢" if "RICEVUTO" in tx['type'] or "DEPOSITO" in tx['type'] else "🔴"
                embed.add_field(name=f"{icon} {tx['type']} - ${tx['amount']:,.2f}", value=f"└ `{tx['details']}`", inline=False)
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
            title="🏦 Sportello Bancomat",
            description=f"• **Conto N°:** `ACC-{self.user_id}`\n• **Banca:** `${float(u.get('bank', 0)):,.2f}`\n• **Contanti:** `${float(u.get('cash', 0)):,.2f}`",
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
    @ui.button(label="✖", style=discord.ButtonStyle.danger, row=3)
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


# --- POLIZIA CAD COMPLETO (NOME, TARGA & MATRICOLA) ---

# --- MODAL PER RICERCA DIRETTA DA CAD ---

class CadSearchPlateModal(ui.Modal, title="🔍 Ricerca Veicolo per Targa"):
    plate_input = ui.TextInput(label="Inserisci la Targa", placeholder="Es. AB123CD", required=True)

    def __init__(self, officer_id: int):
        super().__init__()
        self.officer_id = officer_id

    async def on_submit(self, interaction: discord.Interaction):
        plate_search = self.plate_input.value.strip().upper()
        res = supabase.table("registered_vehicles").select("*").eq("plate", plate_search).execute()

        if not res.data:
            await interaction.response.send_message(f"❌ Nessun veicolo trovato con targa `{plate_search}`.", ephemeral=True)
            return

        vehicle = res.data[0]
        owner_id = vehicle.get("discord_id")

        doc_res = supabase.table("documents").select("*").eq("discord_id", owner_id).execute()
        owner_name = f"{doc_res.data[0]['name']} {doc_res.data[0]['surname']}" if doc_res.data else "Sconosciuto (Senza Documenti)"

        embed = discord.Embed(
            title=f"🚔 CAD - Risultato Ricerca Targa: {plate_search}",
            color=discord.Color.dark_green()
        )
        embed.add_field(name="🚗 Modello Veicolo", value=f"`{vehicle.get('model')}`", inline=True)
        embed.add_field(name="🏷️ Targa", value=f"`{vehicle.get('plate')}`", inline=True)
        embed.add_field(name="👤 Intestatario RP", value=f"`{owner_name}`", inline=False)
        embed.add_field(name="🌐 Account Discord", value=f"<@{owner_id}>", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class CadSearchSerialModal(ui.Modal, title="🔍 Ricerca Arma per Matricola"):
    serial_input = ui.TextInput(label="Inserisci la Matricola", placeholder="Es. WPN-9921", required=True)

    def __init__(self, officer_id: int):
        super().__init__()
        self.officer_id = officer_id

    async def on_submit(self, interaction: discord.Interaction):
        serial_search = self.serial_input.value.strip()
        res = supabase.table("registered_weapons").select("*").eq("serial_number", serial_search).execute()

        if not res.data:
            await interaction.response.send_message(f"❌ Nessuna arma registrata con matricola `{serial_search}`.", ephemeral=True)
            return

        weapon = res.data[0]
        owner_id = weapon.get("discord_id")

        doc_res = supabase.table("documents").select("*").eq("discord_id", owner_id).execute()
        owner_name = f"{doc_res.data[0]['name']} {doc_res.data[0]['surname']}" if doc_res.data else "Sconosciuto (Senza Documenti)"

        embed = discord.Embed(
            title=f"🚔 CAD - Risultato Ricerca Matricola: {serial_search}",
            color=discord.Color.red()
        )
        embed.add_field(name="⚔️ Modello Arma", value=f"`{weapon.get('model')}`", inline=True)
        embed.add_field(name="🔢 Matricola", value=f"`{weapon.get('serial_number')}`", inline=True)
        embed.add_field(name="👤 Intestatario RP", value=f"`{owner_name}`", inline=False)
        embed.add_field(name="🌐 Account Discord", value=f"<@{owner_id}>", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- MODAL PER VERBALI, MULTE ED ARRESTI ---

class FineModal(ui.Modal, title="🚨 Rilascia Multa"):
    reason_input = ui.TextInput(label="Motivazione Sanzione", placeholder="Es. Eccesso di velocità", required=True)
    amount_input = ui.TextInput(label="Importo Multa ($)", placeholder="Es. 500", required=True)

    def __init__(self, target_id: str, officer_name: str):
        super().__init__()
        self.target_id = target_id
        self.officer_name = officer_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.amount_input.value.strip())
            if val <= 0: raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ Inserisci un importo valido!", ephemeral=True)
            return

        supabase.table("police_fines").insert({
            "discord_id": self.target_id,
            "officer_name": self.officer_name,
            "reason": self.reason_input.value.strip(),
            "amount": round(val, 2),
            "status": "Da Pagare"
        }).execute()

        embed = discord.Embed(
            title="📄 Multa Registrata",
            description=f"• **Cittadino:** <@{self.target_id}>\n• **Importo:** `${val:,.2f}`\n• **Causale:** `{self.reason_input.value.strip()}`\n• **Agente:** `{self.officer_name}`",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ArrestModal(ui.Modal, title="🔒 Registra Arresto"):
    reason_input = ui.TextInput(label="Capo d'Imputazione", placeholder="Es. Rapina a mano armata", required=True)
    months_input = ui.TextInput(label="Mesi di Reclusione (Minuti RP)", placeholder="Es. 30", required=True)
    bail_input = ui.TextInput(label="Cauzione ($) (Opzionale)", placeholder="0 se non prevista", required=False)

    def __init__(self, target_id: str, officer_name: str):
        super().__init__()
        self.target_id = target_id
        self.officer_name = officer_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            months = int(self.months_input.value.strip())
            bail = float(self.bail_input.value.strip()) if self.bail_input.value.strip() else 0.0
        except ValueError:
            await interaction.response.send_message("❌ Inserisci valori numerici validi!", ephemeral=True)
            return

        supabase.table("police_arrests").insert({
            "discord_id": self.target_id,
            "officer_name": self.officer_name,
            "reason": self.reason_input.value.strip(),
            "months": months,
            "bail": bail
        }).execute()

        embed = discord.Embed(
            title="🚔 Arresto Registrato",
            description=f"• **Detenuto:** <@{self.target_id}>\n• **Pena:** `{months} Mesi/Minuti`\n• **Cauzione:** `${bail:,.2f}`\n• **Motivo:** `{self.reason_input.value.strip()}`",
            color=discord.Color.dark_purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ReportModal(ui.Modal, title="📝 Verbale / Rapporto Giudiziario"):
    title_input = ui.TextInput(label="Titolo Rapporto", placeholder="Es. Perquisizione e Sequestro", required=True)
    desc_input = ui.TextInput(label="Dettagli del Verbale", style=discord.TextStyle.paragraph, placeholder="Descrivi i fatti...", required=True)

    def __init__(self, target_id: str, officer_name: str):
        super().__init__()
        self.target_id = target_id
        self.officer_name = officer_name

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("police_reports").insert({
            "discord_id": self.target_id,
            "officer_name": self.officer_name,
            "title": self.title_input.value.strip(),
            "description": self.desc_input.value.strip()
        }).execute()

        embed = discord.Embed(
            title="📋 Verbale Archiviato",
            description=f"• **Soggetto:** <@{self.target_id}>\n• **Titolo:** `{self.title_input.value.strip()}`\n• **Agente:** `{self.officer_name}`",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- DETTAGLIO SCHEDA CITTADINO ---

class PoliceCadDetailView(ui.View):
    def __init__(self, citizen_doc: dict, officer_id: int):
        super().__init__(timeout=180)
        self.doc = citizen_doc
        self.officer_id = officer_id
        self.target_id_str = citizen_doc.get("discord_id")

    def _check_officer(self, interaction: discord.Interaction):
        return interaction.user.id == self.officer_id

    @ui.button(label="📋 Generalità", style=discord.ButtonStyle.primary, row=0)
    async def btn_gen(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_officer(interaction): return
        
        photo_url = self.doc.get('photo_url')

        embed = discord.Embed(
            title=f"🚔 Scheda Anagrafica: {self.doc.get('name')} {self.doc.get('surname')}",
            description=(
                f"• **Nome & Cognome:** `{self.doc.get('name')} {self.doc.get('surname')}`\n"
                f"• **Data di Nascita:** `{self.doc.get('birth_date', 'N/D')} a {self.doc.get('birth_place', 'N/D')}`\n"
                f"• **Codice Fiscale:** `{self.doc.get('cf', 'N/D')}`\n"
                f"• **N° Documento:** `{self.doc.get('doc_number', 'N/D')}`\n\n"
                f"### 🧬 Caratteristiche Fisiche:\n"
                f"• **Occhi:** `{self.doc.get('eye_color', 'N/D')}`\n"
                f"• **Capelli:** `{self.doc.get('hair_color', 'N/D')}`\n"
                f"• **Segni Particolari:** `{self.doc.get('distinct_marks', 'Nessuno')}`\n\n"
                f"• **Discord User:** `<@{self.target_id_str}>`"
            ),
            color=discord.Color.dark_blue()
        )
        
        if photo_url:
            embed.set_thumbnail(url=photo_url)

        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="🚗 Proprietà", style=discord.ButtonStyle.success, row=0)
    async def btn_prop(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_officer(interaction): return
        v_res = supabase.table("registered_vehicles").select("*").eq("discord_id", self.target_id_str).execute()
        h_res = supabase.table("registered_properties").select("*").eq("discord_id", self.target_id_str).execute()

        v_text = "\n".join([f"• **{v['model']}** - Targa: `{v['plate']}`" for v in v_res.data]) if v_res.data else "*Nessun veicolo.*"
        h_text = "\n".join([f"• **{h['address']}** ({h['property_type']})" for h in h_res.data]) if h_res.data else "*Nessun immobile.*"

        embed = discord.Embed(
            title=f"🚘 Veicoli & Case - {self.doc.get('name')} {self.doc.get('surname')}",
            description=f"### 🚗 Veicoli:\n{v_text}\n\n### 🏠 Immobili:\n{h_text}",
            color=discord.Color.dark_green()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="🔫 Licenze", style=discord.ButtonStyle.secondary, row=0)
    async def btn_weapons(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_officer(interaction): return
        g_res = supabase.table("registered_weapons").select("*").eq("discord_id", self.target_id_str).execute()
        l_res = supabase.table("gun_licenses").select("*").eq("discord_id", self.target_id_str).execute()
        d_res = supabase.table("driver_licenses").select("*").eq("discord_id", self.target_id_str).execute()

        g_text = "\n".join([f"• **{w['model']}** - Mat: `{w['serial_number']}`" for w in g_res.data]) if g_res.data else "*Nessuna arma.*"
        l_text = "\n".join([f"• **{l['license_type']}** (`{l['status']}`)" for l in l_res.data]) if l_res.data else "*Nessun porto d'armi.*"
        d_text = "\n".join([f"• Patente **{d['license_type']}** (`{d['status']}`)" for d in d_res.data]) if d_res.data else "*Nessuna patente.*"

        embed = discord.Embed(
            title=f"🛡️ Licenze e Armi - {self.doc.get('name')} {self.doc.get('surname')}",
            description=f"### 🔫 Armi Registrate:\n{g_text}\n\n### 📜 Porto d'Armi:\n{l_text}\n\n### 💳 Patenti:\n{d_text}",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="⚖️ Fedina & Multe", style=discord.ButtonStyle.danger, row=0)
    async def btn_records(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_officer(interaction): return

        fines_res = supabase.table("police_fines").select("*").eq("discord_id", self.target_id_str).execute()
        arrests_res = supabase.table("police_arrests").select("*").eq("discord_id", self.target_id_str).execute()
        reports_res = supabase.table("police_reports").select("*").eq("discord_id", self.target_id_str).execute()

        f_text = "\n".join([f"• ID #{f['id']} - **${f['amount']:,.2f}** | `{f['reason']}` | Status: **{f['status']}**" for f in fines_res.data]) if fines_res.data else "*Nessuna sanzione.*"
        a_text = "\n".join([f"• **{a['months']} Mesi** | Motivo: `{a['reason']}` | Agente: `{a['officer_name']}`" for a in arrests_res.data]) if arrests_res.data else "*Nessun arresto a carico.*"
        r_text = "\n".join([f"• **{r['title']}**: {r['description']} (Agente: `{r['officer_name']}`)" for r in reports_res.data]) if reports_res.data else "*Nessun verbale.*"

        embed = discord.Embed(
            title=f"⚖️ Casellario Giudiziario - {self.doc.get('name')} {self.doc.get('surname')}",
            description=f"### 💶 Sanzioni & Multe:\n{f_text}\n\n### ⛓️ Storico Arresti:\n{a_text}\n\n### 📝 Verbali & Rapporti:\n{r_text}",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="➕ Multa", style=discord.ButtonStyle.danger, row=1)
    async def add_fine(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_officer(interaction): return
        await interaction.response.send_modal(FineModal(self.target_id_str, interaction.user.display_name))

    @ui.button(label="➕ Arresto", style=discord.ButtonStyle.secondary, row=1)
    async def add_arrest(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_officer(interaction): return
        await interaction.response.send_modal(ArrestModal(self.target_id_str, interaction.user.display_name))

    @ui.button(label="➕ Verbale", style=discord.ButtonStyle.primary, row=1)
    async def add_report(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_officer(interaction): return
        await interaction.response.send_modal(ReportModal(self.target_id_str, interaction.user.display_name))


# --- MENU SCHERMATA INIZIALE CAD CON SELEZIONE E BOTTONI RAPIDI ---

class CitizenSelectMenu(ui.Select):
    def __init__(self, citizens_list: list, officer_id: int):
        options = []
        for c in citizens_list[:25]:
            options.append(discord.SelectOption(
                label=f"{c.get('name')} {c.get('surname')}",
                value=c.get("discord_id"),
                description=f"CF: {c.get('cf')} | Doc: {c.get('doc_number')}"
            ))
        super().__init__(placeholder="Seleziona cittadino per Nome & Cognome...", min_values=1, max_values=1, options=options)
        self.citizens_list = citizens_list
        self.officer_id = officer_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.officer_id: return
        selected_id = self.values[0]
        doc = next((c for c in self.citizens_list if c.get("discord_id") == selected_id), None)

        if doc:
            view = PoliceCadDetailView(doc, self.officer_id)
            embed = discord.Embed(
                title=f"🚔 Terminale Polizia - {doc.get('name')} {doc.get('surname')}",
                description="Usa i pulsanti per consultare la scheda o registrare nuovi atti:",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)


class PoliceCadSelectView(ui.View):
    def __init__(self, citizens_list: list, officer_id: int):
        super().__init__(timeout=120)
        self.officer_id = officer_id
        # Aggiunge il menu a tendina
        self.add_item(CitizenSelectMenu(citizens_list, officer_id))

    @ui.button(label="🔍 Cerca Targa", style=discord.ButtonStyle.success, row=1)
    async def btn_search_plate(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.officer_id:
            await interaction.response.send_modal(CadSearchPlateModal(self.officer_id))

    @ui.button(label="🔍 Cerca Matricola Arma", style=discord.ButtonStyle.danger, row=1)
    async def btn_search_serial(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id == self.officer_id:
            await interaction.response.send_modal(CadSearchSerialModal(self.officer_id))


# --- COMANDO UNICO `/cad_polizia` ---

@bot.tree.command(name="cad_polizia", description="[POLIZIA] Terminale operativo per ricerche anagrafiche, targhe e matricole.")
async def cad_polizia(interaction: discord.Interaction):
    if RUOLO_POLIZIA_ID:
        police_role = interaction.guild.get_role(RUOLO_POLIZIA_ID)
        if police_role and police_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Riservato alle Forze dell'Ordine!", ephemeral=True)
            return

    res = supabase.table("documents").select("*").order("name", desc=False).execute()
    if not res.data:
        await interaction.response.send_message("❌ Nessun cittadino presente nel database.", ephemeral=True)
        return

    view = PoliceCadSelectView(res.data, interaction.user.id)
    embed = discord.Embed(
        title="🚔 CAD Polizia di Stato - Centrale Operativa",
        description=(
            "Seleziona un **cittadino** dal menu a tendina oppure premi uno dei bottoni sottostanti "
            "per cercare direttamente un veicolo tramite **targa** o un'arma tramite **matricola**."
        ),
        color=discord.Color.dark_blue()
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --- COMANDO CITTADINO PER PAGARE LE MULTE ---

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

        # Scalo i soldi dal conto e aggiorno lo stato della multa
        new_bank = bank_balance - amount
        supabase.table("users").update({"bank": new_bank}).eq("discord_id", str(self.user_id)).execute()
        supabase.table("police_fines").update({"status": "Pagata"}).eq("id", fine_id).execute()

        # Log transazione
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

import io
import random
import string
import aiohttp
import discord
from discord import app_commands
from playwright.async_api import async_playwright

# Inserisci qui la tua API Key di ImgBB
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
async def upload_to_imgbb(foto: discord.Attachment) -> str:
    url = "https://api.imgbb.com/1/upload"
    
    foto_bytes = await foto.read()
    
    # Usiamo FormData di aiohttp per gestire correttamente testo e file insieme
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

# --- 2. FUNZIONI DI SUPPORTO (Codice Fiscale e Numero Documento) ---
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


# --- 3. FUNZIONE CHE CREA L'IMMAGINE REALISTICA (HTML/PLAYWRIGHT) ---
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
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                border: 4px solid #1a252f;
                box-sizing: border-box;
                position: relative;
            }}
            .header {{
                background-color: #1a252f;
                color: white;
                padding: 12px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 18px;
                letter-spacing: 1px;
            }}
            .header span {{
                font-size: 13px;
                color: #bdc3c7;
            }}
            .body-content {{
                padding: 20px;
                display: flex;
                gap: 20px;
            }}
            .foto-container {{
                width: 140px;
                height: 180px;
                border: 2px solid #1a252f;
                background: #fff;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
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
                gap: 10px;
            }}
            .field {{
                display: flex;
                flex-direction: column;
                border-bottom: 1px solid #dcdde1;
                padding-bottom: 3px;
            }}
            .field.full {{
                grid-column: span 2;
            }}
            .label {{
                font-size: 10px;
                text-transform: uppercase;
                color: #7f8c8d;
                font-weight: bold;
            }}
            .value {{
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
            }}
            .footer {{
                position: absolute;
                bottom: 12px;
                left: 20px;
                right: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 12px;
                color: #7f8c8d;
                border-top: 1px solid #dcdde1;
                padding-top: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>REPUBBLICA DI EVREN CITY</h1>
            <span>CARTA D'IDENTITÀ ELETTRONICA</span>
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
                    <span class="label">Nome / Name</span>
                    <span class="value">{nome.capitalize()}</span>
                </div>
                <div class="field full">
                    <span class="label">Data e Luogo di Nascita / Date & Place</span>
                    <span class="value">{birth_date} - {birth_place}</span>
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
                    <span class="label">Segni Particolari / Distinct Marks</span>
                    <span class="value">{segni_particolari}</span>
                </div>
            </div>
        </div>

        <div class="footer">
            <span>Codice Fiscale: <b>{cf}</b></span>
            <span>N. Doc: <b>{doc_number}</b></span>
        </div>
    </body>
    </html>
    """

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


# --- 4. COMANDO CREA DOCUMENTI ---
@bot.tree.command(name="crea_documenti", description="Genera i tuoi documenti identificativi completi di caratteristiche fisiche e foto.")
async def crea_documenti(
    interaction: discord.Interaction, 
    nome: str, 
    cognome: str, 
    data_nascita: str, 
    luogo_nascita: str,
    colore_occhi: str,
    colore_capelli: str,
    foto: discord.Attachment,
    segni_particolari: str = "Nessuno"
):
    user_id = str(interaction.user.id)
    existing = supabase.table("documents").select("*").eq("discord_id", user_id).execute()

    if existing.data:
        doc = existing.data[0]
        await interaction.response.send_message(f"❌ Documenti già esistenti!\nCF: `{doc['cf']}`", ephemeral=True)
        return

    if not foto.content_type or not foto.content_type.startswith("image/"):
        await interaction.response.send_message("❌ Il file allegato deve essere un'immagine valida (PNG, JPG, ecc.)!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Carica automaticamente l'immagine su ImgBB usando la funzione dedicata
        photo_url = await upload_to_imgbb(foto)
    except Exception as e:
        await interaction.followup.send(f"❌ Errore durante il caricamento della foto su ImgBB: {e}", ephemeral=True)
        return

    cf = genera_codice_fiscale(nome, cognome)
    doc_num = genera_num_documento()

    supabase.table("documents").insert({
        "discord_id": user_id,
        "name": nome.capitalize(),
        "surname": cognome.capitalize(),
        "birth_date": data_nascita,
        "birth_place": luogo_nascita.capitalize(),
        "eye_color": colore_occhi.capitalize(),
        "hair_color": colore_capelli.capitalize(),
        "distinct_marks": segni_particolari,
        "photo_url": photo_url,
        "cf": cf,
        "doc_number": doc_num
    }).execute()

    # Genera l'immagine grafica realistica del documento
    file_documento = await genera_carta_identita(
        nome=nome,
        cognome=cognome,
        birth_date=data_nascita,
        birth_place=luogo_nascita,
        cf=cf,
        doc_number=doc_num,
        photo_url=photo_url,
        colore_occhi=colore_occhi,
        colore_capelli=colore_capelli,
        segni_particolari=segni_particolari
    )
    
    await interaction.followup.send(
        content="✅ **Documenti creati con successo!** Ecco la tua carta d'identità ufficiale:", 
        file=file_documento, 
        ephemeral=True
    )


# --- 5. COMANDO MOSTRA DOCUMENTO ---
@bot.tree.command(name="mostra_documento", description="Mostra la tua carta d'identità ufficiale in chat.")
async def mostra_documento(interaction: discord.Interaction):
    await interaction.response.defer()
    
    user_id = str(interaction.user.id)
    response = supabase.table("documents").select("*").eq("discord_id", user_id).execute()
    
    if not response.data:
        await interaction.followup.send("❌ Non possiedi ancora un documento registrato! Usa `/crea_documenti` per crearlo.", ephemeral=True)
        return
        
    doc = response.data[0]
    
    # Genera l'immagine grafica riprendendo i dati salvati nel database
    file_documento = await genera_carta_identita(
        nome=doc["name"],
        cognome=doc["surname"],
        birth_date=doc["birth_date"],
        birth_place=doc["birth_place"],
        cf=doc["cf"],
        doc_number=doc["doc_number"],
        photo_url=doc["photo_url"],
        colore_occhi=doc["eye_color"],
        colore_capelli=doc["hair_color"],
        segni_particolari=doc["distinct_marks"]
    )
    
    await interaction.followup.send(file=file_documento)

@bot.tree.command(name="registra_veicolo", description="[MOTORIZZAZIONE] Registra un veicolo con targa.")
async def registra_veicolo(interaction: discord.Interaction, proprietario: discord.Member, modello: str, targa: str):
    if RUOLO_MOTORIZZAZIONE_ID and interaction.guild.get_role(RUOLO_MOTORIZZAZIONE_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato alla Motorizzazione!", ephemeral=True)
        return

    supabase.table("registered_vehicles").insert({"discord_id": str(proprietario.id), "model": modello, "plate": targa.upper()}).execute()
    embed = discord.Embed(title="🚗 Veicolo Immatricolato", description=f"• Proprietario: {proprietario.mention}\n• Modello: `{modello}`\n• Targa: `{targa.upper()}`", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="registra_patente", description="[MOTORIZZAZIONE] Rilascia una patente di guida.")
async def registra_patente(interaction: discord.Interaction, cittadino: discord.Member, tipo_patente: str):
    if RUOLO_MOTORIZZAZIONE_ID and interaction.guild.get_role(RUOLO_MOTORIZZAZIONE_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato alla Motorizzazione!", ephemeral=True)
        return

    supabase.table("driver_licenses").insert({"discord_id": str(cittadino.id), "license_type": tipo_patente.upper(), "status": "Valida"}).execute()
    embed = discord.Embed(title="💳 Patente Rilasciata", description=f"• Cittadino: {cittadino.mention}\n• Tipo Patente: `{tipo_patente.upper()}`", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="registra_arma", description="[ARMERIA] Registra una matricola d'arma a un cittadino.")
async def registra_arma(interaction: discord.Interaction, acquirente: discord.Member, matricola: str, modello: str):
    if RUOLO_ARMERIA_ID and interaction.guild.get_role(RUOLO_ARMERIA_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato all'Armeria!", ephemeral=True)
        return

    supabase.table("registered_weapons").insert({"discord_id": str(acquirente.id), "model": modello, "serial_number": matricola}).execute()
    embed = discord.Embed(title="📜 Arma Registrata", description=f"• Intestatario: {acquirente.mention}\n• Modello: `{modello}`\n• Matricola: `{matricola}`", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="registra_porto_darmi", description="[POLIZIA] Rilascia un porto d'armi.")
async def registra_porto_darmi(interaction: discord.Interaction, cittadino: discord.Member, tipo_licenza: str, numero_licenza: str):
    if RUOLO_POLIZIA_ID and interaction.guild.get_role(RUOLO_POLIZIA_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato alla Polizia!", ephemeral=True)
        return

    supabase.table("gun_licenses").insert({"discord_id": str(cittadino.id), "license_type": tipo_licenza, "license_number": numero_licenza, "status": "Attivo"}).execute()
    embed = discord.Embed(title="🛡️ Porto d'Armi Registrato", description=f"• Intestatario: {cittadino.mention}\n• Licenza: `{tipo_licenza}`\n• N°: `{numero_licenza}`", color=discord.Color.dark_blue())
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="registra_casa", description="[IMMOBILIARE] Registra un immobile.")
async def registra_casa(interaction: discord.Interaction, proprietario: discord.Member, indirizzo: str, tipologia: str):
    if RUOLO_IMMOBILIARE_ID and interaction.guild.get_role(RUOLO_IMMOBILIARE_ID) not in interaction.user.roles:
        await interaction.response.send_message("❌ Riservato all'Agenzia Immobiliare!", ephemeral=True)
        return

    supabase.table("registered_properties").insert({"discord_id": str(proprietario.id), "address": indirizzo, "property_type": tipologia}).execute()
    embed = discord.Embed(title="🏠 Immobile Registrato", description=f"• Proprietario: {proprietario.mention}\n• Indirizzo: `{indirizzo}`\n• Categoria: `{tipologia}`", color=discord.Color.gold())
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- EVENTO READY E AVVIO ---

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot online come {bot.user}")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.run(DISCORD_TOKEN)