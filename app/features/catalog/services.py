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
        return "/static/img/no-poster.svg"
    clean = str(poster_path).strip()
    if not clean or "ui-avatars.com" in clean:
        return "/static/img/no-poster.svg"
    if clean.startswith("https://image.tmdb.org/t/p/"):
        return clean
    if clean.startswith("http://") or clean.startswith("https://"):
        return clean
    if not clean.startswith("/"):
        clean = f"/{clean}"
    return f"https://image.tmdb.org/t/p/w500{clean}"


def _format_backdrop_url(backdrop_path: Optional[str], fallback_poster: Optional[str] = None) -> str:
    if backdrop_path:
        clean = str(backdrop_path).strip()
        if clean and "ui-avatars.com" not in clean:
            if clean.startswith("https://image.tmdb.org/t/p/"):
                return clean
            if clean.startswith("http://") or clean.startswith("https://"):
                return clean
            if not clean.startswith("/"):
                clean = f"/{clean}"
            return f"https://image.tmdb.org/t/p/w1280{clean}"
    return _format_poster_url(fallback_poster)


def _format_profile_url(profile_path: Optional[str], name: str = "") -> str:
    if profile_path:
        clean = str(profile_path).strip()
        if clean and "ui-avatars.com" not in clean:
            if clean.startswith("https://image.tmdb.org/t/p/"):
                return clean
            if clean.startswith("http://") or clean.startswith("https://"):
                return clean
            if not clean.startswith("/"):
                clean = f"/{clean}"
            return f"https://image.tmdb.org/t/p/w185{clean}"
    return "/static/img/no-avatar.svg"


def _format_still_url(still_path: Optional[str], fallback_url: str = "/static/img/no-poster.svg") -> str:
    if still_path:
        clean = str(still_path).strip()
        if clean and "ui-avatars.com" not in clean:
            if clean.startswith("https://image.tmdb.org/t/p/"):
                return clean
            if clean.startswith("http://") or clean.startswith("https://"):
                return clean
            if clean.startswith("/static/"):
                return clean
            if not clean.startswith("/"):
                clean = f"/{clean}"
            return f"https://image.tmdb.org/t/p/w500{clean}"
    return fallback_url


