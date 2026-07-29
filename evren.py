import os
import io
import json
import random
import string
import threading
import asyncio
import aiohttp
import numpy as np
import imageio_ffmpeg
from flask import Flask, jsonify

import discord
from discord import app_commands, ui
from discord.ext import commands
from discord.ui import View, Button, Select
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.async_api import async_playwright

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# --- CONFIGURAZIONE RUOLI SPECIFICI ---
RUOLO_STAFF_ID = 1521205969269555351           # Permesso per comandi Staff / Amministrazione
RUOLO_BANCOMAT_ID = 123456789012345677        # Permesso per accedere al Bancomat (opzionale)
RUOLO_ARMERIA_ID = 123456789012345678        # Permesso per registrare ed emettere armi
RUOLO_MOTORIZZAZIONE_ID = 123456789012345679  # Permesso per registrare veicoli e patenti
RUOLO_POLIZIA_ID = 1521205969269555351         # Permesso per CAD Polizia, Porto d'Armi, Cerca Foto
RUOLO_IMMOBILIARE_ID = 123456789012345681     # Permesso per registrare le case/immobili
RUOLO_RICHIESTO_ID = None                     # Permesso per lo smartphone (None = aperto a tutti)

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
            "max_weight": 10.0
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

def genera_matricola_arma() -> str:
    parte1 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
    parte2 = "".join(random.choices(string.digits + string.ascii_uppercase, k=4))
    return f"{parte1}-{parte2}"

async def upload_to_imgbb(foto: discord.Attachment) -> str:
    url = "https://api.imgbb.com/1/upload"
    foto_bytes = await foto.read()
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

async def riproduci_audio_canale(channel: discord.VoiceChannel, audio_file: str, loop: bool = False):
    vc = None
    try:
        if not os.path.exists(audio_file):
            print(f"❌ File audio non trovato: {audio_file}")
            return

        vc = await channel.connect()
        while vc.is_connected():
            fatto = asyncio.Event()

            def after_play(error):
                if error:
                    print(f"Errore riproduzione audio: {error}")
                fatto.set()

            kwargs = {"executable": FFMPEG_PATH} if FFMPEG_PATH else {}
            source = discord.FFmpegPCMAudio(audio_file, **kwargs)

            if not vc.is_playing():
                vc.play(source, after=after_play)
                await fatto.wait()

            if not loop:
                break
            await asyncio.sleep(0.5)

    except Exception as e:
        print(f"Errore audio: {e}")
    finally:
        if vc and vc.is_connected():
            await vc.disconnect()


# --- BENVENUTO E BOTTONI GUDA ---

