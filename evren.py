import os
import json
import asyncio
from threading import Thread
from flask import Flask
import discord
from discord.ext import commands, tasks

# =====================================================================
# MINE ROLEPLAY - DISCORD SERVER ARCHITECT & BACKUP BOT (FULL EDITION)
# Formato 100% Uniforme: Categorie, Canali Testuali, Vocali & Ruoli
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
# GERARCHIA RUOLI COMPLETA (DALL'ALTO VERSO IL BASSO)
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

    ("sep_gov", "⫷・═══ 𝐈𝐒𝐓𝐈𝐓𝐔𝐙𝐈𝐎𝐍𝐈 & 𝐅𝐀𝐙𝐈𝐎𝐍𝐈 𝐔𝐒𝐀 ═══・⫸", 0x2B2D31, True, False, False),
    ("governatore", "🏛️・𝐆𝐨𝐯𝐞𝐫𝐧𝐚𝐭𝐨𝐫𝐞 𝐌𝐢𝐧𝐞 𝐑𝐨𝐥𝐞𝐩𝐥𝐚𝐲", 0xFFD700, True, False, False),
    ("giudice", "⚖️・𝐆𝐢𝐮𝐝𝐢𝐜𝐞 / 𝐏𝐫𝐨𝐜𝐮𝐫𝐚𝐭𝐨𝐫𝐞", 0xFFE082, True, False, False),
    ("chief_mrpd", "⭐・𝐂𝐡𝐢𝐞𝐟 𝐎𝐟 𝐏𝐨𝐥𝐢𝐜𝐞 (𝐌𝐑𝐏𝐃)", 0x1565C0, True, False, False),
    ("cmd_mrpd", "🚓・𝐀𝐥𝐭𝐨 𝐂𝐨𝐦𝐚𝐧𝐝𝐨 𝐌𝐑𝐏𝐃", 0x1976D2, True, False, False),
    ("mrpd", "🚔・𝐀𝐠𝐞𝐧𝐭𝐞 𝐌𝐑𝐏𝐃", 0x42A5F5, True, False, False),
    ("dir_fib", "🕵️・𝐃𝐢𝐫𝐞𝐭𝐭𝐨𝐫𝐞 𝐃𝐞𝐭𝐞𝐜𝐭𝐢𝐯𝐞 / 𝐅𝐈𝐁", 0x263238, True, False, False),
    ("fib", "🕶️・𝐀𝐠𝐞𝐧𝐭𝐞 𝐃𝐞𝐭𝐞𝐜𝐭𝐢𝐯𝐞 / 𝐅𝐈𝐁", 0x455A64, True, False, False),
    ("chief_mrems", "🩺・𝐂𝐡𝐢𝐞𝐟 𝐎𝐟 𝐄𝐌𝐒 (𝐌𝐑𝐄𝐌𝐒)", 0xC62828, True, False, False),
    ("mrems", "🚑・𝐏𝐚𝐫𝐚𝐦𝐞𝐝𝐢𝐜𝐨 𝐌𝐑𝐄𝐌𝐒 𝟗𝟏𝟏", 0xEF5350, True, False, False),
    ("chief_mrfd", "🚒・𝐅𝐢𝐫𝐞 𝐂𝐡𝐢𝐞𝐟 (𝐌𝐑𝐅𝐃)", 0xD84315, True, False, False),
    ("mrfd", "🧯・𝐕𝐢𝐠𝐢𝐥𝐞 𝐝𝐞𝐥 𝐅𝐮𝐨𝐜𝐨 𝐌𝐑𝐅𝐃", 0xFF7043, True, False, False),

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
# STRUTTURA CATEGORIE E CANALI (100% FORMATO IDENTICO: 〔emoji〕・ɴᴏᴍᴇ)
# =====================================================================
STRUTTURA_SERVER = [
    ("⫷༺ 📊 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐇𝐄 𝐌𝐈𝐍𝐄 𝐑𝐎𝐋𝐄𝐏𝐥𝐚𝐲 ༻⫸", "stats", [
        ("voice", "〔📊〕・ᴍᴇᴍʙʀɪ-ᴛᴏᴛᴀʟɪ-0"),
        ("voice", "〔🛡️〕・ꜱᴛᴀꜰꜰ-ᴛᴏᴛᴀʟɪ-0"),
        ("voice", "〔🪪〕・ᴄɪᴛᴛᴀᴅɪɴɪ-0"),
        ("voice", "〔🟢〕・ꜱᴇʀᴠᴇʀ-ᴏɴʟɪɴᴇ"),
    ]),
    ("⫷༺ ⚔️ 𝐁𝐄𝐍𝐕𝐄𝐍𝐔𝐓𝐎 & 𝐈𝐍𝐅𝐎 ༻⫸", "public_read", [
        ("text", "〔👋〕・ʙᴇɴᴠᴇɴᴜᴛᴏ"),
        ("text", "〔🚪〕・ᴀᴅᴅɪᴏ"),
        ("text", "〔✅〕・ᴠᴇʀɪꜰɪᴄᴀ"),
        ("text", "〔📜〕・ꜱᴛᴏʀɪᴀ-ᴅᴇʟʟᴀ-ᴄɪᴛᴛᴀ̀"),
        ("text", "〔🗺️〕・ᴍᴀᴘᴘᴀ-ᴇ-ᴘᴜɴᴛɪ-ɢᴘꜱ"),
        ("text", "〔🎮〕・ᴄᴏᴍᴇ-ᴇɴᴛʀᴀʀᴇ-ᴘꜱ4-ᴘꜱ5-ᴘᴄ"),
        ("text", "〔🎧〕・ᴄᴏʟʟᴇɢᴀ-ᴠᴏᴄᴇ-ᴏᴘᴇɴᴀᴜᴅɪᴏ"),
        ("text", "〔💎〕・ᴠɪᴘ-ᴇ-ꜱᴜᴘᴘᴏʀᴛ-ᴘᴀᴄᴋ"),
        ("text", "〔🔗〕・ʟɪɴᴋ-ɪɴᴠɪᴛᴏ"),
        ("text", "〔🟢〕・ꜱᴛᴀᴛᴏ-ꜱᴇʀᴠᴇʀ"),
    ]),
    ("⫷༺ 📜 𝐑𝐄𝐆𝐎𝐋𝐀𝐌𝐄𝐍𝐓𝐈 𝐔𝐅𝐅𝐈𝐂𝐈𝐀𝐋𝐈 ༻⫸", "public_read", [
        ("text", "〔📕〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ꜱᴇʀᴠᴇʀ"),
        ("text", "〔📘〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ᴅɪꜱᴄᴏʀᴅ"),
        ("text", "〔📗〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ꜰᴀᴢɪᴏɴɪ"),
        ("text", "〔📙〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ᴄʀɪᴍɪɴᴇ"),
        ("text", "〔⚖️〕・ᴄᴏᴅɪᴄᴇ-ᴘᴇɴᴀʟᴇ-ᴍʀᴘᴅ"),
        ("text", "〔🚗〕・ᴄᴏᴅɪᴄᴇ-ᴅᴇʟʟᴀ-ꜱᴛʀᴀᴅᴀ-ᴅᴍᴠ"),
        ("text", "〔🔫〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ᴘᴏʀᴛᴏ-ᴅᴀʀᴍɪ"),
        ("text", "〔🏠〕・ʀᴇɢᴏʟᴀᴍᴇɴᴛᴏ-ɪᴍᴍᴏʙɪʟɪ-ᴇ-ᴀᴢɪᴇɴᴅᴇ"),
    ]),
    ("⫷༺ 🛂 𝐀𝐑𝐄𝐀 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓 & 𝐓𝐈𝐂𝐊𝐄𝐓 ༻⫸", "public_chat", [
        ("text", "〔📝〕・ꜰᴀɪ-ᴡʜɪᴛᴇʟɪꜱᴛ"),
        ("text", "〔📩〕・ᴇꜱɪᴛᴏ-ᴡʜɪᴛᴇʟɪꜱᴛ"),
        ("text", "〔❓〕・ᴅᴏᴍᴀɴᴅᴇ-ᴡʜɪᴛᴇʟɪꜱᴛ"),
        ("text", "〔🎫〕・ᴛɪᴄᴋᴇᴛ-ɢᴇɴᴇʀᴀʟᴇ"),
        ("text", "〔💎〕・ᴛɪᴄᴋᴇᴛ-ᴅᴏɴᴀᴢɪᴏɴɪ"),
        ("text", "〔⭐〕・ᴛɪᴄᴋᴇᴛ-ɢʀᴀᴅᴏ-ᴀʟᴛᴏ"),
        ("text", "〔🏛️〕・ᴛɪᴄᴋᴇᴛ-ꜰᴀᴢɪᴏɴᴇ"),
        ("text", "〔🏢〕・ᴛɪᴄᴋᴇᴛ-ᴀᴘᴇʀᴛᴜʀᴀ-ᴀᴢɪᴇɴᴅᴀ"),
        ("text", "〔🐛〕・ꜱᴇɢɴᴀʟᴀ-ʙᴜɢ"),
        ("text", "〔⚖️〕・ʀɪᴄʜɪᴇꜱᴛᴀ-ᴜɴʙᴀɴ"),
        ("text", "〔☠️〕・ʀɪᴄʜɪᴇꜱᴛᴀ-ᴘᴇʀᴍᴀᴅᴇᴀᴛʜ"),
    ]),
    ("⫷༺ 💬 𝐂𝐎𝐌𝐌𝐔𝐍𝐈𝐓𝐘 𝐎𝐎𝐂 & 𝐌𝐄𝐃𝐈𝐀 ༻⫸", "public_chat", [
        ("text", "〔📢〕・ᴀɴɴᴜɴᴄɪ-ꜱᴇʀᴠᴇʀ"),
        ("text", "〔💬〕・ᴄʜᴀᴛ-ᴏᴏᴄ"),
        ("text", "〔💡〕・ꜱᴜɢɢᴇʀɪᴍᴇɴᴛɪ-ꜱᴇʀᴠᴇʀ"),
        ("text", "〔📸〕・ᴍᴇᴅɪᴀ-ᴄʟɪᴘ-ʀᴘ"),
        ("text", "〔🎥〕・ᴄʟɪᴘ-ᴇ-ᴛɪᴋᴛᴏᴋ"),
        ("text", "〔🎁〕・ɢɪᴠᴇᴀᴡᴀʏ-ᴇ-ᴇᴠᴇɴᴛɪ"),
        ("text", "〔🤝〕・ᴘᴀʀᴛɴᴇʀꜱʜɪᴘ"),
        ("text", "〔🤖〕・ᴄᴏᴍᴀɴᴅɪ-ʙᴏᴛ"),
    ]),
    ("⫷༺ 🌆 𝐀𝐑𝐄𝐀 𝐈𝐍-𝐂𝐇𝐀𝐑𝐀𝐂𝐓𝐄𝐑 (𝐈𝐂) ༻⫸", "public_chat", [
        ("text", "〔📱〕・ʏᴇʟʟᴏᴡ-ᴘᴀɢᴇꜱ-ᴀɴɴᴜɴᴄɪ"),
        ("text", "〔📰〕・ᴍɪɴᴇ-ʀᴏʟᴇᴘʟᴀʏ-ɴᴇᴡꜱ"),
        ("text", "〔🏛️〕・ᴄᴏᴍᴜɴɪᴄᴀᴛɪ-ɢᴏᴠᴇʀɴᴏ"),
        ("text", "〔⚖️〕・ᴛʀɪʙᴜɴᴀʟᴇ-ᴇ-ꜱᴇɴᴛᴇɴᴢᴇ"),
        ("text", "〔🚗〕・ᴀᴜᴛᴏꜱᴀʟᴏɴᴇ-ᴜꜱᴀᴛᴏ"),
        ("text", "〔🏠〕・ᴀɢᴇɴᴢɪᴀ-ɪᴍᴍᴏʙɪʟɪᴀʀᴇ"),
        ("text", "〔💼〕・ᴄᴇɴᴛʀᴏ-ɪᴍᴘɪᴇɢᴏ"),
        ("text", "〔🏢〕・ᴀʟʙᴏ-ᴀᴢɪᴇɴᴅᴇ"),
        ("text", "〔🌑〕・ᴅᴀʀᴋ-ᴡᴇʙ-ɪᴄ"),
    ]),
    ("⫷༺ 🏢 𝐀𝐙𝐈𝐄𝐍𝐃𝐄 & 𝐀𝐓𝐓𝐈𝐕𝐈𝐓𝐀̀ 𝐂𝐎𝐌𝐌𝐄𝐑𝐂𝐈𝐀𝐋𝐈 ༻⫸", "aziende", [
        ("text", "〔🏎️〕・ᴍʀ-ᴍᴏᴛᴏʀꜱ-ʟɪꜱᴛɪɴᴏ"),
        ("text", "〔🔧〕・ᴍʀ-ᴍᴏᴛᴏʀꜱ-ᴏꜰꜰɪᴄɪɴᴀ"),
        ("text", "〔🍔〕・ʙᴜʀɢᴇʀ-ꜱʜᴏᴛ-ᴍᴇɴᴜ"),
        ("text", "〔🥂〕・ᴇᴄʟɪᴘꜱᴇ-ᴄʟᴜʙ-ᴇᴠᴇɴᴛɪ"),
        ("text", "〔🚕〕・ʏᴇʟʟᴏᴡ-ᴄᴀʙ-ᴛᴀxɪ"),
        ("voice", "〔🏎️〕・ᴜꜰꜰɪᴄɪᴏ-ᴍʀ-ᴍᴏᴛᴏʀꜱ"),
        ("voice", "〔🍔〕・ᴄᴜᴄɪɴᴀ-ʙᴜʀɢᴇʀ-ꜱʜᴏᴛ"),
        ("voice", "〔🥂〕・ᴠɪᴘ-ᴇᴄʟɪᴘꜱᴇ-ᴄʟᴜʙ"),
    ]),
    ("⫷༺ 🚔 𝐌𝐑𝐏𝐃 - 𝐏𝐎𝐋𝐈𝐂𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓 ༻⫸", "mrpd", [
        ("text", "〔📋〕・ʙᴀɴᴅɪ-ᴍʀᴘᴅ-ᴀᴘᴇʀᴛɪ"),
        ("text", "〔⏱️〕・ʀᴇɢɪꜱᴛʀᴏ-ᴛᴜʀɴɪ-ᴍʀᴘᴅ"),
        ("text", "〔🚨〕・ʀɪᴄᴇʀᴄᴀᴛɪ-ᴡᴀɴᴛᴇᴅ"),
        ("text", "〔💻〕・ᴏʀɪɢᴇɴ-ᴄᴀᴅ-ᴍʀᴘᴅ"),
        ("text", "〔📄〕・ᴠᴇʀʙᴀʟɪ-ᴇ-ᴍᴜʟᴛᴇ"),
        ("text", "〔📦〕・ᴅᴇᴘᴏꜱɪᴛᴏ-ꜱᴇQᴜᴇꜱᴛʀɪ"),
        ("text", "〔📡〕・ᴄᴏᴍᴜɴɪᴄᴀᴢɪᴏɴɪ-ᴍʀᴘᴅ"),
        ("voice", "〔🔊〕・ᴄᴇɴᴛʀᴀʟᴇ-ᴏᴘᴇʀᴀᴛɪᴠᴀ-911"),
        ("voice", "〔🚓〕・ᴘᴀᴛᴛᴜɢʟɪᴀ-ᴀʟᴘʜᴀ"),
        ("voice", "〔🚓〕・ᴘᴀᴛᴛᴜɢʟɪᴀ-ʙʀᴀᴠᴏ"),
        ("voice", "〔🚓〕・ᴘᴀᴛᴛᴜɢʟɪᴀ-ᴄʜᴀʀʟɪᴇ"),
        ("voice", "〔🛡️〕・ꜱᴡᴀᴛ-ᴛᴀᴄᴛɪᴄᴀʟ"),
        ("voice", "〔🏛️〕・ᴜꜰꜰɪᴄɪᴏ-ᴄʜɪᴇꜰ-ᴏꜰ-ᴘᴏʟɪᴄᴇ"),
    ]),
    ("⫷༺ 🕵️ 𝐃𝐄𝐓𝐄𝐂𝐓𝐈𝐕𝐄 𝐁𝐔𝐑𝐄𝐀𝐔 / 𝐅𝐈𝐁 ༻⫸", "fib", [
        ("text", "〔📂〕・ꜰᴀꜱᴄɪᴄᴏʟɪ-ɪɴᴅᴀɢɪɴɪ"),
        ("text", "〔🔍〕・ʀɪᴄᴇʀᴄᴀᴛɪ-ꜰᴇᴅᴇʀᴀʟɪ"),
        ("text", "〔📸〕・ᴘʀᴏᴠᴇ-ᴇ-ɪɴᴛᴇʀᴄᴇᴛᴛᴀᴢɪᴏɴɪ"),
        ("voice", "〔🕵️〕・ꜱᴀʟᴀ-ᴏᴘᴇʀᴀᴛɪᴠᴀ-ꜰɪʙ"),
        ("voice", "〔🕶️〕・ɪɴᴛᴇʀʀᴏɢᴀᴛᴏʀɪ-ꜰɪʙ"),
    ]),
    ("⫷༺ 🚑 𝐌𝐑𝐄𝐌𝐒 - 𝐄𝐌𝐄𝐑𝐆𝐄𝐍𝐂𝐘 𝐌𝐄𝐃𝐈𝐂𝐀𝐋 ༻⫸", "mrems", [
        ("text", "〔📋〕・ʙᴀɴᴅɪ-ᴍʀᴇᴍꜱ-ᴀᴘᴇʀᴛɪ"),
        ("text", "〔⏱️〕・ʀᴇɢɪꜱᴛʀᴏ-ᴛᴜʀɴɪ-ᴍʀᴇᴍꜱ"),
        ("text", "〔🏥〕・ʀᴇꜰᴇʀᴛɪ-ᴍᴇᴅɪᴄɪ-911"),
        ("text", "〔💊〕・ᴄᴇʀᴛɪꜰɪᴄᴀᴛɪ-ᴘᴏʀᴛᴏ-ᴅᴀʀᴍɪ"),
        ("voice", "〔🚑〕・ᴄᴇɴᴛʀᴀʟᴇ-ᴍʀᴇᴍꜱ-911"),
        ("voice", "〔🩺〕・ᴜɴɪᴛᴀ̀-ᴀᴍʙᴜʟᴀɴᴢᴀ-1"),
        ("voice", "〔🚁〕・ᴇʟɪꜱᴏᴄᴄᴏʀꜱᴏ-ᴍᴇᴅᴇᴠᴀᴄ"),
    ]),
    ("⫷༺ 🚒 𝐌𝐑𝐅𝐃 - 𝐅𝐈𝐑𝐄 𝐃𝐄𝐏𝐀𝐑𝐓𝐌𝐄𝐍𝐓 ༻⫸", "mrfd", [
        ("text", "〔📋〕・ʙᴀɴᴅɪ-ᴍʀꜰᴅ-ᴀᴘᴇʀᴛɪ"),
        ("text", "〔⏱️〕・ʀᴇɢɪꜱᴛʀᴏ-ᴛᴜʀɴɪ-ᴍʀꜰᴅ"),
        ("text", "〔🧯〕・ʀᴀᴘᴘᴏʀᴛɪ-ɪɴᴛᴇʀᴠᴇɴᴛᴏ"),
        ("text", "〔🔥〕・ᴀʟʟᴇʀᴛᴇ-ɪɴᴄᴇɴᴅɪᴏ-115"),
        ("voice", "〔🚒〕・ᴄᴀꜱᴇʀᴍᴀ-ᴍʀꜰᴅ-115"),
        ("voice", "〔🪓〕・ꜱQᴜᴀᴅʀᴀ-ꜱᴏᴄᴄᴏʀꜱᴏ-1"),
    ]),
    ("⫷༺ 🎙️ 𝐒𝐀𝐋𝐄 𝐑𝐏 𝐂𝐈𝐓𝐓𝐀𝐃𝐈𝐍𝐄 ༻⫸", "public_chat", [
        ("voice", "〔🏙️〕・ᴘɪᴀᴢᴢᴀ-ᴄᴇɴᴛʀᴀʟᴇ-ʀᴘ"),
        ("voice", "〔⚖️〕・ᴀᴜʟᴀ-ᴛʀɪʙᴜɴᴀʟᴇ"),
        ("voice", "〔🍔〕・ʙᴜʀɢᴇʀ-ꜱʜᴏᴛ-ꜱᴀʟᴀ"),
        ("voice", "〔🥂〕・ᴇᴄʟɪᴘꜱᴇ-ᴄʟᴜʙ-ᴘɪꜱᴛᴀ"),
        ("voice", "〔🎲〕・ꜱᴀʟᴀ-ʀᴘ-ʟɪʙᴇʀᴀ-1"),
        ("voice", "〔🎲〕・ꜱᴀʟᴀ-ʀᴘ-ʟɪʙᴇʀᴀ-2"),
    ]),
    ("⫷༺ 🎧 𝐀𝐒𝐒𝐈𝐒𝐓𝐄𝐍𝐙𝐀 & 𝐒𝐔𝐏𝐏𝐎𝐑𝐓𝐎 ༻⫸", "public_chat", [
        ("voice", "〔⏳〕・ᴀᴛᴛᴇꜱᴀ-ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ"),
        ("voice", "〔💎〕・ᴀᴛᴛᴇꜱᴀ-ᴅᴏɴᴀᴢɪᴏɴɪ"),
        ("voice", "〔🛂〕・ᴀᴛᴛᴇꜱᴀ-ᴡʜɪᴛᴇʟɪꜱᴛ"),
        ("voice", "〔☕〕・ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ-1"),
        ("voice", "〔☕〕・ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ-2"),
        ("voice", "〔☕〕・ᴀꜱꜱɪꜱᴛᴇɴᴢᴀ-3"),
    ]),
    ("⫷༺ 🛡️ 𝐀𝐑𝐄𝐀 𝐑𝐈𝐒𝐄𝐑𝐕𝐀𝐓𝐀 𝐒𝐓𝐀𝐅𝐅 ༻⫸", "staff", [
        ("text", "〔👑〕・ᴄʜᴀᴛ-ᴅɪʀᴇᴢɪᴏɴᴇ"),
        ("text", "〔💬〕・ᴄʜᴀᴛ-ꜱᴛᴀꜰꜰ"),
        ("text", "〔📋〕・ɢᴇꜱᴛɪᴏɴᴇ-ᴛᴜʀɴɪ-ꜱᴛᴀꜰꜰ"),
        ("text", "〔⚠️〕・ᴡᴀʀɴ-ᴇ-ʙᴀɴ-ᴀᴄ"),
        ("text", "〔🔍〕・ᴄᴏɴᴛʀᴏʟʟᴏ-ᴘɢ-ᴇ-ʙᴀɴᴄᴀ"),
        ("text", "〔📑〕・ᴇꜱɪᴛᴏ-ᴀꜱꜱɪꜱᴛᴇɴᴢᴇ"),
        ("text", "〔⭐〕・ꜰᴇᴇᴅʙᴀᴄᴋ-ᴀꜱꜱɪꜱᴛᴇɴᴢᴇ"),
        ("text", "〔🛠️〕・ꜱᴠɪʟᴜᴘᴘᴏ-ᴇ-ᴜᴘᴅᴀᴛᴇ"),
        ("text", "〔📁〕・ʟᴏɢ-ꜱɪꜱᴛᴇᴍᴀ"),
        ("voice", "〔🎮〕・ꜱᴛᴀꜰꜰ-ɪɴ-ʀᴘ"),
        ("voice", "〔🎙️〕・ꜱᴀʟᴀ-ʀɪᴜɴɪᴏɴɪ-ꜱᴛᴀꜰꜰ"),
        ("voice", "〔👑〕・ᴜꜰꜰɪᴄɪᴏ-ᴄʀᴇᴀᴛᴏʀ"),
    ]),
]

