import os
import re
import math
import time
import random
import asyncio
import datetime
from threading import Thread
from typing import Optional, List, Dict, Any, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify
from supabase import create_client, Client

# ==============================================================================
# CONFIGURAZIONE & AMBIENTE
# ==============================================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
PORT = int(os.getenv("PORT", 10000))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Imposta SUPABASE_URL e SUPABASE_KEY nelle variabili d'ambiente.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

THEME_COLOR = 0xDC143C  # Crimson Red
ACCENT_COLOR = 0x111116
WIN_COLOR = 0x2ECC71
LOSE_COLOR = 0xE74C3C
DRAW_COLOR = 0xF1C40F

# ==============================================================================
# SERVER FLASK KEEP-ALIVE (RENDER / UPTIMEROBOT)
# ==============================================================================
flask_app = Flask(__name__)


@flask_app.route("/")
def index():
    return "⫷・═══ 𝐀𝐑𝐄𝐍𝐀 𝐌𝐈𝐍𝐈𝐆𝐀𝐌𝐄 𝐁𝐎𝐓 • 𝐎𝐍𝐋𝐈𝐍𝐄 ═══・⫸", 200


@flask_app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "games_count": len(GAMES_CATALOG),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }), 200


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ==============================================================================
# DATABASE SUPABASE HELPER
# ==============================================================================
def get_or_create_player(user_id: int, username: str) -> Dict[str, Any]:
    res = supabase.table("minigame_stats").select("*").eq("user_id", user_id).execute()
    if res.data:
        player = res.data[0]
        if player.get("username") != username:
            supabase.table("minigame_stats").update({"username": username}).eq("user_id", user_id).execute()
            player["username"] = username
        return player

    new_player = {
        "user_id": user_id,
        "username": username,
        "points": 100,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "pve_wins": 0,
        "pvp_wins": 0,
        "streak": 0,
        "best_streak": 0,
        "games_played": 0,
        "favorite_game": "Nessuno"
    }
    supabase.table("minigame_stats").insert(new_player).execute()
    return new_player


