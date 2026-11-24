"""
Profile feature iş mantığı:
Aktif oturumdaki kullanıcının profil bilgilerini, izlediği film/dizi/bölüm sayılarını,
verdiği ortalama puanı ve Sinema Evrenleri & Stüdyoları tamamlama rozetlerini üretir.
"""

from typing import Any, Dict, List, Optional

from app.features.catalog.repository import CatalogRepository
from app.features.catalog.services import get_all_collections


def get_dynamic_user_profile(current_user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Aktif oturumdaki kullanıcının profil kimlik verilerini döndürür.
    Güvenlik ve gizlilik gereği kullanıcının rastgele sayısal `id` değeri
    veya dosya yolu profil ekranına gönderilmez.
    """
    if not current_user:
        return {
            "ad": "Misafir Kullanıcı",
            "first_name": "Misafir",
            "last_name": "Kullanıcı",
            "full_name": "Misafir Kullanıcı",
            "username": "misafir",
            "kullanici_adi": "@misafir",
            "email": "",
            "role": "Misafir",
            "avatar_initial": "M",
            "bio": "SineMix kişisel film ve dizi öneri platformu üyesi.",
            "uyelik_tarihi": "2026",
            "son_giris_tarihi": "2026",
        }

    username = current_user.get("username", "kullanici")
    first_name = current_user.get("first_name") or ""
    last_name = current_user.get("last_name") or ""
    full_name = current_user.get("full_name") or f"{first_name} {last_name}".strip() or username
    email = current_user.get("email", "")
    role = current_user.get("role", "SineMix Üyesi")
    created_raw = str(current_user.get("created_at", "2026-11-20"))[:10]
    last_login_raw = str(current_user.get("last_login_at") or created_raw)[:10]
    bio = (
        current_user.get("bio")
        or f"Merhaba, ben {full_name}! SineMix kişisel izleme listem ve öneri algoritmamla favori film ve dizilerimi keşfediyorum."
    )

    return {
        "ad": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "username": username,
        "kullanici_adi": f"@{username}",
        "email": email,
        "role": role,
        "avatar_initial": current_user.get("avatar_initial") or (full_name[0].upper() if full_name else "S"),
        "bio": bio,
        "uyelik_tarihi": created_raw,
        "son_giris_tarihi": last_login_raw,
    }


def compute_user_profile_metrics(watchlist_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Kullanıcının izleme listesindeki yapımlardan:
    - İzlenen Film sayısı (`movie_count`),
    - İzlenen Dizi sayısı (`tv_count`),
    - İzlenen Dizilerin toplam bölüm sayısı (`watched_episodes_count`),
    - Verilen Ortalama Puan (`avg_rating`),
    - Tamamlanan ve ilerlenen Sinema Evrenleri & Stüdyo rozetlerini (`universe_badges`)
    hesaplar.
    """
    items = watchlist_items or []
    movie_items = [i for i in items if i.get("media_type") == "movie"]
    tv_items = [i for i in items if i.get("media_type") == "tv"]

    ratings = [int(i.get("user_rating", 8)) for i in items if i.get("user_rating") is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

    # İzlenen dizilerin katalogdaki gerçek bölüm sayılarını topla
    watched_episodes_count = 0
    for tv_entry in tv_items:
        tmdb_id = int(tv_entry.get("tmdb_id", 0))
        cat_tv = CatalogRepository.get_by_id(tmdb_id, "tv")
        if cat_tv:
            ep_total = int(cat_tv.get("number_of_episodes") or 0)
            if ep_total <= 0 and isinstance(cat_tv.get("seasons"), list):
                ep_total = sum(len(s.get("episodes") or []) for s in cat_tv["seasons"])
            watched_episodes_count += max(1, ep_total)
        else:
            watched_episodes_count += 1

    # Kullanıcının izlediği (media_type, tmdb_id) ve tmdb_id kümeleri
    watched_ids = {int(i.get("tmdb_id", 0)) for i in items if i.get("tmdb_id")}

    # Sinema Evrenleri & Stüdyo Koleksiyonları İlerleme ve Rozet Hesabı
    raw_collections = get_all_collections()
    if isinstance(raw_collections, dict):
        all_collections = list(raw_collections.get("universes", [])) + list(raw_collections.get("studios", []))
    elif isinstance(raw_collections, list):
        all_collections = raw_collections
    else:
        all_collections = []
    universe_badges: List[Dict[str, Any]] = []
    completed_universes_count = 0
    active_universes_count = 0

    badge_icons = {
        "marvel": "🛡️",
        "star-wars": "⚔️",
        "dc": "🦇",
        "middle-earth-magic": "💍",
        "pixar": "🚀",
        "disney": "🏰",
        "epic-series": "👑",
        "dark-sci-fi": "🌀",
    }

    for col in all_collections:
        col_items = col.get("items") or []
        total_in_col = len(col_items)
        if total_in_col == 0:
            continue

        watched_in_col = sum(1 for c_item in col_items if int(c_item.get("tmdb_id", 0)) in watched_ids)
        percent = int(round((watched_in_col / total_in_col) * 100))
        is_completed = watched_in_col >= total_in_col
        is_started = watched_in_col > 0

        if is_completed:
            completed_universes_count += 1
            active_universes_count += 1
            status_label = "🏆 Evren Tamamlandı"
            status_tone = "completed"
        elif is_started:
            active_universes_count += 1
            status_label = f"🔥 %{percent} Tamamlandı"
            status_tone = "in-progress"
        else:
            status_label = "🌌 Keşfetmeye Hazır"
            status_tone = "not-started"

        slug = str(col.get("slug", ""))
        universe_badges.append({
            "slug": slug,
            "title": col.get("title", ""),
            "group": col.get("group", "universe"),
            "tagline": col.get("tagline", ""),
            "icon": badge_icons.get(slug, "🎬"),
            "watched_count": watched_in_col,
            "total_count": total_in_col,
            "percent": percent,
            "is_completed": is_completed,
            "is_started": is_started,
            "status_label": status_label,
            "status_tone": status_tone,
        })

    # Tamamlanan ve başlanan evrenleri en üste sırala
    universe_badges.sort(
        key=lambda b: (b["is_completed"], b["is_started"], b["percent"], b["watched_count"]),
        reverse=True,
    )

    return {
        "total_watched": len(items),
        "movie_count": len(movie_items),
        "tv_count": len(tv_items),
        "watched_episodes_count": watched_episodes_count,
        "avg_rating": avg_rating,
        "completed_universes_count": completed_universes_count,
        "active_universes_count": active_universes_count,
        "universe_badges": universe_badges,
    }
