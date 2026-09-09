// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi4222375517460530289Source extends ComicSource {
    name = "Dongman Manhua";
    key = "keiyoushi_4222375517460530289";
    version = "1.0.2";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_4222375517460530289","name":"Dongman Manhua","languages":["zh-Hans"],"contentOrigins":[],"contentWarning":"SAFE","sourceType":"html","baseUrl":"https://www.dongmanmanhua.cn","mobileUrl":"https://www.dongmanmanhua.cn","requiresAuth":false,"requiresWebView":false,"familyContract":"dongmanmanhua-v1","headers":{"Referer":"https://www.dongmanmanhua.cn/","Origin":"https://www.dongmanmanhua.cn"},"explore":{"popular":{"url":"https://www.dongmanmanhua.cn/dailySchedule","method":"GET","maxPage":1},"latest":{"url":"https://www.dongmanmanhua.cn/dailySchedule?sortOrder=UPDATE&webtoonCompleteType=ONGOING","method":"GET","maxPage":1}},"search":{"url":"https://www.dongmanmanhua.cn/search","method":"GET","selector":"#content > div.card_wrap.search ul:not(#filterLayer) li a","pagination":{"nextSelector":"div.more_area, div.paginate a[onclick] + a"}},"details":{"url":"{comicId}","method":"GET","fields":{"title":"h1.subj, h3.subj","description":"#_asideDetail p.summary"}},"chapters":{"url":"{comicId}","method":"GET","selector":"ul#_listUl li","pagination":{"nextSelector":"div.paginate a[onclick] + a"},"order":"response"},"pages":{"url":"{chapterId}","method":"GET","selector":"div#_imageList > img","fields":{"imageUrl":"@data-url"},"order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.zh.dongmanmanhua","upstreamSourceId":"4222375517460530289","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.4.6","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-08T16:25:36Z"},"artifactId":"dongmanmanhua_zh_hans","version":"1.0.2"};
    get baseUrl() { return this.config.baseUrl; }
    get locale() { return this.config.languages[0]; }
    get headers() { return this.config.headers; }
    text = (el, selector) => {
        const node = selector ? el.querySelector(selector) : el;
        return node ? (node.text || "").trim() : "";
    };
    attr = (el, selector, name) => {
        const node = selector ? el.querySelector(selector) : el;
        return node ? node.attributes[name] || "" : "";
    };
    absolute = (value, base = this.baseUrl + "/") => {
        if (typeof value !== "string" || !value) return "";
        if (/^https?:\/\//i.test(value)) return value;
        if (/^[a-z][a-z0-9+.-]*:/i.test(value)) throw new Error("Unsupported URL scheme");
        const match = base.match(/^(https?:)\/\/([^/?#]+)([^?#]*)(\?[^#]*)?/i);
        if (!match) throw new Error("Invalid URL base");
        const origin = match[1] + "//" + match[2];
        if (value.startsWith("//")) return match[1] + value;
        const path = match[3] || "/";
        if (value.startsWith("?")) return origin + path + value;
        if (value.startsWith("#")) return origin + path + (match[4] || "") + value;
        const at = value.search(/[?#]/);
        const suffix = at < 0 ? "" : value.slice(at);
        const raw = at < 0 ? value : value.slice(0, at);
        const full = raw.startsWith("/") ? raw : path.slice(0, path.lastIndexOf("/") + 1) + raw;
        const parts = [];
        for (const p of full.split("/")) {
            if (p === "..") parts.pop();
            else if (p && p !== ".") parts.push(p);
        }
        return origin + "/" + parts.join("/") + (full.endsWith("/") && parts.length ? "/" : "") + suffix;
    };
    pageNumber = page => {
        if (!Number.isSafeInteger(page) || page < 1) throw new Error("Invalid page");
        return page;
    };
    query = (url, values) => url + "?" + values.map(([key, value]) =>
        encodeURIComponent(key) + "=" + encodeURIComponent(String(value))).join("&");
    array = value => {
        if (!Array.isArray(value)) throw new Error("Malformed list response");
        return value;
    };
    required = value => {
        if (typeof value !== "string" || !value.trim()) throw new Error("Missing required value");
        return value;
    };
    unique = (items, key = "id") => {
        const seen = new Set();
        return items.filter(item => {
            const id = this.required(String(item[key] ?? ""));
            if (seen.has(id)) return false;
            seen.add(id);
            return true;
        });
    };
    request = async (url, data = undefined) => {
        url = this.networkUrl(url);
        const res = data === undefined ? await Network.get(url, this.headers)
            : await Network.post(url, {...this.headers, "Content-Type": "application/json"}, JSON.stringify(data));
        if (res.status === 402) throw new Error("Payment required");
        if (res.status !== 200 && res.status !== 204) throw new Error("HTTP " + res.status);
        return res;
    };
    json = async (url, data = undefined) => {
        const res = await this.request(url, data);
        if (res.status === 204) return null;
        const result = typeof res.body === "string" ? JSON.parse(res.body) : res.body;
        if (!result || typeof result !== "object" || Array.isArray(result)) throw new Error("Malformed JSON response");
        return result;
    };
    html = async (url, parse) => {
        const res = await this.request(url);
        if (res.status !== 200) throw new Error("Empty HTML response");
        const doc = new HtmlDocument(res.body);
        try { return parse(doc, url); } finally { doc.dispose(); }
    };
    chaptersObject = rows => {
        const result = Object.create(null);
        for (const row of this.unique(rows)) result[row.id] = row.title || "";
        return result;
    };
    details = (data, chapters) => new ComicDetails({
        title: this.required(data.title), subtitle: data.subtitle || "", subTitle: data.subtitle || "",
        cover: data.cover || "", description: data.description || "", tags: data.tags || {}, chapters
    });
    explore = [
        {title: "Popular", type: "multiPageComicList", load: page => this.catalog("popular", "", this.pageNumber(page))},
        {title: "Latest", type: "multiPageComicList", load: page => this.catalog("latest", "", this.pageNumber(page))}
    ];
    search = {load: (keyword, options, page) => this.catalog("search", String(keyword), this.pageNumber(page))};
    comic = {
        loadInfo: async id => this.details(await this.info(id), await this.loadChapters(id)),
        loadEp: async (comicId, epId) => ({images: await this.images(comicId, epId)}),
        onThumbnailLoad: (url, comicId) => this.imageConfig(url, this.networkUrl(comicId || "/")),
        onImageLoad: (url, comicId, epId) => this.imageConfig(url, epId ? this.readerBase(comicId, epId) : this.networkUrl(comicId || "/"))
    };
    urlOrigin = url => {
        const match = url.match(/^(https?):\/\/([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?::([0-9]{1,5}))?(?:[/?#]|$)/i);
        if (!match || match[2].includes("..") || (match[3] && (+match[3] < 1 || +match[3] > 65535)))
            throw new Error("Malformed HTTP URL");
        const scheme = match[1].toLowerCase(), port = match[3] ? String(+match[3]) : "";
        return scheme + "://" + match[2].toLowerCase() +
            (port && port !== (scheme === "https" ? "443" : "80") ? ":" + port : "");
    };
    networkUrl = (value, base = this.baseUrl + "/") => {
        const clean = this.required(value).trim();
        if (/[\u0000-\u0020\u007f\\]/.test(clean) || /%(?![0-9a-f]{2})/i.test(clean))
            throw new Error("Malformed HTTP URL");
        this.urlOrigin(base);
        const url = this.absolute(clean, base);
        this.urlOrigin(url);
        return url;
    };
    imageConfig = (url, base) => ({url: this.networkUrl(url, base), headers: this.headers});
    readerBase = (comicId, epId) => this.networkUrl(epId, this.networkUrl(comicId || "/"));
    author = doc => {
        const info = doc.querySelector(".detail_header .info");
        if (!info) return "";
        // Upstream selects the first author that is first among siblings of its tag,
        // not simply the first element with the author class. Dart html lacks this pseudo-class.
        const author = info.querySelectorAll(".author").find(el => {
            for (let prev = el.previousElementSibling; prev; prev = prev.previousElementSibling)
                if (prev.localName === el.localName) return false;
            return true;
        }) || info.querySelector(".author_area");
        if (!author) return "";
        return author.nodes.filter(node => node.type === "text").map(node => node.text)
            .join("").replace(/\s+/g, " ").trim();
    };
    listItem = (el, url) => new Comic({
        id: this.networkUrl(this.required(this.attr(el, null, "href")), url),
        title: this.required(this.text(el, "p.subj")),
        cover: this.attr(el, "img", "src") ? this.networkUrl(this.attr(el, "img", "src"), url) : ""
    });
    catalog = async (kind, keyword, page) => {
        let url, selector;
        if (kind === "search") {
            const params = [["keyword", keyword]];
            if (page > 1) params.push(["page", page]);
            url = this.query(this.config.search.url, params);
            selector = this.config.search.selector;
        } else {
            if (page !== 1) return {comics: [], hasMore: false, maxPage: 1};
            url = this.config.explore[kind].url;
            const days = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];
            selector = kind === "popular" ? "div#dailyList .daily_section li a, div.daily_lst.comp li a"
                : "div#dailyList > div._list_" + days[new Date().getDay()] + " li > a";
        }
        return this.html(url, (doc, request) => ({
            comics: this.unique(doc.querySelectorAll(selector).map(el => this.listItem(el, request))),
            hasMore: kind === "search" && !!doc.querySelector(this.config.search.pagination.nextSelector),
            // Both daily calendars are complete, unpaged upstream responses.
            ...(kind === "search" ? {} : {maxPage: 1})
        }));
    };
    info = async id => this.html(this.networkUrl(id), (doc, url) => {
        const style = this.attr(doc, "#content > div.cont_box > div.detail_body", "style");
        const match = style.match(/url\(\s*["']?(.*?)["']?\s*\)/);
        const cover = match?.[1] || this.attr(doc, "#content > div.cont_box > div.detail_header > span.thmb img:not([alt='Representative image'])", "src");
        return {title: this.required(this.text(doc, this.config.details.fields.title)),
            subtitle: this.author(doc),
            description: this.text(doc, this.config.details.fields.description), cover: cover ? this.networkUrl(cover, url) : ""};
    });
    loadChapters = async id => {
        let url = this.networkUrl(id), ended = false;
        const visited = new Set(), chapterIds = new Set(), rows = [];
        for (let page = 0; page < 1000; page++) {
            if (visited.has(url)) throw new Error("Cyclic chapter pagination");
            visited.add(url);
            const parsed = await this.html(url, (doc, request) => ({
                rows: doc.querySelectorAll(this.config.chapters.selector).map(el => ({
                    id: this.networkUrl(this.required(this.attr(el, "a", "href")), request),
                    title: this.required(this.text(el, "span.subj span"))
                })),
                next: this.attr(doc, this.config.chapters.pagination.nextSelector, "href")
            }));
            const before = chapterIds.size;
            for (const row of parsed.rows) {
                if (!chapterIds.has(row.id)) { chapterIds.add(row.id); rows.push(row); }
            }
            if (!parsed.next) { ended = true; break; }
            if (chapterIds.size === before) throw new Error("Non-progressing chapter pagination");
            const next = this.networkUrl(parsed.next, url);
            // Keep navigation within this source's origin.
            if (this.urlOrigin(next) !== this.urlOrigin(this.baseUrl))
                throw new Error("Foreign chapter pagination URL");
            url = next;
        }
        if (!ended) throw new Error("Chapter traversal bound exceeded");
        return this.chaptersObject(rows);
    };
    images = async (comicId, epId) => this.html(this.readerBase(comicId, epId), (doc, url) =>
        doc.querySelectorAll(this.config.pages.selector).map(el => this.networkUrl(this.required(this.attr(el, null, "data-url")), url)));

}
