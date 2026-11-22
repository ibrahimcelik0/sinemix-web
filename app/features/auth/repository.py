"""
Kullanıcı hesaplarını yerel `data/users.json` dosyasında saklayan izole veri katmanı.
Şifreler yalnızca `werkzeug.security` hash değerleri olarak (`password_hash`) tutulur.
Otomatik demo kullanıcı oluşturmaz; sistem sıfırdan başlar.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class UserRepository:
    """`data/users.json` üzerindeki kullanıcı okuma ve yazma işlemlerini yürütür."""

    @staticmethod
    def _get_base_data_dir() -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        return base_dir / "data"

    @classmethod
    def _get_users_file_path(cls) -> Path:
        return cls._get_base_data_dir() / "users.json"

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
            if not raw:
                return []
            users = json.loads(raw)
            return users if isinstance(users, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    @classmethod
    def _save_all(cls, users: List[Dict[str, Any]]) -> None:
        file_path = cls._ensure_users_storage()
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(users, ensure_ascii=False, indent=2),
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
        clean = (email or "").strip().lower()
        if not clean:
            return None
        for user in cls.get_all():
            if str(user.get("email", "")).strip().lower() == clean:
                return user
        return None

    @classmethod
    def get_by_username(cls, username: str) -> Optional[Dict[str, Any]]:
        clean = (username or "").strip().lower()
        if not clean:
            return None
        for user in cls.get_all():
            if str(user.get("username", "")).strip().lower() == clean:
                return user
        return None

    @classmethod
    def get_by_identifier(cls, identifier: str) -> Optional[Dict[str, Any]]:
        """Kullanıcı adı veya e-posta adresi ile kullanıcıyı bulur."""
        user = cls.get_by_email(identifier)
        if user:
            return user
        return cls.get_by_username(identifier)

    @classmethod
    def create_user(cls, username: str, email: str, password_hash: str) -> Dict[str, Any]:
        users = cls.get_all()
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_user: Dict[str, Any] = {
            "id": user_id,
            "username": username.strip(),
            "email": email.strip().lower(),
            "password_hash": password_hash,
            "created_at": now_iso,
        }
        users.append(new_user)
        cls._save_all(users)
        return new_user
