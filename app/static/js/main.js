// SineMix - Oturum Durumuna Göre (Misafir Bellek İçi vs. Oturum Açmış Kalıcı JSON) İstemci Mantığı
document.addEventListener("DOMContentLoaded", () => {
    const mainNavbar = document.getElementById("mainNavbar");
    const isAuthenticated = mainNavbar?.dataset.authenticated === "true";

    const toastEl = document.getElementById("toastNotification");
    const navWatchlistBadge = document.getElementById("navWatchlistBadge");
    const guestTempCountBadge = document.getElementById("guestTempCountBadge");
    const navbarSearchInput = document.getElementById("filmSearchInput");
    const searchClearBtn = document.getElementById("searchClearBtn");
    const clearWatchlistBtn = document.getElementById("clearWatchlistBtn");

    // Misafir Modu: Yalnızca o anki sayfa yaşam döngüsünde (JS belleğinde) tutulur; F5 atıldığında sıfırlanır.
    let guestWatchlist = [];

    let toastTimer = null;
    function showToast(message) {
        if (!toastEl) return;
        toastEl.textContent = message;
        toastEl.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            toastEl.hidden = true;
        }, 3000);
    }

    function updateCounters(newCount) {
        if (navWatchlistBadge && typeof newCount === "number") {
            navWatchlistBadge.textContent = String(newCount);
        }
        if (guestTempCountBadge && typeof newCount === "number") {
            guestTempCountBadge.textContent = String(newCount);
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
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && whyModal && !whyModal.hidden) {
            closeWhyRecommendedModal();
        }
    });

    // =========================================================================
    // 2. Misafir Modu Bellek İçi (Stateless) Öneri Hesaplama ve Kart Çizimi
    // =========================================================================
    function upsertGuestWatchlistItem(itemObj) {
        const idx = guestWatchlist.findIndex(
            (x) => Number(x.tmdb_id) === Number(itemObj.tmdb_id) && x.media_type === itemObj.media_type
        );
        if (idx >= 0) {
            guestWatchlist[idx] = { ...guestWatchlist[idx], ...itemObj };
        } else {
            guestWatchlist.unshift(itemObj);
        }
        updateCounters(guestWatchlist.length);
    }

    function syncDiscoverCardsWithGuestWatchlist() {
        if (isAuthenticated) return;
        const lookup = new Map(
            guestWatchlist.map((i) => [`${i.media_type}_${i.tmdb_id}`, Number(i.user_rating)])
        );

        document.querySelectorAll("#discoverGrid .media-card").forEach((card) => {
            const key = `${card.dataset.mediaType || "movie"}_${card.dataset.tmdbId}`;
            const rating = lookup.get(key);
            const ribbon = card.querySelector(".watched-ribbon");
            const ratingValEl = card.querySelector(".user-rating-val");

            if (rating) {
                card.classList.add("is-in-watchlist");
                if (ribbon) ribbon.hidden = false;
                if (ratingValEl) ratingValEl.textContent = String(rating);
                card.querySelectorAll(".rate-num-btn").forEach((b) => {
                    b.classList.toggle("selected", Number(b.dataset.rating) === rating);
                });
            } else {
                card.classList.remove("is-in-watchlist");
                if (ribbon) ribbon.hidden = true;
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
            .slice(0, 3)
            .map((g) => `<span class="genre-tag ${matchedSet.has(g) ? "matched" : ""}">${escapeHtml(g)}</span>`)
            .join("");

        let ratingBtnsHtml = "";
        for (let r = 1; r <= 10; r++) {
            const toneCls = r < 5 ? "low-rate" : r >= 8 ? "high-rate" : "";
            ratingBtnsHtml += `<button type="button" class="rate-num-btn ${toneCls}" data-rating="${r}">${r}</button>`;
        }

        const badgeTone = item.match_score >= 85 ? "high-match" : item.match_score >= 70 ? "mid-match" : "";

        article.innerHTML = `
            <div class="media-poster-wrap">
                <span class="media-badge-type ${escapeHtml(item.media_type)}">
                    ${item.media_type === "tv" ? "DİZİ" : "FİLM"}
                </span>
                <div class="match-score-badge ${badgeTone}">
                    %${item.match_score} Eşleşme
                </div>
                <div class="watched-ribbon" hidden>
                    ✓ Listene Eklendi: <strong class="user-rating-val"></strong>/10
                </div>
                <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}" class="poster-link">
                    <img src="${escapeHtml(item.poster_path)}" alt="${escapeHtml(item.title)}" loading="lazy">
                </a>
            </div>
            <div class="media-card-body">
                <div class="media-meta-row">
                    <span class="tmdb-score">⭐ ${escapeHtml(String(item.vote_average))} <small>(${escapeHtml(String(item.release_year || ""))})</small></span>
                    <div class="genre-tags">${genreTagsHtml}</div>
                </div>
                <h3 class="media-title">
                    <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}">${escapeHtml(item.title)}</a>
                </h3>
                <p class="media-overview">${escapeHtml(item.overview || "")}</p>
                <button type="button" class="why-modal-trigger-btn" aria-haspopup="dialog">
                    <span class="sparkle-icon">✨</span>
                    <span>Neden Önerildi?</span>
                    <span class="why-score-pill">%${item.match_score}</span>
                </button>
                <div class="quick-rate-box">
                    <div class="quick-rate-header">
                        <span class="rate-label">İzledin mi? Puan Ver & Listeye Ekle:</span>
                    </div>
                    <div class="rating-number-bar">${ratingBtnsHtml}</div>
                </div>
            </div>
        `;
        return article;
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

            // A) Keşfet sayfasındaki canlı öneri paneli
            const liveSection = document.getElementById("liveGuestRecommendationsSection");
            const liveGrid = document.getElementById("liveRecommendationsGrid");
            const liveChips = document.getElementById("liveProfileChips");

            if (liveSection && liveGrid) {
                if (recs.length === 0) {
                    liveSection.hidden = true;
                    liveGrid.innerHTML = "";
                } else {
                    liveSection.hidden = false;
                    liveGrid.innerHTML = "";
                    recs.slice(0, 6).forEach((item) => {
                        liveGrid.appendChild(buildRecommendationCardElement(item));
                    });
                    bindMediaCardEvents(liveGrid);

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

            // B) /oneriler sayfasındaysak ana öneri gridini güncelle
            const recsGrid = document.getElementById("recommendationsGrid");
            const recsEmptyBox = document.getElementById("recsEmptyStateBox");
            const recsProfileCard = document.getElementById("recsProfileSummaryCard");
            const recsSegmentedBar = document.getElementById("recsSegmentedBar");
            const favGenresEl = document.getElementById("recsFavoriteGenresChips");
            const favKwsEl = document.getElementById("recsFavoriteKeywordsChips");

            if (recsGrid) {
                recsGrid.innerHTML = "";
                recs.forEach((item) => {
                    recsGrid.appendChild(buildRecommendationCardElement(item));
                });
                bindMediaCardEvents(recsGrid);

                if (recsEmptyBox) recsEmptyBox.hidden = recs.length > 0;
                if (recsSegmentedBar) recsSegmentedBar.hidden = recs.length === 0;
                if (recsProfileCard) recsProfileCard.hidden = recs.length === 0;

                if (favGenresEl) {
                    const posHtml = (profile.favorite_genres || [])
                        .map((g) => `<span class="taste-chip positive">${escapeHtml(g.name)} <small>+${g.weight}</small></span>`)
                        .join("");
                    const negHtml = (profile.disliked_genres || [])
                        .map((g) => `<span class="taste-chip negative">${escapeHtml(g.name)} <small>${g.weight}</small></span>`)
                        .join("");
                    favGenresEl.innerHTML = posHtml + negHtml;
                }

                if (favKwsEl) {
                    favKwsEl.innerHTML = (profile.favorite_keywords || [])
                        .slice(0, 8)
                        .map((kw) => `<span class="taste-chip keyword">#${escapeHtml(kw.name)} <small>+${kw.weight}</small></span>`)
                        .join("");
                }

                updateSegmentedCounts();
                applySegmentedTabFilter();
            }
        } catch (err) {
            console.error("Misafir öneri hesaplama hatası:", err);
        }
    }

    // =========================================================================
    // 3. Kart Etkileşimleri (1-10 Puan Verme, Silme, Neden Önerildi Modal)
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

            // "✨ Neden Önerildi?" Butonu
            const whyBtn = card.querySelector(".why-modal-trigger-btn");
            if (whyBtn) {
                whyBtn.addEventListener("click", () => {
                    openWhyRecommendedModal(card);
                });
            }

            // 1-10 Puan Butonları
            card.querySelectorAll(".rate-num-btn").forEach((btn) => {
                btn.addEventListener("click", async () => {
                    const rating = parseInt(btn.dataset.rating || "8", 10);

                    card.classList.add("is-in-watchlist");
                    card.querySelectorAll(".rate-num-btn").forEach((b) => {
                        b.classList.toggle("selected", b === btn);
                    });

                    const ribbon = card.querySelector(".watched-ribbon");
                    const ratingValEl = card.querySelector(".user-rating-val");
                    if (ribbon) ribbon.hidden = false;
                    if (ratingValEl) ratingValEl.textContent = String(rating);

                    const rateLabel = card.querySelector(".rate-label");
                    if (rateLabel) rateLabel.textContent = "Puanını Güncelle (1-10):";

                    // Misafir Modu: Sunucuya kaydetme, yalnızca bellek içi (JS state) tut!
                    if (!isAuthenticated) {
                        upsertGuestWatchlistItem({
                            tmdb_id: tmdbId,
                            media_type: mediaType,
                            title: title,
                            poster_path: posterPath,
                            user_rating: rating,
                            genres: genres,
                            keywords: keywords,
                        });
                        showToast(`⚡ "${title}" (${rating}/10) geçici listeye eklendi (Misafir Modu: F5'te sıfırlanır)`);
                        await refreshGuestRecommendationsPreview(false);
                        return;
                    }

                    // Oturum Açmış Kullanıcı: Sunucudaki data/watchlists/<user_id>.json dosyasına kalıcı kaydet
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
                                genres: genres,
                                keywords: keywords,
                            }),
                        });

                        if (!res.ok) return;
                        const data = await res.json();

                        if (data.stats) {
                            updateCounters(data.stats.total);
                            const statTotal = document.getElementById("statTotalCount");
                            const statAvg = document.getElementById("statAvgRating");
                            if (statTotal) statTotal.textContent = String(data.stats.total);
                            if (statAvg) statAvg.textContent = `⭐ ${data.stats.avg_rating}`;
                        }

                        showToast(`✓ "${title}" (${rating}/10) kalıcı izleme listene kaydedildi!`);
                    } catch (err) {
                        console.error("Puan kaydetme hatası:", err);
                    }
                });
            });

            // Listeden Çıkar Butonu
            const removeBtn = card.querySelector(".remove-watchlist-btn");
            if (removeBtn) {
                removeBtn.addEventListener("click", async () => {
                    if (!isAuthenticated) {
                        guestWatchlist = guestWatchlist.filter(
                            (x) => !(Number(x.tmdb_id) === tmdbId && x.media_type === mediaType)
                        );
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
                        if (data.stats) {
                            updateCounters(data.stats.total);
                            if (data.stats.total === 0) {
                                window.location.reload();
                            }
                        }
                        showToast(`🗑️ "${title}" kalıcı izleme listenden çıkarıldı.`);
                    } catch (err) {
                        console.error("Silme hatası:", err);
                    }
                });
            }
        });
    }

    bindMediaCardEvents(document);

    // =========================================================================
    // 4. Film ve Dizi Ayrımı (Segmented Control Tabs) + 36'şar Sayfalama (Load More)
    // =========================================================================
    const segmentedControl = document.getElementById("mediaSegmentedControl");
    const activeGrid =
        document.getElementById("discoverGrid") ||
        document.getElementById("watchlistGrid") ||
        document.getElementById("recommendationsGrid");
    const tabEmptyState =
        document.getElementById("tabEmptyState") ||
        document.getElementById("discoverEmptyState");

    const watchlistQuickSearchInput = document.getElementById("watchlistQuickSearchInput");
    const watchlistPaginationBar = document.getElementById("watchlistPaginationBar");
    const watchlistShowingStatus = document.getElementById("watchlistShowingStatus");
    const watchlistLoadMoreBtn = document.getElementById("watchlistLoadMoreBtn");

    let currentMediaFilter = "ALL";
    let quickSearchQuery = "";
    const PAGE_SIZE = 36;
    let visibleLimit = PAGE_SIZE;

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

    function applySegmentedTabFilter() {
        if (!activeGrid) return;
        const cards = Array.from(activeGrid.querySelectorAll(".media-card"));
        const isPaginatedWatchlist = activeGrid.id === "watchlistGrid" || activeGrid.id === "discoverGrid";
        const cleanQuick = quickSearchQuery.trim().toLowerCase();

        let matchedTotal = 0;
        let shownCount = 0;

        cards.forEach((card) => {
            const cType = card.dataset.mediaType || "movie";
            const cTitle = (card.dataset.title || "").toLowerCase();
            const matchesType = currentMediaFilter === "ALL" || cType === currentMediaFilter;
            const matchesQuick = !cleanQuick || cTitle.includes(cleanQuick);

            if (matchesType && matchesQuick) {
                matchedTotal += 1;
                if (!isPaginatedWatchlist || shownCount < visibleLimit) {
                    card.style.display = "";
                    shownCount += 1;
                } else {
                    card.style.display = "none";
                }
            } else {
                card.style.display = "none";
            }
        });

        if (isPaginatedWatchlist && watchlistPaginationBar) {
            if (matchedTotal > PAGE_SIZE) {
                watchlistPaginationBar.hidden = false;
                if (watchlistShowingStatus) {
                    watchlistShowingStatus.textContent = `${shownCount} / ${matchedTotal} yapım gösteriliyor`;
                }
                if (watchlistLoadMoreBtn) {
                    watchlistLoadMoreBtn.hidden = shownCount >= matchedTotal;
                }
            } else {
                watchlistPaginationBar.hidden = true;
            }
        }

        if (tabEmptyState && cards.length > 0) {
            tabEmptyState.hidden = matchedTotal > 0;
        }
    }

    if (segmentedControl) {
        segmentedControl.querySelectorAll(".segment-btn").forEach((btn) => {
            btn.addEventListener("click", () => {
                currentMediaFilter = btn.dataset.mediaFilter || "ALL";
                visibleLimit = PAGE_SIZE;
                segmentedControl.querySelectorAll(".segment-btn").forEach((b) => {
                    const isActive = b === btn;
                    b.classList.toggle("active", isActive);
                    b.setAttribute("aria-selected", String(isActive));
                });
                applySegmentedTabFilter();
            });
        });
    }

    if (watchlistQuickSearchInput) {
        watchlistQuickSearchInput.addEventListener("input", (e) => {
            quickSearchQuery = e.target.value;
            visibleLimit = PAGE_SIZE;
            applySegmentedTabFilter();
        });
    }

    if (watchlistLoadMoreBtn) {
        watchlistLoadMoreBtn.addEventListener("click", () => {
            visibleLimit += PAGE_SIZE;
            applySegmentedTabFilter();
        });
    }

    // İlk yüklemede sayfalama sınırını uygula (400-500+ kart varsa ilk 36'yı göster)
    applySegmentedTabFilter();

    // =========================================================================
    // 5. Örnek İzleme Listesi Yükle (Seed) & Listeyi Sıfırla (Clear)
    // =========================================================================
    async function triggerSeedWatchlist() {
        // Misafir Modu: Sunucudaki hiçbir .json dosyasına yazmadan bellek içine yükle
        if (!isAuthenticated) {
            try {
                const res = await fetch("/api/watchlist/sample-template");
                if (!res.ok) return;
                const data = await res.json();
                guestWatchlist = data.items || [];
                updateCounters(guestWatchlist.length);
                syncDiscoverCardsWithGuestWatchlist();
                await refreshGuestRecommendationsPreview(true);
                showToast("⚡ Örnek veri geçici belleğe yüklendi! (Misafir Modu: F5'te sıfırlanır)");
            } catch (err) {
                console.error("Misafir örnek veri hatası:", err);
            }
            return;
        }

        // Oturum Açmış Kullanıcı: data/watchlists/<user_id>.json dosyasına kalıcı kaydet
        try {
            const res = await fetch("/api/watchlist/seed", {
                method: "POST",
                headers: { Accept: "application/json" },
            });
            if (res.ok) {
                showToast("⚡ Örnek izleme listesi hesabınıza kalıcı olarak yüklendi!");
                setTimeout(() => window.location.reload(), 400);
            }
        } catch (err) {
            console.error("Örnek veri yükleme hatası:", err);
        }
    }

    async function triggerClearWatchlist() {
        if (!isAuthenticated) {
            guestWatchlist = [];
            updateCounters(0);
            syncDiscoverCardsWithGuestWatchlist();
            await refreshGuestRecommendationsPreview(false);
            showToast("🗑️ Geçici misafir listesi sıfırlandı.");
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

    ["seedWatchlistBtn", "emptySeedWatchlistBtn", "seedFromRecsBtn", "emptySeedRecsBtn"].forEach((id) => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener("click", triggerSeedWatchlist);
    });

    if (clearWatchlistBtn) {
        clearWatchlistBtn.addEventListener("click", triggerClearWatchlist);
    }

    const scrollToGuestRecsBtn = document.getElementById("scrollToGuestRecsBtn");
    if (scrollToGuestRecsBtn) {
        scrollToGuestRecsBtn.addEventListener("click", async () => {
            if (guestWatchlist.length === 0) {
                await triggerSeedWatchlist();
            } else {
                await refreshGuestRecommendationsPreview(true);
            }
        });
    }

    // =========================================================================
    // 6. Keşfet & Ekle Canlı TMDB Arama
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
                    .slice(0, 3)
                    .map((g) => `<span class="genre-tag">${escapeHtml(g)}</span>`)
                    .join("");

                let ratingBtnsHtml = "";
                for (let r = 1; r <= 10; r++) {
                    const selectedCls = item.user_rating === r ? "selected" : "";
                    const toneCls = r < 5 ? "low-rate" : r >= 8 ? "high-rate" : "";
                    ratingBtnsHtml += `<button type="button" class="rate-num-btn ${selectedCls} ${toneCls}" data-rating="${r}" title="${r}/10 Puan Ver">${r}</button>`;
                }

                article.innerHTML = `
                    <div class="media-poster-wrap">
                        <span class="media-badge-type ${escapeHtml(item.media_type)}">
                            ${item.media_type === "tv" ? "DİZİ" : "FİLM"}
                        </span>
                        <span class="media-badge-year">${escapeHtml(String(item.release_year || ""))}</span>
                        <div class="watched-ribbon" ${item.in_watchlist ? "" : "hidden"}>
                            ✓ Listende: <strong class="user-rating-val">${item.user_rating || ""}</strong>/10
                        </div>
                        <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}" class="poster-link">
                            <img src="${escapeHtml(item.poster_path)}" alt="${escapeHtml(item.title)}" loading="lazy">
                        </a>
                    </div>
                    <div class="media-card-body">
                        <div class="media-meta-row">
                            <span class="tmdb-score">⭐ ${escapeHtml(String(item.vote_average))} <small>TMDB</small></span>
                            <div class="genre-tags">${genreTagsHtml}</div>
                        </div>
                        <h3 class="media-title">
                            <a href="/detail/${escapeHtml(item.media_type)}/${item.tmdb_id}">${escapeHtml(item.title)}</a>
                        </h3>
                        <p class="media-overview">${escapeHtml(item.overview || "")}</p>
                        <div class="quick-rate-box">
                            <div class="quick-rate-header">
                                <span class="rate-label">${item.in_watchlist ? "Puanını Güncelle (1-10):" : "Puan Ver & Listeye Ekle (1-10):"}</span>
                            </div>
                            <div class="rating-number-bar">${ratingBtnsHtml}</div>
                        </div>
                    </div>
                `;
                discoverGrid.appendChild(article);
            });

            bindMediaCardEvents(discoverGrid);
            syncDiscoverCardsWithGuestWatchlist();
            updateSegmentedCounts();
            applySegmentedTabFilter();
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
                if (navbarSearchInput) navbarSearchInput.value = discoverState.q;
                if (searchClearBtn) searchClearBtn.hidden = discoverState.q.length === 0;
                scheduleDiscoverSearch();
            });
        }

        if (navbarSearchInput) {
            navbarSearchInput.addEventListener("input", (e) => {
                discoverState.q = e.target.value;
                if (discoverSearchInput) discoverSearchInput.value = discoverState.q;
                if (searchClearBtn) searchClearBtn.hidden = discoverState.q.length === 0;
                scheduleDiscoverSearch();
            });
        }

        if (searchClearBtn) {
            searchClearBtn.addEventListener("click", () => {
                discoverState.q = "";
                if (navbarSearchInput) navbarSearchInput.value = "";
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
    // 7. Sinematik İçerik Detay Sayfası (/detail/<media_type>/<int:tmdb_id>) Mantığı
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

        let selectedRating = 8;
        const preSelected = ratingBar?.querySelector(".detail-rate-btn.selected");
        if (preSelected) {
            selectedRating = parseInt(preSelected.dataset.rating || "8", 10);
        }

        async function saveDetailRating(ratingToSave) {
            if (!isAuthenticated) {
                upsertGuestWatchlistItem({
                    tmdb_id: tmdbId,
                    media_type: mediaType,
                    title: title,
                    poster_path: posterPath,
                    user_rating: ratingToSave,
                    genres: genres,
                    keywords: keywords,
                });
                if (watchedRibbon) watchedRibbon.hidden = false;
                if (userRatingVal) userRatingVal.textContent = String(ratingToSave);
                if (saveBtn) saveBtn.textContent = "💾 Geçici Puanı Güncelle";
                if (removeBtn) removeBtn.hidden = false;
                if (ratePromptLabel) {
                    ratePromptLabel.innerHTML = `⚡ Geçici Listende (Puanın: <strong class="gold-text">${ratingToSave}/10</strong> • F5'te sıfırlanır):`;
                }
                showToast(`⚡ "${title}" (${ratingToSave}/10) geçici listeye eklendi (Misafir Modu: F5'te sıfırlanır)`);
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
                        user_rating: ratingToSave,
                        genres: genres,
                        keywords: keywords,
                    }),
                });
                if (!res.ok) return;
                const data = await res.json();

                if (watchedRibbon) watchedRibbon.hidden = false;
                if (userRatingVal) userRatingVal.textContent = String(ratingToSave);
                if (saveBtn) saveBtn.textContent = "💾 Puanı Güncelle";
                if (removeBtn) removeBtn.hidden = false;
                if (ratePromptLabel) {
                    ratePromptLabel.innerHTML = `✓ İzleme Listende (Mevcut Puanın: <strong class="gold-text">${ratingToSave}/10</strong>) — Puanı Güncelle:`;
                }
                if (data.stats) updateCounters(data.stats.total);
                showToast(`✓ "${title}" (${ratingToSave}/10) kalıcı izleme listene kaydedildi!`);
            } catch (err) {
                console.error("Detay sayfası kayıt hatası:", err);
            }
        }

        if (ratingBar) {
            ratingBar.querySelectorAll(".detail-rate-btn").forEach((btn) => {
                btn.addEventListener("click", () => {
                    selectedRating = parseInt(btn.dataset.rating || "8", 10);
                    ratingBar.querySelectorAll(".detail-rate-btn").forEach((b) => {
                        b.classList.toggle("selected", b === btn);
                    });
                    saveDetailRating(selectedRating);
                });
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener("click", () => saveDetailRating(selectedRating));
        }

        if (removeBtn) {
            removeBtn.addEventListener("click", async () => {
                if (!isAuthenticated) {
                    guestWatchlist = guestWatchlist.filter(
                        (x) => !(Number(x.tmdb_id) === tmdbId && x.media_type === mediaType)
                    );
                    updateCounters(guestWatchlist.length);
                    if (watchedRibbon) watchedRibbon.hidden = true;
                    if (saveBtn) saveBtn.textContent = "➕ İzleme Listeme Ekle";
                    removeBtn.hidden = true;
                    if (ratePromptLabel) {
                        ratePromptLabel.textContent = "Puan Seç (1-10) ve İzleme Listene Ekle:";
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
                    if (saveBtn) saveBtn.textContent = "➕ İzleme Listeme Ekle";
                    removeBtn.hidden = true;
                    if (ratePromptLabel) {
                        ratePromptLabel.textContent = "Puan Seç (1-10) ve İzleme Listene Ekle:";
                    }
                    if (data.stats) updateCounters(data.stats.total);
                    showToast(`🗑️ "${title}" kalıcı izleme listenden çıkarıldı.`);
                } catch (err) {
                    console.error("Detay sayfası silme hatası:", err);
                }
            });
        }

        // Resmi Fragman (YouTube Embed) Glassmorphism Modal
        const openTrailerBtn = document.getElementById("openTrailerModalBtn");
        const closeTrailerBtn = document.getElementById("closeTrailerModalBtn");
        const trailerModal = document.getElementById("trailerModal");
        const trailerIframe = document.getElementById("trailerYoutubeIframe");

        function openTrailerModal() {
            if (!trailerModal || !trailerIframe || !trailerKey) return;
            trailerIframe.src = `https://www.youtube.com/embed/${trailerKey}?autoplay=1&rel=0`;
            trailerModal.hidden = false;
        }

        function closeTrailerModal() {
            if (!trailerModal || !trailerIframe) return;
            trailerModal.hidden = true;
            trailerIframe.src = "";
        }

        if (openTrailerBtn) openTrailerBtn.addEventListener("click", openTrailerModal);
        if (closeTrailerBtn) closeTrailerBtn.addEventListener("click", closeTrailerModal);
        if (trailerModal) {
            trailerModal.addEventListener("click", (e) => {
                if (e.target === trailerModal) closeTrailerModal();
            });
        }
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && trailerModal && !trailerModal.hidden) {
                closeTrailerModal();
            }
        });
    }
});