# =====================================================================
# TASK AGGIORNAMENTO STATISTICHE (STESSO IDENTICO FORMATO 〔emoji〕・ɴᴏᴍᴇ)
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
# COMANDO 1: !setup_mr
# =====================================================================
@bot.command(name="setup_mr")
@commands.has_permissions(administrator=True)
async def setup_mr(ctx):
    guild = ctx.guild
    await ctx.send("⚙️ **Avvio creazione struttura completa Mine Roleplay...** (Attendi circa 35 secondi)")

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

    ruoli_creati = {}
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

    everyone = guild.default_role
    staff_r = ruoli_creati["staff_team"]
    mrpd_r = ruoli_creati["mrpd"]
    fib_r = ruoli_creati["fib"]
    mrems_r = ruoli_creati["mrems"]
    mrfd_r = ruoli_creati["mrfd"]

    for cat_nome, accesso, canali in STRUTTURA_SERVER:
        overwrites = {}
        if accesso == "stats":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=True, connect=False)
            }
        elif accesso == "public_read":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True),
                staff_r: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
        elif accesso == "public_chat":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)
            }
        elif accesso == "aziende":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)
            }
        elif accesso == "staff":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=False),
                staff_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)
            }
        elif accesso == "mrpd":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=False),
                staff_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                mrpd_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                ruoli_creati["cmd_mrpd"]: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                ruoli_creati["chief_mrpd"]: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)
            }
        elif accesso == "fib":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=False),
                staff_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                fib_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                ruoli_creati["dir_fib"]: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)
            }
        elif accesso == "mrems":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=False),
                staff_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                mrems_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                ruoli_creati["chief_mrems"]: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)
            }
        elif accesso == "mrfd":
            overwrites = {
                everyone: discord.PermissionOverwrite(view_channel=False),
                staff_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                mrfd_r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True),
                ruoli_creati["chief_mrfd"]: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True)
            }

        categoria = await guild.create_category(name=cat_nome, overwrites=overwrites)
        await asyncio.sleep(0.35)

        for tipo, ch_nome in canali:
            if tipo == "text":
                await guild.create_text_channel(name=ch_nome, category=categoria)
            else:
                await guild.create_voice_channel(name=ch_nome, category=categoria)
            await asyncio.sleep(0.35)

    try:
        await ctx.channel.delete()
    except Exception:
        pass

    staff_chat = discord.utils.find(lambda c: "ᴄʜᴀᴛ-ꜱᴛᴀꜰꜰ" in c.name, guild.text_channels)
    if staff_chat:
        await staff_chat.send("✅ **Struttura completa di Mine Roleplay generata con successo!** Usa `!backup_mr` per esportare il file JSON di sicurezza.")

