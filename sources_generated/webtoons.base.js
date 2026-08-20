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
    version = "1.0.1"
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
    // Patch Hooks / Boundaries
    // =========================================================================

    /**
     * [MANUAL PATCH HOOK] Load and parse chapters
     * Upstream Webtoons uses mobile JSON API: {{mobileUrl}}/api/v1/webtoon/{{titleId}}/episodes?pageSize=99999
     * Manual patch is required for episode title parsing, season numbering, and offsets.
     */
    loadChapters = async (comicUrl) => {
        return this.parseChaptersCustom(comicUrl);
    }

    /**
     * Placeholder hook to be overridden by manual patch layer for Details.
     */
    parseDetailsCustom = (comicDetails, htmlDoc) => {
        throw new Error('MANUAL PATCH REQUIRED: parseDetailsCustom must be implemented in patch layer.');
    }

    /**
     * Placeholder hook to be overridden by manual patch layer.
     */
    parseChaptersCustom = async (comicUrl) => {
        throw new Error("MANUAL PATCH REQUIRED: parseChaptersCustom must be implemented in patch layer.");
    }

    /**
     * Placeholder hook for special page variants (e.g. MotionToon).
     */
    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
}
