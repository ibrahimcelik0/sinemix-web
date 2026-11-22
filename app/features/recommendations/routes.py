"""Recommendations feature endpoint'leri (Sana Özel Öneriler sayfası ve Kalıcı/Geçici JSON API'si)."""

from flask import Blueprint, jsonify, render_template, request
from app.features.recommendations.services import get_personalized_recommendations
from app.features.watchlist.repository import WatchlistRepository

recommendations_bp = Blueprint(
    "recommendations",
    __name__,
    template_folder="templates",
)


@recommendations_bp.route("/oneriler")
@recommendations_bp.route("/recommendations")
def recommendations_page():
    """
    Sana Özel Öneriler sayfası görünümü.
    Oturum açmış kullanıcılar için `data/watchlists/<user_id>.json` üzerinden hesaplar;
    misafir kullanıcılar için sayfa her F5'te sıfırdan (boş) başlar ve
    bellek içi geçici listeyle test edilebilir.
    """
    data = get_personalized_recommendations(limit=100)
    watchlist_count = len(WatchlistRepository.get_all())

    return render_template(
        "recommendations/recommendations.html",
        recommendations=data["recommendations"],
        profile=data["profile"],
        watchlist_empty=data["watchlist_empty"],
        watchlist_count=watchlist_count,
        active_page="recommendations",
    )


@recommendations_bp.route("/api/recommendations", methods=["GET"])
def api_recommendations():
    """Aktif oturumdaki kullanıcının önerilerini JSON olarak döndürür."""
    data = get_personalized_recommendations(limit=100)
    return jsonify(data)


@recommendations_bp.route("/api/recommendations/preview", methods=["POST"])
def api_recommendations_preview():
    """
    Misafir (Geçici Demo Modu) kullanıcıların sunucudaki hiçbir `.json` dosyasına
    kayıt yapmadan, yalnızca o anki bellek içi (client-side JS state) izleme
    listesiyle öneri algoritmasını çalıştırmasını sağlar.
    """
    payload = request.get_json(silent=True) or {}
    guest_watchlist = payload.get("watchlist") or []
    if not isinstance(guest_watchlist, list):
        guest_watchlist = []

    data = get_personalized_recommendations(limit=100, watchlist_items=guest_watchlist)
    return jsonify(data)