def _fetch_tmdb_tv_seasons(
    tmdb_id: int,
    raw_seasons_meta: List[Dict[str, Any]],
    fallback_still: str,
) -> List[Dict[str, Any]]:
    """
    TMDB `GET /tv/{tmdb_id}/season/{season_number}` uç noktasından
    `season_number >= 1` olan gerçek sezonların tüm bölümlerini çeker.
    Türkçe bölüm adı veya özeti boşsa `en-US` fallback uygular.
    """
    seasons_result: List[Dict[str, Any]] = []
    valid_season_nums = sorted({
        int(s.get("season_number") or 0)
        for s in (raw_seasons_meta or [])
        if int(s.get("season_number") or 0) >= 1
    })

    for s_num in valid_season_nums:
        s_tr = _tmdb_get(f"/tv/{tmdb_id}/season/{s_num}", {"language": "tr-TR"})
        if not s_tr:
            continue
        raw_eps_tr = s_tr.get("episodes") or []
        en_eps_by_num: Dict[int, Dict[str, Any]] = {}

        # Herhangi bir bölümde Türkçe isim veya özet eksikse en-US sezon verisini çek
        needs_en = any(
            not (ep.get("name") or "").strip() or not (ep.get("overview") or "").strip()
            for ep in raw_eps_tr
        )
        if needs_en:
            s_en = _tmdb_get(f"/tv/{tmdb_id}/season/{s_num}", {"language": "en-US"})
            if s_en and s_en.get("episodes"):
                en_eps_by_num = {
                    int(e.get("episode_number") or 0): e for e in s_en["episodes"]
                }

        episodes_list: List[Dict[str, Any]] = []
        for ep in raw_eps_tr:
            ep_num = int(ep.get("episode_number") or 0)
            if ep_num < 1:
                continue
            en_ep = en_eps_by_num.get(ep_num) or {}
            ep_name = (ep.get("name") or "").strip()
            if not ep_name or ep_name.lower().startswith("bölüm "):
                ep_name = (en_ep.get("name") or ep_name or f"{ep_num}. Bölüm").strip()
            ep_overview = (ep.get("overview") or "").strip() or (en_ep.get("overview") or "").strip()
            episodes_list.append({
                "season_number": s_num,
                "episode_number": ep_num,
                "name": ep_name,
                "overview": ep_overview,
                "air_date": ep.get("air_date") or s_tr.get("air_date") or "",
                "runtime": int(ep.get("runtime") or 45),
                "still_path": _format_still_url(ep.get("still_path"), fallback_still),
            })

        if episodes_list:
            seasons_result.append({
                "season_number": s_num,
                "name": f"{s_num}. Sezon",
                "episode_count": len(episodes_list),
                "air_date": s_tr.get("air_date") or episodes_list[0]["air_date"],
                "episodes": episodes_list,
            })

    return seasons_result


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

    # 1. Akıllı Önbellek (Sıfır Tekrar İstek):
    # Veriler `data/catalog.json` içinde zaten mevcutsa (diziler için `seasons` dahil) tekrar TMDB API isteği atma!
    has_cached_seasons = bool(fb_item and (media_type != "tv" or fb_item.get("seasons")))
    needs_live_enrichment = is_tmdb_live_enabled() and (not fb_item or not has_cached_seasons)
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

            poster_url = _format_poster_url(data.get("poster_path"))
            backdrop_url = _format_backdrop_url(data.get("backdrop_path"), poster_url)

            # Süre & Format + Diziler için Sezon/Bölüm Listesi (GET /tv/{id}/season/{season_number})
            runtime = data.get("runtime")
            runtime_formatted = format_runtime(runtime) if media_type == "movie" else ""
            seasons_list: List[Dict[str, Any]] = []
            if media_type == "tv":
                seasons_list = (fb_item.get("seasons") if fb_item else None) or _fetch_tmdb_tv_seasons(
                    tmdb_id=int(data["id"]),
                    raw_seasons_meta=data.get("seasons") or [],
                    fallback_still=backdrop_url or poster_url,
                )

            number_of_seasons = len(seasons_list) if seasons_list else int(data.get("number_of_seasons") or 0)
            number_of_episodes = (
                sum(len(s.get("episodes") or []) for s in seasons_list)
                if seasons_list
                else int(data.get("number_of_episodes") or 0)
            )
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
                "seasons": seasons_list,
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

    # 2. Doğrudan `data/catalog.json` (CatalogRepository) Üzerinden Sıfır Gecikmeyle Oku
    if not item_detail and fb_item:
        media_type = fb_item["media_type"]
        raw_status = fb_item.get("status", "Released")
        raw_lang = fb_item.get("original_language", "en")

        runtime_formatted = fb_item.get("runtime_formatted") or (format_runtime(fb_item.get("runtime")) if media_type == "movie" else "")
        seasons_list = list(fb_item.get("seasons") or [])
        seasons = int(fb_item.get("number_of_seasons") or (len(seasons_list) if seasons_list else 1))
        episodes = int(
            fb_item.get("number_of_episodes")
            or (sum(len(s.get("episodes") or []) for s in seasons_list) if seasons_list else 1)
        )
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
            "seasons": seasons_list,
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
            matches_title = (
                fuzzy_text_match(item.get("title", ""), clean_query)
                or fuzzy_text_match(item.get("original_title", ""), clean_query)
                or fuzzy_text_match(item.get("tr_title", ""), clean_query)
            )
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
# ==============================================================================
# DİSNEY+ TARZI SİNEMA EVRENLERİ & STÜDYO KOLEKSİYONLARI
# ==============================================================================

