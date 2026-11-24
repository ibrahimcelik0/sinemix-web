"""
SineMix — 434 Yapımlık Güvenli Katalog Veri Çekme ve Onarım Betiği (`seed_catalog.py`)

Özellikler:
1. Sahte Baş Harfli Eski Kayıtları Temizleme:
   - `data/catalog.json` içindeki `ui-avatars.com` (dev sarı baş harf: TGI, SLI, PFI, 1AM vb.)
     içeren veya 434 yapımlık ana katalog listemizde yer almayan eski başlangıç kayıtlarını
     (`The Godfather Part II`, `12 Angry Men`, `Schindler's List` vb.) tamamen temizler.
2. Poster URL Kontrolü (`format_tmdb_poster_url`):
   - TMDB'den gelen `poster_path` değerinin her zaman `https://image.tmdb.org/t/p/w500` ile
     başlayan tam ve geçerli bir URL olmasını sağlar; çift domain oluşmasını engeller.
   - Gerçek posteri bulunamayan nadir bir yapım olursa harf basmak yerine sade koyu mat
     sinema ikonu (`/static/img/no-poster.svg`) kullanır.
3. Akıllı Arama Eşleşmesi (`_clean_title_variants` & `_smart_tmdb_search`):
   - Türkçe başlıkla yapılan aramada sonuç dönmezse veya ilk sonucun `poster_path` değeri `None` ise;
     başlıktaki `1. BÖLÜM`, `2. BÖLÜM`, `:`, `-` gibi ekleri sadeleştirerek ve sonuçları popülerliğe
     göre sıralayarak posteri olan gerçek TMDB kaydını eşleştirir.
4. Açıklama (`overview`) Kalitesi:
   - Önce `language=tr-TR` ile çeker; Türkçe özet boşsa veya 30 karakterden kısaysa otomatik olarak
     `language=en-US` ile tam özeti çekip kaydeder.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
CATALOG_JSON_PATH = BASE_DIR / "data" / "catalog.json"
VERIFIED_SEED_PATH = BASE_DIR / "app" / "core" / "verified_catalog_seed.json"

from app.config import _load_dotenv_file
from app.core.tmdb_fallback import FALLBACK_TMDB_CATALOG, TMDB_GENRE_MAP
from app.core.utils import normalize_search_text
from app.features.catalog.repository import normalize_genre_objects

_load_dotenv_file(BASE_DIR / ".env")

SYNTHETIC_OVERVIEW_MARKERS = (
    "sürükleyici atmosferi ve güçlü anlatımıyla SineMix kataloğunda yer alıyor",
    "SineMix 434 yapımlık ana arşivinde yer alan",
    "SineMix arşivinde yer alan",
    "yapımı SineMix kataloğunda",
)


def format_tmdb_poster_url(poster_path: Any) -> str:
    """
    TMDB `poster_path` değerini her zaman `https://image.tmdb.org/t/p/w500/...`
    formatında tam ve geçerli bir URL olarak döndürür.
    Çift domain oluşmasını ve `ui-avatars.com` baş harf görsellerini engeller.
    """
    if not poster_path:
        return "/static/img/no-poster.svg"
    clean = str(poster_path).strip()
    if not clean or "ui-avatars.com" in clean:
        return "/static/img/no-poster.svg"

    # Çift domain oluşmuşsa temizle
    if "https://image.tmdb.org/t/p/" in clean:
        idx = clean.rfind("https://image.tmdb.org/t/p/")
        clean = clean[idx:]
        parts = clean.split("/t/p/", 1)[1]
        slash_idx = parts.find("/")
        if slash_idx != -1:
            return f"https://image.tmdb.org/t/p/w500{parts[slash_idx:]}"
        return clean

    if clean.startswith("http://") or clean.startswith("https://"):
        return clean
    if clean.startswith("/static/"):
        return clean
    if not clean.startswith("/"):
        clean = f"/{clean}"
    return f"https://image.tmdb.org/t/p/w500{clean}"


def format_tmdb_backdrop_url(backdrop_path: Any, fallback_poster_url: str) -> str:
    """TMDB `backdrop_path` değerini geçerli `w1280` URL'sine dönüştürür."""
    if backdrop_path:
        clean = str(backdrop_path).strip()
        if clean and "ui-avatars.com" not in clean:
            if "https://image.tmdb.org/t/p/" in clean:
                idx = clean.rfind("https://image.tmdb.org/t/p/")
                return clean[idx:]
            if clean.startswith("http://") or clean.startswith("https://"):
                return clean
            if not clean.startswith("/"):
                clean = f"/{clean}"
            return f"https://image.tmdb.org/t/p/w1280{clean}"
    return fallback_poster_url


