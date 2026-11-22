import os
import json
import asyncio
from threading import Thread
from flask import Flask
import discord
from discord.ext import commands, tasks

# =====================================================================
# MINE ROLEPLAY - DISCORD SERVER ARCHITECT & BACKUP BOT (PERMESSI FULL)
# Gerarchia Ruoli Blindata + Canali Bandi Dedicati + Auto-Popolamento Guide
# =====================================================================

TOKEN = os.getenv("DISCORD_TOKEN")
BACKUP_FILE = "backup_mine_roleplay.json"

app = Flask(__name__)

@app.route("/")
def health():
    return "Mine Roleplay Architect Bot Online", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# =====================================================================
# 1. GERARCHIA RUOLI COMPLETA (DALL'ALTO VERSO IL BASSO - ORDINE ESATTO)
# Formato: (chiave, nome, colore_hex, hoist, is_admin, is_staff)
# =====================================================================
RUOLI_TEMPLATE = [
    ("creator", "👑・𝐂𝐫𝐞𝐚𝐭𝐨𝐫 𝐎𝐟 𝐌𝐢𝐧𝐞 𝐑𝐨𝐥𝐞𝐩𝐥𝐚𝐲 ®", 0xFF0033, True, True, True),
    ("cocreator", "🔱・𝐂𝐨-𝐂𝐫𝐞𝐚𝐭𝐨𝐫 𝐎𝐟 𝐌𝐢𝐧𝐞 𝐑𝐨𝐥𝐞𝐩𝐥𝐚𝐲 ®", 0x00E5FF, True, True, True),
    ("bot_mr", "🤖・𝐌𝐢𝐧𝐞 𝐑𝐨𝐥𝐞𝐩𝐥𝐚𝐲 𝐁𝐨𝐭 ®", 0x00B8D4, True, True, True),
    ("bot_off", "⚙️・𝐎𝐟𝐟𝐢𝐜𝐢𝐚𝐥 𝐁𝐨𝐭 ®", 0x546E7A, True, False, False),
    ("key_perm", "🔑・𝐀𝐜𝐜𝐞𝐬𝐬𝐨 𝐒𝐢𝐬𝐭𝐞𝐦𝐚", 0xFFD600, False, True, True),

    ("sep_dir", "⫷・═══ 𝐃𝐈𝐑𝐄𝐙𝐈𝐎𝐍𝐄 & 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓 ═══・⫸", 0x2B2D31, True, False, False),
    ("owner", "🦅・𝐎𝐰𝐧𝐞𝐫 ®", 0xD50000, True, True, True),
    ("deputy_owner", "🦁・𝐃𝐞𝐩𝐮𝐭𝐲 𝐎𝐰𝐧𝐞𝐫 ®", 0xFF1744, True, True, True),
    ("head_dev", "🧠・𝐇𝐞𝐚𝐝 𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐫 ®", 0xAA00FF, True, True, True),
    ("head_staff", "⚜️・𝐇𝐞𝐚𝐝 𝐎𝐟 𝐒𝐭𝐚𝐟𝐟 ®", 0xFF9100, True, False, True),
    ("head_admin", "🛡️・𝐇𝐞𝐚𝐝 𝐀𝐝𝐦𝐢𝐧 ®", 0xFF3D00, True, False, True),
    ("senior_admin", "🐆・𝐒𝐞𝐧𝐢𝐨𝐫 𝐀𝐝𝐦𝐢𝐧 ®", 0xF50057, True, False, True),
    ("admin", "🧿・𝐀𝐝𝐦𝐢𝐧 ®", 0x2979FF, True, False, True),
    ("trial_admin", "🚀・𝐓𝐫𝐢𝐚𝐥 𝐀𝐝𝐦𝐢𝐧 ®", 0x00B0FF, True, False, True),

    ("sep_mod", "⫷・═══ 𝐀𝐌𝐌𝐈𝐍𝐈𝐒𝐓𝐑𝐀𝐙𝐈𝐎𝐍𝐄 & 𝐒𝐓𝐀𝐅𝐅 ═══・⫸", 0x2B2D31, True, False, False),
    ("head_mod", "🎖️・𝐇𝐞𝐚𝐝 𝐌𝐨𝐝 ®", 0x00C853, True, False, True),
    ("senior_mod", "⚡・𝐒𝐞𝐧𝐢𝐨𝐫 𝐌𝐨𝐝 ®", 0x00E676, True, False, True),
    ("mod", "🔰・𝐌𝐨𝐝𝐞𝐫𝐚𝐭𝐨𝐫 ®", 0x69F0AE, True, False, True),
    ("helper", "🎧・𝐇𝐞𝐥𝐩𝐞𝐫 / 𝐒𝐮𝐩𝐩𝐨𝐫𝐭 ®", 0x1DE9B6, True, False, True),
    ("dev", "💻・𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐫 ®", 0x7C4DFF, True, False, True),
    ("gest_ticket", "🎫・𝐆𝐞𝐬𝐭𝐨𝐫𝐞 𝐓𝐢𝐜𝐤𝐞𝐭", 0xFFEA00, False, False, True),
    ("gest_perma", "☠️・𝐆𝐞𝐬𝐭𝐨𝐫𝐞 𝐏𝐞𝐫𝐦𝐚𝐃𝐞𝐚𝐭𝐡", 0xB71C1C, False, False, True),
    ("whitelister", "📋・𝐖𝐡𝐢𝐭𝐞𝐥𝐢𝐬𝐭𝐞𝐫", 0x00BFA5, False, False, True),
    ("staff_on", "🟢・𝐒𝐭𝐚𝐟𝐟 𝐈𝐧 𝐒𝐞𝐫𝐯𝐢𝐳𝐢𝐨 ®", 0x00E676, True, False, True),
    ("staff_off", "🔴・𝐒𝐭𝐚𝐟𝐟 𝐅𝐮𝐨𝐫𝐢 𝐒𝐞𝐫𝐯𝐢𝐳𝐢𝐨 ®", 0xFF5252, False, False, True),
    ("staff_team", "💎・𝐒𝐭𝐚𝐟𝐟 𝐎𝐟 𝐌𝐢𝐧𝐞 𝐑𝐨𝐥𝐞𝐩𝐥𝐚𝐲 ®", 0x00E5FF, True, False, True),

    ("sep_sanz", "⫷・════ 𝐒𝐀𝐍𝐙𝐈𝐎𝐍𝐈 & 𝐀𝐕𝐕𝐈𝐒𝐈 ════・⫸", 0x2B2D31, False, False, False),
    ("sanz_1", "1️⃣・𝐒𝐚𝐧𝐳𝐢𝐨𝐧𝐞 𝟏", 0xFFF176, False, False, False),
    ("sanz_2", "2️⃣・𝐒𝐚𝐧𝐳𝐢𝐨𝐧𝐞 𝟐", 0xFFB74D, False, False, False),
    ("sanz_3", "3️⃣・𝐒𝐚𝐧𝐳𝐢𝐨𝐧𝐞 𝟑 (𝐔𝐥𝐭𝐢𝐦𝐨 𝐀𝐯𝐯𝐢𝐬𝐨)", 0xE57373, False, False, False),

    ("sep_gov", "⫷・═══ 𝐆𝐎𝐕𝐄𝐑𝐍𝐎 & 𝐌𝐀𝐆𝐈𝐒𝐓𝐑𝐀𝐓𝐔𝐑𝐀 ═══・⫸", 0x2B2D31, True, False, False),
    ("governatore", "🏛️・𝐆𝐨𝐯𝐞𝐫𝐧𝐚𝐭𝐨𝐫𝐞 𝐌𝐢𝐧𝐞 𝐑𝐨𝐥𝐞𝐩𝐥𝐚𝐲", 0xFFD700, True, False, False),
    ("vice_gov", "🎖️・𝐕𝐢𝐜𝐞 𝐆𝐨𝐯𝐞𝐫𝐧𝐚𝐭𝐨𝐫𝐞", 0xFBC02D, True, False, False),
    ("giudice", "⚖️・𝐆𝐢𝐮𝐝𝐢𝐜𝐞 𝐒𝐮𝐩𝐫𝐞𝐦𝐨", 0xFFE082, True, False, False),
    ("procuratore", "📜・𝐏𝐫𝐨𝐜𝐮𝐫𝐚𝐭𝐨𝐫𝐞 𝐃𝐢𝐬𝐭𝐫𝐞𝐭𝐭𝐮𝐚𝐥𝐞", 0xFFF59D, False, False, False),

    ("sep_pd", "⫷・═══ 𝐌𝐑𝐏𝐃 - 𝐏𝐎𝐋𝐈𝐂𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓 ═══・⫸", 0x2B2D31, True, False, False),
    ("chief_mrpd", "⭐・𝐂𝐡𝐢𝐞𝐟 𝐎𝐟 𝐏𝐨𝐥𝐢𝐜𝐞 (𝐌𝐑𝐏𝐃)", 0x0D47A1, True, False, False),
    ("deputy_chief_mrpd", "🌟・𝐃𝐞𝐩𝐮𝐭𝐲 𝐂𝐡𝐢𝐞𝐟 𝐌𝐑𝐏𝐃", 0x1565C0, True, False, False),
    ("captain_mrpd", "🎖️・𝐂𝐚𝐩𝐭𝐚𝐢𝐧 𝐌𝐑𝐏𝐃", 0x1976D2, False, False, False),
    ("lieutenant_mrpd", "🎖️・𝐋𝐢𝐞𝐮𝐭𝐞𝐧𝐚𝐧𝐭 𝐌𝐑𝐏𝐃", 0x1E88E5, False, False, False),
    ("sergeant_mrpd", "🛡️・𝐒𝐞𝐫𝐠𝐞𝐚𝐧𝐭 𝐌𝐑𝐏𝐃", 0x2196F3, False, False, False),
    ("swat_mrpd", "🔫・𝐒.𝐖.𝐀.𝐓. 𝐎𝐩𝐞𝐫𝐚𝐭𝐨𝐫", 0x263238, False, False, False),
    ("senior_mrpd", "🚓・𝐒𝐞𝐧𝐢𝐨𝐫 𝐋𝐞𝐚𝐝 𝐎𝐟𝐟𝐢𝐜𝐞𝐫", 0x42A5F5, False, False, False),
    ("officer2_mrpd", "🚓・𝐎𝐟𝐟𝐢𝐜𝐞𝐫 𝐈𝐈", 0x64B5F6, False, False, False),
    ("officer1_mrpd", "🚓・𝐎𝐟𝐟𝐢𝐜𝐞𝐫 𝐈", 0x90CAF9, False, False, False),
    ("recruit_mrpd", "🎓・𝐑𝐞𝐜𝐫𝐮𝐢𝐭 / 𝐂𝐚𝐝𝐞𝐭 𝐌𝐑𝐏𝐃", 0xBBDEFB, False, False, False),
    ("mrpd", "🚔・𝐌𝐞𝐦𝐛𝐫𝐨 𝐌𝐑𝐏𝐃", 0x42A5F5, True, False, False),

    ("sep_fib", "⫷・═══ 𝐃𝐄𝐓𝐄𝐂𝐓𝐈𝐕𝐄 𝐁𝐔𝐑𝐄𝐀𝐔 / 𝐅𝐈𝐁 ═══・⫸", 0x2B2D31, True, False, False),
    ("dir_fib", "🕵️・𝐃𝐢𝐫𝐞𝐭𝐭𝐨𝐫𝐞 𝐅𝐈𝐁 / 𝐃𝐞𝐭𝐞𝐜𝐭𝐢𝐯𝐞", 0x263238, True, False, False),
    ("senior_fib", "🕶️・𝐒𝐞𝐧𝐢𝐨𝐫 𝐒𝐩𝐞𝐜𝐢𝐚𝐥 𝐀𝐠𝐞𝐧𝐭", 0x37474F, False, False, False),
    ("fib", "🔍・𝐀𝐠𝐞𝐧𝐭𝐞 𝐃𝐞𝐭𝐞𝐜𝐭𝐢𝐯𝐞 / 𝐅𝐈𝐁", 0x455A64, True, False, False),

    ("sep_ems", "⫷・═══ 𝐌𝐑𝐄𝐌𝐒 - 𝐌𝐄𝐃𝐈𝐂𝐀𝐋 𝐃𝐄𝐏𝐓 ═══・⫸", 0x2B2D31, True, False, False),
    ("chief_mrems", "🩺・𝐂𝐡𝐢𝐞𝐟 𝐎𝐟 𝐌𝐞𝐝𝐢𝐜𝐢𝐧𝐞 (𝐌𝐑𝐄𝐌𝐒)", 0xB71C1C, True, False, False),
    ("doctor_mrems", "🏥・𝐄𝐑 𝐃𝐨𝐜𝐭𝐨𝐫 / 𝐒𝐮𝐫𝐠𝐞𝐨𝐧", 0xC62828, False, False, False),
    ("senior_paramedic", "🚑・𝐒𝐞𝐧𝐢𝐨𝐫 𝐏𝐚𝐫𝐚𝐦𝐞𝐝𝐢𝐜", 0xD32F2F, False, False, False),
    ("paramedic_mrems", "🚑・𝐏𝐚𝐫𝐚𝐦𝐞𝐝𝐢𝐜", 0xE53935, False, False, False),
    ("emt_basic", "🩹・𝐄𝐌𝐓 𝐁𝐚𝐬𝐢𝐜", 0xEF5350, False, False, False),
    ("emt_trainee", "🎓・𝐄𝐌𝐓 𝐓𝐫𝐚𝐢𝐧𝐞𝐞", 0xE57373, False, False, False),
    ("mrems", "🚑・𝐌𝐞𝐦𝐛𝐫𝐨 𝐌𝐑𝐄𝐌𝐒 𝟗𝟏𝟏", 0xEF5350, True, False, False),

    ("sep_fd", "⫷・═══ 𝐌𝐑𝐅𝐃 - 𝐅𝐈𝐑𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓 ═══・⫸", 0x2B2D31, True, False, False),
    ("chief_mrfd", "🚒・𝐅𝐢𝐫𝐞 𝐂𝐡𝐢𝐞𝐟 (𝐌𝐑𝐅𝐃)", 0xBF360C, True, False, False),
    ("captain_mrfd", "🔥・𝐂𝐚𝐩𝐭𝐚𝐢𝐧 𝐌𝐑𝐅𝐃", 0xD84315, False, False, False),
    ("lieutenant_mrfd", "🔥・𝐋𝐢𝐞𝐮𝐭𝐞𝐧𝐚𝐧𝐭 𝐌𝐑𝐅𝐃", 0xE64A19, False, False, False),
    ("engineer_mrfd", "🧯・𝐄𝐧𝐠𝐢𝐧𝐞𝐞𝐫 / 𝐃𝐫𝐢𝐯𝐞𝐫", 0xF4511E, False, False, False),
    ("firefighter_mrfd", "🪓・𝐅𝐢𝐫𝐞𝐟𝐢𝐠𝐡𝐭𝐞𝐫", 0xFF5722, False, False, False),
    ("prob_mrfd", "🎓・𝐏𝐫𝐨𝐛𝐚𝐭𝐢𝐨𝐧𝐚𝐫𝐲 𝐅𝐢𝐫𝐞𝐟𝐢𝐠𝐡𝐭𝐞𝐫", 0xFF8A65, False, False, False),
    ("mrfd", "🧯・𝐌𝐞𝐦𝐛𝐫𝐨 𝐌𝐑𝐅𝐃", 0xFF7043, True, False, False),

    ("sep_aziende", "⫷・════ 𝐀𝐙𝐈𝐄𝐍𝐃𝐄 & 𝐀𝐓𝐓𝐈𝐕𝐈𝐓𝐀̀ ════・⫸", 0x2B2D31, True, False, False),
    ("dir_motors", "🏎️・𝐃𝐢𝐫𝐞𝐭𝐭𝐨𝐫𝐞 𝐌𝐑 𝐌𝐨𝐭𝐨𝐫𝐬", 0xE65100, True, False, False),
    ("motors", "🔧・𝐌𝐞𝐜𝐜𝐚𝐧𝐢𝐜𝐨 / 𝐌𝐑 𝐌𝐨𝐭𝐨𝐫𝐬", 0xFFA726, True, False, False),
    ("dir_burger", "🍔・𝐃𝐢𝐫𝐞𝐭𝐭𝐨𝐫𝐞 𝐁𝐮𝐫𝐠𝐞𝐫 𝐒𝐡𝐨𝐭", 0xF9A825, True, False, False),
    ("burger", "🍟・𝐃𝐢𝐩𝐞𝐧𝐝𝐞𝐧𝐭𝐞 𝐁𝐮𝐫𝐠𝐞𝐫 𝐒𝐡𝐨𝐭", 0xFFF176, True, False, False),
    ("dir_club", "🌴・𝐃𝐢𝐫𝐞𝐭𝐭𝐨𝐫𝐞 𝐄𝐜𝐥𝐢𝐩𝐬𝐞 𝐂𝐥𝐮𝐛", 0x8E24AA, True, False, False),
    ("club", "🥂・𝐒𝐭𝐚𝐟𝐟 𝐄𝐜𝐥𝐢𝐩𝐬𝐞 𝐂𝐥𝐮𝐛", 0xCE93D8, True, False, False),
    ("taxi", "🚕・𝐓𝐚𝐬𝐬𝐢𝐬𝐭𝐚 𝐘𝐞𝐥𝐥𝐨𝐰 𝐂𝐚𝐛", 0xFDD835, True, False, False),

    ("sep_civ", "⫷・════ 𝐂𝐈𝐓𝐓𝐀𝐃𝐈𝐍𝐀𝐍𝐙𝐀 & 𝐒𝐓𝐀𝐓𝐎 ════・⫸", 0x2B2D31, True, False, False),
    ("vip", "💎・𝐒𝐮𝐩𝐩𝐨𝐫𝐭𝐞𝐫 𝐕𝐈𝐏", 0xE040FB, True, False, False),
    ("cittadino", "🪪・𝐂𝐢𝐭𝐭𝐚𝐝𝐢𝐧𝐨 𝐌𝐢𝐧𝐞 𝐑𝐨𝐥𝐞𝐩𝐥𝐚𝐲", 0x00E5FF, True, False, False),
    ("attesa_wl", "⏳・𝐀𝐭𝐭𝐞𝐬𝐚 𝐖𝐡𝐢𝐭𝐞𝐋𝐢𝐬𝐭", 0xFFB300, False, False, False),
    ("no_wl", "❌・𝐍𝐨 𝐖𝐡𝐢𝐭𝐞𝐋𝐢𝐬𝐭", 0xE53935, False, False, False),
    ("verificato", "✅・𝐕𝐞𝐫𝐢𝐟𝐢𝐜𝐚𝐭𝐨", 0x43A047, False, False, False),
    ("non_verificato", "🔒・𝐍𝐨𝐧 𝐕𝐞𝐫𝐢𝐟𝐢𝐜𝐚𝐭𝐨", 0x757575, False, False, False),
]