COLLECTIONS_METADATA = [
    {
        "slug": "marvel",
        "title": "Marvel Evreni",
        "group": "universe",
        "icon": "🦸‍♂️",
        "tagline": "Sonsuzluk Taşları'ndan Çoklu Evren'e uzanan dev süper kahraman destanı.",
        "why_watch": "Bağımsız kahraman hikayelerinin yıllar içinde devasa bir ortak evrende birleşmesini, yüksek tempolu aksiyonu ve unutulmaz takım dinamiklerini deneyimlemek için seçmelisin.",
        "watch_order_note": "Karakter gelişimlerini, Sonsuzluk Taşları'nın hikayesini ve Endgame gibi büyük kırılma anlarının duygusal karşılığını tam almak için kronolojik/çıkış sırasıyla izlenmelidir.",
        "is_sequential": True,
        "keywords": [
            "iron man", "kaptan amerika", "captain america", "thor", "yenilmezler",
            "avengers", "örümcek-adam", "spider-man", "doktor strange", "doctor strange",
            "galaksinin koruyucuları", "guardians of the galaxy", "ant-man", "black panther",
            "deadpool", "x-men", "wolverine", "venom", "daredevil", "loki",
            "wandavision", "punisher", "moon knight", "hawkeye", "what if"
        ],
    },
    {
        "slug": "star-wars",
        "title": "Star Wars Evreni",
        "group": "universe",
        "icon": "⚔️",
        "tagline": "Uzak bir galakside Güç'ün aydınlık ve karanlık tarafının efsanevi savaşı.",
        "why_watch": "Sinema tarihinin en ikonik mitolojisini, unutulmaz müziklerini ve galaktik politik entrikalarla örülü epik maceralarını yaşamak için bu evrene girmelisin.",
        "watch_order_note": "Skywalker ailesinin yükselişi ile İmparatorluk dönemi arasındaki geçişleri ve The Mandalorian gibi yan dizilerdeki sürpriz bağlantıları kaçırmamak için hikaye sırası kritik önem taşır.",
        "is_sequential": True,
        "keywords": ["star wars", "rogue one", "han solo", "mandalorian", "obi-wan"],
    },
    {
        "slug": "dc",
        "title": "DC Evreni",
        "group": "universe",
        "icon": "🦇",
        "tagline": "Gotham'ın karanlık sokaklarından Metropolis'in tanrısal kahramanlarına.",
        "why_watch": "Daha karanlık, psikolojik derinliği yüksek ve ikonik kötü karakterleriyle öne çıkan gerçekçi süper kahraman hikayeleri arıyorsan DC evreni tam sana göre.",
        "watch_order_note": "Kara Şövalye üçlemesi ve Joker gibi bağımsız başyapıtları kendi içinde sırayla, Adalet Birliği hattını ise Man of Steel'den başlayarak takip etmen önerilir.",
        "is_sequential": True,
        "keywords": [
            "batman", "kara şövalye", "dark knight", "çelik adam", "man of steel",
            "adalet birliği", "justice league", "joker", "wonder woman", "aquaman",
            "shazam", "intihar timi", "suicide squad"
        ],
    },
    {
        "slug": "fantasy-worlds",
        "title": "Orta Dünya & Büyücülük",
        "group": "universe",
        "icon": "🧙‍♂️",
        "tagline": "Yüzüklerin Efendisi ve Harry Potter'ın büyüleyici fantastik dünyaları.",
        "why_watch": "İnce ince işlenmiş evren kuralları, dostluk teması ve sinema tarihine damga vurmuş destansı yolculuklarla bambaşka dünyalara kaçmak için seçmelisin.",
        "watch_order_note": "Karakterlerin ilk adımdan büyük savaşa evrilen büyüme yolculuğunu ve evren gizemlerini adım adım çözmek için seri sırasını bozmadan izlemek şarttır.",
        "is_sequential": True,
        "keywords": [
            "yüzüklerin efendisi", "lord of the rings", "hobbit",
            "harry potter", "fantastik canavarlar", "fantastic beasts"
        ],
    },
    {
        "slug": "twd",
        "title": "The Walking Dead Evreni",
        "group": "universe",
        "icon": "🧟",
        "tagline": "Kıyamet sonrası dünyada asıl tehlike ölüler değil, hayatta kalanlardır.",
        "why_watch": "İnsan psikolojisinin sınırlarını zorlayan hayatta kalma mücadelesi, yüksek gerilim ve yıllarca süren derin karakter bağları için bu evreni seçmelisin.",
        "watch_order_note": "Ana dizideki karakter ayrılıklarının ve Dead City, Daryl Dixon gibi yan dizilerdeki yeni yolculukların zaman çizelgesini kaçırmamak için sırayla izlenmelidir.",
        "is_sequential": True,
        "keywords": ["walking dead", "dead city", "daryl dixon", "ones who live"],
    },
    {
        "slug": "pixar",
        "title": "Pixar Animasyon",
        "group": "studio",
        "icon": "💡",
        "tagline": "Her yaşa dokunan derin hikayeler ve görsel şölen.",
        "why_watch": "Sadece çocuklara değil yetişkinlere de hayat, dostluk ve duygular üzerine derin alt metinler sunan, gözyaşartıcı ve kusursuz anlatımlar için seçmelisin.",
        "watch_order_note": "Çoğu yapım bağımsız birer başyapıttır; Oyuncak Hikayesi ve Arabalar gibi serileri kendi içinde sırayla izlemek nostaljik bağları güçlendirir.",
        "is_sequential": False,
        "keywords": [
            "arabalar", "cars", "oyuncak hikayesi", "toy story", "inanılmaz aile",
            "incredibles", "kayıp balık", "nemo", "dory", "sevimli canavarlar",
            "monsters", "ters yüz", "inside out", "coco", "soul", "ratatuy",
            "ratatouille", "yukarı bak", "up", "vol-i", "wall-e", "luca",
            "bir böceğin yaşamı", "iyi bir dinozor", "hadi gidelim"
        ],
    },
    {
        "slug": "walt-disney",
        "title": "Walt Disney Animasyon",
        "group": "studio",
        "icon": "🏰",
        "tagline": "Klasikleşmiş masallar, unutulmaz müzikler ve büyülü dünyalar.",
        "why_watch": "Sıcak aile atmosferi, ikonik müzikal sahneler ve nesiller boyu eskimeyen zamansız animasyon klasikleri için Walt Disney seçkisini tercih etmelisin.",
        "watch_order_note": "Her yapım kendi bağımsız masalını anlatır; Karlar Ülkesi, Moana ve Zootropolis gibi devam filmlerini sıralı izlemen yeterlidir.",
        "is_sequential": False,
        "keywords": [
            "aslan kral", "lion king", "karlar ülkesi", "frozen", "moana",
            "zootropolis", "zootopia", "rapunzel", "tangled", "güzel ve çirkin",
            "beauty and the beast", "cesur", "brave", "6 süper kahraman",
            "big hero 6", "christopher robin"
        ],
    },
    {
        "slug": "dreamworks-family",
        "title": "DreamWorks & Aile",
        "group": "studio",
        "icon": "🐉",
        "tagline": "Yüksek mizah, tempo ve unutulmaz animasyon serileri.",
        "why_watch": "Kung Fu Panda ve Ejderhanı Nasıl Eğitirsin gibi hem güldüren hem de epik macera sunan yüksek enerjili animasyon serileri arıyorsan doğru yerdesin.",
        "watch_order_note": "Karakterlerin usta-çırak ve dostluk gelişimlerini eksiksiz takip etmek için üçlemeleri çıkış sırasıyla izlemen tavsiye edilir.",
        "is_sequential": False,
        "keywords": [
            "kung fu panda", "ejderhanı nasıl eğitirsin", "how to train your dragon",
            "buz devri", "ice age", "çılgın hırsız", "despicable me",
            "minyonlar", "minions", "küçük prens"
        ],
    },
]


