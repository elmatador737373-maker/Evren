# menu_bellevue.py

TEMPI = {
    "pizza": 300,
    "primo": 450,
    "secondo": 600,
    "dessert": 180,
    "last_minute": 240
}

MENU_DATI = {
    # --- LE NOSTRE PIZZE ---
    "Margherita": {"desc": "Impasto, pomodoro, mozzarella, basilico", "tempo": TEMPI["pizza"]},
    "Diavola": {"desc": "Impasto, pomodoro, mozzarella, salame piccante", "tempo": TEMPI["pizza"]},
    "Marinara": {"desc": "Impasto, pomodoro, aglio, origano, olio", "tempo": TEMPI["pizza"]},
    "Quattro Formaggi": {"desc": "Impasto, mozzarella, gorgonzola, fontina, parmigiano", "tempo": TEMPI["pizza"]},
    "Boscaiola": {"desc": "Impasto, pomodoro, mozzarella, funghi, prosciutto cotto", "tempo": TEMPI["pizza"]},
    "Salsicce E Friarielli": {"desc": "Impasto, mozzarella, salsiccia, friarielli", "tempo": TEMPI["pizza"]},
    "Capricciosa": {"desc": "Impasto, pomodoro, mozzarella, prosciutto cotto, funghi, carciofi, olive", "tempo": TEMPI["pizza"]},
    "Wurstel E Patatine": {"desc": "Impasto, pomodoro, mozzarella, wurstel, patatine fritte", "tempo": TEMPI["pizza"]},
    "Frutti Di Mare": {"desc": "Impasto, pomodoro, frutti di mare, aglio, prezzemolo", "tempo": TEMPI["pizza"]},
    "La Bellevue": {"desc": "Impasto, pomodoro, mozzarella, rucola, parmigiano, pomodorini, bresaola", "tempo": 360},

    # --- I NOSTRI PRIMI PIATTI ---
    "Pasta Al Ragù": {"desc": "Pasta fresca, ragù di carne", "tempo": TEMPI["primo"]},
    "Penne All'Arrabbiata": {"desc": "Penne, pomodoro, aglio, peperoncino", "tempo": TEMPI["primo"]},
    "Cacio E Pepe": {"desc": "Pasta, pecorino romano, pepe nero", "tempo": TEMPI["primo"]},
    "Spaghetti Alle Vongole": {"desc": "Spaghetti, vongole, aglio, prezzemolo", "tempo": TEMPI["primo"]},
    "Orecchiette Cime Di Rapa": {"desc": "Orecchiette, cime di rapa, aglio, olio", "tempo": TEMPI["primo"]},
    "Pasta Panna E Tonno": {"desc": "Pasta, panna, tonno", "tempo": TEMPI["primo"]},
    "Pasta Sugo Di Salsiccia": {"desc": "Pasta, pomodoro, salsiccia", "tempo": TEMPI["primo"]},
    "Tortellini In Brodo": {"desc": "Tortellini di carne, brodo di carne", "tempo": TEMPI["primo"]},
    "Spaghetti Sugo E Polpette": {"desc": "Spaghetti, pomodoro, polpette di carne", "tempo": TEMPI["primo"]},

    # --- I NOSTRI SECONDI PIATTI ---
    "Scaloppine Al Limone": {"desc": "Fettine di carne, limone", "tempo": TEMPI["secondo"]},
    "Involtini Pollo E Formaggio": {"desc": "Pollo, formaggio", "tempo": TEMPI["secondo"]},
    "Arrosto Di Vitello": {"desc": "Carne di vitello", "tempo": 900},
    "Filetto Di Maiale In Salsa": {"desc": "Filetto di maiale, salsa", "tempo": TEMPI["secondo"]},
    "Pollo Al Lime": {"desc": "Petto di pollo, lime", "tempo": TEMPI["secondo"]},
    "Involtini Vitello Nocciole": {"desc": "Fettine di vitello, nocciole", "tempo": TEMPI["secondo"]},
    "Finta Pizza Di Albumi": {"desc": "Albumi, funghi champignon", "tempo": TEMPI["last_minute"]},
    
    
    "Tiramisù": {"tempo": 15, "desc": "Savoiardi, caffè, mascarpone"},
    "Creme Brûlée": {"tempo": 20, "desc": "Crema inglese con crosta di zucchero"},
    "Mousse al Cioccolato": {"tempo": 10, "desc": "Mousse soffice al cioccolato fondente"},
    "Puffinglese": {"tempo": 25, "desc": "Dessert speciale Bellevue"},
    "Zuppa Inglese": {"tempo": 15, "desc": "Alchermes, crema e cacao"},
    "Cannoli Siciliani": {"tempo": 20, "desc": "Ricotta fresca e granella di pistacchio"},
    "Babà Napoletano": {"tempo": 10, "desc": "Soffice babà bagnato al rum"},
    "Profitterol": {"tempo": 25, "desc": "Bignè ripieni di crema al cioccolato"}
}
