"""
Öneri Algoritması (`recommendations/services.py`):
1. `watchlist.json` içindeki yapımların `user_rating` (1-10) puanlarına göre tür (genre)
   ve anahtar kelime (keyword) ağırlıklarını hesaplayarak Kullanıcı İlgi Profili çıkarır
   (yüksek puanlar pozitif, 5 altı puanlar düşük/negatif ağırlık alır).
2. Kullanıcının en yüksek puan verdiği yapımların TMDB `/recommendations` endpoint'lerinden
   (ve yerel TMDB aday grafiğinden) bir aday havuzu toplar.
3. `watchlist.json` içinde zaten kayıtlı olan yapımları aday havuzundan eler.
4. Kalan her aday yapımın tür ve anahtar kelimelerini kullanıcının profil ağırlıklarıyla
   karşılaştırarak `% Eşleşme Skoru (Match Score)` ve "Neden önerildi?" açıklaması üretir.
"""

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from app.features.catalog.repository import CatalogRepository, extract_genre_names
from app.features.watchlist.repository import WatchlistRepository


def _rating_to_weight(user_rating: int) -> float:
    """
    1-10 arası kullanıcı puanını profil ağırlığına dönüştürür:
    - 6..10 arası yüksek puanlar pozitif ağırlık (+1.5 ile +7.5 arası)
    - 5 puan nötr/hafif pozitif (+0.4)
    - 1..4 arası (5 altı) puanlar negatif ağırlık (-1.8 ile -5.4 arası)
    """
    r = max(1, min(10, int(user_rating)))
    if r >= 6:
        return (r - 5) * 1.5
    if r == 5:
        return 0.4
    return (r - 5.5) * 1.2


