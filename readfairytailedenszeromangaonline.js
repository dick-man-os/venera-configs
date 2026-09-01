/**
 * @file en_readfairytailedenszeromangaonline.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.en.readfairytailedenszeromangaonline
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.4.9
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class EnReadfairytailedenszeromangaonlineSource extends ComicSource {
    name = "Read Fairy Tail & Edens Zero Manga Online"
    key = "en_readfairytailedenszeromangaonline"
    version = "1.0.1"
    minAppVersion = "1.6.0"

    static baseUrl = "https://ww8.readfairytail.com"
    static mobileUrl = "https://m.webtoons.com"

    static headers = {

    }

    static resolveAbsoluteUrl = (rawValue, requestUrl) => {
        if (rawValue === null || rawValue === undefined || rawValue === "") {
            return "";
        }

        let raw = String(rawValue);
        if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(raw)) {
            return raw;
        }

        let baseMatch = String(requestUrl || "").match(/^([A-Za-z][A-Za-z0-9+.-]*:)\/\/([^/?#]+)([^?#]*)(\?[^#]*)?(?:#.*)?$/);
        if (!baseMatch) {
            return raw;
        }

        let origin = baseMatch[1] + "//" + baseMatch[2];
        let basePath = baseMatch[3] || "/";
        let baseQuery = baseMatch[4] || "";

        if (raw.startsWith("//")) {
            return baseMatch[1] + raw;
        }
        if (raw.startsWith("#")) {
            return origin + basePath + baseQuery + raw;
        }
        if (raw.startsWith("?")) {
            return origin + basePath + raw;
        }

        let suffixAt = raw.search(/[?#]/);
        let suffix = suffixAt === -1 ? "" : raw.slice(suffixAt);
        let rawPath = suffixAt === -1 ? raw : raw.slice(0, suffixAt);
        let path = rawPath.startsWith("/")
            ? rawPath
            : basePath.slice(0, basePath.lastIndexOf("/") + 1) + rawPath;
        let trailingSlash = path.endsWith("/") || path.endsWith("/.") || path.endsWith("/..");
        let segments = [];
        for (let segment of path.split("/")) {
            if (!segment || segment === ".") {
                continue;
            }
            if (segment === "..") {
                segments.pop();
            } else {
                segments.push(segment);
            }
        }

        let normalizedPath = "/" + segments.join("/");
        if (trailingSlash && normalizedPath !== "/") {
            normalizedPath += "/";
        }
        return origin + normalizedPath + suffix;
    }
    // Static Catalog Array
    staticCatalog = [
        {
                "title": "Eden's Zero",
                "url": "https://ww8.readfairytail.com/manga/edens-zero/"
        },
        {
                "title": "Fairy Tail",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail/"
        },
        {
                "title": "FT Zero",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-zero/"
        },
        {
                "title": "FT City Hero",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-city-hero/"
        },
        {
                "title": "Hero’s",
                "url": "https://ww8.readfairytail.com/manga/heros/"
        },
        {
                "title": "FT Happy Adv",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-happys-grand-adventure/"
        },
        {
                "title": "FT 100 Year",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-100-years-quest/"
        },
        {
                "title": "FT Ice Trail",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-ice-trail/"
        },
        {
                "title": "FT x Taizai",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-x-nanatsu-no-taizai-christmas-special/"
        },
        {
                "title": "Parasyte x FT",
                "url": "https://ww8.readfairytail.com/manga/parasyte-x-fairy-tail/"
        },
        {
                "title": "Gaiden 1",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-gaiden-raigo-issen/"
        },
        {
                "title": "FT x Rave",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-x-rave/"
        },
        {
                "title": "Monster Hunter",
                "url": "https://ww8.readfairytail.com/manga/monster-hunter-orage/"
        },
        {
                "title": "Rave Master",
                "url": "https://ww8.readfairytail.com/manga/rave-master/"
        },
        {
                "title": "Dead Rock",
                "url": "https://ww8.readfairytail.com/manga/dead-rock/"
        },
        {
                "title": "Fairy Girls",
                "url": "https://ww8.readfairytail.com/manga/fairy-girls/"
        },
        {
                "title": "Gaiden 4",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-gaiden-raigo-issen/"
        },
        {
                "title": "Gaiden 2",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-gaiden-kengami-no-souryuu/"
        },
        {
                "title": "Gaiden 3",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-gaiden-road-knight/"
        },
        {
                "title": "FT x 7DS",
                "url": "https://ww8.readfairytail.com/manga/fairy-tail-x-nanatsu-no-taizai-christmas-special/"
        }
];


    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                return {
                    comics: this.staticCatalog.map(item => new Comic({
                        id: item.url,
                        title: item.title,
                        cover: ""
                    })),
                    hasMore: false
                };
            }
        }
    ]

    // Search
    search = {
        load: async (keyword, options, page) => {
              const q = (keyword || "").toLowerCase();
              return {
                  comics: this.staticCatalog
                      .filter(item => item.title.toLowerCase().includes(q))
                      .map(item => new Comic({
                          id: item.url,
                          title: item.title,
                          cover: ""
                      })),
                  hasMore: false
              };
        }
    }

    // Comic Details and Reader Loading
    comic = {
        loadInfo: async (id) => {
            let url = id.startsWith("http") ? id : `${EnReadfairytailedenszeromangaonlineSource.baseUrl}${id}`;
            let res = await Network.get(url, EnReadfairytailedenszeromangaonlineSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector("div.container > h1");
            let authorEl = doc.querySelector(".author") || doc.querySelector(".author_area");
            let descEl = doc.querySelector("text");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = EnReadfairytailedenszeromangaonlineSource.resolveAbsoluteUrl((doc.querySelector('div.flex > img') ? (doc.querySelector('div.flex > img').attributes['src'] || '') : ''), url);
            doc.dispose();

            let chapters = await this.loadChapters(id);

            return new ComicDetails({
                title: title,
                subtitle: author,
                subTitle: author,
                cover: cover,
                description: description,
                tags: {},
                chapters: chapters,
            });
        },

        loadEp: async (comicId, epId) => {
            let url = epId.startsWith("http") ? epId : `${EnReadfairytailedenszeromangaonlineSource.baseUrl}${epId}`;
            let res = await Network.get(url, EnReadfairytailedenszeromangaonlineSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load episode, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let imgElements = doc.querySelectorAll("img[data-src]");
            let images = imgElements.map(el => EnReadfairytailedenszeromangaonlineSource.resolveAbsoluteUrl((el.attributes['data-src'] || ''), url)).filter(Boolean);
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
                ...EnReadfairytailedenszeromangaonlineSource.headers,
                "Referer": `${EnReadfairytailedenszeromangaonlineSource.baseUrl}/`,
            },
        }),

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...EnReadfairytailedenszeromangaonlineSource.headers,
                "Referer": `${EnReadfairytailedenszeromangaonlineSource.baseUrl}/`,
            },
        }),
    }

    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    loadChapters = async (comicUrl) => {
        let url = comicUrl.startsWith("http") ? comicUrl : `${EnReadfairytailedenszeromangaonlineSource.baseUrl}${comicUrl}`;
        let res = await Network.get(url, EnReadfairytailedenszeromangaonlineSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load chapters, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("div.w-full > div.bg-bg-secondary > div.grid");

        let chaptersList = elements.map(el => ({
            id: EnReadfairytailedenszeromangaonlineSource.resolveAbsoluteUrl((el.querySelector('.col-span-4 > a') ? (el.querySelector('.col-span-4 > a').attributes['href'] || '') : ''), url),
            title: (el.querySelector('.col-span-4 > a') ? el.querySelector('.col-span-4 > a').text : ''),
        }));

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

    /**
     * Placeholder hook for custom chapter transformations.
     */
    parseChaptersCustom = (chaptersObj, htmlBody) => {
        return chaptersObj;
    }

    /**
     * Placeholder hook for special page variants (e.g. MotionToon).
     */
    parsePagesCustom = (images, htmlBody) => {
        return images;
    }
}