# =====================================================================
# 2. CONTENUTI TESTUALI COMPLETI (GUIDE, REGOLAMENTI, CODICI E BANDI)
# =====================================================================
MESSAGGI_CANALI = {
    "benvenuto": """# 〘 🇺🇸 𝐁𝐄𝐍𝐕𝐄𝐍𝐔𝐓𝐈 𝐒𝐔 𝐌𝐈𝐍𝐄 𝐑𝐎𝐋𝐄𝐏𝐋𝐀𝐘 🇺🇸 〙

Benvenuti nella nostra metropoli Roleplay in stile americano!
Il server è **100% Cross-Platform**: puoi giocare insieme ai tuoi amici da **PC Java**, **PS4 / PS5**, **Xbox**, **Nintendo Switch**, **iOS** e **Android** con vestiti, divise graduate e accessori 3D reali.

---

### 🚀 𝐈 𝐏𝐑𝐈𝐌𝐈 𝟒 𝐏𝐀𝐒𝐒𝐈 𝐏𝐄𝐑 𝐈𝐍𝐈𝐙𝐈𝐀𝐑𝐄

1️⃣ **Completa la Verifica** nel canale `〔✅〕・ᴠᴇʀɪꜰɪᴄᴀ` per sbloccare l'accesso al server Discord.
2️⃣ **Leggi tutti i Regolamenti Ufficiali** nella categoria `📜 REGOLAMENTI UFFICIALI`.
3️⃣ **Collega il tuo Account Minecraft** seguendo la guida in `〔🎮〕・ᴄᴏᴍᴇ-ᴇɴᴛʀᴀʀᴇ-ᴘꜱ4-ᴘꜱ5-ᴘᴄ` e scrivendo `!collega <codice>` nel canale `〔🔐〕・ᴄᴏʟʟᴇɢᴀ-ᴀᴄᴄᴏᴜɴᴛ`.
4️⃣ **Scegli la tua Carriera** candidandoti nei canali della categoria `📋 BANDI DI ARRUOLAMENTO` oppure avviando la tua attività commerciale in città!

---

*Buona permanenza e buon Roleplay a tutti i cittadini!* 🚓🚑🚒""",

    "storia": """# 〘 📜 𝐒𝐓𝐎𝐑𝐈𝐀 𝐃𝐄𝐋𝐋𝐀 𝐂𝐈𝐓𝐓𝐀̀ — 𝐌𝐈𝐍𝐄 𝐑𝐎𝐋𝐄𝐏𝐋𝐀𝐘 〙

Affacciata sulla costa meridionale degli Stati Uniti e protetta a nord dalle catene montuose, la città di **Mine Roleplay** nasce come grande polo portuale, finanziario e commerciale.

---

### 🏙️ 𝐋'𝐄𝐐𝐔𝐈𝐋𝐈𝐁𝐑𝐈𝐎 𝐓𝐑𝐀 𝐋𝐄𝐆𝐆𝐄 𝐄 𝐂𝐑𝐈𝐌𝐈𝐍𝐄
Negli ultimi anni, la crescita economica ha attirato investitori, imprenditori e nuovi cittadini in cerca di fortuna, ma ha anche alimentato la nascita di organizzazioni criminali pronte a contendersi il controllo dei quartieri, del porto e dei traffici notturni.

* **Lo Stato e le Istituzioni:** Il **Governo**, il **Tribunale**, il **Mine Roleplay Police Department (MRPD)**, il **Federal Investigation Bureau (FIB)**, il dipartimento medico **MREMS 911** e i vigili del fuoco **MRFD** lavorano ogni giorno per garantire ordine, giustizia e soccorso.
* **Il Settore Privato:** Officine come **MR Motors**, locali come l'**Eclipse Club**, catene come **Burger Shot** e la compagnia **Yellow Cab** rappresentano il cuore pulsante dell'economia cittadina.

*Ogni tua scelta scriverà il prossimo capitolo della città.*""",

    "come_entrare": """# 〘 🎮 𝐆𝐔𝐈𝐃𝐀 𝐀𝐋𝐋'𝐀𝐂𝐂𝐄𝐒𝐒𝐎 — 𝐏𝐒𝟒 / 𝐏𝐒𝟓 / 𝐏𝐂 / 𝐌𝐎𝐁𝐈𝐋𝐄 〙

Segui attentamente le istruzioni per la tua piattaforma. **Ricorda:** prima di entrare in game devi avere il ruolo **Verificato** su Discord!

---

### 💻 𝟏. 𝐏𝐂 (𝐌𝐢𝐧𝐞𝐜𝐫𝐚𝐟𝐭 𝐉𝐚𝐯𝐚 𝐄𝐝𝐢𝐭𝐢𝐨𝐧 𝟏.𝟐𝟏.𝐱 / 𝟐𝟔.𝟑)
1. Avvia **Minecraft Java Edition** e vai su **Multigiocatore** ➔ **Aggiungi Server**.
2. Compila i campi:
   * **Nome Server:** `Mine Roleplay USA`
   * **Indirizzo Server (IP):** `INSERISCI_IP_JAVA`
3. Imposta **Pacchetti di risorse del server: Attivati** *(obbligatorio per vedere divise, cappelli, occhiali, maschere e zaini 3D)*.

---

### 🎮 𝟐. 𝐏𝐒𝟒 / 𝐏𝐒𝟓 / 𝐗𝐁𝐎𝐗 / 𝐍𝐈𝐍𝐓𝐄𝐍𝐃𝐎 𝐒𝐖𝐈𝐓𝐂𝐇
1. Scarica sul tuo smartphone l'app gratuita **BedrockTogether** (App Store / Google Play).
2. Assicurati che **telefono e console siano collegati allo stesso Wi-Fi**.
3. Apri **BedrockTogether** e inserisci:
   * **IP:** `INSERISCI_IP_BEDROCK`
   * **Porta:** `INSERISCI_PORTA_BEDROCK`
4. Premi **Watch Ad & Run** e lascia l'app aperta sullo schermo del telefono.
5. Sulla console apri Minecraft ➔ **Gioca** ➔ scheda **Amici** ➔ entra su **BedrockTogether**.

---

### 📱 𝟑. 𝐒𝐌𝐀𝐑𝐓𝐏𝐇𝐎𝐍𝐄 (𝐢𝐎𝐒 / 𝐀𝐧𝐝𝐫𝐨𝐢𝐝)
1. Apri **Minecraft Bedrock Edition** ➔ **Gioca** ➔ scheda **Server** ➔ **Aggiungi Server**.
2. Inserisci:
   * **Nome:** `Mine Roleplay USA`
   * **Indirizzo:** `INSERISCI_IP_BEDROCK`
   * **Porta:** `INSERISCI_PORTA_BEDROCK`

---

### 🔐 𝟒. 𝐒𝐁𝐋𝐎𝐂𝐂𝐎 𝐀𝐂𝐂𝐎𝐔𝐍𝐓 𝐎𝐁𝐁𝐋𝐈𝐆𝐀𝐓𝐎𝐑𝐈𝐎 (`!collega`)
Appena entrerai nel server verrai bloccato allo spawn con un **Codice di Sicurezza** personale:
1. Vai nel canale `〔🔐〕・ᴄᴏʟʟᴇɢᴀ-ᴀᴄᴄᴏᴜɴᴛ` qui su Discord.
2. Scrivi il comando:
   > `!collega TUO_CODICE`
3. Torna su Minecraft: verrai sbloccato all'istante, il tuo nickname sarà protetto dal sistema Anti-Clone 1:1 e potrai scegliere subito uno dei **10 Completi Civili Preimpostati**!""",

    "mappa_gps": """# 〘 🗺️ 𝐌𝐀𝐏𝐏𝐀 & 𝐏𝐔𝐍𝐓𝐈 𝐆𝐏𝐒 𝐏𝐑𝐈𝐍𝐂𝐈𝐏𝐀𝐋𝐈 〙

La città è chiusa naturalmente tra il **lungomare/porto a sud** e le **montagne a nord**. Usa questi punti di riferimento per orientarti:

---

### 🏛️ 𝐄𝐃𝐈𝐅𝐈𝐂𝐈 𝐈𝐒𝐓𝐈𝐓𝐔𝐙𝐈𝐎𝐍𝐀𝐋𝐈 & 𝐒𝐎𝐂𝐂𝐎𝐑𝐒𝐎
* **Centrale MRPD (Police Department):** Centro città, accanto a Piazza Principale *(Locker `/locker pd`, Celle, Sala Interrogatori, Elisuperficie)*.
* **Ospedale Centrale MREMS 911:** Zona Est *(Locker `/locker ems`, Pronto Soccorso, Sale Operatorie, Elisuperficie)*.
* **Caserma MRFD (Fire Department):** Viale Sud-Est *(Locker `/locker fd`, Autorimessa Autopompe)*.
* **Municipio & Tribunale:** Piazza Centrale *(Anagrafe per Carta d'Identità e Patente, Aula Udienze)*.

---

### 🏪 𝐀𝐓𝐓𝐈𝐕𝐈𝐓𝐀̀, 𝐋𝐀𝐕𝐎𝐑𝐈 & 𝐒𝐄𝐑𝐕𝐈𝐙𝐈
* **Banca Centrale:** Distretto Finanziario *(Depositi, Prelievi, Caveau)*.
* **Concessionario MR Motors:** Viale Principale *(Acquisto Auto, Moto, Elicotteri e Officina Tuning)*.
* **Boutique Style USA (`/vestiti`):** Via Commerciale *(Oltre 75 capi d'abbigliamento e accessori 3D)*.
* **Ufficio Collocamento:** Accanto al Municipio *(Lavori base: Tassista, Meccanico, Corriere)*.
* **Burger Shot & Eclipse Club:** Zona Lungomare / Intrattenimento.""",

    "reg_server": """# 〘 📕 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐆𝐄𝐍𝐄𝐑𝐀𝐋𝐄 𝐑𝐎𝐋𝐄𝐏𝐋𝐀𝐘 〙

L'obiettivo di **Mine Roleplay** è garantire una simulazione realistica e immersiva. La mancata lettura del regolamento non costituisce mai una giustificazione.

---

### 🔹 𝟏. 𝐑𝐄𝐆𝐎𝐋𝐄 𝐅𝐎𝐍𝐃𝐀𝐌𝐄𝐍𝐓𝐀𝐋𝐈 (𝐈𝐍-𝐂𝐇𝐀𝐑𝐀𝐂𝐓𝐄𝐑)
* **Nome e Cognome RP:** È obbligatorio creare un personaggio con Nome e Cognome realistici in stile USA (es. *Marcus Vance*, *Sarah Connor*). Vietati nomi famosi, troll o sigle.
* **Metagame (MG):** Vietato usare in gioco informazioni apprese su Discord, live, chat OOC o da altri canali esterni.
* **Powergame (PG):** Vietato compiere azioni fisicamente impossibili nella realtà (es. guidare su montagne verticali con un'auto sportiva, parlare mentre si è a terra feriti gravi, non simulare il dolore dopo un incidente).
* **Random Deathmatch (RDM):** Vietato uccidere o ferire altri cittadini senza una motivazione Roleplay valida, chiara e sviluppata prima dello scontro.
* **Vehicle Deathmatch (VDM):** Vietato investire volontariamente giocatori con auto, moto o elicotteri.
* **No Fear (Valorizzazione della Vita):** Devi sempre simulare paura per la tua incolumità. Se hai un'arma puntata da distanza ravvicinata, devi alzare le mani e collaborare.
* **Combat Log:** Severamente vietato uscire dal server o chiudere il gioco durante un'azione RP, un inseguimento, un arresto o mentre si è in attesa dei soccorsi MREMS.
* **Revenge Kill (RK):** Se vieni abbattuto e rianimato dai medici, dimentichi completamente gli eventi che hanno causato il tuo ferimento e non puoi tornare sul posto per 30 minuti.

---

### 🔹 𝟐. 𝐒𝐀𝐅𝐄 𝐙𝐎𝐍𝐄 (𝐙𝐎𝐍𝐄 𝐏𝐑𝐎𝐓𝐄𝐓𝐓𝐄)
All'interno di **Ospedale, Centrale MRPD, Caserma MRFD, Municipio, Banca (fuori da rapina autorizzata), Concessionario e Spawn** è severamente vietato:
* Avviare sparatorie, risse o accoltellamenti;
* Effettuare rapine, borseggi o sequestri di persona;
* Rubare veicoli parcheggiati davanti all'ingresso.""",

    "reg_discord": """# 〘 📘 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐂𝐎𝐌𝐌𝐔𝐍𝐈𝐓𝐘 𝐃𝐈𝐒𝐂𝐎𝐑𝐃 〙

Per mantenere un ambiente sano, ordinato e rispettoso per tutta la community, segui queste regole su Discord:

---

### 📌 𝐍𝐎𝐑𝐌𝐄 𝐃𝐈 𝐂𝐎𝐌𝐏𝐎𝐑𝐓𝐀𝐌𝐄𝐍𝐓𝐎
1. **Rispetto Reciproco:** Vietati insulti, bestemmie, razzismo, sessismo, minacce reali o qualsiasi forma di discriminazione.
2. **Divieto di Spam e Self-Promotion:** Vietato inviare link di altri server Discord, IP di altri server Minecraft o pubblicità non autorizzata (anche nei DM ai membri).
3. **Uso Corretto dei Canali:** Rispetta la divisione tra canali **OOC** (fuori dal personaggio) e canali **IC** (in-character, come `yellow-pages`, `mine-roleplay-news` e `dark-web-ic`).
4. **Supporto & Ticket:** Non taggare lo Staff nei canali pubblici. Per assistenza apri un ticket nella sezione dedicata e attendi con pazienza.
5. **Account Unico:** Ogni utente Discord può collegare **1 solo account Minecraft** tramite `!collega`. L'uso di account secondari per aggirare ban o duplicare soldi comporta il ban permanente.""",

    "reg_fazioni": """# 〘 📗 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐅𝐀𝐙𝐈𝐎𝐍𝐈 𝐒𝐓𝐀𝐓𝐀𝐋𝐈 (𝐌𝐑𝐏𝐃 / 𝐅𝐈𝐁 / 𝐌𝐑𝐄𝐌𝐒 / 𝐌𝐑𝐅𝐃) 〙

Gli operatori statali rappresentano lo Stato e devono mantenere un comportamento esemplare sia in servizio che fuori servizio.

---

### 🏛️ 𝐑𝐄𝐆𝐎𝐋𝐄 𝐃𝐈 𝐒𝐄𝐑𝐕𝐈𝐙𝐈𝐎
* **Obbligo di Divisa & Radio:** Quando sei On-Duty devi indossare esclusivamente la divisa del tuo grado tramite il Locker (`/locker pd`, `/locker ems`, `/locker fd`) ed essere presente nei canali vocali operativi.
* **Divieto di Corruzione non Autorizzata:** È severamente vietato vendere, regalare o passare armi d'ordinanza, divise, distintivi o informazioni riservate ai civili/criminali. Eventuali ruoli da agente corrotto devono essere approvati dalla Direzione tramite ticket.
* **Fine Turno (Off-Duty):** Prima di dedicarti ad attività private o civili, devi obbligatoriamente smontare dal servizio tramite il tasto **Off Duty** nel Locker.
* **Imparzialità MREMS & MRFD:** Medici e Vigili del Fuoco sono neutrali: devono soccorrere chiunque senza favoritismi, dando priorità ai feriti più gravi e agli operatori statali in pericolo.""",

    "reg_crimine": """# 〘 📙 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐂𝐑𝐈𝐌𝐈𝐍𝐄 & 𝐎𝐑𝐆𝐀𝐍𝐈𝐙𝐙𝐀𝐙𝐈𝐎𝐍𝐈 〙

Le attività illegali arricchiscono il Roleplay solo se svolte con logica, pianificazione e rispetto dei limiti numerici.

---

### 🕶️ 𝐑𝐄𝐆𝐎𝐋𝐄 𝐀𝐙𝐈𝐎𝐍𝐈 𝐈𝐋𝐋𝐄𝐆𝐀𝐋𝐈
* **Maschera & Riconoscimento:** Se indossi un **Passamontagna, una Maschera o una Bandana** (acquistabili al Mercato Nero o Boutique), i giocatori non possono riconoscerti dal volto, ma possono comunque riconoscere la voce se non la camuffi in RP.
* **Numero Minimo MRPD per Rapine:**
  * **Furto Veicolo / Borseggio:** Minimo **2 Agenti MRPD** in servizio.
  * **Rapina Minimarket / Gioielleria:** Minimo **4 Agenti MRPD** in servizio.
  * **Rapina Banca Centrale:** Minimo **6 Agenti MRPD** in servizio + autorizzazione Staff/Bando azione.
* **Ostaggi:** È vietato usare amici o complici finti come ostaggi durante una rapina. L'ostaggio deve essere un vero cittadino catturato in azione RP.
* **Limiti Membri Azione:** Nelle azioni criminali esterne è consentito un massimo di **6 criminali** contemporaneamente per evitare squilibri irreali.""",

    "codice_penale": """# 〘 ⚖️ 𝐂𝐎𝐃𝐈𝐂𝐄 𝐏𝐄𝐍𝐀𝐋𝐄 𝐌𝐑𝐏𝐃 (𝐒𝐈𝐍𝐓𝐄𝐒𝐈 𝐑𝐄𝐀𝐓𝐈) 〙

Tabella ufficiale delle sanzioni applicate dal **Police Department** e dal **Tribunale**:

---

### 🔹 𝟏. 𝐑𝐄𝐀𝐓𝐈 𝐌𝐈𝐍𝐎𝐑𝐈 (𝐌𝐮𝐥𝐭𝐚 + 𝐅𝐞𝐫𝐦𝐨 𝐛𝐫𝐞𝐯𝐞)
* **Oltraggio a Pubblico Ufficiale:** Multa `$500`
* **Rifiuto di fornire i documenti:** Multa `$600` + fermo per identificazione
* **Disturbo della quiete pubblica:** Multa `$400`
* **Possesso di grimaldello o attrezzi da scasso:** Multa `$800` + sequestro

---

### 🔹 𝟐. 𝐑𝐄𝐀𝐓𝐈 𝐌𝐄𝐃𝐈 (𝐌𝐮𝐥𝐭𝐚 + 𝐀𝐫𝐫𝐞𝐬𝐭𝐨)
* **Furto d'auto / Ricettazione:** Multa `$1.500` + 10 min carcere
* **Fuga all'alt della Polizia:** Multa `$2.000` + 15 min carcere + ritiro patente
* **Possesso d'arma bianca / da fuoco senza porto d'armi:** Multa `$3.000` + 20 min carcere + sequestro
* **Rapina a mano armata (Negozio):** Multa `$4.000` + 25 min carcere

---

### 🔹 𝟑. 𝐑𝐄𝐀𝐓𝐈 𝐆𝐑𝐀𝐕𝐈 (𝐏𝐫𝐨𝐜𝐞𝐬𝐬𝐨 & 𝐂𝐚𝐫𝐜𝐞𝐫𝐞 𝐝𝐢 𝐌𝐚𝐬𝐬𝐢𝐦𝐚 𝐒𝐢𝐜𝐮𝐫𝐞𝐳𝐳𝐚)
* **Sequestro di persona / Presa d'ostaggi:** Multa `$6.000` + 35 min carcere
* **Rapina alla Banca Centrale:** Multa `$10.000` + 45 min carcere
* **Tentato omicidio / Aggressione a Pubblico Ufficiale:** Multa `$8.000` + 40 min carcere
* **Omicidio (con eventuale richiesta PermaDeath):** Processo in Tribunale + ergastolo / pena capitale RP.""",

    "codice_strada": """# 〘 🚗 𝐂𝐎𝐃𝐈𝐂𝐄 𝐃𝐄𝐋𝐋𝐀 𝐒𝐓𝐑𝐀𝐃𝐀 & 𝐃𝐌𝐕 〙

Tutti i conducenti devono conseguire la **Patente di Guida** presso l'Anagrafe / Municipio prima di mettersi alla guida.

---

### 🚦 𝐋𝐈𝐌𝐈𝐓𝐈 𝐃𝐈 𝐕𝐄𝐋𝐎𝐂𝐈𝐓𝐀̀ & 𝐒𝐀𝐍𝐙𝐈𝐎𝐍𝐈
* **Centro Urbano / Aree Residenziali:** Max **50 km/h**
* **Strade Extraurbane / Lungomare:** Max **90 km/h**
* **Autostrada / Perimetrale:** Max **130 km/h**

### 📋 𝐈𝐍𝐅𝐑𝐀𝐙𝐈𝐎𝐍𝐈 𝐂𝐎𝐌𝐔𝐍𝐈
* **Guida senza patente:** Multa `$1.200` + sequestro amministrativo del veicolo
* **Eccesso di velocità grave:** Multa `$700` + decurtazione punti patente
* **Passaggio con semaforo rosso / Guida contromano:** Multa `$500`
* **Sosta vietata davanti a Ospedale / Centrale MRPD:** Multa `$350` + rimozione forzata
* **Volo in elicottero a bassa quota non autorizzato sul centro città:** Multa `$2.500` + sospensione brevetto di volo""",

    "porto_armi": """# 〘 🔫 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐏𝐎𝐑𝐓𝐎 𝐃'𝐀𝐑𝐌𝐈 𝐂𝐈𝐕𝐈𝐋𝐄 〙

Negli Stati Uniti il possesso legale di un'arma da difesa personale è regolamentato da severi controlli medici e giudiziari.

---

### 📋 𝐑𝐄𝐐𝐔𝐈𝐒𝐈𝐓𝐈 𝐏𝐄𝐑 𝐈𝐋 𝐑𝐈𝐋𝐀𝐒𝐂𝐈𝐎
1. **Fedina Penale Pulita:** Nessun precedente penale grave registrato nel database **MRPD**.
2. **Certificato Medico Psico-Attitudinale:** Rilasciato da un medico **MREMS** dopo visita in ospedale (canale `〔💊〕・ᴄᴇʀᴛɪꜰɪᴄᴀᴛɪ-ᴘᴏʀᴛᴏ-ᴅᴀʀᴍɪ`).
3. **Tassa di Concessione:** Versamento di `$2.500` presso la Centrale MRPD / Municipio.

*Nota: Il Porto d'Armi consente esclusivamente il porto occulto di una pistola di piccolo calibro per difesa personale. Fucili d'assalto, mitra e armi pesanti sono sempre illegali per i civili.*""",

    "immobili_aziende": """# 〘 🏠 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐈𝐌𝐌𝐎𝐁𝐈𝐋𝐈 & 𝐀𝐙𝐈𝐄𝐍𝐃𝐄 𝐏𝐑𝐈𝐕𝐀𝐓𝐄 〙

Ogni cittadino può acquistare appartamenti, ville o richiedere l'apertura di un'attività commerciale.

---

### 🏢 𝐆𝐄𝐒𝐓𝐈𝐎𝐍𝐄 𝐀𝐙𝐈𝐄𝐍𝐃𝐄
* **Apertura Attività:** Per proporre una nuova azienda (officina, locale, concessionario, agenzia sicurezza), apri un ticket in `〔🏢〕・ᴛɪᴄᴋᴇᴛ-ᴀᴘᴇʀᴛᴜʀᴀ-ᴀᴢɪᴇɴᴅᴀ` presentando il tuo Business Plan.
* **Attività Minima:** Il Direttore di un'azienda deve garantire l'apertura del locale almeno **3 volte a settimana** e assumere personale regolarmente registrato.
* **Tasse & Stipendi:** Gli stipendi dei dipendenti devono essere pagati regolarmente tramite bonifico bancario.""",

    "bando_staff": """# 〘 🛡️ 𝐁𝐀𝐍𝐃𝐎 𝐒𝐓𝐀𝐅𝐅 — 𝐌𝐈𝐍𝐄 𝐑𝐎𝐋𝐄𝐏𝐋𝐀𝐘 〙

Vuoi contribuire alla crescita della community come **Helper / Moderator / Whitelister**?
Copia il modulo qui sotto e invialo aprendo un ticket in `〔🎫〕・ᴛɪᴄᴋᴇᴛ-ɢᴇɴᴇʀᴀʟᴇ` con oggetto **Candidatura Staff**:

---

### 📋 𝐌𝐎𝐃𝐔𝐋𝐎 𝐂𝐀𝐍𝐃𝐈𝐃𝐀𝐓𝐔𝐑𝐀 𝐒𝐓𝐀𝐅𝐅
```text
• Nome e Nickname Discord:
• Nickname Minecraft (Java o Bedrock/PS4/PS5):
• Età reale:
• Ruolo per cui ti candidi (Helper / Moderator / Whitelister):
• Hai già avuto esperienze come Staff su server RP? Se sì, quali?
• Quante ore al giorno puoi dedicare al server e ai ticket?
• Come ti comporteresti davanti a un giocatore che fa RDM o Combat Log?
• Perché dovremmo scegliere te nel team di Mine Roleplay?
```""",

    "bando_mrpd": """# 〘 🚔 𝐁𝐀𝐍𝐃𝐎 𝐃𝐈 𝐀𝐑𝐑𝐔𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 — 𝐌𝐑𝐏𝐃 (𝐏𝐎𝐋𝐈𝐂𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓) 〙

Il **Mine Roleplay Police Department** cerca nuove reclute motivate per proteggere i cittadini e pattugliare le strade!
Compila il modulo qui sotto e invialo in `〔🏛️〕・ᴛɪᴄᴋᴇᴛ-ꜰᴀᴢɪᴏɴᴇ` con oggetto **Bando MRPD**:

---

### 📋 𝐌𝐎𝐃𝐔𝐋𝐎 𝐀𝐑𝐑𝐔𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐌𝐑𝐏𝐃
```text
• Nome e Cognome RP:
• Data di nascita RP (Età minima 21 anni):
• Nickname Minecraft & Piattaforma (PC / PS4 / PS5 / Mobile):
• Possiedi la Patente di Guida e fedina penale pulita? (Sì/No):
• Hai esperienze pregresse nelle forze dell'ordine su server RP?
• Conosci i 10-Codes e le procedure di arresto?
• Disponibilità oraria settimanale:
• Motivazione per cui vuoi entrare nell'Accademia MRPD:
```""",

    "bando_fib": """# 〘 🕵️ 𝐁𝐀𝐍𝐃𝐎 𝐀𝐆𝐄𝐍𝐓𝐈 — 𝐃𝐄𝐓𝐄𝐂𝐓𝐈𝐕𝐄 𝐁𝐔𝐑𝐄𝐀𝐔 / 𝐅𝐈𝐁 〙

Il **Federal Investigation Bureau & Detective Bureau** seleziona investigatori discreti, analitici e preparati per indagini sotto copertura e lotta al crimine organizzato.
Invia il modulo in `〔🏛️〕・ᴛɪᴄᴋᴇᴛ-ꜰᴀᴢɪᴏɴᴇ` con oggetto **Bando FIB**:

---

### 📋 𝐌𝐎𝐃𝐔𝐋𝐎 𝐂𝐀𝐍𝐃𝐈𝐃𝐀𝐓𝐔𝐑𝐀 𝐅𝐈𝐁 / 𝐃𝐄𝐓𝐄𝐂𝐓𝐈𝐕𝐄
```text
• Nome e Cognome RP:
• Grado attuale in MRPD (se già in servizio) o esperienze investigative RP:
• Nickname Minecraft & Discord:
• Capacità di raccolta prove, pedinamenti e stesura fascicoli:
• Perché ritieni di essere idoneo per il Bureau Investigativo?
```""",

    "bando_mrems": """# 〘 🚑 𝐁𝐀𝐍𝐃𝐎 𝐒𝐀𝐍𝐈𝐓𝐀𝐑𝐈𝐎 — 𝐌𝐑𝐄𝐌𝐒 𝟗𝟏𝟏 (𝐎𝐒𝐏𝐄𝐃𝐀𝐋𝐄 & 𝐒𝐎𝐂𝐂𝐎𝐑𝐒𝐎) 〙

Il dipartimento medico **MREMS 911** assume **EMT Trainee, Paramedici e Medici Chirurghi** per garantire assistenza sanitaria 24/7 in città!
Invia il modulo in `〔🏛️〕・ᴛɪᴄᴋᴇᴛ-ꜰᴀᴢɪᴏɴᴇ` con oggetto **Bando MREMS**:

---

### 📋 𝐌𝐎𝐃𝐔𝐋𝐎 𝐀𝐑𝐑𝐔𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐌𝐑𝐄𝐌𝐒 𝟗𝟏𝟏
```text
• Nome e Cognome RP:
• Età RP:
• Nickname Minecraft & Piattaforma (PC / PS4 / PS5 / Mobile):
• Ruolo richiesto (EMT Soccorritore / Infermiere / Medico Chirurgo):
• Hai esperienze come medico/soccorritore in altri server RP?
• Disponibilità oraria settimanale:
• Perché vuoi entrare nel personale sanitario MREMS?
```""",

    "bando_mrfd": """# 〘 🚒 𝐁𝐀𝐍𝐃𝐎 𝐀𝐑𝐑𝐔𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 — 𝐌𝐑𝐅𝐃 (𝐅𝐈𝐑𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓) 〙

Il **Mine Roleplay Fire Department (MRFD)** apre le selezioni per **Probationary Firefighter**! Unisciti alla squadra antincendio e soccorso tecnico urgente.
Invia il modulo in `〔🏛️〕・ᴛɪᴄᴋᴇᴛ-ꜰᴀᴢɪᴏɴᴇ` con oggetto **Bando MRFD**:

---

### 📋 𝐌𝐎𝐃𝐔𝐋𝐎 𝐀𝐑𝐑𝐔𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 𝐌𝐑𝐅𝐃
```text
• Nome e Cognome RP:
• Età RP:
• Nickname Minecraft & Piattaforma (PC / PS4 / PS5 / Mobile):
• Possiedi la Patente di Guida per mezzi pesanti? (Sì/No):
• Esperienze RP precedenti (Fire Dept / Protezione Civile / Altro):
• Disponibilità oraria settimanale:
• Perché vuoi diventare un Vigile del Fuoco MRFD?
```""",

    "bando_gov": """# 〘 🏛️ 𝐁𝐀𝐍𝐃𝐎 𝐆𝐎𝐕𝐄𝐑𝐍𝐎, 𝐌𝐀𝐆𝐈𝐒𝐓𝐑𝐀𝐓𝐔𝐑𝐀 & 𝐀𝐕𝐕𝐎𝐂𝐀𝐓𝐔𝐑𝐀 〙

Sono aperte le candidature per **Giudici, Procuratori Distrettuali, Avvocati Penalisti e Funzionari Municipali**.
Invia il modulo in `〔🏛️〕・ᴛɪᴄᴋᴇᴛ-ꜰᴀᴢɪᴏɴᴇ` con oggetto **Bando Governo/Tribunale**:

---

### 📋 𝐌𝐎𝐃𝐔𝐋𝐎 𝐂𝐀𝐍𝐃𝐈𝐃𝐀𝐓𝐔𝐑𝐀 𝐈𝐒𝐓𝐈𝐓𝐔𝐙𝐈𝐎𝐍𝐀𝐋𝐄
```text
• Nome e Cognome RP:
• Ruolo richiesto (Giudice / Procuratore / Avvocato / Funzionario):
• Conoscenza del Codice Penale e delle procedure processuali RP:
• Fedina penale RP (deve essere completamente pulita):
• Perché vuoi servire le istituzioni di Mine Roleplay?
```""",

    "bando_aziende": """# 〘 🏢 𝐁𝐀𝐍𝐃𝐎 𝐃𝐈𝐏𝐄𝐍𝐃𝐄𝐍𝐓𝐈 & 𝐃𝐈𝐑𝐄𝐓𝐓𝐎𝐑𝐈 𝐀𝐙𝐈𝐄𝐍𝐃𝐄 〙

Cerchi un lavoro stabile e ben retribuito in città? Le aziende **MR Motors (Concessionario & Officina)**, **Burger Shot**, **Eclipse Club** e **Yellow Cab Taxi** assumono personale!
Invia il modulo in `〔🏢〕・ᴛɪᴄᴋᴇᴛ-ᴀᴘᴇʀᴛᴜʀᴀ-ᴀᴢɪᴇɴᴅᴀ` con oggetto **Candidatura Azienda**:

---

### 📋 𝐌𝐎𝐃𝐔𝐋𝐎 𝐀𝐒𝐒𝐔𝐍𝐙𝐈𝐎𝐍𝐄 𝐀𝐙𝐈𝐄𝐍𝐃𝐀𝐋𝐄
```text
• Nome e Cognome RP:
• Azienda scelta (MR Motors / Burger Shot / Eclipse Club / Yellow Cab):
• Posizione richiesta (Dipendente / Meccanico / Tassista / Barman / Direttore):
• Possiedi la Patente di Guida? (Sì/No):
• Disponibilità oraria in città:
• Breve presentazione del tuo personaggio:
```"""
}