class WelcomeButtonsView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="Bottone N1", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1500844219424706581"))
        self.add_item(ui.Button(label="Bottone N2", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1252225171553652787"))
        self.add_item(ui.Button(label="Bottone N3", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1374421195163963553"))
        self.add_item(ui.Button(label="Bottone N4", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1519623994591019189"))
        self.add_item(ui.Button(label="Bottone N5", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1252225106785337355"))
        self.add_item(ui.Button(label="Bottone N6", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1503750254028390580"))


@bot.event
async def on_member_join(member: discord.Member):
    welcome_text = (
        "✦ **BENVENUTO SU EVREN!** ✦\n"
        "Ecco i passaggi fondamentali per iniziare la tua avventura:\n\n"
        "> 🔓 **1. Sblocco Canali**\n"
        "> Se non vedi tutti i canali, segui la guida iniziale premendo **Bottone N1** per sbloccarli.\n> \n"
        "> 📜 **2. Regolamenti**\n"
        "> Leggi le linee guida nei canali associati a **Bottone N2**, **Bottone N3** e **Bottone N4**.\n> \n"
        "> 📝 **3. Background**\n"
        "> Scrivi la storia del tuo personaggio seguendo i modelli nella sezione **Bottone N5**.\n> \n"
        "> 🛡️ **4. Whitelist (WL)**\n"
        "> Invia la tua richiesta di WL nel canale **Bottone N6** per completare l'accesso.\n\n"
        "Hai dubbi o domande? Lo staff è sempre a tua disposizione. Buon divertimento! ✨"
    )
    try:
        await member.send(content=welcome_text, view=WelcomeButtonsView())
    except Exception:
        pass


# --- MODULO 1: DOCUMENTI IDENTITÀ & PATENTI & PORTO D'ARMI ---

@bot.tree.command(name="crea_carta_identita", description="[Staff] Registra una Carta d'Identità per un cittadino.")
@app_commands.describe(utente="Cittadino a cui rilasciare il documento", nome="Nome RP", cognome="Cognome RP", foto="Foto volto del personaggio")
async def crea_carta_identita(interaction: discord.Interaction, utente: discord.Member, nome: str, cognome: str, foto: discord.Attachment):
    ruolo_staff = interaction.guild.get_role(RUOLO_STAFF_ID)
    if not ruolo_staff or ruolo_staff not in interaction.user.roles:
        await interaction.response.send_message("❌ **Accesso Negato:** Non possiedi i permessi per rilasciare documenti.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        photo_url = await upload_to_imgbb(foto)
    except Exception as e:
        await interaction.followup.send(f"❌ Errore nel caricamento della foto: {e}", ephemeral=True)
        return

    cf = genera_codice_fiscale(nome, cognome)
    doc_num = genera_num_documento()

    dati = {
        "discord_id": str(utente.id),
        "first_name": nome.strip().capitalize(),
        "last_name": cognome.strip().capitalize(),
        "fiscal_code": cf,
        "doc_number": doc_num,
        "photo_url": photo_url
    }

    try:
        supabase.table("identity_cards").upsert(dati, on_conflict="discord_id").execute()
        get_or_create_user(utente.id, utente.name)

        embed = discord.Embed(title="🆔 Carta d'Identità - Evren City", color=discord.Color.blue())
        embed.add_field(name="👤 Nome & Cognome", value=f"{nome} {cognome}", inline=True)
        embed.add_field(name="📄 Codice Fiscale", value=f"`{cf}`", inline=True)
        embed.add_field(name="🔢 N. Documento", value=f"`{doc_num}`", inline=True)
        embed.set_thumbnail(url=photo_url)
        embed.set_footer(text=f"Titolare: {utente.display_name}")

        await interaction.followup.send(content=f"✅ Carta d'Identità creata con successo per {utente.mention}!", embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Errore durante il salvataggio: {e}", ephemeral=True)


@bot.tree.command(name="mostra_carta_identita", description="Mostra la tua Carta d'Identità o quella di un cittadino presente.")
@app_commands.describe(utente="Utente di cui visionare il documento (Opzionale)")
async def mostra_carta_identita(interaction: discord.Interaction, utente: discord.Member = None):
    target = utente or interaction.user
    res = supabase.table("identity_cards").select("*").eq("discord_id", str(target.id)).execute()

    if not res.data:
        msg = "❌ Non possiedi ancora una Carta d'Identità." if target == interaction.user else f"❌ **{target.display_name}** non possiede una Carta d'Identità registrata."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    dati = res.data[0]
    embed = discord.Embed(title="🆔 Carta d'Identità - Evren City", color=discord.Color.blue())
    embed.add_field(name="👤 Nome & Cognome", value=f"{dati['first_name']} {dati['last_name']}", inline=True)
    embed.add_field(name="📄 Codice Fiscale", value=f"`{dati['fiscal_code']}`", inline=True)
    embed.add_field(name="🔢 N. Documento", value=f"`{dati['doc_number']}`", inline=True)
    if dati.get("photo_url"):
        embed.set_thumbnail(url=dati["photo_url"])
    embed.set_footer(text=f"Titolare: {target.display_name}")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="crea_patente", description="[Motorizzazione] Rilascia una patente di guida ad un cittadino.")
@app_commands.describe(utente="Cittadino", categorie="Es. B, A, C", punti="Punti iniziali (Default 20)")
async def crea_patente(interaction: discord.Interaction, utente: discord.Member, categorie: str, punti: int = 20):
    ruolo_moto = interaction.guild.get_role(RUOLO_MOTORIZZAZIONE_ID)
    if not ruolo_moto or ruolo_moto not in interaction.user.roles:
        await interaction.response.send_message("❌ **Accesso Negato:** Comando riservato alla Motorizzazione.", ephemeral=True)
        return

    num_patente = f"PAT-{genera_num_documento()}"
    dati = {
        "discord_id": str(utente.id),
        "license_number": num_patente,
        "categories": categorie.upper(),
        "points": punti
    }

    supabase.table("driving_licenses").upsert(dati, on_conflict="discord_id").execute()
    await interaction.response.send_message(f"✅ Patente `{num_patente}` rilasciata a {utente.mention} per le categorie: **{categorie.upper()}** ({punti} punti).", ephemeral=True)


@bot.tree.command(name="mostra_patente", description="Mostra la patente di guida.")
async def mostra_patente(interaction: discord.Interaction, utente: discord.Member = None):
    target = utente or interaction.user
    res = supabase.table("driving_licenses").select("*").eq("discord_id", str(target.id)).execute()

    if not res.data:
        await interaction.response.send_message("❌ Nessuna patente trovata per questo cittadino.", ephemeral=True)
        return

    dati = res.data[0]
    embed = discord.Embed(title="🚗 Patente di Guida - Evren City", color=discord.Color.green())
    embed.add_field(name="🔢 N. Patente", value=f"`{dati['license_number']}`", inline=True)
    embed.add_field(name="🚗 Categorie", value=f"`{dati['categories']}`", inline=True)
    embed.add_field(name="💯 Punti Residui", value=f"**{dati['points']} / 20**", inline=False)
    embed.set_footer(text=f"Titolare: {target.display_name}")

    await interaction.response.send_message(embed=embed)


# --- MODULO 2: ARMERIA & BANCO POLIZIA (CAD) ---

@bot.tree.command(name="registra_arma", description="[Armeria/Polizia] Registra una nuova arma a nome di un cittadino.")
@app_commands.describe(utente="Proprietario dell'arma", tipo_arma="Modello dell'arma (es. Glock-17, AK-47)")
async def registra_arma(interaction: discord.Interaction, utente: discord.Member, tipo_arma: str):
    ruolo_armeria = interaction.guild.get_role(RUOLO_ARMERIA_ID)
    ruolo_polizia = interaction.guild.get_role(RUOLO_POLIZIA_ID)
    
    if not (ruolo_armeria in interaction.user.roles or ruolo_polizia in interaction.user.roles):
        await interaction.response.send_message("❌ **Accesso Negato:** Non sei autorizzato a registrare armi da fuoco.", ephemeral=True)
        return

    matricola = genera_matricola_arma()
    supabase.table("weapons_registry").insert({
        "serial_number": matricola,
        "owner_discord_id": str(utente.id),
        "weapon_type": tipo_arma.strip(),
        "registered_by": interaction.user.display_name
    }).execute()

    embed = discord.Embed(title="🔫 Arma Registrata nel Registro Statale", color=discord.Color.dark_red())
    embed.add_field(name="👤 Titolare", value=utente.mention, inline=True)
    embed.add_field(name="🔫 Modello Arma", value=f"**{tipo_arma}**", inline=True)
    embed.add_field(name="🔢 Matricola Unica", value=f"`{matricola}`", inline=False)
    embed.set_footer(text=f"Agente/Armaiolo: {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed)

import discord
from discord.ui import View, Button, Modal, TextInput, Select
from discord import app_commands

# --- 1. SCHEDA CITTADINO INTERATTIVA CON BOTTONI ---
class CADCitizenProfile(View):
    def __init__(self, target_discord_id: str, guild: discord.Guild, requester: discord.Member):
        super().__init__(timeout=300)
        self.discord_id = str(target_discord_id)
        self.guild = guild
        self.requester = requester

        self.res_doc = supabase.table("documents").select("*").eq("discord_id", self.discord_id).execute()
        self.res_pat = supabase.table("driver_licenses").select("*").eq("discord_id", self.discord_id).execute()
        self.res_porto = supabase.table("gun_licenses").select("*").eq("discord_id", self.discord_id).execute()
        self.res_armi = supabase.table("registered_weapons").select("*").eq("discord_id", self.discord_id).execute()
        self.res_veh = supabase.table("registered_vehicles").select("*").eq("discord_id", self.discord_id).execute()
        self.res_prop = supabase.table("registered_properties").select("*").eq("discord_id", self.discord_id).execute()
        self.res_fines = supabase.table("police_fines").select("*").eq("discord_id", self.discord_id).execute()
        self.res_arrests = supabase.table("police_arrests").select("*").eq("discord_id", self.discord_id).execute()
        self.res_reports = supabase.table("police_reports").select("*").eq("discord_id", self.discord_id).execute()

        member = self.guild.get_member(int(self.discord_id)) if self.discord_id.isdigit() else None
        self.target_name = member.display_name if member else f"ID: {self.discord_id}"

    @discord.ui.button(label="Identità & Licenze", style=discord.ButtonStyle.primary, emoji="🆔", row=0)
    async def btn_identita(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title=f"🚨 CAD Polizia - Anagrafica: {self.target_name}", color=discord.Color.blue())
        
        if self.res_doc.data:
            d = self.res_doc.data[0]
            embed.add_field(name="👤 Nome Completo", value=f"{d['name']} {d['surname']}", inline=True)
            embed.add_field(name="📜 CF", value=f"`{d['cf']}`", inline=True)
            embed.add_field(name="📄 N. Documento", value=f"`{d['doc_number']}`", inline=True)
            embed.add_field(name="🎂 Nato/a il", value=f"{d['birth_date']} ({d.get('birth_place', 'N/D')})", inline=True)
            if d.get("photo_url"):
                embed.set_thumbnail(url=d["photo_url"])
        else:
            embed.add_field(name="🆔 Carta d'Identità", value="❌ *Nessun documento registrato.*", inline=False)

        if self.res_pat.data:
            patenti = "\n".join([f"• tipo: `{p['license_type']}` | Stato: **{p.get('status', 'Attiva')}**" for p in self.res_pat.data])
            embed.add_field(name="🚗 Patenti di Guida", value=patenti, inline=False)
        else:
            embed.add_field(name="🚗 Patenti di Guida", value="❌ *Nessuna patente.*", inline=False)

        if self.res_porto.data:
            porti = "\n".join([f"• Tipo: `{p['license_type']}` | Stato: **{p.get('status', 'Attivo')}**" for p in self.res_porto.data])
            embed.add_field(name="📜 Porto d'Armi", value=porti, inline=False)
        else:
            embed.add_field(name="📜 Porto d'Armi", value="❌ *Nessun porto d'armi registrato.*", inline=False)

        embed.set_footer(text=f"Agente: {self.requester.display_name}")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Armi", style=discord.ButtonStyle.danger, emoji="🔫", row=0)
    async def btn_armi(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title=f"🚨 CAD Polizia - Armi Registrate: {self.target_name}", color=discord.Color.dark_red())
        if self.res_armi.data:
            lista = "\n".join([f"🔹 **{a['model']}** (Matricola: `{a['serial_number']}`)" for a in self.res_armi.data])
            embed.add_field(name="🔫 Registro Armi", value=lista, inline=False)
        else:
            embed.add_field(name="🔫 Registro Armi", value="🟢 *Nessuna arma intestata.*", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Veicoli", style=discord.ButtonStyle.success, emoji="🚘", row=0)
    async def btn_veicoli(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title=f"🚨 CAD Polizia - Motorizzazione: {self.target_name}", color=discord.Color.gold())
        if self.res_veh.data:
            lista = "\n".join([f"🚘 **{v['model']}** — Targa: `{v['plate'].upper()}`" for v in self.res_veh.data])
            embed.add_field(name="🚘 Veicoli Intestati", value=lista, inline=False)
        else:
            embed.add_field(name="🚘 Veicoli Intestati", value="🟢 *Nessun veicolo intestato.*", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Immobili", style=discord.ButtonStyle.secondary, emoji="🏠", row=0)
    async def btn_immobili(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title=f"🚨 CAD Polizia - Catasto: {self.target_name}", color=discord.Color.purple())
        if self.res_prop.data:
            lista = "\n".join([f"🏠 **{pr['property_type']}** in {pr['address']}" for pr in self.res_prop.data])
            embed.add_field(name="🏠 Immobili Registrati", value=lista, inline=False)
        else:
            embed.add_field(name="🏠 Immobili Registrati", value="🟢 *Nessun immobile intestato.*", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Precedenti, Multe & Verbali", style=discord.ButtonStyle.primary, emoji="⚖️", row=1)
    async def btn_penale(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(title=f"🚨 CAD Polizia - Casellario Giudiziale: {self.target_name}", color=discord.Color.dark_purple())
        
        # Multe
        if self.res_fines.data:
            multe = "\n".join([f"💶 **€{f['amount']}** - {f['reason']} (Stato: `{f.get('status', 'Da Pagare')}`)" for f in self.res_fines.data[:3]])
            embed.add_field(name="📋 Multe", value=multe, inline=False)
        else:
            embed.add_field(name="📋 Multe", value="🟢 *Nessuna multa registrata.*", inline=False)

        # Arresti
        if self.res_arrests.data:
            arresti = "\n".join([f"🔒 **{a['reason']}** ({a['months']} mesi) - Agente: {a['officer_name']}" for a in self.res_arrests.data[:3]])
            embed.add_field(name="🚨 Precedenti / Arresti", value=arresti, inline=False)
        else:
            embed.add_field(name="🚨 Precedenti / Arresti", value="🟢 *Nessun arresto a carico.*", inline=False)

        # Verbali / Rapporti
        if self.res_reports.data:
            verbali = "\n".join([f"📄 **{r['title']}**: {r['description']} (Agente: {r['officer_name']})" for r in self.res_reports.data[:3]])
            embed.add_field(name="📝 Verbali di Polizia", value=verbali, inline=False)
        else:
            embed.add_field(name="📝 Verbali di Polizia", value="🟢 *Nessun verbale registrato.*", inline=False)

        embed.set_footer(text=f"Agente: {self.requester.display_name}")
        await interaction.response.edit_message(embed=embed, view=self)


# --- 2. MODAL DI REGISTRAZIONE AZIONI POLIZIA ---

# MODAL: EMODI EMISSIONE MULTA
class MultaModal(Modal, title='Registra Sanzione Pecuniaria'):
    discord_id = TextInput(label='ID Discord del Cittadino', placeholder='Incolla ID Discord...', required=True)
    importo = TextInput(label='Importo (€)', placeholder='Es. 500', required=True)
    causale = TextInput(label='Motivazione / Causa', style=discord.TextStyle.paragraph, placeholder='Es. Eccesso di velocità, guida pericolosa...', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("police_fines").insert({
            "discord_id": self.discord_id.value.strip(),
            "officer_name": interaction.user.display_name,
            "reason": self.causale.value.strip(),
            "amount": float(self.importo.value.strip()),
            "status": "Da Pagare"
        }).execute()

        await interaction.response.send_message(f"✅ **Multa Registrata!** Emessa sanzione di **€{self.importo.value}** all'utente <@{self.discord_id.value}>.", ephemeral=True)


# MODAL: ARRESTO
class ArrestoModal(Modal, title='Registra Fermo / Arresto'):
    discord_id = TextInput(label='ID Discord del Cittadino', placeholder='Incolla ID Discord...', required=True)
    mesi = TextInput(label='Mesi di Prigione', placeholder='Es. 10', required=True)
    cauzione = TextInput(label='Cauzione (€)', placeholder='Es. 1000 (metti 0 se non applicabile)', default="0", required=True)
    motivo = TextInput(label='Motivo dell\'Arresto', style=discord.TextStyle.paragraph, placeholder='Es. Rapina a mano armata, resistenza a pubblico ufficiale...', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("police_arrests").insert({
            "discord_id": self.discord_id.value.strip(),
            "officer_name": interaction.user.display_name,
            "reason": self.motivo.value.strip(),
            "months": int(self.mesi.value.strip()),
            "bail": float(self.cauzione.value.strip())
        }).execute()

        await interaction.response.send_message(f"🚨 **Arresto Registrato!** Soggetto <@{self.discord_id.value}> condannato a **{self.mesi.value} mesi**.", ephemeral=True)


# MODAL: VERBALE / RAPPORTO
class VerbaleModal(Modal, title='Compila Rapporto / Verbale'):
    discord_id = TextInput(label='ID Discord del Cittadino', placeholder='Incolla ID Discord...', required=True)
    titolo = TextInput(label='Titolo del Verbale', placeholder='Es. Perquisizione Veicolare / Interrogatorio', required=True)
    descrizione = TextInput(label='Dettagli del Verbale', style=discord.TextStyle.paragraph, placeholder='Descrivi dettagliatamente l\'accaduto...', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("police_reports").insert({
            "discord_id": self.discord_id.value.strip(),
            "officer_name": interaction.user.display_name,
            "title": self.titolo.value.strip(),
            "description": self.descrizione.value.strip()
        }).execute()

        await interaction.response.send_message(f"📄 **Verbale Salvato!** Registrato con successo a carico di <@{self.discord_id.value}>.", ephemeral=True)


# MODAL: PORTO D'ARMI / LICENZA
class PortoArmiModal(Modal, title='Rilascio Licenza / Porto d\'Armi'):
    discord_id = TextInput(label='ID Discord del Cittadino', placeholder='Incolla ID Discord...', required=True)
    tipo_licenza = TextInput(label='Tipo Licenza', placeholder='Es. Porto d\'Armi Leggero / Difesa Personale', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("gun_licenses").insert({
            "discord_id": self.discord_id.value.strip(),
            "license_type": self.tipo_licenza.value.strip(),
            "status": "Attivo"
        }).execute()

        await interaction.response.send_message(f"🔫 **Licenza Armi Registrata!** Rilasciata licenza `{self.tipo_licenza.value}` all'utente <@{self.discord_id.value}>.", ephemeral=True)


# --- 3. MODAL E SELECT DI RICERCA ---

class ElencoCittadiniSelect(Select):
    def __init__(self):
        res = supabase.table("documents").select("discord_id, name, surname, cf").limit(25).execute()
        options = []
        for c in res.data:
            options.append(discord.SelectOption(
                label=f"{c['name']} {c['surname']}",
                description=f"CF: {c['cf']}",
                value=c['discord_id'],
                emoji="👤"
            ))
        if not options:
            options.append(discord.SelectOption(label="Nessun cittadino nel database", value="null"))

        super().__init__(placeholder="Seleziona un cittadino dal registro...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "null":
            await interaction.response.send_message("❌ Nessun cittadino registrato.", ephemeral=True)
            return
        
        view = CADCitizenProfile(self.values[0], interaction.guild, interaction.user)
        embed = discord.Embed(title="🚨 Profilo Caricato", description="Usa i bottoni in basso per consultare i registri.", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ListaCittadiniView(View):
    def __init__(self):
        super().__init__()
        self.add_item(ElencoCittadiniSelect())

class RicercaCittadinoModal(Modal, title='Ricerca Anagrafica CAD'):
    query = TextInput(label='Nome, Cognome o Codice Fiscale', placeholder='Es. Mario Rossi o CF...', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        q = self.query.value.strip()
        res = supabase.table("documents").select("*").or_(f"name.ilike.%{q}%,surname.ilike.%{q}%,cf.ilike.%{q}%").execute()
        
        if not res.data:
            await interaction.response.send_message(f"❌ Nessun cittadino trovato con la ricerca: `{q}`", ephemeral=True)
            return
        
        target_id = res.data[0]["discord_id"]
        view = CADCitizenProfile(target_id, interaction.guild, interaction.user)
        embed = discord.Embed(title="🚨 Scheda Trovata", description="Seleziona una categoria da consultare:", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class RicercaTargaModal(Modal, title='Ricerca Motorizzazione'):
    targa = TextInput(label='Targa del veicolo', placeholder='Es. AB123CD', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        t = self.targa.value.strip().upper()
        res = supabase.table("registered_vehicles").select("*").eq("plate", t).execute()
        
        if not res.data:
            await interaction.response.send_message(f"⚠️ La targa `{t}` non risulta nei registri!", ephemeral=True)
            return
            
        v = res.data[0]
        embed = discord.Embed(title="🚘 Esito Riscontro Targa", color=discord.Color.gold())
        embed.add_field(name="🚘 Modello", value=v['model'], inline=True)
        embed.add_field(name="🔢 Targa", value=f"`{v['plate'].upper()}`", inline=True)
        
        view = View()
        btn = Button(label="Apri Scheda Proprietario", style=discord.ButtonStyle.primary, emoji="👤")
        async def btn_callback(inter: discord.Interaction):
            prof_view = CADCitizenProfile(v['discord_id'], inter.guild, inter.user)
            await inter.response.send_message(embed=discord.Embed(title="🚨 Fascicolo Proprietario Caricato", color=discord.Color.blue()), view=prof_view, ephemeral=True)
        btn.callback = btn_callback
        view.add_item(btn)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class RicercaArmaModal(Modal, title='Ricerca Registro Armi'):
    matricola = TextInput(label='Matricola dell\'arma', placeholder='Es. WPN-8819', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        m = self.matricola.value.strip()
        res = supabase.table("registered_weapons").select("*").eq("serial_number", m).execute()
        
        if not res.data:
            await interaction.response.send_message(f"⚠️ La matricola `{m}` non esiste nei registri armi!", ephemeral=True)
            return
            
        a = res.data[0]
        embed = discord.Embed(title="🔫 Esito Riscontro Arma", color=discord.Color.red())
        embed.add_field(name="🔫 Modello", value=a['model'], inline=True)
        embed.add_field(name="🔢 Matricola", value=f"`{a['serial_number']}`", inline=True)

        view = View()
        btn = Button(label="Apri Scheda Titolare", style=discord.ButtonStyle.danger, emoji="👤")
        async def btn_callback(inter: discord.Interaction):
            prof_view = CADCitizenProfile(a['discord_id'], inter.guild, inter.user)
            await inter.response.send_message(embed=discord.Embed(title="🚨 Fascicolo Titolare Caricato", color=discord.Color.blue()), view=prof_view, ephemeral=True)
        btn.callback = btn_callback
        view.add_item(btn)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --- 4. DASHBOARD CENTRALE MENU PRINCIPALE ---

class CADMainMenu(View):
    def __init__(self):
        super().__init__(timeout=None)

    # --- SEZIONE CONSULTAZIONE ---
    @discord.ui.button(label="Lista Cittadini", style=discord.ButtonStyle.primary, emoji="📋", row=0)
    async def btn_lista(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Seleziona un cittadino dal menu a tendina:", view=ListaCittadiniView(), ephemeral=True)

    @discord.ui.button(label="Cerca Cittadino", style=discord.ButtonStyle.secondary, emoji="🔍", row=0)
    async def btn_cerca_cit(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RicercaCittadinoModal())

    @discord.ui.button(label="Cerca Targa", style=discord.ButtonStyle.success, emoji="🚘", row=0)
    async def btn_cerca_targa(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RicercaTargaModal())

    @discord.ui.button(label="Cerca Arma", style=discord.ButtonStyle.danger, emoji="🔫", row=0)
    async def btn_cerca_arma(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RicercaArmaModal())

    # --- SEZIONE GESTIONE OPERATIVA POLIZIA ---
    @discord.ui.button(label="Emetti Multa", style=discord.ButtonStyle.secondary, emoji="💶", row=1)
    async def btn_multa(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(MultaModal())

    @discord.ui.button(label="Registra Arresto", style=discord.ButtonStyle.danger, emoji="🔒", row=1)
    async def btn_arresto(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ArrestoModal())

    @discord.ui.button(label="Crea Verbale", style=discord.ButtonStyle.primary, emoji="📄", row=1)
    async def btn_verbale(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(VerbaleModal())

    @discord.ui.button(label="Rilascia Porto d'Armi", style=discord.ButtonStyle.success, emoji="📜", row=1)
    async def btn_porto_armi(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PortoArmiModal())


# --- 5. COMANDO PRINCIPALE ---

@bot.tree.command(name="cad", description="[Polizia] Apre il terminale centrale CAD interattivo.")
async def comando_cad(interaction: discord.Interaction):
    ruolo_polizia = interaction.guild.get_role(RUOLO_POLIZIA_ID)
    if not ruolo_polizia or ruolo_polizia not in interaction.user.roles:
        await interaction.response.send_message("❌ **Accesso Negato:** Terminale riservato esclusivamente alle Forze dell'Ordine.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🚨 Terminale CAD - Forze dell'Ordine",
        description="Seleziona un'operazione dal pannello sottostante per consultare la banca dati o registrare un nuovo atto giudiziario.",
        color=discord.Color.dark_blue()
    )
    
    await interaction.response.send_message(embed=embed, view=CADMainMenu(), ephemeral=True)

# --- MODULO 3: AGENZIA IMMOBILIARE ---

@bot.tree.command(name="registra_immobile", description="[Immobiliare] Registra una proprietà o casa a un cittadino.")
@app_commands.describe(utente="Acquirente/Proprietario", tipo_immobile="Es. Appartamento, Villa, Garage", indirizzo="Indirizzo dell'immobile")
async def registra_immobile(interaction: discord.Interaction, utente: discord.Member, tipo_immobile: str, indirizzo: str):
    ruolo_imm = interaction.guild.get_role(RUOLO_IMMOBILIARE_ID)
    if not ruolo_imm or ruolo_imm not in interaction.user.roles:
        await interaction.response.send_message("❌ **Accesso Negato:** Comando riservato agli Agenti Immobiliari.", ephemeral=True)
        return

    prop_id = f"PROP-{random.randint(1000, 9999)}"
    supabase.table("properties").insert({
        "property_id": prop_id,
        "owner_discord_id": str(utente.id),
        "property_type": tipo_immobile,
        "address": indirizzo
    }).execute()

    embed = discord.Embed(title="🏠 Registrazione Immobile Completata", color=discord.Color.gold())
    embed.add_field(name="🔑 ID Proprietà", value=f"`{prop_id}`", inline=True)
    embed.add_field(name="👤 Proprietario", value=utente.mention, inline=True)
    embed.add_field(name="🏠 Tipologia", value=tipo_immobile, inline=True)
    embed.add_field(name="📍 Indirizzo", value=indirizzo, inline=False)

    await interaction.response.send_message(embed=embed)


# --- MODULO 4: BANCOMAT & CONTANTI ---

class BancomatPINModal(discord.ui.Modal, title="Imposta PIN Bancomat"):
    pin1 = discord.ui.TextInput(label="Nuovo PIN (4 cifre)", max_length=4, min_length=4, required=True)
    pin2 = discord.ui.TextInput(label="Conferma PIN", max_length=4, min_length=4, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if self.pin1.value != self.pin2.value or not self.pin1.value.isdigit():
            await interaction.response.send_message("❌ I PIN non coincidono o contengono caratteri non numerici.", ephemeral=True)
            return

        supabase.table("users").update({"pin": self.pin1.value}).eq("discord_id", str(interaction.user.id)).execute()
        await interaction.response.send_message("✅ PIN impostato con successo! Conservalo con cura.", ephemeral=True)


@bot.tree.command(name="bancomat", description="Accedi al Bancomat per verificare saldo, prelevare o depositare contanti.")
async def bancomat(interaction: discord.Interaction):
    user_db = get_or_create_user(interaction.user.id, interaction.user.name)

    embed = discord.Embed(title="🏦 Banca Centrale di Evren - ATM Terminal", color=discord.Color.green())
    embed.add_field(name="💵 Contanti in Tasca", value=f"**€ {user_db['cash']:,.2f}**", inline=True)
    embed.add_field(name="💳 Saldo Bancomat", value=f"**€ {user_db['bank']:,.2f}**", inline=True)
    
    status_pin = "🟢 Configurato" if user_db.get("pin") else "🔴 Non Impostato (Usa /imposta_pin)"
    embed.add_field(name="🔒 Stato PIN", value=status_pin, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="imposta_pin", description="Imposta o cambia il tuo codice PIN Bancomat.")
async def imposta_pin(interaction: discord.Interaction):
    await interaction.response.send_modal(BancomatPINModal())


@bot.tree.command(name="deposita", description="Deposita contanti sul tuo conto bancario.")
@app_commands.describe(importo="Cifra da depositare in banca")
async def deposita(interaction: discord.Interaction, importo: float):
    if importo <= 0:
        await interaction.response.send_message("❌ Inserisci un importo valido.", ephemeral=True)
        return

    user_db = get_or_create_user(interaction.user.id, interaction.user.name)
    if user_db["cash"] < importo:
        await interaction.response.send_message("❌ Non hai abbastanza contanti con te.", ephemeral=True)
        return

    nuovo_cash = user_db["cash"] - importo
    nuovo_bank = user_db["bank"] + importo

    supabase.table("users").update({"cash": nuovo_cash, "bank": nuovo_bank}).eq("discord_id", str(interaction.user.id)).execute()
    log_transaction(str(interaction.user.id), "DEPOSITO", importo, "Deposito contanti presso ATM")

    await interaction.response.send_message(f"✅ Depositati **€ {importo:,.2f}** nel conto bancario.", ephemeral=True)


@bot.tree.command(name="preleva", description="Preleva contanti dal tuo conto bancario inserendo il PIN.")
@app_commands.describe(importo="Cifra da prelevare", pin="Il tuo PIN Bancomat a 4 cifre")
async def preleva(interaction: discord.Interaction, importo: float, pin: str):
    if importo <= 0:
        await interaction.response.send_message("❌ Inserisci un importo valido.", ephemeral=True)
        return

    user_db = get_or_create_user(interaction.user.id, interaction.user.name)

    if not user_db.get("pin"):
        await interaction.response.send_message("❌ Devi prima impostare un PIN con `/imposta_pin`.", ephemeral=True)
        return

    if user_db["pin"] != pin:
        await interaction.response.send_message("❌ **PIN Errato!** Operazione annullata.", ephemeral=True)
        return

    if user_db["bank"] < importo:
        await interaction.response.send_message("❌ Saldo bancario insufficiente.", ephemeral=True)
        return

    nuovo_cash = user_db["cash"] + importo
    nuovo_bank = user_db["bank"] - importo

    supabase.table("users").update({"cash": nuovo_cash, "bank": nuovo_bank}).eq("discord_id", str(interaction.user.id)).execute()
    log_transaction(str(interaction.user.id), "PRELIEVO", importo, "Prelievo contanti da ATM")

    await interaction.response.send_message(f"✅ Prelevati **€ {importo:,.2f}** in contanti.", ephemeral=True)


# --- MODULO 5: SHOP & COMPRA ---

class ShopCategorySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Armi", description="Acquista armi e munizioni", emoji="🔫", value="armi"),
            discord.SelectOption(label="Mediche", description="Kit medici e bende", emoji="💊", value="mediche"),
            discord.SelectOption(label="Generale", description="Oggetti vari e utility", emoji="🎒", value="generale"),
        ]
        super().__init__(placeholder="📂 Seleziona una categoria...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        categoria = self.values[0]
        res = supabase.table("shop_items").select("*").eq("category", categoria).execute()
        items = res.data if res.data else []

        embed = discord.Embed(
            title=f"🛒 Evren Shop - Categoria: {categoria.capitalize()}",
            description="Ecco gli articoli disponibili. Usa `/compra [nome_item]` per acquistare.",
            color=discord.Color.blue()
        )

        if not items:
            embed.add_field(name="Vuoto", value="Non ci sono oggetti in questa categoria.", inline=False)
        else:
            for item in items:
                embed.add_field(
                    name=f"🔹 {item['name']}",
                    value=f"💰 Prezzo: **€ {item['price']:,.2f}**\n🔒 Ruolo: `{item.get('required_role_name', 'Nessuno')}`",
                    inline=False
                )

        await interaction.response.edit_message(embed=embed, view=self.view)


class ShopView(View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(ShopCategorySelect())


@bot.tree.command(name="shop", description="Visualizza lo store ufficiale di Evren City OS.")
async def shop(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 Evren City OS - Negozio Generale", description="Seleziona una categoria dal menu per sfogliare gli articoli.", color=discord.Color.blue())
    await interaction.response.send_message(embed=embed, view=ShopView(), ephemeral=True)


async def shop_item_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("shop_items").select("name").ilike("name", f"%{current}%").limit(25).execute()
    items = res.data if res.data else []
    return [app_commands.Choice(name=i["name"], value=i["name"]) for i in items]


@bot.tree.command(name="compra", description="Acquista un articolo dallo shop.")
@app_commands.describe(item="Nome dell'oggetto da acquistare")
@app_commands.autocomplete(item=shop_item_autocomplete)
async def compra(interaction: discord.Interaction, item: str):
    user_id = str(interaction.user.id)
    res_item = supabase.table("shop_items").select("*").ilike("name", item).execute()

    if not res_item.data:
        await interaction.response.send_message("❌ Oggetto non trovato nello shop.", ephemeral=True)
        return

    item_data = res_item.data[0]
    prezzo = item_data.get("price", 0)
    req_role = item_data.get("required_role_id")

    if req_role and not any(r.id == int(req_role) for r in interaction.user.roles):
        await interaction.response.send_message("❌ Non possiedi il ruolo richiesto per questo oggetto.", ephemeral=True)
        return

    user_db = get_or_create_user(interaction.user.id, interaction.user.name)
    if user_db["cash"] < prezzo:
        await interaction.response.send_message(f"❌ Non hai abbastanza contanti (€ {user_db['cash']:,.2f} / € {prezzo:,.2f}).", ephemeral=True)
        return

    nuovo_saldo = user_db["cash"] - prezzo
    supabase.table("users").update({"cash": nuovo_saldo}).eq("discord_id", user_id).execute()
    supabase.table("user_inventory").insert({"discord_id": user_id, "item_name": item_data["name"], "quantity": 1}).execute()

    await interaction.response.send_message(f"✅ Hai acquistato **{item_data['name']}** per **€ {prezzo:,.2f}**!", ephemeral=True)


# --- MODULO 6: SMARTPHONE & CHIAMATE VOCALI ---

class AggiungiContattoModal(discord.ui.Modal, title="Nuovo Contatto"):
    nome = discord.ui.TextInput(label="Nome Contatto", placeholder="Es. Mario Rossi", required=True)
    numero = discord.ui.TextInput(label="Numero di Telefono", placeholder="Es. +1 (555) 0192", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        supabase.table("contacts").insert({
            "owner_id": str(interaction.user.id),
            "name": self.nome.value.strip(),
            "phone_number": self.numero.value.strip()
        }).execute()
        await interaction.response.send_message(f"✅ Contatto **{self.nome.value}** salvato in rubrica!", ephemeral=True)


class WhatsAppMessageModal(discord.ui.Modal, title="Invia Messaggio WhatsApp"):
    testo = discord.ui.TextInput(label="Messaggio", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, destinatario: str):
        super().__init__()
        self.destinatario = destinatario

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"💬 Messaggio inviato a **{self.destinatario}**:\n> {self.testo.value}", ephemeral=True)


class WhatsAppChatView(View):
    def __init__(self, destinatario: str):
        super().__init__(timeout=180)
        self.destinatario = destinatario

    @discord.ui.button(label="Invia Messaggio", style=discord.ButtonStyle.green, emoji="💬")
    async def invia(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(WhatsAppMessageModal(self.destinatario))


class RispondiChiamataView(View):
    def __init__(self, chiamante: discord.Member, destinatario: discord.Member, channel: discord.VoiceChannel, task_squillo: asyncio.Task):
        super().__init__(timeout=120)
        self.chiamante = chiamante
        self.destinatario = destinatario
        self.channel = channel
        self.task_squillo = task_squillo
        self.risposta = False

    @discord.ui.button(label="Rispondi", style=discord.ButtonStyle.green, emoji="📞")
    async def rispondi(self, interaction: discord.Interaction, button: Button):
        self.risposta = True
        self.stop()
        if not self.task_squillo.done():
            self.task_squillo.cancel()

        link = self.channel.jump_url
        await interaction.response.edit_message(content=f"✅ Chiamata accettata!\n🔊 **Entra nel canale vocale:** {link}", view=None)
        try:
            await self.chiamante.send(f"📞 **{self.destinatario.display_name}** ha risposto!\n🔊 Entra nel canale: {link}")
        except Exception:
            pass

    @discord.ui.button(label="Rifiuta", style=discord.ButtonStyle.red, emoji="❌")
    async def rifiuta(self, interaction: discord.Interaction, button: Button):
        self.risposta = True
        self.stop()
        if not self.task_squillo.done():
            self.task_squillo.cancel()

        await interaction.response.edit_message(content="❌ Chiamata rifiutata.", view=None)
        try:
            await self.chiamante.send(f"❌ **{self.destinatario.display_name}** ha rifiutato la chiamata.")
            await riproduci_audio_canale(self.channel, "rifiuto.mp3", loop=False)
            await self.channel.delete()
        except Exception:
            pass


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

        btn = Button(label="Nuovo Contatto", style=discord.ButtonStyle.blurple, emoji="➕", row=0)
        btn.callback = self.apri_modal_contatto
        self.add_item(btn)

        if contacts:
            opts = [discord.SelectOption(label=c["name"], description=c["phone_number"], value=c["phone_number"]) for c in contacts[:25]]
            
            sel_chiama = Select(placeholder="📞 Chiama contatto", options=opts, row=1)
            sel_chiama.callback = self.chiama_callback
            self.add_item(sel_chiama)

            sel_wa = Select(placeholder="💬 Chat WhatsApp", options=opts, row=2)
            sel_wa.callback = self.wa_callback
            self.add_item(sel_wa)

    async def apri_modal_contatto(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AggiungiContattoModal())

    async def chiama_callback(self, interaction: discord.Interaction):
        num = interaction.data["values"][0]
        await interaction.response.defer(ephemeral=True)
        await avvia_chiamata_vocale(interaction, num)

    async def wa_callback(self, interaction: discord.Interaction):
        num = interaction.data["values"][0]
        await interaction.response.send_message(f"📱 **WhatsApp Chat**", view=WhatsAppChatView(num), ephemeral=True)


async def avvia_chiamata_vocale(interaction: discord.Interaction, numero: str):
    guild = interaction.guild
    chiamante = interaction.user

    res = supabase.table("user_phones").select("discord_id").eq("phone_number", numero).execute()
    if not res.data:
        await interaction.followup.send("❌ Numero non raggiungibile o inesistente.", ephemeral=True)
        return

    destinatario = guild.get_member(int(res.data[0]["discord_id"]))
    if not destinatario:
        await interaction.followup.send("❌ Utente non trovato nel server.", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(connect=False),
        chiamante: discord.PermissionOverwrite(connect=True, speak=True),
        destinatario: discord.PermissionOverwrite(connect=True, speak=True)
    }

    voice = await guild.create_voice_channel(name=f"📞 {chiamante.name} ➡️ {destinatario.name}", overwrites=overwrites)
    task_squillo = asyncio.create_task(riproduci_audio_canale(voice, "squillo.mp3", loop=True))

    view = RispondiChiamataView(chiamante, destinatario, voice, task_squillo)
    try:
        await destinatario.send(f"📱 **CHIAMATA IN ARRIVO** da {chiamante.mention}!", view=view)
        await interaction.followup.send(f"📞 Squillo in corso verso **{destinatario.display_name}**...", ephemeral=True)
    except Exception:
        task_squillo.cancel()
        await voice.delete()
        await interaction.followup.send("❌ Impossibile chiamare l'utente (DM chiusi).", ephemeral=True)


@bot.tree.command(name="telefono", description="Apre il tuo Smartphone personale.")
async def telefono(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    res = supabase.table("user_phones").select("phone_number").eq("discord_id", user_id).execute()

    if not res.data:
        num = f"+1 ({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"
        supabase.table("user_phones").insert({"discord_id": user_id, "phone_number": num}).execute()
        phone_number = num
    else:
        phone_number = res.data[0]["phone_number"]

    embed = discord.Embed(title="📱 Evren OS Smartphone", color=discord.Color.green())
    embed.add_field(name="📞 Il tuo Numero", value=f"`{phone_number}`", inline=False)
    
    await interaction.response.send_message(embed=embed, view=EvrenPhoneView(user_id, phone_number), ephemeral=True)


# --- MODULO 7: RICONOSCIMENTO BIOMETRICO / FOTO ---

@bot.tree.command(name="cerca_foto", description="[Polizia] Identifica un cittadino scansionando una foto.")
@app_commands.describe(foto="Carica l'immagine da analizzare")
async def cerca_foto(interaction: discord.Interaction, foto: discord.Attachment):
    ruolo_polizia = interaction.guild.get_role(RUOLO_POLIZIA_ID)
    if not ruolo_polizia or ruolo_polizia not in interaction.user.roles:
        await interaction.response.send_message("❌ **Accesso Negato:** Riservato alla Polizia.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    sito = f"https://bot-kiwonuwy1-elmatador737373-makers-projects.vercel.app/?url={foto.url}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(sito, wait_until="networkidle")

            await page.wait_for_selector("#result", timeout=60000)
            res_text = await page.inner_text("#result")
            await browser.close()

        data = json.loads(res_text)
        if data.get("status") == "success":
            match = data["match"]
            embed = discord.Embed(title="🔍 Biometria Polizia - Match Trovato", color=discord.Color.green())
            embed.add_field(name="👤 Nome", value=match.get("name", "N/D"), inline=True)
            embed.add_field(name="📄 Codice Fiscale", value=f"`{match.get('fiscal_code', 'N/D')}`", inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("❌ Nessun riscontro trovato nel database biometrico.", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Errore durante l'analisi: {e}", ephemeral=True)


# --- MODULO 8: FAZIONI & DEPOSITI (CON COMANDO STAFF) ---

class FactionCashModal(discord.ui.Modal):
    def __init__(self, faction_name: str, action_type: str):
        title = "Deposita Soldi" if action_type == "deposita" else "Preleva Soldi"
        super().__init__(title=f"{title} - {faction_name}")
        self.faction_name = faction_name
        self.action_type = action_type
        self.quantita = discord.ui.TextInput(label="Importo (€)", placeholder="Es. 5000", required=True)
        self.add_item(self.quantita)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.quantita.value.strip())
            if val <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Inserisci una cifra valida.", ephemeral=True)
            return

        res = supabase.table("faction_vaults").select("cash_balance").eq("faction_name", self.faction_name).execute()
        saldo = res.data[0].get("cash_balance", 0.0) if res.data else 0.0

        if self.action_type == "preleva" and saldo < val:
            await interaction.response.send_message(f"❌ Fondi fazione insufficienti (€ {saldo:,.2f}).", ephemeral=True)
            return

        nuovo_saldo = (saldo + val) if self.action_type == "deposita" else (saldo - val)
        supabase.table("faction_vaults").update({"cash_balance": nuovo_saldo}).eq("faction_name", self.faction_name).execute()

        az = "depositato" if self.action_type == "deposita" else "prelevato"
        await interaction.response.send_message(f"✅ Hai {az} **€ {val:,.2f}** nella cassa di **{self.faction_name}**!\nNuovo saldo: **€ {nuovo_saldo:,.2f}**", ephemeral=True)


class FactionItemModal(discord.ui.Modal):
    def __init__(self, faction_name: str, action_type: str):
        title = "Deposita Item" if action_type == "deposita" else "Preleva Item"
        super().__init__(title=f"{title} - {faction_name}")
        self.faction_name = faction_name
        self.action_type = action_type

        self.item = discord.ui.TextInput(label="Nome Oggetto", placeholder="Es. Kit Medico", required=True)
        self.qta = discord.ui.TextInput(label="Quantità", placeholder="Es. 2", required=True)
        self.add_item(self.item)
        self.add_item(self.qta)

    async def on_submit(self, interaction: discord.Interaction):
        az = "depositato" if self.action_type == "deposita" else "prelevato"
        await interaction.response.send_message(f"✅ Hai {az} **{self.qta.value}x {self.item.value}** nel deposito di **{self.faction_name}**.", ephemeral=True)


class FactionVaultView(View):
    def __init__(self, faction_name: str):
        super().__init__(timeout=300)
        self.faction_name = faction_name

    @discord.ui.button(label="Deposita Soldi", style=discord.ButtonStyle.green, emoji="💵", row=0)
    async def dep_s(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionCashModal(self.faction_name, "deposita"))

    @discord.ui.button(label="Preleva Soldi", style=discord.ButtonStyle.red, emoji="💸", row=0)
    async def pre_s(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionCashModal(self.faction_name, "preleva"))

    @discord.ui.button(label="Deposita Item", style=discord.ButtonStyle.blurple, emoji="📦", row=1)
    async def dep_i(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionItemModal(self.faction_name, "deposita"))

    @discord.ui.button(label="Preleva Item", style=discord.ButtonStyle.grey, emoji="📤", row=1)
    async def pre_i(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(FactionItemModal(self.faction_name, "preleva"))


async def fazione_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    res = supabase.table("faction_roles").select("faction_name").ilike("faction_name", f"%{current}%").limit(25).execute()
    fazioni = res.data if res.data else []
    return [app_commands.Choice(name=f["faction_name"], value=f["faction_name"]) for f in fazioni]


@bot.tree.command(name="deposito_fazione", description="Apri e gestisci il deposito della tua fazione.")
@app_commands.describe(fazione="Nome della fazione")
@app_commands.autocomplete(fazione=fazione_autocomplete)
async def deposito_fazione(interaction: discord.Interaction, fazione: str):
    res = supabase.table("faction_roles").select("role_id").eq("faction_name", fazione).execute()
    if not res.data:
        await interaction.response.send_message("❌ Fazione non registrata nel sistema.", ephemeral=True)
        return

    role_id = int(res.data[0]["role_id"])
    if not any(r.id == role_id for r in interaction.user.roles):
        await interaction.response.send_message("❌ Non possiedi il ruolo autorizzato per questa fazione.", ephemeral=True)
        return

    res_v = supabase.table("faction_vaults").select("cash_balance, items_list").eq("faction_name", fazione).execute()
    saldo = res_v.data[0].get("cash_balance", 0.0) if res_v.data else 0.0
    items = res_v.data[0].get("items_list", "Deposito Vuoto.") if res_v.data else "Deposito Vuoto."

    embed = discord.Embed(title=f"🏛️ Deposito Fazione: {fazione}", color=discord.Color.gold())
    embed.add_field(name="💰 Saldo Cassa", value=f"**€ {saldo:,.2f}**", inline=False)
    embed.add_field(name="📦 Inventario", value=f"```{items}```", inline=False)

    await interaction.response.send_message(embed=embed, view=FactionVaultView(fazione), ephemeral=True)


@bot.tree.command(name="registra_deposito_fazione", description="[Staff] Configura una nuova fazione e collega il relativo Ruolo Discord.")
@app_commands.describe(nome_fazione="Nome identificativo", ruolo="Ruolo Discord abilitato", saldo_iniziale="Cassa iniziale (€)")
async def registra_deposito_fazione(interaction: discord.Interaction, nome_fazione: str, ruolo: discord.Role, saldo_iniziale: float = 0.0):
    ruolo_staff = interaction.guild.get_role(RUOLO_STAFF_ID)
    if not ruolo_staff or ruolo_staff not in interaction.user.roles:
        await interaction.response.send_message("❌ **Accesso Negato:** Comando riservato allo Staff.", ephemeral=True)
        return

    supabase.table("faction_roles").upsert({"faction_name": nome_fazione, "role_id": str(ruolo.id)}, on_conflict="faction_name").execute()
    supabase.table("faction_vaults").upsert({"faction_name": nome_fazione, "cash_balance": max(0.0, saldo_iniziale), "items_list": "Deposito vuoto."}, on_conflict="faction_name").execute()

    embed = discord.Embed(title="✅ Deposito Fazione Configurato", color=discord.Color.green())
    embed.add_field(name="🏰 Fazione", value=f"`{nome_fazione}`", inline=True)
    embed.add_field(name="🎭 Ruolo", value=ruolo.mention, inline=True)
    embed.add_field(name="💵 Saldo Iniziale", value=f"**€ {saldo_iniziale:,.2f}**", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- SETUP BOT & RUN ---

@bot.event
async def on_ready():
    print(f"🤖 Bot operativo come {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Sincronizzati {len(synced)} comandi slash globali.")
    except Exception as e:
        print(f"❌ Errore durante la sincronizzazione: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ Token Discord mancante nel file .env!")
