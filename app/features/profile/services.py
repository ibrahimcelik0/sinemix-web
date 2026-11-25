"""
Profile feature iş mantığı:
1. Aktif oturumdaki kullanıcının profil bilgilerini (kullanıcı ID'si gizli tutularak) döndürür.
2. Kullanıcının izlediği film, dizi/bölüm sayılarını, ortalama puanını ve
   Sinema Evrenleri & Stüdyoları tamamlama rozetlerini hesaplar.
3. 2026–2020 Yıllık İstatistik Motoru (`compute_yearly_watch_statistics`):
   - Yıl sekmeleri sabit sırayla `2026, 2025, 2024, 2023, 2022, 2021, 2020` ve en sonda `"Tüm Zamanlar"` (`all`)
     olarak üretilir; varsayılan seçili yıl her zaman `"2026"` olur.
   - Her yıl için:
     * Toplam İzlenen Film Sayısı ve Tamamlanan Dizi / Bölüm Sayısı
     * Toplam İzleme Süresi (Saat ve eşdeğer Gün hesabı, ör. "284 saat • ~11.8 gün")
     * En Çok İzlenen Türler (Top 3 Genre ve yüzdelik dağılım çubukları)
     * Puan Ortalaması & Yılın Favori Yapımı
     * Aylık İzleme Aktivitesi (Ocak–Aralık 12 aylık bar grafiği verisi)
"""

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from app.features.catalog.repository import CatalogRepository, extract_genre_names
from app.features.catalog.services import get_all_collections
from app.features.watchlist.repository import parse_and_normalize_watched_date

YEAR_TABS_SEQUENCE: List[Tuple[str, str]] = [
    ("2026", "2026"),
    ("2025", "2025"),
    ("2024", "2024"),
    ("2023", "2023"),
    ("2022", "2022"),
    ("2021", "2021"),
    ("2020", "2020"),
    ("all", "Tüm Zamanlar"),
]

MONTHS_TR: List[Tuple[int, str, str]] = [
    (1, "Oca", "Ocak"),
    (2, "Şub", "Şubat"),
    (3, "Mar", "Mart"),
    (4, "Nis", "Nisan"),
    (5, "May", "Mayıs"),
    (6, "Haz", "Haziran"),
    (7, "Tem", "Temmuz"),
    (8, "Ağu", "Ağustos"),
    (9, "Eyl", "Eylül"),
    (10, "Eki", "Ekim"),
    (11, "Kas", "Kasım"),
    (12, "Ara", "Aralık"),
]


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


def _estimate_item_duration_and_episodes(entry: Dict[str, Any]) -> Tuple[int, int]:
    """
    Bir izleme kaydı için `(toplam_dakika, bolum_sayisi)` döndürür:
    - Film (`movie`) ise katalogdaki `runtime` (yoksa 125 dk) ve `0` bölüm döner.
    - Dizi (`tv`) ise katalogdaki tüm sezonların bölüm süreleri toplamı ve toplam bölüm sayısı döner.
    """
    tmdb_id = int(entry.get("tmdb_id", 0))
    media_type = str(entry.get("media_type", "movie")).lower()
    cat_item = CatalogRepository.get_by_id(tmdb_id, media_type)

    if media_type == "tv":
        if cat_item:
            seasons = cat_item.get("seasons")
            if isinstance(seasons, list) and seasons:
                ep_count = 0
                total_mins = 0
                for s in seasons:
                    eps = s.get("episodes") or []
                    ep_count += len(eps)
                    total_mins += sum(int(ep.get("runtime") or 45) for ep in eps)
                if ep_count > 0:
                    return max(45, total_mins), ep_count

            ep_total = max(1, int(cat_item.get("number_of_episodes") or 8))
            ep_runtime = int(cat_item.get("runtime") or 45)
            return ep_total * ep_runtime, ep_total
        return 8 * 45, 8

    # Movie
    if cat_item and int(cat_item.get("runtime") or 0) > 0:
        return int(cat_item["runtime"]), 0
    return 125, 0