# =====================================================================
# 3. STRUTTURA CATEGORIE E CANALI CON PERMESSO SPECIFICO & CONTENUTO
# Formato canale: (tipo, nome, permesso_canale, chiave_messaggio_auto)
# =====================================================================
STRUTTURA_SERVER = [
    ("⫷༺ 📊 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐇𝐄 𝐌𝐈𝐍𝐄 𝐑𝐎𝐋𝐄𝐏𝐋𝐀𝐘 ༻⫸", "stats", [
        ("voice", "〔📊〕・ᴍᴇᴍʙʀɪ-ᴛᴏᴛᴀʟɪ-0", "stats", None),
        ("voice", "〔🛡️〕・ꜱᴛᴀꜰꜰ-ᴛᴏᴛᴀʟɪ-0", "stats", None),
        ("voice", "〔🪪〕・ᴄɪᴛᴛᴀᴅɪɴɪ-0", "stats", None),
        ("voice", "〔🟢〕・ꜱᴇʀᴠᴇʀ-ᴏɴʟɪɴᴇ", "stats", None),
    ]),
    ("⫷༺ ⚔️ 𝐁𝐄𝐍𝐕𝐄𝐍𝐔𝐓𝐎 & 𝐈𝐍𝐅𝐎 ༻⫸", "public_read", [
        ("text", "〔👋〕・ʙᴇɴᴠᴇɴᴜᴛᴏ", "public_read", "benvenuto"),
        ("text", "〔🚪〕・ᴀᴅᴅɪᴏ", "public_read", None),
        ("text", "〔✅〕・ᴠᴇʀɪꜰɪᴄᴀ", "verifica_ch", None),
        ("text", "〔🔐〕・ᴄᴏʟʟᴇɢᴀ-ᴀᴄᴄᴏᴜɴᴛ", "verificato_chat", None),
        ("text", "〔📜〕・ꜱᴛᴏʀɪᴀ-ᴅᴇʟʟᴀ-ᴄɪᴛᴛᴀ̀", "public_read", "storia"),
        ("text", "〔🗺️〕・ᴍᴀᴘᴘᴀ-ᴇ-ᴘᴜɴᴛɪ-ɢᴘꜱ", "public_read", "mappa_gps"),
        ("text", "〔🎮〕・ᴄᴏᴍᴇ-ᴇɴᴛʀᴀʀᴇ-ᴘꜱ4-ᴘꜱ5-ᴘᴄ", "public_read", "come_entrare"),
        ("text", "〔🎧〕・ᴄᴏʟʟᴇɢᴀ-ᴠᴏᴄᴇ-ᴏᴘᴇɴᴀᴜᴅɪᴏ", "public_read", None),
        ("text", "〔💎〕・ᴠɪᴘ-ᴇ-ꜱᴜᴘᴘᴏʀᴛ-ᴘᴀᴄᴋ", "public_read", None),
        ("text", "〔🔗〕・ʟɪɴᴋ-ɪɴᴠɪᴛᴏ", "public_read", None),
        ("text", "〔🟢〕・ꜱᴛᴀᴛᴏ-ꜱᴇʀᴠᴇʀ", "public_read", None),
    ]),
    ("⫷༺ 📜 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐈 𝐔𝐅𝐅𝐈𝐂𝐈𝐀𝐋𝐈 ༻⫸", "public_read", [
        ("text", "〔📕〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ꜱᴇʀᴠᴇʀ", "public_read", "reg_server"),
        ("text", "〔📘〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ᴅɪꜱᴄᴏʀᴅ", "public_read", "reg_discord"),
        ("text", "〔📗〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ꜰᴀᴢɪᴏɴɪ", "public_read", "reg_fazioni"),
        ("text", "〔📙〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ᴄʀɪᴍɪɴᴇ", "public_read", "reg_crimine"),
        ("text", "〔⚖️〕・ᴄᴏᴅɪᴄᴇ-ᴘᴇɴᴀʟᴇ-ᴍʀᴘᴅ", "public_read", "codice_penale"),
        ("text", "〔🚗〕・ᴄᴏᴅɪᴄᴇ-ᴅᴇʟʟᴀ-ꜱᴛʀᴀᴅᴀ-ᴅᴍᴠ", "public_read", "codice_strada"),
        ("text", "〔🔫〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ᴘᴏʀᴛᴏ-ᴅᴀʀᴍɪ", "public_read", "porto_armi"),
        ("text", "〔🏠〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ɪᴍᴍᴏʙɪʟɪ-ᴇ-ᴀᴢɪᴇɴᴅᴇ", "public_read", "immobili_aziende"),
    ]),
    ("⫷༺ 📋 𝐁𝐀𝐍𝐃𝐈 𝐃𝐈 𝐀𝐑𝐑𝐔𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐎 & 𝐌𝐎𝐃𝐔𝐋𝐈 ༻⫸", "verificato_read", [
        ("text", "〔🛡️〕・ʙᴀɴᴅᴏ-ꜱᴛᴀꜰꜰ", "verificato_read", "bando_staff"),
        ("text", "〔🚔〕・ʙᴀɴᴅᴏ-ᴍʀᴘᴅ-ᴘᴏʟɪᴢɪᴀ", "verificato_read", "bando_mrpd"),
        ("text", "〔🕵️〕・ʙᴀɴᴅᴏ-ꜰɪʙ-ᴅᴇᴛᴇᴄᴛɪᴠᴇ", "verificato_read", "bando_fib"),
        ("text", "〔🚑〕・ʙᴀɴᴅᴏ-ᴍʀᴇᴍꜱ-ᴏꜱᴘᴇᴅᴀʟᴇ", "verificato_read", "bando_mrems"),
        ("text", "〔🚒〕・ʙᴀɴᴅᴏ-ᴍʀꜰᴅ-ᴠɪɢɪʟɪ-ꜰᴜᴏᴄᴏ", "verificato_read", "bando_mrfd"),
        ("text", "〔🏛️〕・ʙᴀɴᴅᴏ-ɢᴏᴠᴇʀɴᴏ-ᴇ-ᴛʀɪʙᴜɴᴀʟᴇ", "verificato_read", "bando_gov"),
        ("text", "〔🏢〕・ʙᴀɴᴅᴏ-ᴀᴢɪᴇɴᴅᴇ-ᴄɪᴛᴛᴀᴅɪɴᴇ", "verificato_read", "bando_aziende"),
    ]),
    ("⫷༺ 🛂 𝐀𝐑𝐄𝐀 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓 & 𝐓𝐈𝐂𝐊𝐄𝐓 ༻⫸", "verificato_chat", [
        ("text", "〔📝〕・ꜰᴀɪ-ᴡʜɪᴛᴇʟɪꜱᴛ", "verificato_chat", None),
        ("text", "〔📩〕・ᴇꜱɪᴛᴏ-ᴡʜɪᴛᴇʟɪꜱᴛ", "verificato_read", None),
        ("text", "〔❓〕・ᴅᴏᴍᴀɴᴅᴇ-ᴡʜɪᴛᴇʟɪꜱᴛ", "verificato_chat", None),
        ("text", "〔🎫〕・ᴛɪᴄᴋᴇᴛ-ɢᴇɴᴇʀᴀʟᴇ", "verificato_chat", None),
        ("text", "〔💎〕・ᴛɪᴄᴋᴇᴛ-ᴅᴏɴᴀᴢɪᴏɴɪ", "verificato_chat", None),
        ("text", "〔⭐〕・ᴛɪᴄᴋᴇᴛ-ɢʀᴀᴅᴏ-ᴀʟᴛᴏ", "verificato_chat", None),
        ("text", "〔🏛️〕・ᴛɪᴄᴋᴇᴛ-ꜰᴀᴢɪᴏɴᴇ", "cittadino_chat", None),
        ("text", "〔🏢〕・ᴛɪᴄᴋᴇᴛ-ᴀᴘᴇʀᴛᴜʀᴀ-ᴀᴢɪᴇɴᴅᴀ", "cittadino_chat", None),
        ("text", "〔🐛〕・ꜱᴇɢɴᴀʟᴀ-ʙᴜɢ", "verificato_chat", None),
        ("text", "〔⚖️〕・ʀɪᴄʜɪᴇꜱᴛᴀ-ᴜɴʙᴀɴ", "verificato_chat", None),
        ("text", "〔☠️〕・ʀɪᴄʜɪᴇꜱᴛᴀ-ᴘᴇʀᴍᴀᴅᴇᴀᴛʜ", "cittadino_chat", None),
    ]),
    ("⫷༺ 💬 𝐂𝐎𝐌𝐌𝐔𝐍𝐈𝐓𝐘 𝐎𝐎𝐂 & 𝐌𝐄𝐃𝐈𝐀 ༻⫸", "verificato_chat", [
        ("text", "〔📢〕・ᴀɴɴᴜɴᴄɪ-ꜱᴇʀᴠᴇʀ", "verificato_read", None),
        ("text", "〔💬〕・ᴄʜᴀᴛ-ᴏᴏᴄ", "verificato_chat", None),
        ("text", "〔💡〕・ꜱᴜɢɢᴇʀɪᴍᴇɴᴛɪ-ꜱᴇʀᴠᴇʀ", "verificato_chat", None),
        ("text", "〔📸〕・ᴍᴇᴅɪᴀ-ᴄʟɪᴘ-ʀᴘ", "verificato_chat", None),
        ("text", "〔🎥〕・ᴄʟɪᴘ-ᴇ-ᴛɪᴋᴛᴏᴋ", "verificato_chat", None),
        ("text", "〔🎁〕・ɢɪᴠᴇᴀᴡᴀʏ-ᴇ-ᴇᴠᴇɴᴛɪ", "verificato_read", None),
        ("text", "〔🤝〕・ᴘᴀʀᴛɴᴇʀꜱʜɪᴘ", "verificato_read", None),
        ("text", "〔🤖〕・ᴄᴏᴍᴀɴᴅɪ-ʙᴏᴛ", "verificato_chat", None),
    ]),
    ("⫷༺ 🌆 𝐀𝐑𝐄𝐀 𝐈𝐍-𝐂𝐇𝐀𝐑𝐀𝐂𝐓𝐄𝐑 (𝐈𝐂) ༻⫸", "cittadino_chat", [
        ("text", "〔📱〕・ʏᴇʟʟᴏᴡ-ᴘᴀɢᴇꜱ-ᴀɴɴᴜɴᴄɪ", "cittadino_chat", None),
        ("text", "〔📰〕・ᴍɪɴᴇ-ʀᴏʟᴇᴘʟᴀʏ-ɴᴇᴡꜱ", "cittadino_read", None),
        ("text", "〔🏛️〕・ᴄᴏᴍᴜɴɪᴄᴀᴛɪ-ɢᴏᴠᴇʀɴᴏ", "gov_write", None),
        ("text", "〔⚖️〕・ᴛʀɪʙᴜɴᴀʟᴇ-ᴇ-ꜱᴇɴᴛᴇɴᴢᴇ", "giudice_write", None),
        ("text", "〔🚗〕・ᴀᴜᴛᴏꜱᴀʟᴏɴᴇ-ᴜꜱᴀᴛᴏ", "cittadino_chat", None),
        ("text", "〔🏠〕・ᴀɢᴇɴᴢɪᴀ-ɪᴍᴍᴏʙɪʟɪᴀʀᴇ", "cittadino_chat", None),
        ("text", "〔💼〕・ᴄᴇɴᴛʀᴏ-ɪᴍᴘɪᴇɢᴏ", "cittadino_chat", None),
        ("text", "〔🏢〕・ᴀʟʙᴏ-ᴀᴢɪᴇɴᴅᴇ", "cittadino_read", None),
        ("text", "〔🌑〕・ᴅᴀʀᴋ-ᴡᴇʙ-ɪᴄ", "cittadino_chat", None),
    ]),
    ("⫷༺ 🏢 𝐀𝐙𝐈𝐄𝐍𝐃𝐄 & 𝐀𝐓𝐓𝐈𝐕𝐈𝐓𝐀̀ 𝐂𝐎𝐌𝐌𝐄𝐑𝐂𝐈𝐀𝐋𝐈 ༻⫸", "cittadino_read", [
        ("text", "〔🏎️〕・ᴍʀ-ᴍᴏᴛᴏʀꜱ-ʟɪꜱᴛɪɴᴏ", "motors_write", None),
        ("text", "〔🔧〕・ᴍʀ-ᴍᴏᴛᴏʀꜱ-ᴏꜰꜰɪᴄɪɴᴀ", "motors_write", None),
        ("text", "〔🍔〕・ʙᴜʀɢᴇʀ-ꜱʜᴏᴛ-ᴍᴇɴᴜ", "burger_write", None),
        ("text", "〔🥂〕・ᴇᴄʟɪᴘꜱᴇ-ᴄʟᴜʙ-ᴇᴠᴇɴᴛɪ", "club_write", None),
        ("text", "〔🚕〕・ʏᴇʟʟᴏᴡ-ᴄᴀʙ-ᴛᴀxɪ", "taxi_write", None),
        ("voice", "〔🏎️〕・ᴜꜰꜰɪᴄɪᴏ-ᴍʀ-ᴍᴏᴛᴏʀꜱ", "motors_only", None),
        ("voice", "〔🍔〕・ᴄᴜᴄɪɴᴀ-ʙᴜʀɢᴇʀ-ꜱʜᴏᴛ", "burger_only", None),
        ("voice", "〔🥂〕・ᴠɪᴘ-ᴇᴄʟɪᴘꜱᴇ-ᴄʟᴜʙ", "club_only", None),
    ]),
    ("⫷༺ 🚔 𝐌𝐑𝐏𝐃 - 𝐏𝐎𝐋𝐈𝐂𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓 ༻⫸", "mrpd", [
        ("text", "〔⏱️〕・ʀᴇɢɪꜱᴛʀᴏ-ᴛᴜʀɴɪ-ᴍʀᴘᴅ", "mrpd", None),
        ("text", "〔🚨〕・ʀɪᴄᴇʀᴄᴀᴛɪ-ᴡᴀɴᴛᴇᴅ", "mrpd", None),
        ("text", "〔💻〕・ᴏʀɪɢᴇɴ-ᴄᴀᴅ-ᴍʀᴘᴅ", "mrpd", None),
        ("text", "〔📄〕・ᴠᴇʀʙᴀʟɪ-ᴇ-ᴍᴜʟᴛᴇ", "mrpd", None),
        ("text", "〔📦〕・ᴅᴇᴘᴏꜱɪᴛᴏ-ꜱᴇQᴜᴇꜱᴛʀɪ", "mrpd_cmd", None),
        ("text", "〔📡〕・ᴄᴏᴍᴜɴɪᴄᴀᴢɪᴏɴɪ-ᴍʀᴘᴅ", "mrpd", None),
        ("voice", "〔🔊〕・ᴄᴇɴᴛʀᴀʟᴇ-ᴏᴘᴇʀᴀᴛɪᴠᴀ-911", "mrpd", None),
        ("voice", "〔🚓〕・ᴘᴀᴛᴛᴜɢʟɪᴀ-ᴀʟᴘʜᴀ", "mrpd", None),
        ("voice", "〔🚓〕・ᴘᴀᴛᴛᴜɢʟɪᴀ-ʙʀᴀᴠᴏ", "mrpd", None),
        ("voice", "〔🚓〕・ᴘᴀᴛᴛᴜɢʟɪᴀ-ᴄʜᴀʀʟɪᴇ", "mrpd", None),
        ("voice", "〔🛡️〕・ꜱᴡᴀᴛ-ᴛᴀᴄᴛɪᴄᴀʟ", "mrpd", None),
        ("voice", "〔🏛️〕・ᴜꜰꜰɪᴄɪᴏ-ᴄʜɪᴇꜰ-ᴏꜰ-ᴘᴏʟɪᴄᴇ", "mrpd_cmd", None),
    ]),
    ("⫷༺ 🕵️ 𝐃𝐄𝐓𝐄𝐂𝐓𝐈𝐕𝐄 𝐁𝐔𝐑𝐄𝐀𝐔 / 𝐅𝐈𝐁 ༻⫸", "fib", [
        ("text", "〔📂〕・ꜰᴀꜱᴄɪᴄᴏʟɪ-ɪɴᴅᴀɢɪɴɪ", "fib", None),
        ("text", "〔🔍〕・ʀɪᴄᴇʀᴄᴀᴛɪ-ꜰᴇᴅᴇʀᴀʟɪ", "fib", None),
        ("text", "〔📸〕・ᴘʀᴏᴠᴇ-ᴇ-ɪɴᴛᴇʀᴄᴇᴛᴛᴀᴢɪᴏɴɪ", "fib", None),
        ("voice", "〔🕵️〕・ꜱᴀʟᴀ-ᴏᴘᴇʀᴀᴛɪᴠᴀ-ꜰɪʙ", "fib", None),
        ("voice", "〔🕶️〕・ɪɴᴛᴇʀʀᴏɢᴀᴛᴏʀɪ-ꜰɪʙ", "fib", None),
    ]),
    ("⫷༺ 🚑 𝐌𝐑𝐄𝐌𝐒 - 𝐄𝐌𝐄𝐑𝐆𝐄𝐍𝐂𝐘 𝐌𝐄𝐃𝐈𝐂𝐀𝐋 ༻⫸", "mrems", [
        ("text", "〔⏱️〕・ʀᴇɢɪꜱᴛʀᴏ-ᴛᴜʀɴɪ-ᴍʀᴇᴍꜱ", "mrems", None),
        ("text", "〔🏥〕・ʀᴇꜰᴇʀᴛɪ-ᴍᴇᴅɪᴄɪ-911", "mrems", None),
        ("text", "〔💊〕・ᴄᴇʀᴛɪꜰɪᴄᴀᴛɪ-ᴘᴏʀᴛᴏ-ᴅᴀʀᴍɪ", "mrems", None),
        ("voice", "〔🚑〕・ᴄᴇɴᴛʀᴀʟᴇ-ᴍʀᴇᴍꜱ-911", "mrems", None),
        ("voice", "〔🩺〕・ᴜɴɪᴛᴀ̀-ᴀᴍʙᴜʟᴀɴᴢᴀ-1", "mrems", None),
        ("voice", "〔🚁〕・ᴇʟɪꜱᴏᴄᴄᴏʀꜱᴏ-ᴍᴇᴅᴇᴠᴀᴄ", "mrems", None),
    ]),
    ("⫷༺ 🚒 𝐌𝐑𝐅𝐃 - 𝐅𝐈𝐑𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓 ༻⫸", "mrfd", [
        ("text", "〔⏱️〕・ʀᴇɢɪꜱᴛʀᴏ-ᴛᴜʀɴɪ-ᴍʀꜰᴅ", "mrfd", None),
        ("text", "〔🧯〕・ʀᴀᴘᴘᴏʀᴛɪ-ɪɴᴛᴇʀᴠᴇɴᴛᴏ", "mrfd", None),
        ("text", "〔🔥〕・ᴀʟʟᴇʀᴛᴇ-ɪɴᴄᴇɴᴅɪᴏ-115", "mrfd", None),
        ("voice", "〔🚒〕・ᴄᴀꜱᴇʀᴍᴀ-ᴍʀꜰᴅ-115", "mrfd", None),
        ("voice", "〔🪓〕・ꜱQᴜᴀᴅʀᴀ-ꜱᴏᴄᴄᴏʀꜱᴏ-1", "mrfd", None),
    ]),
    ("⫷༺ 🎙️ 𝐒𝐀𝐋𝐄 𝐑𝐏 𝐂𝐈𝐓𝐓𝐀𝐃𝐈𝐍𝐄 ༻⫸", "cittadino_chat", [
        ("voice", "〔🏙️〕・ᴘɪᴀᴢᴢᴀ-ᴄᴇɴᴛʀᴀʟᴇ-ʀᴘ", "cittadino_chat", None),
        ("voice", "〔⚖️〕・ᴀᴜʟᴀ-ᴛʀɪʙᴜɴᴀʟᴇ", "cittadino_chat", None),
        ("voice", "〔🍔〕・ʙᴜʀɢᴇʀ-ꜱʜᴏᴛ-ꜱᴀʟᴀ", "cittadino_chat", None),
        ("voice", "〔🥂〕・ᴇᴄʟɪᴘꜱᴇ-ᴄʟᴜʙ-ᴘɪꜱᴛᴀ", "cittadino_chat", None),
        ("voice", "〔🎲〕・ꜱᴀʟᴀ-ʀᴘ-ʟɪʙᴇʀᴀ-1", "cittadino_chat", None),
        ("voice", "〔🎲〕・ꜱᴀʟᴀ-ʀᴘ-ʟɪʙᴇʀᴀ-2", "cittadino_chat", None),
    ]),
    ("⫷༺ 🎧 𝐀𝐒𝐒𝐈𝐒𝐓𝐄𝐍𝐙𝐀 & 𝐒𝐔𝐏𝐏𝐎𝐑𝐓𝐎 ༻⫸", "verificato_chat", [
        ("voice", "〔⏳〕・ᴀᴛᴛᴇꜱᴀ-ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ", "verificato_chat", None),
        ("voice", "〔💎〕・ᴀᴛᴛᴇꜱᴀ-ᴅᴏɴᴀᴢɪᴏɴɪ", "verificato_chat", None),
        ("voice", "〔🛂〕・ᴀᴛᴛᴇꜱᴀ-ᴡʜɪᴛᴇʟɪꜱᴛ", "verificato_chat", None),
        ("voice", "〔☕〕・ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ-1", "staff_voice_support", None),
        ("voice", "〔☕〕・ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ-2", "staff_voice_support", None),
        ("voice", "〔☕〕・ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ-3", "staff_voice_support", None),
    ]),
    ("⫷༺ 🛡️ 𝐀𝐑𝐄𝐀 𝐑𝐈𝐒𝐄𝐑𝐕𝐀𝐓𝐀 𝐒𝐓𝐀𝐅𝐅 ༻⫸", "staff", [
        ("text", "〔👑〕・ᴄʜᴀᴛ-ᴅɪʀᴇᴢɪᴏɴᴇ", "direzione", None),
        ("text", "〔💬〕・ᴄʜᴀᴛ-ꜱᴛᴀꜰꜰ", "staff", None),
        ("text", "〔📋〕・ɢᴇꜱᴛɪᴏɴᴇ-ᴛᴜʀɴɪ-ꜱᴛᴀꜰꜰ", "staff", None),
        ("text", "〔⚠️〕・ᴡᴀʀɴ-ᴇ-ʙᴀɴ-ᴀᴄ", "staff", None),
        ("text", "〔🔍〕・ᴄᴏɴᴛʀᴏʟʟᴏ-ᴘɢ-ᴇ-ʙᴀɴᴄᴀ", "direzione", None),
        ("text", "〔📑〕・ᴇꜱɪᴛᴏ-ᴀꜱꜱɪꜱᴛᴇɴᴢᴇ", "staff", None),
        ("text", "〔⭐〕・ꜰᴇᴇᴅʙᴀᴄᴋ-ᴀꜱꜱɪꜱᴛᴇɴᴢᴇ", "staff", None),
        ("text", "〔🛠️〕・ꜱᴠɪʟᴜᴘᴘᴏ-ᴇ-ᴜᴘᴅᴀᴛᴇ", "staff", None),
        ("text", "〔📁〕・ʟᴏɢ-ꜱɪꜱᴛᴇᴍᴀ", "direzione", None),
        ("voice", "〔🎮〕・ꜱᴛᴀꜰꜰ-ɪɴ-ʀᴘ", "staff", None),
        ("voice", "〔🎙️〕・ꜱᴀʟᴀ-ʀɪᴜɴɪᴏɴɪ-ꜱᴛᴀꜰꜰ", "staff", None),
        ("voice", "〔👑〕・ᴜꜰꜰɪᴄɪᴏ-ᴄʀᴇᴀᴛᴏʀ", "direzione", None),
    ]),
]

