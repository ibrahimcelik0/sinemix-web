"""Main feature iş mantığı (5000+ Film & Dizi ölçeklenebilir arama, filtreleme ve sayfalama servisi)."""

import math
from typing import Any, Dict, List, Optional
from app.core.utils import (
    EVRENSEL_TURLER,
    FILM_VERITABANI,
    ICERIK_TIPLERI,
    fuzzy_text_match,
    normalize_search_text,
)


def get_featured_movies() -> List[Dict[str, Any]]:
    """Ana sayfada listelenecek öne çıkan içerikleri döndürür."""
    return FILM_VERITABANI


def get_filter_metadata() -> Dict[str, Any]:
    """
    5000+ içerikli katalog için evrensel filtre seçeneklerini döndürür.
    (Sabit 7 filme göre değil, tüm sinema/dizi kataloğuna uygun yapı).
    """
    return {
        "turler": EVRENSEL_TURLER,
        "tipler": ICERIK_TIPLERI,
        "min_yil_limit": 1920,
        "max_yil_limit": 2026,
    }


def search_and_filter_catalog(
    q: str = "",
    tip: str = "ALL",
    turler: Optional[List[str]] = None,
    min_yil: Optional[int] = None,
    max_yil: Optional[int] = None,
    yonetmen: str = "",
    oyuncu: str = "",
    min_puan: float = 0.0,
    siralama: str = "title-asc",
    page: int = 1,
    per_page: int = 24,
) -> Dict[str, Any]:
    """
    5000+ Film ve Dizi kataloğu için sunucu taraflı (server-side)
    filtreleme, sıralama ve sayfalama (pagination) motoru.
    """
    selected_genres = [normalize_search_text(t) for t in (turler or []) if t.strip()]
    results: List[Dict[str, Any]] = []

    for item in FILM_VERITABANI:
        item_title = item.get("isim", "")
        item_type = item.get("tip", "Film")
        item_genres_raw = item.get("tur", "")
        item_genres = [normalize_search_text(g) for g in item_genres_raw.split(",") if g.strip()]
        item_year = int(item.get("yil", 0) or 0)
        item_director = item.get("yonetmen", "")
        item_cast = item.get("oyuncular", "")
        item_rating = float(item.get("puan", 0) or 0)

        # 1. İçerik Tipi (Film / Dizi)
        if tip and tip != "ALL":
            if normalize_search_text(item_type) != normalize_search_text(tip):
                continue

        # 2. Film / Dizi İsmi Arama (Büyük/küçük harf duyarsız + yazım hatası toleranslı)
        if q and not fuzzy_text_match(item_title, q):
            continue

        # 3. Çoklu Tür Filtresi (Seçilen türlerden en az birini veya tamamını içerme)
        if selected_genres:
            if not any(sg in item_genres for sg in selected_genres):
                continue

        # 4. Yapım Yılı Aralığı (Min Yıl - Max Yıl)
        if min_yil is not None and item_year < min_yil:
            continue
        if max_yil is not None and item_year > max_yil:
            continue

        # 5. Yönetmen Arama (Serbest metin + yazım toleranslı)
        if yonetmen and not fuzzy_text_match(item_director, yonetmen):
            continue

        # 6. Oyuncu / Kadro Arama (Serbest metin + yazım toleranslı)
        if oyuncu and not fuzzy_text_match(item_cast, oyuncu):
            continue

        # 7. Minimum IMDb Puanı
        if min_puan > 0 and item_rating < min_puan:
            continue

        results.append(item)

    # Sıralama
    if siralama == "title-asc":
        results.sort(key=lambda x: normalize_search_text(x.get("isim", "")))
    elif siralama == "title-desc":
        results.sort(key=lambda x: normalize_search_text(x.get("isim", "")), reverse=True)
    elif siralama == "year-desc":
        results.sort(key=lambda x: (int(x.get("yil", 0) or 0), normalize_search_text(x.get("isim", ""))), reverse=True)
    elif siralama == "year-asc":
        results.sort(key=lambda x: (int(x.get("yil", 0) or 0), normalize_search_text(x.get("isim", ""))))
    elif siralama == "rating-desc":
        results.sort(key=lambda x: (float(x.get("puan", 0) or 0), normalize_search_text(x.get("isim", ""))), reverse=True)
    elif siralama == "rating-asc":
        results.sort(key=lambda x: (float(x.get("puan", 0) or 0), normalize_search_text(x.get("isim", ""))))

    # Sayfalama (5000+ içerik için)
    total_items = len(results)
    per_page = max(1, min(per_page, 100))
    total_pages = max(1, math.ceil(total_items / per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_items = results[start_idx:end_idx]

    return {
        "items": paginated_items,
        "total": total_items,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
