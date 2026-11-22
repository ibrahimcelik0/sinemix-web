"""
Catalog feature iş mantığı:
TMDB API (/search/multi, /movie/{id}, /tv/{id} + append_to_response=credits,videos,recommendations,keywords)
entegrasyonu ve kapsamlı içerik detay biçimlendirme servisi.
"""

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from flask import current_app

from app.core.tmdb_fallback import (
    FALLBACK_TMDB_CATALOG,
    LANGUAGE_NAME_MAP,
    STATUS_TR_MAP,
    TMDB_GENRE_MAP,
)
from app.core.utils import EVRENSEL_TURLER, FILM_VERITABANI, fuzzy_text_match, normalize_search_text
from app.features.catalog.repository import CatalogRepository
from app.features.watchlist.repository import WatchlistRepository


LEGACY_ID_TO_TMDB: Dict[int, Dict[str, Any]] = {
    1825: {"tmdb_id": 155, "media_type": "movie"},
    2225: {"tmdb_id": 27205, "media_type": "movie"},
    1425: {"tmdb_id": 157336, "media_type": "movie"},
    1725: {"tmdb_id": 603, "media_type": "movie"},
    1925: {"tmdb_id": 752, "media_type": "movie"},
    6225: {"tmdb_id": 299534, "media_type": "movie"},
    7325: {"tmdb_id": 13, "media_type": "movie"},
}


def resolve_legacy_id(item_id: int, default_media_type: str = "movie") -> Dict[str, Any]:
    """Eski 4 haneli demo ID'leri gerçek TMDB ID ve media_type değerine dönüştürür."""
    if item_id in LEGACY_ID_TO_TMDB:
        return LEGACY_ID_TO_TMDB[item_id]
    cat_item = CatalogRepository.get_by_id(item_id)
    if cat_item:
        return {"tmdb_id": int(cat_item["tmdb_id"]), "media_type": cat_item["media_type"]}
    return {"tmdb_id": int(item_id), "media_type": default_media_type}


def _get_tmdb_api_key() -> str:
    try:
        key = current_app.config.get("TMDB_API_KEY", "")
        if key:
            return key.strip()
    except RuntimeError:
        pass
    return os.environ.get("TMDB_API_KEY", "").strip()


def is_tmdb_live_enabled() -> bool:
    """TMDB_API_KEY tanımlı mı kontrol eder."""
    key = _get_tmdb_api_key()
    return bool(key and key != "your_tmdb_api_key_here")


def _tmdb_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """TMDB v3 REST API'sine GET isteği gönderir."""
    api_key = _get_tmdb_api_key()
    if not api_key:
        return None

    query_params: Dict[str, Any] = {"api_key": api_key, "language": "tr-TR"}
    if params:
        query_params.update(params)

    url = f"https://api.themoviedb.org/3{endpoint}?{urllib.parse.urlencode(query_params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SineMix/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return None


def _format_poster_url(poster_path: Optional[str]) -> str:
    if not poster_path:
        return "https://images.pexels.com/photos/7991579/pexels-photo-7991579.jpeg?auto=compress&cs=tinysrgb&w=500"
    if poster_path.startswith("http://") or poster_path.startswith("https://"):
        return poster_path
    return f"https://image.tmdb.org/t/p/w500{poster_path}"


def _format_backdrop_url(backdrop_path: Optional[str], fallback_poster: Optional[str] = None) -> str:
    if backdrop_path:
        if backdrop_path.startswith("http://") or backdrop_path.startswith("https://"):
            return backdrop_path
        return f"https://image.tmdb.org/t/p/w1280{backdrop_path}"
    return _format_poster_url(fallback_poster)


def _format_profile_url(profile_path: Optional[str], name: str = "") -> str:
    if profile_path:
        if profile_path.startswith("http://") or profile_path.startswith("https://"):
            return profile_path
        return f"https://image.tmdb.org/t/p/w185{profile_path}"
    encoded_name = urllib.parse.quote(name or "Oyuncu")
    return f"https://ui-avatars.com/api/?name={encoded_name}&background=1f1f2e&color=f5c518&size=185&bold=true"


def format_currency(amount: Optional[int]) -> str:
    """Bütçe ve gişe hasılatını '$160.000.000' formatına dönüştürür; 0 ise 'Belirtilmemiş' döner."""
    if not amount or int(amount) <= 0:
        return "Belirtilmemiş"
    formatted = f"{int(amount):,}".replace(",", ".")
    return f"${formatted}"