def is_valid_overview(overview: Any) -> bool:
    """Açıklamanın boş, 30 karakterden kısa veya eski şablon metin olmadığını doğrular."""
    if not overview:
        return False
    text = str(overview).strip()
    if len(text) < 30:
        return False
    for marker in SYNTHETIC_OVERVIEW_MARKERS:
        if marker.lower() in text.lower():
            return False
    return True


def _clean_title_variants(tr_title: str, en_title: str = "") -> List[str]:
    """
    Aramada eşleşme kalitesini artırmak için başlıktaki `1. BÖLÜM`, `2. BÖLÜM`,
    `BÖLÜM 1`, `:`, `-`, parantez içi notlar gibi ekleri sadeleştirerek
    aday arama başlıkları üretir.
    """
    variants: List[str] = []

    def _add(val: str) -> None:
        v = re.sub(r"\s+", " ", (val or "")).strip(" -–—:.")
        if v and v.lower() not in {x.lower() for x in variants}:
            variants.append(v)

    for raw in (tr_title, en_title):
        if not raw:
            continue
        _add(raw)
        # Parantez içi ifadeleri kaldır
        no_paren = re.sub(r"\s*\(.*?\)\s*", " ", raw)
        _add(no_paren)
        # "1. BÖLÜM", "2. BÖLÜM", "BÖLÜM 1", "PART 1" gibi ekleri temizle
        no_part = re.sub(
            r"\b(?:\d+\.\s*BÖLÜM|BÖLÜM\s*\d+|PART\s*(?:\d+|[IVX]+)|SEZON\s*\d+)\b",
            "",
            no_paren,
            flags=re.IGNORECASE,
        )
        _add(no_part)
        # İki nokta (:) veya tire (-) sonrası alt başlığı sadeleştir
        if ":" in no_part:
            _add(no_part.split(":", 1)[0])
        if " - " in no_part:
            _add(no_part.split(" - ", 1)[0])
        # Sondaki tekil sıra numarasını sadeleştir ("ARABALAR 1" -> "ARABALAR")
        no_trailing_num = re.sub(r"\s+1$", "", no_part)
        _add(no_trailing_num)

    return variants


