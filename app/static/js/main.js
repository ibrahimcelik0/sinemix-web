// SineMix - Klasik Posterli Kart (Grid) + Seçilebilir Çubuk (Bar) Görünümü,
// Sayfa Başına 20 Yapım Numaralı Sayfalama ve Film/Dizi Talep Sistemi
document.addEventListener("DOMContentLoaded", () => {
    const mainNavbar = document.getElementById("mainNavbar");
    const isAuthenticated = mainNavbar?.dataset.authenticated === "true";

    const toastEl = document.getElementById("toastNotification");
    const navWatchlistBadge = document.getElementById("navWatchlistBadge");
    const searchClearBtn = document.getElementById("searchClearBtn");
    const clearWatchlistBtn = document.getElementById("clearWatchlistBtn");

    // Misafir Modu: Yalnızca o anki sayfa yaşam döngüsünde (JS belleğinde) tutulur
    let guestWatchlist = [];

    let toastTimer = null;
    function showToast(message) {
        if (!toastEl) return;
        toastEl.textContent = message;
        toastEl.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            toastEl.hidden = true;
        }, 3200);
    }

    function updateCounters(newCount) {
        if (navWatchlistBadge && typeof newCount === "number") {
            navWatchlistBadge.textContent = String(newCount);
        }
        if (clearWatchlistBtn && typeof newCount === "number") {
            clearWatchlistBtn.hidden = newCount === 0;
        }
    }

    function escapeHtml(str) {
        const d = document.createElement("div");
        d.textContent = str || "";
        return d.innerHTML;
    }

    function getDefaultTodayDate2026() {
        const now = new Date();
        let y = now.getFullYear();
        if (y < 2020 || y > 2026) y = 2026;
        const m = String(now.getMonth() + 1).padStart(2, "0");
        const d = String(now.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
    }

    const TR_MONTHS_CLIENT = [
        "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    ];

    function formatTurkishDateRangeClient(startRaw, endRaw) {
        const fallback = getDefaultTodayDate2026();
        let s = (startRaw || fallback).trim();
        let e = (endRaw || s).trim();
        if (e < s) {
            const tmp = s;
            s = e;
            e = tmp;
        }
        const sp = s.split("-");
        const ep = e.split("-");
        if (sp.length < 3 || ep.length < 3) return s;

        const sy = parseInt(sp[0], 10);
        const sm = parseInt(sp[1], 10);
        const sd = parseInt(sp[2], 10);
        const ey = parseInt(ep[0], 10);
        const em = parseInt(ep[1], 10);
        const ed = parseInt(ep[2], 10);

        const sMonth = TR_MONTHS_CLIENT[sm] || "";
        const eMonth = TR_MONTHS_CLIENT[em] || "";

        if (s === e) return `${sd} ${sMonth} ${sy}`;
        if (sy === ey && sm === em) return `${sd}–${ed} ${sMonth} ${sy}`;
        if (sy === ey) return `${sd} ${sMonth} – ${ed} ${eMonth} ${sy}`;
        return `${sd} ${sMonth} ${sy} – ${ed} ${eMonth} ${ey}`;
    }

    // =========================================================================
    // 1. Transparan (Glassmorphism) "✨ Neden Önerildi?" Modal Yönetimi
    // =========================================================================
    const whyModal = document.getElementById("whyRecommendedModal");
    const closeWhyModalBtn = document.getElementById("closeWhyModalBtn");
    const whyModalPoster = document.getElementById("whyModalPoster");
    const whyModalTypeBadge = document.getElementById("whyModalTypeBadge");
    const whyModalScoreBadge = document.getElementById("whyModalScoreBadge");
    const whyModalTitle = document.getElementById("whyModalTitle");
    const whyModalSummary = document.getElementById("whyModalSummary");
    const whyModalSourcesSection = document.getElementById("whyModalSourcesSection");
    const whyModalSourcesList = document.getElementById("whyModalSourcesList");
    const whyModalGenresSection = document.getElementById("whyModalGenresSection");
    const whyModalGenresList = document.getElementById("whyModalGenresList");
    const whyModalKeywordsSection = document.getElementById("whyModalKeywordsSection");
    const whyModalKeywordsList = document.getElementById("whyModalKeywordsList");

    function openWhyRecommendedModal(card) {
        if (!whyModal || !card) return;

        const title = card.dataset.title || "";
        const mediaType = card.dataset.mediaType || "movie";
        const poster = card.dataset.poster || "";
        const matchScore = card.dataset.matchScore || "90";
        const whySummary = card.dataset.why || "";

        let matchedGenres = [];
        let matchedKeywords = [];
        let seedSources = [];

        try {
            matchedGenres = JSON.parse(card.dataset.matchedGenres || "[]");
        } catch (_) {}
        try {
            matchedKeywords = JSON.parse(card.dataset.matchedKeywords || "[]");
        } catch (_) {}
        try {
            seedSources = JSON.parse(card.dataset.seedSources || "[]");
        } catch (_) {}

        if (whyModalPoster) {
            whyModalPoster.src = poster;
            whyModalPoster.alt = title;
        }
        if (whyModalTypeBadge) {
            whyModalTypeBadge.textContent = mediaType === "tv" ? "DİZİ" : "FİLM";
            whyModalTypeBadge.className = `media-badge-type ${mediaType}`;
        }
        if (whyModalScoreBadge) {
            whyModalScoreBadge.textContent = `%${matchScore} Eşleşme Skoru`;
        }
        if (whyModalTitle) {
            whyModalTitle.textContent = title;
        }
        if (whyModalSummary) {
            whyModalSummary.textContent = whySummary;
        }

        if (whyModalSourcesList && whyModalSourcesSection) {
            whyModalSourcesList.innerHTML = "";
            whyModalSourcesSection.hidden = false;
            if (seedSources.length > 0) {
                seedSources.forEach((src) => {
                    const pill = document.createElement("span");
                    pill.className = "modal-reason-pill source-pill";
                    pill.textContent = `⭐ ${src.title} (${src.rating}/10 puan verdin)`;
                    whyModalSourcesList.appendChild(pill);
                });
            } else {
                const pill = document.createElement("span");
                pill.className = "modal-reason-pill source-pill";
                pill.textContent = "⭐ İzleme listendeki yüksek puan profilin";
                whyModalSourcesList.appendChild(pill);
            }
        }

        if (whyModalGenresList && whyModalGenresSection) {
            whyModalGenresList.innerHTML = "";
            if (matchedGenres.length > 0) {
                whyModalGenresSection.hidden = false;
                matchedGenres.forEach((g) => {
                    const pill = document.createElement("span");
                    pill.className = "modal-reason-pill genre-pill";
                    pill.textContent = `✓ ${g}`;
                    whyModalGenresList.appendChild(pill);
                });
            } else {
                whyModalGenresSection.hidden = true;
            }
        }

        if (whyModalKeywordsList && whyModalKeywordsSection) {
            whyModalKeywordsList.innerHTML = "";
            if (matchedKeywords.length > 0) {
                whyModalKeywordsSection.hidden = false;
                matchedKeywords.forEach((kw) => {
                    const pill = document.createElement("span");
                    pill.className = "modal-reason-pill kw-pill-tag";
                    pill.textContent = `#${kw}`;
                    whyModalKeywordsList.appendChild(pill);
                });
            } else {
                whyModalKeywordsSection.hidden = true;
            }
        }

        whyModal.hidden = false;
    }

    function closeWhyRecommendedModal() {
        if (whyModal) whyModal.hidden = true;
    }

    if (closeWhyModalBtn) closeWhyModalBtn.addEventListener("click", closeWhyRecommendedModal);
    if (whyModal) {
        whyModal.addEventListener("click", (event) => {
            if (event.target === whyModal) closeWhyRecommendedModal();
        });
    }

    // =========================================================================
    // 2. Görünüm Seçici: Klasik Posterli Kart (Grid) vs. Seçilebilir Çubuk (Bar)
    // =========================================================================
    const viewModeSwitcher = document.getElementById("viewModeSwitcher");
    const activeGrid =
        document.getElementById("discoverGrid") ||
        document.getElementById("watchlistGrid") ||
        document.getElementById("recommendationsGrid");
    const liveRecsGrid = document.getElementById("liveRecommendationsGrid");

    let currentViewMode = "grid"; // Varsayılan: Klasik Posterli Kart (Grid)

    function applyViewMode(mode) {
        currentViewMode = mode === "bar" ? "bar" : "grid";
        [activeGrid, liveRecsGrid].forEach((grid) => {
            if (!grid) return;
            grid.classList.toggle("view-grid", currentViewMode === "grid");
            grid.classList.toggle("view-bar", currentViewMode === "bar");
        });

        if (viewModeSwitcher) {
            viewModeSwitcher.querySelectorAll(".view-mode-btn").forEach((btn) => {
                btn.classList.toggle("active", btn.dataset.viewMode === currentViewMode);
            });
        }
    }

    if (viewModeSwitcher) {
        viewModeSwitcher.querySelectorAll(".view-mode-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                applyViewMode(btn.dataset.viewMode || "grid");
            });
        });
    }

    // =========================================================================
    // 3. Misafir Modu Bellek İçi Öneri Hesaplama ve Kart Çizimi
    // =========================================================================
    function syncGuestWatchlistSessionStorage() {
        try {
            sessionStorage.setItem("sinemix_guest_watchlist", JSON.stringify(guestWatchlist));
        } catch (_) {}
    }

    function upsertGuestWatchlistItem(itemObj) {
        const idx = guestWatchlist.findIndex(
            (x) => Number(x.tmdb_id) === Number(itemObj.tmdb_id) && x.media_type === itemObj.media_type
        );
        if (idx >= 0) {
            guestWatchlist[idx] = { ...guestWatchlist[idx], ...itemObj };
        } else {
            guestWatchlist.unshift(itemObj);
        }
        syncGuestWatchlistSessionStorage();
        updateCounters(guestWatchlist.length);
    }

    function syncDiscoverCardsWithGuestWatchlist() {
        if (isAuthenticated) return;
        const lookup = new Map(
            guestWatchlist.map((i) => [`${i.media_type}_${i.tmdb_id}`, Number(i.user_rating)])
        );

        document.querySelectorAll(".media-card").forEach((card) => {
            const key = `${card.dataset.mediaType || "movie"}_${card.dataset.tmdbId}`;
            const rating = lookup.get(key);
            const ribbon = card.querySelector(".watched-ribbon");
            const ratingValEl = card.querySelector(".user-rating-val");
            const rateLabel = card.querySelector(".rate-label");
            const confirmBtn = card.querySelector(".card-watch-confirm-btn");

            if (rating) {
                card.classList.add("is-in-watchlist");
                card.dataset.confirmedRating = String(rating);
                if (ribbon) ribbon.hidden = false;
                if (ratingValEl) ratingValEl.textContent = String(rating);
                if (rateLabel) {
                    rateLabel.innerHTML = `✓ İzlendi (Puanın: <strong class="gold-text">${rating}/10</strong>)`;
                }
                if (confirmBtn) {
                    confirmBtn.textContent = `✓ İzlendi (${rating}/10)`;
                    confirmBtn.classList.add("is-watched-confirmed");
                    confirmBtn.classList.remove("is-pending-confirm");
                }
                card.querySelectorAll(".rate-num-btn").forEach((b) => {
                    b.classList.toggle("selected", Number(b.dataset.rating) === rating);
                });
            } else {
                card.classList.remove("is-in-watchlist");
                delete card.dataset.confirmedRating;
                delete card.dataset.pendingRating;
                if (ribbon) ribbon.hidden = true;
                if (rateLabel) rateLabel.textContent = "Puan Seç (1-10):";
                if (confirmBtn) {
                    confirmBtn.textContent = "🎬 İzledim";
                    confirmBtn.classList.remove("is-watched-confirmed", "is-pending-confirm");
                }
                card.querySelectorAll(".rate-num-btn").forEach((b) => b.classList.remove("selected"));
            }
        });
    }

    function buildRecommendationCardElement(item) {
        const article = document.createElement("article");
        article.className = "media-card recommendation-card";
        article.dataset.tmdbId = String(item.tmdb_id);
        article.dataset.mediaType = item.media_type;
        article.dataset.title = item.title;
        article.dataset.year = String(item.release_year || "");
        article.dataset.poster = item.poster_path;
        article.dataset.matchScore = String(item.match_score);
        article.dataset.why = item.why_recommended || "";
        article.dataset.genres = JSON.stringify(item.genres || []);
        article.dataset.matchedGenres = JSON.stringify(item.matched_genres || []);
        article.dataset.keywords = JSON.stringify(item.keywords || []);
        article.dataset.matchedKeywords = JSON.stringify(item.matched_keywords || []);
        article.dataset.seedSources = JSON.stringify(item.seed_sources || []);

        const matchedSet = new Set(item.matched_genres || []);
        const genreTagsHtml = (item.genres || [])
            .slice(0, 2)
            .map((g) => `<span class="genre-tag ${matchedSet.has(g) ? "matched" : ""}">${escapeHtml(g)}</span>`)
            .join("");

        let ratingBtnsHtml = "";
        for (let r = 1; r <= 10; r++) {
            ratingBtnsHtml += `<button type="button" class="rate-num-btn" data-rating="${r}" title="${r}/10 Puan Seç">${r}</button>`;
        }

        const badgeTone = item.match_score >= 85 ? "high-match" : item.match_score >= 70 ? "mid-match" : "";
        const badgeText = item.match_badge_text || `%${item.match_score} Uyum`;

        article.innerHTML = `
            <div class="media-poster-wrap">
                <span class="media-badge-type ${escapeHtml(item.media_type)}">
                    ${item.media_type === "tv" ? "DİZİ" : "FİLM"}
                </span>
                <div class="match-score-badge ${badgeTone}">
                    ${escapeHtml(badgeText)}
                </div>
                <div class="watched-ribbon" hidden>
                    ✓ İzlendi (<strong class="user-rating-val"></strong>/10)
                </div>
                <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}" class="poster-link">
                    <img src="${escapeHtml(item.poster_path || '/static/img/no-poster.svg')}" alt="${escapeHtml(item.title)}" loading="lazy" onerror="this.onerror=null;this.src='/static/img/no-poster.svg';">
                </a>
            </div>
            <div class="media-card-body">
                <div class="media-meta-row">
                    <span class="tmdb-score">⭐ ${escapeHtml(String(item.vote_average))}</span>
                    <span class="card-year-inline">${escapeHtml(String(item.release_year || ""))}</span>
                    <div class="genre-tags">${genreTagsHtml}</div>
                </div>
                <h3 class="media-title">
                    <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}">${escapeHtml(item.title)}</a>
                </h3>
                <p class="media-overview">${escapeHtml(item.overview || "")}</p>
                <button type="button" class="why-modal-trigger-btn" aria-haspopup="dialog">
                    <span class="sparkle-icon">✨</span>
                    <span>Neden Önerildi?</span>
                    <span class="why-score-pill">%${item.match_score} Uyum</span>
                </button>
                <div class="quick-rate-box">
                    <div class="quick-rate-header">
                        <span class="rate-label">Puan Seç (1-10):</span>
                        <button type="button" class="card-watch-confirm-btn">🎬 İzledim</button>
                    </div>
                    <div class="rating-number-bar">${ratingBtnsHtml}</div>
                </div>
            </div>
        `;
        return article;
    }

    function applyRecommendationsPagePayload(data) {
        const recs = data.recommendations || [];
        const profile = data.profile || {};
        const watchlistEmpty = Boolean(data.watchlist_empty);

        const recsGrid = document.getElementById("recommendationsGrid");
        const recsEmptyBox = document.getElementById("recsEmptyStateBox");
        const recsProfileCard = document.getElementById("recsProfileSummaryCard");
        const favGenresEl = document.getElementById("recsFavoriteGenresChips");
        const formatChipEl = document.getElementById("recsFormatAffinityChip");
        const statusPill = document.getElementById("recsEngineStatusPill");

        if (!recsGrid) return;

        recsGrid.innerHTML = "";
        recs.forEach((item) => {
            recsGrid.appendChild(buildRecommendationCardElement(item));
        });
        bindMediaCardEvents(recsGrid);

        if (recsEmptyBox) recsEmptyBox.hidden = recs.length > 0;
        if (recsProfileCard) recsProfileCard.hidden = watchlistEmpty || recs.length === 0;

        if (favGenresEl) {
            const posHtml = (profile.favorite_genres || [])
                .map((g) => `<span class="taste-chip positive">${escapeHtml(g.name)} <small>+${g.weight}</small></span>`)
                .join("");
            const negHtml = (profile.disliked_genres || [])
                .map((g) => `<span class="taste-chip negative">${escapeHtml(g.name)} <small>${g.weight}</small></span>`)
                .join("");
            favGenresEl.innerHTML = posHtml + negHtml;
        }

        if (formatChipEl && profile.preferred_format_label) {
            formatChipEl.innerHTML = `<span class="taste-chip keyword">${escapeHtml(profile.preferred_format_label)}</span>`;
        }

        if (statusPill && !watchlistEmpty && profile.preferred_format_label) {
            statusPill.innerHTML = `<span class="status-dot live"></span> Dinamik Ağırlıklı Algoritma • <strong>${escapeHtml(profile.preferred_format_label)}</strong>`;
        }

        currentPage = 1;
        updateSegmentedCounts();
        applySegmentedTabFilter();
    }

    async function refreshAuthenticatedRecommendations() {
        if (!document.getElementById("recommendationsGrid")) return;
        try {
            const res = await fetch("/api/recommendations");
            if (!res.ok) return;
            const data = await res.json();
            applyRecommendationsPagePayload(data);
        } catch (err) {
            console.error("Öneri listesi yenileme hatası:", err);
        }
    }

    async function refreshGuestRecommendationsPreview(scrollToSection = false) {
        try {
            const res = await fetch("/api/recommendations/preview", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ watchlist: guestWatchlist }),
            });
            if (!res.ok) return;
            const data = await res.json();
            const recs = data.recommendations || [];
            const profile = data.profile || {};

            const liveSection = document.getElementById("liveGuestRecommendationsSection");
            const liveChips = document.getElementById("liveProfileChips");

            if (liveSection && liveRecsGrid) {
                if (guestWatchlist.length === 0 || recs.length === 0) {
                    liveSection.hidden = true;
                    liveRecsGrid.innerHTML = "";
                } else {
                    liveSection.hidden = false;
                    liveRecsGrid.innerHTML = "";
                    recs.slice(0, 5).forEach((item) => {
                        liveRecsGrid.appendChild(buildRecommendationCardElement(item));
                    });
                    bindMediaCardEvents(liveRecsGrid);

                    if (liveChips) {
                        liveChips.innerHTML = (profile.favorite_genres || [])
                            .slice(0, 4)
                            .map((g) => `<span class="taste-chip positive">${escapeHtml(g.name)} <small>+${g.weight}</small></span>`)
                            .join("");
                    }

                    if (scrollToSection) {
                        liveSection.scrollIntoView({ behavior: "smooth", block: "start" });
                    }
                }
            }

            applyRecommendationsPagePayload(data);
        } catch (err) {
            console.error("Misafir öneri hesaplama hatası:", err);
        }
    }

    // =========================================================================
    // 4. Kart Etkileşimleri (1-10 Puan Verme, Silme, Neden Önerildi Modal)
    // =========================================================================
    function bindMediaCardEvents(rootContainer) {
        if (!rootContainer) return;

        rootContainer.querySelectorAll(".media-card").forEach((card) => {
            if (card.dataset.bound === "true") return;
            card.dataset.bound = "true";

            const tmdbId = parseInt(card.dataset.tmdbId || "0", 10);
            const mediaType = card.dataset.mediaType || "movie";
            const title = card.dataset.title || "";
            const posterPath = card.dataset.poster || "";

            let genres = [];
            let keywords = [];
            try {
                genres = JSON.parse(card.dataset.genres || "[]");
            } catch (_) {}
            try {
                keywords = JSON.parse(card.dataset.keywords || "[]");
            } catch (_) {}

            const whyBtn = card.querySelector(".why-modal-trigger-btn");
            if (whyBtn) {
                whyBtn.addEventListener("click", () => {
                    openWhyRecommendedModal(card);
                });
            }

            const confirmWatchBtn = card.querySelector(".card-watch-confirm-btn");
            const rateLabel = card.querySelector(".rate-label");
            const ratingBarEl = card.querySelector(".rating-number-bar");
            const quickRateBox = card.querySelector(".quick-rate-box");
            const initialSelectedBtn = card.querySelector(".rate-num-btn.selected");
            if (initialSelectedBtn && card.classList.contains("is-in-watchlist")) {
                card.dataset.confirmedRating = initialSelectedBtn.dataset.rating || "";
            }

            // Filmler için Başlama–Bitiş Tarih Aralığı, Diziler için Sezon Bazlı Başlama–Bitiş Tarihleri
            let watchedDateRow = card.querySelector(".card-watched-date-row");
            if (!watchedDateRow && quickRateBox) {
                watchedDateRow = document.createElement("div");
                watchedDateRow.className = "card-watched-date-row";
                watchedDateRow.hidden = !card.classList.contains("is-in-watchlist");
                const initStart = card.dataset.watchStart || card.dataset.watchedAt || getDefaultTodayDate2026();
                const initEnd = card.dataset.watchEnd || card.dataset.watchedAt || initStart;
                const initLabel = card.dataset.watchedLabel || formatTurkishDateRangeClient(initStart, initEnd);

                if (mediaType === "tv") {
                    watchedDateRow.innerHTML = `
                        <div class="card-date-summary-line">
                            <span class="watched-date-label">📺 Sezon İzleme Tarihleri:</span>
                        </div>
                        <div class="card-season-chips-wrap"></div>
                        <div class="card-date-inputs-line">
                            <select class="watched-season-select card-season-select" title="Sezon Seç">
                                <option value="1">1. Sezon</option>
                                <option value="2">2. Sezon</option>
                                <option value="3">3. Sezon</option>
                                <option value="4">4. Sezon</option>
                                <option value="5">5. Sezon</option>
                                <option value="6">6. Sezon</option>
                                <option value="7">7. Sezon</option>
                                <option value="8">8. Sezon</option>
                            </select>
                            <input type="date"
                                   class="watched-date-input card-watch-start-input"
                                   min="2020-01-01"
                                   max="2026-12-31"
                                   value="${escapeHtml(initStart)}"
                                   title="Sezona Başlama Tarihi">
                            <span class="date-range-arrow">→</span>
                            <input type="date"
                                   class="watched-date-input card-watch-end-input"
                                   min="2020-01-01"
                                   max="2026-12-31"
                                   value="${escapeHtml(initEnd)}"
                                   title="Sezonu Bitirme Tarihi">
                        </div>
                    `;
                } else {
                    watchedDateRow.innerHTML = `
                        <div class="card-date-summary-line">
                            <span class="watched-date-label">🎬 İzleme Aralığı:</span>
                            <span class="watched-range-pretty-pill card-pretty-date-pill">📅 ${escapeHtml(initLabel)}</span>
                        </div>
                        <div class="card-date-inputs-line">
                            <input type="date"
                                   class="watched-date-input card-watch-start-input"
                                   min="2020-01-01"
                                   max="2026-12-31"
                                   value="${escapeHtml(initStart)}"
                                   title="Başlama Tarihi">
                            <span class="date-range-arrow">→</span>
                            <input type="date"
                                   class="watched-date-input card-watch-end-input"
                                   min="2020-01-01"
                                   max="2026-12-31"
                                   value="${escapeHtml(initEnd)}"
                                   title="Bitiş Tarihi">
                        </div>
                    `;
                }
                quickRateBox.appendChild(watchedDateRow);
            }

            const startInput = card.querySelector(".card-watch-start-input");
            const endInput = card.querySelector(".card-watch-end-input");
            const seasonSelect = card.querySelector(".card-season-select");
            const prettyPill = card.querySelector(".card-pretty-date-pill");
            const seasonChipsWrap = card.querySelector(".card-season-chips-wrap");

            function updateCardLiveDatePreview() {
                const sVal = (startInput?.value || getDefaultTodayDate2026()).trim();
                const eVal = (endInput?.value || sVal).trim();
                if (prettyPill) {
                    prettyPill.textContent = `📅 ${formatTurkishDateRangeClient(sVal, eVal)}`;
                }
            }

            async function submitCardWatchedRating(rating) {
                const chosenStart = (startInput?.value || card.dataset.watchStart || getDefaultTodayDate2026()).trim();
                const chosenEnd = (endInput?.value || card.dataset.watchEnd || chosenStart).trim();
                const chosenSeason = seasonSelect ? parseInt(seasonSelect.value || "1", 10) : 1;
                const rangeLabel = formatTurkishDateRangeClient(chosenStart, chosenEnd);

                card.classList.add("is-in-watchlist");
                card.dataset.confirmedRating = String(rating);
                card.dataset.watchStart = chosenStart;
                card.dataset.watchEnd = chosenEnd;
                card.dataset.watchedAt = chosenEnd;
                delete card.dataset.pendingRating;
                if (watchedDateRow) watchedDateRow.hidden = false;
                updateCardLiveDatePreview();

                card.querySelectorAll(".rate-num-btn").forEach((b) => {
                    b.classList.toggle("selected", parseInt(b.dataset.rating || "0", 10) === rating);
                });

                const ribbon = card.querySelector(".watched-ribbon");
                const ratingValEl = card.querySelector(".user-rating-val");
                if (ribbon) ribbon.hidden = false;
                if (ratingValEl) ratingValEl.textContent = String(rating);

                if (rateLabel) {
                    rateLabel.innerHTML = `✓ İzlendi (Puanın: <strong class="gold-text">${rating}/10</strong>)`;
                }
                if (confirmWatchBtn) {
                    confirmWatchBtn.textContent = `✓ İzlendi (${rating}/10)`;
                    confirmWatchBtn.classList.add("is-watched-confirmed");
                    confirmWatchBtn.classList.remove("is-pending-confirm");
                }

                const toastDateText = mediaType === "tv" ? `${chosenSeason}. Sezon: ${rangeLabel}` : rangeLabel;

                if (!isAuthenticated) {
                    upsertGuestWatchlistItem({
                        tmdb_id: tmdbId,
                        media_type: mediaType,
                        title: title,
                        poster_path: posterPath,
                        user_rating: rating,
                        watch_start_date: chosenStart,
                        watch_end_date: chosenEnd,
                        watched_at: chosenEnd,
                        season_number: mediaType === "tv" ? chosenSeason : undefined,
                        genres: genres,
                        keywords: keywords,
                    });
                    if (mediaType === "tv" && seasonChipsWrap) {
                        seasonChipsWrap.innerHTML = `<span class="season-date-chip">📺 ${escapeHtml(toastDateText)}</span>`;
                    }
                    showToast(`✓ "${title}" (${rating}/10 • ${toastDateText}) İzlendi olarak işaretlendi!`);
                    await refreshGuestRecommendationsPreview(false);
                    return;
                }

                try {
                    const res = await fetch("/api/watchlist", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            tmdb_id: tmdbId,
                            media_type: mediaType,
                            title: title,
                            poster_path: posterPath,
                            user_rating: rating,
                            watch_start_date: chosenStart,
                            watch_end_date: chosenEnd,
                            watched_at: chosenEnd,
                            season_number: mediaType === "tv" ? chosenSeason : undefined,
                            genres: genres,
                            keywords: keywords,
                        }),
                    });

                    if (!res.ok) return;
                    const data = await res.json();

                    if (data.item) {
                        if (prettyPill && data.item.watched_date_label) {
                            prettyPill.textContent = `📅 ${data.item.watched_date_label}`;
                        }
                        if (seasonChipsWrap && Array.isArray(data.item.season_watch_dates)) {
                            seasonChipsWrap.innerHTML = data.item.season_watch_dates
                                .map((s) => `<span class="season-date-chip">📺 ${escapeHtml(s.label)}</span>`)
                                .join("");
                        }
                    }

                    if (data.stats) {
                        updateCounters(data.stats.total);
                        const recsCountEl = document.getElementById("recsWatchlistCountText");
                        if (recsCountEl) recsCountEl.textContent = String(data.stats.total);
                    }

                    showToast(`✓ "${title}" (${rating}/10 • ${toastDateText}) İzlendi olarak kaydedildi!`);

                    if (document.getElementById("recommendationsGrid")) {
                        await refreshAuthenticatedRecommendations();
                    }
                } catch (err) {
                    console.error("Puan kaydetme hatası:", err);
                }
            }

            // 1. Adım: Kullanıcı 1-10 arası puan seçer (Tarih Aralığı / Sezon Tarihi seçicisini açar)
            card.querySelectorAll(".rate-num-btn").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const chosen = parseInt(btn.dataset.rating || "0", 10);
                    if (!chosen) return;

                    card.dataset.pendingRating = String(chosen);
                    card.querySelectorAll(".rate-num-btn").forEach((b) => {
                        b.classList.toggle("selected", b === btn);
                    });

                    if (watchedDateRow) {
                        watchedDateRow.hidden = false;
                        updateCardLiveDatePreview();
                    }

                    if (rateLabel) {
                        rateLabel.innerHTML = `Seçilen Puan: <strong class="gold-text">${chosen}/10</strong>`;
                    }
                    if (confirmWatchBtn) {
                        confirmWatchBtn.textContent = `🎬 İzledim (${chosen}/10)`;
                        confirmWatchBtn.classList.add("is-pending-confirm");
                        confirmWatchBtn.classList.remove("is-watched-confirmed");
                    }
                });
            });

            [startInput, endInput, seasonSelect].forEach((inp) => {
                if (!inp) return;
                inp.addEventListener("change", async () => {
                    updateCardLiveDatePreview();
                    const activeRating = parseInt(card.dataset.pendingRating || card.dataset.confirmedRating || "0", 10);
                    if (card.classList.contains("is-in-watchlist") && activeRating > 0 && inp !== seasonSelect) {
                        await submitCardWatchedRating(activeRating);
                    }
                });
            });

            // 2. Adım: Kullanıcı "İzledim" butonuna tıkladığında puan kaydedilir ve "✓ İzlendi (X/10)" olur
            if (confirmWatchBtn) {
                confirmWatchBtn.addEventListener("click", async () => {
                    const pending = parseInt(card.dataset.pendingRating || "0", 10);
                    const confirmed = parseInt(card.dataset.confirmedRating || "0", 10);
                    const ratingToSave = pending || confirmed;

                    if (!ratingToSave) {
                        if (ratingBarEl) {
                            ratingBarEl.classList.add("needs-rating-pulse");
                            setTimeout(() => ratingBarEl.classList.remove("needs-rating-pulse"), 900);
                        }
                        showToast(`⭐ Lütfen önce "${title}" için 1–10 arası puanınızı seçin, ardından "İzledim" butonuna tıklayın.`);
                        return;
                    }

                    await submitCardWatchedRating(ratingToSave);
                });
            }

            const removeBtn = card.querySelector(".remove-watchlist-btn");
            if (removeBtn) {
                removeBtn.addEventListener("click", async () => {
                    if (!isAuthenticated) {
                        guestWatchlist = guestWatchlist.filter(
                            (x) => !(Number(x.tmdb_id) === tmdbId && x.media_type === mediaType)
                        );
                        syncGuestWatchlistSessionStorage();
                        updateCounters(guestWatchlist.length);
                        syncDiscoverCardsWithGuestWatchlist();
                        await refreshGuestRecommendationsPreview(false);
                        return;
                    }

                    try {
                        const res = await fetch(`/api/watchlist/${mediaType}/${tmdbId}`, {
                            method: "DELETE",
                        });
                        if (!res.ok) return;
                        const data = await res.json();

                        card.remove();
                        updateSegmentedCounts();
                        applySegmentedTabFilter();
                        if (data.stats) {
                            updateCounters(data.stats.total);
                            if (data.stats.total === 0) {
                                window.location.reload();
                            }
                        }
                        showToast(`🗑️ "${title}" izleme listenden çıkarıldı.`);
                    } catch (err) {
                        console.error("Silme hatası:", err);
                    }
                });
            }
        });
    }

    bindMediaCardEvents(document);

    // =========================================================================
    // 5. Sayfa Başına 20 Film Numaralı Sayfalama (Page Switcher: 1, 2, 3...)
    // =========================================================================
    const segmentedControl = document.getElementById("mediaSegmentedControl");
    const tabEmptyState =
        document.getElementById("tabEmptyState") ||
        document.getElementById("discoverEmptyState");
    const watchlistQuickSearchInput = document.getElementById("watchlistQuickSearchInput");
    const numberedPaginationBar = document.getElementById("numberedPaginationBar");

    let currentMediaFilter = "ALL";
    let quickSearchQuery = "";
    const PAGE_SIZE = 20; // Ana sayfada ve listelerde sayfa başına tam 20 yapım
    let currentPage = 1;

    function updateSegmentedCounts() {
        if (!segmentedControl || !activeGrid) return;
        const allCards = Array.from(activeGrid.querySelectorAll(".media-card"));
        const movieCount = allCards.filter((c) => c.dataset.mediaType === "movie").length;
        const tvCount = allCards.filter((c) => c.dataset.mediaType === "tv").length;

        const allBadge = segmentedControl.querySelector('[data-count-for="ALL"]');
        const movieBadge = segmentedControl.querySelector('[data-count-for="movie"]');
        const tvBadge = segmentedControl.querySelector('[data-count-for="tv"]');

        if (allBadge) allBadge.textContent = String(allCards.length);
        if (movieBadge) movieBadge.textContent = String(movieCount);
        if (tvBadge) tvBadge.textContent = String(tvCount);
    }

    function renderNumberedPagination(totalMatched) {
        if (!numberedPaginationBar) return;
        const totalPages = Math.ceil(totalMatched / PAGE_SIZE);

        if (totalPages <= 1) {
            numberedPaginationBar.hidden = true;
            numberedPaginationBar.innerHTML = "";
            return;
        }

        numberedPaginationBar.hidden = false;
        numberedPaginationBar.innerHTML = "";

        const prevBtn = document.createElement("button");
        prevBtn.type = "button";
        prevBtn.className = "page-nav-btn";
        prevBtn.textContent = "← Önceki";
        prevBtn.disabled = currentPage <= 1;
        prevBtn.addEventListener("click", () => {
            if (currentPage > 1) {
                currentPage -= 1;
                applySegmentedTabFilter(true);
            }
        });
        numberedPaginationBar.appendChild(prevBtn);

        // Akıllı sayfa numarası aralığı (1 ... 4 5 6 ... 22)
        const maxButtons = 7;
        let startPage = Math.max(1, currentPage - 3);
        let endPage = Math.min(totalPages, startPage + maxButtons - 1);
        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }

        if (startPage > 1) {
            const firstBtn = document.createElement("button");
            firstBtn.type = "button";
            firstBtn.className = "page-nav-btn";
            firstBtn.textContent = "1";
            firstBtn.addEventListener("click", () => {
                currentPage = 1;
                applySegmentedTabFilter(true);
            });
            numberedPaginationBar.appendChild(firstBtn);
        }

        for (let p = startPage; p <= endPage; p++) {
            const pageBtn = document.createElement("button");
            pageBtn.type = "button";
            pageBtn.className = `page-nav-btn ${p === currentPage ? "active" : ""}`;
            pageBtn.textContent = String(p);
            pageBtn.addEventListener("click", () => {
                currentPage = p;
                applySegmentedTabFilter(true);
            });
            numberedPaginationBar.appendChild(pageBtn);
        }

        if (endPage < totalPages) {
            const lastBtn = document.createElement("button");
            lastBtn.type = "button";
            lastBtn.className = "page-nav-btn";
            lastBtn.textContent = String(totalPages);
            lastBtn.addEventListener("click", () => {
                currentPage = totalPages;
                applySegmentedTabFilter(true);
            });
            numberedPaginationBar.appendChild(lastBtn);
        }

        const nextBtn = document.createElement("button");
        nextBtn.type = "button";
        nextBtn.className = "page-nav-btn";
        nextBtn.textContent = "Sonraki →";
        nextBtn.disabled = currentPage >= totalPages;
        nextBtn.addEventListener("click", () => {
            if (currentPage < totalPages) {
                currentPage += 1;
                applySegmentedTabFilter(true);
            }
        });
        numberedPaginationBar.appendChild(nextBtn);

        const summary = document.createElement("span");
        summary.className = "page-summary-label";
        summary.textContent = `Sayfa ${currentPage} / ${totalPages} (${totalMatched} yapım)`;
        numberedPaginationBar.appendChild(summary);
    }

    function applySegmentedTabFilter(scrollTop = false) {
        if (!activeGrid) return;
        const cards = Array.from(activeGrid.querySelectorAll(".media-card"));
        const cleanQuick = quickSearchQuery.trim().toLowerCase();

        const matchingCards = [];
        cards.forEach((card) => {
            const cType = card.dataset.mediaType || "movie";
            const cTitle = (card.dataset.title || "").toLowerCase();
            const matchesType = currentMediaFilter === "ALL" || cType === currentMediaFilter;
            const matchesQuick = !cleanQuick || cTitle.includes(cleanQuick);

            if (matchesType && matchesQuick) {
                matchingCards.push(card);
            } else {
                card.style.display = "none";
            }
        });

        const totalMatched = matchingCards.length;
        const totalPages = Math.max(1, Math.ceil(totalMatched / PAGE_SIZE));
        if (currentPage > totalPages) currentPage = totalPages;
        if (currentPage < 1) currentPage = 1;

        const startIdx = (currentPage - 1) * PAGE_SIZE;
        const endIdx = startIdx + PAGE_SIZE;

        matchingCards.forEach((card, idx) => {
            card.style.display = idx >= startIdx && idx < endIdx ? "" : "none";
        });

        renderNumberedPagination(totalMatched);

        if (tabEmptyState) {
            const isDiscoverGrid = activeGrid.id === "discoverGrid";
            if (isDiscoverGrid) {
                tabEmptyState.hidden = totalMatched > 0;
            } else if (cards.length > 0) {
                tabEmptyState.hidden = totalMatched > 0;
            }
        }

        const searchBarRequestBtn = document.getElementById("searchBarRequestBtn");
        if (searchBarRequestBtn) {
            const discoverInputEl = document.getElementById("discoverSearchInput");
            const hasSearchQuery = Boolean(discoverInputEl && discoverInputEl.value.trim().length > 0);
            searchBarRequestBtn.hidden = !(totalMatched === 0 && (hasSearchQuery || cards.length === 0));
        }

        if (scrollTop) {
            window.scrollTo({ top: 0, behavior: "smooth" });
        }
    }

    if (segmentedControl) {
        segmentedControl.querySelectorAll(".segment-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                currentMediaFilter = btn.dataset.mediaFilter || "ALL";
                currentPage = 1;
                segmentedControl.querySelectorAll(".segment-btn").forEach((b) => {
                    const isActive = b === btn;
                    b.classList.toggle("active", isActive);
                    b.setAttribute("aria-selected", String(isActive));
                });
                applySegmentedTabFilter(false);
            });
        });
    }

    if (watchlistQuickSearchInput) {
        watchlistQuickSearchInput.addEventListener("input", (e) => {
            quickSearchQuery = e.target.value;
            currentPage = 1;
            applySegmentedTabFilter(false);
        });
    }

    // İlk yüklemede 20'lik sayfalamayı uygula
    applySegmentedTabFilter(false);

    // =========================================================================
    // 6. Listeyi Sıfırla (Clear)
    // =========================================================================
    async function triggerClearWatchlist() {
        if (!isAuthenticated) {
            guestWatchlist = [];
            updateCounters(0);
            syncDiscoverCardsWithGuestWatchlist();
            await refreshGuestRecommendationsPreview(false);
            showToast("🗑️ Geçici liste sıfırlandı.");
            return;
        }

        try {
            const res = await fetch("/api/watchlist/clear", {
                method: "POST",
                headers: { Accept: "application/json" },
            });
            if (res.ok) {
                showToast("🗑️ İzleme listeniz sıfırlandı.");
                setTimeout(() => window.location.reload(), 380);
            }
        } catch (err) {
            console.error("Liste sıfırlama hatası:", err);
        }
    }

    if (clearWatchlistBtn) {
        clearWatchlistBtn.addEventListener("click", triggerClearWatchlist);
    }

    const scrollToGuestRecsBtn = document.getElementById("scrollToGuestRecsBtn");
    if (scrollToGuestRecsBtn) {
        scrollToGuestRecsBtn.addEventListener("click", async () => {
            if (guestWatchlist.length === 0) {
                showToast("✨ Öneri hesaplamak için önce listeden birkaç film veya diziye puan verin.");
            } else {
                await refreshGuestRecommendationsPreview(true);
            }
        });
    }

    // =========================================================================
    // 7. Keşfet Canlı Arama (Unified Search & Filter Bar)
    // =========================================================================
    const discoverGrid = document.getElementById("discoverGrid");
    const discoverSearchInput = document.getElementById("discoverSearchInput");
    const discoverGenreSelect = document.getElementById("discoverGenreSelect");
    const discoverSortSelect = document.getElementById("discoverSortSelect");

    if (discoverGrid) {
        const discoverState = {
            q: "",
            genre: "ALL",
            sortBy: "popularity",
        };

        let searchTimer = null;

        function renderDiscoverCards(items) {
            discoverGrid.innerHTML = "";

            items.forEach((item) => {
                const article = document.createElement("article");
                article.className = `media-card ${item.in_watchlist ? "is-in-watchlist" : ""}`;
                article.dataset.tmdbId = String(item.tmdb_id);
                article.dataset.mediaType = item.media_type;
                article.dataset.title = item.title;
                article.dataset.poster = item.poster_path;
                article.dataset.genres = JSON.stringify(item.genres || []);
                article.dataset.keywords = JSON.stringify(item.keywords || []);

                const genreTagsHtml = (item.genres || [])
                    .slice(0, 2)
                    .map((g) => `<span class="genre-tag">${escapeHtml(g)}</span>`)
                    .join("");

                let ratingBtnsHtml = "";
                for (let r = 1; r <= 10; r++) {
                    const selectedCls = (item.in_watchlist && item.user_rating === r) ? "selected" : "";
                    ratingBtnsHtml += `<button type="button" class="rate-num-btn ${selectedCls}" data-rating="${r}" title="${r}/10 Puan Seç">${r}</button>`;
                }

                const watchedHeaderLabel = (item.in_watchlist && item.user_rating)
                    ? `✓ İzlendi (Puanın: <strong class="gold-text">${item.user_rating}/10</strong>)`
                    : "Puan Seç (1-10):";
                const watchedBtnText = (item.in_watchlist && item.user_rating)
                    ? `✓ İzlendi (${item.user_rating}/10)`
                    : "🎬 İzledim";
                const watchedBtnCls = (item.in_watchlist && item.user_rating) ? "is-watched-confirmed" : "";

                article.innerHTML = `
                    <div class="media-poster-wrap">
                        <span class="media-badge-type ${escapeHtml(item.media_type)}">
                            ${item.media_type === "tv" ? "DİZİ" : "FİLM"}
                        </span>
                        <span class="media-badge-year">${escapeHtml(String(item.release_year || ""))}</span>
                        <div class="watched-ribbon" ${item.in_watchlist ? "" : "hidden"}>
                            ✓ İzlendi (<strong class="user-rating-val">${item.user_rating || ""}</strong>/10)
                        </div>
                        <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}" class="poster-link">
                            <img src="${escapeHtml(item.poster_path || '/static/img/no-poster.svg')}" alt="${escapeHtml(item.title)}" loading="lazy" onerror="this.onerror=null;this.src='/static/img/no-poster.svg';">
                        </a>
                    </div>
                    <div class="media-card-body">
                        <div class="media-meta-row">
                            <span class="tmdb-score">⭐ ${escapeHtml(String(item.vote_average))}</span>
                            <span class="card-year-inline">${escapeHtml(String(item.release_year || ""))}</span>
                            <div class="genre-tags">${genreTagsHtml}</div>
                        </div>
                        <h3 class="media-title">
                            <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}">${escapeHtml(item.title)}</a>
                        </h3>
                        <p class="media-overview">${escapeHtml(item.overview || "")}</p>
                        <div class="quick-rate-box">
                            <div class="quick-rate-header">
                                <span class="rate-label">${watchedHeaderLabel}</span>
                                <button type="button" class="card-watch-confirm-btn ${watchedBtnCls}">${watchedBtnText}</button>
                            </div>
                            <div class="rating-number-bar">${ratingBtnsHtml}</div>
                        </div>
                    </div>
                `;
                discoverGrid.appendChild(article);
            });

            currentPage = 1;
            bindMediaCardEvents(discoverGrid);
            syncDiscoverCardsWithGuestWatchlist();
            updateSegmentedCounts();
            applySegmentedTabFilter(false);
        }

        async function fetchDiscoverItems() {
            const params = new URLSearchParams();
            if (discoverState.q.trim()) params.set("q", discoverState.q.trim());
            if (discoverState.genre !== "ALL") params.set("genre", discoverState.genre);
            params.set("sort_by", discoverState.sortBy);

            try {
                const res = await fetch(`/api/catalog/search?${params.toString()}`);
                if (!res.ok) return;
                const data = await res.json();
                renderDiscoverCards(data.items || []);
            } catch (err) {
                console.error("Keşfet arama hatası:", err);
            }
        }

        function scheduleDiscoverSearch() {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(fetchDiscoverItems, 130);
        }

        if (discoverSearchInput) {
            discoverSearchInput.addEventListener("input", (e) => {
                discoverState.q = e.target.value;
                if (searchClearBtn) searchClearBtn.hidden = discoverState.q.length === 0;
                scheduleDiscoverSearch();
            });
        }

        if (searchClearBtn) {
            searchClearBtn.addEventListener("click", () => {
                discoverState.q = "";
                if (discoverSearchInput) discoverSearchInput.value = "";
                searchClearBtn.hidden = true;
                scheduleDiscoverSearch();
            });
        }

        if (discoverGenreSelect) {
            discoverGenreSelect.addEventListener("change", (e) => {
                discoverState.genre = e.target.value;
                scheduleDiscoverSearch();
            });
        }

        if (discoverSortSelect) {
            discoverSortSelect.addEventListener("change", (e) => {
                discoverState.sortBy = e.target.value;
                scheduleDiscoverSearch();
            });
        }
    }

    // =========================================================================
    // 8. "🎬 Film / Dizi Talep Et" Modal & Form Yönetimi (data/requests.json)
    // =========================================================================
    const requestModal = document.getElementById("contentRequestModal");
    const closeRequestModalBtn = document.getElementById("closeRequestModalBtn");
    const contentRequestForm = document.getElementById("contentRequestForm");
    const reqUsernameInput = document.getElementById("reqUsernameInput");
    const reqEmailInput = document.getElementById("reqEmailInput");
    const reqTitleInput = document.getElementById("reqTitleInput");
    const reqTypeSelect = document.getElementById("reqTypeSelect");
    const reqYearInput = document.getElementById("reqYearInput");
    const reqNoteInput = document.getElementById("reqNoteInput");
    const requestFeedbackAlert = document.getElementById("requestFeedbackAlert");
    const submitRequestBtn = document.getElementById("submitRequestBtn");

    function openRequestModal() {
        if (!requestModal) return;
        if (requestFeedbackAlert) requestFeedbackAlert.hidden = true;
        if (reqUsernameInput && !reqUsernameInput.value && reqUsernameInput.dataset.defaultVal) {
            reqUsernameInput.value = reqUsernameInput.dataset.defaultVal;
        }
        if (reqEmailInput && !reqEmailInput.value && reqEmailInput.dataset.defaultVal) {
            reqEmailInput.value = reqEmailInput.dataset.defaultVal;
        }
        // Eğer arama kutusunda bir metin varsa otomatik olarak talep başlığına doldur
        if (reqTitleInput && discoverSearchInput && discoverSearchInput.value.trim()) {
            reqTitleInput.value = discoverSearchInput.value.trim();
        }
        requestModal.hidden = false;
        reqTitleInput?.focus();
    }

    function closeRequestModal() {
        if (requestModal) requestModal.hidden = true;
    }

    document.querySelectorAll(".open-request-modal-btn").forEach((btn) => {
        btn.addEventListener("click", openRequestModal);
    });

    if (closeRequestModalBtn) {
        closeRequestModalBtn.addEventListener("click", closeRequestModal);
    }

    if (requestModal) {
        requestModal.addEventListener("click", (e) => {
            if (e.target === requestModal) closeRequestModal();
        });
    }

    if (contentRequestForm) {
        contentRequestForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const titleVal = (reqTitleInput?.value || "").trim();
            const usernameVal = (reqUsernameInput?.value || "").trim();
            const emailVal = (reqEmailInput?.value || "").trim();
            if (!titleVal || !usernameVal || !emailVal) return;

            if (submitRequestBtn) {
                submitRequestBtn.disabled = true;
                submitRequestBtn.textContent = "⏳ Gönderiliyor...";
            }

            try {
                const res = await fetch("/api/requests", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        title: titleVal,
                        media_type: reqTypeSelect?.value || "Film",
                        year: reqYearInput?.value || "",
                        note: reqNoteInput?.value || "",
                        requester_username: usernameVal,
                        requester_email: emailVal,
                    }),
                });

                const data = await res.json();
                if (res.ok && data.status === "ok") {
                    if (requestFeedbackAlert) {
                        requestFeedbackAlert.textContent = `✓ ${data.message}`;
                        requestFeedbackAlert.hidden = false;
                    }
                    showToast(`🎬 ${data.message}`);
                    contentRequestForm.reset();
                    if (reqUsernameInput && reqUsernameInput.dataset.defaultVal) {
                        reqUsernameInput.value = reqUsernameInput.dataset.defaultVal;
                    }
                    if (reqEmailInput && reqEmailInput.dataset.defaultVal) {
                        reqEmailInput.value = reqEmailInput.dataset.defaultVal;
                    }
                    setTimeout(() => {
                        closeRequestModal();
                    }, 1500);
                } else if (data.error && requestFeedbackAlert) {
                    requestFeedbackAlert.textContent = `⚠️ ${data.error}`;
                    requestFeedbackAlert.hidden = false;
                }
            } catch (err) {
                console.error("Talep gönderme hatası:", err);
            } finally {
                if (submitRequestBtn) {
                    submitRequestBtn.disabled = false;
                    submitRequestBtn.textContent = "📨 Talebi Gönder";
                }
            }
        });
    }

    // =========================================================================
    // 9. Sinematik İçerik Detay Sayfası (/detail/<media_type>/<int:tmdb_id>) Mantığı
    // =========================================================================
    const detailRoot = document.getElementById("detailPageRoot");
    if (detailRoot) {
        const tmdbId = parseInt(detailRoot.dataset.tmdbId || "0", 10);
        const mediaType = detailRoot.dataset.mediaType || "movie";
        const title = detailRoot.dataset.title || "";
        const posterPath = detailRoot.dataset.poster || "";
        const trailerKey = detailRoot.dataset.trailerKey || "";

        let genres = [];
        let keywords = [];
        try {
            genres = JSON.parse(detailRoot.dataset.genres || "[]");
        } catch (_) {}
        try {
            keywords = JSON.parse(detailRoot.dataset.keywords || "[]");
        } catch (_) {}

        const ratingBar = document.getElementById("detailRatingBar");
        const saveBtn = document.getElementById("detailSaveWatchlistBtn");
        const removeBtn = document.getElementById("detailRemoveWatchlistBtn");
        const watchedRibbon = document.getElementById("detailWatchedRibbon");
        const userRatingVal = document.getElementById("detailUserRatingVal");
        const ratePromptLabel = document.getElementById("detailRatePromptLabel");
        const detailStartInput = document.getElementById("detailWatchStartDateInput");
        const detailEndInput = document.getElementById("detailWatchEndDateInput");
        const detailRangeBadge = document.getElementById("detailWatchedRangeBadge");
        const detailSeasonSelect = document.getElementById("detailSeasonNumberSelect");
        const detailSeasonPillsRow = document.getElementById("detailSeasonDatesPillsRow");

        if (detailStartInput && !detailStartInput.value) detailStartInput.value = getDefaultTodayDate2026();
        if (detailEndInput && !detailEndInput.value) detailEndInput.value = detailStartInput?.value || getDefaultTodayDate2026();

        function updateDetailRangePreview() {
            if (!detailRangeBadge || !detailStartInput || !detailEndInput) return;
            detailRangeBadge.textContent = `📅 ${formatTurkishDateRangeClient(detailStartInput.value, detailEndInput.value)}`;
        }

        if (detailSeasonSelect) {
            detailSeasonSelect.addEventListener("change", () => {
                const opt = detailSeasonSelect.selectedOptions[0];
                if (opt) {
                    if (detailStartInput && opt.dataset.start) detailStartInput.value = opt.dataset.start;
                    if (detailEndInput && opt.dataset.end) detailEndInput.value = opt.dataset.end;
                }
            });
        }

        let selectedRating = null;
        const preSelected = ratingBar?.querySelector(".detail-rate-btn.selected");
        if (preSelected && detailRoot.dataset.inWatchlist === "true") {
            selectedRating = parseInt(preSelected.dataset.rating || "0", 10) || null;
        }

        // Misafir modunda detay sayfası açıldığında geçici listede varsa senkronize et
        if (!isAuthenticated) {
            const guestMatch = guestWatchlist.find(
                (x) => Number(x.tmdb_id) === tmdbId && x.media_type === mediaType
            );
            if (guestMatch && guestMatch.user_rating) {
                selectedRating = Number(guestMatch.user_rating);
                if (watchedRibbon) watchedRibbon.hidden = false;
                if (userRatingVal) userRatingVal.textContent = String(selectedRating);
                if (saveBtn) {
                    saveBtn.textContent = `✓ İzlendi (${selectedRating}/10)`;
                    saveBtn.classList.add("is-watched-confirmed");
                }
                if (removeBtn) removeBtn.hidden = false;
                if (ratePromptLabel) {
                    ratePromptLabel.innerHTML = `✓ İzlendi — Verdiğin Puan: <strong class="gold-text">${selectedRating}/10</strong>:`;
                }
                ratingBar?.querySelectorAll(".detail-rate-btn").forEach((b) => {
                    b.classList.toggle("selected", Number(b.dataset.rating) === selectedRating);
                });
            }
        }

        async function saveDetailRating(ratingToSave, customSeasonNum = null, customStart = "", customEnd = "") {
            const effRating = ratingToSave || selectedRating || 8;
            if (!ratingToSave && !customSeasonNum) {
                if (ratingBar) {
                    ratingBar.classList.add("needs-rating-pulse");
                    setTimeout(() => ratingBar.classList.remove("needs-rating-pulse"), 900);
                }
                showToast(`⭐ Lütfen önce "${title}" için 1–10 arası puanınızı seçin, ardından "İzledim" butonuna tıklayın.`);
                return;
            }

            selectedRating = effRating;
            const chosenStart = (customStart || detailStartInput?.value || getDefaultTodayDate2026()).trim();
            const chosenEnd = (customEnd || detailEndInput?.value || chosenStart).trim();
            const chosenSeason = customSeasonNum || (detailSeasonSelect ? parseInt(detailSeasonSelect.value || "1", 10) : 1);
            const rangeText = formatTurkishDateRangeClient(chosenStart, chosenEnd);
            const displayDateLabel = mediaType === "tv" ? `${chosenSeason}. Sezon: ${rangeText}` : rangeText;

            updateDetailRangePreview();

            if (!isAuthenticated) {
                upsertGuestWatchlistItem({
                    tmdb_id: tmdbId,
                    media_type: mediaType,
                    title: title,
                    poster_path: posterPath,
                    user_rating: effRating,
                    watch_start_date: chosenStart,
                    watch_end_date: chosenEnd,
                    watched_at: chosenEnd,
                    season_number: mediaType === "tv" ? chosenSeason : undefined,
                    genres: genres,
                    keywords: keywords,
                });
                detailRoot.dataset.inWatchlist = "true";
                if (watchedRibbon) watchedRibbon.hidden = false;
                if (userRatingVal) userRatingVal.textContent = String(effRating);
                if (saveBtn) {
                    saveBtn.textContent = `✓ İzlendi (${effRating}/10)`;
                    saveBtn.classList.add("is-watched-confirmed");
                    saveBtn.classList.remove("is-pending-confirm");
                }
                if (removeBtn) removeBtn.hidden = false;
                if (detailSeasonPillsRow && mediaType === "tv") {
                    detailSeasonPillsRow.hidden = false;
                    detailSeasonPillsRow.innerHTML = `<span class="season-date-chip">📺 ${escapeHtml(displayDateLabel)}</span>`;
                }
                const seasonChipEl = document.querySelector(`[data-season-label-chip="${chosenSeason}"]`);
                if (seasonChipEl) seasonChipEl.textContent = displayDateLabel;
                if (ratePromptLabel) {
                    ratePromptLabel.innerHTML = `✓ İzlendi (${escapeHtml(displayDateLabel)}) — Verdiğin Puan: <strong class="gold-text">${effRating}/10</strong>:`;
                }
                showToast(`✓ "${title}" (${effRating}/10 • ${displayDateLabel}) İzlendi olarak işaretlendi!`);
                return;
            }

            try {
                const res = await fetch("/api/watchlist", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        tmdb_id: tmdbId,
                        media_type: mediaType,
                        title: title,
                        poster_path: posterPath,
                        user_rating: effRating,
                        watch_start_date: chosenStart,
                        watch_end_date: chosenEnd,
                        watched_at: chosenEnd,
                        season_number: mediaType === "tv" ? chosenSeason : undefined,
                        genres: genres,
                        keywords: keywords,
                    }),
                });
                if (!res.ok) return;
                const data = await res.json();

                detailRoot.dataset.inWatchlist = "true";
                if (watchedRibbon) watchedRibbon.hidden = false;
                if (userRatingVal) userRatingVal.textContent = String(effRating);
                if (saveBtn) {
                    saveBtn.textContent = `✓ İzlendi (${effRating}/10)`;
                    saveBtn.classList.add("is-watched-confirmed");
                    saveBtn.classList.remove("is-pending-confirm");
                }
                if (removeBtn) removeBtn.hidden = false;

                if (data.item) {
                    if (detailRangeBadge && data.item.watched_date_label) {
                        detailRangeBadge.textContent = `📅 ${data.item.watched_date_label}`;
                    }
                    if (detailSeasonPillsRow && Array.isArray(data.item.season_watch_dates)) {
                        detailSeasonPillsRow.hidden = data.item.season_watch_dates.length === 0;
                        detailSeasonPillsRow.innerHTML = data.item.season_watch_dates
                            .map((s) => `<span class="season-date-chip">📺 ${escapeHtml(s.label)}</span>`)
                            .join("");
                        data.item.season_watch_dates.forEach((s) => {
                            const chip = document.querySelector(`[data-season-label-chip="${s.season_number}"]`);
                            if (chip) chip.textContent = s.label;
                        });
                    }
                }

                if (ratePromptLabel) {
                    ratePromptLabel.innerHTML = `✓ İzlendi (${escapeHtml(displayDateLabel)}) — Verdiğin Puan: <strong class="gold-text">${effRating}/10</strong>:`;
                }
                if (data.stats) updateCounters(data.stats.total);
                showToast(`✓ "${title}" (${effRating}/10 • ${displayDateLabel}) İzlendi olarak kaydedildi!`);
            } catch (err) {
                console.error("Detay sayfası kayıt hatası:", err);
            }
        }

        [detailStartInput, detailEndInput].forEach((inp) => {
            if (!inp) return;
            inp.addEventListener("change", () => {
                updateDetailRangePreview();
                if (detailRoot.dataset.inWatchlist === "true" && selectedRating) {
                    saveDetailRating(selectedRating);
                }
            });
        });

        // Dizi detay sayfasındaki sezon panellerinde yer alan "💾 X. Sezon Tarihini Kaydet" butonları
        document.querySelectorAll(".btn-save-season-dates").forEach((btn) => {
            btn.addEventListener("click", () => {
                const sNum = parseInt(btn.dataset.saveSeasonNum || "1", 10);
                const bar = btn.closest("[data-season-date-bar]");
                const sStart = bar?.querySelector(".season-panel-start-input")?.value || getDefaultTodayDate2026();
                const sEnd = bar?.querySelector(".season-panel-end-input")?.value || sStart;
                saveDetailRating(selectedRating || 8, sNum, sStart, sEnd);
            });
        });

        if (ratingBar) {
            ratingBar.querySelectorAll(".detail-rate-btn").forEach((btn) => {
                btn.addEventListener("click", () => {
                    selectedRating = parseInt(btn.dataset.rating || "0", 10);
                    ratingBar.querySelectorAll(".detail-rate-btn").forEach((b) => {
                        b.classList.toggle("selected", b === btn);
                    });
                    if (ratePromptLabel) {
                        ratePromptLabel.innerHTML = `Seçilen Puan: <strong class="gold-text">${selectedRating}/10</strong> — Onaylamak için "İzledim" butonuna tıkla:`;
                    }
                    if (saveBtn) {
                        saveBtn.textContent = `🎬 İzledim (${selectedRating}/10 Onayla)`;
                        saveBtn.classList.add("is-pending-confirm");
                        saveBtn.classList.remove("is-watched-confirmed");
                    }
                });
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener("click", () => saveDetailRating(selectedRating));
        }

        if (removeBtn) {
            removeBtn.addEventListener("click", async () => {
                selectedRating = null;
                ratingBar?.querySelectorAll(".detail-rate-btn").forEach((b) => b.classList.remove("selected"));

                if (!isAuthenticated) {
                    guestWatchlist = guestWatchlist.filter(
                        (x) => !(Number(x.tmdb_id) === tmdbId && x.media_type === mediaType)
                    );
                    updateCounters(guestWatchlist.length);
                    if (watchedRibbon) watchedRibbon.hidden = true;
                    if (saveBtn) {
                        saveBtn.textContent = "🎬 İzledim";
                        saveBtn.classList.remove("is-watched-confirmed", "is-pending-confirm");
                    }
                    removeBtn.hidden = true;
                    if (ratePromptLabel) {
                        ratePromptLabel.textContent = '1–10 Arası Puanını Seç ve "İzledim" Butonuna Tıkla:';
                    }
                    showToast(`🗑️ "${title}" geçici listeden çıkarıldı.`);
                    return;
                }

                try {
                    const res = await fetch(`/api/watchlist/${mediaType}/${tmdbId}`, {
                        method: "DELETE",
                    });
                    if (!res.ok) return;
                    const data = await res.json();

                    if (watchedRibbon) watchedRibbon.hidden = true;
                    if (saveBtn) {
                        saveBtn.textContent = "🎬 İzledim";
                        saveBtn.classList.remove("is-watched-confirmed", "is-pending-confirm");
                    }
                    removeBtn.hidden = true;
                    if (ratePromptLabel) {
                        ratePromptLabel.textContent = '1–10 Arası Puanını Seç ve "İzledim" Butonuna Tıkla:';
                    }
                    if (data.stats) updateCounters(data.stats.total);
                    showToast(`🗑️ "${title}" izleme listenden çıkarıldı.`);
                } catch (err) {
                    console.error("Detay sayfası silme hatası:", err);
                }
            });
        }

        const openTrailerBtn = document.getElementById("openTrailerModalBtn");
        const closeTrailerBtn = document.getElementById("closeTrailerModalBtn");
        const trailerModal = document.getElementById("trailerModal");
        const trailerIframe = document.getElementById("trailerYoutubeIframe");

        function openTrailerModal() {
            if (!trailerModal) return;
            if (trailerIframe && trailerKey) {
                trailerIframe.src = `https://www.youtube.com/embed/${trailerKey}?autoplay=1&rel=0`;
            }
            trailerModal.hidden = false;
        }

        function closeTrailerModal() {
            if (!trailerModal) return;
            trailerModal.hidden = true;
            if (trailerIframe) {
                trailerIframe.src = "";
            }
        }

        if (openTrailerBtn) openTrailerBtn.addEventListener("click", openTrailerModal);
        if (closeTrailerBtn) closeTrailerBtn.addEventListener("click", closeTrailerModal);
        if (trailerModal) {
            trailerModal.addEventListener("click", (e) => {
                if (e.target === trailerModal) closeTrailerModal();
            });
        }
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            if (whyModal && !whyModal.hidden) closeWhyRecommendedModal();
            if (requestModal && !requestModal.hidden) closeRequestModal();
        }
    });
});
