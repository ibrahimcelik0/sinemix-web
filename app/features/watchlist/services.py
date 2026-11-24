"""
Watchlist feature iş mantığı:
Yapımları TMDB/katalog detayları ile zenginleştirerek
`WatchlistRepository` üzerinden kullanıcının JSON dosyasına kaydetme, puanlama ve silme.
"""

from typing import Any, Dict, List
from app.features.watchlist.repository import WatchlistRepository


def get_user_watchlist() -> List[Dict[str, Any]]:
    """Kullanıcının izleme listesindeki tüm yapımları döndürür."""
    return WatchlistRepository.get_all()


def get_watchlist_stats() -> Dict[str, Any]:
    """İzleme listesi özet istatistiklerini döndürür."""
    items = WatchlistRepository.get_all()
    if not items:
        return {
            "total": 0,
            "movie_count": 0,
            "tv_count": 0,
            "avg_rating": 0.0,
            "liked_count": 0,
        }

    total = len(items)
    movie_count = sum(1 for i in items if i.get("media_type") == "movie")
    tv_count = sum(1 for i in items if i.get("media_type") == "tv")
    ratings = [int(i.get("user_rating", 0)) for i in items]
    avg_rating = round(sum(ratings) / total, 1) if total else 0.0
    liked_count = sum(1 for r in ratings if r >= 7)

    return {
        "total": total,
        "movie_count": movie_count,
        "tv_count": tv_count,
        "avg_rating": avg_rating,
        "liked_count": liked_count,
    }


def add_or_rate_watchlist_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Yapımı kullanıcının JSON dosyasına ekler veya puanını günceller.
    Eklendiği anda `genres` ve `keywords` verilerini katalogdan çekip JSON'a kaydeder.
    """
    tmdb_id = int(payload["tmdb_id"])
    media_type = str(payload.get("media_type", "movie")).lower()
    user_rating = max(1, min(10, int(float(payload.get("user_rating", 8)))))

    title = payload.get("title")
    poster_path = payload.get("poster_path")
    genres = payload.get("genres") or []
    keywords = payload.get("keywords") or []

    if not title or not genres or not keywords:
        from app.features.catalog.services import fetch_item_details_with_keywords
        details = fetch_item_details_with_keywords(tmdb_id=tmdb_id, media_type=media_type)
        if details:
            title = title or details.get("title")
            poster_path = poster_path or details.get("poster_path")
            if not genres:
                genres = details.get("genres") or []
            if not keywords:
                keywords = details.get("keywords") or []

    return WatchlistRepository.upsert({
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": title or "Bilinmeyen Yapım",
        "poster_path": poster_path or "",
        "user_rating": user_rating,
        "genres": genres,
        "keywords": keywords,
    })


def remove_watchlist_item(tmdb_id: int, media_type: str = "movie") -> bool:
    """Yapımı izleme listesinden çıkarır."""
    return WatchlistRepository.delete(tmdb_id=tmdb_id, media_type=media_type)


def clear_user_watchlist() -> None:
    """Tüm izleme listesini sıfırlar."""
    WatchlistRepository.clear_all()
