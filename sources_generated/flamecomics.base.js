/**
 * @file en_flamecomics.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.en.flamecomics
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.4.50
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class EnFlamecomicsSource extends ComicSource {
    name = "Flame Comics"
    key = "en_flamecomics"
    version = "1.0.1"
    minAppVersion = "1.6.0"

    static baseUrl = "https://flamecomics.xyz"
    static mobileUrl = "https://m.webtoons.com"

    static headers = {

    }

    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                return await this.loadPopularCustom(page);
            }
        },
        {
            title: "Latest",
            type: "multiPageComicList",
            load: async (page) => {
                return await this.loadLatestCustom(page);
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
            let url = id.startsWith("http") ? id : `${EnFlamecomicsSource.baseUrl}${id}`;
            let res = await Network.get(url, EnFlamecomicsSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector("h1.subj, h3.subj");
            let authorEl = doc.querySelector(".author") || doc.querySelector(".author_area");
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
            return await this.loadEpCustom(comicId, epId);
        },

        onImageLoad: (url, comicId, epId) => ({
            url: url,
            headers: {
                ...EnFlamecomicsSource.headers,
                "Referer": `${EnFlamecomicsSource.baseUrl}/`,
            },
        }),

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...EnFlamecomicsSource.headers,
                "Referer": `${EnFlamecomicsSource.baseUrl}/`,
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
     * Placeholder hook to be overridden by manual patch layer for Explore Popular.
     */
    loadPopularCustom = async (page) => {
        throw new Error("MANUAL PATCH REQUIRED: loadPopularCustom must be implemented in patch layer.");
    }
    /**
     * Placeholder hook to be overridden by manual patch layer for Explore Latest.
     */
    loadLatestCustom = async (page) => {
        throw new Error("MANUAL PATCH REQUIRED: loadLatestCustom must be implemented in patch layer.");
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
     * Placeholder hook for special page variants (e.g. MotionToon).
     */
    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
}
