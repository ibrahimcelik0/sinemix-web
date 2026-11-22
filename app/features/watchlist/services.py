"""
Watchlist feature iş mantığı:
- Tekil ve Toplu (500+ yapım Bulk Import) izleme listesi yönetimi
- Satır başı numara temizleyici (`1- `, `24. `, `#12 ` vb.)
- Yerel TMDB Meta Veri Önbelleği (`data/tmdb_cache.json`) ile tekrarlayan API isteklerini önleme
"""

import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.tmdb_fallback import FALLBACK_TMDB_CATALOG, TMDB_GENRE_MAP
from app.core.utils import fuzzy_text_match, normalize_search_text
from app.features.watchlist.repository import WatchlistRepository


# Satır başındaki numaraları (1-, 24., 105), •, -, #12 vb.) temizleyen düzenli ifade
LINE_PREFIX_REGEX = re.compile(
    r"^\s*(?:[#•\-\*\+]+|\d+\s*[\-\.\)\:\]\–\—]+|\[\d+\]\s*)+\s*",
    re.UNICODE,
)
TRAILING_YEAR_REGEX = re.compile(r"\s*\((19\d{2}|20\d{2})\)\s*$")


def _get_cache_file_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    cache_path = base_dir / "data" / "tmdb_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    return cache_path


