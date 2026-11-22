"""
SineMix — 434 Yapımlık Güvenli ve Kesintisiz Katalog Veri Çekme Betiği (`seed_catalog.py`)

Özellikler:
1. `.env` dosyasındaki `TMDB_API_KEY` değerini kullanarak 434 film, dizi ve animasyonu
   TMDB API v3 (`/search/movie` ve `/search/tv`, `language=tr-TR`; Türkçe özet boşsa
   fallback olarak `language=en-US`) üzerinden çeker ve `data/catalog.json` dosyasına kaydeder.
2. TMDB API limitlerine takılmamak için istekler arasında `time.sleep(0.15)` bekler.
3. Her 20 yapımda bir `data/catalog.json` dosyasına ara kayıt (checkpoint) yapar;
   işlem yarıda kesilse bile tekrar çalıştırıldığında mevcut yapımları atlayıp
   kaldığı yerden devam eder (Resume desteği).
4. `TMDB_API_KEY` henüz girilmemişse yerleşik zengin meta veri üreticisiyle 434 yapımın
   tamamını standart şemayla `data/catalog.json` dosyasına hazırlar.
"""

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
CATALOG_JSON_PATH = BASE_DIR / "data" / "catalog.json"

from app.config import _load_dotenv_file
from app.core.tmdb_fallback import FALLBACK_TMDB_CATALOG, TMDB_GENRE_MAP
from app.core.utils import normalize_search_text
from app.features.catalog.repository import normalize_genre_objects
from app.features.watchlist.services import _infer_genres_and_keywords_from_title, clean_bulk_title_line

_load_dotenv_file(BASE_DIR / ".env")

