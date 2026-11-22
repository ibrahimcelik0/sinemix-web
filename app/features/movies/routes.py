"""Movies feature endpoint'leri (Eski /film/<id> rotalarını yeni /detail/<media_type>/<tmdb_id> sayfasına yönlendirir)."""

from flask import Blueprint, redirect, render_template, url_for
from app.features.catalog.services import resolve_legacy_id

movies_bp = Blueprint(
    "movies",
    __name__,
    template_folder="templates",
)


@movies_bp.route("/film/<int:id>")
def film_detay(id: int):
    """Eski film detay rotasını yeni sinematik detay sayfasına yönlendirir."""
    resolved = resolve_legacy_id(id, "movie")
    return redirect(url_for("catalog.detail", media_type=resolved["media_type"], tmdb_id=resolved["tmdb_id"]))


@movies_bp.route("/detay")
def detay():
    """Varsayılan detay sayfası görünümü."""
    return redirect(url_for("catalog.detail", media_type="movie", tmdb_id=157336))


@movies_bp.route("/yorum_yap/<string:film_ismi>")
@movies_bp.route("/yorum-yap/<string:film_ismi>")
def yorum_yap(film_ismi: str):
    """Belirli bir film için yorum yapma sayfasını gösterir."""
    return render_template("movies/yorum.html", film_adi=film_ismi)
