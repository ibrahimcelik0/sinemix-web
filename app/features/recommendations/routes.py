"""Recommendations feature endpoint'leri (Bana Özel Top 10 Öneriler sayfası ve JSON API'si)."""

from flask import Blueprint, jsonify, render_template, request
from app.features.recommendations.services import (
    TOP_RECOMMENDATIONS_LIMIT,
    get_personalized_recommendations,
)
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
    Bana Özel Öneriler (Top 10) sayfası görünümü.
    - Oturum açmış veya izleme verisi olan kullanıcılar için %65 Kişisel Tür/Format Uyumu + %35 Kalite
      formülüyle henüz izlenmemiş en yüksek uyum skorlu Top 10 yapımı sunar.
    - Henüz hiç izleme/puan verisi olmayan kullanıcılar için Cold-Start kuralıyla katalogdaki
      en yüksek kalite/popülerlik skorlu Top 10 başlangıç önerisini sunar.
    """
    data = get_personalized_recommendations(limit=TOP_RECOMMENDATIONS_LIMIT)
    watchlist_count = len(WatchlistRepository.get_all())

    return render_template(
        "recommendations/recommendations.html",
        recommendations=data["recommendations"],
        profile=data["profile"],
        watchlist_empty=data["watchlist_empty"],
        is_cold_start=data.get("is_cold_start", False),
        watchlist_count=watchlist_count,
        active_page="recommendations",
    )


@recommendations_bp.route("/api/recommendations", methods=["GET"])
def api_recommendations():
    """Aktif oturumdaki kullanıcının Top 10 önerilerini JSON olarak döndürür."""
    data = get_personalized_recommendations(limit=TOP_RECOMMENDATIONS_LIMIT)
    return jsonify(data)


@recommendations_bp.route("/api/recommendations/preview", methods=["POST"])
def api_recommendations_preview():
    """
    Misafir kullanıcıların bellek içi (client-side JS state) izleme listesiyle
    dinamik Top 10 öneri algoritmasını çalıştırmasını sağlar.
    """
    payload = request.get_json(silent=True) or {}
    guest_watchlist = payload.get("watchlist") or []
    if not isinstance(guest_watchlist, list):
        guest_watchlist = []

    data = get_personalized_recommendations(
        limit=TOP_RECOMMENDATIONS_LIMIT,
        watchlist_items=guest_watchlist,
    )
    return jsonify(data)