def _build_single_period_stats(
    year_key: str,
    label: str,
    period_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Belirli bir yıl (`2026`..`2020`) veya `Tüm Zamanlar` (`all`) için ayrıntılı istatistik sözlüğü üretir."""
    if not period_items:
        empty_months = [
            {
                "month_num": m_num,
                "short_name": m_short,
                "full_name": m_full,
                "count": 0,
                "height_pct": 6,
            }
            for m_num, m_short, m_full in MONTHS_TR
        ]
        return {
            "year_key": year_key,
            "label": label,
            "has_data": False,
            "empty_message": (
                f"{label} yılı için henüz izleme kaydı bulunmuyor."
                if year_key != "all"
                else "Henüz hiçbir yıl için izleme kaydı bulunmuyor."
            ),
            "total_count": 0,
            "movie_count": 0,
            "tv_count": 0,
            "episode_count": 0,
            "total_minutes": 0,
            "total_hours": 0,
            "total_days": 0.0,
            "watch_time_label": "0 saat • ~0 gün",
            "avg_rating": 0.0,
            "favorite_item": None,
            "top_genres": [],
            "monthly_activity": empty_months,
        }

    movie_count = 0
    tv_count = 0
    episode_count = 0
    total_minutes = 0
    ratings: List[int] = []
    genre_counter: Counter = Counter()
    month_counter: Counter = Counter()

    for entry in period_items:
        m_type = str(entry.get("media_type", "movie")).lower()
        mins, eps = _estimate_item_duration_and_episodes(entry)
        total_minutes += mins

        if m_type == "tv":
            tv_count += 1
            episode_count += eps
        else:
            movie_count += 1

        if entry.get("user_rating") is not None:
            ratings.append(int(entry["user_rating"]))

        for g_name in extract_genre_names(entry.get("genres")):
            clean_g = str(g_name).strip()
            if clean_g:
                genre_counter[clean_g] += 1

        _, _, w_month = parse_and_normalize_watched_date(
            entry.get("watched_at"),
            entry.get("added_at"),
        )
        m_val = int(entry.get("watched_month") or w_month)
        if 1 <= m_val <= 12:
            month_counter[m_val] += 1

    total_hours = int(round(total_minutes / 60.0))
    total_days = round(total_minutes / (60.0 * 24.0), 1)
    watch_time_label = f"{total_hours} saat • ~{total_days} gün"
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0.0

    # Yılın Favori Yapımı (En yüksek puan verilen, eşitlikte en son izlenen)
    sorted_by_fav = sorted(
        period_items,
        key=lambda x: (int(x.get("user_rating", 0)), str(x.get("watched_at", ""))),
        reverse=True,
    )
    best = sorted_by_fav[0]
    favorite_item = {
        "tmdb_id": int(best.get("tmdb_id", 0)),
        "media_type": best.get("media_type", "movie"),
        "title": best.get("title", "Bilinmeyen Yapım"),
        "user_rating": int(best.get("user_rating", 8)),
        "watched_at": best.get("watched_at", ""),
        "watched_date_label": best.get("watched_date_label") or best.get("watched_at", ""),
        "poster_path": best.get("poster_path", "/static/img/no-poster.svg"),
    }

    # En Çok İzlenen Türler (Top 3 Genre ve yüzdelik dağılım çubuğu)
    top_3_raw = genre_counter.most_common(3)
    top_3_total = sum(cnt for _, cnt in top_3_raw) or 1
    top_genres: List[Dict[str, Any]] = []
    for g_name, cnt in top_3_raw:
        pct = int(round((cnt / top_3_total) * 100))
        top_genres.append({
            "name": g_name,
            "count": cnt,
            "percent": max(10, min(100, pct)),
        })

    # 12 Aylık İzleme Aktivitesi (Ocak–Aralık)
    max_month_cnt = max(month_counter.values(), default=1) or 1
    monthly_activity: List[Dict[str, Any]] = []
    for m_num, m_short, m_full in MONTHS_TR:
        cnt = int(month_counter.get(m_num, 0))
        height_pct = int(round((cnt / max_month_cnt) * 100)) if cnt > 0 else 6
        monthly_activity.append({
            "month_num": m_num,
            "short_name": m_short,
            "full_name": m_full,
            "count": cnt,
            "height_pct": max(6, min(100, height_pct)),
        })

    return {
        "year_key": year_key,
        "label": label,
        "has_data": True,
        "empty_message": "",
        "total_count": len(period_items),
        "movie_count": movie_count,
        "tv_count": tv_count,
        "episode_count": episode_count,
        "total_minutes": total_minutes,
        "total_hours": total_hours,
        "total_days": total_days,
        "watch_time_label": watch_time_label,
        "avg_rating": avg_rating,
        "favorite_item": favorite_item,
        "top_genres": top_genres,
        "monthly_activity": monthly_activity,
    }


def compute_yearly_watch_statistics(watchlist_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    2026'dan 2020'ye kadar (`2026, 2025, 2024, 2023, 2022, 2021, 2020`) ve
    en sonda `"Tüm Zamanlar"` (`all`) için yıllık izleme istatistiklerini hesaplar.
    Mevcut kayıtlarda tarih yoksa varsayılan yıl `2026` kabul edilir.
    """
    items = watchlist_items or []
    items_by_year: Dict[str, List[Dict[str, Any]]] = {y_key: [] for y_key, _ in YEAR_TABS_SEQUENCE if y_key != "all"}

    normalized_all: List[Dict[str, Any]] = []
    for raw_entry in items:
        entry = dict(raw_entry)
        w_at, w_year, w_month = parse_and_normalize_watched_date(
            entry.get("watched_at"),
            entry.get("added_at"),
        )
        y_val = int(entry.get("watched_year") or w_year)
        if str(y_val) not in items_by_year:
            y_val = 2026
        m_val = int(entry.get("watched_month") or w_month)
        if not (1 <= m_val <= 12):
            m_val = w_month

        entry["watched_at"] = w_at
        entry["watched_year"] = y_val
        entry["watched_month"] = m_val
        normalized_all.append(entry)
        items_by_year[str(y_val)].append(entry)

    yearly_tabs: List[Dict[str, Any]] = []
    yearly_by_key: Dict[str, Dict[str, Any]] = {}

    for y_key, y_label in YEAR_TABS_SEQUENCE:
        bucket = normalized_all if y_key == "all" else items_by_year.get(y_key, [])
        stat_obj = _build_single_period_stats(y_key, y_label, bucket)
        yearly_tabs.append(stat_obj)
        yearly_by_key[y_key] = stat_obj

    return {
        "default_year": "2026",
        "tabs": yearly_tabs,
        "by_key": yearly_by_key,
    }


def compute_user_profile_metrics(watchlist_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Kullanıcının izleme listesindeki yapımlardan genel metrikleri,
    Sinema Evrenleri rozetlerini ve 2026–2020 Yıllık İzleme İstatistiklerini üretir.
    """
    items = watchlist_items or []
    yearly_data = compute_yearly_watch_statistics(items)
    all_time_stats = yearly_data["by_key"]["all"]

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

    universe_badges.sort(
        key=lambda b: (b["is_completed"], b["is_started"], b["percent"], b["watched_count"]),
        reverse=True,
    )

    return {
        "total_watched": all_time_stats["total_count"],
        "movie_count": all_time_stats["movie_count"],
        "tv_count": all_time_stats["tv_count"],
        "watched_episodes_count": all_time_stats["episode_count"],
        "total_hours": all_time_stats["total_hours"],
        "total_days": all_time_stats["total_days"],
        "watch_time_label": all_time_stats["watch_time_label"],
        "avg_rating": all_time_stats["avg_rating"],
        "completed_universes_count": completed_universes_count,
        "active_universes_count": active_universes_count,
        "universe_badges": universe_badges,
        "yearly_stats": yearly_data,
    }
