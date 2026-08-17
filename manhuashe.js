/**
 * @file zh-Hans_manhuashe.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.zh.manhuashe
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.0
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class ZhhansManhuasheSource extends ComicSource {
    name = "Manhuashe"
    key = "zh_Hans_manhuashe"
    version = "1.0.0"
    minAppVersion = "1.6.0"
    get baseUrl() {
        let m = this.loadSetting('baseUrlSelection');
        return m ? m : "https://www.311s.com";
    }

    static mobileUrl = "https://m.webtoons.com"

    static headers = {

    }
    settings = {
        baseUrlSelection: {
            title: "Preferred Mirror",
            type: "select",
            options: [
                { value: "https://www.311s.com", text: "www.311s.com" },
                { value: "https://www.m206.com", text: "www.m206.com" }
            ],
            default: "https://www.311s.com"
        }
    }


    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                let res = await Network.get(`${this.baseUrl}/category/order/hits/page/{{page}}`, ZhhansManhuasheSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load popular comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll("div.comic-list > div.comic-item");
                let comics = elements.map(el => new Comic({
                    id: (el.querySelector('a') ? (el.querySelector('a').attributes['href'] || '') : ''),
                    title: (el.querySelector('h3 a') ? el.querySelector('h3 a').text : ''),
                    cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
                }));
                let nextEl = doc.querySelector("div.pagination > a.next");
                let currEl = doc.querySelector("div.pagination > a.on");
                let hasNext = nextEl && currEl && nextEl.attributes["href"] !== currEl.attributes["href"];
                let outMaxPage = hasNext ? page + 1 : page;
                doc.dispose();
                return {
                    comics: comics,
                    maxPage: outMaxPage,
                };
            }
        },
        {
            title: "Latest",
            type: "multiPageComicList",
            load: async (page) => {
                let res = await Network.get(`${this.baseUrl}/category/order/addtime/page/{{page}}`, ZhhansManhuasheSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load latest comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll("div.comic-list > div.comic-item");
                let comics = elements.map(el => new Comic({
                    id: (el.querySelector('a') ? (el.querySelector('a').attributes['href'] || '') : ''),
                    title: (el.querySelector('h3 a') ? el.querySelector('h3 a').text : ''),
                    cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
                }));
                let nextEl = doc.querySelector("div.pagination > a.next");
                let currEl = doc.querySelector("div.pagination > a.on");
                let hasNext = nextEl && currEl && nextEl.attributes["href"] !== currEl.attributes["href"];
                let outMaxPage = hasNext ? page + 1 : page;
                doc.dispose();
                return {
                    comics: comics,
                    maxPage: outMaxPage,
                };
            }
        }
    ]

    // Search
    search = {
        load: async (keyword, options, page) => {
            let url = `${this.baseUrl}/search/${encodeURIComponent(keyword)}/${page}`;
            let res = await Network.get(url, ZhhansManhuasheSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load search results, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let elements = doc.querySelectorAll("div.comic-list > div.comic-item");
            let comics = elements.map(el => new Comic({
                id: (el.querySelector('a') ? (el.querySelector('a').attributes['href'] || '') : ''),
                title: (el.querySelector('h3 a') ? el.querySelector('h3 a').text : ''),
                cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
            }));
            let nextEl = doc.querySelector("div.pagination > a.next");
            let currEl = doc.querySelector("div.pagination > a.on");
            let hasNext = nextEl && currEl && nextEl.attributes["href"] !== currEl.attributes["href"];
            let outMaxPage = hasNext ? page + 1 : page;
            doc.dispose();
            return {
                comics: comics,
                maxPage: outMaxPage,
            };
        }
    }

    // Comic Details and Reader Loading
    comic = {
        loadInfo: async (id) => {
            let url = id.startsWith("http") ? id : `${this.baseUrl}${id}`;
            let res = await Network.get(url, ZhhansManhuasheSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector("div.comic-meta-info > h1");
            let authorEl = doc.querySelector(".author") || doc.querySelector(".author_area");
            let descEl = doc.querySelector("div.comic-description > p");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = (doc.querySelector('div.comic-cover-large > img') ? (doc.querySelector('div.comic-cover-large > img').attributes['src'] || '') : '');


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
            let url = epId.startsWith("http") ? epId : `${this.baseUrl}${epId}`;
            let res = await Network.get(url, ZhhansManhuasheSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load episode, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let imgElements = doc.querySelectorAll("div.comic-content > img");
            let images = imgElements.map(el => el.attributes["src"]).filter(Boolean);
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
                ...ZhhansManhuasheSource.headers,
                "Referer": `${this.baseUrl}/`,
            },
        }),

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...ZhhansManhuasheSource.headers,
                "Referer": `${this.baseUrl}/`,
            },
        }),
    }

    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    loadChapters = async (comicUrl) => {
        let url = comicUrl.startsWith("http") ? comicUrl : `${this.baseUrl}${comicUrl}`;
        let res = await Network.get(url, ZhhansManhuasheSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load chapters, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("#chapter-list > div.chapter-item > a");

        let chaptersList = elements.map(el => ({
            id: (el.attributes['href'] || ''),
            title: (el.text || ''),
        }));
        chaptersList.reverse();

        let chaptersObj = {};
        for (let ch of chaptersList) {
            if (ch.id) {
                chaptersObj[ch.id] = ch.title || "";
            }
        }
        doc.dispose();

        // Hook for custom chapter parsing
        return this.parseChaptersCustom(chaptersObj, res.body);
    }

    parseDetailsCustom = (comicDetails, htmlDoc) => {
        // Author extraction using :contains(作者：)
        let statsEls = htmlDoc.querySelectorAll("div.comic-stats > div.stat-item");
        for (let el of statsEls) {
            let text = el.text || "";
            if (text.includes("作者：")) {
                let author = text.replace("作者：", "").trim();
                comicDetails.subtitle = author;
                comicDetails.subTitle = author;
                break;
            }
        }

        // Status and Genre extraction
        let tagsEls = htmlDoc.querySelectorAll("div.comic-meta-info > div.comic-tags > span");
        if (tagsEls.length > 0) {
            let lastTag = tagsEls[tagsEls.length - 1].text.trim();
            if (lastTag === "连载" || lastTag === "连载中") {
                comicDetails.status = 1; // ONGOING
            } else if (lastTag === "完结" || lastTag === "已完结") {
                comicDetails.status = 2; // COMPLETED
            } else {
                comicDetails.status = 0; // UNKNOWN
            }

            let genres = [];
            for (let el of tagsEls) {
                if (el.text) {
                    genres.push(el.text.trim());
                }
            }
            if (genres.length > 0) {
                comicDetails.tags = comicDetails.tags || {};
                comicDetails.tags["Tags"] = genres;
            }
        }

        return comicDetails;
    }

    parseChaptersCustom = (chaptersObj, htmlBody) => {
        return chaptersObj;
    }

    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
}
