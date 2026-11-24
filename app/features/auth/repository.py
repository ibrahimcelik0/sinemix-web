"""
Kullanıcı hesaplarını yerel `data/users.json` dosyasında tamamen ŞİFRESİZ (Passwordless)
olarak saklayan izole veri katmanı.

Şema (`data/users.json`):
- `id`, `first_name`, `last_name`, `full_name`, `username`, `email`, `role`,
  `avatar_initial`, `bio`, `created_at`, `last_login_at`
- Hiçbir şekilde `password` veya `password_hash` alanı tutulmaz.
- Sistem tamamen boş (`[]`) başlar; otomatik/ön tanımlı hiçbir kullanıcı veya e-posta eklemez.
"""

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def normalize_username(raw_username: str) -> str:
    """
    Kullanıcı adını otomatik küçük harfe çevirir, Türkçe karakterleri ASCII karşılıklarına
    dönüştürür ve boşluk/özel karakterleri temizler.
    """
    text = (raw_username or "").strip().lstrip("@").lower()
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")
    text = text.translate(tr_map)
    return re.sub(r"[^a-z0-9_.]", "", text)


class UserRepository:
    """`data/users.json` üzerindeki şifresiz kullanıcı okuma ve yazma işlemlerini yürütür."""

    @staticmethod
    def _get_base_data_dir() -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        return base_dir / "data"

    @classmethod
    def _get_users_file_path(cls) -> Path:
        return cls._get_base_data_dir() / "users.json"

    @staticmethod
    def _compute_avatar_initial(first_name: str, full_name: str, username: str) -> str:
        for candidate in (first_name, full_name, username):
            clean = (candidate or "").strip()
            if clean:
                return clean[0].upper()
        return "S"

    @staticmethod
    def _split_full_name(full_name: str) -> tuple[str, str]:
        parts = [p for p in (full_name or "").strip().split() if p]
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:-1]), parts[-1]

    @staticmethod
    def _generate_random_numeric_id(existing_ids: Optional[Set[str]] = None) -> str:
        """Her seferinde benzersiz, tamamen rastgele 8 haneli sayısal kullanıcı ID'si üretir."""
        taken = existing_ids or set()
        while True:
            candidate = str(secrets.randbelow(90000000) + 10000000)
            if candidate not in taken:
                return candidate

    @classmethod
    def _migrate_watchlist_file_if_needed(cls, old_id: str, new_id: str) -> None:
        if not old_id or not new_id or old_id == new_id:
            return
        watchlists_dir = cls._get_base_data_dir() / "watchlists"
        old_path = watchlists_dir / f"{old_id}.json"
        new_path = watchlists_dir / f"{new_id}.json"
        if old_path.exists() and not new_path.exists():
            try:
                os.replace(old_path, new_path)
            except OSError:
                pass

    @classmethod
    def _sanitize_passwordless_record(
        cls,
        raw_user: Dict[str, Any],
        existing_ids: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Kullanıcı kaydından olası şifre alanlarını temizler ve rastgele sayısal ID garanti eder."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_username = str(raw_user.get("username") or "").strip()
        username = normalize_username(raw_username) or "sinemasever"

        first_name = str(raw_user.get("first_name") or "").strip()
        last_name = str(raw_user.get("last_name") or "").strip()
        raw_full = str(raw_user.get("full_name") or "").strip()

        if (not first_name and not last_name) and raw_full:
            first_name, last_name = cls._split_full_name(raw_full)

        if not first_name:
            first_name = raw_full or username

        full_name = f"{first_name} {last_name}".strip() if last_name else first_name
        email = str(raw_user.get("email") or "").strip().lower()

        raw_id = str(raw_user.get("id") or "").strip()
        if raw_id.isdigit():
            user_id = raw_id
        else:
            user_id = cls._generate_random_numeric_id(existing_ids)
            if raw_id:
                cls._migrate_watchlist_file_if_needed(raw_id, user_id)

        if existing_ids is not None:
            existing_ids.add(user_id)

        created_at = str(raw_user.get("created_at") or now_iso).strip()
        last_login_at = str(raw_user.get("last_login_at") or created_at).strip()
        role = str(raw_user.get("role") or "SineMix Üyesi").strip()
        bio = str(
            raw_user.get("bio")
            or f"Merhaba, ben {full_name}! SineMix kişisel izleme listem ve öneri algoritmamla favori film ve dizilerimi keşfediyorum."
        ).strip()
        avatar_initial = str(
            raw_user.get("avatar_initial")
            or cls._compute_avatar_initial(first_name, full_name, username)
        ).strip()

        return {
            "id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "username": username,
            "email": email,
            "role": role,
            "avatar_initial": avatar_initial,
            "bio": bio,
            "created_at": created_at,
            "last_login_at": last_login_at,
        }

    @classmethod
    def _ensure_users_storage(cls) -> Path:
        file_path = cls._get_users_file_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.write_text("[]", encoding="utf-8")
        return file_path

    @classmethod
    def get_all(cls) -> List[Dict[str, Any]]:
        file_path = cls._ensure_users_storage()
        try:
            raw = file_path.read_text(encoding="utf-8").strip()
            users = json.loads(raw) if raw else []
            if not isinstance(users, list):
                users = []
        except (json.JSONDecodeError, OSError):
            users = []

        needs_save = False
        sanitized_users: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        required_keys = {
            "id", "first_name", "last_name", "full_name", "username",
            "email", "role", "avatar_initial", "created_at", "last_login_at",
        }

        for u in users:
            if not isinstance(u, dict):
                needs_save = True
                continue
            raw_id = str(u.get("id") or "").strip()
            if (
                "password" in u
                or "password_hash" in u
                or not required_keys.issubset(u.keys())
                or not raw_id.isdigit()
            ):
                needs_save = True
            sanitized_users.append(cls._sanitize_passwordless_record(u, existing_ids=seen_ids))

        if needs_save:
            cls._save_all(sanitized_users)

        return sanitized_users

    @classmethod
    def _save_all(cls, users: List[Dict[str, Any]]) -> None:
        file_path = cls._get_users_file_path()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        seen_ids: Set[str] = set()
        clean_list = [
            cls._sanitize_passwordless_record(u, existing_ids=seen_ids)
            for u in users
            if isinstance(u, dict)
        ]
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(clean_list, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, file_path)

    @classmethod
    def get_by_id(cls, user_id: str) -> Optional[Dict[str, Any]]:
        if not user_id:
            return None
        for user in cls.get_all():
            if str(user.get("id")) == str(user_id):
                return user
        return None

    @classmethod
    def get_by_email(cls, email: str) -> Optional[Dict[str, Any]]:
        """Büyük/küçük harf duyarsız (case-insensitive) e-posta araması yapar."""
        clean = (email or "").strip().lower()
        if not clean:
            return None
        for user in cls.get_all():
            if str(user.get("email", "")).strip().lower() == clean:
                return user
        return None

    @classmethod
    def get_by_username(cls, username: str) -> Optional[Dict[str, Any]]:
        """Büyük/küçük harf duyarsız (case-insensitive) kullanıcı adı araması yapar."""
        raw_clean = (username or "").strip().lstrip("@").lower()
        norm_clean = normalize_username(username)
        if not raw_clean and not norm_clean:
            return None
        for user in cls.get_all():
            u_name = str(user.get("username", "")).strip().lower()
            if u_name == raw_clean or (norm_clean and u_name == norm_clean):
                return user
        return None

    @classmethod
    def get_by_identifier(cls, identifier: str) -> Optional[Dict[str, Any]]:
        """E-posta adresi veya kullanıcı adı ile kullanıcıyı bulur."""
        user = cls.get_by_email(identifier)
        if user:
            return user
        return cls.get_by_username(identifier)

    @classmethod
    def update_last_login(cls, user_id: str) -> Optional[Dict[str, Any]]:
        """Kullanıcının `last_login_at` zaman damgasını günceller ve kaydeder."""
        users = cls.get_all()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        updated_user = None
        for u in users:
            if str(u.get("id")) == str(user_id):
                u["last_login_at"] = now_iso
                updated_user = u
                break
        if updated_user is not None:
            cls._save_all(users)
        return updated_user

    @classmethod
    def create_user(
        cls,
        username: str,
        email: str,
        first_name: str = "",
        last_name: str = "",
        full_name: str = "",
    ) -> Dict[str, Any]:
        """Yeni bir şifresiz (passwordless) kullanıcı kaydı oluşturur ve `data/users.json` içine yazar."""
        users = cls.get_all()
        existing_ids = {str(u.get("id")) for u in users if u.get("id")}
        user_id = cls._generate_random_numeric_id(existing_ids)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        clean_username = normalize_username(username)
        clean_first = (first_name or "").strip()
        clean_last = (last_name or "").strip()
        clean_full = (full_name or "").strip()

        if (not clean_first and not clean_last) and clean_full:
            clean_first, clean_last = cls._split_full_name(clean_full)

        if not clean_first:
            clean_first = clean_username or "SineMix"

        computed_full = f"{clean_first} {clean_last}".strip() if clean_last else clean_first
        clean_email = email.strip().lower()

        new_user: Dict[str, Any] = {
            "id": user_id,
            "first_name": clean_first,
            "last_name": clean_last,
            "full_name": computed_full,
            "username": clean_username,
            "email": clean_email,
            "role": "SineMix Üyesi",
            "avatar_initial": cls._compute_avatar_initial(clean_first, computed_full, clean_username),
            "bio": f"Merhaba, ben {computed_full}! SineMix kişisel izleme listem ve öneri algoritmamla favori film ve dizilerimi keşfediyorum.",
            "created_at": now_iso,
            "last_login_at": now_iso,
        }
        users.append(new_user)
        cls._save_all(users)
        return new_user
