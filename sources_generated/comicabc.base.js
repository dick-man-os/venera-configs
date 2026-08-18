/**
 * @file zh-Hant_comicabc.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.zh.comicabc
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.0
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class ZhhantComicabcSource extends ComicSource {
    name = "Comicabc"
    key = "zh_Hant_comicabc"
    version = "1.0.1"
    minAppVersion = "1.6.0"

    static baseUrl = "https://www.8comic.com"
    static mobileUrl = "https://m.webtoons.com"

    static headers = {

    }

    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                let res = await Network.get(`${ZhhantComicabcSource.baseUrl}/comic/h-{{page}}.html`, ZhhantComicabcSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load popular comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll(".container .row a.comicpic_col6");
                let comics = elements.map(el => new Comic({
                    id: (el.attributes['href'] || ''),
                    title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
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
                let res = await Network.get(`${ZhhantComicabcSource.baseUrl}/comic/u-{{page}}.html`, ZhhantComicabcSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load latest comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll(".container .row .cat2_list a");
                let comics = elements.map(el => new Comic({
                    id: (el.attributes['href'] || ''),
                    title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
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
            return await this.loadSearchCustom(keyword, options, page);
        }
    }

    // Comic Details and Reader Loading
    comic = {
        loadInfo: async (id) => {
            let url = id.startsWith("http") ? id : `${ZhhantComicabcSource.baseUrl}${id}`;
            let res = await Network.get(url, ZhhantComicabcSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector(".item_content_box .h2");
            let authorEl = doc.querySelector(".author") || doc.querySelector(".author_area");
            let descEl = doc.querySelector(".item_content_box .item_info_detail");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = (doc.querySelector('.item-cover img') ? (doc.querySelector('.item-cover img').attributes['src'] || '') : '');


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
            return await this.loadEpCustom(comicId, epId);
        },

        onImageLoad: (url, comicId, epId) => {
            if (this.onImageLoadCustom) {
                return this.onImageLoadCustom(url, comicId, epId);
            }
            return {
                url: url,
                headers: {
                    ...ZhhantComicabcSource.headers,
                    "Referer": `${ZhhantComicabcSource.baseUrl}/`,
                },
            };
        },

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...ZhhantComicabcSource.headers,
                "Referer": `${ZhhantComicabcSource.baseUrl}/`,
            },
        }),
    }

    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    /**
     * [MANUAL PATCH HOOK] Load and parse chapters
     * Upstream Webtoons uses mobile JSON API:
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
     * Placeholder hook to be overridden by manual patch layer for Search.
     */
    loadSearchCustom = async (keyword, options, page) => {
        throw new Error("MANUAL PATCH REQUIRED: loadSearchCustom must be implemented in patch layer.");
    }    /**
     * Placeholder hook to be overridden by manual patch layer.
     */
    parseChaptersCustom = async (comicUrl) => {
        throw new Error("MANUAL PATCH REQUIRED: parseChaptersCustom must be implemented in patch layer.");
    }
    /**
     * Placeholder hook to be overridden by manual patch layer for Pages.
     */
    loadEpCustom = async (comicId, epId) => {
        throw new Error("MANUAL PATCH REQUIRED: loadEpCustom must be implemented in patch layer.");
    }
    /**
     * Placeholder hook to be overridden by manual patch layer for Image Load.
     */
    onImageLoadCustom = (url, comicId, epId) => {
        throw new Error("MANUAL PATCH REQUIRED: onImageLoadCustom must be implemented in patch layer.");
    }

    /**
     * Placeholder hook for special page variants (e.g. MotionToon).
     */
    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
}