def record_match_result(
    user_id: int,
    username: str,
    outcome: str,  # "win", "loss", "draw"
    points_delta: int,
    mode: str,     # "PvE" o "PvP"
    game_name: str
) -> Dict[str, Any]:
    p = get_or_create_player(user_id, username)
    new_points = max(0, p["points"] + points_delta)
    wins = p["wins"] + (1 if outcome == "win" else 0)
    losses = p["losses"] + (1 if outcome == "loss" else 0)
    draws = p["draws"] + (1 if outcome == "draw" else 0)
    pve_wins = p["pve_wins"] + (1 if outcome == "win" and mode == "PvE" else 0)
    pvp_wins = p["pvp_wins"] + (1 if outcome == "win" and mode == "PvP" else 0)

    if outcome == "win":
        streak = p["streak"] + 1
    elif outcome == "loss":
        streak = 0
    else:
        streak = p["streak"]

    best_streak = max(p["best_streak"], streak)
    games_played = p["games_played"] + 1

    update_payload = {
        "username": username,
        "points": new_points,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "pve_wins": pve_wins,
        "pvp_wins": pvp_wins,
        "streak": streak,
        "best_streak": best_streak,
        "games_played": games_played,
        "favorite_game": game_name,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    supabase.table("minigame_stats").update(update_payload).eq("user_id", user_id).execute()
    p.update(update_payload)
    return p


def fetch_leaderboard_page(page: int = 1, per_page: int = 10) -> Tuple[List[Dict[str, Any]], int]:
    count_res = supabase.table("minigame_stats").select("user_id", count="exact").execute()
    total = count_res.count or 0
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page - 1

    data_res = (
        supabase.table("minigame_stats")
        .select("*")
        .order("points", desc=True)
        .order("wins", desc=True)
        .range(start, end)
        .execute()
    )
    return (data_res.data or []), total_pages


def get_player_rank(user_id: int) -> int:
    res = (
        supabase.table("minigame_stats")
        .select("user_id")
        .order("points", desc=True)
        .order("wins", desc=True)
        .execute()
    )
    for idx, row in enumerate(res.data or [], start=1):
        if row["user_id"] == user_id:
            return idx
    return 0


# ==============================================================================
# CATALOGO 54 MINIGAME (6 CATEGORIE x 9 GIOCHI)
# ==============================================================================
# Ogni entry: (id, nome, categoria, emoji, punti_base, engine, descrizione)
GAMES_CATALOG: List[Tuple[str, str, str, str, int, str, str]] = [
    # 1. STRATEGIA & GRIGLIA (9)
    ("tris", "Tris 3x3", "Strategia", "❌", 25, "grid_ttt", "Allinea 3 simboli sulla griglia 3x3."),
    ("forza4", "Forza 4", "Strategia", "🔴", 35, "grid_c4", "Fai cadere i gettoni e allineane 4."),
    ("battaglia_navale", "Battaglia Navale", "Strategia", "🚢", 40, "grid_battleship", "Affonda le 3 navi nemiche sulla mappa 5x5."),
    ("campo_minato", "Campo Minato Duel", "Strategia", "💣", 35, "grid_mines", "Scopri caselle sicure evitando le mine nascoste."),
    ("caccia_tesoro", "Caccia al Tesoro", "Strategia", "💎", 30, "grid_treasure", "Segui gli indizi caldo/freddo nella griglia 5x5."),
    ("nim", "Nim Bastoncini", "Strategia", "🥢", 30, "nim_engine", "Prendi 1, 2 o 3 bastoncini: chi prende l'ultimo perde."),
    ("reversi", "Mini Reversi 4x4", "Strategia", "⚫", 40, "grid_reversi", "Ribalta le pedine avversarie sulla scacchiera."),
    ("dama_lampo", "Conquista Settori", "Strategia", "♟️", 35, "grid_territory", "Conquista più caselle adiacenti dell'avversario."),
    ("torre_codice", "Mastermind Colori", "Strategia", "🔐", 45, "mastermind_engine", "Decifra la sequenza segreta di 4 simboli."),

    # 2. DUELLI & AZIONE TATTICA (9)
    ("morra_cinese", "Sasso Carta Forbice", "Duelli", "✂️", 20, "rps_classic", "Il classico duello psicologico a 3 mosse."),
    ("morra_estesa", "RPS Lizard Spock", "Duelli", "🖖", 25, "rps_spock", "5 mosse tattiche con combinazioni incrociate."),
    ("rigori", "Calci di Rigore", "Duelli", "⚽", 30, "duel_turns", "Sfida portiere contro tiratore su 3 tiri."),
    ("boxe", "Incontro di Boxe", "Duelli", "🥊", 35, "combat_hp", "Gestisci Jab, Gancio e Guardia sul ring."),
    ("scherma", "Duello di Scherma", "Duelli", "🤺", 35, "combat_hp", "Affondo, Parata o Finta: vince chi colpisce meglio."),
    ("arena_rpg", "Arena Gladiatori", "Duelli", "⚔️", 40, "combat_hp", "Spada, Scudo o Pozione Curativa nell'arena."),
    ("roulette_russa", "Roulette Tattica", "Duelli", "🔫", 45, "roulette_engine", "Spara, gira il tamburo o passa il turno."),
    ("western", "Duello Far West", "Duelli", "🤠", 35, "reflex_engine", "Aspetta il segnale FUOCO e spara per primo!"),
    ("dogfight", "Dogfight Aereo", "Duelli", "✈️", 35, "combat_hp", "Manovra in quota e aggancia il caccia nemico."),

    # 3. CASINÒ & CARTE (9)
    ("blackjack", "Blackjack 21", "Casinò", "🃏", 35, "blackjack_engine", "Avvicinati a 21 senza sballare contro il banco/rivale."),
    ("sette_mezzo", "Sette e Mezzo", "Casinò", "🎴", 35, "sette_mezzo_engine", "Il grande classico italiano con le figure da 0.5."),
    ("dadi_duello", "Duello 3d6", "Casinò", "🎲", 25, "dice_engine", "Lancia 3 dadi e rilancia quelli bassi."),
    ("high_low", "Carta Alta o Bassa", "Casinò", "📈", 25, "highlow_engine", "Indovina se la prossima carta sarà più alta o bassa."),
    ("corsa_cavalli", "Corsa dei Cavalli", "Casinò", "🏇", 30, "horse_engine", "Scegli il tuo cavallo e tifalo fino al traguardo."),
    ("slot_duel", "Slot Machine Duel", "Casinò", "🎰", 25, "slot_engine", "Gira i rulli e batti il punteggio avversario."),
    ("ruota_fortuna", "Ruota della Fortuna", "Casinò", "🎡", 30, "wheel_engine", "Gira la ruota moltiplicatore e sfida la sorte."),
    ("coin_streak", "Rischia o Incassa", "Casinò", "🪙", 30, "push_luck_engine", "Lancia la moneta: raddoppia o perdi tutto!"),
    ("pesca_bomba", "Pesca la Bomba", "Casinò", "🧨", 35, "bomb_card_engine", "Pesca carte punti evitando la carta bomba."),

    # 4. PAROLE & ENIGMI (9)
    ("impiccato", "Impiccato", "Parole", "🪢", 35, "hangman_engine", "Indovina la parola segreta lettera per lettera."),
    ("wordle", "Wordle 5 Lettere", "Parole", "🟩", 45, "wordle_engine", "Scopri la parola da 5 lettere in 6 tentativi."),
    ("anagramma", "Anagramma Lampo", "Parole", "🔤", 30, "scramble_engine", "Riordina le lettere mescolate nel minor tempo."),
    ("indovinello", "Enigma del Saggio", "Parole", "📜", 30, "quiz_engine", "Risolvi l'indovinello logico-letterario."),
    ("vero_falso", "Vero o Falso", "Parole", "⚖️", 20, "tf_engine", "Affermazioni assurde o reali: scegli subito."),
    ("citta_nazioni", "Geografia Capitale", "Parole", "🌍", 25, "quiz_engine", "Indovina la capitale esatta della nazione."),
    ("sinonimi", "Sfida Lessicale", "Parole", "📖", 25, "quiz_engine", "Trova il sinonimo corretto della parola."),
    ("morse", "Codice Morse", "Parole", "📡", 35, "morse_engine", "Decodifica il messaggio trasmesso in Morse."),
    ("proverbi", "Completa il Proverbio", "Parole", "🇮🇹", 25, "quiz_engine", "Completa il famoso proverbio italiano."),

    # 5. MATEMATICA & LOGICA (9)
    ("calcolo_lampo", "Calcolo Mentale", "Logica", "🧮", 25, "math_engine", "Risolvi operazioni aritmetiche al volo."),
    ("sequenza_logica", "Sequenza Numerica", "Logica", "🔢", 30, "math_engine", "Trova il numero successivo nella serie."),
    ("equazione_x", "Trova la X", "Logica", "✖️", 35, "math_engine", "Risolvi l'equazione di primo grado."),
    ("binario_hex", "Binario & Hex", "Logica", "💻", 40, "binary_engine", "Converti numeri binari ed esadecimali."),
    ("numero_segreto", "Indovina Numero 1-100", "Logica", "🎯", 30, "guess_num_engine", "Trova il numero segreto con indizi Più/Meno."),
    ("pari_dispari", "Pari o Dispari Pro", "Logica", "✌️", 20, "even_odd_engine", "Scegli un numero da 1 a 5 e indovina la somma."),
    ("percentuale", "Calcolo Percentuale", "Logica", "📊", 30, "math_engine", "Calcola rapidamente sconti e percentuali."),
    ("potenze_radici", "Potenze & Radici", "Logica", "📐", 35, "math_engine", "Quadrati, cubi e radici perfette."),
    ("logica_booleana", "Porte Logiche AND/OR", "Logica", "🔌", 35, "logic_gate_engine", "Valuta l'output di circuiti logici binari."),

    # 6. CULTURA, MEMORIA & RIFLESSI (9)
    ("trivia_gaming", "Quiz Gaming & Tech", "Cultura", "🎮", 25, "quiz_engine", "Domande su videogiochi, hardware e console."),
    ("trivia_calcio", "Quiz Calcio & Sport", "Cultura", "🏆", 25, "quiz_engine", "Serie A, Serie B, Mondiali e leggende dello sport."),
    ("trivia_scienza", "Quiz Scienza & Spazio", "Cultura", "🚀", 25, "quiz_engine", "Astronomia, fisica, chimica e scoperte."),
    ("trivia_cinema", "Quiz Cinema & Serie", "Cultura", "🎬", 25, "quiz_engine", "Film cult, registi e serie TV famose."),
    ("bandiere", "Indovina la Bandiera", "Cultura", "🏳️", 25, "flag_engine", "Riconosci lo Stato dalla sua bandiera."),
    ("trova_intruso", "Trova l'Intruso", "Cultura", "🕵️", 25, "odd_one_engine", "Individua l'elemento che non c'entra nulla."),
    ("memoria_emoji", "Simon Says Emoji", "Cultura", "🧠", 35, "simon_engine", "Memorizza la sequenza di emoji e ripetila."),
    ("memory_coppie", "Memory 4x3", "Cultura", "🃏", 35, "memory_engine", "Trova le coppie nascoste sulla griglia."),
    ("riflessi_semaforo", "Semaforo Verde", "Cultura", "🚦", 30, "reflex_engine", "Premi il pulsante appena diventa verde!"),
]

GAMES_BY_ID: Dict[str, Tuple[str, str, str, int, str, str]] = {
    g[0]: (g[1], g[2], g[3], g[4], g[5], g[6]) for g in GAMES_CATALOG
}

CATEGORIES = ["Strategia", "Duelli", "Casinò", "Parole", "Logica", "Cultura"]

# ==============================================================================
# BANCHE DATI DOMANDE / PAROLE / ENIGMI
# ==============================================================================
QUIZ_BANK: Dict[str, List[Tuple[str, List[str], int]]] = {
    "indovinello": [
        ("Più ne togli e più diventa grande. Cos'è?", ["Una buca", "Un debito", "Il silenzio", "Una nuvola"], 0),
        ("Ha città senza case, foreste senza alberi e fiumi senza acqua. Cos'è?", ["Un sogno", "Una mappa", "Un quadro", "Un libro"], 1),
        ("Cammina sempre senza avere piedi, piange senza avere occhi. Cos'è?", ["Il vento", "La nuvola", "Il tempo", "Il fiume"], 1),
        ("Se lo nomini sparisce. Cos'è?", ["Il segreto", "Il buio", "Il silenzio", "Il vento"], 2),
        ("Ha 13 cuori ma nessun altro organo. Cos'è?", ["Un polpo", "Un mazzo di carte", "Un robot", "Un orologio"], 1),
        ("Entra duro ed esce molle e bagnato. Cos'è?", ["Il pane", "Lo spaghetto", "Il ghiaccio", "Il sapone"], 1),
    ],
    "citta_nazioni": [
        ("Qual è la capitale dell'Australia?", ["Sydney", "Melbourne", "Canberra", "Perth"], 2),
        ("Qual è la capitale del Canada?", ["Toronto", "Ottawa", "Vancouver", "Montreal"], 1),
        ("Qual è la capitale del Brasile?", ["Rio de Janeiro", "San Paolo", "Brasilia", "Salvador"], 2),
        ("Qual è la capitale del Giappone?", ["Osaka", "Kyoto", "Tokyo", "Nagoya"], 2),
        ("Qual è la capitale della Norvegia?", ["Bergen", "Oslo", "Stoccolma", "Helsinki"], 1),
        ("Qual è la capitale dell'Islanda?", ["Reykjavik", "Nuuk", "Copenaghen", "Tallinn"], 0),
    ],
    "sinonimi": [
        ("Qual è un sinonimo di 'Effimero'?", ["Eterno", "Passeggero", "Pesante", "Luminoso"], 1),
        ("Qual è un sinonimo di 'Perspicace'?", ["Acuto", "Lento", "Distratto", "Timido"], 0),
        ("Qual è un sinonimo di 'Facondo'?", ["Silenzioso", "Eloquente", "Avaro", "Stanco"], 1),
        ("Qual è un sinonimo di 'Ostico'?", ["Facile", "Difficile", "Dolce", "Veloce"], 1),
        ("Qual è un sinonimo di 'Ineluttabile'?", ["Evitabile", "Inevitabile", "Invisibile", "Inutile"], 1),
    ],
    "proverbi": [
        ("Chi dorme...", ["non piglia pesci", "fa bei sogni", "non lavora", "si riposa"], 0),
        ("Tra i due litiganti...", ["vince il più forte", "il terzo gode", "scappa il quarto", "nessuno vince"], 1),
        ("L'abito non fa...", ["il sarto", "il monaco", "la festa", "il prezzo"], 1),
        ("A caval donato...", ["non si mette la sella", "non si guarda in bocca", "si dice grazie", "si dà biada"], 1),
        ("Il lupo perde il pelo ma...", ["non il vizio", "non i denti", "cambia bosco", "torna sempre"], 0),
    ],
    "trivia_gaming": [
        ("In che anno è uscito Grand Theft Auto V per la prima volta?", ["2011", "2013", "2015", "2012"], 1),
        ("Quale linguaggio è nativo per i plugin di Minecraft Java?", ["Python", "C#", "Java", "Lua"], 2),
        ("Chi è il creatore originale di Minecraft?", ["Gabe Newell", "Notch", "Hideo Kojima", "Todd Howard"], 1),
        ("Quale azienda produce le schede video GeForce RTX?", ["AMD", "Intel", "NVIDIA", "ASUS"], 2),
        ("Qual è il nome del protagonista di The Legend of Zelda?", ["Zelda", "Link", "Ganon", "Epona"], 1),
        ("In Counter-Strike, quanti secondi dura il timer della bomba C4?", ["30s", "40s", "45s", "60s"], 1),
    ],
    "trivia_calcio": [
        ("Quanti Mondiali di calcio ha vinto l'Italia?", ["3", "4", "5", "2"], 1),
        ("Chi ha vinto il Pallone d'Oro nel 2024?", ["Vinicius Jr", "Rodri", "Bellingham", "Haaland"], 1),
        ("In quale città gioca l'US Catanzaro 1929?", ["Cosenza", "Reggio Calabria", "Catanzaro", "Crotone"], 2),
        ("Quale squadra ha vinto più Champions League nella storia?", ["Milan", "Bayern Monaco", "Real Madrid", "Liverpool"], 2),
        ("Chi è il miglior marcatore all-time della Serie A?", ["Francesco Totti", "Silvio Piola", "Gunnar Nordahl", "Ciro Immobile"], 1),
    ],
    "trivia_scienza": [
        ("Qual è il pianeta più grande del Sistema Solare?", ["Saturno", "Giove", "Nettuno", "Urano"], 1),
        ("Qual è il simbolo chimico dell'Oro?", ["Ag", "Fe", "Au", "Or"], 2),
        ("A quanti km/s viaggia circa la luce nel vuoto?", ["300.000 km/s", "150.000 km/s", "30.000 km/s", "1.000.000 km/s"], 0),
        ("Qual è l'osso più lungo del corpo umano?", ["Tibia", "Omero", "Femore", "Radio"], 2),
        ("Quanti bit ci sono in un Byte?", ["4", "8", "16", "32"], 1),
    ],
    "trivia_cinema": [
        ("Chi ha diretto il film 'Inception' (2010)?", ["Steven Spielberg", "Christopher Nolan", "Quentin Tarantino", "Martin Scorsese"], 1),
        ("Qual è il vero nome di Heisenberg in Breaking Bad?", ["Jesse Pinkman", "Walter White", "Saul Goodman", "Hank Schrader"], 1),
        ("In 'Matrix', quale pillola sceglie Neo?", ["Blu", "Rossa", "Verde", "Gialla"], 1),
        ("Chi interpreta Tony Stark / Iron Man nel MCU?", ["Chris Evans", "Robert Downey Jr.", "Chris Hemsworth", "Mark Ruffalo"], 1),
    ],
}

TRUE_FALSE_BANK: List[Tuple[str, bool]] = [
    ("Il fulmine è più caldo della superficie del Sole.", True),
    ("Gli squali sono mammiferi marini.", False),
    ("La Grande Muraglia Cinese è visibile ad occhio nudo dalla Luna.", False),
    ("Il polpo ha tre cuori.", True),
    ("Venere ruota in senso opposto rispetto alla maggior parte dei pianeti.", True),
    ("In Python, una tupla è mutabile come una lista.", False),
    ("Il Monte Everest è la montagna più alta sopra il livello del mare.", True),
    ("L'acqua bolle a 100°C anche in cima all'Everest.", False),
]

WORDS_5: List[str] = [
    "PIZZA", "FUOCO", "MONDO", "TIGRE", "CUORE", "STELLA"[:5], "FORZA", "LAMPO",
    "SCUDO", "SPADA", "NOTTE", "CIELO", "VENTO", "FIUME", "PIANO", "TRENO",
    "PORTA", "LIBRO", "SOGNO", "OMBRA", "LUPIN"[:5], "DRAGO", "TORRE", "REALE"
]

WORDS_HANGMAN: List[str] = [
    "ALGORITMO", "ASTRONAVE", "LABIRINTO", "GLADIATORE", "TEMPESTA",
    "DIAMANTE", "VULCANO", "ORIZZONTE", "SERVER", "DISCORD", "CALABRIA", "CAMPIONE"
]

FLAGS_BANK: List[Tuple[str, str, List[str]]] = [
    ("🇯🇵", "Giappone", ["Cina", "Giappone", "Corea del Sud", "Vietnam"]),
    ("🇧🇷", "Brasile", ["Argentina", "Portogallo", "Brasile", "Colombia"]),
    ("🇨🇦", "Canada", ["Canada", "Svizzera", "Austria", "Danimarca"]),
    ("🇦🇷", "Argentina", ["Uruguay", "Argentina", "Grecia", "Honduras"]),
    ("🇸🇪", "Svezia", ["Finlandia", "Norvegia", "Svezia", "Ucraina"]),
    ("🇰🇷", "Corea del Sud", ["Giappone", "Corea del Sud", "Taiwan", "Mongolia"]),
    ("🇲🇽", "Messico", ["Italia", "Irlanda", "Messico", "Ungheria"]),
    ("🇳🇴", "Norvegia", ["Islanda", "Norvegia", "Danimarca", "Svezia"]),
]

ODD_ONE_BANK: List[Tuple[List[str], int, str]] = [
    (["Python", "Java", "HTML", "C++"], 2, "HTML è un linguaggio di markup, gli altri sono di programmazione."),
    (["Marte", "Giove", "Luna", "Saturno"], 2, "La Luna è un satellite naturale, gli altri sono pianeti."),
    (["Ferrari", "Lamborghini", "Ducati", "Maserati"], 2, "Ducati produce moto, gli altri sono marchi automobilistici."),
    (["Tastiera", "Mouse", "Monitor", "Scanner"], 2, "Il Monitor è una periferica di output, gli altri sono di input."),
    (["Calcio", "Basket", "Tennis", "Nuoto"], 3, "Il Nuoto non usa una palla."),
]

MORSE_MAP: Dict[str, str] = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--.."
}

