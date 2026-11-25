"""Profile feature endpoint'leri (Aktif oturumdaki kullanıcının dinamik profili ve 2026–2020 yıllık istatistikleri)."""

from flask import Blueprint, render_template, request
from app.features.auth.services import get_current_user, login_required
from app.features.profile.services import (
    compute_user_profile_metrics,
    get_dynamic_user_profile,
)
from app.features.watchlist.services import get_user_watchlist, get_watchlist_stats
from app.features.recommendations.services import build_user_interest_profile

profile_bp = Blueprint(
    "profile",
    __name__,
    template_folder="templates",
)


@profile_bp.route("/profil")
@profile_bp.route("/profile")
@login_required
def profil():
    """Giriş yapmış kullanıcının dinamik profil ve 2026–2020 yıllık istatistik sayfası."""
    current_user = get_current_user()
    kullanici_bilgisi = get_dynamic_user_profile(current_user)
    items = get_user_watchlist()
    stats = get_watchlist_stats()
    profile_metrics = compute_user_profile_metrics(items)
    taste_profile = build_user_interest_profile(items)

    requested_year = (request.args.get("year") or "2026").strip().lower()
    valid_keys = {t["year_key"] for t in profile_metrics["yearly_stats"]["tabs"]}
    selected_year = requested_year if requested_year in valid_keys else "2026"

    return render_template(
        "profile/profil.html",
        kullanici=kullanici_bilgisi,
        stats=stats,
        metrics=profile_metrics,
        yearly_stats=profile_metrics["yearly_stats"],
        selected_year=selected_year,
        profile=taste_profile,
        recent_items=items[:6],
        active_page="profile",
    )
