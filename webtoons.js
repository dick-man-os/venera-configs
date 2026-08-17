/**
 * @file en_webtoons.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.all.webtoons
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.4.57
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class EnWebtoonsSource extends ComicSource {
    name = "Webtoons"
    key = "en_webtoons"
    version = "1.0.0"
    minAppVersion = "1.6.0"

    static baseUrl = "https://www.webtoons.com"
    static mobileUrl = "https://m.webtoons.com"

    static headers = {
        "Referer": "https://www.webtoons.com/",
    }

    init() {
        Network.setCookies(EnWebtoonsSource.baseUrl, [
            new Cookie({ name: "ageGatePass", value: "true", domain: "webtoons.com" }),
            new Cookie({ name: "locale", value: "en", domain: "webtoons.com" }),
            new Cookie({ name: "needGDPR", value: "false", domain: "webtoons.com" }),
        ]);
    }

    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                let res = await Network.get(`${EnWebtoonsSource.baseUrl}/en/ranking/trending`, EnWebtoonsSource.headers);
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
                let res = await Network.get(`${EnWebtoonsSource.baseUrl}/en/originals/${day}?sortOrder=UPDATE`, EnWebtoonsSource.headers);
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
            let url = `${EnWebtoonsSource.baseUrl}/en/search?keyword=${encodeURIComponent(keyword)}&page=${page}`;
            let res = await Network.get(url, EnWebtoonsSource.headers);
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
            let url = id.startsWith("http") ? id : `${EnWebtoonsSource.baseUrl}${id}`;
            let res = await Network.get(url, EnWebtoonsSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector("h1.subj, h3.subj");
            let authorEl = doc.querySelector(".author:nth-of-type(1)") || doc.querySelector(".author_area");
            let descEl = doc.querySelector("#_asideDetail p.summary");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = (doc.querySelector('.detail_header .thmb img') ? (doc.querySelector('.detail_header .thmb img').attributes['src'] || '') : '');
            doc.dispose();

            let chapters = await this.loadChapters(id);

            return new ComicDetails({
                title: title,
                subtitle: author,
                subTitle: author,
                cover: cover,
                description: description,
                chapters: chapters,
            });
        },

        loadEp: async (comicId, epId) => {
            let url = epId.startsWith("http") ? epId : `${EnWebtoonsSource.baseUrl}${epId}`;
            let res = await Network.get(url, EnWebtoonsSource.headers);
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
                ...EnWebtoonsSource.headers,
                "Referer": `${EnWebtoonsSource.baseUrl}/`,
            },
        }),

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...EnWebtoonsSource.headers,
                "Referer": `${EnWebtoonsSource.baseUrl}/`,
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
     * Custom page processing hook (preserves standard images by default)
     */
    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
}
