"""
Kullanıcıya özel izleme listelerini yerel `data/watchlists/<user_id>.json`
dosyalarında izole olarak yöneten veri erişim katmanı.

Kritik Kural:
- Oturum açmamış (Misafir) kullanıcılar için sunucudaki hiçbir `.json` dosyasına
  okuma veya yazma yapılmaz; `get_all()` her zaman boş liste (`[]`) döner.
- Oturum açmış kullanıcılar için tüm veriler `data/watchlists/<user_id>.json`
  dosyasından okunur ve bu dosyaya kalıcı olarak kaydedilir.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from flask import has_request_context, session

MIN_WATCH_YEAR = 2020
MAX_WATCH_YEAR = 2026
DEFAULT_WATCH_YEAR = 2026

TR_MONTH_NAMES: Dict[int, str] = {
    1: "Ocak",
    2: "Şubat",
    3: "Mart",
    4: "Nisan",
    5: "Mayıs",
    6: "Haziran",
    7: "Temmuz",
    8: "Ağustos",
    9: "Eylül",
    10: "Ekim",
    11: "Kasım",
    12: "Aralık",
}


def get_default_today_watched_at() -> str:
    """Varsayılan izlenme tarihini 2026 yılı içinde bugünün tarihi (YYYY-MM-DD) olarak döndürür."""
    now = datetime.now(timezone.utc)
    year = now.year if MIN_WATCH_YEAR <= now.year <= MAX_WATCH_YEAR else DEFAULT_WATCH_YEAR
    return f"{year:04d}-{now.month:02d}-{now.day:02d}"


def parse_and_normalize_watched_date(
    raw_watched_at: Any = None,
    fallback_added_at: Any = None,
) -> Tuple[str, int, int]:
    """
    `watched_at` tarih dizgesinden (`YYYY-MM-DD`) geçerli `(watched_at, watched_year, watched_month)`
    üçlüsünü ayıklar.
    - Yıl `2020` ile `2026` arasında sınırlandırılır.
    - Mevcut kayıtlarda tarih yoksa varsayılan yıl her zaman `2026` kabul edilir.
    """
    candidate = str(raw_watched_at or "").strip()
    match = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", candidate)
    if match:
        y = int(match.group(1))
        m = int(match.group(2))
        d = int(match.group(3) or 1)
        y = max(MIN_WATCH_YEAR, min(MAX_WATCH_YEAR, y))
        m = max(1, min(12, m))
        d = max(1, min(28 if m == 2 else (30 if m in (4, 6, 9, 11) else 31), d))
        return f"{y:04d}-{m:02d}-{d:02d}", y, m

    fb_str = str(fallback_added_at or "").strip()
    fb_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", fb_str)
    if fb_match:
        m = max(1, min(12, int(fb_match.group(2))))
        d = max(1, min(28 if m == 2 else 30, int(fb_match.group(3))))
        return f"{DEFAULT_WATCH_YEAR:04d}-{m:02d}-{d:02d}", DEFAULT_WATCH_YEAR, m

    today_str = get_default_today_watched_at()
    parts = today_str.split("-")
    return today_str, int(parts[0]), int(parts[1])


def format_turkish_date_range(start_date_raw: Any, end_date_raw: Any = None) -> str:
    """
    Başlama ve bitiş tarihlerini ('YYYY-MM-DD') Türkçe okunaklı tarih aralığına dönüştürür:
    - '2026-11-25', '2026-11-26' -> '25–26 Kasım 2026'
    - '2026-11-25', '2026-11-25' -> '25 Kasım 2026'
    - '2026-10-31', '2026-11-02' -> '31 Ekim – 2 Kasım 2026'
    - '2025-12-30', '2026-01-02' -> '30 Aralık 2025 – 2 Ocak 2026'
    """
    s_str, s_y, s_m = parse_and_normalize_watched_date(start_date_raw)
    e_str, e_y, e_m = parse_and_normalize_watched_date(end_date_raw or s_str, s_str)

    if e_str < s_str:
        s_str, e_str = e_str, s_str
        s_y, e_y = e_y, s_y
        s_m, e_m = e_m, s_m

    s_d = int(s_str.split("-")[2])
    e_d = int(e_str.split("-")[2])
    s_month_name = TR_MONTH_NAMES.get(s_m, "")
    e_month_name = TR_MONTH_NAMES.get(e_m, "")

    if s_str == e_str:
        return f"{s_d} {s_month_name} {s_y}"
    if s_y == e_y and s_m == e_m:
        return f"{s_d}–{e_d} {s_month_name} {s_y}"
    if s_y == e_y:
        return f"{s_d} {s_month_name} – {e_d} {e_month_name} {s_y}"
    return f"{s_d} {s_month_name} {s_y} – {e_d} {e_month_name} {e_y}"


def normalize_tv_season_watch_dates(
    raw_seasons: Any,
    fallback_start: str = "",
    fallback_end: str = "",
) -> List[Dict[str, Any]]:
    """
    Diziler için sezon bazlı başlama ve bitiş tarihlerini normalize eder:
    `[{"season_number": 1, "start_date": "2026-11-10", "end_date": "2026-11-18", "label": "1. Sezon: 10–18 Kasım 2026"}, ...]`
    """
    by_season: Dict[int, Dict[str, Any]] = {}
    if isinstance(raw_seasons, list):
        for s_entry in raw_seasons:
            if not isinstance(s_entry, dict):
                continue
            s_num = max(1, int(s_entry.get("season_number") or 1))
            s_start, _, _ = parse_and_normalize_watched_date(s_entry.get("start_date") or fallback_start)
            s_end, _, _ = parse_and_normalize_watched_date(s_entry.get("end_date") or s_start)
            if s_end < s_start:
                s_start, s_end = s_end, s_start
            rng_label = format_turkish_date_range(s_start, s_end)
            by_season[s_num] = {
                "season_number": s_num,
                "start_date": s_start,
                "end_date": s_end,
                "label": f"{s_num}. Sezon: {rng_label}",
            }
    elif isinstance(raw_seasons, dict):
        for k, s_entry in raw_seasons.items():
            if not isinstance(s_entry, dict):
                continue
            s_num = max(1, int(s_entry.get("season_number") or (int(k) if str(k).isdigit() else 1)))
            s_start, _, _ = parse_and_normalize_watched_date(s_entry.get("start_date") or fallback_start)
            s_end, _, _ = parse_and_normalize_watched_date(s_entry.get("end_date") or s_start)
            if s_end < s_start:
                s_start, s_end = s_end, s_start
            rng_label = format_turkish_date_range(s_start, s_end)
            by_season[s_num] = {
                "season_number": s_num,
                "start_date": s_start,
                "end_date": s_end,
                "label": f"{s_num}. Sezon: {rng_label}",
            }

    if not by_season and (fallback_start or fallback_end):
        s_start, _, _ = parse_and_normalize_watched_date(fallback_start or fallback_end)
        s_end, _, _ = parse_and_normalize_watched_date(fallback_end or s_start)
        if s_end < s_start:
            s_start, s_end = s_end, s_start
        rng_label = format_turkish_date_range(s_start, s_end)
        by_season[1] = {
            "season_number": 1,
            "start_date": s_start,
            "end_date": s_end,
            "label": f"1. Sezon: {rng_label}",
        }

    return [by_season[k] for k in sorted(by_season.keys())]


class WatchlistRepository:
    """
    Kullanıcı bazlı `data/watchlists/<user_id>.json` dosyalarını yöneten Repository sınıfı.
    Misafir modunda hiçbir dosyaya kayıt yapmaz.
    """

    @staticmethod
    def _get_data_root() -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        return base_dir / "data"

    @classmethod
    def _get_watchlists_dir(cls) -> Path:
        watchlists_dir = cls._get_data_root() / "watchlists"
        watchlists_dir.mkdir(parents=True, exist_ok=True)
        return watchlists_dir

    @staticmethod
    def _resolve_user_id(user_id: Optional[str] = None) -> Optional[str]:
        if user_id:
            return str(user_id).strip()
        if has_request_context():
            active_id = session.get("user_id")
            if active_id:
                return str(active_id).strip()
        return None

    @classmethod
    def get_user_file_path(cls, user_id: str) -> Path:
        safe_id = "".join(ch for ch in str(user_id) if ch.isalnum() or ch in ("_", "-"))
        if not safe_id:
            raise ValueError("Geçersiz user_id")
        return cls._get_watchlists_dir() / f"{safe_id}.json"

    @classmethod
    def ensure_user_watchlist_file(cls, user_id: str) -> Path:
        target_path = cls.get_user_file_path(user_id)
        if not target_path.exists():
            target_path.write_text("[]", encoding="utf-8")
        return target_path

    @classmethod
    def get_all(cls, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Aktif oturumdaki kullanıcının izleme listesini döndürür.
        Misafir (oturum açmamış) kullanıcılar için her zaman boş liste (`[]`) döner.
        """
        uid = cls._resolve_user_id(user_id)
        if not uid:
            return []

        file_path = cls.ensure_user_watchlist_file(uid)
        try:
            raw_content = file_path.read_text(encoding="utf-8").strip()
            if not raw_content:
                return []
            data = json.loads(raw_content)
            if not isinstance(data, list):
                return []
            normalized_list: List[Dict[str, Any]] = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                item_copy = dict(entry)
                m_type = str(item_copy.get("media_type", "movie")).lower()
                w_start, _, _ = parse_and_normalize_watched_date(
                    item_copy.get("watch_start_date") or item_copy.get("watched_at"),
                    item_copy.get("added_at"),
                )
                w_end, w_year, w_month = parse_and_normalize_watched_date(
                    item_copy.get("watch_end_date") or item_copy.get("watched_at") or w_start,
                    item_copy.get("added_at"),
                )
                if w_end < w_start:
                    w_start, w_end = w_end, w_start

                if m_type == "tv":
                    seasons_dates = normalize_tv_season_watch_dates(
                        item_copy.get("season_watch_dates"),
                        fallback_start=w_start,
                        fallback_end=w_end,
                    )
                    if seasons_dates:
                        w_start = min(s["start_date"] for s in seasons_dates)
                        w_end = max(s["end_date"] for s in seasons_dates)
                        _, w_year, w_month = parse_and_normalize_watched_date(w_end)
                    item_copy["season_watch_dates"] = seasons_dates
                    item_copy["watched_date_label"] = " • ".join(s["label"] for s in seasons_dates)
                else:
                    item_copy["season_watch_dates"] = []
                    item_copy["watched_date_label"] = format_turkish_date_range(w_start, w_end)

                item_copy["watch_start_date"] = w_start
                item_copy["watch_end_date"] = w_end
                item_copy["watched_at"] = w_end
                item_copy["watched_year"] = int(item_copy.get("watched_year") or w_year)
                if not (MIN_WATCH_YEAR <= item_copy["watched_year"] <= MAX_WATCH_YEAR):
                    item_copy["watched_year"] = DEFAULT_WATCH_YEAR
                item_copy["watched_month"] = int(item_copy.get("watched_month") or w_month)
                if not (1 <= item_copy["watched_month"] <= 12):
                    item_copy["watched_month"] = w_month
                normalized_list.append(item_copy)
            return normalized_list
        except (json.JSONDecodeError, OSError):
            return []

    @classmethod
    def _save_all(cls, items: List[Dict[str, Any]], user_id: Optional[str] = None) -> None:
        uid = cls._resolve_user_id(user_id)
        if not uid:
            # Misafir modunda sunucudaki hiçbir .json dosyasına kayıt yapılmaz
            return
        file_path = cls.ensure_user_watchlist_file(uid)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, file_path)

    @classmethod
    def get_by_id(cls, tmdb_id: int, media_type: str = "movie", user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        items = cls.get_all(user_id=user_id)
        for item in items:
            if int(item.get("tmdb_id", 0)) == int(tmdb_id) and item.get("media_type") == media_type:
                return item
        return None

    @classmethod
    def upsert(cls, item_data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
        uid = cls._resolve_user_id(user_id)
        tmdb_id = int(item_data["tmdb_id"])
        media_type = str(item_data.get("media_type", "movie")).lower()
        if media_type not in ("movie", "tv"):
            media_type = "movie"

        rating = max(1, min(10, int(float(item_data.get("user_rating", 8)))))
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_watched_at = item_data.get("watched_at")
        raw_start = item_data.get("watch_start_date") or raw_watched_at
        raw_end = item_data.get("watch_end_date") or raw_watched_at or raw_start

        watch_start_date, _, _ = parse_and_normalize_watched_date(
            raw_start,
            item_data.get("added_at") or now_iso,
        )
        watch_end_date, watched_year, watched_month = parse_and_normalize_watched_date(
            raw_end,
            item_data.get("added_at") or now_iso,
        )
        if watch_end_date < watch_start_date:
            watch_start_date, watch_end_date = watch_end_date, watch_start_date
            _, watched_year, watched_month = parse_and_normalize_watched_date(watch_end_date)

        # Diziler için sezon bazlı başlama & bitiş tarihleri
        raw_seasons = item_data.get("season_watch_dates")
        single_season_num = item_data.get("season_number")
        if media_type == "tv":
            if single_season_num and not raw_seasons:
                raw_seasons = [{
                    "season_number": int(single_season_num),
                    "start_date": watch_start_date,
                    "end_date": watch_end_date,
                }]
            season_watch_dates = normalize_tv_season_watch_dates(
                raw_seasons,
                fallback_start=watch_start_date,
                fallback_end=watch_end_date,
            )
            watched_date_label = " • ".join(s["label"] for s in season_watch_dates)
        else:
            season_watch_dates = []
            watched_date_label = format_turkish_date_range(watch_start_date, watch_end_date)

        record: Dict[str, Any] = {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": str(item_data.get("title", "Bilinmeyen Yapım")).strip(),
            "poster_path": str(item_data.get("poster_path", "")).strip(),
            "user_rating": rating,
            "genres": list(item_data.get("genres") or []),
            "keywords": list(item_data.get("keywords") or []),
            "watch_start_date": watch_start_date,
            "watch_end_date": watch_end_date,
            "watched_at": watch_end_date,
            "watched_year": watched_year,
            "watched_month": watched_month,
            "watched_date_label": watched_date_label,
            "season_watch_dates": season_watch_dates,
            "added_at": str(item_data.get("added_at") or now_iso),
        }

        if not uid:
            return record

        items = cls.get_all(user_id=uid)
        updated = False
        for idx, existing in enumerate(items):
            if int(existing.get("tmdb_id", 0)) == tmdb_id and existing.get("media_type") == media_type:
                record["added_at"] = existing.get("added_at") or now_iso
                if media_type == "tv":
                    # Mevcut sezon tarihleriyle yeni gönderilen sezon tarihini birleştir
                    existing_seasons = {
                        int(s["season_number"]): s
                        for s in normalize_tv_season_watch_dates(
                            existing.get("season_watch_dates"),
                            existing.get("watch_start_date") or existing.get("watched_at"),
                            existing.get("watch_end_date") or existing.get("watched_at"),
                        )
                    }
                    if raw_seasons or single_season_num:
                        for new_s in season_watch_dates:
                            existing_seasons[int(new_s["season_number"])] = new_s
                    merged_seasons = [existing_seasons[k] for k in sorted(existing_seasons.keys())]
                    if merged_seasons:
                        record["season_watch_dates"] = merged_seasons
                        record["watch_start_date"] = min(s["start_date"] for s in merged_seasons)
                        record["watch_end_date"] = max(s["end_date"] for s in merged_seasons)
                        record["watched_at"] = record["watch_end_date"]
                        _, wy, wm = parse_and_normalize_watched_date(record["watch_end_date"])
                        record["watched_year"] = wy
                        record["watched_month"] = wm
                        record["watched_date_label"] = " • ".join(s["label"] for s in merged_seasons)
                elif not raw_start and not raw_end and existing.get("watched_at"):
                    es_at, _, _ = parse_and_normalize_watched_date(
                        existing.get("watch_start_date") or existing.get("watched_at"),
                        existing.get("added_at"),
                    )
                    ee_at, ew_year, ew_month = parse_and_normalize_watched_date(
                        existing.get("watch_end_date") or existing.get("watched_at"),
                        existing.get("added_at"),
                    )
                    record["watch_start_date"] = es_at
                    record["watch_end_date"] = ee_at
                    record["watched_at"] = ee_at
                    record["watched_year"] = ew_year
                    record["watched_month"] = ew_month
                    record["watched_date_label"] = format_turkish_date_range(es_at, ee_at)
                items[idx] = record
                updated = True
                break

        if not updated:
            items.insert(0, record)

        cls._save_all(items, user_id=uid)
        return record

    @classmethod
    def bulk_upsert(
        cls,
        records: List[Dict[str, Any]],
        skip_existing: bool = True,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        500+ yapımlık toplu içe aktarma (Bulk Import) işlemlerinde
        JSON dosyasını tek seferde okuyup tek seferde atomik olarak yazar.
        Mükerrer kayıtları O(1) hash kümesiyle atlar.
        """
        uid = cls._resolve_user_id(user_id)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        existing_items = cls.get_all(user_id=uid) if uid else []
        existing_keys = {
            (int(item.get("tmdb_id", 0)), str(item.get("media_type", "movie")))
            for item in existing_items
        }
        existing_titles_norm = {
            str(item.get("title", "")).strip().lower()
            for item in existing_items
            if item.get("title")
        }

        added_items: List[Dict[str, Any]] = []
        skipped_count = 0

        for item_data in records:
            tmdb_id = int(item_data["tmdb_id"])
            media_type = str(item_data.get("media_type", "movie")).lower()
            if media_type not in ("movie", "tv"):
                media_type = "movie"

            title = str(item_data.get("title", "Bilinmeyen Yapım")).strip()
            key = (tmdb_id, media_type)

            if skip_existing and (key in existing_keys or title.lower() in existing_titles_norm):
                skipped_count += 1
                continue

            rating = max(1, min(10, int(float(item_data.get("user_rating", 8)))))
            w_at, w_year, w_month = parse_and_normalize_watched_date(
                item_data.get("watched_at"),
                item_data.get("added_at") or now_iso,
            )
            record: Dict[str, Any] = {
                "tmdb_id": tmdb_id,
                "media_type": media_type,
                "title": title,
                "poster_path": str(item_data.get("poster_path", "")).strip(),
                "user_rating": rating,
                "genres": list(item_data.get("genres") or []),
                "keywords": list(item_data.get("keywords") or []),
                "watched_at": w_at,
                "watched_year": w_year,
                "watched_month": w_month,
                "added_at": str(item_data.get("added_at") or now_iso),
            }

            existing_keys.add(key)
            existing_titles_norm.add(title.lower())
            added_items.append(record)

        if uid and added_items:
            merged = added_items + existing_items
            cls._save_all(merged, user_id=uid)

        return {
            "added_items": added_items,
            "added_count": len(added_items),
            "skipped_count": skipped_count,
            "total_count": len(existing_items) + len(added_items),
        }

    @classmethod
    def delete(cls, tmdb_id: int, media_type: str = "movie", user_id: Optional[str] = None) -> bool:
        uid = cls._resolve_user_id(user_id)
        if not uid:
            return False
        items = cls.get_all(user_id=uid)
        filtered = [
            item
            for item in items
            if not (int(item.get("tmdb_id", 0)) == int(tmdb_id) and item.get("media_type") == media_type)
        ]
        if len(filtered) == len(items):
            return False
        cls._save_all(filtered, user_id=uid)
        return True

    @classmethod
    def clear_all(cls, user_id: Optional[str] = None) -> None:
        uid = cls._resolve_user_id(user_id)
        if not uid:
            return
        cls._save_all([], user_id=uid)