# 434 Seçkin Film, Dizi ve Animasyon Listesi (media_type, title, release_year)
CURATED_movies_and_shows: List[Tuple[str, str, int]] = [
    # --- FİLMLER (234 Film) ---
    ("movie", "The Shawshank Redemption", 1994), ("movie", "The Godfather", 1972),
    ("movie", "The Dark Knight", 2008), ("movie", "The Godfather Part II", 1974),
    ("movie", "12 Angry Men", 1957), ("movie", "Schindler's List", 1993),
    ("movie", "The Lord of the Rings: The Return of the King", 2003), ("movie", "Pulp Fiction", 1994),
    ("movie", "The Lord of the Rings: The Fellowship of the Ring", 2001), ("movie", "The Good, the Bad and the Ugly", 1966),
    ("movie", "Forrest Gump", 1994), ("movie", "Fight Club", 1999),
    ("movie", "The Lord of the Rings: The Two Towers", 2002), ("movie", "Inception", 2010),
    ("movie", "Star Wars: Episode V - The Empire Strikes Back", 1980), ("movie", "The Matrix", 1999),
    ("movie", "GoodFellas", 1990), ("movie", "One Flew Over the Cuckoo's Nest", 1975),
    ("movie", "Se7en", 1995), ("movie", "It's a Wonderful Life", 1946),
    ("movie", "Seven Samurai", 1954), ("movie", "Interstellar", 2014),
    ("movie", "The Silence of the Lambs", 1991), ("movie", "Saving Private Ryan", 1998),
    ("movie", "City of God", 2002), ("movie", "Life Is Beautiful", 1997),
    ("movie", "The Green Mile", 1999), ("movie", "Star Wars: Episode IV - A New Hope", 1977),
    ("movie", "Terminator 2: Judgment Day", 1991), ("movie", "Back to the Future", 1985),
    ("movie", "Spirited Away", 2001), ("movie", "The Pianist", 2002),
    ("movie", "Psycho", 1960), ("movie", "Parasite", 2019),
    ("movie", "Léon: The Professional", 1994), ("movie", "The Lion King", 1994),
    ("movie", "Gladiator", 2000), ("movie", "American History X", 1998),
    ("movie", "The Departed", 2006), ("movie", "Whiplash", 2014),
    ("movie", "The Prestige", 2006), ("movie", "The Usual Suspects", 1995),
    ("movie", "Casablanca", 1942), ("movie", "Grave of the Fireflies", 1988),
    ("movie", "Harakiri", 1962), ("movie", "The Intouchables", 2011),
    ("movie", "Modern Times", 1936), ("movie", "Once Upon a Time in the West", 1968),
    ("movie", "Cinema Paradiso", 1988), ("movie", "Rear Window", 1954),
    ("movie", "Alien", 1979), ("movie", "City Lights", 1931),
    ("movie", "Apocalypse Now", 1979), ("movie", "Memento", 2000),
    ("movie", "Django Unchained", 2012), ("movie", "Raiders of the Lost Ark", 1981),
    ("movie", "WALL-E", 2008), ("movie", "The Lives of Others", 2006),
    ("movie", "Sunset Boulevard", 1950), ("movie", "Paths of Glory", 1957),
    ("movie", "Avengers: Infinity War", 2018), ("movie", "Spider-Man: Into the Spider-Verse", 2018),
    ("movie", "The Shining", 1980), ("movie", "Witness for the Prosecution", 1957),
    ("movie", "Aliens", 1986), ("movie", "Inglourious Basterds", 2009),
    ("movie", "The Dark Knight Rises", 2012), ("movie", "Dr. Strangelove", 1964),
    ("movie", "Oldboy", 2003), ("movie", "Coco", 2017),
    ("movie", "Amadeus", 1984), ("movie", "Toy Story", 1995),
    ("movie", "Braveheart", 1995), ("movie", "Das Boot", 1981),
    ("movie", "Avengers: Endgame", 2019), ("movie", "Princess Mononoke", 1997),
    ("movie", "Once Upon a Time in America", 1984), ("movie", "Good Will Hunting", 1997),
    ("movie", "Your Name.", 2016), ("movie", "Requiem for a Dream", 2000),
    ("movie", "3 Idiots", 2009), ("movie", "Singin' in the Rain", 1952),
    ("movie", "Toy Story 3", 2010), ("movie", "High and Low", 1963),
    ("movie", "Capernaum", 2018), ("movie", "Star Wars: Episode VI - Return of the Jedi", 1983),
    ("movie", "Eternal Sunshine of the Spotless Mind", 2004), ("movie", "2001: A Space Odyssey", 1968),
    ("movie", "Reservoir Dogs", 1992), ("movie", "Come and See", 1985),
    ("movie", "The Hunt", 2012), ("movie", "Citizen Kane", 1941),
    ("movie", "M", 1931), ("movie", "Lawrence of Arabia", 1962),
    ("movie", "North by Northwest", 1959), ("movie", "Vertigo", 1958),
    ("movie", "Amélie", 2001), ("movie", "A Clockwork Orange", 1971),
    ("movie", "Double Indemnity", 1944), ("movie", "Full Metal Jacket", 1987),
    ("movie", "Scarface", 1983), ("movie", "Hamilton", 2020),
    ("movie", "Incendies", 2010), ("movie", "To Kill a Mockingbird", 1962),
    ("movie", "The Sting", 1973), ("movie", "Up", 2009),
    ("movie", "Heat", 1995), ("movie", "Taxi Driver", 1976),
    ("movie", "A Separation", 2011), ("movie", "Metropolis", 1927),
    ("movie", "L.A. Confidential", 1997), ("movie", "Snatch", 2000),
    ("movie", "Die Hard", 1988), ("movie", "Bicycle Thieves", 1948),
    ("movie", "Indiana Jones and the Last Crusade", 1989), ("movie", "1917", 2019),
    ("movie", "Like Stars on Earth", 2007), ("movie", "Downfall", 2004),
    ("movie", "For a Few Dollars More", 1965), ("movie", "Batman Begins", 2005),
    ("movie", "Dangal", 2016), ("movie", "The Kid", 1921),
    ("movie", "Some Like It Hot", 1959), ("movie", "The Father", 2020),
    ("movie", "All About Eve", 1950), ("movie", "Green Book", 2018),
    ("movie", "The Wolf of Wall Street", 2013), ("movie", "Judgment at Nuremberg", 1961),
    ("movie", "Casino", 1995), ("movie", "Ran", 1985),
    ("movie", "Pan's Labyrinth", 2006), ("movie", "The Truman Show", 1998),
    ("movie", "There Will Be Blood", 2007), ("movie", "Unforgiven", 1992),
    ("movie", "The Sixth Sense", 1999), ("movie", "Shutter Island", 2010),
    ("movie", "A Beautiful Mind", 2001), ("movie", "Jurassic Park", 1993),
    ("movie", "Yojimbo", 1961), ("movie", "The Treasure of the Sierra Madre", 1948),
    ("movie", "Monty Python and the Holy Grail", 1975), ("movie", "No Country for Old Men", 2007),
    ("movie", "Kill Bill: Vol. 1", 2003), ("movie", "Rashomon", 1950),
    ("movie", "The Thing", 1982), ("movie", "Finding Nemo", 2003),
    ("movie", "The Elephant Man", 1980), ("movie", "Chinatown", 1974),
    ("movie", "Raging Bull", 1980), ("movie", "V for Vendetta", 2005),
    ("movie", "Gone with the Wind", 1939), ("movie", "Lock, Stock and Two Smoking Barrels", 1998),
    ("movie", "Inside Out", 2015), ("movie", "Dial M for Murder", 1954),
    ("movie", "The Secret in Their Eyes", 2009), ("movie", "Howl's Moving Castle", 2004),
    ("movie", "Three Billboards Outside Ebbing, Missouri", 2017), ("movie", "Trainspotting", 1996),
    ("movie", "The Bridge on the River Kwai", 1957), ("movie", "Prisoners", 2013),
    ("movie", "Fargo", 1996), ("movie", "Warrior", 2011),
    ("movie", "Gran Torino", 2008), ("movie", "Catch Me If You Can", 2002),
    ("movie", "My Neighbor Totoro", 1988), ("movie", "Million Dollar Baby", 2004),
    ("movie", "Children of Heaven", 1997), ("movie", "Blade Runner", 1982),
    ("movie", "The Gold Rush", 1925), ("movie", "Before Sunrise", 1995),
    ("movie", "12 Years a Slave", 2013), ("movie", "Klaus", 2019),
    ("movie", "Harry Potter and the Deathly Hallows: Part 2", 2011), ("movie", "On the Waterfront", 1954),
    ("movie", "Ben-Hur", 1959), ("movie", "Gone Girl", 2014),
    ("movie", "The Grand Budapest Hotel", 2014), ("movie", "Wild Strawberries", 1957),
    ("movie", "The General", 1926), ("movie", "The Third Man", 1949),
    ("movie", "In the Name of the Father", 1993), ("movie", "The Deer Hunter", 1978),
    ("movie", "Barry Lyndon", 1975), ("movie", "Hacksaw Ridge", 2016),
    ("movie", "The Wages of Fear", 1953), ("movie", "Memories of Murder", 2003),
    ("movie", "Sherlock Jr.", 1924), ("movie", "Wild Tales", 2014),
    ("movie", "Mad Max: Fury Road", 2015), ("movie", "The Seventh Seal", 1957),
    ("movie", "Mary and Max", 2009), ("movie", "How to Train Your Dragon", 2010),
    ("movie", "Room", 2015), ("movie", "Monsters, Inc.", 2001),
    ("movie", "Jaws", 1975), ("movie", "Dead Poets Society", 1989),
    ("movie", "The Big Lebowski", 1998), ("movie", "Tokyo Story", 1953),
    ("movie", "The Passion of Joan of Arc", 1928), ("movie", "Hotel Rwanda", 2004),
    ("movie", "Ford v Ferrari", 2019), ("movie", "Rocky", 1976),
    ("movie", "Platoon", 1986), ("movie", "Ratatouille", 2007),
    ("movie", "Spotlight", 2015), ("movie", "The Terminator", 1984),
    ("movie", "Logan", 2017), ("movie", "Stand by Me", 1986),
    ("movie", "Rush", 2013), ("movie", "Network", 1976),
    ("movie", "Into the Wild", 2007), ("movie", "The Wizard of Oz", 1939),
    ("movie", "The Exorcist", 1973), ("movie", "La Haine", 1995),
    ("movie", "The Incredibles", 2004), ("movie", "Before Sunset", 2004),
    ("movie", "Arrival", 2016), ("movie", "The Martian", 2015),
    ("movie", "Blade Runner 2049", 2017), ("movie", "Tenet", 2020),
    ("movie", "Dune: Çöl Gezegeni", 2021), ("movie", "Dune: Part Two", 2024),
    ("movie", "The Batman", 2022), ("movie", "Joker", 2019),
    ("movie", "Ex Machina", 2015), ("movie", "Oppenheimer", 2023),
    ("movie", "Everything Everywhere All at Once", 2022), ("movie", "Top Gun: Maverick", 2022),
    ("movie", "Spider-Man: Across the Spider-Verse", 2023), ("movie", "The Social Network", 2010),
    ("movie", "Drive", 2011), ("movie", "Nightcrawler", 2014),
    ("movie", "Her", 2013), ("movie", "The Revenant", 2015),

    # --- DİZİLER VE ANİMASYONLAR (200 Dizi & Anime) ---
    ("tv", "Breaking Bad", 2008), ("tv", "Planet Earth II", 2016),
    ("tv", "Planet Earth", 2006), ("tv", "Band of Brothers", 2001),
    ("tv", "Chernobyl", 2019), ("tv", "The Wire", 2002),
    ("tv", "Avatar: The Last Airbender", 2005), ("tv", "Blue Planet II", 2017),
    ("tv", "The Sopranos", 1999), ("tv", "Cosmos: A Spacetime Odyssey", 2014),
    ("tv", "Cosmos", 1980), ("tv", "Our Planet", 2019),
    ("tv", "Game of Thrones", 2011), ("tv", "The World at War", 1973),
    ("tv", "Rick and Morty", 2013), ("tv", "Fullmetal Alchemist: Brotherhood", 2009),
    ("tv", "The Last Dance", 2020), ("tv", "Life", 2009),
    ("tv", "Sherlock", 2010), ("tv", "The Twilight Zone", 1959),
    ("tv", "The Vietnam War", 2017), ("tv", "Batman: The Animated Series", 1992),
    ("tv", "Attack on Titan", 2013), ("tv", "Arcane", 2021),
    ("tv", "Better Call Saul", 2015), ("tv", "The Office", 2005),
    ("tv", "Firefly", 2002), ("tv", "Human Planet", 2011),
    ("tv", "Death Note", 2006), ("tv", "Frozen Planet", 2011),
    ("tv", "Clarkson's Farm", 2021), ("tv", "Hunter x Hunter", 2011),
    ("tv", "Only Fools and Horses", 1981), ("tv", "The Civil War", 1990),
    ("tv", "True Detective", 2014), ("tv", "Seinfeld", 1989),
    ("tv", "Dekalog", 1989), ("tv", "Persona", 2018),
    ("tv", "The Beatles: Get Back", 2021), ("tv", "Fargo", 2014),
    ("tv", "Cowboy Bebop", 1998), ("tv", "Gravity Falls", 2012),
    ("tv", "Nathan for You", 2013), ("tv", "Last Week Tonight with John Oliver", 2014),
    ("tv", "When They See Us", 2019), ("tv", "Succession", 2018),
    ("tv", "Friends", 1994), ("tv", "Africa", 2013),
    ("tv", "Apocalypse: The Second World War", 2009), ("tv", "TVF Pitchers", 2015),
    ("tv", "It's Always Sunny in Philadelphia", 2005), ("tv", "Monty Python's Flying Circus", 1969),
    ("tv", "Taskmaster", 2015), ("tv", "Das Boot", 1985),
    ("tv", "Curb Your Enthusiasm", 2000), ("tv", "The West Wing", 1999),
    ("tv", "Pride and Prejudice", 1995), ("tv", "Fawlty Towers", 1975),
    ("tv", "Freaks and Geeks", 1999), ("tv", "Leyla and Mecnun", 2011),
    ("tv", "Blackadder Goes Forth", 1989), ("tv", "Twin Peaks", 1990),
    ("tv", "BoJack Horseman", 2014), ("tv", "Black Mirror", 2011),
    ("tv", "Narcos", 2015), ("tv", "Chappelle's Show", 2003),
    ("tv", "Dragon Ball Z", 1989), ("tv", "One Piece", 1999),
    ("tv", "I, Claudius", 1976), ("tv", "South Park", 1997),
    ("tv", "Rome", 2005), ("tv", "Ted Lasso", 2020),
    ("tv", "Oz", 1997), ("tv", "Six Feet Under", 2001),
    ("tv", "Over the Garden Wall", 2014), ("tv", "Peaky Blinders", 2013),
    ("tv", "Kota Factory", 2019), ("tv", "Dark", 2017),
    ("tv", "The Mandalorian", 2019), ("tv", "Steins;Gate", 2011),
    ("tv", "Arrested Development", 2003), ("tv", "The Boys", 2019),
    ("tv", "Vinland Saga", 2019), ("tv", "The Simpsons", 1989),
    ("tv", "House", 2004), ("tv", "Stranger Things", 2016),
    ("tv", "The Shield", 2002), ("tv", "Battlestar Galactica", 2004),
    ("tv", "Monster", 2004), ("tv", "Downton Abbey", 2010),
    ("tv", "Invincible", 2021), ("tv", "Mad Men", 2007),
    ("tv", "Fleabag", 2016), ("tv", "Gullak", 2019),
    ("tv", "The Crown", 2016), ("tv", "Panchayat", 2020),
    ("tv", "Berserk", 1997), ("tv", "Star Trek: The Next Generation", 1987),
    ("tv", "The Adventures of Sherlock Holmes", 1984), ("tv", "Friday Night Lights", 2006),
    ("tv", "The Thick of It", 2005), ("tv", "Line of Duty", 2012),
    ("tv", "TheJinx: The Life and Deaths of Robert Durst", 2015), ("tv", "Parks and Recreation", 2009),
    ("tv", "Father Ted", 1995), ("tv", "deadwood", 2004),
    ("tv", "Code Geass", 2006), ("tv", "The X-Files", 1993),
    ("tv", "dexter", 2006), ("tv", "Boardwalk Empire", 2010),
    ("tv", "Black Books", 2000), ("tv", "The Queen's Gambit", 2020),
    ("tv", "Justice League Unlimited", 2004), ("tv", "Peep Show", 2003),
    ("tv", "Spaced", 1999), ("tv", "Scam 1992: The Harshad Mehta Story", 2020),
    ("tv", "Atlanta", 2016), ("tv", "Yeh Meri Family", 2018),
    ("tv", "Through the Wormhole", 2010), ("tv", "Gomorrah", 2014),
    ("tv", "Severance", 2022), ("tv", "Mindhunter", 2017),
    ("tv", "Mr. Robot", 2015), ("tv", "The Last of Us", 2023),
    ("tv", "House of the Dragon", 2022), ("tv", "Andor", 2022),
    ("tv", "The Bear", 2022), ("tv", "Shogun", 2024),
    ("tv", "Fallout", 2024), ("tv", "Silo", 2023),
    ("tv", "The Penguin", 2024), ("tv", "Blue Eye Samurai", 2023),
    ("tv", "Jujutsu Kaisen", 2020), ("tv", "Demon Slayer: Kimetsu no Yaiba", 2019),
    ("tv", "Chainsaw Man", 2022), ("tv", "Spy x Family", 2022),
    ("tv", "One Punch Man", 2015), ("tv", "Mob Psycho 100", 2016),
    ("tv", "Neon Genesis Evangelion", 1995), ("tv", "Naruto: Shippuden", 2007),
    ("tv", "Bleach: Thousand-Year Blood War", 2022), ("tv", "Frieren: Beyond Journey's End", 2023),
    ("tv", "Solo Leveling", 2024), ("tv", "Cyberpunk: Edgerunners", 2022),
    ("tv", "Castlevania", 2017), ("tv", "X-Men '97", 2024),
    ("tv", "Daredevil", 2015), ("tv", "The Punisher", 2017),
    ("tv", "Loki", 2021), ("tv", "WandaVision", 2021),
    ("tv", "Squid Game", 2021), ("tv", "Money Heist", 2017),
    ("tv", "Kingdom", 2019), ("tv", "Alice in Borderland", 2020),
    ("tv", "All of Us Are Dead", 2022), ("tv", "The Glory", 2022),
    ("tv", "Crash Landing on You", 2019), ("tv", "Goblin", 2016),
    ("tv", "Signal", 2016), ("tv", "Stranger", 2017),
    ("tv", "Reply 1988", 2015), ("tv", "My Mister", 2018),
    ("tv", "Hospital Playlist", 2020), ("tv", "Moving", 2023),
    ("tv", "Westworld", 2016), ("tv", "Lost", 2004),
    ("tv", "Prison Break", 2005), ("tv", "24", 2001),
    ("tv", "Fringe", 2008), ("tv", "Person of Interest", 2011),
    ("tv", "Hannibal", 2013), ("tv", "Bates Motel", 2013),
    ("tv", "Penny Dreadful", 2014), ("tv", "The Haunting of Hill House", 2018),
    ("tv", "Midnight Mass", 2021), ("tv", "The Fall of the House of Usher", 2023),
    ("tv", "Yellowjackets", 2021), ("tv", "From", 2022),
    ("tv", "The Leftovers", 2014), ("tv", "Watchmen", 2019),
    ("tv", "Station Eleven", 2021), ("tv", "Foundation", 2021),
    ("tv", "For All Mankind", 2019), ("tv", "The Expanse", 2015),
    ("tv", "Altered Carbon", 2018), ("tv", "Sense8", 2015),
    ("tv", "The OA", 2016), ("tv", "1899", 2022),
    ("tv", "Bodies", 2023), ("tv", "3 Body Problem", 2024),
    ("tv", "Dark Matter", 2024), ("tv", "Devs", 2020),
    ("tv", "Utopia", 2013), ("tv", "Broadchurch", 2013),
    ("tv", "Happy Valley", 2014), ("tv", "Luther", 2010),
    ("tv", "Bodyguard", 2018), ("tv", "Slow Horses", 2022),
    ("tv", "The Night Manager", 2016), ("tv", "Homeland", 2011),
]