def format_runtime(minutes: Optional[int]) -> str:
    """Dakika cinsinden süreyi '2 sa 49 dk' formatına dönüştürür."""
    if not minutes or int(minutes) <= 0:
        return "Belirtilmemiş"
    total_mins = int(minutes)
    hours = total_mins // 60
    mins = total_mins % 60
    if hours > 0 and mins > 0:
        return f"{hours} sa {mins} dk"
    if hours > 0:
        return f"{hours} sa"
    return f"{mins} dk"


def fetch_item_details_with_keywords(tmdb_id: int, media_type: str = "movie") -> Optional[Dict[str, Any]]:
    """İzleme listesine kayıt sırasında temel detayları ve anahtar kelimeleri çeker."""
    full_detail = fetch_comprehensive_item_detail(tmdb_id=tmdb_id, media_type=media_type)
    if not full_detail:
        return None
    return {
        "tmdb_id": full_detail["tmdb_id"],
        "media_type": full_detail["media_type"],
        "title": full_detail["title"],
        "release_year": full_detail["release_year"],
        "vote_average": full_detail["vote_average"],
        "poster_path": full_detail["poster_path"],
        "genres": full_detail["genres"],
        "keywords": full_detail["keywords"],
        "overview": full_detail["overview"],
    }


def fetch_comprehensive_item_detail(tmdb_id: int, media_type: str = "movie") -> Optional[Dict[str, Any]]:
    """
    Tek bir API isteğiyle (`append_to_response=credits,videos,recommendations,keywords`)
    Sinematik İçerik Detay Sayfası (`/detail/<media_type>/<int:tmdb_id>`) için
    tüm teknik künye, kadro, fragman, finansal veri, benzer yapımlar ve kullanıcı eşleşme analizini getirir.
    """
    resolved = resolve_legacy_id(tmdb_id, media_type)
    tmdb_id = int(resolved["tmdb_id"])
    media_type = "tv" if str(resolved["media_type"]).lower() == "tv" else "movie"

    catalog_all = CatalogRepository.get_all()
    catalog_by_id = {int(c["tmdb_id"]): c for c in catalog_all}
    fb_item = CatalogRepository.get_by_id(tmdb_id, media_type) or catalog_by_id.get(tmdb_id)

    item_detail: Optional[Dict[str, Any]] = None

    # 1. Yalnızca detay sayfasında ek veriler (cast / trailer_key) eksikse ve Canlı TMDB API aktifse çekip catalog.json'a önbellekle
    needs_live_enrichment = is_tmdb_live_enabled() and (not fb_item or not fb_item.get("cast"))
    if needs_live_enrichment:
        data = _tmdb_get(
            f"/{media_type}/{tmdb_id}",
            {"append_to_response": "credits,videos,recommendations,keywords", "include_video_language": "tr,en,null"},
        )
        if data and data.get("id"):
            title = data.get("title") or data.get("name") or "Bilinmeyen Yapım"
            original_title = data.get("original_title") or data.get("original_name") or title
            tagline = data.get("tagline") or (fb_item.get("tagline") if fb_item else "") or ""
            date_str = data.get("release_date") or data.get("first_air_date") or ""
            release_year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else 2024
            genres = [g.get("name") for g in (data.get("genres") or []) if g.get("name")]

            raw_status = data.get("status") or "Released"
            status_tr = STATUS_TR_MAP.get(raw_status, raw_status)
            raw_lang = (data.get("original_language") or "en").lower()
            lang_tr = LANGUAGE_NAME_MAP.get(raw_lang, raw_lang.upper())

            # Süre & Format
            runtime = data.get("runtime")
            runtime_formatted = format_runtime(runtime) if media_type == "movie" else ""
            number_of_seasons = data.get("number_of_seasons") or 0
            number_of_episodes = data.get("number_of_episodes") or 0
            format_summary = (
                runtime_formatted
                if media_type == "movie"
                else f"{number_of_seasons} Sezon • {number_of_episodes} Bölüm"
            )

            # Finansal Veriler
            budget_formatted = format_currency(data.get("budget")) if media_type == "movie" else "Belirtilmemiş"
            revenue_formatted = format_currency(data.get("revenue")) if media_type == "movie" else "Belirtilmemiş"

            # Anahtar Kelimeler
            kw_block = data.get("keywords") or {}
            kw_list = kw_block.get("keywords") or kw_block.get("results") or []
            keywords = [k.get("name").lower() for k in kw_list if k.get("name")][:12]

            # Ekip & Kadro (credits)
            credits_block = data.get("credits") or {}
            crew_list = credits_block.get("crew") or []
            cast_raw = credits_block.get("cast") or []

            if media_type == "movie":
                directors = [c.get("name") for c in crew_list if c.get("job") == "Director" and c.get("name")]
                creator_or_director = ", ".join(directors[:2]) if directors else (fb_item.get("director", "Belirtilmemiş") if fb_item else "Belirtilmemiş")
            else:
                creators = [c.get("name") for c in (data.get("created_by") or []) if c.get("name")]
                creator_or_director = ", ".join(creators[:2]) if creators else (fb_item.get("director", "Belirtilmemiş") if fb_item else "Belirtilmemiş")

            cast_list: List[Dict[str, str]] = []
            for member in cast_raw[:10]:
                m_name = member.get("name") or ""
                if not m_name:
                    continue
                cast_list.append({
                    "name": m_name,
                    "character": member.get("character") or "Başrol",
                    "profile_path": _format_profile_url(member.get("profile_path"), m_name),
                })

            # Fragman (videos)
            videos_block = (data.get("videos") or {}).get("results") or []
            trailer_key = ""
            for vid in videos_block:
                if vid.get("site") == "YouTube" and vid.get("type") == "Trailer" and vid.get("key"):
                    trailer_key = vid["key"]
                    break
            if not trailer_key:
                for vid in videos_block:
                    if vid.get("site") == "YouTube" and vid.get("key"):
                        trailer_key = vid["key"]
                        break
            if not trailer_key and fb_item:
                trailer_key = fb_item.get("trailer_key", "")

            # Benzer Yapımlar (recommendations)
            recs_raw = (data.get("recommendations") or {}).get("results") or []
            similar_items: List[Dict[str, Any]] = []
            for r in recs_raw[:6]:
                if not r.get("id"):
                    continue
                r_type = r.get("media_type") or media_type
                if r_type not in ("movie", "tv"):
                    r_type = media_type
                r_date = r.get("release_date") or r.get("first_air_date") or ""
                r_year = int(r_date[:4]) if len(r_date) >= 4 and r_date[:4].isdigit() else 2024
                similar_items.append({
                    "tmdb_id": int(r["id"]),
                    "media_type": r_type,
                    "title": r.get("title") or r.get("name") or "Yapım",
                    "release_year": r_year,
                    "vote_average": round(float(r.get("vote_average") or 7.5), 1),
                    "poster_path": _format_poster_url(r.get("poster_path")),
                })

            poster_url = _format_poster_url(data.get("poster_path"))
            backdrop_url = _format_backdrop_url(data.get("backdrop_path"), poster_url)

            item_detail = {
                "tmdb_id": int(data["id"]),
                "media_type": media_type,
                "title": title,
                "original_title": original_title,
                "tagline": tagline,
                "overview": data.get("overview") or (fb_item.get("overview") if fb_item else ""),
                "release_year": release_year,
                "release_date": date_str or str(release_year),
                "vote_average": round(float(data.get("vote_average") or 8.0), 1),
                "genres": genres,
                "keywords": keywords,
                "status": status_tr,
                "original_language": lang_tr,
                "runtime_formatted": runtime_formatted,
                "number_of_seasons": number_of_seasons,
                "number_of_episodes": number_of_episodes,
                "format_summary": format_summary,
                "budget_formatted": budget_formatted,
                "revenue_formatted": revenue_formatted,
                "director_or_creator": creator_or_director,
                "cast": cast_list,
                "trailer_key": trailer_key,
                "poster_path": poster_url,
                "backdrop_path": backdrop_url,
                "similar_items": similar_items,
            }
            # Çekilen detayları data/catalog.json içine önbellekle
            CatalogRepository.upsert_catalog_item(item_detail)

    # 2. Doğrudan `data/catalog.json` (CatalogRepository) Üzerinden Oku
    if not item_detail and fb_item:
        media_type = fb_item["media_type"]
        raw_status = fb_item.get("status", "Released")
        raw_lang = fb_item.get("original_language", "en")

        runtime_formatted = fb_item.get("runtime_formatted") or (format_runtime(fb_item.get("runtime")) if media_type == "movie" else "")
        seasons = int(fb_item.get("number_of_seasons") or 1)
        episodes = int(fb_item.get("number_of_episodes") or 10)
        format_summary = (
            runtime_formatted
            if media_type == "movie"
            else f"{seasons} Sezon • {episodes} Bölüm"
        )

        cast_list = []
        for member in (fb_item.get("cast") or [])[:10]:
            m_name = member.get("name", "")
            cast_list.append({
                "name": m_name,
                "character": member.get("character", "Başrol"),
                "profile_path": _format_profile_url(member.get("profile_path"), m_name),
            })

        similar_items = []
        for rec_id in (fb_item.get("recommended_ids") or [])[:6]:
            target = catalog_by_id.get(int(rec_id))
            if target:
                similar_items.append({
                    "tmdb_id": int(target["tmdb_id"]),
                    "media_type": target["media_type"],
                    "title": target["title"],
                    "release_year": target.get("release_year", 2024),
                    "vote_average": target.get("vote_average", 8.0),
                    "poster_path": target["poster_path"],
                })

        # recommended_ids boşsa aynı türdeki katalog yapımlarından benzer 6 yapım seç
        if not similar_items:
            fb_genres = set(fb_item.get("genres") or [])
            for candidate in catalog_all:
                if int(candidate["tmdb_id"]) == int(fb_item["tmdb_id"]):
                    continue
                if fb_genres & set(candidate.get("genres") or []):
                    similar_items.append({
                        "tmdb_id": int(candidate["tmdb_id"]),
                        "media_type": candidate["media_type"],
                        "title": candidate["title"],
                        "release_year": candidate.get("release_year", 2022),
                        "vote_average": candidate.get("vote_average", 8.0),
                        "poster_path": candidate["poster_path"],
                    })
                if len(similar_items) >= 6:
                    break

        item_detail = {
            "tmdb_id": int(fb_item["tmdb_id"]),
            "media_type": media_type,
            "title": fb_item["title"],
            "original_title": fb_item.get("original_title") or fb_item["title"],
            "tagline": fb_item.get("tagline") or "",
            "overview": fb_item.get("overview") or "",
            "release_year": fb_item.get("release_year", 2024),
            "release_date": fb_item.get("release_date") or str(fb_item.get("release_year", 2024)),
            "vote_average": fb_item.get("vote_average", 8.0),
            "genres": list(fb_item.get("genres") or []),
            "keywords": list(fb_item.get("keywords") or []),
            "status": STATUS_TR_MAP.get(raw_status, raw_status),
            "original_language": LANGUAGE_NAME_MAP.get(raw_lang, raw_lang.upper()),
            "runtime_formatted": runtime_formatted,
            "number_of_seasons": seasons,
            "number_of_episodes": episodes,
            "format_summary": format_summary,
            "budget_formatted": format_currency(fb_item.get("budget")) if media_type == "movie" else "Belirtilmemiş",
            "revenue_formatted": format_currency(fb_item.get("revenue")) if media_type == "movie" else "Belirtilmemiş",
            "director_or_creator": fb_item.get("director") or "Belirtilmemiş",
            "cast": cast_list,
            "trailer_key": fb_item.get("trailer_key") or "",
            "poster_path": fb_item["poster_path"],
            "backdrop_path": fb_item.get("backdrop_path") or fb_item["poster_path"],
            "similar_items": similar_items,
        }

    if not item_detail:
        # 2.B) Toplu İçe Aktarma (Bulk Import) Önbelleği veya Kullanıcının İzleme Listesinden Çözümle
        from app.features.watchlist.services import get_cached_tmdb_item
        cached = get_cached_tmdb_item(tmdb_id) or WatchlistRepository.get_by_id(tmdb_id, media_type)
        if cached:
            m_type = cached.get("media_type", media_type)
            item_detail = {
                "tmdb_id": int(cached["tmdb_id"]),
                "media_type": m_type,
                "title": cached.get("title", "Yapım"),
                "original_title": cached.get("title", "Yapım"),
                "tagline": "SineMix Katalog & Toplu Liste İçe Aktarma Kaydı",
                "overview": cached.get("overview") or f"{cached.get('title')} yapımı izleme listenizde yer alıyor.",
                "release_year": cached.get("release_year", 2022),
                "release_date": str(cached.get("release_year", 2022)),
                "vote_average": cached.get("vote_average", 8.0),
                "genres": list(cached.get("genres") or ["Dram"]),
                "keywords": list(cached.get("keywords") or []),
                "status": "Yayınlandı",
                "original_language": "İngilizce (EN)",
                "runtime_formatted": "2 sa 10 dk" if m_type == "movie" else "",
                "number_of_seasons": 1,
                "number_of_episodes": 12,
                "format_summary": "2 sa 10 dk" if m_type == "movie" else "1 Sezon • 12 Bölüm",
                "budget_formatted": "Belirtilmemiş",
                "revenue_formatted": "Belirtilmemiş",
                "director_or_creator": "Belirtilmemiş",
                "cast": [],
                "trailer_key": "",
                "poster_path": cached.get("poster_path", _format_poster_url(None)),
                "backdrop_path": cached.get("poster_path", _format_poster_url(None)),
                "similar_items": [],
            }

    if not item_detail:
        return None

    # 3. Kullanıcı İzleme Listesi Durumu (`data/watchlist.json`) ve Öneri Eşleşme Analizi
    watched_entry = WatchlistRepository.get_by_id(
        tmdb_id=item_detail["tmdb_id"],
        media_type=item_detail["media_type"],
    )
    item_detail["in_watchlist"] = watched_entry is not None
    item_detail["user_rating"] = int(watched_entry["user_rating"]) if watched_entry else None

    from app.features.recommendations.services import evaluate_single_item_match
    match_analysis = evaluate_single_item_match(item_detail)
    item_detail["match_score"] = match_analysis["match_score"]
    item_detail["matched_genres"] = match_analysis["matched_genres"]
    item_detail["matched_keywords"] = match_analysis["matched_keywords"]
    item_detail["seed_sources"] = match_analysis["seed_sources"]
    item_detail["why_recommended"] = match_analysis["why_recommended"]

    return item_detail