def _tmdb_api_get(api_key: str, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query_params = {"api_key": api_key}
    query_params.update(params)
    url = f"https://api.themoviedb.org/3{endpoint}?{urllib.parse.urlencode(query_params)}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "SineMix-Seeder/2.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def _smart_tmdb_search(
    api_key: str,
    media_type: str,
    tr_title: str,
    en_title: str = "",
) -> Optional[Dict[str, Any]]:
    """
    1. Türkçe ve temizlenmiş başlık varyantlarıyla TMDB API'de arama yapar.
    2. İlk sonucun `poster_path` değeri `None` ise sonuçları `poster_path` varlığına
       ve popülerliğe (`popularity`) göre sıralayarak posteri olan gerçek TMDB kaydını seçer.
    3. Açıklama (`overview`) `language=tr-TR` sorgusunda boşsa veya 30 karakterden kısaysa
       otomatik olarak `language=en-US` ile tam özeti çeker.
    """
    endpoint = "/search/tv" if media_type == "tv" else "/search/movie"
    variants = _clean_title_variants(tr_title, en_title)

    matched_hit: Optional[Dict[str, Any]] = None

    for lang in ("tr-TR", "en-US"):
        for query_variant in variants:
            data = _tmdb_api_get(
                api_key,
                endpoint,
                {"query": query_variant, "language": lang, "include_adult": "false"},
            )
            time.sleep(0.12)
            results = (data or {}).get("results") or []
            if not results:
                continue

            # Önce poster_path değeri dolu olanları popülerliğe göre sırala
            with_poster = [r for r in results if r.get("poster_path")]
            if with_poster:
                # Başlık benzerliği yüksek ve popülerliği en yüksek olanı seç
                norm_q = normalize_search_text(query_variant)
                exact_poster = [
                    r for r in with_poster
                    if normalize_search_text(r.get("title") or r.get("name") or "") == norm_q
                    or normalize_search_text(r.get("original_title") or r.get("original_name") or "") == norm_q
                ]
                pool = exact_poster if exact_poster else with_poster
                pool.sort(key=lambda r: float(r.get("popularity") or 0.0), reverse=True)
                matched_hit = pool[0]
                break

        if matched_hit:
            break

    if not matched_hit or not matched_hit.get("id"):
        return None

    t_id = int(matched_hit["id"])
    overview = (matched_hit.get("overview") or "").strip()

    # Türkçe özet boşsa veya 30 karakterden kısaysa language=en-US fallback ile tam özeti çek
    if not is_valid_overview(overview):
        en_detail = _tmdb_api_get(api_key, f"/{media_type}/{t_id}", {"language": "en-US"})
        time.sleep(0.12)
        if en_detail and is_valid_overview(en_detail.get("overview")):
            overview = en_detail["overview"].strip()
            if not matched_hit.get("poster_path") and en_detail.get("poster_path"):
                matched_hit["poster_path"] = en_detail["poster_path"]

    matched_hit["overview"] = overview
    return matched_hit


def _save_checkpoint(items: List[Dict[str, Any]]) -> None:
    CATALOG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CATALOG_JSON_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, CATALOG_JSON_PATH)


def fetch_tv_seasons_via_tmdb(api_key: str, tmdb_id: int, fallback_still: str) -> Tuple[int, int, List[Dict[str, Any]]]:
    """
    TMDB `GET /tv/{tmdb_id}` ve her sezon için `GET /tv/{tmdb_id}/season/{season_number}`
    uç noktalarından gerçek sezon (`season_number >= 1`) ve bölüm verilerini çeker.
    """
    tv_data = _tmdb_api_get(api_key, f"/tv/{tmdb_id}", {"language": "tr-TR"})
    if not tv_data or not tv_data.get("id"):
        return 0, 0, []

    raw_seasons = tv_data.get("seasons") or []
    valid_season_nums = sorted({
        int(s.get("season_number") or 0)
        for s in raw_seasons
        if int(s.get("season_number") or 0) >= 1
    })

    seasons_list: List[Dict[str, Any]] = []
    total_episodes = 0

    for s_num in valid_season_nums:
        s_tr = _tmdb_api_get(api_key, f"/tv/{tmdb_id}/season/{s_num}", {"language": "tr-TR"})
        time.sleep(0.12)
        if not s_tr:
            continue

        eps_tr = s_tr.get("episodes") or []
        en_by_num: Dict[int, Dict[str, Any]] = {}
        if any(not (e.get("name") or "").strip() or not (e.get("overview") or "").strip() for e in eps_tr):
            s_en = _tmdb_api_get(api_key, f"/tv/{tmdb_id}/season/{s_num}", {"language": "en-US"})
            time.sleep(0.12)
            if s_en and s_en.get("episodes"):
                en_by_num = {int(e.get("episode_number") or 0): e for e in s_en["episodes"]}

        ep_objs: List[Dict[str, Any]] = []
        for ep in eps_tr:
            ep_num = int(ep.get("episode_number") or 0)
            if ep_num < 1:
                continue
            en_ep = en_by_num.get(ep_num) or {}
            ep_name = (ep.get("name") or "").strip()
            if not ep_name or ep_name.lower().startswith("bölüm "):
                ep_name = (en_ep.get("name") or ep_name or f"{ep_num}. Bölüm").strip()
            ep_ov = (ep.get("overview") or "").strip() or (en_ep.get("overview") or "").strip()
            still_raw = ep.get("still_path")
            still_url = format_tmdb_poster_url(still_raw) if still_raw else fallback_still

            ep_objs.append({
                "season_number": s_num,
                "episode_number": ep_num,
                "name": ep_name,
                "overview": ep_ov,
                "air_date": ep.get("air_date") or s_tr.get("air_date") or "",
                "runtime": int(ep.get("runtime") or 45),
                "still_path": still_url,
            })

        if ep_objs:
            total_episodes += len(ep_objs)
            seasons_list.append({
                "season_number": s_num,
                "name": f"{s_num}. Sezon",
                "episode_count": len(ep_objs),
                "air_date": s_tr.get("air_date") or ep_objs[0]["air_date"],
                "episodes": ep_objs,
            })

    return len(seasons_list), total_episodes, seasons_list


