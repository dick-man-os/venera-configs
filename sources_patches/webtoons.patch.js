    // =========================================================================
    // Patched Implementation (Webtoons-specific Chapter & Page Logic)
    // =========================================================================

    /**
     * Load and parse chapters using Webtoons mobile JSON API
     */
    loadChapters = async (comicUrl) => {
        let matchTitleNo = comicUrl.match(/[?&]title_?no=(\d+)/i);
        let titleId = matchTitleNo ? matchTitleNo[1] : null;
        if (!titleId) {
            throw new Error(`Could not extract title_no from URL: ${comicUrl}`);
        }

        let type = (comicUrl.includes("/canvas/") || comicUrl.includes("/challenge/")) ? "canvas" : "webtoon";
        let apiUrl = `${EnWebtoonsSource.mobileUrl}/api/v1/${type}/${titleId}/episodes?pageSize=99999`;
        if (type === "canvas") {
            apiUrl += "&readingLanguageCode=en";
        }

        let res = await Network.get(apiUrl, EnWebtoonsSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load episodes from API, status: ${res.status}`);
        }

        let data = JSON.parse(res.body);
        let rawEpisodes = (data.result && data.result.episodeList) ? data.result.episodeList : [];

        // Regex for episode number & season extraction:
        // Group 1: season number
        // Group 3: mini/bonus/special
        // Group 4: episode/chapter number
        const episodeNoRegex = /(?:(?:s(?:eason)?|saison|part|vol(?:ume)?)\s*\.?\s*(\d+).*?)?(.*?(mini|bonus|special).*?)?(?:e(?:p(?:isode)?)?|ch(?:apter)?)\s*\.?\s*(\d+(?:\.\d+)?)/i;

        let recognized = 0;
        let unrecognized = 0;

        let episodes = rawEpisodes.map(ep => {
            let episodeTitle = ep.episodeTitle || "";
            let match = episodeTitle.match(episodeNoRegex);
            let chapterNumber = -1;
            let seasonNumber = 1;

            if (match && !match[3]) { // not a mini/bonus/special episode
                if (match[4]) {
                    chapterNumber = parseFloat(match[4]);
                }
                if (match[1]) {
                    seasonNumber = parseInt(match[1], 10);
                }
            }

            if (chapterNumber === -1) {
                unrecognized++;
            } else {
                recognized++;
            }

            return {
                episodeTitle: episodeTitle,
                viewerLink: ep.viewerLink || "",
                exposureDateMillis: ep.exposureDateMillis || 0,
                hasBgm: !!ep.hasBgm,
                chapterNumber: chapterNumber,
                seasonNumber: seasonNumber,
            };
        });

        if (unrecognized > recognized) {
            episodes.forEach((ep, idx) => {
                ep.chapterNumber = idx + 1;
            });
        } else {
            let maxChapterNumber = 0;
            let currentSeason = 1;
            let seasonOffset = 0;

            episodes.forEach((ep, idx) => {
                if (ep.chapterNumber !== -1) {
                    let originalNumber = ep.chapterNumber;
                    if (ep.seasonNumber > currentSeason) {
                        currentSeason = ep.seasonNumber;
                        if (originalNumber <= maxChapterNumber) {
                            seasonOffset = maxChapterNumber;
                        }
                    }
                    ep.chapterNumber = seasonOffset + originalNumber;
                    maxChapterNumber = Math.max(maxChapterNumber, ep.chapterNumber);
                } else {
                    let prev = idx > 0 ? episodes[idx - 1] : null;
                    if (!prev) {
                        ep.chapterNumber = 0;
                    } else {
                        ep.chapterNumber = prev.chapterNumber + 0.01;
                    }
                }
            });
        }

        let chaptersMap = new Map();
        // Insert episodes in reverse order (latest first) to match upstream Webtoons conventions
        for (let i = episodes.length - 1; i >= 0; i--) {
            let ep = episodes[i];
            let chNumberStr = Number.isInteger(ep.chapterNumber)
                ? ep.chapterNumber.toString()
                : ep.chapterNumber.toFixed(2).replace(/\.?0+$/, "");
            let title = `${ep.episodeTitle} (ch. ${chNumberStr})${ep.hasBgm ? " ♫" : ""}`;
            chaptersMap.set(ep.viewerLink, title);
        }

        return chaptersMap;
    }

    /**
     * Clean up contaminated author info
     */
    parseDetailsCustom = (comicDetails, htmlDoc) => {
        if (comicDetails.subtitle) {
            let clean = comicDetails.subtitle
                .replace(/author info/gi, "")
                .replace(/\.\.\./g, "")
                .trim();
            // preserve multiple genuine creators if they are separated by newlines or tabs
            clean = clean.split(/[\n\t]+/).map(s => s.trim()).filter(s => s !== "").join(", ");
            comicDetails.subtitle = clean;
            comicDetails.subTitle = clean;
        }
        return comicDetails;
    }

    /**
     * Custom page processing hook (preserves standard images by default)
     */
    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
