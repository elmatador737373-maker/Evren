import os
import random
import threading
from flask import Flask, jsonify
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 5000))

RUOLO_BANCOMAT_ID = 123456789012345678  # Sostituisci con l'ID reale del ruolo bancomat
RUOLO_STAFF_ID = 123456789012345679     # Ruolo autorizzato a creare item e bypassare i requisiti

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Necessario per rilevare l'ingresso degli utenti nel server

class EvrenCityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(WelcomeView())
        await self.tree.sync()
        print("🔄 Comandi Slash e View persistenti sincronizzati con successo.")

bot = EvrenCityBot()


# --- VIEW PERSISTENTE PER I LINK DI BENVENUTO ---

class WelcomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Bottone Nº 1", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1500844219424706581", row=0)
    async def btn_1(self, interaction: discord.Interaction, button: discord.ui.Button): pass

    @discord.ui.button(label="Bottone Nº 2", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1252225171553652787", row=0)
    async def btn_2(self, interaction: discord.Interaction, button: discord.ui.Button): pass

    @discord.ui.button(label="Bottone Nº 3", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1374421195163963553", row=0)
    async def btn_3(self, interaction: discord.Interaction, button: discord.ui.Button): pass

    @discord.ui.button(label="Bottone Nº 4", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1519623994591019189", row=1)
    async def btn_4(self, interaction: discord.Interaction, button: discord.ui.Button): pass

    @discord.ui.button(label="Bottone Nº 5", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1252225106785337355", row=1)
    async def btn_5(self, interaction: discord.Interaction, button: discord.ui.Button): pass

    @discord.ui.button(label="Bottone Nº 6", style=discord.ButtonStyle.link, url="https://discord.com/channels/1233353915559313478/1503750254028390580", row=1)
    async def btn_6(self, interaction: discord.Interaction, button: discord.ui.Button): pass


# --- EVENTO DI BENVENUTO IN DM ---

@bot.event
async def on_member_join(member: discord.Member):
    try:
        welcome_text = (
            "✦ **BENVENUTO SU EVREN!** ✦\n"
            "Ecco i passaggi fondamentali per iniziare la tua avventura:\n\n"
            "> 🔓 **1. Sblocco Canali**\n"
            "> Se non vedi tutti i canali, segui la guida iniziale sul **Bottone Nº 1** del server per sbloccarli.\n\n"
            "> 📜 **2. Regolamenti**\n"
            "> Leggi le linee guida nei canali del **Bottone Nº 2**, **Bottone Nº 3** e **Bottone Nº 4** per conoscere le regole del server.\n\n"
            "> 📝 **3. Background**\n"
            "> Scrivi la storia del tuo personaggio seguendo i modelli nella sezione del **Bottone Nº 5**.\n\n"
            "> 🛡️ **4. Whitelist (WL)**\n"
            "> Invia la tua richiesta di WL nel canale del **Bottone Nº 6** per completare l'accesso e iniziare a giocare.\n\n"
            "Hai dubbi o domande? Lo staff è sempre a tua disposizione. Buon divertimento! ✨"
        )
        embed = discord.Embed(title="Benvenuto a bordo!", description=welcome_text, color=discord.Color.gold())
        await member.send(embed=embed, view=WelcomeView())
    except discord.Forbidden:
        print(f"❌ Impossibile inviare il messaggio privato di benvenuto a {member.name} (DM chiusi).")
    except Exception as e:
        print(f"⚠️ Errore nell'invio del benvenuto a {member.name}: {e}")


# --- FUNZIONI DATABASE & GESTIONE PESO ---

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
            "max_weight": 20.0
        }
        insert_res = supabase.table("users").insert(new_user).execute()
        return insert_res.data[0]

def get_user_current_weight(user_id: str):
    inv_res = supabase.table("inventory").select("quantity, items(weight)").eq("discord_id", user_id).execute()
    total_weight = 0.0
    if inv_res.data:
        for row in inv_res.data:
            item_info = row.get("items")
            if item_info:
                weight = float(item_info.get("weight", 0.0))
                qty = int(row.get("quantity", 1))
                total_weight += weight * qty
    return round(total_weight, 2)

def update_balance_safe(user_id: int, cash_change: float = 0.0, bank_change: float = 0.0):
    user = get_or_create_user(user_id, "Unknown")
    current_cash = float(user.get("cash", 0.0))
    current_bank = float(user.get("bank", 0.0))
    
    new_cash = current_cash + cash_change
    new_bank = current_bank + bank_change
    
    if new_cash < 0.0 or new_bank < 0.0:
        return False
        
    supabase.table("users").update({
        "cash": round(new_cash, 2),
        "bank": round(new_bank, 2)
    }).eq("discord_id", str(user_id)).execute()
    
    return True


# --- TASTIERINO BANCOMAT (VIEW) ---

class PinKeypadView(discord.ui.View):
    def __init__(self, user_id: int, user_data: dict, mode: str = "login"):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.user_data = user_data
        self.mode = mode
        self.entered_pin = ""
        self.max_length = 4

    async def update_display(self, interaction: discord.Interaction, message_text: str):
        masked_pin = "*" * len(self.entered_pin) + "_" * (self.max_length - len(self.entered_pin))
        embed = discord.Embed(
            title="💳 Tastierino Bancomat - Evren City RP",
            description=f"{message_text}\n\n**PIN inserito:** `{masked_pin}`",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def handle_digit(self, interaction: discord.Interaction, digit: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Questo bancomat non è per te!", ephemeral=True)
            return

        if len(self.entered_pin) < self.max_length:
            self.entered_pin += digit

        if len(self.entered_pin) == self.max_length:
            if self.mode == "register":
                supabase.table("users").update({"pin": self.entered_pin}).eq("discord_id", str(self.user_id)).execute()
                embed = discord.Embed(
                    title="🔐 Bancomat - Registrato",
                    description=f"PIN impostato con successo!\nSaldo Conto: **${float(self.user_data.get('bank', 0.0)):,.2f}**",
                    color=discord.Color.green()
                )
                self.stop()
                await interaction.response.edit_message(embed=embed, view=None)
            
            elif self.mode == "login":
                saved_pin = self.user_data.get("pin")
                if self.entered_pin == saved_pin:
                    bank_balance = float(self.user_data.get("bank", 0.0))
                    embed = discord.Embed(
                        title="💳 Bancomat - Accesso Riuscito",
                        description=f"Benvenuto nel tuo conto.\nSaldo attuale: **${bank_balance:,.2f}**",
                        color=discord.Color.green()
                    )
                    self.stop()
                    await interaction.response.edit_message(embed=embed, view=None)
                else:
                    self.entered_pin = ""
                    await self.update_display(interaction, "❌ **PIN Errato!** Riprova:")
        else:
            action_text = "Crea il tuo PIN segreto di 4 cifre:" if self.mode == "register" else "Inserisci il tuo PIN segreto:"
            await self.update_display(interaction, action_text)

    @discord.ui.button(label="1", style=discord.ButtonStyle.secondary, row=0)
    async def b1(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "1")
    @discord.ui.button(label="2", style=discord.ButtonStyle.secondary, row=0)
    async def b2(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "2")
    @discord.ui.button(label="3", style=discord.ButtonStyle.secondary, row=0)
    async def b3(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "3")
    @discord.ui.button(label="4", style=discord.ButtonStyle.secondary, row=1)
    async def b4(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "4")
    @discord.ui.button(label="5", style=discord.ButtonStyle.secondary, row=1)
    async def b5(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "5")
    @discord.ui.button(label="6", style=discord.ButtonStyle.secondary, row=1)
    async def b6(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "6")
    @discord.ui.button(label="7", style=discord.ButtonStyle.secondary, row=2)
    async def b7(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "7")
    @discord.ui.button(label="8", style=discord.ButtonStyle.secondary, row=2)
    async def b8(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "8")
    @discord.ui.button(label="9", style=discord.ButtonStyle.secondary, row=2)
    async def b9(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "9")
    @discord.ui.button(label="C", style=discord.ButtonStyle.danger, row=3)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        self.entered_pin = ""
        action_text = "Crea il tuo PIN segreto di 4 cifre:" if self.mode == "register" else "Inserisci il tuo PIN segreto:"
        await self.update_display(interaction, action_text)
    @discord.ui.button(label="0", style=discord.ButtonStyle.secondary, row=3)
    async def b0(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_digit(interaction, "0")
    @discord.ui.button(label="✖", style=discord.ButtonStyle.danger, row=3)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        self.stop()
        await interaction.response.edit_message(content="❌ Operazione annullata.", embed=None, view=None)


# --- COMANDI ECONOMIA & BANCOMAT ---

@bot.event
async def on_ready():
    print(f"✅ Bot online come {bot.user} (Evren City RP)")

@bot.tree.command(name="portafoglio", description="Mostra i contanti che hai nel portafoglio.")
async def portafoglio(interaction: discord.Interaction):
    user_data = get_or_create_user(interaction.user.id, interaction.user.name)
    cash = float(user_data.get("cash", 0.0))
    embed = discord.Embed(title="💼 Portafoglio - Evren City RP", description=f"Contanti attuali di **{interaction.user.mention}**:\n💵 **${cash:,.2f}**", color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="bancomat", description="Accedi al conto bancario tramite tastierino interattivo.")
async def bancomat(interaction: discord.Interaction):
    if RUOLO_BANCOMAT_ID:
        role = interaction.guild.get_role(RUOLO_BANCOMAT_ID)
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message(f"❌ Non possiedi il ruolo richiesto per accedere agli sportelli bancari.", ephemeral=True)
            return

    user_data = get_or_create_user(interaction.user.id, interaction.user.name)
    saved_pin = user_data.get("pin")

    if saved_pin is None:
        view = PinKeypadView(interaction.user.id, user_data, mode="register")
        embed = discord.Embed(title="💳 Bancomat - Primo Accesso", description="Crea il tuo PIN segreto di 4 cifre:\n\n**PIN inserito:** `____`", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        view = PinKeypadView(interaction.user.id, user_data, mode="login")
        embed = discord.Embed(title="💳 Tastierino Bancomat - Evren City RP", description="Inserisci il tuo PIN segreto:\n\n**PIN inserito:** `____`", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --- AUTOCOMPLETE INTELLIGENTE ---

async def user_inventory_autocomplete(interaction: discord.Interaction, current: str):
    res = supabase.table("inventory").select("item_id, items(name)").eq("discord_id", str(interaction.user.id)).execute()
    items = []
    if res.data:
        for row in res.data:
            item_info = row.get("items")
            if item_info:
                name = item_info.get("name")
                if current.lower() in name.lower():
                    items.append(app_commands.Choice(name=name, value=name))
    return items[:25]

async def global_items_autocomplete(interaction: discord.Interaction, current: str):
    res = supabase.table("items").select("name").ilike("name", f"%{current}%").limit(25).execute()
    return [app_commands.Choice(name=row["name"], value=row["name"]) for row in res.data] if res.data else []


# --- GESTIONE OGGETTI & SHOP ---

@bot.tree.command(name="item-crea", description="[STAFF] Crea un nuovo oggetto con peso, ruolo richiesto, categoria e azione.")
@app_commands.describe(
    name="Nome univoco dell'oggetto",
    category="Categoria dell'oggetto",
    action_type="Azione scatenata all'uso",
    weight="Peso in kg (per gli zaini rappresenta i kg di espansione capienza)",
    required_role="Ruolo richiesto per acquistarlo/riceverlo (Lasciare vuoto se libero)",
    success_rate="Percentuale di successo (0 a 100)",
    description="Descrizione dell'oggetto"
)
@app_commands.choices(category=[
    app_commands.Choice(name="Cibo / Bevanda", value="cibo"),
    app_commands.Choice(name="Droga / Sostanza", value="droga"),
    app_commands.Choice(name="Arma / Munizioni", value="arma"),
    app_commands.Choice(name="Zaino / Contenitore", value="zaino"),
    app_commands.Choice(name="Strumento / Utility", value="strumento"),
    app_commands.Choice(name="Medico / Cura", value="medico"),
    app_commands.Choice(name="Generico", value="generico")
], action_type=[
    app_commands.Choice(name="Espandi Zaino (Capacità Inventario)", value="expand_backpack"),
    app_commands.Choice(name="Guarisci / Ripristina HP", value="heal"),
    app_commands.Choice(name="Dà Denaro (Contanti)", value="give_cash"),
    app_commands.Choice(name="Rischio / Sballo (Effetto Casuale)", value="sballo"),
    app_commands.Choice(name="Sblocca Accesso / Azione RP", value="rp_action"),
    app_commands.Choice(name="Distruggilo / Consumabile Normale", value="consume")
])
async def item_crea(
    interaction: discord.Interaction, 
    name: str, 
    category: str, 
    action_type: str, 
    weight: float, 
    required_role: discord.Role = None, 
    success_rate: int = 100, 
    description: str = "Nessuna descrizione."
):
    if RUOLO_STAFF_ID:
        role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message("❌ Non hai i permessi per creare oggetti.", ephemeral=True)
            return

        if weight < 0.0:
            await interaction.response.send_message("❌ Il valore non può essere negativo.", ephemeral=True)
            return

        if not (0 <= success_rate <= 100):
            await interaction.response.send_message("❌ La percentuale di successo deve essere tra **0 e 100**.", ephemeral=True)
            return

        item_data = {
            "name": name,
            "category": category,
            "action_type": action_type,
            "weight": round(weight, 2),
            "required_role_id": str(required_role.id) if required_role else None,
            "success_rate": success_rate,
            "description": description
        }
        
        supabase.table("items").upsert(item_data, on_conflict="name").execute()

        role_name = required_role.name if required_role else "Nessuno (Libero)"
        embed = discord.Embed(
            title="📦 Oggetto Creato con Successo!",
            description=(
                f"**Nome:** `{name}`\n"
                f"**Categoria:** `{category}`\n"
                f"**Valore/Peso:** `{weight} kg`\n"
                f"**Ruolo Richiesto:** `{role_name}`\n"
                f"**Azione:** `{action_type}`\n"
                f"**Successo:** `{success_rate}%`\n"
                f"**Descrizione:** {description}"
            ),
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="compra", description="Acquista un oggetto dallo shop (con ricerca intelligente e controllo ruoli/peso).")
@app_commands.describe(item_name="Nome o parte del nome dell'oggetto da acquistare", quantity="Quantità (default 1)", price="Prezzo totale o unitario dell'acquisto")
@app_commands.autocomplete(item_name=global_items_autocomplete)
async def compra(interaction: discord.Interaction, item_name: str, price: float, quantity: int = 1):
    user_id = str(interaction.user.id)
    user_data = get_or_create_user(interaction.user.id, interaction.user.name)
    max_weight = float(user_data.get("max_weight", 20.0))
    current_cash = float(user_data.get("cash", 0.0))

    item_res = supabase.table("items").select("*").ilike("name", f"%{item_name}%").execute()
    if not item_res.data:
        await interaction.response.send_message("❌ Nessun oggetto trovato con questo nome nel database.", ephemeral=True)
        return
    
    item = item_res.data[0]
    real_item_name = item["name"]
    item_id = item["id"]
    category = item["category"]
    item_weight = float(item.get("weight", 0.0))
    required_role_id = item.get("required_role_id")

    is_staff = False
    if RUOLO_STAFF_ID:
        staff_role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if staff_role and staff_role in interaction.user.roles:
            is_staff = True

    if required_role_id and not is_staff:
        req_role = interaction.guild.get_role(int(required_role_id))
        if not req_role or req_role not in interaction.user.roles:
            await interaction.response.send_message(
                f"❌ Non possiedi il ruolo richiesto (**{req_role.name if req_role else 'Ruolo Specifico'}**) per acquistare **{real_item_name}**.",
                ephemeral=True
            )
            return

    if current_cash < price:
        await interaction.response.send_message(
            f"❌ **Fondi insufficienti!** Ti servono **${price:,.2f}** in contanti, ma ne hai solo **${current_cash:,.2f}**.",
            ephemeral=True
        )
        return

    current_weight = get_user_current_weight(user_id)
    added_weight = item_weight * quantity
    if (current_weight + added_weight) > max_weight:
        await interaction.response.send_message(
            f"❌ **Zaino Pieno!** Non puoi trasportare questo peso.\n"
            f"• Peso attuale: `{current_weight} kg` / `{max_weight} kg`\n"
            f"• Peso aggiuntivo richiesto: `{added_weight} kg`",
            ephemeral=True
        )
        return

    success_payment = update_balance_safe(interaction.user.id, cash_change=-price)
    if not success_payment:
        await interaction.response.send_message("❌ Errore durante la transazione monetaria.", ephemeral=True)
        return

    final_item_name = real_item_name
    if category == "arma":
        serial_part1 = f"{random.randint(1000, 9999)}"
        serial_part2 = f"{random.randint(1000, 9999)}"
        matricola = f"[{serial_part1}-{serial_part2}]"
        final_item_name = f"{real_item_name} {matricola}"

    if category == "arma":
        supabase.table("inventory").insert({
            "discord_id": user_id,
            "item_id": item_id,
            "quantity": quantity,
            "custom_name": final_item_name
        }).execute()
    else:
        inv_res = supabase.table("inventory").select("*").eq("discord_id", user_id).eq("item_id", item_id).is_("custom_name", "null").execute()
        if inv_res.data:
            new_qty = inv_res.data[0]["quantity"] + quantity
            supabase.table("inventory").update({"quantity": new_qty}).eq("id", inv_res.data[0]["id"]).execute()
        else:
            supabase.table("inventory").insert({"discord_id": user_id, "item_id": item_id, "quantity": quantity}).execute()

    new_total_w = get_user_current_weight(user_id)
    remaining_cash = current_cash - price

    embed = discord.Embed(
        title="🛍️ Acquisto Effettuato con Successo!",
        description=(
            f"Hai acquistato **{quantity}x {final_item_name}** per **${price:,.2f}**.\n\n"
            f"💵 Contanti rimasti: **${remaining_cash:,.2f}**\n"
            f"🎒 Peso zaino: **{new_total_w} / {max_weight} kg**"
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="vendi", description="Vendi un oggetto dal tuo inventario per recuperare contanti.")
@app_commands.describe(item_name="Seleziona l'oggetto da vendere dal tuo inventario", price="Prezzo totale o unitario di vendita", quantity="Quantità da vendere (default 1)")
@app_commands.autocomplete(item_name=user_inventory_autocomplete)
async def vendi(interaction: discord.Interaction, item_name: str, price: float, quantity: int = 1):
    user_id = str(interaction.user.id)

    if price < 0.0:
        await interaction.response.send_message("❌ Il prezzo di vendita non può essere negativo.", ephemeral=True)
        return

    if quantity <= 0:
        await interaction.response.send_message("❌ La quantità deve essere maggiore di zero.", ephemeral=True)
        return

    inv_query = supabase.table("inventory").select("id, quantity, custom_name, item_id, items(*)").eq("discord_id", user_id).execute()
    
    target_row = None
    if inv_query.data:
        for row in inv_query.data:
            item_info = row.get("items")
            if item_info:
                base_name = item_info.get("name")
                custom = row.get("custom_name")
                displayed_name = custom if custom else base_name
                if displayed_name.lower() == item_name.lower() or base_name.lower() == item_name.lower():
                    target_row = row
                    break

    if not target_row or target_row["quantity"] < quantity:
        await interaction.response.send_message("❌ Non possiedi una quantità sufficiente di questo oggetto nel tuo inventario!", ephemeral=True)
        return

    current_qty = target_row["quantity"]
    row_id = target_row["id"]
    display_name = target_row.get("custom_name") if target_row.get("custom_name") else target_row["items"]["name"]

    success_payment = update_balance_safe(interaction.user.id, cash_change=price)
    if not success_payment:
        await interaction.response.send_message("❌ Errore durante l'accredito dei contanti.", ephemeral=True)
        return

    new_qty = current_qty - quantity
    if new_qty <= 0:
        supabase.table("inventory").delete().eq("id", row_id).execute()
    else:
        supabase.table("inventory").update({"quantity": new_qty}).eq("id", row_id).execute()

    user_data = get_or_create_user(interaction.user.id, interaction.user.name)
    new_cash = float(user_data.get("cash", 0.0))
    max_weight = float(user_data.get("max_weight", 20.0))
    new_weight = get_user_current_weight(user_id)

    embed = discord.Embed(
        title="💰 Vendita Effettuata con Successo!",
        description=(
            f"Hai venduto **{quantity}x {display_name}** per **${price:,.2f}**.\n\n"
            f"💵 Contanti attuali: **${new_cash:,.2f}**\n"
            f"🎒 Peso zaino: **{new_weight} / {max_weight} kg**"
        ),
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="item-give", description="[STAFF] Aggiunge un oggetto direttamente all'inventario di un utente.")
@app_commands.describe(member="Utente a cui dare l'oggetto", item_name="Nome dell'oggetto da dare", quantity="Quantità (default 1)")
@app_commands.autocomplete(item_name=global_items_autocomplete)
async def item_give(interaction: discord.Interaction, member: discord.Member, item_name: str, quantity: int = 1):
    if RUOLO_STAFF_ID:
        role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando.", ephemeral=True)
            return

    if quantity <= 0:
        await interaction.response.send_message("❌ La quantità deve essere maggiore di zero.", ephemeral=True)
        return

    user_id = str(member.id)
    user_data = get_or_create_user(member.id, member.name)
    max_weight = float(user_data.get("max_weight", 20.0))

    item_res = supabase.table("items").select("*").ilike("name", f"%{item_name}%").execute()
    if not item_res.data:
        await interaction.response.send_message("❌ Oggetto non trovato nel database.", ephemeral=True)
        return
    
    item = item_res.data[0]
    item_id = item["id"]
    category = item["category"]
    item_weight = float(item.get("weight", 0.0))

    final_item_name = item["name"]
    if category == "arma":
        serial_part1 = f"{random.randint(1000, 9999)}"
        serial_part2 = f"{random.randint(1000, 9999)}"
        matricola = f"[{serial_part1}-{serial_part2}]"
        final_item_name = f"{item['name']} {matricola}"

    current_weight = get_user_current_weight(user_id)
    added_weight = item_weight * quantity
    
    if (current_weight + added_weight) > max_weight:
        await interaction.response.send_message(
            f"❌ **Zaino Pieno!** L'utente non può trasportare questo peso.\n"
            f"• Peso attuale: `{current_weight} kg` / `{max_weight} kg`\n"
            f"• Peso aggiuntivo richiesto: `{added_weight} kg`",
            ephemeral=True
        )
        return

    if category == "arma":
        supabase.table("inventory").insert({
            "discord_id": user_id,
            "item_id": item_id,
            "quantity": quantity,
            "custom_name": final_item_name
        }).execute()
    else:
        inv_res = supabase.table("inventory").select("*").eq("discord_id", user_id).eq("item_id", item_id).is_("custom_name", "null").execute()
        if inv_res.data:
            new_qty = inv_res.data[0]["quantity"] + quantity
            supabase.table("inventory").update({"quantity": new_qty}).eq("id", inv_res.data[0]["id"]).execute()
        else:
            supabase.table("inventory").insert({"discord_id": user_id, "item_id": item_id, "quantity": quantity}).execute()

    new_total_w = get_user_current_weight(user_id)
    await interaction.response.send_message(
        f"✅ Hai dato **{quantity}x {final_item_name}** a **{member.mention}** (`{added_weight} kg`).\n"
        f"🎒 Peso zaino utente: **{new_total_w} / {max_weight} kg**",
        ephemeral=True
    )


@bot.tree.command(name="item-remove", description="[STAFF] Rimuove un oggetto dall'inventario di un utente.")
@app_commands.describe(member="Utente da cui rimuovere l'oggetto", item_name="Nome o parte del nome dell'oggetto", quantity="Quantità da rimuovere (default 1)")
@app_commands.autocomplete(item_name=user_inventory_autocomplete)
async def item_remove(interaction: discord.Interaction, member: discord.Member, item_name: str, quantity: int = 1):
    if RUOLO_STAFF_ID:
        role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando.", ephemeral=True)
            return

    if quantity <= 0:
        await interaction.response.send_message("❌ La quantità deve essere maggiore di zero.", ephemeral=True)
        return

    user_id = str(member.id)
    inv_query = supabase.table("inventory").select("id, quantity, custom_name, item_id, items(*)").eq("discord_id", user_id).execute()
    
    target_row = None
    if inv_query.data:
        for row in inv_query.data:
            item_info = row.get("items")
            if item_info:
                base_name = item_info.get("name")
                custom = row.get("custom_name")
                displayed_name = custom if custom else base_name
                if displayed_name.lower() == item_name.lower() or base_name.lower() == item_name.lower():
                    target_row = row
                    break

    if not target_row or target_row["quantity"] < quantity:
        await interaction.response.send_message("❌ L'utente non possiede una quantità sufficiente di questo oggetto!", ephemeral=True)
        return

    current_qty = target_row["quantity"]
    row_id = target_row["id"]
    display_name = target_row.get("custom_name") if target_row.get("custom_name") else target_row["items"]["name"]

    new_qty = current_qty - quantity
    if new_qty <= 0:
        supabase.table("inventory").delete().eq("id", row_id).execute()
    else:
        supabase.table("inventory").update({"quantity": new_qty}).eq("id", row_id).execute()

    new_weight = get_user_current_weight(user_id)
    user_data = get_or_create_user(member.id, member.name)
    max_weight = float(user_data.get("max_weight", 20.0))

    await interaction.response.send_message(
        f"✅ Rimosso con successo **{quantity}x {display_name}** dall'inventario di **{member.mention}**.\n"
        f"🎒 Peso zaino attuale: **{new_weight} / {max_weight} kg**",
        ephemeral=True
    )


@bot.tree.command(name="add-money", description="[STAFF] Aggiunge denaro (contanti o banca) a un utente.")
@app_commands.describe(member="Utente a cui aggiungere denaro", wallet="Contanti da aggiungere", bank="Denaro in banca da aggiungere")
async def add_money(interaction: discord.Interaction, member: discord.Member, wallet: float = 0.0, bank: float = 0.0):
    if RUOLO_STAFF_ID:
        role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando.", ephemeral=True)
            return

    if wallet < 0.0 or bank < 0.0:
        await interaction.response.send_message("❌ Non puoi aggiungere valori negativi.", ephemeral=True)
        return

    success = update_balance_safe(member.id, cash_change=wallet, bank_change=bank)
    if not success:
        await interaction.response.send_message("❌ Errore durante l'aggiornamento del saldo.", ephemeral=True)
        return

    updated_user = get_or_create_user(member.id, member.name)
    await interaction.response.send_message(
        f"✅ Aggiunti a **{member.mention}**:\n"
        f"💵 Contanti: **+${wallet:,.2f}** (Totale: ${float(updated_user.get('cash', 0)):,.2f})\n"
        f"💳 Banca: **+${bank:,.2f}** (Totale: ${float(updated_user.get('bank', 0)):,.2f})",
        ephemeral=True
    )


@bot.tree.command(name="remove-money", description="[STAFF] Rimuove denaro (contanti o banca) da un utente (con controllo anti-negativo).")
@app_commands.describe(member="Utente da cui rimuovere denaro", wallet="Contanti da rimuovere", bank="Denaro in banca da rimuovere")
async def remove_money(interaction: discord.Interaction, member: discord.Member, wallet: float = 0.0, bank: float = 0.0):
    if RUOLO_STAFF_ID:
        role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando.", ephemeral=True)
            return

    if wallet < 0.0 or bank < 0.0:
        await interaction.response.send_message("❌ Inserisci valori positivi da sottrarre.", ephemeral=True)
        return

    user_data = get_or_create_user(member.id, member.name)
    current_cash = float(user_data.get("cash", 0.0))
    current_bank = float(user_data.get("bank", 0.0))

    if current_cash < wallet or current_bank < bank:
        await interaction.response.send_message(
            f"❌ L'utente non ha abbastanza fondi da rimuovere!\n"
            f"• Contanti attuali: **${current_cash:,.2f}** (Richiesti: ${wallet:,.2f})\n"
            f"• Banca attuale: **${current_bank:,.2f}** (Richiesti: ${bank:,.2f})",
            ephemeral=True
        )
        return

    success = update_balance_safe(member.id, cash_change=-wallet, bank_change=-bank)
    if not success:
        await interaction.response.send_message("❌ Errore durante la rimozione del denaro.", ephemeral=True)
        return

    updated_user = get_or_create_user(member.id, member.name)
    await interaction.response.send_message(
        f"✅ Rimossi da **{member.mention}**:\n"
        f"💵 Contanti: **-${wallet:,.2f}** (Rimasti: ${float(updated_user.get('cash', 0)):,.2f})\n"
        f"💳 Banca: **-${bank:,.2f}** (Rimasti: ${float(updated_user.get('bank', 0)):,.2f})",
        ephemeral=True
    )

@bot.tree.command(name="zaino", description="Mostra il contenuto del tuo zaino, il peso attuale e la capienza massima.")
async def zaino(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_data = get_or_create_user(interaction.user.id, interaction.user.name)
    max_weight = float(user_data.get("max_weight", 20.0))
    current_weight = get_user_current_weight(user_id)

    inv_res = supabase.table("inventory").select("quantity, custom_name, items(name, category, weight, description)").eq("discord_id", user_id).execute()

    embed = discord.Embed(
        title=f"🎒 Zaino di {interaction.user.display_name}",
        description=f"Capacità Massima: **{current_weight} kg / {max_weight} kg**",
        color=discord.Color.blurple()
    )

    if not inv_res.data:
        embed.add_field(name="Zaino Vuoto", value="Non hai nessun oggetto all'interno.", inline=False)
    else:
        for row in inv_res.data:
            item_info = row.get("items")
            if item_info:
                qty = row.get("quantity")
                name = row.get("custom_name") if row.get("custom_name") else item_info.get("name")
                cat = item_info.get("category").upper()
                w = float(item_info.get("weight", 0.0))
                total_item_w = round(w * qty, 2)
                desc = item_info.get("description")
                embed.add_field(
                    name=f"[{cat}] {name} (x{qty})",
                    value=f"Peso unitario: `{w} kg` | Totale: `{total_item_w} kg`\n*{desc}*",
                    inline=False
                )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="zaino-modifica", description="[STAFF] Modifica la capienza massima dello zaino di un utente.")
@app_commands.describe(member="Utente da modificare", new_max_weight="Nuovo peso massimo in kg (es. 50.0)")
async def zaino_modifica(interaction: discord.Interaction, member: discord.Member, new_max_weight: float):
    if RUOLO_STAFF_ID:
        role = interaction.guild.get_role(RUOLO_STAFF_ID)
        if not role or role not in interaction.user.roles:
            await interaction.response.send_message("❌ Non hai i permessi per modificare gli zaini.", ephemeral=True)
            return

        if new_max_weight < 1.0:
            await interaction.response.send_message("❌ La capienza minima dello zaino deve essere almeno `1.0 kg`.", ephemeral=True)
            return

        get_or_create_user(member.id, member.name)
        supabase.table("users").update({"max_weight": round(new_max_weight, 2)}).eq("discord_id", str(member.id)).execute()

        await interaction.response.send_message(
            f"✅ Capienza dello zaino di **{member.mention}** impostata a **{new_max_weight} kg**.",
            ephemeral=True
        )


@bot.tree.command(name="usa", description="Usa un oggetto dal tuo inventario in base alla sua categoria e azione.")
@app_commands.describe(item_name="Seleziona l'oggetto da usare dal tuo inventario")
@app_commands.autocomplete(item_name=user_inventory_autocomplete)
async def usa(interaction: discord.Interaction, item_name: str):
    user_id = str(interaction.user.id)

    inv_query = supabase.table("inventory").select("id, quantity, custom_name, item_id, items(*)").eq("discord_id", user_id).execute()
    
    target_row = None
    if inv_query.data:
        for row in inv_query.data:
            item_info = row.get("items")
            if item_info:
                base_name = item_info.get("name")
                custom = row.get("custom_name")
                displayed_name = custom if custom else base_name
                if displayed_name.lower() == item_name.lower() or base_name.lower() == item_name.lower():
                    target_row = row
                    break

    if not target_row or target_row["quantity"] <= 0:
        await interaction.response.send_message("❌ Non possiedi questo oggetto nel tuo inventario!", ephemeral=True)
        return

    item = target_row["items"]
    item_id = item["id"]
    category = item["category"]
    action_type = item["action_type"]
    success_rate = item["success_rate"]
    item_weight = float(item.get("weight", 0.0))
    current_qty = target_row["quantity"]
    row_id = target_row["id"]
    display_name = target_row.get("custom_name") if target_row.get("custom_name") else item["name"]

    roll = random.randint(1, 100)
    successo = roll <= success_rate

    if not successo:
        new_qty = current_qty - 1
        if new_qty <= 0:
            supabase.table("inventory").delete().eq("id", row_id).execute()
        else:
            supabase.table("inventory").update({"quantity": new_qty}).eq("id", row_id).execute()

        await interaction.response.send_message(
            f"⚠️ Hai tentato di usare **{display_name}**, ma qualcosa è andato storto e l'oggetto è andato sprecato! *(Tiro: {roll}/{success_rate}%)*",
            ephemeral=True
        )
        return

    risultato_testo = ""
    if category == "zaino" or action_type == "expand_backpack":
        user_data = get_or_create_user(interaction.user.id, interaction.user.name)
        current_max_weight = float(user_data.get("max_weight", 20.0))
        expansion_amount = item_weight if item_weight > 0 else 10.0
        new_max_weight = current_max_weight + expansion_amount

        supabase.table("users").update({"max_weight": round(new_max_weight, 2)}).eq("discord_id", str(interaction.user.id)).execute()
        risultato_testo = f"🎒 Hai indossato/aperto **{display_name}**. La capienza massima del tuo zaino è aumentata di **+{expansion_amount} kg**! (Nuovo limite: **{new_max_weight} kg**)"
    elif category == "cibo":
        risultato_testo = f"🍔 Hai mangiato/bevuto **{display_name}**. Sazi la tua fame e ti senti in forze!"
    elif category == "medico":
        risultato_testo = f"💉 Hai usato il kit medico **{display_name}**. Le tue ferite si rimarginano correttamente."
    elif category == "droga":
        risultato_testo = f"💊 Hai assunto **{display_name}**. Una strana euforia comincia a scorrere nel tuo corpo..."
    elif category == "arma":
        risultato_testo = f"🔫 Hai impugnato l'arma **{display_name}** ed estratto la sicura. Prontə all'azione!"
    elif category == "strumento":
        if action_type == "give_cash":
            vincita = random.randint(50, 250)
            update_balance_safe(interaction.user.id, cash_change=vincita)
            risultato_testo = f"🔧 Hai utilizzato con successo **{display_name}** e hai ricavato **${vincita:.2f}** in contanti!"
        else:
            risultato_testo = f"🛠️ Hai adoperato lo strumento **{display_name}** con successo."
    else:
        risultato_testo = f"✨ Hai usato con successo l'oggetto **{display_name}**."

    new_qty = current_qty - 1
    if new_qty <= 0:
        supabase.table("inventory").delete().eq("id", row_id).execute()
    else:
        supabase.table("inventory").update({"quantity": new_qty}).eq("id", row_id).execute()

    new_weight = get_user_current_weight(user_id)
    updated_user = get_or_create_user(interaction.user.id, interaction.user.name)
    current_max_w = float(updated_user.get("max_weight", 20.0))

    embed = discord.Embed(
        title=f"📦 Utilizzo Oggetto: {display_name}",
        description=f"{risultato_testo}\n\n*(Tiro di successo: {roll}/{success_rate}%)*\n⚖️ Zaino: `{new_weight} / {current_max_w} kg`",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- SERVER FLASK INTEGRATO ---
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "online", "server": "Evren City RP", "message": "Flask & Bot running with smart-search compra & vendi commands!"})

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.run(DISCORD_TOKEN)
