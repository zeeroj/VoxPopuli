import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "consultbot.db")
FACE_CACHE_PATH = os.path.join(DATA_DIR, "face_encodings.pkl")

CANDIDATES = {
    "javier_milei": {
        "name": "Javier Milei",
        "full_name": "Javier Gerardo Milei",
        "party": "La Libertad Avanza",
        "keywords": ["milei", "javier milei", "presidente milei", "milei presidente",
                     "javier milei 2027", "milei 2027", "milei argentina",
                     "libertad avanza", "lla milei"],
        "search_terms": ["milei", "javier milei", "#milei", "#javiermilei",
                         "#mileipresidente", "#libertadavanza"],
        "color": "#8B5CF6"
    },
    "axel_kicillof": {
        "name": "Axel Kicillof",
        "full_name": "Axel Kicillof",
        "party": "Unión por la Patria",
        "keywords": ["kicillof", "axel kicillof", "gobernador kicillof",
                     "kicillof 2027", "axel 2027", "kicillof presidente"],
        "search_terms": ["kicillof", "axel kicillof", "#kicillof", "#axelkicillof",
                         "#kicillofgobernador", "#kicillof2027"],
        "color": "#3B82F6"
    },
    "patricia_bullrich": {
        "name": "Patricia Bullrich",
        "full_name": "Patricia Bullrich",
        "party": "PRO",
        "keywords": ["bullrich", "patricia bullrich", "patricia 2027",
                     "bullrich 2027", "bullrich presidente"],
        "search_terms": ["bullrich", "patricia bullrich", "#bullrich",
                         "#patriciabullrich", "#bullrich2027"],
        "color": "#F59E0B"
    },
    "sergio_massa": {
        "name": "Sergio Massa",
        "full_name": "Sergio Tomás Massa",
        "party": "Frente Renovador",
        "keywords": ["massa", "sergio massa", "massa 2027", "sergio massa 2027"],
        "search_terms": ["massa", "sergio massa", "#massa", "#sergiomassa", "#massa2027"],
        "color": "#10B981"
    },
    "mauricio_macri": {
        "name": "Mauricio Macri",
        "full_name": "Mauricio Macri",
        "party": "PRO",
        "keywords": ["macri", "mauricio macri", "macri 2027", "mauricio macri 2027"],
        "search_terms": ["macri", "mauricio macri", "#macri", "#mauriciomacri", "#macri2027"],
        "color": "#FBBF24"
    },
    "horacio_rodriguez_larreta": {
        "name": "Horacio Rodríguez Larreta",
        "full_name": "Horacio Rodríguez Larreta",
        "party": "PRO",
        "keywords": ["larreta", "rodriguez larreta", "horacio larreta",
                     "larreta 2027"],
        "search_terms": ["larreta", "rodriguez larreta", "#larreta",
                         "#rodriguezlarreta"],
        "color": "#EC4899"
    },
    "cristina_fernandez": {
        "name": "Cristina Fernández de Kirchner",
        "full_name": "Cristina Elisabet Fernández de Kirchner",
        "party": "Unión por la Patria",
        "keywords": ["cristina", "cristina kirchner", "cfk", "cristina fernandez",
                     "cristina 2027", "cfk 2027"],
        "search_terms": ["cristina kirchner", "cfk", "cristina fernandez",
                         "#cristinakirchner", "#cfk", "#cristinafernandez"],
        "color": "#EF4444"
    },
    "juan_grabois": {
        "name": "Juan Grabois",
        "full_name": "Juan Grabois",
        "party": "Frente Patria Grande",
        "keywords": ["grabois", "juan grabois", "grabois 2027"],
        "search_terms": ["grabois", "juan grabois", "#grabois", "#juangrabois"],
        "color": "#059669"
    },
    "nicolas_del_cano": {
        "name": "Nicolás del Caño",
        "full_name": "Nicolás del Caño",
        "party": "Frente de Izquierda",
        "keywords": ["del caño", "nicolas del caño", "del caño 2027", "fit"],
        "search_terms": ["del caño", "nicolas del caño", "#delcaño",
                         "#nicolasdelcaño", "#frentedeizquierda"],
        "color": "#DC2626"
    },
    "myriam_bregman": {
        "name": "Myriam Bregman",
        "full_name": "Myriam Bregman",
        "party": "Frente de Izquierda",
        "keywords": ["bregman", "myriam bregman", "bregman 2027"],
        "search_terms": ["bregman", "myriam bregman", "#bregman", "#myriambregman"],
        "color": "#B91C1C"
    }
}

PLATFORMS = {
    "instagram": {
        "enabled": True,
        "rate_limit": 3,
        "max_posts_per_search": 40,
    },
    "facebook": {
        "enabled": True,
        "rate_limit": 5,
        "max_posts_per_search": 30,
    },
    "twitter": {
        "enabled": True,
        "rate_limit": 3,
        "max_posts_per_search": 30,
    },
    "tiktok": {
        "enabled": True,
        "rate_limit": 4,
        "max_posts_per_search": 25,
    },
    "reddit": {
        "enabled": True,
        "rate_limit": 2,
        "max_posts_per_search": 20,
    },
    "youtube": {
        "enabled": True,
        "rate_limit": 3,
        "max_posts_per_search": 15,
    },
    "threads": {
        "enabled": True,
        "rate_limit": 4,
        "max_posts_per_search": 20,
    },
}

REACTION_MAP = {
    "like": 1.0,
    "me_gusta": 1.0,
    "love": 1.5,
    "me_encanta": 1.5,
    "care": 1.2,
    "me_importa": 1.2,
    "haha": 0.8,
    "me_divierte": 0.8,
    "wow": 0.9,
    "me_asombra": 0.9,
    "sad": 0.5,
    "me_entristece": 0.5,
    "angry": 0.3,
    "me_enoja": 0.3,
}

ENGAGEMENT_WEIGHTS = {
    "reactions": 0.4,
    "comments": 0.35,
    "shares": 0.25,
}

SCRAPER_TIMEOUT = 30
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