COLLECTIONS = COLLECTIONS_METADATA


class CollectionDict(dict):
    """
    Hem Python içinde `collection["items"]` erişimini hem de Jinja2 şablonlarında
    `{% for item in collection.items %}` nokta notasyonunu destekleyen sözlük sınıfı.
    """

    @property
    def items(self):  # type: ignore[override]
        return self.get("items", [])


def _keyword_matches_text(kw: str, combined_text: str, words_set: set[str]) -> bool:
    kw_low = kw.lower().strip()
    if len(kw_low) <= 3 and " " not in kw_low:
        return kw_low in words_set
    return kw_low in combined_text


def _match_collection_items(all_items: list[dict], keywords: list[str], is_sequential: bool) -> list[dict]:
    import re
    matched = []
    for item in all_items:
        title = (item.get("title") or "").lower()
        orig_title = (item.get("original_title") or "").lower()
        tr_title = (item.get("tr_title") or "").lower()
        combined = f"{title} {orig_title} {tr_title}"
        words_set = set(re.findall(r"[a-z0-9ğüşıöç]+", combined))
        if any(_keyword_matches_text(kw, combined, words_set) for kw in keywords):
            matched.append(item)

    if is_sequential:
        matched.sort(
            key=lambda x: (
                int(x.get("release_year") or x.get("year") or 9999),
                str(x.get("release_date") or "9999"),
            )
        )
    else:
        matched.sort(key=lambda x: float(x.get("popularity") or 0), reverse=True)
    return matched


def get_all_collections() -> dict:
    """Tüm Sinema Evrenleri ve Stüdyo koleksiyonlarını yapım sayılarıyla döndürür."""
    all_items = search_multi_catalog(query="", media_type="ALL", genre="ALL", sort_by="popularity")
    universes = []
    studios = []

    for col in COLLECTIONS_METADATA:
        items = _match_collection_items(all_items, col["keywords"], col["is_sequential"])
        entry = CollectionDict({
            **col,
            "items": items,
            "count": len(items),
            "preview_posters": [i.get("poster_path") for i in items[:4] if i.get("poster_path")],
        })
        if col["group"] == "universe":
            universes.append(entry)
        else:
            studios.append(entry)

    return {"universes": universes, "studios": studios}


def get_collection_by_slug(slug: str) -> dict | None:
    """Belirli bir slug'a ait koleksiyon bilgisini ve içindeki yapımları döndürür."""
    target = next((c for c in COLLECTIONS_METADATA if c["slug"] == slug), None)
    if not target:
        return None

    all_items = search_multi_catalog(query="", media_type="ALL", genre="ALL", sort_by="popularity")
    items = _match_collection_items(all_items, target["keywords"], target["is_sequential"])
    return CollectionDict({
        **target,
        "items": items,
        "count": len(items),
        "preview_posters": [i.get("poster_path") for i in items[:4] if i.get("poster_path")],
    })