def costruisci_permessi(guild, r, profilo):
    everyone = guild.default_role
    ver = r["verificato"]
    cit = r["cittadino"]
    staff = r["staff_team"]

    read_only = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)
    full_chat = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, connect=True, speak=True, attach_files=True, embed_links=True)
    hidden = discord.PermissionOverwrite(view_channel=False)

    if profilo == "stats":
        return {everyone: discord.PermissionOverwrite(view_channel=True, connect=False)}
    elif profilo == "public_read":
        return {everyone: read_only, staff: full_chat}
    elif profilo == "verifica_ch":
        return {everyone: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True), staff: full_chat}
    elif profilo == "verificato_read":
        return {everyone: hidden, ver: read_only, staff: full_chat}
    elif profilo == "verificato_chat":
        return {everyone: hidden, ver: full_chat, staff: full_chat}
    elif profilo == "cittadino_read":
        return {everyone: hidden, cit: read_only, staff: full_chat}
    elif profilo == "cittadino_chat":
        return {everyone: hidden, cit: full_chat, staff: full_chat}
    elif profilo == "gov_write":
        return {everyone: hidden, cit: read_only, r["governatore"]: full_chat, r["vice_gov"]: full_chat, staff: full_chat}
    elif profilo == "giudice_write":
        return {everyone: hidden, cit: read_only, r["giudice"]: full_chat, r["procuratore"]: full_chat, r["governatore"]: full_chat, staff: full_chat}
    elif profilo == "motors_write":
        return {everyone: hidden, cit: read_only, r["motors"]: full_chat, r["dir_motors"]: full_chat, staff: full_chat}
    elif profilo == "motors_only":
        return {everyone: hidden, r["motors"]: full_chat, r["dir_motors"]: full_chat, staff: full_chat}
    elif profilo == "burger_write":
        return {everyone: hidden, cit: read_only, r["burger"]: full_chat, r["dir_burger"]: full_chat, staff: full_chat}
    elif profilo == "burger_only":
        return {everyone: hidden, r["burger"]: full_chat, r["dir_burger"]: full_chat, staff: full_chat}
    elif profilo == "club_write":
        return {everyone: hidden, cit: read_only, r["club"]: full_chat, r["dir_club"]: full_chat, staff: full_chat}
    elif profilo == "club_only":
        return {everyone: hidden, r["club"]: full_chat, r["dir_club"]: full_chat, staff: full_chat}
    elif profilo == "taxi_write":
        return {everyone: hidden, cit: read_only, r["taxi"]: full_chat, staff: full_chat}
    elif profilo == "mrpd":
        return {everyone: hidden, r["mrpd"]: full_chat, r["recruit_mrpd"]: full_chat, r["officer1_mrpd"]: full_chat, r["officer2_mrpd"]: full_chat, r["senior_mrpd"]: full_chat, r["sergeant_mrpd"]: full_chat, r["lieutenant_mrpd"]: full_chat, r["captain_mrpd"]: full_chat, r["deputy_chief_mrpd"]: full_chat, r["chief_mrpd"]: full_chat, r["swat_mrpd"]: full_chat, staff: full_chat}
    elif profilo == "mrpd_cmd":
        return {everyone: hidden, r["lieutenant_mrpd"]: full_chat, r["captain_mrpd"]: full_chat, r["deputy_chief_mrpd"]: full_chat, r["chief_mrpd"]: full_chat, staff: full_chat}
    elif profilo == "fib":
        return {everyone: hidden, r["fib"]: full_chat, r["senior_fib"]: full_chat, r["dir_fib"]: full_chat, staff: full_chat}
    elif profilo == "mrems":
        return {everyone: hidden, r["mrems"]: full_chat, r["emt_trainee"]: full_chat, r["emt_basic"]: full_chat, r["paramedic_mrems"]: full_chat, r["senior_paramedic"]: full_chat, r["doctor_mrems"]: full_chat, r["chief_mrems"]: full_chat, staff: full_chat}
    elif profilo == "mrfd":
        return {everyone: hidden, r["mrfd"]: full_chat, r["prob_mrfd"]: full_chat, r["firefighter_mrfd"]: full_chat, r["engineer_mrfd"]: full_chat, r["lieutenant_mrfd"]: full_chat, r["captain_mrfd"]: full_chat, r["chief_mrfd"]: full_chat, staff: full_chat}
    elif profilo == "staff_voice_support":
        return {everyone: hidden, ver: discord.PermissionOverwrite(view_channel=True, connect=False, speak=True), staff: full_chat}
    elif profilo == "staff":
        return {everyone: hidden, staff: full_chat}
    elif profilo == "direzione":
        return {
            everyone: hidden,
            r["creator"]: full_chat,
            r["cocreator"]: full_chat,
            r["owner"]: full_chat,
            r["deputy_owner"]: full_chat,
            r["head_staff"]: full_chat
        }
    return {everyone: read_only}

