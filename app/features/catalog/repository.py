"""
Ana Katalog Veri Katmanı (`app/features/catalog/repository.py`):
Tüm film ve dizi kataloğunu `data/catalog.json` dosyasından milisaniyeler içinde okur.
Bellek içi (in-memory) `mtime` duyarlı önbellek kullanarak disk I/O maliyetini sıfıra indirir.
Detay sayfasında TMDB API'den çekilen ek verileri (oyuncu kadrosu, fragman, bütçe vb.)
`data/catalog.json` içine kalıcı olarak önbellekler.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.tmdb_fallback import FALLBACK_TMDB_CATALOG, TMDB_GENRE_MAP

NAME_TO_GENRE_ID: Dict[str, int] = {v.lower(): k for k, v in TMDB_GENRE_MAP.items()}


def normalize_genre_objects(genres_raw: Any) -> List[Dict[str, Any]]:
    """
    Tür listesini `[{"id": 878, "name": "Bilim Kurgu"}, ...]` şemasına dönüştürür.
    """
    if not genres_raw:
        return [{"id": 18, "name": "Dram"}]

    result: List[Dict[str, Any]] = []
    seen_names = set()

    for g in genres_raw:
        if isinstance(g, dict):
            g_name = str(g.get("name") or "Dram").strip()
            g_id = int(g.get("id") or NAME_TO_GENRE_ID.get(g_name.lower(), 18))
        else:
            g_name = str(g).strip()
            g_id = int(NAME_TO_GENRE_ID.get(g_name.lower(), 18))

        if g_name and g_name.lower() not in seen_names:
            seen_names.add(g_name.lower())
            result.append({"id": g_id, "name": g_name})

    return result or [{"id": 18, "name": "Dram"}]


def extract_genre_names(genres_raw: Any) -> List[str]:
    """`[{"id": 878, "name": "Bilim Kurgu"}]` veya `["Bilim Kurgu"]` yapısından isim listesi döndürür."""
    return [g["name"] for g in normalize_genre_objects(genres_raw)]


class CatalogRepository:
    """
    `data/catalog.json` dosyasını yöneten ana katalog veri katmanı.
    """

    _memory_cache: Optional[List[Dict[str, Any]]] = None
    _cache_mtime: float = -1.0

    @staticmethod
    def _get_catalog_file_path() -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        return base_dir / "data" / "catalog.json"

    @classmethod
    def _seed_initial_from_fallback(cls, file_path: Path) -> List[Dict[str, Any]]:
        """`data/catalog.json` henüz oluşturulmamışsa yerleşik katalogdan ilk şemayı hazırlar."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        records: List[Dict[str, Any]] = []

        for idx, fb in enumerate(FALLBACK_TMDB_CATALOG):
            record = dict(fb)
            record["tmdb_id"] = int(fb["tmdb_id"])
            record["media_type"] = fb.get("media_type", "movie")
            record["title"] = fb["title"]
            record["original_title"] = fb.get("original_title") or fb["title"]
            record["poster_path"] = fb.get("poster_path", "")
            record["backdrop_path"] = fb.get("backdrop_path") or fb.get("poster_path", "")
            record["overview"] = fb.get("overview", "")
            record["release_year"] = int(fb.get("release_year", 2020))
            record["vote_average"] = float(fb.get("vote_average", 8.0))
            record["genres"] = normalize_genre_objects(fb.get("genres"))
            record["popularity"] = round(float(fb.get("popularity") or (150.0 - idx * 1.5)), 2)
            record["added_at"] = fb.get("added_at") or now_iso
            records.append(record)

        cls.save_all_raw(records)
        return records

    @classmethod
    def get_all_raw(cls) -> List[Dict[str, Any]]:
        """
        `data/catalog.json` içindeki ham kayıtları (`genres: [{"id": ..., "name": ...}]`)
        bellek önbelleğiyle milisaniyenin altında sürede döndürür.
        """
        file_path = cls._get_catalog_file_path()
        if not file_path.exists():
            return cls._seed_initial_from_fallback(file_path)

        try:
            current_mtime = file_path.stat().st_mtime
            if cls._memory_cache is not None and current_mtime == cls._cache_mtime:
                return cls._memory_cache

            raw_text = file_path.read_text(encoding="utf-8").strip()
            if not raw_text:
                return cls._seed_initial_from_fallback(file_path)

            data = json.loads(raw_text)
            if not isinstance(data, list) or len(data) == 0:
                return cls._seed_initial_from_fallback(file_path)

            cls._memory_cache = data
            cls._cache_mtime = current_mtime
            return data
        except (json.JSONDecodeError, OSError):
            return cls._seed_initial_from_fallback(file_path)

    @classmethod
    def save_all_raw(cls, items: List[Dict[str, Any]]) -> None:
        """Tüm kataloğu atomik olarak `data/catalog.json` dosyasına kaydeder."""
        file_path = cls._get_catalog_file_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, file_path)
        cls._memory_cache = items
        try:
            cls._cache_mtime = file_path.stat().st_mtime
        except OSError:
            cls._cache_mtime = -1.0

    @staticmethod
    def normalize_poster_url(poster_path: Any) -> str:
        """
        TMDB poster_path değerini her zaman geçerli tam URL (`https://image.tmdb.org/t/p/w500/...`)
        veya sade koyu sinema ikonu (`/static/img/no-poster.svg`) olarak döndürür.
        Çift domain eklenmesini ve eski `ui-avatars.com` baş harf görsellerini engeller.
        """
        if not poster_path:
            return "/static/img/no-poster.svg"
        clean = str(poster_path).strip()
        if not clean or "ui-avatars.com" in clean:
            return "/static/img/no-poster.svg"
        if clean.startswith("https://image.tmdb.org/t/p/"):
            return clean
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        if clean.startswith("/static/"):
            return clean
        if not clean.startswith("/"):
            clean = f"/{clean}"
        return f"https://image.tmdb.org/t/p/w500{clean}"

    @classmethod
    def _to_app_dict(cls, raw_item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Disk üzerindeki `genres: [{"id": ..., "name": ...}]` şemasını korurken,
        uygulama şablonları ve öneri algoritması için `genres` alanını isim listesi
        ve `genre_objects` alanını `{id, name}` listesi olarak sunar.
        """
        item = dict(raw_item)
        genre_objs = normalize_genre_objects(raw_item.get("genres"))
        item["genre_objects"] = genre_objs
        item["genres"] = [g["name"] for g in genre_objs]
        item["poster_path"] = cls.normalize_poster_url(raw_item.get("poster_path"))
        backdrop_raw = raw_item.get("backdrop_path")
        if backdrop_raw and "ui-avatars.com" not in str(backdrop_raw):
            b_clean = str(backdrop_raw).strip()
            if b_clean.startswith("https://image.tmdb.org/t/p/") or b_clean.startswith("http"):
                item["backdrop_path"] = b_clean
            elif b_clean.startswith("/"):
                item["backdrop_path"] = f"https://image.tmdb.org/t/p/w1280{b_clean}"
            else:
                item["backdrop_path"] = item["poster_path"]
        else:
            item["backdrop_path"] = item["poster_path"]
        return item

    @classmethod
    def get_all(cls) -> List[Dict[str, Any]]:
        """Uygulama katmanı için normalize edilmiş tüm katalog kayıtlarını döndürür."""
        return [cls._to_app_dict(item) for item in cls.get_all_raw()]

    @classmethod
    def get_by_id(cls, tmdb_id: int, media_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """`tmdb_id` (ve opsiyonel `media_type`) ile katalogdan tekil yapım döndürür."""
        target_id = int(tmdb_id)
        raw_items = cls.get_all_raw()

        if media_type in ("movie", "tv"):
            for item in raw_items:
                if int(item.get("tmdb_id", 0)) == target_id and item.get("media_type") == media_type:
                    return cls._to_app_dict(item)

        for item in raw_items:
            if int(item.get("tmdb_id", 0)) == target_id:
                return cls._to_app_dict(item)

        return None

    @classmethod
    def upsert_catalog_item(cls, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detay sayfasında veya veri çekme sırasında bir yapımın ek verilerini
        (cast, trailer_key, budget, revenue, keywords vb.) `data/catalog.json` içine önbellekler.
        """
        raw_items = list(cls.get_all_raw())
        target_id = int(item_data["tmdb_id"])
        target_type = str(item_data.get("media_type", "movie")).lower()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        record = dict(item_data)
        record["tmdb_id"] = target_id
        record["media_type"] = target_type
        record["genres"] = normalize_genre_objects(item_data.get("genre_objects") or item_data.get("genres"))
        record.pop("genre_objects", None)
        if "added_at" not in record or not record["added_at"]:
            record["added_at"] = now_iso

        updated = False
        for idx, existing in enumerate(raw_items):
            if int(existing.get("tmdb_id", 0)) == target_id and existing.get("media_type") == target_type:
                merged = dict(existing)
                merged.update(record)
                merged["genres"] = normalize_genre_objects(record.get("genres") or existing.get("genres"))
                raw_items[idx] = merged
                record = merged
                updated = True
                break

        if not updated:
            raw_items.append(record)

        cls.save_all_raw(raw_items)
        return cls._to_app_dict(record)


class ContentRequestRepository:
    """
    Kullanıcıların katalogda bulamadıkları yapımlar için gönderdikleri
    Film / Dizi / Animasyon taleplerini `data/requests.json` dosyasında yönetir.
    Şema: id, title, media_type, year, note, requested_by, created_at, status ('pending'), request_count.
    """

    @staticmethod
    def _get_requests_file_path() -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        return base_dir / "data" / "requests.json"

    @classmethod
    def _ensure_storage(cls) -> Path:
        path = cls._get_requests_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("[]", encoding="utf-8")
        return path

    @classmethod
    def get_all(cls) -> List[Dict[str, Any]]:
        path = cls._ensure_storage()
        try:
            raw = path.read_text(encoding="utf-8").strip()
            data = json.loads(raw) if raw else []
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    @classmethod
    def _save_all(cls, items: List[Dict[str, Any]]) -> None:
        path = cls._ensure_storage()
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, path)

    @classmethod
    def create_or_increment_request(
        cls,
        title: str,
        media_type: str = "Film",
        year: str = "",
        note: str = "",
        requested_by: str = "misafir",
        requester_email: str = "",
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Yeni bir film/dizi talebi kaydeder (`requested_by` kullanıcı adı ve `requester_email` e-posta bilgisiyle).
        Aynı yapım için mükerrer talep gönderilirse `request_count` sayacını artırır
        ve `(record, is_duplicate=True)` döndürür.
        """
        from app.core.utils import normalize_search_text
        import secrets

        clean_title = (title or "").strip()
        clean_username = (requested_by or "misafir").strip().lstrip("@")
        clean_email = (requester_email or "").strip().lower()
        norm_title = normalize_search_text(clean_title)
        items = cls.get_all()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for item in items:
            if normalize_search_text(item.get("title", "")) == norm_title:
                item["request_count"] = int(item.get("request_count", 1)) + 1
                item["updated_at"] = now_iso
                item["requested_by"] = clean_username
                item["requester_username"] = clean_username
                if clean_email:
                    item["requester_email"] = clean_email
                if note and not item.get("note"):
                    item["note"] = note.strip()
                cls._save_all(items)
                return item, True

        new_record: Dict[str, Any] = {
            "id": str(secrets.randbelow(90000000) + 10000000),
            "title": clean_title,
            "media_type": (media_type or "Film").strip(),
            "year": (str(year).strip() if year else ""),
            "note": (note or "").strip(),
            "requested_by": clean_username,
            "requester_username": clean_username,
            "requester_email": clean_email,
            "created_at": now_iso,
            "status": "pending",
            "request_count": 1,
        }
        items.insert(0, new_record)
        cls._save_all(items)
        return new_record, False