# ==============================================================================
# UTILITÀ EMBED
# ==============================================================================
def make_embed(title: str, description: str, color: int = THEME_COLOR) -> discord.Embed:
    embed = discord.Embed(
        title=f"⫷・═══ {title} ═══・⫸",
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.set_footer(text="𝐀𝐑𝐄𝐍𝐀 𝐌𝐈𝐍𝐈𝐆𝐀𝐌𝐄 • 𝐏𝐯𝐏 & 𝐏𝐯𝐄 𝐒𝐘𝐒𝐓𝐄𝐌")
    return embed


async def finalize_game(
    interaction: discord.Interaction,
    game_id: str,
    mode: str,
    p1: discord.User,
    p2: Optional[discord.User],
    winner: Optional[int],  # 1 = p1, 2 = p2/bot, 0 = draw
    summary: str,
    view: Optional[discord.ui.View] = None
):
    g_name, _, g_emoji, base_pts, _, _ = GAMES_BY_ID[game_id]
    p2_name = p2.display_name if p2 else "🤖 Bot IA"

    # In PvE i punti guadagnati sono ridotti al 50% (minimo 3 pt) per evitare farm facile
    earned_pts = base_pts if mode == "PvP" else max(3, int(round(base_pts * 0.2)))
    lost_pts = max(5, earned_pts // 2)

    if winner == 1:
        s1 = record_match_result(p1.id, p1.display_name, "win", earned_pts, mode, g_name)
        if p2:
            record_match_result(p2.id, p2.display_name, "loss", -lost_pts, mode, g_name)
        res_text = (
            f"🏆 **VINCITORE:** {p1.mention} (`+{earned_pts} pt`)\n"
            f"💀 **SCONFITTO:** {p2.mention if p2 else p2_name}\n"
            f"🔥 **Serie Vittorie:** `{s1['streak']}` • **Totale Punti:** `{s1['points']}`"
        )
        color = WIN_COLOR
    elif winner == 2:
        record_match_result(p1.id, p1.display_name, "loss", -lost_pts, mode, g_name)
        if p2:
            s2 = record_match_result(p2.id, p2.display_name, "win", earned_pts, mode, g_name)
            extra = f" (`+{earned_pts} pt` | Totale: `{s2['points']}`)"
        else:
            extra = " (IA Competitiva)"
        res_text = (
            f"🏆 **VINCITORE:** {p2.mention if p2 else p2_name}{extra}\n"
            f"💀 **SCONFITTO:** {p1.mention} (`-{lost_pts} pt`)"
        )
        color = LOSE_COLOR
    else:
        draw_pts = max(2, earned_pts // 4)
        record_match_result(p1.id, p1.display_name, "draw", draw_pts, mode, g_name)
        if p2:
            record_match_result(p2.id, p2.display_name, "draw", draw_pts, mode, g_name)
        res_text = f"🤝 **PAREGGIO!** Entrambi guadagnano `+{draw_pts} pt`."
        color = DRAW_COLOR

    if view:
        for item in view.children:
            item.disabled = True

    embed = make_embed(f"{g_emoji} {g_name.upper()} • FINE PARTITA", f"{summary}\n\n{res_text}", color)
    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.edit_message(embed=embed, view=view)



# ==============================================================================
# ENGINE 1: TRIS 3x3 (PvP & PvE Intelligente + Variabilità)
# ==============================================================================
class TicTacToeButton(discord.ui.Button):
    def __init__(self, idx: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="⬜", row=idx // 3)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view
        await view.handle_move(interaction, self.idx)


class TicTacToeView(discord.ui.View):
    def __init__(self, p1: discord.User, p2: Optional[discord.User]):
        super().__init__(timeout=180)
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.board = [0] * 9
        self.turn = 1
        for i in range(9):
            self.add_item(TicTacToeButton(i))

    def check_winner(self) -> Optional[int]:
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a, b, c in wins:
            if self.board[a] != 0 and self.board[a] == self.board[b] == self.board[c]:
                return self.board[a]
        if 0 not in self.board:
            return 0
        return None

    def bot_move(self) -> int:
        empty = [i for i, v in enumerate(self.board) if v == 0]
        # 70% mossa tattica (vince o blocca), 30% mossa creativa/casuale per non essere identico
        if random.random() < 0.72:
            for target in (2, 1):
                for idx in empty:
                    self.board[idx] = target
                    if self.check_winner() == target:
                        self.board[idx] = 0
                        return idx
                    self.board[idx] = 0
        return random.choice(empty)

    async def handle_move(self, interaction: discord.Interaction, idx: int):
        expected = self.p1.id if self.turn == 1 else (self.p2.id if self.p2 else -1)
        if interaction.user.id != expected:
            return await interaction.response.send_message("❌ Non è il tuo turno!", ephemeral=True)
        if self.board[idx] != 0:
            return await interaction.response.send_message("❌ Casella già occupata!", ephemeral=True)

        self.board[idx] = self.turn
        btn: TicTacToeButton = self.children[idx]
        btn.label = "❌" if self.turn == 1 else "⭕"
        btn.style = discord.ButtonStyle.danger if self.turn == 1 else discord.ButtonStyle.primary
        btn.disabled = True

        w = self.check_winner()
        if w is not None:
            return await finalize_game(interaction, "tris", self.mode, self.p1, self.p2, w, "Partita conclusa sulla griglia 3x3!", self)

        if self.mode == "PvE":
            b_idx = self.bot_move()
            self.board[b_idx] = 2
            b_btn: TicTacToeButton = self.children[b_idx]
            b_btn.label = "⭕"
            b_btn.style = discord.ButtonStyle.primary
            b_btn.disabled = True
            w2 = self.check_winner()
            if w2 is not None:
                return await finalize_game(interaction, "tris", "PvE", self.p1, None, w2, "Duello contro l'IA concluso!", self)
            embed = make_embed("❌ TRIS 3X3 • PVE", f"Tocca a {self.p1.mention} (`❌`) contro 🤖 **Bot IA** (`⭕`).")
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.turn = 2 if self.turn == 1 else 1
            curr = self.p1 if self.turn == 1 else self.p2
            sym = "❌" if self.turn == 1 else "⭕"
            embed = make_embed("❌ TRIS 3X3 • PVP", f"Turno di {curr.mention} (`{sym}`).")
            await interaction.response.edit_message(embed=embed, view=self)


# ==============================================================================
# ENGINE 2: FORZA 4 (5x5 / 6x5 COMPATTO PER DISCORD)
# ==============================================================================
class Connect4Button(discord.ui.Button):
    def __init__(self, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=f"{col+1}️⃣", row=0)
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        await self.view.drop_piece(interaction, self.col)


class Connect4View(discord.ui.View):
    ROWS = 5
    COLS = 5

    def __init__(self, p1: discord.User, p2: Optional[discord.User]):
        super().__init__(timeout=240)
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.grid = [[0] * self.COLS for _ in range(self.ROWS)]
        self.turn = 1
        for c in range(self.COLS):
            self.add_item(Connect4Button(c))

    def render_board(self) -> str:
        icons = {0: "⚫", 1: "🔴", 2: "🟡"}
        lines = ["".join(icons[cell] for cell in row) for row in self.grid]
        lines.append("1️⃣2️⃣3️⃣4️⃣5️⃣")
        return "\n".join(lines)

    def can_drop(self, col: int) -> int:
        for r in range(self.ROWS - 1, -1, -1):
            if self.grid[r][col] == 0:
                return r
        return -1

    def check_win(self, player: int) -> bool:
        for r in range(self.ROWS):
            for c in range(self.COLS):
                for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
                    cnt = 0
                    for k in range(4):
                        nr, nc = r + dr*k, c + dc*k
                        if 0 <= nr < self.ROWS and 0 <= nc < self.COLS and self.grid[nr][nc] == player:
                            cnt += 1
                    if cnt == 4:
                        return True
        return False

    def is_full(self) -> bool:
        return all(self.grid[0][c] != 0 for c in range(self.COLS))

    def bot_choose_col(self) -> int:
        valid = [c for c in range(self.COLS) if self.can_drop(c) != -1]
        for target in (2, 1):
            for c in valid:
                r = self.can_drop(c)
                self.grid[r][c] = target
                won = self.check_win(target)
                self.grid[r][c] = 0
                if won and random.random() < 0.8:
                    return c
        return random.choice(valid)

    async def drop_piece(self, interaction: discord.Interaction, col: int):
        expected = self.p1.id if self.turn == 1 else (self.p2.id if self.p2 else -1)
        if interaction.user.id != expected:
            return await interaction.response.send_message("❌ Non è il tuo turno!", ephemeral=True)

        row = self.can_drop(col)
        if row == -1:
            return await interaction.response.send_message("❌ Colonna piena!", ephemeral=True)

        self.grid[row][col] = self.turn
        if self.check_win(self.turn):
            return await finalize_game(interaction, "forza4", self.mode, self.p1, self.p2, self.turn, self.render_board(), self)
        if self.is_full():
            return await finalize_game(interaction, "forza4", self.mode, self.p1, self.p2, 0, self.render_board(), self)

        if self.mode == "PvE":
            bc = self.bot_choose_col()
            br = self.can_drop(bc)
            self.grid[br][bc] = 2
            if self.check_win(2):
                return await finalize_game(interaction, "forza4", "PvE", self.p1, None, 2, self.render_board(), self)
            if self.is_full():
                return await finalize_game(interaction, "forza4", "PvE", self.p1, None, 0, self.render_board(), self)
            embed = make_embed("🔴 FORZA 4 • PVE", f"{self.render_board()}\n\nTocca a {self.p1.mention} (`🔴`).")
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.turn = 2 if self.turn == 1 else 1
            curr = self.p1 if self.turn == 1 else self.p2
            sym = "🔴" if self.turn == 1 else "🟡"
            embed = make_embed("🔴 FORZA 4 • PVP", f"{self.render_board()}\n\nTocca a {curr.mention} (`{sym}`).")
            await interaction.response.edit_message(embed=embed, view=self)


# ==============================================================================
# ENGINE 3: DUELLI SIMULTANEI / A TURNI (MORRA, RIGORI, BOXE, SCHERMA, RPG, ROULETTE)
# ==============================================================================
class SimultaneousChoiceView(discord.ui.View):
    def __init__(self, game_id: str, p1: discord.User, p2: Optional[discord.User], options: List[Tuple[str, str]]):
        super().__init__(timeout=120)
        self.game_id = game_id
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.options = options
        self.choices: Dict[int, str] = {}
        self.hp = {1: 100, 2: 100}
        self.round_num = 1

        for idx, (label, emoji) in enumerate(options):
            btn = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary, row=idx // 3)
            btn.callback = self.make_callback(label)
            self.add_item(btn)

    def make_callback(self, choice_label: str):
        async def cb(interaction: discord.Interaction):
            uid = interaction.user.id
            valid_ids = [self.p1.id] + ([self.p2.id] if self.p2 else [])
            if uid not in valid_ids:
                return await interaction.response.send_message("❌ Non partecipi a questo duello!", ephemeral=True)

            self.choices[uid] = choice_label
            if self.mode == "PvE":
                bot_choice = random.choice([o[0] for o in self.options])
                await self.resolve_round(interaction, choice_label, bot_choice)
            else:
                if len(self.choices) < 2:
                    await interaction.response.send_message(f"✅ Hai scelto **{choice_label}**! In attesa dell'avversario...", ephemeral=True)
                else:
                    c1 = self.choices[self.p1.id]
                    c2 = self.choices[self.p2.id]
                    self.choices.clear()
                    await self.resolve_round(interaction, c1, c2)
        return cb

    async def resolve_round(self, interaction: discord.Interaction, c1: str, c2: str):
        g_name, _, g_emoji, _, engine, _ = GAMES_BY_ID[self.game_id]
        p2_name = self.p2.display_name if self.p2 else "🤖 Bot IA"

        # Logica Morra Classica & Spock
        if engine in ("rps_classic", "rps_spock"):
            beats = {
                "Sasso": ["Forbice", "Lizard"],
                "Carta": ["Sasso", "Spock"],
                "Forbice": ["Carta", "Lizard"],
                "Lizard": ["Spock", "Carta"],
                "Spock": ["Forbice", "Sasso"],
            }
            if c1 == c2:
                w = 0
                desc = f"Entrambi avete scelto **{c1}**!"
            elif c2 in beats.get(c1, []):
                w = 1
                desc = f"**{self.p1.display_name}** (`{c1}`) batte **{p2_name}** (`{c2}`)!"
            else:
                w = 2
                desc = f"**{p2_name}** (`{c2}`) batte **{self.p1.display_name}** (`{c1}`)!"
            return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, w, desc, self)

        # Logica Rigori
        if engine == "duel_turns":
            if c1 == c2:
                w = 2
                desc = f"🧤 **PARATA!** Il portiere ({p2_name}) indovina l'angolo **{c2}** e para il tiro di {self.p1.display_name}!"
            else:
                w = 1
                desc = f"⚽ **GOOOOL!** {self.p1.display_name} calcia a **{c1}** mentre {p2_name} si tuffa a **{c2}**!"
            return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, w, desc, self)

        # Logica Combattimento HP (Boxe, Scherma, Arena RPG, Dogfight)
        dmg_map = {
            "Attacco Rapido": (25, 10), "Colpo Pesante": (45, 0), "Guardia": (5, 30),
            "Affondo": (35, 5), "Finta": (30, 15), "Parata": (0, 35),
            "Spada": (35, 5), "Scudo": (5, 30), "Pozione": (-20, 15),
            "Mitraglia": (30, 10), "Missile": (50, 0), "Virata Evita": (0, 40)
        }
        atk1, def1 = dmg_map.get(c1, (25, 10))
        atk2, def2 = dmg_map.get(c2, (25, 10))

        if atk1 < 0:
            self.hp[1] = min(100, self.hp[1] - atk1)
        else:
            self.hp[2] = max(0, self.hp[2] - max(5, atk1 - def2 // 2))

        if atk2 < 0:
            self.hp[2] = min(100, self.hp[2] - atk2)
        else:
            self.hp[1] = max(0, self.hp[1] - max(5, atk2 - def1 // 2))

        log = (
            f"**Round {self.round_num}**\n"
            f"• {self.p1.display_name}: **{c1}** → ❤️ `{self.hp[1]} HP`\n"
            f"• {p2_name}: **{c2}** → ❤️ `{self.hp[2]} HP`"
        )
        self.round_num += 1

        if self.hp[1] <= 0 or self.hp[2] <= 0 or self.round_num > 5:
            if self.hp[1] > self.hp[2]:
                w = 1
            elif self.hp[2] > self.hp[1]:
                w = 2
            else:
                w = 0
            return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, w, log, self)

        embed = make_embed(f"{g_emoji} {g_name.upper()} • {self.mode}", f"{log}\n\nScegli la prossima mossa!")
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ==============================================================================
# ENGINE 4: CASINÒ & CARTE (BLACKJACK, SETTE E MEZZO, DADI, HIGH-LOW, CAVALLI, SLOT, RUOTA, MONETA, BOMBA)
# ==============================================================================
class CasinoDuelView(discord.ui.View):
    def __init__(self, game_id: str, p1: discord.User, p2: Optional[discord.User]):
        super().__init__(timeout=180)
        self.game_id = game_id
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.turn = 1
        self.scores = {1: 0.0, 2: 0.0}
        self.done = {1: False, 2: False}
        self.current_card = random.randint(2, 12)

        engine = GAMES_BY_ID[game_id][4]
        if engine in ("blackjack_engine", "sette_mezzo_engine"):
            self.scores[1] = self.draw_card()
            self.scores[2] = self.draw_card()
            self.add_action("Carta", "🃏", discord.ButtonStyle.success)
            self.add_action("Stai", "🛑", discord.ButtonStyle.danger)
        elif engine == "highlow_engine":
            self.add_action("Più Alta", "⬆️", discord.ButtonStyle.success)
            self.add_action("Più Bassa", "⬇️", discord.ButtonStyle.primary)
            self.add_action("Incassa", "💰", discord.ButtonStyle.secondary)
        elif engine == "push_luck_engine":
            self.scores = {1: 10.0, 2: 10.0}
            self.add_action("Lancia Moneta (2x)", "🪙", discord.ButtonStyle.success)
            self.add_action("Incassa Punti", "🏦", discord.ButtonStyle.primary)
        elif engine == "bomb_card_engine":
            self.bombs = set(random.sample(range(9), 2))
            for i in range(9):
                b = discord.ui.Button(label="🎴", style=discord.ButtonStyle.secondary, row=i // 3)
                b.callback = self.make_bomb_cb(i)
                self.add_item(b)
        else:
            self.add_action("Lancia / Gira", "🎲", discord.ButtonStyle.success)

    def draw_card(self) -> float:
        engine = GAMES_BY_ID[self.game_id][4]
        if engine == "blackjack_engine":
            return float(random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]))
        return float(random.choice([1, 2, 3, 4, 5, 6, 7, 0.5, 0.5, 0.5]))

    def add_action(self, label: str, emoji: str, style: discord.ButtonStyle):
        btn = discord.ui.Button(label=label, emoji=emoji, style=style)
        btn.callback = self.make_action_cb(label)
        self.add_item(btn)

    def make_bomb_cb(self, idx: int):
        async def cb(interaction: discord.Interaction):
            expected = self.p1.id if self.turn == 1 else (self.p2.id if self.p2 else -1)
            if interaction.user.id != expected:
                return await interaction.response.send_message("❌ Non è il tuo turno!", ephemeral=True)

            btn = self.children[idx]
            btn.disabled = True
            if idx in self.bombs:
                btn.label = "💥"
                btn.style = discord.ButtonStyle.danger
                winner = 2 if self.turn == 1 else 1
                return await finalize_game(
                    interaction,
                    self.game_id,
                    self.mode,
                    self.p1,
                    self.p2,
                    winner,
                    f"💥 **{interaction.user.display_name}** ha pescato la bomba!",
                    self
                )

            pts = random.choice([10, 15, 20, 25])
            self.scores[self.turn] += pts
            btn.label = f"+{pts}"
            btn.style = discord.ButtonStyle.success

            if self.mode == "PvE":
                avail = [i for i, c in enumerate(self.children) if not c.disabled]
                if avail:
                    bi = random.choice(avail)
                    bb = self.children[bi]
                    bb.disabled = True
                    if bi in self.bombs:
                        bb.label = "💥"
                        bb.style = discord.ButtonStyle.danger
                        return await finalize_game(
                            interaction,
                            self.game_id,
                            "PvE",
                            self.p1,
                            None,
                            1,
                            "🤖 Il Bot IA ha pescato la **BOMBA**! Hai vinto!",
                            self
                        )
                    b_pts = random.choice([10, 15, 20])
                    self.scores[2] += b_pts
                    bb.label = f"+{b_pts}"
                    bb.style = discord.ButtonStyle.primary

            rem = [c for c in self.children if not c.disabled]
            if len(rem) <= 2:
                w = 1 if self.scores[1] > self.scores[2] else (2 if self.scores[2] > self.scores[1] else 0)
                return await finalize_game(
                    interaction,
                    self.game_id,
                    self.mode,
                    self.p1,
                    self.p2,
                    w,
                    f"Punteggi finali: **{int(self.scores[1])}** vs **{int(self.scores[2])}**",
                    self
                )

            if self.mode == "PvP":
                self.turn = 2 if self.turn == 1 else 1
            curr = self.p1 if self.turn == 1 else self.p2
            embed = make_embed(
                "🧨 PESCA LA BOMBA",
                f"Punti: **{int(self.scores[1])}** vs **{int(self.scores[2])}**\nTocca a {curr.mention}!"
            )
            await interaction.response.edit_message(embed=embed, view=self)
        return cb

    def make_action_cb(self, action: str):
        async def cb(interaction: discord.Interaction):
            expected = self.p1.id if self.turn == 1 else (self.p2.id if self.p2 else -1)
            if interaction.user.id != expected:
                return await interaction.response.send_message("❌ Non è il tuo turno!", ephemeral=True)

            g_name, _, g_emoji, _, engine, _ = GAMES_BY_ID[self.game_id]
            limit = 21.0 if engine == "blackjack_engine" else 7.5

            if engine in ("blackjack_engine", "sette_mezzo_engine"):
                if action == "Carta":
                    self.scores[self.turn] += self.draw_card()
                    if self.scores[self.turn] > limit:
                        winner = 2 if self.turn == 1 else 1
                        return await finalize_game(
                            interaction,
                            self.game_id,
                            self.mode,
                            self.p1,
                            self.p2,
                            winner,
                            f"💥 **{interaction.user.display_name}** ha sballato con `{self.scores[self.turn]}` (limite `{limit}`).",
                            self
                        )
                else:
                    self.done[self.turn] = True

                if self.mode == "PvE" and self.done[1]:
                    while self.scores[2] < (limit - random.choice([2.5, 3.5, 4.0])):
                        self.scores[2] += self.draw_card()
                    if self.scores[2] > limit:
                        return await finalize_game(
                            interaction,
                            self.game_id,
                            "PvE",
                            self.p1,
                            None,
                            1,
                            f"🤖 Il Bot IA ha sballato con `{self.scores[2]}`! Tu avevi `{self.scores[1]}`.",
                            self
                        )
                    w = 1 if self.scores[1] > self.scores[2] else (2 if self.scores[2] > self.scores[1] else 0)
                    return await finalize_game(
                        interaction,
                        self.game_id,
                        "PvE",
                        self.p1,
                        None,
                        w,
                        f"Tu: `{self.scores[1]}` • 🤖 Bot IA: `{self.scores[2]}`",
                        self
                    )

                if self.mode == "PvP":
                    if self.done[1] and self.done[2]:
                        w = 1 if self.scores[1] > self.scores[2] else (2 if self.scores[2] > self.scores[1] else 0)
                        return await finalize_game(
                            interaction,
                            self.game_id,
                            "PvP",
                            self.p1,
                            self.p2,
                            w,
                            f"{self.p1.display_name}: `{self.scores[1]}` • {self.p2.display_name}: `{self.scores[2]}`",
                            self
                        )
                    other = 2 if self.turn == 1 else 1
                    if not self.done[other]:
                        self.turn = other

                curr = self.p1 if self.turn == 1 else self.p2
                p2_label = self.p2.display_name if self.p2 else "Bot IA"
                embed = make_embed(
                    f"{g_emoji} {g_name.upper()} • {self.mode}",
                    f"• **{self.p1.display_name}:** `{self.scores[1]}`\n"
                    f"• **{p2_label}:** `{self.scores[2] if self.mode == 'PvP' else '?'}`\n\n"
                    f"Tocca a {curr.mention}!"
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            # High-Low (Carta Alta o Bassa)
            if engine == "highlow_engine" and action != "Incassa":
                nxt = random.randint(1, 13)
                ok = (action == "Più Alta" and nxt >= self.current_card) or (action == "Più Bassa" and nxt <= self.current_card)
                if not ok:
                    winner = 2 if self.turn == 1 else 1
                    return await finalize_game(
                        interaction,
                        self.game_id,
                        self.mode,
                        self.p1,
                        self.p2,
                        winner,
                        f"❌ Uscito **{nxt}** (era **{self.current_card}**). **{interaction.user.display_name}** perde!",
                        self
                    )
                self.current_card = nxt
                self.scores[self.turn] += 20
                curr = self.p1 if self.turn == 1 else self.p2
                embed = make_embed(
                    "📈 CARTA ALTA O BASSA",
                    f"Nuova carta: **{self.current_card}**\nPunti {curr.mention}: `{int(self.scores[self.turn])}`"
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            # Rischia o Incassa (Coin Streak)
            if engine == "push_luck_engine" and action != "Incassa Punti":
                if random.random() < 0.45:
                    winner = 2 if self.turn == 1 else 1
                    return await finalize_game(
                        interaction,
                        self.game_id,
                        self.mode,
                        self.p1,
                        self.p2,
                        winner,
                        f"💀 **CROCE!** {interaction.user.display_name} perde tutto!",
                        self
                    )
                self.scores[self.turn] *= 2
                curr = self.p1 if self.turn == 1 else self.p2
                embed = make_embed(
                    "🪙 RISCHIA O INCASSA",
                    f"✨ **TESTA!** Montepremi {curr.mention}: `{int(self.scores[self.turn])} pt`"
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            # Turno singolo PvP/PvE per Dadi, Slot, Cavalli, Ruota o Incasso
            if self.scores[self.turn] <= 10:
                self.scores[self.turn] = float(random.randint(15, 100))

            if self.mode == "PvP" and self.turn == 1:
                self.turn = 2
                self.current_card = random.randint(2, 12)
                embed = make_embed(
                    f"{g_emoji} {g_name.upper()} • PVP",
                    f"✅ **{self.p1.display_name}** ha totalizzato `{int(self.scores[1])} pt`!\n\nOra tocca a {self.p2.mention}!"
                )
                return await interaction.response.edit_message(embed=embed, view=self)

            if self.mode == "PvE":
                self.scores[2] = float(random.randint(15, 100))

            s1, s2 = int(self.scores[1]), int(self.scores[2])
            w = 1 if s1 > s2 else (2 if s2 > s1 else 0)
            p2_n = self.p2.display_name if self.p2 else "🤖 Bot IA"
            await finalize_game(
                interaction,
                self.game_id,
                self.mode,
                self.p1,
                self.p2,
                w,
                f"🎲 **{self.p1.display_name}:** `{s1}` pts\n🎲 **{p2_n}:** `{s2}` pts",
                self
            )

        return cb

# ==============================================================================
# ENGINE 5: QUIZ, MATEMATICA, BANDIERE, INTRUSO, BINARIO, LOGICA (MULTI-CHOICE)
# ==============================================================================
class MultiChoiceView(discord.ui.View):
    def __init__(
        self,
        game_id: str,
        p1: discord.User,
        p2: Optional[discord.User],
        question: str,
        choices: List[str],
        correct_idx: int
    ):
        super().__init__(timeout=90)
        self.game_id = game_id
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.question = question
        self.choices = choices
        self.correct_idx = correct_idx

        for idx, text in enumerate(choices):
            btn = discord.ui.Button(label=str(text)[:80], style=discord.ButtonStyle.secondary, row=idx // 2)
            btn.callback = self.make_answer_cb(idx)
            self.add_item(btn)

     def make_answer_cb(self, idx: int):
        async def cb(interaction: discord.Interaction):
            valid_ids = [self.p1.id] + ([self.p2.id] if self.p2 else [])
            if interaction.user.id not in valid_ids:
                return await interaction.response.send_message("❌ Non sei in questa sfida!", ephemeral=True)

            is_p1 = interaction.user.id == self.p1.id
            player_correct = (idx == self.correct_idx)
            right_text = self.choices[self.correct_idx]

            if self.mode == "PvE":
                bot_correct = random.random() < 0.65
                if player_correct and not bot_correct:
                    winner = 1
                    desc = f"✅ Hai risposto correttamente (**{right_text}**), mentre il Bot IA ha sbagliato!"
                elif bot_correct and not player_correct:
                    winner = 2
                    desc = f"❌ Hai risposto `{self.choices[idx]}` e il **Bot IA** ha indovinato (**{right_text}**)!"
                elif player_correct and bot_correct:
                    winner = 1 if random.random() < 0.55 else 2
                    who = "Tu" if winner == 1 else "Il Bot IA"
                    desc = f"⚡ Entrambi avete risposto **{right_text}**, ma **{who}** è stato più rapido!"
                else:
                    winner = 0
                    desc = f"❌ Nessuno ha indovinato! La risposta corretta era **{right_text}**."
                return await finalize_game(interaction, self.game_id, "PvE", self.p1, None, winner, desc, self)

            if player_correct:
                winner = 1 if is_p1 else 2
                desc = f"✅ **{interaction.user.display_name}** ha risposto per primo correttamente: **{right_text}**!"
            else:
                winner = 2 if is_p1 else 1
                desc = f"❌ **{interaction.user.display_name}** ha sbagliato (`{self.choices[idx]}`)! La risposta era **{right_text}**."

            await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, winner, desc, self)
        return cb

def build_question_payload(game_id: str) -> Tuple[str, List[str], int]:
    engine = GAMES_BY_ID[game_id][4]

    if engine == "quiz_engine":
        bank = QUIZ_BANK.get(game_id, QUIZ_BANK["trivia_gaming"])
        return random.choice(bank)

    if engine == "tf_engine":
        stmt, ans = random.choice(TRUE_FALSE_BANK)
        return f"Affermazione:\n> *{stmt}*", ["✅ VERO", "❌ FALSO"], 0 if ans else 1

    if engine == "flag_engine":
        flag, country, opts = random.choice(FLAGS_BANK)
        return f"A quale nazione appartiene questa bandiera?\n# {flag}", opts, opts.index(country)

    if engine == "odd_one_engine":
        items, idx, _ = random.choice(ODD_ONE_BANK)
        return "Qual è l'intruso tra questi 4 elementi?", items, idx

    if engine == "morse_engine":
        word = random.choice(["SOS", "CIAO", "BOT", "PRO", "VIP", "KING"])
        encoded = " ".join(MORSE_MAP[ch] for ch in word)
        distractors = random.sample(["ALFA", "BETA", "LUNA", "SOLE", "RETE", "CODE"], 3)
        opts = distractors + [word]
        random.shuffle(opts)
        return f"Decodifica questo segnale Morse:\n`{encoded}`", opts, opts.index(word)

    if engine == "binary_engine":
        num = random.randint(10, 63)
        if random.choice([True, False]):
            q = f"Converti il binario `{bin(num)[2:]}` in decimale:"
            ans = str(num)
            wrongs = [str(num + 2), str(num - 1), str(num + 4)]
        else:
            q = f"Converti il decimale `{num}` in esadecimale (HEX):"
            ans = hex(num)[2:].upper()
            wrongs = [hex(num + 1)[2:].upper(), hex(num - 2)[2:].upper(), hex(num + 3)[2:].upper()]
        opts = wrongs + [ans]
        random.shuffle(opts)
        return q, opts, opts.index(ans)

    if engine == "logic_gate_engine":
        a, b = random.randint(0, 1), random.randint(0, 1)
        gate = random.choice(["AND", "OR", "XOR", "NAND"])
        res = {
            "AND": a & b,
            "OR": a | b,
            "XOR": a ^ b,
            "NAND": 1 - (a & b)
        }[gate]
        return f"Qual è l'output di `{a} {gate} {b}`?", ["0", "1"], res

    # Matematica & Sequenze
    if game_id == "sequenza_logica":
        step = random.randint(3, 9)
        start = random.randint(2, 15)
        seq = [start + step * i for i in range(4)]
        ans = str(start + step * 4)
        opts = [ans, str(int(ans) + step), str(int(ans) - 2), str(int(ans) + 1)]
        random.shuffle(opts)
        return f"Completa la sequenza:\n`{seq[0]}, {seq[1]}, {seq[2]}, {seq[3]}, ?`", opts, opts.index(ans)

    if game_id == "equazione_x":
        x = random.randint(3, 15)
        a = random.randint(2, 6)
        b = random.randint(1, 20)
        c = a * x + b
        ans = str(x)
        opts = [ans, str(x + 1), str(x - 1), str(x + 3)]
        random.shuffle(opts)
        return f"Risolvi per `x`:\n`{a}x + {b} = {c}`", opts, opts.index(ans)

    a, b = random.randint(12, 48), random.randint(7, 29)
    ans = str(a * b if game_id == "potenze_radici" else a + b * 2)
    q = f"Quanto fa `{a} × {b}`?" if game_id == "potenze_radici" else f"Calcola al volo:\n`{a} + ({b} × 2)`"
    opts = [ans, str(int(ans) + 4), str(int(ans) - 6), str(int(ans) + 10)]
    random.shuffle(opts)
    return q, opts, opts.index(ans)


# ==============================================================================
# ENGINE 6: PAROLE INTERATTIVE (IMPICCATO, WORDLE, ANAGRAMMA) & NIM / RIFLESSI
# ==============================================================================
class WordGuessModal(discord.ui.Modal, title="Inserisci la tua risposta"):
    guess = discord.ui.TextInput(label="Parola o Lettera", min_length=1, max_length=20)

    def __init__(self, parent_view: "WordGameView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.parent_view.process_input(interaction, self.guess.value.strip().upper())


class WordGameView(discord.ui.View):
    def __init__(self, game_id: str, p1: discord.User, p2: Optional[discord.User]):
        super().__init__(timeout=240)
        self.game_id = game_id
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.engine = GAMES_BY_ID[game_id][4]

        if self.engine == "wordle_engine":
            self.secret = random.choice(WORDS_5)
            self.attempts: List[str] = []
        elif self.engine == "hangman_engine":
            self.secret = random.choice(WORDS_HANGMAN)
            self.guessed = set()
            self.lives = 6
        else:  # scramble_engine
            self.secret = random.choice(WORDS_HANGMAN)
            chars = list(self.secret)
            random.shuffle(chars)
            self.scrambled = "".join(chars)

        btn = discord.ui.Button(label="Scrivi Risposta", emoji="✍️", style=discord.ButtonStyle.success)
        btn.callback = self.open_modal
        self.add_item(btn)

    async def open_modal(self, interaction: discord.Interaction):
        valid_ids = [self.p1.id] + ([self.p2.id] if self.p2 else [])
        if interaction.user.id not in valid_ids:
            return await interaction.response.send_message("❌ Non partecipi a questa partita!", ephemeral=True)
        await interaction.response.send_modal(WordGuessModal(self))

    def render_state(self) -> str:
        if self.engine == "wordle_engine":
            board = "\n".join(self.attempts) if self.attempts else "Nessun tentativo ancora."
            return f"Indovina la parola segreta di **5 lettere** (`{len(self.attempts)}/6` tentativi):\n\n{board}"
        if self.engine == "hangman_engine":
            masked = " ".join(c if c in self.guessed else "⬜" for c in self.secret)
            return f"Parola: `{masked}`\nVite rimaste: {'❤️' * self.lives}\nLettere usate: `{', '.join(sorted(self.guessed)) or 'Nessuna'}`"
        return f"Riordina queste lettere:\n# `{self.scrambled}`"

    async def process_input(self, interaction: discord.Interaction, text: str):
        is_p1 = interaction.user.id == self.p1.id
        winner_id = 1 if is_p1 else 2

        if self.engine == "scramble_engine":
            if text == self.secret:
                return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, winner_id, f"🎉 **{interaction.user.display_name}** ha decifrato `{self.secret}`!", self)
            return await interaction.response.send_message(f"❌ `{text}` non è corretto! Riprova.", ephemeral=True)

        if self.engine == "hangman_engine":
            if len(text) > 1:
                if text == self.secret:
                    return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, winner_id, f"🎉 **{interaction.user.display_name}** ha indovinato la parola `{self.secret}`!", self)
                self.lives -= 1
            else:
                ch = text[0]
                self.guessed.add(ch)
                if ch not in self.secret:
                    self.lives -= 1
                if all(c in self.guessed for c in self.secret):
                    return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, winner_id, f"🎉 Parola completata: `{self.secret}`!", self)

            if self.lives <= 0:
                return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, 2 if self.mode == "PvE" else 0, f"💀 Vite finite! La parola era `{self.secret}`.", self)

            g_name, _, g_emoji, _, _, _ = GAMES_BY_ID[self.game_id]
            return await interaction.response.edit_message(embed=make_embed(f"{g_emoji} {g_name.upper()}", self.render_state()), view=self)

        # Wordle
        if len(text) != 5:
            return await interaction.response.send_message("❌ Inserisci una parola di esattamente 5 lettere!", ephemeral=True)

        row_icons = []
        for i, ch in enumerate(text):
            if ch == self.secret[i]:
                row_icons.append("🟩")
            elif ch in self.secret:
                row_icons.append("🟨")
            else:
                row_icons.append("⬛")
        self.attempts.append(f"{''.join(row_icons)} `{text}`")

        if text == self.secret:
            return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, winner_id, f"🎉 **{interaction.user.display_name}** ha trovato `{self.secret}`!\n\n{self.render_state()}", self)
        if len(self.attempts) >= 6:
            return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, 2 if self.mode == "PvE" else 0, f"💀 Tentativi esauriti! La parola era `{self.secret}`.", self)

        await interaction.response.edit_message(embed=make_embed("🟩 WORDLE 5 LETTERE", self.render_state()), view=self)


# ==============================================================================
# ENGINE 7: NIM, RIFLESSI, CACCIA TESORO, BATTAGLIA NAVALE, CAMPO MINATO
# ==============================================================================
class NimView(discord.ui.View):
    def __init__(self, p1: discord.User, p2: Optional[discord.User]):
        super().__init__(timeout=180)
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.sticks = random.randint(13, 19)
        self.turn = 1
        for take in (1, 2, 3):
            b = discord.ui.Button(label=f"Prendi {take}", emoji="🥢", style=discord.ButtonStyle.primary)
            b.callback = self.make_take_cb(take)
            self.add_item(b)

    def make_take_cb(self, take: int):
        async def cb(interaction: discord.Interaction):
            expected = self.p1.id if self.turn == 1 else (self.p2.id if self.p2 else -1)
            if interaction.user.id != expected:
                return await interaction.response.send_message("❌ Non è il tuo turno!", ephemeral=True)
            if take > self.sticks:
                return await interaction.response.send_message("❌ Non ci sono abbastanza bastoncini!", ephemeral=True)

            self.sticks -= take
            if self.sticks == 0:
                winner = 2 if self.turn == 1 else 1
                return await finalize_game(interaction, "nim", self.mode, self.p1, self.p2, winner, f"💀 **{interaction.user.display_name}** ha preso l'ultimo bastoncino e perde!", self)

            if self.mode == "PvE":
                # IA calcola il resto modulo 4 con piccola variabilità
                ideal = (self.sticks - 1) % 4
                b_take = ideal if (ideal in (1, 2, 3) and random.random() < 0.75) else min(self.sticks, random.randint(1, 3))
                self.sticks -= b_take
                if self.sticks == 0:
                    return await finalize_game(interaction, "nim", "PvE", self.p1, None, 1, f"🤖 Il Bot IA ha preso {b_take} e ha raccolto l'ultimo bastoncino! Hai vinto!", self)
                embed = make_embed("🥢 NIM BASTONCINI • PVE", f"Bastoncini rimasti: {'🥢' * self.sticks} (`{self.sticks}`)\n🤖 Bot IA ne ha presi `{b_take}`. Tocca a {self.p1.mention}!")
                return await interaction.response.edit_message(embed=embed, view=self)

            self.turn = 2 if self.turn == 1 else 1
            curr = self.p1 if self.turn == 1 else self.p2
            embed = make_embed("🥢 NIM BASTONCINI • PVP", f"Bastoncini rimasti: {'🥢' * self.sticks} (`{self.sticks}`)\nTocca a {curr.mention}!")
            await interaction.response.edit_message(embed=embed, view=self)
        return cb


class GridRadarView(discord.ui.View):
    """Usato per Battaglia Navale, Campo Minato, Caccia al Tesoro, Memory e Reversi"""
    def __init__(self, game_id: str, p1: discord.User, p2: Optional[discord.User]):
        super().__init__(timeout=240)
        self.game_id = game_id
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.turn = 1
        self.scores = {1: 0, 2: 0}
        self.targets = set(random.sample(range(15), 4))
        self.treasure = random.randint(0, 14)

        for i in range(15):
            b = discord.ui.Button(label="⬜", style=discord.ButtonStyle.secondary, row=i // 5)
            b.callback = self.make_cell_cb(i)
            self.add_item(b)

    def make_cell_cb(self, idx: int):
        async def cb(interaction: discord.Interaction):
            expected = self.p1.id if self.turn == 1 else (self.p2.id if self.p2 else -1)
            if interaction.user.id != expected:
                return await interaction.response.send_message("❌ Non è il tuo turno!", ephemeral=True)

            btn = self.children[idx]
            btn.disabled = True
            engine = GAMES_BY_ID[self.game_id][4]

            if engine == "grid_mines":
                if idx in self.targets:
                    btn.label = "💣"
                    btn.style = discord.ButtonStyle.danger
                    winner = 2 if self.turn == 1 else 1
                    return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, winner, f"💣 **{interaction.user.display_name}** ha calpestato una mina!", self)
                btn.label = "✅"
                btn.style = discord.ButtonStyle.success
                self.scores[self.turn] += 10
            elif engine == "grid_treasure":
                if idx == self.treasure:
                    btn.label = "💎"
                    btn.style = discord.ButtonStyle.success
                    return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, self.turn, f"💎 **{interaction.user.display_name}** ha trovato il tesoro nascosto!", self)
                dist = abs((idx // 5) - (self.treasure // 5)) + abs((idx % 5) - (self.treasure % 5))
                btn.label = "🔥" if dist == 1 else ("♨️" if dist == 2 else "❄️")
            else:
                if idx in self.targets:
                    btn.label = "🎯"
                    btn.style = discord.ButtonStyle.success
                    self.scores[self.turn] += 1
                else:
                    btn.label = "🌊"

            if self.mode == "PvE":
                avail = [i for i, c in enumerate(self.children) if not c.disabled]
                if avail:
                    bi = random.choice(avail)
                    bb = self.children[bi]
                    bb.disabled = True
                    if engine == "grid_mines" and bi in self.targets:
                        bb.label = "💣"
                        bb.style = discord.ButtonStyle.danger
                        return await finalize_game(interaction, self.game_id, "PvE", self.p1, None, 1, "🤖 Il Bot IA ha colpito una mina! Vittoria!", self)
                    if engine == "grid_treasure" and bi == self.treasure:
                        bb.label = "💎"
                        return await finalize_game(interaction, self.game_id, "PvE", self.p1, None, 2, "🤖 Il Bot IA ha trovato il tesoro per primo!", self)
                    if bi in self.targets:
                        bb.label = "💥"
                        self.scores[2] += 1
                    else:
                        bb.label = "▫️"

            rem = [c for c in self.children if not c.disabled]
            if not rem or self.scores[1] >= 3 or self.scores[2] >= 3:
                w = 1 if self.scores[1] > self.scores[2] else (2 if self.scores[2] > self.scores[1] else 0)
                return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, w, f"Risultato griglia: **{self.scores[1]}** vs **{self.scores[2]}**", self)

            if self.mode == "PvP":
                self.turn = 2 if self.turn == 1 else 1
            curr = self.p1 if self.turn == 1 else self.p2
            g_name, _, g_emoji, _, _, _ = GAMES_BY_ID[self.game_id]
            embed = make_embed(f"{g_emoji} {g_name.upper()}", f"Punteggio: **{self.scores[1]}** vs **{self.scores[2]}**\nTocca a {curr.mention}!")
            await interaction.response.edit_message(embed=embed, view=self)
        return cb


class ReflexView(discord.ui.View):
    def __init__(self, game_id: str, p1: discord.User, p2: Optional[discord.User]):
        super().__init__(timeout=60)
        self.game_id = game_id
        self.p1 = p1
        self.p2 = p2
        self.mode = "PvP" if p2 else "PvE"
        self.ready = False
        self.start_ts = 0.0

        self.btn = discord.ui.Button(label="🔴 ASPETTA IL VERDE...", style=discord.ButtonStyle.danger)
        self.btn.callback = self.on_press
        self.add_item(self.btn)

    async def arm_signal(self, message: discord.Message):
        await asyncio.sleep(random.uniform(2.0, 4.5))
        if self.is_finished():
            return
        self.ready = True
        self.start_ts = time.perf_counter()
        self.btn.label = "🟢 CLICCA ORA!!"
        self.btn.style = discord.ButtonStyle.success
        await message.edit(embed=make_embed("🟢 SEGNALE ATTIVO!", "**PREMI IL PULSANTE ADESSO!**"), view=self)

    async def on_press(self, interaction: discord.Interaction):
        valid_ids = [self.p1.id] + ([self.p2.id] if self.p2 else [])
        if interaction.user.id not in valid_ids:
            return await interaction.response.send_message("❌ Non sei in sfida!", ephemeral=True)

        is_p1 = interaction.user.id == self.p1.id
        if not self.ready:
            winner = 2 if is_p1 else 1
            return await finalize_game(interaction, self.game_id, self.mode, self.p1, self.p2, winner, f"🚫 **FALSA PARTENZA!** {interaction.user.display_name} ha cliccato troppo presto!", self)

        reaction_ms = int((time.perf_counter() - self.start_ts) * 1000)
        if self.mode == "PvE":
            bot_ms = random.randint(450, 1200)
            w = 1 if reaction_ms <= bot_ms else 2
            return await finalize_game(interaction, self.game_id, "PvE", self.p1, None, w, f"⚡ **Tuo tempo:** `{reaction_ms} ms`\n🤖 **Bot IA:** `{bot_ms} ms`", self)

        winner = 1 if is_p1 else 2
        await finalize_game(interaction, self.game_id, "PvP", self.p1, self.p2, winner, f"⚡ **{interaction.user.display_name}** ha reagito in `{reaction_ms} ms`!", self)


# ==============================================================================
# FACTORY AVVIO PARTITA PER QUALSIASI DEI 54 MINIGAME
# ==============================================================================
async def launch_minigame(
    interaction: discord.Interaction,
    game_id: str,
    p1: discord.User,
    p2: Optional[discord.User]
):
    g_name, g_cat, g_emoji, g_pts, engine, g_desc = GAMES_BY_ID[game_id]
    mode = "PvP" if p2 else "PvE"
    vs_text = f"{p1.mention} 🆚 {p2.mention}" if p2 else f"{p1.mention} 🆚 🤖 **Bot IA**"

    if engine == "grid_ttt":
        view = TicTacToeView(p1, p2)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n*{g_desc}*\n\nTocca a {p1.mention} (`❌`).")
    elif engine == "grid_c4":
        view = Connect4View(p1, p2)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n\n{view.render_board()}\n\nTocca a {p1.mention} (`🔴`).")
    elif engine in ("rps_classic", "rps_spock", "duel_turns", "combat_hp"):
        opts_map = {
            "rps_classic": [("Sasso", "🪨"), ("Carta", "📄"), ("Forbice", "✂️")],
            "rps_spock": [("Sasso", "🪨"), ("Carta", "📄"), ("Forbice", "✂️"), ("Lizard", "🦎"), ("Spock", "🖖")],
            "duel_turns": [("Sinistra", "⬅️"), ("Centro", "⬆️"), ("Destra", "➡️")],
            "combat_hp": {
                "boxe": [("Attacco Rapido", "👊"), ("Colpo Pesante", "💥"), ("Guardia", "🛡️")],
                "scherma": [("Affondo", "🗡️"), ("Finta", "🌀"), ("Parata", "🛡️")],
                "arena_rpg": [("Spada", "⚔️"), ("Scudo", "🛡️"), ("Pozione", "🧪")],
                "dogfight": [("Mitraglia", "🔫"), ("Missile", "🚀"), ("Virata Evita", "🔄")],
            }.get(game_id, [("Spada", "⚔️"), ("Scudo", "🛡️"), ("Pozione", "🧪")])
        }
        view = SimultaneousChoiceView(game_id, p1, p2, opts_map[engine])
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n*{g_desc}*\n\nSeleziona la tua mossa segreta!")
    elif engine in ("blackjack_engine", "sette_mezzo_engine", "dice_engine", "highlow_engine", "horse_engine", "slot_engine", "wheel_engine", "push_luck_engine", "bomb_card_engine"):
        view = CasinoDuelView(game_id, p1, p2)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n*{g_desc}*\n\nInizia la mano di {p1.mention}!")
    elif engine in ("wordle_engine", "hangman_engine", "scramble_engine"):
        view = WordGameView(game_id, p1, p2)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n\n{view.render_state()}")
    elif engine == "nim_engine":
        view = NimView(p1, p2)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n*{g_desc}*\n\nBastoncini: {'🥢' * view.sticks} (`{view.sticks}`)\nTocca a {p1.mention}!")
    elif engine == "reflex_engine":
        view = ReflexView(game_id, p1, p2)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n*{g_desc}*\n\nTieniti pronto...")
        if interaction.response.is_done():
            msg = await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()
        asyncio.create_task(view.arm_signal(msg))
        return
    elif engine in ("grid_battleship", "grid_mines", "grid_treasure", "grid_reversi", "grid_territory", "memory_engine", "simon_engine"):
        view = GridRadarView(game_id, p1, p2)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n*{g_desc}*\n\nTocca a {p1.mention}!")
    else:
        q, opts, c_idx = build_question_payload(game_id)
        view = MultiChoiceView(game_id, p1, p2, q, opts, c_idx)
        embed = make_embed(f"{g_emoji} {g_name.upper()} • {mode}", f"{vs_text}\n\n{q}")

    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view)


# ==============================================================================
# ==============================================================================
# SFIDA PVP ACCETTAZIONE
# ==============================================================================
class PvPChallengeView(discord.ui.View):
    def __init__(self, game_id: str, challenger: discord.User, opponent: discord.User):
        super().__init__(timeout=90)
        self.game_id = game_id
        self.challenger = challenger
        self.opponent = opponent
        self.resolved = False

    async def on_timeout(self):
        if self.resolved:
            return
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Accetta Sfida", emoji="⚔️", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message(
                f"❌ Solo {self.opponent.mention} può accettare questa sfida!",
                ephemeral=True
            )
        if self.resolved:
            return await interaction.response.send_message("⚠️ Questa sfida è già stata gestita.", ephemeral=True)

        self.resolved = True
        self.stop()
        await interaction.response.defer()
        await launch_minigame(interaction, self.game_id, self.challenger, self.opponent)

    @discord.ui.button(label="Rifiuta", emoji="✖️", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.challenger.id, self.opponent.id):
            return await interaction.response.send_message("❌ Non fai parte di questa sfida.", ephemeral=True)
        if self.resolved:
            return await interaction.response.send_message("⚠️ Questa sfida è già stata gestita.", ephemeral=True)

        self.resolved = True
        self.stop()
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=make_embed("SFIDA ANNULLATA", f"{interaction.user.mention} ha annullato o rifiutato la sfida.", LOSE_COLOR),
            view=self
        )

