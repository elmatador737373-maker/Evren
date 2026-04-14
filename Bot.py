import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from typing import List, Optional

# --- CARICAMENTO TOKEN DA SECRET ---
# In Base44, assicurati di aver creato una variabile chiamata 'DISCORD_TOKEN' 
# nelle impostazioni "Startup" o "Secrets" della tua dashboard.
TOKEN = os.getenv('DISCORD_TOKEN')

# --- CONFIGURAZIONE DATABASE ---
DATABASE_FILE = "evren_city_db.json"

def load_db():
    if not os.path.exists(DATABASE_FILE):
        return {
            "config": {"staff_role": None, "citizen_role": None},
            "users": {}, 
            "shop": {}
        }
    with open(DATABASE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DATABASE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def get_user_data(db, user_id):
    u_id = str(user_id)
    if u_id not in db["users"]:
        db["users"][u_id] = {"cash": 500, "bank": 1000, "inventory": {}}
    return db["users"][u_id]

# --- CLASSE BOT ---
class EvrenBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Evren City Bot Online - Comandi Slash Sincronizzati")

bot = EvrenBot()

# --- AUTOCOMPLETE RICERCA ITEM ---
async def item_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    db = load_db()
    items = list(db["shop"].keys())
    return [
        app_commands.Choice(name=item, value=item)
        for item in items if current.lower() in item.lower()
    ][:25]

# --- COMANDI STAFF (SETUP & GESTIONE) ---

@bot.tree.command(name="setup_evren", description="Configura i ruoli per lo Staff e i Cittadini")
@app_commands.checks.has_permissions(administrator=True)
async def setup_evren(interaction: discord.Interaction, staff: discord.Role, cittadino: discord.Role):
    db = load_db()
    db["config"]["staff_role"] = staff.id
    db["config"]["citizen_role"] = cittadino.id
    save_db(db)
    await interaction.response.send_message(f"✅ Configurazione salvata: Staff={staff.name}, Cittadino={cittadino.name}", ephemeral=True)

@bot.tree.command(name="crea_item", description="[STAFF] Aggiunge un oggetto allo shop")
async def crea_item(interaction: discord.Interaction, nome: str, prezzo: int, ruolo_richiesto: Optional[discord.Role] = None):
    db = load_db()
    staff_id = db["config"].get("staff_role")
    if not any(r.id == staff_id for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Devi essere Staff per creare item.", ephemeral=True)

    db["shop"][nome] = {"prezzo": prezzo, "role_req": ruolo_richiesto.id if ruolo_richiesto else None}
    save_db(db)
    await interaction.response.send_message(f"✅ Item `{nome}` creato a {prezzo}€.")

@bot.tree.command(name="set_money", description="[STAFF] Modifica i soldi di un utente")
async def set_money(interaction: discord.Interaction, utente: discord.Member, quantita: int, dove: str):
    db = load_db()
    staff_id = db["config"].get("staff_role")
    if not any(r.id == staff_id for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Solo lo Staff può farlo.", ephemeral=True)

    u_data = get_user_data(db, utente.id)
    if dove.lower() == "banca": u_data["bank"] = quantita
    else: u_data["cash"] = quantita
    save_db(db)
    await interaction.response.send_message(f"💰 {utente.display_name} ora ha {quantita}€ in {dove}.")

# --- COMANDI CITTADINI ---

@bot.tree.command(name="balance", description="Mostra il tuo saldo o quello di un cittadino")
async def balance(interaction: discord.Interaction, utente: Optional[discord.Member] = None):
    db = load_db()
    target = utente or interaction.user
    
    # Controllo Staff per vedere bilancio altrui
    if utente and utente != interaction.user:
        staff_id = db["config"].get("staff_role")
        if not any(r.id == staff_id for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Non puoi vedere il conto di altri.", ephemeral=True)

    u_data = get_user_data(db, target.id)
    embed = discord.Embed(title=f"🏦 Evren Bank - {target.display_name}", color=0x2ecc71)
    embed.add_field(name="💵 Tasca", value=f"{u_data['cash']}€", inline=True)
    embed.add_field(name="💳 Conto", value=f"{u_data['bank']}€", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="paga", description="Trasferisce contanti a un altro giocatore")
async def paga(interaction: discord.Interaction, ricevente: discord.Member, quantita: int):
    if quantita <= 0: return await interaction.response.send_message("❌ Somma non valida.", ephemeral=True)
    
    db = load_db()
    m_data = get_user_data(db, interaction.user.id)
    r_data = get_user_data(db, ricevente.id)

    if m_data["cash"] < quantita:
        return await interaction.response.send_message("❌ Non hai abbastanza contanti.", ephemeral=True)

    m_data["cash"] -= quantita
    r_data["cash"] += quantita
    save_db(db)
    await interaction.response.send_message(f"💸 Hai consegnato {quantita}€ a {ricevente.mention}.")

@bot.tree.command(name="shop", description="Mostra il catalogo degli oggetti")
async def shop(interaction: discord.Interaction):
    db = load_db()
    if not db["shop"]: return await interaction.response.send_message("Il negozio è vuoto.")
    
    embed = discord.Embed(title="🛒 Negozio Evren City", color=0x3498db)
    for n, i in db["shop"].items():
        prezzo = i["prezzo"]
        req = " (🔒 Speciale)" if i["role_req"] else ""
        embed.add_field(name=f"{n}{req}", value=f"{prezzo}€", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="compra", description="Acquista un oggetto dallo shop")
@app_commands.autocomplete(item=item_autocomplete)
async def compra(interaction: discord.Interaction, item: str):
    db = load_db()
    if item not in db["shop"]: return await interaction.response.send_message("❌ Articolo non trovato.", ephemeral=True)
    
    i_data = db["shop"][item]
    u_data = get_user_data(db, interaction.user.id)

    if i_data["role_req"] and not any(r.id == i_data["role_req"] for r in interaction.user.roles):
        return await interaction.response.send_message("❌ Non hai i requisiti per questo articolo.", ephemeral=True)

    if u_data["cash"] < i_data["prezzo"]:
        return await interaction.response.send_message("❌ Ti mancano contanti per l'acquisto.", ephemeral=True)

    u_data["cash"] -= i_data["prezzo"]
    u_data["inventory"][item] = u_data["inventory"].get(item, 0) + 1
    save_db(db)
    await interaction.response.send_message(f"📦 Hai acquistato: {item}!")

@bot.tree.command(name="inventario", description="Guarda cosa hai nello zaino")
async def inventario(interaction: discord.Interaction):
    db = load_db()
    u_data = get_user_data(db, interaction.user.id)
    items = [f"• {k} (x{v})" for k, v in u_data["inventory"].items() if v > 0]
    output = "\n".join(items) if items else "Lo zaino è vuoto."
    await interaction.response.send_message(f"🎒 **Zaino di {interaction.user.name}:**\n{output}")

@bot.tree.command(name="dai_item", description="Passa un oggetto a un altro cittadino")
@app_commands.autocomplete(item=item_autocomplete)
async def dai_item(interaction: discord.Interaction, ricevente: discord.Member, item: str, quantita: int = 1):
    db = load_db()
    u_data = get_user_data(db, interaction.user.id)
    r_data = get_user_data(db, ricevente.id)
    
    if u_data["inventory"].get(item, 0) < quantita:
        return await interaction.response.send_message("❌ Non ne hai abbastanza.", ephemeral=True)

    u_data["inventory"][item] -= quantita
    r_data["inventory"][item] = r_data["inventory"].get(item, 0) + quantita
    save_db(db)
    await interaction.response.send_message(f"🤝 Hai dato {quantita}x {item} a {ricevente.mention}.")

# --- ESECUZIONE ---
if TOKEN:
    bot.run(TOKEN)
else:
    print("⚠️ ERRORE: Variabile 'DISCORD_TOKEN' non trovata nei Secret di Base44.")
