// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi5943234929466346733Source extends ComicSource {
    name = "《崩坏3》IP站";
    key = "keiyoushi_5943234929466346733";
    version = "1.0.0";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_5943234929466346733","name":"《崩坏3》IP站","languages":["zh-Hans"],"contentOrigins":[],"contentWarning":"SAFE","sourceType":"hybrid","baseUrl":"https://comic.bh3.com","mobileUrl":"https://comic.bh3.com","requiresAuth":false,"requiresWebView":false,"familyContract":"bh3-v1","headers":{"Referer":"https://comic.bh3.com/"},"explore":{"popular":{"url":"https://comic.bh3.com/book","method":"GET","maxPage":1}},"search":{"url":"https://comic.bh3.com/book","method":"GET","selector":"a[href*=book]","filter":"normalized native title over complete finite catalog","pagination":{"maxPage":1}},"details":{"url":"{comicId}","method":"GET","fields":{"title":"div.title","cover":"img.cover[src]","description":"div.detail_info1"}},"chapters":{"url":"{comicId}/get_chapter","method":"GET","isJson":true,"listPath":"$","identity":"bookid/chapterid strings","order":"newest-first; dedupe then reverse"},"pages":{"url":"{chapterId}","method":"GET","selector":"img.lazy.comic_img","fields":{"imageUrl":"data-original"},"order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.zh.bh3","upstreamSourceId":"5943234929466346733","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.4.4","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-12T00:00:00Z"},"artifactId":"bh3","version":"1.0.0"};
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
        onThumbnailLoad: url => ({url, headers: this.headers}),
        onImageLoad: url => ({url, headers: this.headers})
    };
    httpUrl = (value, base = this.baseUrl + "/") => {
        const clean = this.required(value).trim();
        if (/[\u0000-\u0020\u007f\\]/.test(clean) || /%(?![0-9a-f]{2})/i.test(clean)) throw new Error("Invalid BH3 URL");
        const url = this.absolute(clean,base);
        if (!/^https?:\/\/[a-z0-9.-]+(?::\d+)?(?:[/?#]|$)/i.test(url)) throw new Error("Invalid BH3 URL");
        return url;
    };
    idPart = value => {
        if (typeof value !== "string" || !/^\d+$/.test(value)) throw new Error("Invalid BH3 string identity");
        return value;
    };
    route = (value, chapter = false) => {
        const url = this.httpUrl(value), prefix = this.baseUrl + "/book/";
        if (!url.startsWith(prefix) || !(chapter ? /^\d+\/\d+$/ : /^\d+$/).test(url.slice(prefix.length))) throw new Error("Invalid BH3 route");
        return url;
    };
    normalizedTitle = value => String(value).trim().toLowerCase().replace(/\s+/g," ");
    catalog = async (kind, keyword, page) => {
        if (page > 1) return {comics:[],hasMore:false,maxPage:1};
        return this.html(this.config.search.url,doc => {
            const rows = doc.querySelectorAll(this.config.search.selector).map(el => {
                const container = el.querySelector("div.container");
                if (!container) return null;
                return new Comic({id:this.baseUrl + "/book/" + this.idPart(this.attr(container,null,"id")),
                    title:this.required(this.text(el,"div.container-title")),cover:this.httpUrl(this.attr(el,"img","src"))});
            }).filter(Boolean);
            const query = this.normalizedTitle(keyword);
            return {comics:this.unique(rows).filter(row=>kind !== "search" || this.normalizedTitle(row.title).includes(query)),hasMore:false,maxPage:1};
        });
    };
    info = async id => this.html(this.route(id),doc=>({
        title:this.required(this.text(doc,"div.title")),cover:this.httpUrl(this.attr(doc,"img.cover","src")),
        description:this.text(doc,"div.detail_info1"),tags:{}
    }));
    loadChapters = async id => {
        const url = this.route(id), book = url.slice((this.baseUrl + "/book/").length);
        const response = await this.request(url + "/get_chapter");
        const data = this.array(typeof response.body === "string" ? JSON.parse(response.body) : response.body);
        const rows = data.map(ch => {
            if (this.idPart(ch.bookid) !== book) throw new Error("BH3 chapter ownership mismatch");
            return {id:url + "/" + this.idPart(ch.chapterid),title:this.required(ch.title)};
        });
        if (!rows.length) throw new Error("Missing BH3 chapters");
        return this.chaptersObject(this.unique(rows).reverse());
    };
    images = async (comicId, epId) => {
        const comic = this.route(comicId), chapter = this.route(epId,true);
        if (!chapter.startsWith(comic + "/")) throw new Error("BH3 chapter ownership mismatch");
        return this.html(chapter,doc => {
            const images = doc.querySelectorAll(this.config.pages.selector).map(el=>this.httpUrl(this.attr(el,null,"data-original"),chapter));
            if (!images.length) throw new Error("BH3 chapter has no readable images");
            return [...new Set(images)];
        });
    };
    init() { this.explore = [{title:"漫画目录",type:"multiPageComicList",load:page=>this.catalog("popular","",this.pageNumber(page))}]; }

}
