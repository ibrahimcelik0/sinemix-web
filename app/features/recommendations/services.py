"""
Dinamik, Ağırlıklı Skorlamaya Dayalı Akıllı Öneri Algoritması (`app/features/recommendations/services.py`):

Temel Prensipler:
1. Sabit Tür veya Format Kotası Yoktur:
   - Film (`movie`) ve Dizi (`tv`) için sabit sayı zorunluluğu koymaz.
   - Kullanıcının izlediği ve puanladığı yapımlardan Tür (`genres`), Format (`movie` / `tv`) ve Tema (`keywords`)
     ağırlıklarını çıkarır; ağırlıklı dizi izleyen kullanıcıya doğal olarak dizileri, dengeli izleyene hem film
     hem dizileri öne çıkarır.
2. Ağırlıklı Skorlama Formülü (%65 Kişisel Tür/Format Uyumu + %35 Yapım Kalite & Popülerlik Puanı):
   - İzlenenleri Filtrele: Kullanıcının izleme geçmişinde (`watchlist`) yer alan yapımlar aday havuzundan tamamen
     çıkarılır. Bir öneri "İzledim" olarak işaretlendiği an listeden düşer ve sıradaki en yüksek skorlu yapım gelir.
   - Kullanıcı Zevk Profili (Genre & Format Affinity):
     * 7–10 arası yüksek puan verilen yapımların türlerine ve formatına güçlü pozitif ağırlık,
     * 1–4 arası düşük puan verilen yapımların türlerine negatif ağırlık atanır.
   - Kalite ve Popülerlik Dengesi: Katalogdaki IMDb/TMDB puanı (`vote_average`) ve popülerlik değeri normalize
     edilerek (%35 ağırlık) kişisel zevk uyumuyla (%65 ağırlık) birleştirilir ve 0–100 arası Uyum Skoru üretilir.
3. Cold-Start (Yeni Kullanıcı / Boş Liste) Kuralı:
   - Kullanıcının henüz hiç izleme/puan verisi yoksa katalogdaki en yüksek kalite ve popülerlik skoruna sahip
     Top 10 yapım başlangıç önerisi olarak sunulur.
"""

from collections import defaultdict
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from app.features.catalog.repository import CatalogRepository, extract_genre_names
from app.features.watchlist.repository import WatchlistRepository

TOP_RECOMMENDATIONS_LIMIT = 10


def _rating_to_weight(user_rating: int) -> float:
    """
    1-10 arası kullanıcı puanını profil ağırlığına dönüştürür:
    - 7..10 arası yüksek puanlar güçlü pozitif ağırlık (+3.0 ile +7.5 arası)
    - 6 puan hafif pozitif (+1.5)
    - 5 puan nötr (+0.2)
    - 1..4 arası düşük puanlar negatif ağırlık (-2.0 ile -6.5 arası)
    """
    r = max(1, min(10, int(user_rating)))
    if r >= 7:
        return (r - 5) * 1.5
    if r == 6:
        return 1.5
    if r == 5:
        return 0.2
    return (r - 5.3) * 1.5


def _format_match_badge(match_score: int, genres: List[str]) -> str:
    """Kart üzerinde gösterilecek dinamik uyum rozeti metnini üretir (Örn: '%94 Uyum • Suç & Dram')."""
    top_genres = [str(g).strip() for g in (genres or []) if str(g).strip()][:2]
    if top_genres:
        return f"%{match_score} Uyum • {' & '.join(top_genres)}"
    return f"%{match_score} Uyum"


