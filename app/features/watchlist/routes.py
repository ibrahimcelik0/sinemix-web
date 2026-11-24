"""Watchlist feature endpoint'leri (İzleme Listem sayfası ve JSON CRUD API'leri)."""

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from app.features.auth.services import login_required
from app.features.watchlist.services import (
    add_or_rate_watchlist_item,
    clear_user_watchlist,
    get_user_watchlist,
    get_watchlist_stats,
    remove_watchlist_item,
)
from app.features.recommendations.services import build_user_interest_profile

watchlist_bp = Blueprint(
    "watchlist",
    __name__,
    template_folder="templates",
)


@watchlist_bp.route("/izleme-listem")
@watchlist_bp.route("/watchlist")
@login_required
def watchlist_page():
    """İzleme Listem sayfası görünümü (Sadece giriş yapmış kullanıcının kendi listesi)."""
    items = get_user_watchlist()
    stats = get_watchlist_stats()
    profile = build_user_interest_profile(items)

    return render_template(
        "watchlist/watchlist.html",
        items=items,
        stats=stats,
        profile=profile,
        watchlist_count=len(items),
        active_page="watchlist",
    )


@watchlist_bp.route("/api/watchlist", methods=["GET"])
@login_required
def api_get_watchlist():
    """Aktif kullanıcının izleme listesini JSON olarak döndürür."""
    items = get_user_watchlist()
    return jsonify({"items": items, "stats": get_watchlist_stats()})


@watchlist_bp.route("/api/watchlist", methods=["POST"])
@login_required
def api_add_watchlist():
    """Aktif kullanıcının `data/watchlists/<user_id>.json` listesine yapım ekler veya puanını günceller."""
    data = request.get_json(silent=True) or request.form.to_dict()
    if not data or "tmdb_id" not in data:
        return jsonify({"error": "tmdb_id zorunludur"}), 400

    record = add_or_rate_watchlist_item(data)
    return jsonify({
        "status": "ok",
        "item": record,
        "stats": get_watchlist_stats(),
    })


@watchlist_bp.route("/api/watchlist/<string:media_type>/<int:tmdb_id>", methods=["DELETE"])
@login_required
def api_delete_watchlist(media_type: str, tmdb_id: int):
    """Belirtilen yapımı aktif kullanıcının izleme listesinden siler."""
    deleted = remove_watchlist_item(tmdb_id=tmdb_id, media_type=media_type)
    return jsonify({
        "status": "ok" if deleted else "not_found",
        "deleted": deleted,
        "stats": get_watchlist_stats(),
    })


@watchlist_bp.route("/api/watchlist/clear", methods=["POST"])
@login_required
def api_clear_watchlist():
    """Aktif kullanıcının izleme listesini tamamen sıfırlar."""
    clear_user_watchlist()
    if request.accept_mimetypes.best == "application/json" or request.is_json:
        return jsonify({
            "status": "ok",
            "items": [],
            "stats": get_watchlist_stats(),
        })
    return redirect(url_for("watchlist.watchlist_page"))
