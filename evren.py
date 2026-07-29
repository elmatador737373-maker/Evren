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
RUOLO_POLIZIA_ID = 123456789012345680         # Permesso per CAD Polizia e Porto d'Armi
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


# --- SISTEMA OGGETTI (COMANDO STAFF /crea_item & INVENTARIO) ---

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


# --- POLIZIA CAD (SELEZIONE PER NOME E COGNOME RP) ---

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
        embed = discord.Embed(
            title=f"🚔 Scheda Anagrafica: {self.doc.get('name')} {self.doc.get('surname')}",
            description=(
                f"• **Nome & Cognome:** `{self.doc.get('name')} {self.doc.get('surname')}`\n"
                f"• **Data di Nascita:** `{self.doc.get('birth_date', 'N/D')}`\n"
                f"• **Codice Fiscale:** `{self.doc.get('cf', 'N/D')}`\n"
                f"• **N° Documento:** `{self.doc.get('doc_number', 'N/D')}`\n"
                f"• **Discord User:** `<@{self.target_id_str}>`"
            ),
            color=discord.Color.dark_blue()
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="🚗 Proprietá", style=discord.ButtonStyle.success, row=0)
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

    @ui.button(label="🔫 Armi e Licenze", style=discord.ButtonStyle.danger, row=0)
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


class CitizenSelectMenu(ui.Select):
    def __init__(self, citizens_list: list, officer_id: int):
        options = []
        for c in citizens_list[:25]:
            options.append(discord.SelectOption(
                label=f"{c.get('name')} {c.get('surname')}",
                value=c.get("discord_id"),
                description=f"CF: {c.get('cf')} | Doc: {c.get('doc_number')}"
            ))
        super().__init__(placeholder="Seleziona il cittadino dal nome...", min_values=1, max_values=1, options=options)
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
                description="Usa i pulsanti sottostanti per verificare il profilo dell'individuo:",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)


class PoliceCadSelectView(ui.View):
    def __init__(self, citizens_list: list, officer_id: int):
        super().__init__(timeout=120)
        self.add_item(CitizenSelectMenu(citizens_list, officer_id))


@bot.tree.command(name="cad_polizia", description="[POLIZIA] Cerca un cittadino nel database tramite Nome e Cognome.")
async def cad_polizia(interaction: discord.Interaction):
    if RUOLO_POLIZIA_ID:
        police_role = interaction.guild.get_role(RUOLO_POLIZIA_ID)
        if police_role and police_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Riservato alle Forze dell'Ordine!", ephemeral=True)
            return

    res = supabase.table("documents").select("*").order("name", desc=False).execute()
    if not res.data:
        await interaction.response.send_message("❌ Nessun cittadino con documento trovato.", ephemeral=True)
        return

    view = PoliceCadSelectView(res.data, interaction.user.id)
    embed = discord.Embed(
        title="🚔 CAD Polizia di Stato",
        description="Seleziona Nome e Cognome del cittadino per la verifica:",
        color=discord.Color.dark_blue()
    )
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# --- COMANDI REGISTRAZIONE DOCUMENTI E SERVIZI ---

@bot.tree.command(name="crea_documenti", description="Genera i tuoi documenti identificativi (Codice Fiscale e Carta d'Identità).")
async def crea_documenti(interaction: discord.Interaction, nome: str, cognome: str, data_nascita: str):
    user_id = str(interaction.user.id)
    existing = supabase.table("documents").select("*").eq("discord_id", user_id).execute()

    if existing.data:
        doc = existing.data[0]
        await interaction.response.send_message(f"❌ Documenti già esistenti!\nCF: `{doc['cf']}`", ephemeral=True)
        return

    cf = genera_codice_fiscale(nome, cognome)
    doc_num = genera_num_documento()

    supabase.table("documents").insert({
        "discord_id": user_id,
        "name": nome.capitalize(),
        "surname": cognome.capitalize(),
        "birth_date": data_nascita,
        "cf": cf,
        "doc_number": doc_num
    }).execute()

    embed = discord.Embed(
        title="🪪 Documenti Rilasciati",
        description=f"• **Intestatario:** {nome.capitalize()} {cognome.capitalize()}\n• **Data di Nascita:** `{data_nascita}`\n• **Codice Fiscale:** `{cf}`\n• **Carta Identità:** `{doc_num}`",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


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