def _tmdb_search_request(
    api_key: str,
    media_type: str,
    title: str,
    language: str = "tr-TR",
) -> Optional[Dict[str, Any]]:
    endpoint = "/search/tv" if media_type == "tv" else "/search/movie"
    params = {
        "api_key": api_key,
        "query": title,
        "language": language,
        "include_adult": "false",
    }
    url = f"https://api.themoviedb.org/3{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SineMix-Seeder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results") or []
                return results[0] if results else None
    except Exception:
        return None
    return None


def _save_checkpoint(items: List[Dict[str, Any]]) -> None:
    CATALOG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CATALOG_JSON_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, CATALOG_JSON_PATH)


def seed_catalog(custom_list_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    434 yapımlık kataloğu `data/catalog.json` dosyasına çeker ve kaydeder.
    Kaldığı yerden devam etme (Resume) ve her 20 yapımda bir ara kayıt (Checkpoint) içerir.
    """
    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    has_live_api = bool(api_key and api_key != "your_tmdb_api_key_here")

    # Mevcut catalog.json varsa yükle (Kaldığı yerden devam etme / Resume)
    existing_items: List[Dict[str, Any]] = []
    if CATALOG_JSON_PATH.exists():
        try:
            raw = CATALOG_JSON_PATH.read_text(encoding="utf-8").strip()
            loaded = json.loads(raw) if raw else []
            if isinstance(loaded, list):
                existing_items = loaded
        except (json.JSONDecodeError, OSError):
            existing_items = []

    existing_titles_norm = {
        (str(item.get("media_type", "movie")), normalize_search_text(item.get("title", "")))
        for item in existing_items
        if item.get("title")
    } | {
        (str(item.get("media_type", "movie")), normalize_search_text(item.get("original_title", "")))
        for item in existing_items
        if item.get("original_title")
    }
    existing_ids = {
        (int(item.get("tmdb_id", 0)), str(item.get("media_type", "movie")))
        for item in existing_items
    }

    fallback_by_norm_title = {
        normalize_search_text(fb["title"]): fb
        for fb in FALLBACK_TMDB_CATALOG
    }

    # Özel dosya verilmişse oradan oku, yoksa 434'lük master listeyi kullan
    target_entries: List[Tuple[str, str, int]] = []
    if custom_list_file and Path(custom_list_file).exists():
        raw_lines = Path(custom_list_file).read_text(encoding="utf-8").splitlines()
        for line in raw_lines:
            cleaned = clean_bulk_title_line(line)
            if cleaned:
                target_entries.append(("movie", cleaned, 2020))
    else:
        target_entries = list(CURATED_movies_and_shows[:434])

    total_targets = len(target_entries)
    newly_added_since_checkpoint = 0
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"🎬 SineMix Katalog Tohumlama Başlatıldı ({total_targets} Yapım)")
    print(f"📡 Mod: {'Canlı TMDB API v3 (tr-TR + en-US Fallback)' if has_live_api else 'Yerleşik TMDB Şema & Akıllı Katalog Üretici'}")
    print("-" * 68)

    for idx, (m_type, raw_title, default_year) in enumerate(target_entries, start=1):
        norm_title = normalize_search_text(raw_title)

        # Resume Kontrolü: Zaten catalog.json içinde varsa atla
        if (m_type, norm_title) in existing_titles_norm:
            print(f"[{idx}/{total_targets}] Atlandı (Mevcut): {raw_title} ({default_year})")
            continue

        fb_match = fallback_by_norm_title.get(norm_title)
        record: Optional[Dict[str, Any]] = None

        # 1. Canlı TMDB API v3 Sorgusu (`language=tr-TR` + boş özette `en-US` fallback)
        if has_live_api:
            tr_hit = _tmdb_search_request(api_key, m_type, raw_title, language="tr-TR")
            time.sleep(0.15)  # Rate-limit koruması

            if tr_hit and tr_hit.get("id"):
                t_id = int(tr_hit["id"])
                title = tr_hit.get("title") or tr_hit.get("name") or raw_title
                orig_title = tr_hit.get("original_title") or tr_hit.get("original_name") or raw_title
                overview = (tr_hit.get("overview") or "").strip()

                # Türkçe özet boş gelirse en-US fallback
                if not overview:
                    en_hit = _tmdb_search_request(api_key, m_type, raw_title, language="en-US")
                    time.sleep(0.15)
                    if en_hit and en_hit.get("overview"):
                        overview = en_hit["overview"].strip()

                date_str = tr_hit.get("release_date") or tr_hit.get("first_air_date") or ""
                year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else default_year

                g_ids = tr_hit.get("genre_ids") or []
                genre_names = [TMDB_GENRE_MAP.get(gid, "Dram") for gid in g_ids if gid in TMDB_GENRE_MAP]
                inferred_g, inferred_kw = _infer_genres_and_keywords_from_title(title, m_type)
                if not genre_names:
                    genre_names = inferred_g

                poster_raw = tr_hit.get("poster_path")
                backdrop_raw = tr_hit.get("backdrop_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_raw}" if poster_raw else ""
                backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_raw}" if backdrop_raw else poster_url

                record = {
                    "tmdb_id": t_id,
                    "media_type": m_type,
                    "title": title,
                    "original_title": orig_title,
                    "poster_path": poster_url,
                    "backdrop_path": backdrop_url,
                    "overview": overview or f"{title} ({year}) yapımı SineMix kataloğunda.",
                    "release_year": year,
                    "vote_average": round(float(tr_hit.get("vote_average") or 8.0), 1),
                    "genres": normalize_genre_objects(genre_names),
                    "keywords": (fb_match.get("keywords") if fb_match else None) or inferred_kw,
                    "popularity": round(float(tr_hit.get("popularity") or 85.0), 2),
                    "added_at": now_iso,
                }

        # 2. Yerleşik Zengin TMDB Verisi veya Akıllı Katalog Kaydı
        if not record:
            if fb_match:
                record = dict(fb_match)
                record["tmdb_id"] = int(fb_match["tmdb_id"])
                record["media_type"] = fb_match.get("media_type", m_type)
                record["title"] = fb_match["title"]
                record["original_title"] = fb_match.get("original_title") or fb_match["title"]
                record["poster_path"] = fb_match.get("poster_path", "")
                record["backdrop_path"] = fb_match.get("backdrop_path") or fb_match.get("poster_path", "")
                record["overview"] = fb_match.get("overview", "")
                record["release_year"] = int(fb_match.get("release_year", default_year))
                record["vote_average"] = float(fb_match.get("vote_average", 8.5))
                record["genres"] = normalize_genre_objects(fb_match.get("genres"))
                record["popularity"] = round(float(250.0 - (idx * 0.35)), 2)
                record["added_at"] = now_iso
            else:
                hash_int = int(hashlib.md5(norm_title.encode("utf-8")).hexdigest()[:7], 16)
                synthetic_id = 100000 + (hash_int % 890000)
                while (synthetic_id, m_type) in existing_ids:
                    synthetic_id += 1

                inferred_g, inferred_kw = _infer_genres_and_keywords_from_title(raw_title, m_type)
                encoded_label = urllib.parse.quote(raw_title[:28])
                bg_palette = ["141824", "1b1429", "10212b", "241914", "12241b"][hash_int % 5]
                poster_url = f"https://ui-avatars.com/api/?name={encoded_label}&background={bg_palette}&color=f5c518&size=500&bold=true&length=3"

                type_label = "dizisi" if m_type == "tv" else "filmi"
                g_text = ", ".join(inferred_g)
                vote = round(7.6 + ((hash_int % 18) / 10.0), 1)
                popularity = round(max(15.0, 220.0 - (idx * 0.42)), 2)

                record = {
                    "tmdb_id": synthetic_id,
                    "media_type": m_type,
                    "title": raw_title,
                    "original_title": raw_title,
                    "poster_path": poster_url,
                    "backdrop_path": poster_url,
                    "overview": f"{default_year} yapımı {raw_title} {type_label}, {g_text} türlerindeki sürükleyici atmosferi ve güçlü anlatımıyla SineMix kataloğunda yer alıyor.",
                    "release_year": default_year,
                    "vote_average": vote,
                    "genres": normalize_genre_objects(inferred_g),
                    "keywords": inferred_kw,
                    "popularity": popularity,
                    "added_at": now_iso,
                }

        existing_items.append(record)
        existing_titles_norm.add((m_type, norm_title))
        existing_titles_norm.add((record["media_type"], normalize_search_text(record["title"])))
        existing_ids.add((int(record["tmdb_id"]), record["media_type"]))
        newly_added_since_checkpoint += 1

        print(f"[{idx}/{total_targets}] Eklendi: {record['title']} ({record['release_year']})")

        # Her 20 yapımda bir ara kayıt (Checkpoint)
        if newly_added_since_checkpoint >= 20:
            _save_checkpoint(existing_items)
            newly_added_since_checkpoint = 0

    if newly_added_since_checkpoint > 0 or not CATALOG_JSON_PATH.exists():
        _save_checkpoint(existing_items)

    print("-" * 68)
    print(f"✅ Tamamlandı! Toplam {len(existing_items)} yapım `data/catalog.json` dosyasında hazır.")
    return existing_items


if __name__ == "__main__":
    custom_arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    seed_catalog(custom_list_file=custom_arg)
