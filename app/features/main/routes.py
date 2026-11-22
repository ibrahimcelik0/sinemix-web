"""Main feature endpoint'leri (Blueprint - Geriye dönük uyumluluk ve gelişmiş katalog filtresi)."""

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from app.features.main.services import (
    get_featured_movies,
    get_filter_metadata,
    search_and_filter_catalog,
)
from app.features.watchlist.repository import WatchlistRepository

main_bp = Blueprint(
    "main",
    __name__,
    template_folder="templates",
)


@main_bp.route("/anasayfa")
def anasayfa():
    """Ana sayfa yönlendirmesi (Keşfet & Ekle platformuna yönlendirir)."""
    return redirect(url_for("catalog.discover"))


@main_bp.route("/filtre")
def filtre():
    """5000+ Film & Dizi ölçeklenebilir gelişmiş filtreleme sayfası."""
    meta = get_filter_metadata()
    filmler = get_featured_movies()
    watchlist_count = len(WatchlistRepository.get_all())
    return render_template(
        "main/filtre.html",
        filmler=filmler,
        meta=meta,
        watchlist_count=watchlist_count,
    )


@main_bp.route("/api/catalog")
def api_catalog():
    """
    5000+ Film & Dizi için sunucu taraflı (server-side) filtreleme ve sayfalama JSON API'si.
    """
    q = request.args.get("q", "").strip()
    tip = request.args.get("tip", "ALL").strip()
    turler_param = request.args.get("turler", "").strip()
    turler = [t for t in turler_param.split(",") if t.strip()] if turler_param else []

    min_yil_raw = request.args.get("min_yil", "").strip()
    max_yil_raw = request.args.get("max_yil", "").strip()
    min_yil = int(min_yil_raw) if min_yil_raw.isdigit() else None
    max_yil = int(max_yil_raw) if max_yil_raw.isdigit() else None

    yonetmen = request.args.get("yonetmen", "").strip()
    oyuncu = request.args.get("oyuncu", "").strip()

    try:
        min_puan = float(request.args.get("min_puan", "0"))
    except ValueError:
        min_puan = 0.0

    siralama = request.args.get("siralama", "title-asc").strip()

    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1

    try:
        per_page = int(request.args.get("per_page", "24"))
    except ValueError:
        per_page = 24

    result = search_and_filter_catalog(
        q=q,
        tip=tip,
        turler=turler,
        min_yil=min_yil,
        max_yil=max_yil,
        yonetmen=yonetmen,
        oyuncu=oyuncu,
        min_puan=min_puan,
        siralama=siralama,
        page=page,
        per_page=per_page,
    )

    enriched_items = []
    for item in result["items"]:
        enriched = dict(item)
        enriched["detay_url"] = url_for("movies.film_detay", id=item["id"])
        enriched_items.append(enriched)

    result["items"] = enriched_items
    return jsonify(result)