def build_user_interest_profile(watchlist_items: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Adım 1: Kullanıcının `watchlist.json` verisinden Tür ve Anahtar Kelime
    ağırlık profillerini oluşturur.
    """
    if watchlist_items is None:
        watchlist_items = WatchlistRepository.get_all()

    genre_weights: Dict[str, float] = defaultdict(float)
    keyword_weights: Dict[str, float] = defaultdict(float)

    for item in watchlist_items:
        rating = int(item.get("user_rating", 5))
        weight = _rating_to_weight(rating)

        for genre in extract_genre_names(item.get("genres")):
            g_clean = str(genre).strip()
            if g_clean:
                genre_weights[g_clean] = round(genre_weights[g_clean] + weight, 2)

        for kw in item.get("keywords") or []:
            kw_clean = str(kw).strip().lower()
            if kw_clean:
                keyword_weights[kw_clean] = round(keyword_weights[kw_clean] + (weight * 1.15), 2)

    sorted_genres = sorted(genre_weights.items(), key=lambda x: x[1], reverse=True)
    sorted_keywords = sorted(keyword_weights.items(), key=lambda x: x[1], reverse=True)

    favorite_genres = [{"name": k, "weight": v} for k, v in sorted_genres if v > 0][:6]
    disliked_genres = [{"name": k, "weight": v} for k, v in sorted_genres if v < 0]
    favorite_keywords = [{"name": k, "weight": v} for k, v in sorted_keywords if v > 0][:10]

    return {
        "genre_weights": dict(genre_weights),
        "keyword_weights": dict(keyword_weights),
        "favorite_genres": favorite_genres,
        "disliked_genres": disliked_genres,
        "favorite_keywords": favorite_keywords,
    }


def _select_top_seeds(watchlist_items: List[Dict[str, Any]], max_seeds: int = 10) -> List[Dict[str, Any]]:
    """
    400-500+ yapımlık büyük izleme listelerinde her yapım için TMDB API'sine
    istek atmak yerine, yalnızca en yüksek puanlı ve en son eklenen ilk 8-10 yapımı
    tohum (seed) olarak seçer.
    """
    eligible = [item for item in watchlist_items if int(item.get("user_rating", 0)) >= 6]
    if not eligible:
        return []

    # En son eklenen yüksek puanlılardan ilk 4 + en yüksek puanlılardan ilk 6 = maksimum 10 benzersiz tohum
    recent_high = [item for item in eligible if int(item.get("user_rating", 0)) >= 7][:4]
    highest_rated = sorted(
        eligible,
        key=lambda x: (int(x.get("user_rating", 0)), str(x.get("added_at", ""))),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    seen_keys: Set[Tuple[int, str]] = set()

    for candidate in (recent_high + highest_rated):
        key = (int(candidate.get("tmdb_id", 0)), str(candidate.get("media_type", "movie")))
        if key not in seen_keys:
            seen_keys.add(key)
            selected.append(candidate)
        if len(selected) >= max_seeds:
            break

    return selected


def _collect_candidate_pool(
    watchlist_items: List[Dict[str, Any]],
    watched_keys: Set[Tuple[int, str]],
) -> List[Dict[str, Any]]:
    """
    Adım 2 & 3: TMDB API'ye canlı istek atmak yerine doğrudan `data/catalog.json`
    (`CatalogRepository`) içindeki 434+ yapımlık ana katalogdan milisaniyeler içinde
    aday havuzunu oluşturur ve izleme listesinde zaten olanları O(1) sürede eler.
    """
    top_rated_seeds = _select_top_seeds(watchlist_items, max_seeds=10)
    catalog_items = CatalogRepository.get_all()
    catalog_by_id = {int(c["tmdb_id"]): c for c in catalog_items}

    candidates_by_key: Dict[Tuple[int, str], Dict[str, Any]] = {}

    # 1. Öncelikli 8-10 tohum yapımın doğrudan öneri komşularını ve tür/tema ortaklarını eşleştir
    for seed in top_rated_seeds:
        seed_id = int(seed["tmdb_id"])
        seed_title = seed.get("title", "")
        seed_rating = int(seed.get("user_rating", 8))
        seed_genres = set(extract_genre_names(seed.get("genres")))

        cat_seed = catalog_by_id.get(seed_id)
        rec_ids = (cat_seed.get("recommended_ids") or []) if cat_seed else []

        for rec_id in rec_ids:
            target = catalog_by_id.get(int(rec_id))
            if not target:
                continue
            key = (int(target["tmdb_id"]), target["media_type"])
            if key in watched_keys:
                continue

            if key not in candidates_by_key:
                candidates_by_key[key] = dict(target)
                candidates_by_key[key]["seed_sources"] = []

            existing_titles = {s["title"] for s in candidates_by_key[key]["seed_sources"]}
            if seed_title not in existing_titles:
                candidates_by_key[key]["seed_sources"].append({
                    "title": seed_title,
                    "rating": seed_rating,
                })

    # 2. `data/catalog.json` içindeki tüm izlenmemiş yapımları aday havuzuna dahil et
    for item in catalog_items:
        key = (int(item["tmdb_id"]), item["media_type"])
        if key in watched_keys:
            continue

        if key not in candidates_by_key:
            candidate = dict(item)
            candidate["seed_sources"] = []
            candidates_by_key[key] = candidate

        # Tohum yapımlarla en az 2 ortak türü olan adaylara referans bağlamı ekle
        if not candidates_by_key[key]["seed_sources"]:
            c_genres = set(item.get("genres") or [])
            for seed in top_rated_seeds[:4]:
                s_genres = set(extract_genre_names(seed.get("genres")))
                if len(c_genres & s_genres) >= 2:
                    candidates_by_key[key]["seed_sources"].append({
                        "title": seed.get("title", ""),
                        "rating": int(seed.get("user_rating", 8)),
                    })
                    break

    return list(candidates_by_key.values())


def get_personalized_recommendations(
    limit: int = 100,
    watchlist_items: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Adım 4: Aday havuzundaki her yapımın tür ve anahtar kelimelerini
    kullanıcının ilgi profili ağırlıklarıyla karşılaştırarak
    `% Eşleşme Skoru (Match Score)` ve "Neden önerildi?" açıklaması hesaplar.
    Misafir modunda `watchlist_items` bellek içinden (stateless) gönderilebilir;
    bu durumda sunucudaki hiçbir `.json` dosyasına okuma/yazma yapılmaz.
    """
    if watchlist_items is None:
        watchlist_items = WatchlistRepository.get_all()
    if not watchlist_items:
        return {
            "recommendations": [],
            "profile": build_user_interest_profile([]),
            "watchlist_empty": True,
        }

    profile = build_user_interest_profile(watchlist_items)
    genre_weights: Dict[str, float] = profile["genre_weights"]
    keyword_weights: Dict[str, float] = profile["keyword_weights"]

    watched_keys: Set[Tuple[int, str]] = {
        (int(item["tmdb_id"]), item.get("media_type", "movie"))
        for item in watchlist_items
    }

    candidates = _collect_candidate_pool(watchlist_items, watched_keys)

    # Normalizasyon için maksimum pozitif profil potansiyelini hesapla
    positive_genre_scores = sorted([w for w in genre_weights.values() if w > 0], reverse=True)
    positive_kw_scores = sorted([w for w in keyword_weights.values() if w > 0], reverse=True)

    max_possible_genre = sum(positive_genre_scores[:3]) or 10.0
    max_possible_kw = sum(positive_kw_scores[:4]) or 12.0

    scored_recommendations: List[Dict[str, Any]] = []

    for candidate in candidates:
        c_genres = candidate.get("genres") or []
        c_keywords = [str(k).lower() for k in (candidate.get("keywords") or [])]
        seed_sources = candidate.get("seed_sources") or []

        # Tür ağırlık skoru
        genre_raw_score = 0.0
        matched_genres: List[str] = []
        penalized_genres: List[str] = []

        for g in c_genres:
            w = genre_weights.get(g, 0.0)
            genre_raw_score += w
            if w > 0:
                matched_genres.append(g)
            elif w < 0:
                penalized_genres.append(g)

        # Anahtar kelime ağırlık skoru
        kw_raw_score = 0.0
        matched_keywords: List[str] = []

        for kw in c_keywords:
            w = keyword_weights.get(kw, 0.0)
            kw_raw_score += w
            if w > 0:
                matched_keywords.append(kw)

        # Doğrudan yüksek puanlı yapım komşuluğu (TMDB /recommendations) bonusu
        seed_bonus = 0.0
        if seed_sources:
            best_seed_rating = max(s["rating"] for s in seed_sources)
            seed_bonus = ((best_seed_rating - 5) * 3.2) + (len(seed_sources) * 2.5)

        # Negatif ağırlıklı (kullanıcının düşük puan verdiği) yapımlubir aday ise ele veya düşür
        if genre_raw_score < 0 and kw_raw_score <= 0 and not seed_sources:
            continue

        genre_ratio = max(-0.4, min(1.0, genre_raw_score / max_possible_genre))
        kw_ratio = max(-0.3, min(1.0, kw_raw_score / max_possible_kw))
        vote_bonus = (float(candidate.get("vote_average", 7.5)) - 6.5) * 3.0

        # % Eşleşme Skoru (Match Score: 45% - 99% aralığında anlamlı dağılım)
        raw_percentage = (
            38.0
            + (genre_ratio * 28.0)
            + (kw_ratio * 22.0)
            + min(12.0, seed_bonus)
            + max(0.0, min(6.0, vote_bonus))
        )

        match_score = int(round(max(42.0, min(99.0, raw_percentage))))

        if not matched_genres and not matched_keywords and not seed_sources:
            continue

        # "Neden önerildi?" açıklamasını oluştur
        reasons: List[str] = []
        if seed_sources:
            source_labels = [f"{s['title']} ({s['rating']}/10)" for s in seed_sources[:2]]
            reasons.append(f"{' ve '.join(source_labels)} yapımlarına yüksek puan verdin")

        if matched_genres:
            reasons.append(f"Sevdiğin türler: {', '.join(matched_genres[:3])}")

        if matched_keywords:
            reasons.append(f"Ortak temalar: {', '.join(matched_keywords[:4])}")

        why_recommended = " • ".join(reasons) if reasons else "İzleme listendeki genel puan profilinle uyumlu."

        enriched_candidate = dict(candidate)
        enriched_candidate["match_score"] = match_score
        enriched_candidate["matched_genres"] = matched_genres[:3]
        enriched_candidate["matched_keywords"] = matched_keywords[:4]
        enriched_candidate["why_recommended"] = why_recommended
        scored_recommendations.append(enriched_candidate)

    # % Eşleşme Skoruna göre büyükten küçüğe sırala
    scored_recommendations.sort(
        key=lambda x: (x["match_score"], float(x.get("vote_average", 0))),
        reverse=True,
    )

    return {
        "recommendations": scored_recommendations[:limit],
        "profile": profile,
        "watchlist_empty": False,
    }


def evaluate_single_item_match(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tek bir film veya dizi için (Detay sayfasında gösterilmek üzere)
    kullanıcının `watchlist.json` profiline göre `% Eşleşme Skoru` ve
    "Neden önerildi?" analizini hesaplar.
    """
    watchlist_items = WatchlistRepository.get_all()
    if not watchlist_items:
        return {
            "match_score": 0,
            "matched_genres": [],
            "matched_keywords": [],
            "seed_sources": [],
            "why_recommended": "İzleme listenize yapım ekleyip puan verdiğinizde bu yapım için kişisel eşleşme skorunuz hesaplanır.",
        }

    profile = build_user_interest_profile(watchlist_items)
    genre_weights: Dict[str, float] = profile["genre_weights"]
    keyword_weights: Dict[str, float] = profile["keyword_weights"]

    positive_genre_scores = sorted([w for w in genre_weights.values() if w > 0], reverse=True)
    positive_kw_scores = sorted([w for w in keyword_weights.values() if w > 0], reverse=True)

    max_possible_genre = sum(positive_genre_scores[:3]) or 10.0
    max_possible_kw = sum(positive_kw_scores[:4]) or 12.0

    c_genres = item.get("genres") or []
    c_keywords = [str(k).lower() for k in (item.get("keywords") or [])]

    genre_raw_score = 0.0
    matched_genres: List[str] = []
    for g in c_genres:
        w = genre_weights.get(g, 0.0)
        genre_raw_score += w
        if w > 0:
            matched_genres.append(g)

    kw_raw_score = 0.0
    matched_keywords: List[str] = []
    for kw in c_keywords:
        w = keyword_weights.get(kw, 0.0)
        kw_raw_score += w
        if w > 0:
            matched_keywords.append(kw)

    # Kullanıcının yüksek puan verdiği hangi yapımlarla ortak tür/tema taşıdığını bul
    seed_sources: List[Dict[str, Any]] = []
    for w_item in sorted(watchlist_items, key=lambda x: int(x.get("user_rating", 0)), reverse=True):
        if int(w_item.get("user_rating", 0)) < 7:
            continue
        if int(w_item.get("tmdb_id", 0)) == int(item.get("tmdb_id", -1)):
            continue
        w_genres = set(w_item.get("genres") or [])
        w_kws = {str(k).lower() for k in (w_item.get("keywords") or [])}
        if (w_genres & set(c_genres)) or (w_kws & set(c_keywords)):
            seed_sources.append({
                "title": w_item.get("title", ""),
                "rating": int(w_item.get("user_rating", 8)),
            })
        if len(seed_sources) >= 2:
            break

    genre_ratio = max(-0.4, min(1.0, genre_raw_score / max_possible_genre))
    kw_ratio = max(-0.3, min(1.0, kw_raw_score / max_possible_kw))
    vote_bonus = (float(item.get("vote_average", 7.5)) - 6.5) * 3.0
    seed_bonus = 8.0 if seed_sources else 0.0

    raw_percentage = (
        40.0
        + (genre_ratio * 28.0)
        + (kw_ratio * 22.0)
        + seed_bonus
        + max(0.0, min(6.0, vote_bonus))
    )
    match_score = int(round(max(35.0, min(99.0, raw_percentage))))

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
        else "İzleme listendeki tercihlerinle orta/düşük düzeyde kesişiyor."
    )

    return {
        "match_score": match_score,
        "matched_genres": matched_genres[:4],
        "matched_keywords": matched_keywords[:5],
        "seed_sources": seed_sources,
        "why_recommended": why_recommended,
    }
