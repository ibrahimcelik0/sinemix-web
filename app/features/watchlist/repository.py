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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from flask import has_request_context, session


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
            return data if isinstance(data, list) else []
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

        record: Dict[str, Any] = {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "title": str(item_data.get("title", "Bilinmeyen Yapım")).strip(),
            "poster_path": str(item_data.get("poster_path", "")).strip(),
            "user_rating": rating,
            "genres": list(item_data.get("genres") or []),
            "keywords": list(item_data.get("keywords") or []),
            "added_at": str(item_data.get("added_at") or now_iso),
        }

        if not uid:
            return record

        items = cls.get_all(user_id=uid)
        updated = False
        for idx, existing in enumerate(items):
            if int(existing.get("tmdb_id", 0)) == tmdb_id and existing.get("media_type") == media_type:
                record["added_at"] = existing.get("added_at") or now_iso
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
            record: Dict[str, Any] = {
                "tmdb_id": tmdb_id,
                "media_type": media_type,
                "title": title,
                "poster_path": str(item_data.get("poster_path", "")).strip(),
                "user_rating": rating,
                "genres": list(item_data.get("genres") or []),
                "keywords": list(item_data.get("keywords") or []),
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