# =====================================================================
# TASK AGGIORNAMENTO STATISTICHE
# =====================================================================
@tasks.loop(minutes=5)
async def aggiorna_statistiche():
    for guild in bot.guilds:
        membri = guild.member_count
        staff_role = discord.utils.find(lambda r: "Staff Of Mine Roleplay" in r.name, guild.roles)
        cit_role = discord.utils.find(lambda r: "Cittadino Mine Roleplay" in r.name, guild.roles)

        n_staff = len(staff_role.members) if staff_role else 0
        n_cit = len(cit_role.members) if cit_role else 0

        for vc in guild.voice_channels:
            if vc.name.startswith("〔📊〕・"):
                await vc.edit(name=f"〔📊〕・ᴍᴇᴍʙʀɪ-ᴛᴏᴛᴀʟɪ-{membri}")
            elif vc.name.startswith("〔🛡️〕・"):
                await vc.edit(name=f"〔🛡️〕・ꜱᴛᴀꜰꜰ-ᴛᴏᴛᴀʟɪ-{n_staff}")
            elif vc.name.startswith("〔🪪〕・"):
                await vc.edit(name=f"〔🪪〕・ᴄɪᴛᴛᴀᴅɪɴɪ-{n_cit}")

@bot.event
async def on_ready():
    print(f"✅ Bot connesso come {bot.user} | Pronto per Mine Roleplay!")
    if not aggiorna_statistiche.is_running():
        aggiorna_statistiche.start()