// ============================================================================
// 8. Toplu Liste İçe Aktarma (Bulk Import - 500+ Yapım) Modal & İlerleme Çubuğu
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
    const bulkModal = document.getElementById("bulkImportModal");
    if (!bulkModal) return;

    const mainNavbar = document.getElementById("mainNavbar");
    const isAuthenticated = mainNavbar?.dataset.authenticated === "true";

    const openBtns = [
        document.getElementById("openBulkImportModalBtn"),
        document.getElementById("emptyOpenBulkImportBtn"),
    ].filter(Boolean);

    const closeBtn = document.getElementById("closeBulkImportModalBtn");
    const textarea = document.getElementById("bulkImportTextarea");
    const detectedBadge = document.getElementById("bulkDetectedCountBadge");
    const mediaTypeSelect = document.getElementById("bulkMediaTypeSelect");
    const defaultRatingSelect = document.getElementById("bulkDefaultRatingSelect");
    const startBtn = document.getElementById("startBulkImportBtn");
    const reloadBtn = document.getElementById("finishBulkImportReloadBtn");

    const progressContainer = document.getElementById("bulkProgressContainer");
    const progressStatusText = document.getElementById("bulkProgressStatusText");
    const progressPercentText = document.getElementById("bulkProgressPercentText");
    const progressFill = document.getElementById("bulkProgressFill");

    const summaryBox = document.getElementById("bulkSummaryReportBox");
    const reportAddedCount = document.getElementById("reportAddedCount");
    const reportSkippedCount = document.getElementById("reportSkippedCount");
    const reportNotFoundCount = document.getElementById("reportNotFoundCount");

    // Satır başı numaralarını (1-, 24., #12, • vb.) temizleyen istemci ayrıştırıcı
    function cleanLineClient(rawLine) {
        if (!rawLine) return "";
        return rawLine
            .replace(/^\s*(?:[#•\-\*\+]+|\d+\s*[\-\.\)\:\]\–\—]+|\[\d+\]\s*)+\s*/u, "")
            .replace(/\s*\((19\d{2}|20\d{2})\)\s*$/, "")
            .trim();
    }

    function getParsedLines() {
        if (!textarea) return [];
        return textarea.value
            .split(/\r?\n/)
            .map(cleanLineClient)
            .filter((line) => line.length >= 2);
    }

    function updateDetectedCount() {
        const lines = getParsedLines();
        if (detectedBadge) {
            detectedBadge.textContent = `${lines.length} başlık algılandı`;
        }
    }

    if (textarea) {
        textarea.addEventListener("input", updateDetectedCount);
    }

    function openBulkModal() {
        bulkModal.hidden = false;
        updateDetectedCount();
        textarea?.focus();
    }

    function closeBulkModal() {
        bulkModal.hidden = true;
    }

    openBtns.forEach((btn) => btn.addEventListener("click", openBulkModal));
    if (closeBtn) closeBtn.addEventListener("click", closeBulkModal);

    bulkModal.addEventListener("click", (e) => {
        if (e.target === bulkModal) closeBulkModal();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !bulkModal.hidden) closeBulkModal();
    });

    if (startBtn) {
        startBtn.addEventListener("click", async () => {
            const allLines = getParsedLines();
            if (allLines.length === 0) {
                textarea?.focus();
                return;
            }

            const totalLines = allLines.length;
            const mediaType = mediaTypeSelect ? mediaTypeSelect.value : "auto";
            const defaultRating = defaultRatingSelect ? parseInt(defaultRatingSelect.value, 10) : 8;

            startBtn.disabled = true;
            startBtn.textContent = "⏳ İşleniyor...";
            if (reloadBtn) reloadBtn.hidden = true;
            if (summaryBox) summaryBox.hidden = true;
            if (progressContainer) progressContainer.hidden = false;

            const CHUNK_SIZE = 25;
            let processedCount = 0;
            let totalAdded = 0;
            let totalSkipped = 0;
            let totalNotFound = 0;
            const seenClientKeys = new Set();

            for (let i = 0; i < totalLines; i += CHUNK_SIZE) {
                const chunk = allLines.slice(i, i + CHUNK_SIZE);
                const currentEnd = Math.min(i + chunk.length, totalLines);

                if (progressStatusText) {
                    progressStatusText.textContent = `${currentEnd} / ${totalLines} işleniyor...`;
                }
                const pct = Math.round((currentEnd / totalLines) * 100);
                if (progressPercentText) progressPercentText.textContent = `%${pct}`;
                if (progressFill) progressFill.style.width = `${pct}%`;

                try {
                    const res = await fetch("/api/watchlist/bulk-import", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            lines: chunk,
                            media_type: mediaType,
                            default_rating: defaultRating,
                            existing_keys: Array.from(seenClientKeys),
                        }),
                    });

                    if (res.ok) {
                        const data = await res.json();
                        totalAdded += Number(data.added_count || 0);
                        totalSkipped += Number(data.skipped_count || 0);
                        totalNotFound += Number(data.not_found_count || 0);

                        (data.added_items || []).forEach((item) => {
                            seenClientKeys.add(`${item.media_type}_${item.tmdb_id}`);
                            seenClientKeys.add(String(item.title || "").toLowerCase());
                        });
                    }
                } catch (err) {
                    console.error("Bulk chunk hatası:", err);
                }

                processedCount = currentEnd;
            }

            if (progressStatusText) {
                progressStatusText.textContent = `${totalLines} / ${totalLines} tamamlandı!`;
            }
            if (progressPercentText) progressPercentText.textContent = "%100";
            if (progressFill) progressFill.style.width = "100%";

            if (reportAddedCount) reportAddedCount.textContent = String(totalAdded);
            if (reportSkippedCount) reportSkippedCount.textContent = String(totalSkipped);
            if (reportNotFoundCount) reportNotFoundCount.textContent = String(totalNotFound);
            if (summaryBox) summaryBox.hidden = false;

            startBtn.disabled = false;
            startBtn.textContent = "🚀 Toplu Aktarımı Başlat";

            if (reloadBtn) {
                reloadBtn.hidden = false;
                reloadBtn.onclick = () => {
                    if (isAuthenticated) {
                        window.location.reload();
                    } else {
                        closeBulkModal();
                    }
                };
            }
        });
    }
});