# =====================================================================
# COMANDO 2: !backup_mr
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

    for cat in guild.categories:
        cat_obj = {
            "name": cat.name,
            "channels": []
        }
        for ch in cat.channels:
            cat_obj["channels"].append({
                "name": ch.name,
                "type": "voice" if isinstance(ch, discord.VoiceChannel) else "text",
                "topic": getattr(ch, "topic", None)
            })
        data["categories"].append(cat_obj)

    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    await ctx.send(
        f"💾 **Backup completo di `{guild.name}` salvato!**\n"
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
        await ctx.send("❌ Nessun file `backup_mine_roleplay.json` trovato! Caricalo nella cartella del bot o usa `!setup_mr`.")
        return

    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    guild = ctx.guild
    await ctx.send(f"🔄 **Ripristino di `{data['server_name']}` in corso...**")

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

    for r_data in reversed(data["roles"]):
        await guild.create_role(
            name=r_data["name"],
            colour=discord.Colour(r_data["color"]),
            hoist=r_data["hoist"],
            mentionable=r_data["mentionable"],
            permissions=discord.Permissions(r_data["permissions"])
        )
        await asyncio.sleep(0.3)

    for cat_data in data["categories"]:
        cat = await guild.create_category(name=cat_data["name"])
        await asyncio.sleep(0.35)
        for ch_data in cat_data["channels"]:
            if ch_data["type"] == "voice":
                await guild.create_voice_channel(name=ch_data["name"], category=cat)
            else:
                await guild.create_text_channel(name=ch_data["name"], category=cat, topic=ch_data.get("topic"))
            await asyncio.sleep(0.35)

    try:
        await ctx.channel.delete()
    except Exception:
        pass

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