# ==============================================================================
# BROWSER CATEGORIE & SELETTORE GIOCHI (54 MINIGAME)
# ==============================================================================
class GameSelectMenu(discord.ui.Select):
    def __init__(self, category: str, opponent: Optional[discord.User]):
        self.opponent = opponent
        games = [g for g in GAMES_CATALOG if g[2] == category]
        options = [
            discord.SelectOption(
                label=f"{g[1]} (+{g[4]} pt)",
                value=g[0],
                emoji=g[3],
                description=g[6][:95]
            )
            for g in games
        ]
        super().__init__(placeholder=f"Scegli un minigame in {category} (9 giochi)...", options=options)

    async def callback(self, interaction: discord.Interaction):
        game_id = self.values[0]
        if self.opponent:
            g_name, _, g_emoji, g_pts, _, g_desc = GAMES_BY_ID[game_id]
            view = PvPChallengeView(game_id, interaction.user, self.opponent)
            embed = make_embed(
                f"⚔️ SFIDA PVP • {g_name.upper()}",
                f"{interaction.user.mention} sfida {self.opponent.mention} a **{g_emoji} {g_name}**!\n"
                f"*{g_desc}*\n\n💰 **Posta in palio:** `{g_pts} punti`"
            )
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await launch_minigame(interaction, game_id, interaction.user, None)


