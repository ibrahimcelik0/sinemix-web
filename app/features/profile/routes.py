"""Profile feature endpoint'leri (Aktif oturumdaki kullanıcının dinamik profili)."""

from flask import Blueprint, render_template
from app.features.auth.services import get_current_user, login_required
from app.features.profile.services import get_dynamic_user_profile
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
    """Giriş yapmış kullanıcının dinamik profil sayfası görünümü."""
    current_user = get_current_user()
    kullanici_bilgisi = get_dynamic_user_profile(current_user)
    items = get_user_watchlist()
    stats = get_watchlist_stats()
    taste_profile = build_user_interest_profile(items)

    return render_template(
        "profile/profil.html",
        kullanici=kullanici_bilgisi,
        stats=stats,
        profile=taste_profile,
        recent_items=items[:4],
        active_page="profile",
    )
