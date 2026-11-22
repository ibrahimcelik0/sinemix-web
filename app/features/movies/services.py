"""Movies feature iş mantığı (Business logic)."""

from typing import Any, Dict, List, Optional
from app.core.tmdb_fallback import FALLBACK_TMDB_CATALOG
from app.core.utils import FILM_VERITABANI, find_by_field


def get_all_movies() -> List[Dict[str, Any]]:
    """Tüm filmlerin listesini döndürür."""
    return FILM_VERITABANI


def get_movie_by_id(movie_id: int) -> Optional[Dict[str, Any]]:
    """Verilen ID'ye sahip filmi veya TMDB yapımını döndürür. Bulunamazsa None döner."""
    found = find_by_field(FILM_VERITABANI, "id", movie_id)
    if found:
        return found

    for item in FALLBACK_TMDB_CATALOG:
        if int(item["tmdb_id"]) == int(movie_id):
            return {
                "id": int(item["tmdb_id"]),
                "isim": item["title"],
                "puan": str(item.get("vote_average", "8.0")),
                "yil": item.get("release_year", 2024),
                "tur": ", ".join(item.get("genres", [])),
                "yonetmen": item.get("director", ""),
                "resim": item["poster_path"],
                "konu": item.get("overview", ""),
            }
    return None


def get_default_movie() -> Optional[Dict[str, Any]]:
    """Varsayılan olarak ilk filmi döndürür (/detay rotası için)."""
    return FILM_VERITABANI[0] if FILM_VERITABANI else None
