"""Catalog feature endpoint'leri (Keşfet & Ekle, Sinematik İçerik Detay Sayfası ve TMDB Arama API'si)."""

from flask import Blueprint, abort, jsonify, render_template, request
from app.features.catalog.services import (
    fetch_comprehensive_item_detail,
    get_available_genres,
    is_tmdb_live_enabled,
    search_multi_catalog,
)
from app.features.watchlist.repository import WatchlistRepository

catalog_bp = Blueprint(
    "catalog",
    __name__,
    template_folder="templates",
)


@catalog_bp.route("/")
@catalog_bp.route("/kesfet")
def discover():
    """Keşfet & Ekle ana görünümü."""
    q = request.args.get("q", "").strip()
    media_type = request.args.get("media_type", "ALL").strip()
    genre = request.args.get("genre", "ALL").strip()
    sort_by = request.args.get("sort_by", "popularity").strip()

    items = search_multi_catalog(query=q, media_type=media_type, genre=genre, sort_by=sort_by)
    watchlist_count = len(WatchlistRepository.get_all())

    return render_template(
        "catalog/discover.html",
        items=items,
        genres=get_available_genres(),
        watchlist_count=watchlist_count,
        tmdb_live=is_tmdb_live_enabled(),
        active_page="discover",
    )


@catalog_bp.route("/detail/<string:media_type>/<int:tmdb_id>")
def detail(media_type: str, tmdb_id: int):
    """
    Herhangi bir film veya dizi kartına tıklandığında açılan
    kapsamlı ve sinematik İçerik Detay Sayfası (/detail/<media_type>/<int:tmdb_id>).
    """
    if media_type not in ("movie", "tv"):
        media_type = "movie"

    item = fetch_comprehensive_item_detail(tmdb_id=tmdb_id, media_type=media_type)
    if not item:
        abort(404, description="İçerik bulunamadı.")

    watchlist_count = len(WatchlistRepository.get_all())

    return render_template(
        "catalog/detail.html",
        item=item,
        watchlist_count=watchlist_count,
        tmdb_live=is_tmdb_live_enabled(),
        active_page="detail",
    )


@catalog_bp.route("/api/catalog/search")
def api_search():
    """Canlı film ve dizi arama JSON API uç noktası."""
    q = request.args.get("q", "").strip()
    media_type = request.args.get("media_type", "ALL").strip()
    genre = request.args.get("genre", "ALL").strip()
    sort_by = request.args.get("sort_by", "popularity").strip()

    items = search_multi_catalog(query=q, media_type=media_type, genre=genre, sort_by=sort_by)
    return jsonify({
        "items": items,
        "total": len(items),
        "tmdb_live": is_tmdb_live_enabled(),
    })


@catalog_bp.route("/api/catalog/<string:media_type>/<int:tmdb_id>")
def api_item_detail(media_type: str, tmdb_id: int):
    """TMDB üzerinden tekil film/dizi tüm detaylarını JSON olarak döndürür."""
    detail_data = fetch_comprehensive_item_detail(tmdb_id=tmdb_id, media_type=media_type)
    if not detail_data:
        return jsonify({"error": "Yapım bulunamadı"}), 404
    return jsonify(detail_data)
