/**
 * @file zh-Hant_webtoons.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.all.webtoons
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.4.57
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class ZhhantWebtoonsSource extends ComicSource {
    name = "Webtoons 繁體中文"
    key = "zh_Hant_webtoons"
    version = "1.0.1"
    minAppVersion = "1.6.0"

    static baseUrl = "https://www.webtoons.com"
    static mobileUrl = "https://m.webtoons.com"

    static headers = {
        "Referer": "https://www.webtoons.com/",
    }

    init() {
        Network.setCookies(ZhhantWebtoonsSource.baseUrl, [
            new Cookie({ name: "ageGatePass", value: "true", domain: "webtoons.com" }),
            new Cookie({ name: "locale", value: "zh_TW", domain: "webtoons.com" }),
            new Cookie({ name: "needGDPR", value: "false", domain: "webtoons.com" }),
        ]);
    }

    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                let res = await Network.get(`${ZhhantWebtoonsSource.baseUrl}/zh-hant/ranking/trending`, ZhhantWebtoonsSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load popular comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll(".webtoon_list li a");
                let comics = elements.map(el => new Comic({
                    id: (el.attributes['href'] || ''),
                    title: (el.querySelector('.title') ? el.querySelector('.title').text : ''),
                    cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
                }));
                doc.dispose();
                return {
                    comics: comics,
                    maxPage: 1,
                };
            }
        },
        {
            title: "Latest",
            type: "multiPageComicList",
            load: async (page) => {
                let days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
                let day = days[new Date().getDay()];
                let res = await Network.get(`${ZhhantWebtoonsSource.baseUrl}/zh-hant/originals/${day}?sortOrder=UPDATE`, ZhhantWebtoonsSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load latest comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll(".webtoon_list li a");
                let comics = elements.map(el => new Comic({
                    id: (el.attributes['href'] || ''),
                    title: (el.querySelector('.title') ? el.querySelector('.title').text : ''),
                    cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
                }));
                doc.dispose();
                return {
                    comics: comics,
                    maxPage: 1,
                };
            }
        }
    ]

    // Search
    search = {
        load: async (keyword, options, page) => {
            let url = `${ZhhantWebtoonsSource.baseUrl}/zh-hant/search?keyword=${encodeURIComponent(keyword)}&page=${page}`;
            let res = await Network.get(url, ZhhantWebtoonsSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load search results, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let elements = doc.querySelectorAll(".webtoon_list li a");
            let comics = elements.map(el => new Comic({
                id: (el.attributes['href'] || ''),
                title: (el.querySelector('.title') ? el.querySelector('.title').text : ''),
                cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
            }));
            doc.dispose();
            return {
                comics: comics,
                maxPage: 100,
            };
        }
    }

    // Comic Details and Reader Loading
    comic = {
        loadInfo: async (id) => {
            let url = id.startsWith("http") ? id : `${ZhhantWebtoonsSource.baseUrl}${id}`;
            let res = await Network.get(url, ZhhantWebtoonsSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector("h1.subj, h3.subj");
            let authorEl = doc.querySelector(".author, .author_area") || doc.querySelector(".author_area");
            let descEl = doc.querySelector("#_asideDetail p.summary");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = (doc.querySelector('.detail_header .thmb img') ? (doc.querySelector('.detail_header .thmb img').attributes['src'] || '') : '');


            let chapters = await this.loadChapters(id);

            let comicDetails = new ComicDetails({
                title: title,
                subtitle: author,
                subTitle: author,
                cover: cover,
                description: description,
                tags: {},
                chapters: chapters,
            });

            comicDetails = this.parseDetailsCustom(comicDetails, doc);
            doc.dispose();
            return comicDetails;
        },

        loadEp: async (comicId, epId) => {
            let url = epId.startsWith("http") ? epId : `${ZhhantWebtoonsSource.baseUrl}${epId}`;
            let res = await Network.get(url, ZhhantWebtoonsSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load episode, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let imgElements = doc.querySelectorAll("div#_imageList > img");
            let images = imgElements.map(el => el.attributes["data-url"]).filter(Boolean);
            doc.dispose();

            // Hook for custom page transformations (e.g. MotionToon / AuthorNotes)
            images = this.parsePagesCustom(images, res.body);

            return {
                images: images,
            };
        },

        onImageLoad: (url, comicId, epId) => ({
            url: url,
            headers: {
                ...ZhhantWebtoonsSource.headers,
                "Referer": `${ZhhantWebtoonsSource.baseUrl}/`,
            },
        }),

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...ZhhantWebtoonsSource.headers,
                "Referer": `${ZhhantWebtoonsSource.baseUrl}/`,
            },
        }),
    }

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
        let apiUrl = `${ZhhantWebtoonsSource.mobileUrl}/api/v1/${type}/${titleId}/episodes?pageSize=200`;
        if (type === "canvas") apiUrl += "&readingLanguageCode=zh-hant";
        const rawEpisodes = [], seen = new Set();
        let cursor = 0, ended = false;
        for (let pass = 0; pass < 1000; pass++) {
            const url = apiUrl + (cursor ? `&cursor=${cursor}` : "");
            const res = await Network.get(url, ZhhantWebtoonsSource.headers);
            if (res.status !== 200) throw new Error(`Failed to load episodes, status: ${res.status}`);
            const data = JSON.parse(res.body), result = data?.result;
            if (data.success === false || !Array.isArray(result?.episodeList))
                throw new Error("Invalid Webtoons episode response");
            const next = result.nextCursor;
            if (!Number.isSafeInteger(next) || next < 0)
                throw new Error("Missing or invalid Webtoons cursor");
            const before = seen.size;
            for (const ep of result.episodeList) {
                if (typeof ep?.viewerLink !== "string" || !ep.viewerLink.trim())
                    throw new Error("Missing Webtoons chapter identity");
                if (seen.has(ep.viewerLink)) continue;
                seen.add(ep.viewerLink);
                rawEpisodes.push(ep);
            }
            if ((cursor || next) && seen.size === before)
                throw new Error("Non-progressing Webtoons chapter page");
            if (next === 0) { ended = true; break; }
            if (next <= cursor) throw new Error("Non-progressing Webtoons cursor");
            cursor = next;
        }
        if (!ended) throw new Error("Incomplete Webtoons chapter pagination");

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
        // The API is chronological. Preserve complete, deduplicated reader order.
        for (let i = 0; i < episodes.length; i++) {
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

    // The combined search route is a preview and ignores page. Search each
    // provider-owned result type, with its advertised 30-slot page count.
    search = {
        load: async (keyword, options, page) => {
            if (!Number.isSafeInteger(page) || page < 1) throw new Error("Invalid search page");
            const comics = [], seen = new Set();
            let maxPage = 1;
            for (const type of ["originals", "canvas"]) {
                const url = `${ZhhantWebtoonsSource.baseUrl}/zh-hant/search/${type}?keyword=${encodeURIComponent(keyword)}&page=${page}`;
                const res = await Network.get(url, ZhhantWebtoonsSource.headers);
                if (res.status !== 200) throw new Error(`Failed to search Webtoons, status: ${res.status}`);
                const doc = new HtmlDocument(res.body);
                try {
                    const elements = doc.querySelectorAll(".webtoon_list li a");
                    const text = (doc.querySelector(".series_count .number")?.text || "").replace(/,/g, "").trim();
                    if (!/^\d+$/.test(text) && elements.length) throw new Error("Missing Webtoons search count");
                    const total = text ? Number(text) : 0;
                    if (!Number.isSafeInteger(total) || total < 0) throw new Error("Invalid Webtoons search count");
                    const last = Math.max(1, Math.ceil(total / 30));
                    maxPage = Math.max(maxPage, last);
                    if (page > last) continue;
                    for (const el of elements) {
                        const id = el.attributes.href || "";
                        if (!id || seen.has(id)) continue;
                        seen.add(id);
                        comics.push(new Comic({id, title: el.querySelector(".title")?.text || "",
                            cover: el.querySelector("img")?.attributes.src || ""}));
                    }
                } finally { doc.dispose(); }
            }
            return {comics, maxPage};
        }
    }
}