def _compute_catalog_quality_norm(item: Dict[str, Any], max_popularity: float = 200.0) -> float:
    """
    Yapımın TMDB/IMDb puanını (`vote_average`) ve popülerliğini `[0.0, 1.0]` aralığında
    normalize edilmiş bir Kalite Skoruna dönüştürür (%80 Puan Kalitesi + %20 Popülerlik).
    """
    vote_avg = float(item.get("vote_average") or 7.0)
    popularity = max(1.0, float(item.get("popularity") or 50.0))

    # 5.5 - 9.3 aralığını 0.0 - 1.0 aralığına ölçekle
    vote_norm = max(0.0, min(1.0, (vote_avg - 5.5) / 3.8))
    pop_norm = max(0.0, min(1.0, math.log1p(popularity) / math.log1p(max(10.0, max_popularity))))

    return round((vote_norm * 0.80) + (pop_norm * 0.20), 4)


def build_user_interest_profile(watchlist_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Kullanıcının izlediği ve puanladığı yapımlardan:
    - Tür ağırlıklarını (`genre_weights`),
    - Format eğilimini (`format_affinity`: `movie` vs `tv`),
    - Anahtar kelime/tema ağırlıklarını (`keyword_weights`)
    hesaplar.
    """
    if watchlist_items is None:
        watchlist_items = WatchlistRepository.get_all()

    genre_weights: Dict[str, float] = defaultdict(float)
    keyword_weights: Dict[str, float] = defaultdict(float)
    format_scores: Dict[str, float] = {"movie": 0.0, "tv": 0.0}
    format_counts: Dict[str, int] = {"movie": 0, "tv": 0}

    for item in watchlist_items:
        rating = int(item.get("user_rating", 7))
        weight = _rating_to_weight(rating)
        m_type = str(item.get("media_type", "movie")).lower()
        if m_type not in ("movie", "tv"):
            m_type = "movie"

        format_counts[m_type] += 1
        # Pozitif/nötr izlemeler format tercihini artırır; düşük puanlar daha az artırır
        format_scores[m_type] += max(0.25, weight + 1.5)

        for genre in extract_genre_names(item.get("genres")):
            g_clean = str(genre).strip()
            if g_clean:
                genre_weights[g_clean] = round(genre_weights[g_clean] + weight, 2)

        for kw in item.get("keywords") or []:
            kw_clean = str(kw).strip().lower()
            if kw_clean:
                keyword_weights[kw_clean] = round(keyword_weights[kw_clean] + (weight * 1.15), 2)

    total_format_score = format_scores["movie"] + format_scores["tv"]
    if total_format_score > 0:
        movie_share = format_scores["movie"] / total_format_score
        tv_share = format_scores["tv"] / total_format_score
    else:
        movie_share = 0.5
        tv_share = 0.5

    # Format Affinity: 0.0 ile 1.0 arasında normalize değer (0.5 = dengeli, 1.0 = tamamen o format)
    format_affinity = {
        "movie": round(movie_share, 3),
        "tv": round(tv_share, 3),
    }

    sorted_genres = sorted(genre_weights.items(), key=lambda x: x[1], reverse=True)
    sorted_keywords = sorted(keyword_weights.items(), key=lambda x: x[1], reverse=True)

    favorite_genres = [{"name": k, "weight": v} for k, v in sorted_genres if v > 0][:6]
    disliked_genres = [{"name": k, "weight": v} for k, v in sorted_genres if v < 0]
    favorite_keywords = [{"name": k, "weight": v} for k, v in sorted_keywords if v > 0][:10]

    preferred_format_label = "Film & Dizi Dengeli"
    if movie_share >= 0.68:
        preferred_format_label = "Film Ağırlıklı"
    elif tv_share >= 0.68:
        preferred_format_label = "Dizi Ağırlıklı"

    return {
        "genre_weights": dict(genre_weights),
        "keyword_weights": dict(keyword_weights),
        "format_affinity": format_affinity,
        "format_counts": format_counts,
        "preferred_format_label": preferred_format_label,
        "favorite_genres": favorite_genres,
        "disliked_genres": disliked_genres,
        "favorite_keywords": favorite_keywords,
    }


def _build_cold_start_recommendations(
    catalog_items: List[Dict[str, Any]],
    limit: int = TOP_RECOMMENDATIONS_LIMIT,
) -> List[Dict[str, Any]]:
    """
    Cold-Start (Yeni Kullanıcı) Kuralı:
    Kullanıcının henüz hiç izleme/puan verisi yoksa katalogdaki en yüksek kalite
    ve popülerlik skoruna sahip en iyi 10 yapımı başlangıç önerisi olarak döndürür.
    """
    if not catalog_items:
        return []

    max_pop = max((float(i.get("popularity") or 1.0) for i in catalog_items), default=200.0)
    scored: List[Dict[str, Any]] = []

    for item in catalog_items:
        q_norm = _compute_catalog_quality_norm(item, max_popularity=max_pop)
        # Cold-start kalite uyum skoru: 84 - 97 aralığı
        match_score = int(round(max(82.0, min(97.0, 74.0 + (q_norm * 24.0)))))
        c_genres = item.get("genres") or []

        enriched = dict(item)
        enriched["match_score"] = match_score
        enriched["matched_genres"] = c_genres[:2]
        enriched["matched_keywords"] = (item.get("keywords") or [])[:3]
        enriched["seed_sources"] = []
        enriched["is_cold_start"] = True
        enriched["match_badge_text"] = _format_match_badge(match_score, c_genres)
        enriched["why_recommended"] = (
            f"SineMix Başlangıç Seçkisi • Yüksek izleyici puanı (⭐ {item.get('vote_average', 8.0)}) "
            f"ve {', '.join(c_genres[:2]) or 'Popüler'} türünde öne çıkan başyapıt."
        )
        enriched["_sort_score"] = q_norm
        scored.append(enriched)

    scored.sort(
        key=lambda x: (x["_sort_score"], float(x.get("vote_average") or 0), float(x.get("popularity") or 0)),
        reverse=True,
    )

    top_items = scored[:limit]
    for it in top_items:
        it.pop("_sort_score", None)
    return top_items


def get_personalized_recommendations(
    limit: int = TOP_RECOMMENDATIONS_LIMIT,
    watchlist_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Dinamik Ağırlıklı Öneri Motoru (Varsayılan: Top 10):
    - Sabit tür/format kotası uygulamadan tüm izlenmemiş katalog öğelerine
      `%65 Kişisel Tür/Format/Tema Uyumu + %35 Yapım Kalite Puanı` formülüyle
      0–100 arası Uyum Skoru verir ve en yüksek skorlu ilk `limit` (10) yapımı döndürür.
    - Kullanıcının hiç izleme verisi yoksa Cold-Start kuralıyla en yüksek kaliteli 10 yapımı döndürür.
    """
    if watchlist_items is None:
        watchlist_items = WatchlistRepository.get_all()

    catalog_items = CatalogRepository.get_all()
    profile = build_user_interest_profile(watchlist_items)

    # Cold-Start: Henüz hiç izlenen/puanlanan yapım yoksa en yüksek kaliteli Top 10 yapımı sun
    if not watchlist_items:
        cold_start_recs = _build_cold_start_recommendations(catalog_items, limit=limit)
        return {
            "recommendations": cold_start_recs,
            "profile": profile,
            "watchlist_empty": True,
            "is_cold_start": True,
            "total_count": len(cold_start_recs),
        }

    # İzlenen yapımları aday havuzundan tamamen çıkar
    watched_keys: Set[Tuple[int, str]] = {
        (int(item.get("tmdb_id", 0)), str(item.get("media_type", "movie")).lower())
        for item in watchlist_items
        if item.get("tmdb_id")
    }
    watched_ids_only: Set[int] = {
        int(item.get("tmdb_id", 0))
        for item in watchlist_items
        if item.get("tmdb_id")
    }

    unwatched_candidates = [
        item for item in catalog_items
        if (int(item["tmdb_id"]), str(item.get("media_type", "movie")).lower()) not in watched_keys
        and int(item["tmdb_id"]) not in watched_ids_only
    ]

    genre_weights: Dict[str, float] = profile["genre_weights"]
    keyword_weights: Dict[str, float] = profile["keyword_weights"]
    format_affinity: Dict[str, float] = profile["format_affinity"]

    positive_genre_scores = sorted([w for w in genre_weights.values() if w > 0], reverse=True)
    positive_kw_scores = sorted([w for w in keyword_weights.values() if w > 0], reverse=True)

    # Tek bir yapımın alabileceği referans maksimum tür ve tema ağırlığı
    max_possible_genre = sum(positive_genre_scores[:2]) if positive_genre_scores else 6.0
    max_possible_genre = max(3.0, max_possible_genre)
    max_possible_kw = sum(positive_kw_scores[:3]) if positive_kw_scores else 6.0
    max_possible_kw = max(3.0, max_possible_kw)

    max_popularity = max((float(i.get("popularity") or 1.0) for i in unwatched_candidates), default=200.0)

    # Yüksek puanlı (7-10) izlenen yapımları referans tohum olarak hazırla
    high_rated_watched = sorted(
        [w for w in watchlist_items if int(w.get("user_rating", 0)) >= 7],
        key=lambda x: int(x.get("user_rating", 0)),
        reverse=True,
    )

    scored_recommendations: List[Dict[str, Any]] = []

    for candidate in unwatched_candidates:
        c_type = str(candidate.get("media_type", "movie")).lower()
        c_genres = candidate.get("genres") or []
        c_keywords = [str(k).lower() for k in (candidate.get("keywords") or [])]

        # 1. Tür (Genre) Uyumu (-0.5 ile +1.0 arası)
        genre_raw = 0.0
        matched_genres: List[str] = []
        disliked_hit_count = 0
        for g in c_genres:
            w = genre_weights.get(g, 0.0)
            genre_raw += w
            if w > 0:
                matched_genres.append(g)
            elif w < 0:
                disliked_hit_count += 1

        # Eşleşen türleri kullanıcının en sevdiği sıraya göre diz
        matched_genres.sort(key=lambda g_name: genre_weights.get(g_name, 0.0), reverse=True)
        genre_norm = max(-0.45, min(1.0, genre_raw / max_possible_genre))

        # 2. Format (Film / Dizi) Uyumu (0.0 ile 1.0 arası)
        # Kullanıcının izleme geçmişi dizi ağırlıklıysa diziler, film ağırlıklıysa filmler doğal bonus alır
        user_format_share = float(format_affinity.get(c_type, 0.5))
        format_norm = max(0.15, min(1.0, user_format_share * 1.45))

        # 3. Tema (Keyword) ve Referans Yapım Komşuluğu (0.0 ile 1.0 arası)
        kw_raw = 0.0
        matched_keywords: List[str] = []
        for kw in c_keywords:
            w = keyword_weights.get(kw, 0.0)
            if w > 0:
                kw_raw += w
                matched_keywords.append(kw)
        kw_norm = max(0.0, min(1.0, kw_raw / max_possible_kw))

        seed_sources: List[Dict[str, Any]] = []
        c_genre_set = set(c_genres)
        c_kw_set = set(c_keywords)
        for seed in high_rated_watched[:8]:
            s_genres = set(extract_genre_names(seed.get("genres")))
            s_kws = {str(k).lower() for k in (seed.get("keywords") or [])}
            shared_g = c_genre_set & s_genres
            shared_k = c_kw_set & s_kws
            if len(shared_g) >= 2 or (len(shared_g) >= 1 and (len(shared_k) >= 1 or seed.get("media_type") == c_type)):
                seed_sources.append({
                    "title": seed.get("title", ""),
                    "rating": int(seed.get("user_rating", 8)),
                })
            if len(seed_sources) >= 2:
                break

        # Kişisel Uyum Skoru Bileşeni ([0.0, 1.0] -> %65 Ağırlık)
        # Tür uyumu (%70), Format uyumu (%20), Tema/Tohum komşuluğu (%10)
        seed_norm = min(1.0, len(seed_sources) * 0.55)
        theme_and_seed_norm = max(kw_norm, seed_norm)

        personal_affinity_norm = (
            (genre_norm * 0.70)
            + (format_norm * 0.20)
            + (theme_and_seed_norm * 0.10)
        )
        if disliked_hit_count > 0 and not matched_genres:
            personal_affinity_norm -= 0.25

        personal_affinity_norm = max(0.0, min(1.0, personal_affinity_norm))

        # Yapım Kalite & Popülerlik Bileşeni ([0.0, 1.0] -> %35 Ağırlık)
        quality_norm = _compute_catalog_quality_norm(candidate, max_popularity=max_popularity)

        # Toplam Ağırlıklı Skor (%65 Kişisel Uyum + %35 Yapım Kalitesi)
        weighted_total = (personal_affinity_norm * 65.0) + (quality_norm * 35.0)

        # Kullanıcı dostu 0-100 Uyum Skoru ölçeklemesi
        if matched_genres or seed_sources:
            display_score = int(round(max(55.0, min(99.0, 38.0 + (weighted_total * 0.62)))))
        else:
            display_score = int(round(max(35.0, min(78.0, 25.0 + (weighted_total * 0.55)))))

        badge_genres = matched_genres[:2] if matched_genres else c_genres[:2]
        match_badge_text = _format_match_badge(display_score, badge_genres)

        reasons: List[str] = []
        if seed_sources:
            source_labels = [f"{s['title']} ({s['rating']}/10)" for s in seed_sources[:2]]
            reasons.append(f"{' ve '.join(source_labels)} yapımlarına yüksek puan verdin")
        if matched_genres:
            reasons.append(f"Sevdiğin türler: {', '.join(matched_genres[:3])}")
        if matched_keywords:
            reasons.append(f"Ortak temalar: {', '.join(matched_keywords[:3])}")

        why_recommended = (
            " • ".join(reasons)
            if reasons
            else f"İzleme profilin ve yüksek kalite puanı (⭐ {candidate.get('vote_average', 8.0)}) ile öne çıktı."
        )

        enriched = dict(candidate)
        enriched["match_score"] = display_score
        enriched["matched_genres"] = matched_genres[:3] if matched_genres else c_genres[:2]
        enriched["matched_keywords"] = matched_keywords[:4]
        enriched["seed_sources"] = seed_sources
        enriched["is_cold_start"] = False
        enriched["match_badge_text"] = match_badge_text
        enriched["why_recommended"] = why_recommended
        enriched["_raw_weighted_score"] = round(weighted_total, 4)
        scored_recommendations.append(enriched)

    # En yüksek ağırlıklı uyum skoruna göre sırala ve Top 10 (limit) yapımı seç
    scored_recommendations.sort(
        key=lambda x: (
            x["_raw_weighted_score"],
            x["match_score"],
            float(x.get("vote_average") or 0),
        ),
        reverse=True,
    )

    top_recommendations = scored_recommendations[:limit]
    for item in top_recommendations:
        item.pop("_raw_weighted_score", None)

    return {
        "recommendations": top_recommendations,
        "profile": profile,
        "watchlist_empty": False,
        "is_cold_start": False,
        "total_count": len(top_recommendations),
    }


def evaluate_single_item_match(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tek bir film veya dizi için (Detay sayfasında gösterilmek üzere)
    kullanıcının izleme profiline göre `% Uyum Skoru` ve "Neden önerildi?" analizini hesaplar.
    """
    watchlist_items = WatchlistRepository.get_all()
    if not watchlist_items:
        q_norm = _compute_catalog_quality_norm(item)
        cold_score = int(round(max(80.0, min(96.0, 72.0 + (q_norm * 24.0)))))
        return {
            "match_score": cold_score,
            "matched_genres": (item.get("genres") or [])[:3],
            "matched_keywords": [],
            "seed_sources": [],
            "why_recommended": "Henüz yapım puanlamadınız; bu skor yapımın genel IMDb/TMDB kalite ve popülerlik puanına göre hesaplandı.",
        }

    profile = build_user_interest_profile(watchlist_items)
    genre_weights: Dict[str, float] = profile["genre_weights"]
    keyword_weights: Dict[str, float] = profile["keyword_weights"]
    format_affinity: Dict[str, float] = profile["format_affinity"]

    positive_genre_scores = sorted([w for w in genre_weights.values() if w > 0], reverse=True)
    positive_kw_scores = sorted([w for w in keyword_weights.values() if w > 0], reverse=True)

    max_possible_genre = max(3.0, sum(positive_genre_scores[:2]) if positive_genre_scores else 6.0)
    max_possible_kw = max(3.0, sum(positive_kw_scores[:3]) if positive_kw_scores else 6.0)

    c_type = str(item.get("media_type", "movie")).lower()
    c_genres = item.get("genres") or []
    c_keywords = [str(k).lower() for k in (item.get("keywords") or [])]

    genre_raw = 0.0
    matched_genres: List[str] = []
    for g in c_genres:
        w = genre_weights.get(g, 0.0)
        genre_raw += w
        if w > 0:
            matched_genres.append(g)

    kw_raw = 0.0
    matched_keywords: List[str] = []
    for kw in c_keywords:
        w = keyword_weights.get(kw, 0.0)
        if w > 0:
            kw_raw += w
            matched_keywords.append(kw)

    seed_sources: List[Dict[str, Any]] = []
    for w_item in sorted(watchlist_items, key=lambda x: int(x.get("user_rating", 0)), reverse=True):
        if int(w_item.get("user_rating", 0)) < 7:
            continue
        if int(w_item.get("tmdb_id", 0)) == int(item.get("tmdb_id", -1)):
            continue
        w_genres = set(extract_genre_names(w_item.get("genres")))
        w_kws = {str(k).lower() for k in (w_item.get("keywords") or [])}
        if (w_genres & set(c_genres)) or (w_kws & set(c_keywords)):
            seed_sources.append({
                "title": w_item.get("title", ""),
                "rating": int(w_item.get("user_rating", 8)),
            })
        if len(seed_sources) >= 2:
            break

    genre_norm = max(-0.45, min(1.0, genre_raw / max_possible_genre))
    format_norm = max(0.15, min(1.0, float(format_affinity.get(c_type, 0.5)) * 1.45))
    kw_norm = max(0.0, min(1.0, kw_raw / max_possible_kw))
    seed_norm = min(1.0, len(seed_sources) * 0.55)

    personal_norm = max(0.0, min(1.0, (genre_norm * 0.70) + (format_norm * 0.20) + (max(kw_norm, seed_norm) * 0.10)))
    quality_norm = _compute_catalog_quality_norm(item)

    weighted_total = (personal_norm * 65.0) + (quality_norm * 35.0)
    match_score = int(round(max(40.0, min(99.0, 36.0 + (weighted_total * 0.63)))))

    reasons: List[str] = []
    if seed_sources:
        source_labels = [f"{s['title']} ({s['rating']}/10)" for s in seed_sources]
        reasons.append(f"{' ve '.join(source_labels)} yapımlarına yüksek puan verdin")
    if matched_genres:
        reasons.append(f"Sevdiğin türler: {', '.join(matched_genres[:3])}")
    if matched_keywords:
        reasons.append(f"Ortak temalar: {', '.join(matched_keywords[:4])}")

    why_recommended = (
        " • ".join(reasons)
        if reasons
        else "İzleme listendeki tercihlerin ve yapımın kalite skoruyla değerlendirildi."
    )

    return {
        "match_score": match_score,
        "matched_genres": matched_genres[:4],
        "matched_keywords": matched_keywords[:5],
        "seed_sources": seed_sources,
        "why_recommended": why_recommended,
    }