def search_multi_catalog(
    query: str = "",
    media_type: str = "ALL",
    genre: str = "ALL",
    sort_by: str = "popularity",
) -> List[Dict[str, Any]]:
    """
    TMDB API'ye canlı istek atmak yerine doğrudan `data/catalog.json`
    (`CatalogRepository`) üzerinden milisaniyeler içinde okuma ve filtreleme yapar.
    """
    watchlist_items = WatchlistRepository.get_all()
    watched_lookup = {
        (int(w["tmdb_id"]), w.get("media_type", "movie")): int(w.get("user_rating", 0))
        for w in watchlist_items
    }

    catalog_items = CatalogRepository.get_all()
    results: List[Dict[str, Any]] = []
    clean_query = (query or "").strip()

    for item in catalog_items:
        m_type = item["media_type"]
        if media_type in ("movie", "tv") and m_type != media_type:
            continue

        if genre and genre != "ALL":
            if not any(normalize_search_text(g) == normalize_search_text(genre) for g in item.get("genres", [])):
                continue

        if clean_query:
            matches_title = fuzzy_text_match(item.get("title", ""), clean_query) or fuzzy_text_match(item.get("original_title", ""), clean_query)
            matches_kw = any(fuzzy_text_match(kw, clean_query) for kw in item.get("keywords", []))
            matches_dir = fuzzy_text_match(item.get("director", ""), clean_query)
            if not (matches_title or matches_kw or matches_dir):
                continue

        t_id = int(item["tmdb_id"])
        enriched = dict(item)
        enriched["user_rating"] = watched_lookup.get((t_id, m_type))
        enriched["in_watchlist"] = (t_id, m_type) in watched_lookup
        results.append(enriched)

    if sort_by == "title-asc":
        results.sort(key=lambda x: normalize_search_text(x.get("title", "")))
    elif sort_by == "rating-desc":
        results.sort(key=lambda x: float(x.get("vote_average", 0)), reverse=True)
    elif sort_by == "year-desc":
        results.sort(key=lambda x: int(x.get("release_year", 0)), reverse=True)
    else:
        results.sort(key=lambda x: float(x.get("popularity", 0)), reverse=True)

    return results


def get_available_genres() -> List[str]:
    return EVRENSEL_TURLER