class GameBrowserView(discord.ui.View):
    def __init__(self, category: str = "Strategia", opponent: Optional[discord.User] = None):
        super().__init__(timeout=180)
        self.category = category
        self.opponent = opponent
        self.build_items()

    def build_items(self):
        self.clear_items()
        self.add_item(GameSelectMenu(self.category, self.opponent))
        for idx, cat in enumerate(CATEGORIES):
            btn = discord.ui.Button(
                label=cat,
                style=discord.ButtonStyle.danger if cat == self.category else discord.ButtonStyle.secondary,
                row=1 if idx < 3 else 2
            )
            btn.callback = self.make_cat_cb(cat)
            self.add_item(btn)

    def make_cat_cb(self, cat: str):
        async def cb(interaction: discord.Interaction):
            self.category = cat
            self.build_items()
            mode_lbl = f"PvP vs {self.opponent.mention}" if self.opponent else "PvE vs 🤖 Bot IA"
            embed = make_embed(
                f"🎮 CATALOGO MINIGAME • {cat.upper()}",
                f"**Modalità Attiva:** {mode_lbl}\n**Giochi Totali Disponibili:** `{len(GAMES_CATALOG)}`\n\nSeleziona un gioco dal menu qui sotto:"
            )
            await interaction.response.edit_message(embed=embed, view=self)
        return cb