# =====================================================================
# COMANDO 1: !setup_mr (CREA RUOLI IN ORDINE ESATTO, CANALI E INVIA GUIDE)
# =====================================================================
@bot.command(name="setup_mr")
@commands.has_permissions(administrator=True)
async def setup_mr(ctx):
    guild = ctx.guild
    await ctx.send("⚙️ **Avvio creazione server Mine Roleplay (Ruoli ordinati, Permessi Granulari, Guide & Moduli Bandi)...**")

    for ch in list(guild.channels):
        if ch.id != ctx.channel.id:
            try:
                await ch.delete()
                await asyncio.sleep(0.35)
            except Exception:
                pass

    for r in list(guild.roles):
        if not r.is_default() and not r.managed and r < guild.me.top_role:
            try:
                await r.delete()
                await asyncio.sleep(0.25)
            except Exception:
                pass

    # Creazione ruoli in ordine inverso + forzatura posizioni esatte dall'alto al basso
    ruoli_creati = {}
    lista_ordinata_oggetti = []
    for key, nome, colore, hoist, is_admin, is_staff in reversed(RUOLI_TEMPLATE):
        perms = discord.Permissions.none()
        if is_admin:
            perms = discord.Permissions.all()
        elif is_staff:
            perms = discord.Permissions(
                view_channel=True, send_messages=True, manage_messages=True,
                kick_members=True, mute_members=True, move_members=True,
                connect=True, speak=True, read_message_history=True
            )
        ruolo = await guild.create_role(
            name=nome,
            colour=discord.Colour(colore),
            hoist=hoist,
            permissions=perms
        )
        ruoli_creati[key] = ruolo
        await asyncio.sleep(0.3)

    # Forzatura posizioni esatte (risolve definitivamente l'inversione ruoli)
    for key, _, _, _, _, _ in RUOLI_TEMPLATE:
        lista_ordinata_oggetti.append(ruoli_creati[key])

    top_pos = guild.me.top_role.position - 1
    posizioni = {}
    for idx, ruolo_obj in enumerate(lista_ordinata_oggetti):
        posizioni[ruolo_obj] = max(1, top_pos - idx)

    try:
        await guild.edit_role_positions(positions=posizioni)
    except Exception as e:
        print(f"Avviso ordinamento ruoli: {e}")

    # Creazione categorie, canali, permessi e invio automatico testi
    for cat_nome, cat_perm, canali in STRUTTURA_SERVER:
        cat_ow = costruisci_permessi(guild, ruoli_creati, cat_perm)
        categoria = await guild.create_category(name=cat_nome, overwrites=cat_ow)
        await asyncio.sleep(0.35)

        for tipo, ch_nome, ch_perm, msg_key in canali:
            ch_ow = costruisci_permessi(guild, ruoli_creati, ch_perm)
            if tipo == "text":
                canale = await guild.create_text_channel(name=ch_nome, category=categoria, overwrites=ch_ow)
                if msg_key and msg_key in MESSAGGI_CANALI:
                    testo = MESSAGGI_CANALI[msg_key]
                    for i in range(0, len(testo), 1950):
                        await canale.send(testo[i:i + 1950])
                        await asyncio.sleep(0.4)
            else:
                await guild.create_voice_channel(name=ch_nome, category=categoria, overwrites=ch_ow)
            await asyncio.sleep(0.35)

    try:
        await ctx.channel.delete()
    except Exception:
        pass

    staff_chat = discord.utils.find(lambda c: "ᴄʜᴀᴛ-ꜱᴛᴀꜰꜰ" in c.name, guild.text_channels)
    if staff_chat:
        await staff_chat.send(
            "✅ **Server Mine Roleplay completato con successo!**\n"
            f"• **{len(RUOLI_TEMPLATE)} ruoli** creati e ordinati perfettamente dall'alto al basso.\n"
            "• Tutti i regolamenti, le guide e i moduli dei bandi sono stati inviati nei canali appositi."
        )

