"""Catalog feature endpoint'leri (Keşfet & Ekle, Sinematik İçerik Detay Sayfası ve TMDB Arama API'si)."""

from flask import Blueprint, abort, jsonify, render_template, request
from app.features.auth.services import get_current_user
from app.features.catalog.repository import ContentRequestRepository
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



@catalog_bp.route("/api/requests", methods=["POST"])
def api_submit_content_request():
    """
    Kullanıcıların 434 yapımlık katalogda bulamadıkları Film / Dizi / Animasyon
    içeriklerini talep edebileceği API uç noktası (`data/requests.json`).
    """
    payload = request.get_json(silent=True) or request.form.to_dict() or {}
    title = (payload.get("title") or "").strip()
    if not title or len(title) < 2:
        return jsonify({"error": "Lütfen geçerli bir yapım adı girin."}), 400

    media_type = (payload.get("media_type") or "Film").strip()
    year = (str(payload.get("year") or "")).strip()
    note = (payload.get("note") or "").strip()

    user = get_current_user()
    requested_by = user["username"] if user else "misafir"

    record, is_duplicate = ContentRequestRepository.create_or_increment_request(
        title=title,
        media_type=media_type,
        year=year,
        note=note,
        requested_by=requested_by,
    )

    if is_duplicate:
        msg = f"'{record['title']}' için talebiniz eklendi (Toplam {record['request_count']} kez talep edildi). En kısa sürede kataloğa eklenecek!"
    else:
        msg = "Talebin alındı, en kısa sürede kataloğa eklenecek!"

    return jsonify({
        "status": "ok",
        "is_duplicate": is_duplicate,
        "message": msg,
        "request": record,
    })