# ==============================================================================
# CLASSIFICA PAGINATA & VIEW PERSISTENTI
# ==============================================================================
def build_leaderboard_embed(page: int = 1) -> Tuple[discord.Embed, int]:
    rows, total_pages = fetch_leaderboard_page(page, per_page=10)
    page = max(1, min(page, total_pages))
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    if not rows:
        desc = "Nessun giocatore registrato in classifica. Gioca una partita per entrare in top!"
    else:
        lines = []
        offset = (page - 1) * 10
        for idx, r in enumerate(rows, start=1):
            rank = offset + idx
            prefix = medals.get(rank, f"`#{rank:02d}`")
            gp = r["games_played"]
            wr = int((r["wins"] / gp) * 100) if gp > 0 else 0
            lines.append(
                f"{prefix} **{r['username']}** — 💰 `{r['points']} pt` | 🏆 `{r['wins']}W` (`{wr}%`) | 🔥 `{r['streak']}`"
            )
        desc = "\n".join(lines)

    embed = make_embed(f"🏆 CLASSIFICA GLOBALE • PAGINA {page}/{total_pages}", desc)
    return embed, total_pages


class PersistentLeaderboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    def extract_page(self, interaction: discord.Interaction) -> int:
        if interaction.message and interaction.message.embeds:
            title = interaction.message.embeds[0].title or ""
            m = re.search(r"PAGINA\s+(\d+)/(\d+)", title)
            if m:
                return int(m.group(1))
        return 1

    @discord.ui.button(label="◀ Precedente", style=discord.ButtonStyle.secondary, custom_id="mg_lb_prev")
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        curr = self.extract_page(interaction)
        embed, _ = build_leaderboard_embed(max(1, curr - 1))
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Successiva ▶", style=discord.ButtonStyle.secondary, custom_id="mg_lb_next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        curr = self.extract_page(interaction)
        embed, _ = build_leaderboard_embed(curr + 1)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Aggiorna", emoji="🔄", style=discord.ButtonStyle.primary, custom_id="mg_lb_refresh")
    async def refresh_lb(self, interaction: discord.Interaction, button: discord.ui.Button):
        curr = self.extract_page(interaction)
        embed, _ = build_leaderboard_embed(curr)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="I Miei Punti", emoji="📊", style=discord.ButtonStyle.success, custom_id="mg_lb_mystats")
    async def my_stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_stats_embed(interaction.user)
        await interaction.response.send_message(embed=embed, ephemeral=True)