# =====================================================================
# COMANDO 2: !backup_mr (SALVA ANCHE I PERMESSI DI OGNI CANALE E CATEGORIA)
# =====================================================================
@bot.command(name="backup_mr")
@commands.has_permissions(administrator=True)
async def backup_mr(ctx):
    guild = ctx.guild
    data = {
        "server_name": guild.name,
        "roles": [],
        "categories": []
    }

    for r in reversed(guild.roles):
        if not r.is_default() and not r.managed:
            data["roles"].append({
                "name": r.name,
                "color": r.colour.value,
                "hoist": r.hoist,
                "mentionable": r.mentionable,
                "permissions": r.permissions.value
            })

    def serialize_ow(overwrites):
        res = []
        for target, ow in overwrites.items():
            if isinstance(target, discord.Role):
                allow, deny = ow.pair()
                res.append({
                    "role_name": target.name,
                    "allow": allow.value,
                    "deny": deny.value
                })
        return res

    for cat in guild.categories:
        cat_obj = {
            "name": cat.name,
            "overwrites": serialize_ow(cat.overwrites),
            "channels": []
        }
        for ch in cat.channels:
            cat_obj["channels"].append({
                "name": ch.name,
                "type": "voice" if isinstance(ch, discord.VoiceChannel) else "text",
                "topic": getattr(ch, "topic", None),
                "overwrites": serialize_ow(ch.overwrites)
            })
        data["categories"].append(cat_obj)

    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    await ctx.send(
        f"💾 **Backup completo di `{guild.name}` (con tutti i permessi) salvato!**\n"
        f"• Ruoli salvati: **{len(data['roles'])}**\n"
        f"• Categorie salvate: **{len(data['categories'])}**",
        file=discord.File(BACKUP_FILE)
    )