def seed_catalog(force_repair: bool = True) -> List[Dict[str, Any]]:
    """
    434 yapımlık (`60 Dizi` + `11 Çizgi Film` + `363 Film`) SineMix kataloğunu
    doğrular, eski baş harfli (`ui-avatars.com`) sahte kayıtları temizler ve
    tüm yapımların geçerli `https://image.tmdb.org/t/p/w500/...` poster ve
    tam `overview` (>= 30 karakter) alanlarıyla `data/catalog.json` içinde
    yer almasını sağlar.
    """
    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    has_live_api = bool(api_key and api_key != "your_tmdb_api_key_here")

    if not VERIFIED_SEED_PATH.exists():
        raise FileNotFoundError(f"Doğrulanmış katalog tohum dosyası bulunamadı: {VERIFIED_SEED_PATH}")

    verified_seed_items: List[Dict[str, Any]] = json.loads(
        VERIFIED_SEED_PATH.read_text(encoding="utf-8")
    )

    # Mevcut catalog.json içindeki gerçek TMDB kayıtlarını kontrol et,
    # sahte ui-avatars.com veya liste dışı eski kayıtları (The Godfather Part II, 12 Angry Men, Schindler's List vb.) temizle
    existing_valid_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    purged_legacy_count = 0

    allowed_titles_norm = {
        (str(item["media_type"]), normalize_search_text(item["title"]))
        for item in verified_seed_items
    } | {
        (str(item["media_type"]), normalize_search_text(item.get("tr_title", "")))
        for item in verified_seed_items
        if item.get("tr_title")
    }

    if CATALOG_JSON_PATH.exists():
        try:
            raw = CATALOG_JSON_PATH.read_text(encoding="utf-8").strip()
            loaded = json.loads(raw) if raw else []
            if isinstance(loaded, list):
                for item in loaded:
                    m_type = str(item.get("media_type", "movie"))
                    norm_t = normalize_search_text(item.get("title", ""))
                    norm_tr = normalize_search_text(item.get("tr_title", ""))
                    p_url = str(item.get("poster_path") or "").strip()
                    ov = str(item.get("overview") or "").strip()

                    is_allowed = ((m_type, norm_t) in allowed_titles_norm) or ((m_type, norm_tr) in allowed_titles_norm)
                    has_real_tmdb_poster = (
                        p_url.startswith("https://image.tmdb.org/t/p/w500/")
                        and "ui-avatars.com" not in p_url
                        and "image.tmdb.org/t/p/w500/https://" not in p_url
                    )

                    if is_allowed and has_real_tmdb_poster and is_valid_overview(ov):
                        existing_valid_by_key[(m_type, norm_t)] = item
                    else:
                        purged_legacy_count += 1
        except (json.JSONDecodeError, OSError):
            existing_valid_by_key = {}

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    final_catalog: List[Dict[str, Any]] = []
    seen_ids = set()
    updated_count = 0

    print(f"🎬 SineMix 434 Yapımlık Katalog Doğrulama & Onarım Başlatıldı")
    if purged_legacy_count > 0:
        print(f"🧹 Temizlenen sahte baş harfli / liste dışı eski kayıt sayısı: {purged_legacy_count}")
    print(f"📡 Mod: {'Canlı TMDB API v3 + Doğrulanmış TMDB Arşivi' if has_live_api else 'Doğrulanmış TMDB Poster & Açıklama Arşivi'}")
    print("-" * 72)

    for idx, seed_item in enumerate(verified_seed_items, start=1):
        m_type = str(seed_item["media_type"])
        en_title = str(seed_item["title"])
        tr_title = str(seed_item.get("tr_title") or en_title)
        norm_t = normalize_search_text(en_title)

        existing = existing_valid_by_key.get((m_type, norm_t))
        record = dict(existing) if (existing and not force_repair) else dict(seed_item)

        # Canlı TMDB API anahtarı varsa ve poster/özet güncellenmek istenirse canlı sorgula
        if has_live_api and (not record.get("poster_path") or not is_valid_overview(record.get("overview"))):
            live_hit = _smart_tmdb_search(api_key, m_type, tr_title, en_title)
            if live_hit:
                record["tmdb_id"] = int(live_hit["id"])
                if live_hit.get("poster_path"):
                    record["poster_path"] = format_tmdb_poster_url(live_hit["poster_path"])
                if live_hit.get("backdrop_path"):
                    record["backdrop_path"] = format_tmdb_backdrop_url(
                        live_hit["backdrop_path"], record["poster_path"]
                    )
                if is_valid_overview(live_hit.get("overview")):
                    record["overview"] = live_hit["overview"].strip()

        # Poster URL ve Overview kalite doğrulaması
        record["poster_path"] = format_tmdb_poster_url(record.get("poster_path") or seed_item["poster_path"])
        record["backdrop_path"] = format_tmdb_backdrop_url(
            record.get("backdrop_path") or seed_item.get("backdrop_path"),
            record["poster_path"],
        )
        if not is_valid_overview(record.get("overview")):
            record["overview"] = seed_item["overview"].strip()

        record["genres"] = normalize_genre_objects(record.get("genres") or seed_item.get("genres"))
        record["added_at"] = record.get("added_at") or now_iso

        # Diziler için sezon ve bölüm listesi önbellek kontrolü
        if m_type == "tv":
            if existing and existing.get("seasons"):
                record["seasons"] = existing["seasons"]
                record["number_of_seasons"] = int(existing.get("number_of_seasons") or len(existing["seasons"]))
                record["number_of_episodes"] = int(
                    existing.get("number_of_episodes")
                    or sum(len(s.get("episodes") or []) for s in existing["seasons"])
                )
            elif has_live_api and not record.get("seasons"):
                n_s, n_e, s_list = fetch_tv_seasons_via_tmdb(
                    api_key,
                    int(record["tmdb_id"]),
                    record.get("backdrop_path") or record["poster_path"],
                )
                if s_list:
                    record["seasons"] = s_list
                    record["number_of_seasons"] = n_s
                    record["number_of_episodes"] = n_e

        t_id = int(record["tmdb_id"])
        while (t_id, m_type) in seen_ids:
            t_id += 1
        record["tmdb_id"] = t_id
        seen_ids.add((t_id, m_type))

        final_catalog.append(record)
        updated_count += 1

        if idx % 20 == 0 or idx == len(verified_seed_items):
            _save_checkpoint(final_catalog)
            print(f"[{idx}/{len(verified_seed_items)}] Doğrulandı & Kaydedildi: {record['title']} ({record['release_year']}) -> {record['poster_path']}")

    print("-" * 72)
    print(f"✅ Katalog Onarımı Tamamlandı! Toplam {len(final_catalog)} yapım `data/catalog.json` içinde hazır.")
    return final_catalog


if __name__ == "__main__":
    seed_catalog(force_repair=True)