def build_stats_embed(user: discord.abc.User) -> discord.Embed:
    p = get_or_create_player(user.id, user.display_name)
    rank = get_player_rank(user.id)
    gp = p["games_played"]
    wr = round((p["wins"] / gp) * 100, 1) if gp > 0 else 0.0

    desc = (
        f"👤 **Giocatore:** {user.mention}\n"
        f"🏅 **Posizione Classifica:** `#{rank}`\n"
        f"💰 **Punti Totali:** `{p['points']} pt`\n\n"
        f"⫷・═══ 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐇𝐄 𝐌𝐀𝐓𝐂𝐇 ═══・⫸\n"
        f"🎮 **Partite Giocate:** `{gp}`\n"
        f"✅ **Vittorie:** `{p['wins']}` (`PvP: {p['pvp_wins']}` • `PvE: {p['pve_wins']}`)\n"
        f"❌ **Sconfitte:** `{p['losses']}` • 🤝 **Pareggi:** `{p['draws']}`\n"
        f"📈 **Win Rate:** `{wr}%`\n"
        f"🔥 **Serie Attuale:** `{p['streak']}` • ⭐ **Record Serie:** `{p['best_streak']}`\n"
        f"🎯 **Ultimo Gioco:** `{p['favorite_game']}`"
    )
    embed = make_embed("📊 PROFILO & STATISTICHE", desc)
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed


class PersistentHubView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Catalogo 54 Minigame (PvE)", emoji="🎮", style=discord.ButtonStyle.danger, custom_id="mg_hub_pve")
    async def open_pve(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = GameBrowserView("Strategia", None)
        embed = make_embed(
            "🎮 CATALOGO MINIGAME • STRATEGIA",
            f"**Modalità:** PvE vs 🤖 Bot IA Dinamico\n**Totale Giochi:** `{len(GAMES_CATALOG)}`\n\nScegli un gioco dal menu:"
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Partita Casuale PvE", emoji="🎲", style=discord.ButtonStyle.primary, custom_id="mg_hub_random")
    async def random_pve(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_id = random.choice(list(GAMES_BY_ID.keys()))
        await launch_minigame(interaction, game_id, interaction.user, None)

    @discord.ui.button(label="Classifica Punti", emoji="🏆", style=discord.ButtonStyle.secondary, custom_id="mg_hub_lb")
    async def open_lb(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed, _ = build_leaderboard_embed(1)
        await interaction.response.send_message(embed=embed, view=PersistentLeaderboardView(), ephemeral=True)

    @discord.ui.button(label="I Miei Punti & Stats", emoji="📊", style=discord.ButtonStyle.success, custom_id="mg_hub_stats")
    async def open_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_stats_embed(interaction.user), ephemeral=True)


# ==============================================================================
# INIZIALIZZAZIONE BOT & SLASH COMMANDS
# ==============================================================================
class MinigameBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Registrazione View Persistenti al riavvio
        self.add_view(PersistentHubView())
        self.add_view(PersistentLeaderboardView())
        await self.tree.sync()


bot = MinigameBot()


@bot.event
async def on_ready():
    print(f"[ONLINE] Connesso come {bot.user} | {len(GAMES_CATALOG)} minigame caricati.")


@bot.tree.command(name="pannello", description="Invia il pannello persistente dell'Arena Minigame (54 giochi PvP & PvE)")
async def cmd_pannello(interaction: discord.Interaction):
    embed = make_embed(
        "🎮 ARENA MINIGAME • 54 GIOCHI",
        "Benvenuto nell'Arena competitiva!\n\n"
        "• **54 Minigame** divisi in **6 Categorie**\n"
        "• **Modalità PvE:** sfida l'IA dinamica con mosse sempre diverse\n"
        "• **Modalità PvP:** usa `/gioca avversario:@utente` per sfidare un player\n"
        "• **Sistema Punti & Classifica:** scala la classifica globale!\n\n"
        "Usa i pulsanti persistenti qui sotto per iniziare:"
    )
    await interaction.response.send_message(embed=embed, view=PersistentHubView())


@bot.tree.command(name="gioca", description="Scegli uno dei 54 minigame (PvE o PvP) con ricerca rapida")
@app_commands.describe(
    gioco="Cerca tra tutti i 54 minigame disponibili",
    avversario="Lascia vuoto per giocare PvE contro il Bot IA, oppure tagga un player per PvP"
)
async def cmd_gioca(
    interaction: discord.Interaction,
    gioco: Optional[str] = None,
    avversario: Optional[discord.Member] = None
):
    if avversario:
        if avversario.bot or avversario.id == interaction.user.id:
            return await interaction.response.send_message(
                "❌ Non puoi sfidare te stesso o un bot Discord! Per PvE lascia vuoto `avversario`.",
                ephemeral=True
            )

    if gioco:
        key = gioco.lower().strip()
        matched_id = None

        if key in GAMES_BY_ID:
            matched_id = key
        else:
            for gid, data in GAMES_BY_ID.items():
                if key == data[0].lower() or key in gid or key in data[0].lower():
                    matched_id = gid
                    break

        if not matched_id:
            return await interaction.response.send_message(
                f"❌ Minigame `{gioco}` non trovato! Selezionalo dall'autocomplete oppure usa `/gioca` senza parametri.",
                ephemeral=True
            )

        if avversario:
            g_name, _, g_emoji, g_pts, _, g_desc = GAMES_BY_ID[matched_id]
            view = PvPChallengeView(matched_id, interaction.user, avversario)
            embed = make_embed(
                f"⚔️ SFIDA PVP • {g_name.upper()}",
                f"{interaction.user.mention} sfida {avversario.mention} a **{g_emoji} {g_name}**!\n"
                f"*{g_desc}*\n\n💰 **Posta in palio:** `{g_pts} punti`"
            )
            return await interaction.response.send_message(embed=embed, view=view)

        return await launch_minigame(interaction, matched_id, interaction.user, None)

    view = GameBrowserView("Strategia", avversario)
    mode_lbl = f"PvP vs {avversario.mention}" if avversario else "PvE vs 🤖 Bot IA Dinamico"
    embed = make_embed(
        "🎮 CATALOGO MINIGAME • STRATEGIA",
        f"**Modalità:** {mode_lbl}\n**Giochi Disponibili:** `{len(GAMES_CATALOG)}`\n\nSeleziona un minigame dal menu:"
    )
    await interaction.response.send_message(embed=embed, view=view)


@cmd_gioca.autocomplete("gioco")
async def gioco_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    q = current.lower().strip()

    if not q:
        # Mostra i primi 25 in ordine alfabetico quando il campo è vuoto; digitando filtra tutti i 54
        sorted_games = sorted(GAMES_CATALOG, key=lambda g: g[1])
        return [
            app_commands.Choice(
                name=f"{g[3]} {g[1]} • {g[2]} (+{g[4]} pt)"[:100],
                value=g[0]
            )
            for g in sorted_games[:25]
        ]

    exact_or_prefix = []
    partial_matches = []

    for g in GAMES_CATALOG:
        gid, gname, gcat, gemoji, gpts, _, gdesc = g
        haystack = f"{gid} {gname} {gcat} {gdesc}".lower()
        choice = app_commands.Choice(
            name=f"{gemoji} {gname} • {gcat} (+{gpts} pt)"[:100],
            value=gid
        )
        if gname.lower().startswith(q) or gid.startswith(q):
            exact_or_prefix.append(choice)
        elif q in haystack:
            partial_matches.append(choice)

    return (exact_or_prefix + partial_matches)[:25]


@bot.tree.command(name="classifica", description="Visualizza la classifica punti globale con pagine sfogliabili")
@app_commands.describe(pagina="Numero pagina iniziale")
async def cmd_classifica(interaction: discord.Interaction, pagina: int = 1):
    embed, _ = build_leaderboard_embed(pagina)
    await interaction.response.send_message(embed=embed, view=PersistentLeaderboardView())


@bot.tree.command(name="statistiche", description="Visualizza i tuoi punti, il rank e le statistiche di gioco")
@app_commands.describe(utente="Utente di cui vedere le statistiche (opzionale)")
async def cmd_statistiche(interaction: discord.Interaction, utente: Optional[discord.Member] = None):
    target = utente or interaction.user
    await interaction.response.send_message(embed=build_stats_embed(target))


@bot.tree.command(name="lista_giochi", description="Mostra l'elenco completo di tutti i 54 minigame divisi per categoria")
async def cmd_lista_giochi(interaction: discord.Interaction):
    sections = []
    for cat in CATEGORIES:
        items = [f"{g[3]} `{g[1]}`" for g in GAMES_CATALOG if g[2] == cat]
        sections.append(f"**{cat.upper()} (9):** " + " • ".join(items))
    embed = make_embed(f"📚 ELENCO COMPLETO ({len(GAMES_CATALOG)} MINIGAME)", "\n\n".join(sections))
    await interaction.response.send_message(embed=embed)

# ==============================================================================
# COMANDI STAFF PUNTI (SOLO RUOLO STAFF_ROLE_ID)
# ==============================================================================
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1567537096367804547"))


def has_staff_role(interaction: discord.Interaction) -> bool:
    if not STAFF_ROLE_ID or not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    return any(role.id == STAFF_ROLE_ID for role in interaction.user.roles)


def adjust_player_points(user_id: int, username: str, delta: int) -> Dict[str, Any]:
    player = get_or_create_player(user_id, username)
    new_points = max(0, player["points"] + delta)
    payload = {
        "username": username,
        "points": new_points,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    supabase.table("minigame_stats").update(payload).eq("user_id", user_id).execute()
    player.update(payload)
    return player


@bot.tree.command(name="aggiungi_punti", description="[Staff] Aggiungi punti a un giocatore")
@app_commands.describe(
    utente="Giocatore a cui aggiungere punti",
    punti="Quantità di punti da aggiungere (maggiore di 0)",
    motivo="Motivazione opzionale"
)
async def cmd_aggiungi_punti(
    interaction: discord.Interaction,
    utente: discord.Member,
    punti: int,
    motivo: Optional[str] = None
):
    if not has_staff_role(interaction):
        return await interaction.response.send_message(
            "❌ Non hai il ruolo staff autorizzato per usare questo comando.",
            ephemeral=True
        )
    if punti <= 0:
        return await interaction.response.send_message(
            "❌ Inserisci un numero di punti maggiore di `0`.",
            ephemeral=True
        )

    updated = adjust_player_points(utente.id, utente.display_name, punti)
    reason_line = f"\n📝 **Motivo:** {motivo}" if motivo else ""
    embed = make_embed(
        "➕ PUNTI AGGIUNTI",
        f"👤 **Giocatore:** {utente.mention}\n"
        f"💰 **Aggiunti:** `+{punti} pt`\n"
        f"🏦 **Nuovo Saldo:** `{updated['points']} pt`\n"
        f"🛡️ **Staffer:** {interaction.user.mention}{reason_line}",
        WIN_COLOR
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="togli_punti", description="[Staff] Rimuovi punti a un giocatore")
@app_commands.describe(
    utente="Giocatore a cui togliere punti",
    punti="Quantità di punti da rimuovere (maggiore di 0)",
    motivo="Motivazione opzionale"
)
async def cmd_togli_punti(
    interaction: discord.Interaction,
    utente: discord.Member,
    punti: int,
    motivo: Optional[str] = None
):
    if not has_staff_role(interaction):
        return await interaction.response.send_message(
            "❌ Non hai il ruolo staff autorizzato per usare questo comando.",
            ephemeral=True
        )
    if punti <= 0:
        return await interaction.response.send_message(
            "❌ Inserisci un numero di punti maggiore di `0`.",
            ephemeral=True
        )

    updated = adjust_player_points(utente.id, utente.display_name, -punti)
    reason_line = f"\n📝 **Motivo:** {motivo}" if motivo else ""
    embed = make_embed(
        "➖ PUNTI RIMOSSI",
        f"👤 **Giocatore:** {utente.mention}\n"
        f"💰 **Rimossi:** `-{punti} pt`\n"
        f"🏦 **Nuovo Saldo:** `{updated['points']} pt`\n"
        f"🛡️ **Staffer:** {interaction.user.mention}{reason_line}",
        LOSE_COLOR
    )
    await interaction.response.send_message(embed=embed)

# ==============================================================================
# AVVIO FLASK + BOT
# ==============================================================================
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Imposta DISCORD_TOKEN nelle variabili d'ambiente.")
    Thread(target=run_flask, daemon=True).start()
    bot.run(DISCORD_TOKEN)