def _load_tmdb_cache() -> Dict[str, Dict[str, Any]]:
    cache_path = _get_cache_file_path()
    if not cache_path.exists():
        return {}
    try:
        raw = cache_path.read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_tmdb_cache(cache_data: Dict[str, Dict[str, Any]]) -> None:
    cache_path = _get_cache_file_path()
    try:
        cache_path.write_text(
            json.dumps(cache_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def get_cached_tmdb_item(tmdb_id: int) -> Optional[Dict[str, Any]]:
    """Önbellekte kayıtlı bir TMDB yapımını ID ile döndürür."""
    cache = _load_tmdb_cache()
    for val in cache.values():
        if int(val.get("tmdb_id", 0)) == int(tmdb_id):
            return val
    return None


def clean_bulk_title_line(raw_line: str) -> str:
    """
    Kullanıcının yapıştırdığı satırdaki `1- `, `24. `, `434) `, `• ` gibi
    numara ve işaretleri temizleyerek saf film/dizi başlığını döndürür.
    """
    if not raw_line:
        return ""
    line = raw_line.strip()
    if not line:
        return ""
    cleaned = LINE_PREFIX_REGEX.sub("", line).strip()
    cleaned = TRAILING_YEAR_REGEX.sub("", cleaned).strip()
    cleaned = cleaned.strip("\"'“”‘’")
    return cleaned


def _infer_genres_and_keywords_from_title(title: str, media_type: str) -> Tuple[List[str], List[str]]:
    """
    Canlı TMDB API anahtarı tanımlı olmadığında ve yapım sabit katalogda yer almadığında,
    başlık ve medya türünden anlamlı tür ve anahtar kelime vektörü üretir.
    """
    norm = normalize_search_text(title)
    genres: List[str] = []
    keywords: List[str] = []

    rules = [
        (["space", "star", "alien", "cyber", "future", "robot", "matrix", "dune", "blade", "mars", "time", "uzay", "bilim"], ["Bilim Kurgu", "Macera"], ["space travel", "future", "dystopia", "science"]),
        (["dark", "crime", "detective", "murder", "killer", "prison", "gang", "mafia", "godfather", "kartel", "suc"], ["Suç", "Gerilim", "Dram"], ["organized crime", "psychological thriller", "detective", "morality"]),
        (["war", "battle", "soldier", "army", "savas", "history", "empire", "king"], ["Savaş", "Tarih", "Dram"], ["historical events", "survival", "empire", "rebellion"]),
        (["magic", "dragon", "lord", "ring", "witch", "fantasy", "harry", "potter", "game of", "avatar"], ["Fantastik", "Macera"], ["destiny", "parallel world", "supernatural", "life journey"]),
        (["horror", "dead", "zombie", "ghost", "fear", "nightmare", "korku", "scream", "evil"], ["Korku", "Gerilim", "Gizem"], ["survival", "apocalypse", "mystery", "supernatural"]),
        (["love", "romance", "heart", "wedding", "ask", "romantik"], ["Romantik", "Dram"], ["friendship", "life journey", "optimism"]),
        (["anime", "naruto", "piece", "titan", "demon", "ghoul", "hunter", "bleach", "note", "fullmetal", "jujutsu", "chainsaw", "ball"], ["Animasyon", "Aksiyon", "Fantastik"], ["rebellion", "destiny", "friendship", "supernatural"]),
        (["comedy", "funny", "office", "friends", "brooklyn", "komedi", "rick", "morty", "simpsons"], ["Komedi", "Macera"], ["friendship", "optimism", "life journey"]),
    ]

    for triggers, g_list, kw_list in rules:
        if any(t in norm for t in triggers):
            for g in g_list:
                if g not in genres:
                    genres.append(g)
            for kw in kw_list:
                if kw not in keywords:
                    keywords.append(kw)

    if not genres:
        if media_type == "tv":
            genres = ["Dram", "Gizem", "Gerilim"]
            keywords = ["mystery", "psychological thriller", "transformation", "drama"]
        else:
            genres = ["Dram", "Aksiyon", "Macera"]
            keywords = ["life journey", "transformation", "destiny", "cinema"]

    return genres[:3], keywords[:5]


def resolve_title_for_bulk_import(
    raw_title: str,
    preferred_media_type: str = "auto",
    cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Tek bir film/dizi başlığını şu sırayla çözer:
    1. Yerel TMDB Önbelleği (`data/tmdb_cache.json`) -> 0ms
    2. Yerleşik Zengin TMDB Kataloğu (`FALLBACK_TMDB_CATALOG`) -> 0ms
    3. Canlı TMDB API (`/search/multi`, `/search/movie`, `/search/tv`) -> varsa çeker ve önbelleğe yazar
    4. Akıllı Katalog Çözücü (TMDB_API_KEY girilmemişse bile 500+ yapımın tamamını
       deterministik ID, afiş, tür ve anahtar kelimelerle kaydeder).
    """
    clean_title = clean_bulk_title_line(raw_title)
    if not clean_title or len(clean_title) < 2:
        return None

    norm_key = f"{preferred_media_type}:{normalize_search_text(clean_title)}"
    if cache is not None and norm_key in cache:
        return dict(cache[norm_key])

    # 1. Doğrudan `data/catalog.json` (CatalogRepository) Üzerinde Ara (0ms)
    from app.features.catalog.repository import CatalogRepository
    norm_query = normalize_search_text(clean_title)
    for item in CatalogRepository.get_all():
        if preferred_media_type in ("movie", "tv") and item["media_type"] != preferred_media_type:
            continue
        if normalize_search_text(item["title"]) == norm_query or fuzzy_text_match(item["title"], clean_title):
            resolved = {
                "tmdb_id": int(item["tmdb_id"]),
                "media_type": item["media_type"],
                "title": item["title"],
                "poster_path": item["poster_path"],
                "genres": list(item.get("genres") or []),
                "keywords": list(item.get("keywords") or []),
                "release_year": item.get("release_year", 2022),
                "vote_average": item.get("vote_average", 8.0),
                "overview": item.get("overview", ""),
            }
            if cache is not None:
                cache[norm_key] = resolved
            return resolved

    # 2. Canlı TMDB API Üzerinden Ara (TMDB_API_KEY mevcutsa)
    from app.features.catalog.services import _format_poster_url, _tmdb_get, is_tmdb_live_enabled

    if is_tmdb_live_enabled():
        endpoint = "/search/multi"
        if preferred_media_type == "movie":
            endpoint = "/search/movie"
        elif preferred_media_type == "tv":
            endpoint = "/search/tv"

        api_data = _tmdb_get(endpoint, {"query": clean_title, "include_adult": "false"})
        results = (api_data or {}).get("results") or []
        for raw in results:
            m_type = raw.get("media_type") or (preferred_media_type if preferred_media_type in ("movie", "tv") else "movie")
            if m_type not in ("movie", "tv"):
                continue

            t_id = int(raw["id"])
            title = raw.get("title") or raw.get("name") or clean_title
            g_ids = raw.get("genre_ids") or []
            genres = [TMDB_GENRE_MAP.get(gid, "Dram") for gid in g_ids if gid in TMDB_GENRE_MAP]
            inferred_g, inferred_kw = _infer_genres_and_keywords_from_title(title, m_type)
            if not genres:
                genres = inferred_g

            date_str = raw.get("release_date") or raw.get("first_air_date") or ""
            year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else 2022

            resolved = {
                "tmdb_id": t_id,
                "media_type": m_type,
                "title": title,
                "poster_path": _format_poster_url(raw.get("poster_path")),
                "genres": genres,
                "keywords": inferred_kw,
                "release_year": year,
                "vote_average": round(float(raw.get("vote_average") or 7.8), 1),
                "overview": raw.get("overview") or f"{title} yapımı toplu liste aktarımı ile eklendi.",
            }
            if cache is not None:
                cache[norm_key] = resolved
            return resolved

    # 3. Akıllı Deterministik Katalog Kaydı (500+ yapım çevrimdışı/API'siz aktarılırken hiçbir yapım kaybolmasın)
    hash_int = int(hashlib.md5(norm_query.encode("utf-8")).hexdigest()[:7], 16)
    synthetic_id = 9000000 + (hash_int % 900000)

    if preferred_media_type in ("movie", "tv"):
        m_type = preferred_media_type
    else:
        tv_hints = ["season", "sezon", "dizi", "series", "show", "anime", "episode", "bolum"]
        m_type = "tv" if any(h in norm_query for h in tv_hints) else "movie"

    genres, keywords = _infer_genres_and_keywords_from_title(clean_title, m_type)
    encoded_label = urllib.parse.quote(clean_title[:28])
    bg_palette = ["141824", "1b1429", "10212b", "241914", "12241b"][hash_int % 5]
    poster_url = f"https://ui-avatars.com/api/?name={encoded_label}&background={bg_palette}&color=f5c518&size=500&bold=true&length=3"

    resolved = {
        "tmdb_id": synthetic_id,
        "media_type": m_type,
        "title": clean_title,
        "poster_path": poster_url,
        "genres": genres,
        "keywords": keywords,
        "release_year": 2000 + (hash_int % 25),
        "vote_average": round(7.2 + ((hash_int % 20) / 10.0), 1),
        "overview": f"{clean_title}, SineMix Toplu Liste İçe Aktarma motoru ile izleme listenize eklendi.",
    }
    if cache is not None:
        cache[norm_key] = resolved
    return resolved


def process_bulk_import_chunk(
    raw_lines: List[str],
    preferred_media_type: str = "auto",
    default_rating: int = 8,
    existing_keys_from_client: Optional[List[str]] = None,
    persist_to_user_file: bool = True,
) -> Dict[str, Any]:
    """
    Toplu liste aktarımında gönderilen başlık grubunu (chunk) işler,
    mükerrerleri atlar ve sonuç istatistiklerini döndürür.
    """
    rating = max(1, min(10, int(default_rating)))
    media_mode = preferred_media_type if preferred_media_type in ("auto", "movie", "tv") else "auto"

    cache = _load_tmdb_cache()
    cache_dirty = False
    initial_cache_len = len(cache)

    existing_client_set: Set[str] = set(existing_keys_from_client or [])

    resolved_records: List[Dict[str, Any]] = []
    not_found_titles: List[str] = []
    client_skipped = 0

    for raw_line in raw_lines:
        clean_name = clean_bulk_title_line(raw_line)
        if not clean_name:
            continue

        resolved = resolve_title_for_bulk_import(
            raw_title=clean_name,
            preferred_media_type=media_mode,
            cache=cache,
        )
        if not resolved:
            not_found_titles.append(clean_name)
            continue

        item_key = f"{resolved['media_type']}_{resolved['tmdb_id']}"
        title_key = normalize_search_text(resolved["title"])

        if item_key in existing_client_set or title_key in existing_client_set:
            client_skipped += 1
            continue

        existing_client_set.add(item_key)
        existing_client_set.add(title_key)

        resolved["user_rating"] = rating
        resolved_records.append(resolved)

    if len(cache) != initial_cache_len:
        _save_tmdb_cache(cache)

    if persist_to_user_file:
        bulk_result = WatchlistRepository.bulk_upsert(
            records=resolved_records,
            skip_existing=True,
        )
        return {
            "status": "ok",
            "added_items": bulk_result["added_items"],
            "added_count": bulk_result["added_count"],
            "skipped_count": bulk_result["skipped_count"] + client_skipped,
            "not_found_count": len(not_found_titles),
            "not_found_titles": not_found_titles,
            "stats": get_watchlist_stats(),
        }

    # Misafir modu (Bellek içi)
    return {
        "status": "ok",
        "added_items": resolved_records,
        "added_count": len(resolved_records),
        "skipped_count": client_skipped,
        "not_found_count": len(not_found_titles),
        "not_found_titles": not_found_titles,
    }


def get_user_watchlist() -> List[Dict[str, Any]]:
    """Kullanıcının izleme listesindeki tüm yapımları döndürür (Sınırsız kapasite)."""
    return WatchlistRepository.get_all()


def get_watchlist_stats() -> Dict[str, Any]:
    """İzleme listesi özet istatistiklerini döndürür."""
    items = WatchlistRepository.get_all()
    if not items:
        return {
            "total": 0,
            "movie_count": 0,
            "tv_count": 0,
            "avg_rating": 0.0,
            "liked_count": 0,
        }

    total = len(items)
    movie_count = sum(1 for i in items if i.get("media_type") == "movie")
    tv_count = sum(1 for i in items if i.get("media_type") == "tv")
    ratings = [int(i.get("user_rating", 0)) for i in items]
    avg_rating = round(sum(ratings) / total, 1) if total else 0.0
    liked_count = sum(1 for r in ratings if r >= 7)

    return {
        "total": total,
        "movie_count": movie_count,
        "tv_count": tv_count,
        "avg_rating": avg_rating,
        "liked_count": liked_count,
    }


def add_or_rate_watchlist_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Yapımı kullanıcının JSON dosyasına ekler veya puanını günceller.
    Eklendiği anda `genres` ve `keywords` verilerini bir kez çekip JSON'a kaydeder.
    """
    tmdb_id = int(payload["tmdb_id"])
    media_type = str(payload.get("media_type", "movie")).lower()
    user_rating = max(1, min(10, int(float(payload.get("user_rating", 8)))))

    title = payload.get("title")
    poster_path = payload.get("poster_path")
    genres = payload.get("genres") or []
    keywords = payload.get("keywords") or []

    if not title or not genres or not keywords:
        from app.features.catalog.services import fetch_item_details_with_keywords
        details = fetch_item_details_with_keywords(tmdb_id=tmdb_id, media_type=media_type)
        if details:
            title = title or details.get("title")
            poster_path = poster_path or details.get("poster_path")
            if not genres:
                genres = details.get("genres") or []
            if not keywords:
                keywords = details.get("keywords") or []

    if not genres or not keywords:
        inf_g, inf_kw = _infer_genres_and_keywords_from_title(title or "Film", media_type)
        if not genres:
            genres = inf_g
        if not keywords:
            keywords = inf_kw

    return WatchlistRepository.upsert({
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": title or "Bilinmeyen Yapım",
        "poster_path": poster_path or "",
        "user_rating": user_rating,
        "genres": genres,
        "keywords": keywords,
    })


def remove_watchlist_item(tmdb_id: int, media_type: str = "movie") -> bool:
    """Yapımı izleme listesinden çıkarır."""
    return WatchlistRepository.delete(tmdb_id=tmdb_id, media_type=media_type)


def seed_sample_watchlist() -> List[Dict[str, Any]]:
    """Örnek izleme listesini yükler."""
    return WatchlistRepository.seed_sample_data()


def clear_user_watchlist() -> None:
    """Tüm izleme listesini sıfırlar."""
    WatchlistRepository.clear_all()
