"""Profile feature iş mantığı: Aktif oturumdaki kullanıcıdan dinamik profil bilgisi üretir."""

from typing import Any, Dict, Optional


def get_dynamic_user_profile(current_user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Aktif oturumdaki kullanıcının profil verilerini döndürür."""
    if not current_user:
        return {
            "id": "guest",
            "ad": "Misafir Kullanıcı",
            "kullanici_adi": "@misafir",
            "email": "",
            "avatar_initial": "M",
            "bio": "SineMix kişisel film ve dizi öneri platformu üyesi.",
            "uyelik_tarihi": "2026",
            "watchlist_dosyasi": "",
        }

    username = current_user.get("username", "kullanici")
    email = current_user.get("email", "")
    created_raw = str(current_user.get("created_at", "2026-11-20"))[:10]
    user_id = current_user.get("id", "demo")

    return {
        "id": user_id,
        "ad": username,
        "kullanici_adi": f"@{username}",
        "email": email,
        "avatar_initial": current_user.get("avatar_initial", username[0].upper()),
        "bio": f"Merhaba, ben {username}! SineMix kişisel izleme listem ve öneri algoritmamla favori film ve dizilerimi keşfediyorum.",
        "uyelik_tarihi": created_raw,
        "watchlist_dosyasi": f"data/watchlists/{user_id}.json",
    }