# =====================================================================
# COMANDO 3: !ripristina_mr
# =====================================================================
@bot.command(name="ripristina_mr")
@commands.has_permissions(administrator=True)
async def ripristina_mr(ctx):
    if not os.path.exists(BACKUP_FILE):
        await ctx.send("❌ Nessun file `backup_mine_roleplay.json` trovato!")
        return

    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    guild = ctx.guild
    await ctx.send(f"🔄 **Ripristino completo di `{data['server_name']}` (ruoli, canali e permessi) in corso...**")

    for ch in list(guild.channels):
        if ch.id != ctx.channel.id:
            try:
                await ch.delete()
                await asyncio.sleep(0.35)
            except Exception:
                pass

    for r in list(guild.roles):
        if not r.is_default() and not r.managed and r < guild.me.top_role:
            try:
                await r.delete()
                await asyncio.sleep(0.25)
            except Exception:
                pass

    roles_by_name = {"@everyone": guild.default_role}
    ordered_restored = []
    for r_data in reversed(data["roles"]):
        nr = await guild.create_role(
            name=r_data["name"],
            colour=discord.Colour(r_data["color"]),
            hoist=r_data["hoist"],
            mentionable=r_data["mentionable"],
            permissions=discord.Permissions(r_data["permissions"])
        )
        roles_by_name[nr.name] = nr
        await asyncio.sleep(0.3)

    for r_data in data["roles"]:
        if r_data["name"] in roles_by_name:
            ordered_restored.append(roles_by_name[r_data["name"]])

    top_pos = guild.me.top_role.position - 1
    pos_map = {r_obj: max(1, top_pos - i) for i, r_obj in enumerate(ordered_restored)}
    try:
        await guild.edit_role_positions(positions=pos_map)
    except Exception:
        pass

    def build_ow(ow_list):
        ow_dict = {}
        for item in ow_list:
            role_obj = roles_by_name.get(item["role_name"])
            if role_obj:
                ow_dict[role_obj] = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(item["allow"]),
                    discord.Permissions(item["deny"])
                )
        return ow_dict

    for cat_data in data["categories"]:
        cat = await guild.create_category(name=cat_data["name"], overwrites=build_ow(cat_data.get("overwrites", [])))
        await asyncio.sleep(0.35)
        for ch_data in cat_data["channels"]:
            ch_ow = build_ow(ch_data.get("overwrites", []))
            if ch_data["type"] == "voice":
                await guild.create_voice_channel(name=ch_data["name"], category=cat, overwrites=ch_ow)
            else:
                await guild.create_text_channel(name=ch_data["name"], category=cat, topic=ch_data.get("topic"), overwrites=ch_ow)
            await asyncio.sleep(0.35)

    try:
        await ctx.channel.delete()
    except Exception:
        pass

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
