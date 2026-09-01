/**
 * @file en_readonepiecemangaonline.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.en.readonepiecemangaonline
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.4.8
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class EnReadonepiecemangaonlineSource extends ComicSource {
    name = "Read One Piece Manga Online"
    key = "en_readonepiecemangaonline"
    version = "1.0.1"
    minAppVersion = "1.6.0"

    static baseUrl = "https://ww12.readonepiece.com"
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
                "title": "One Piece",
                "url": "https://ww12.readonepiece.com/manga/one-piece/"
        },
        {
                "title": "Colored",
                "url": "https://ww12.readonepiece.com/manga/one-piece-digital-colored-comics/"
        },
        {
                "title": "Soma x Sanji",
                "url": "https://ww12.readonepiece.com/manga/shokugeki-no-sanji-one-shot/"
        },
        {
                "title": "OP x Toriko",
                "url": "https://ww12.readonepiece.com/manga/one-piece-x-toriko/"
        },
        {
                "title": "Party",
                "url": "https://ww12.readonepiece.com/manga/one-piece-party/"
        },
        {
                "title": "DB x OP",
                "url": "https://ww12.readonepiece.com/manga/dragon-ball-x-one-piece/"
        },
        {
                "title": "Wanted!",
                "url": "https://ww12.readonepiece.com/manga/wanted-one-piece/"
        },
        {
                "title": "Ace's Story",
                "url": "https://ww12.readonepiece.com/manga/one-piece-ace-s-story/"
        },
        {
                "title": "Omake",
                "url": "https://ww12.readonepiece.com/manga/one-piece-omake/"
        },
        {
                "title": "Vivre Card",
                "url": "https://ww12.readonepiece.com/manga/vivre-card-databook/"
        },
        {
                "title": "Pirate Recipes",
                "url": "https://ww12.readonepiece.com/manga/one-piece-pirate-recipes/"
        },
        {
                "title": "Databook",
                "url": "https://ww12.readonepiece.com/manga/one-piece-databook/"
        },
        {
                "title": "Ace's Story Manga",
                "url": "https://ww12.readonepiece.com/manga/one-piece-ace-story-manga/"
        },
        {
                "title": "OP Academy",
                "url": "https://ww12.readonepiece.com/manga/one-piece-academy/"
        },
        {
                "title": "MONSTERS",
                "url": "https://ww12.readonepiece.com/manga/monsters/"
        },
        {
                "title": "Zoro Novel",
                "url": "https://ww12.readonepiece.com/manga/one-piece-novel-zoro/"
        },
        {
                "title": "OP in Love",
                "url": "https://ww12.readonepiece.com/manga/one-piece-in-love/"
        },
        {
                "title": "Heroines",
                "url": "https://ww12.readonepiece.com/manga/one-piece-novel-heroines/"
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
            let url = id.startsWith("http") ? id : `${EnReadonepiecemangaonlineSource.baseUrl}${id}`;
            let res = await Network.get(url, EnReadonepiecemangaonlineSource.headers);
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
            let cover = EnReadonepiecemangaonlineSource.resolveAbsoluteUrl((doc.querySelector('div.flex > img') ? (doc.querySelector('div.flex > img').attributes['src'] || '') : ''), url);
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
            let url = epId.startsWith("http") ? epId : `${EnReadonepiecemangaonlineSource.baseUrl}${epId}`;
            let res = await Network.get(url, EnReadonepiecemangaonlineSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load episode, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let imgElements = doc.querySelectorAll("img[data-src]");
            let images = imgElements.map(el => EnReadonepiecemangaonlineSource.resolveAbsoluteUrl((el.attributes['data-src'] || ''), url)).filter(Boolean);
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
                ...EnReadonepiecemangaonlineSource.headers,
                "Referer": `${EnReadonepiecemangaonlineSource.baseUrl}/`,
            },
        }),

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...EnReadonepiecemangaonlineSource.headers,
                "Referer": `${EnReadonepiecemangaonlineSource.baseUrl}/`,
            },
        }),
    }

    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    loadChapters = async (comicUrl) => {
        let url = comicUrl.startsWith("http") ? comicUrl : `${EnReadonepiecemangaonlineSource.baseUrl}${comicUrl}`;
        let res = await Network.get(url, EnReadonepiecemangaonlineSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load chapters, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("div.w-full > div.bg-bg-secondary > div.grid");

        let chaptersList = elements.map(el => ({
            id: EnReadonepiecemangaonlineSource.resolveAbsoluteUrl((el.querySelector('.col-span-4 > a') ? (el.querySelector('.col-span-4 > a').attributes['href'] || '') : ''), url),
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
