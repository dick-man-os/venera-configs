// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi9103931521355991619Source extends ComicSource {
    name = "瓜子漫画";
    key = "keiyoushi_9103931521355991619";
    version = "1.0.0";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_9103931521355991619","name":"瓜子漫画","languages":["zh-Hans"],"contentOrigins":[],"contentWarning":"SAFE","sourceType":"html","baseUrl":"https://www.guazimanhua.com","mobileUrl":"https://www.guazimanhua.com","requiresAuth":false,"requiresWebView":false,"familyContract":"guazimanhua-v1","headers":{"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"},"explore":{"popular":{"url":"https://www.guazimanhua.com/category.php?sort=hits&page={page}","method":"GET"},"latest":{"url":"https://www.guazimanhua.com/category.php?sort=update&page={page}","method":"GET"}},"search":{"url":"https://www.guazimanhua.com/category.php","method":"GET","selector":"article.card","pagination":{"nextSelector":"nav.pager a","nextText":">","maxPage":"same-query numeric pager links"}},"details":{"url":"{comicId}","method":"GET","fields":{"title":"div.mobile-comic-title","cover":"img.mobile-comic-cover[src]","description":"p.mobile-comic-desc"}},"chapters":{"url":"{comicId}","method":"GET","selector":"section.mobile-comic-all-chapters div.mobile-chapter-grid a","order":"newest-first; dedupe then reverse"},"pages":{"url":"{chapterId}","method":"GET","selector":"section.reader-images img","fields":{"imageUrl":"src"},"order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.zh.guazimanhua","upstreamSourceId":"9103931521355991619","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.6.6","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-12T00:00:00Z"},"artifactId":"guazimanhua","version":"1.0.0"};
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
        if (/[\u0000-\u0020\u007f\\]/.test(clean) || /%(?![0-9a-f]{2})/i.test(clean)) throw new Error("Invalid Guazimanhua URL");
        const url = this.absolute(clean,base);
        if (!/^https?:\/\/[a-z0-9.-]+(?::\d+)?(?:[/?#]|$)/i.test(url)) throw new Error("Invalid Guazimanhua URL");
        return url;
    };
    route = (value, kind) => {
        const url = this.httpUrl(value), prefix = this.baseUrl + "/" + kind + ".php?id=";
        if (!url.startsWith(prefix) || !/^\d+$/.test(url.slice(prefix.length))) throw new Error("Invalid Guazimanhua identity");
        return url;
    };
    pagerIdentity = href => {
        const url = this.httpUrl(href), prefix = this.baseUrl + "/category.php?";
        if (!url.startsWith(prefix) || url.includes("#")) throw new Error("Invalid Guazimanhua pagination");
        const values = Object.create(null);
        for (const part of url.slice(prefix.length).split("&")) {
            const at = part.indexOf("="), key = decodeURIComponent(at < 0 ? part : part.slice(0,at));
            if (!["sort","keyword","page"].includes(key) || key in values) throw new Error("Invalid Guazimanhua pagination");
            values[key] = decodeURIComponent((at < 0 ? "" : part.slice(at+1)).replace(/\+/g," "));
        }
        const raw = values.page || "1", page = /^[1-9]\d*$/.test(raw) ? Number(raw) : NaN;
        if (!Number.isSafeInteger(page)) throw new Error("Invalid Guazimanhua pagination");
        return {page,sort:values.sort || "hits",keyword:values.keyword || ""};
    };
    catalog = async (kind, keyword, page) => {
        const query = kind === "search" ? keyword.trim() : "", sort = kind === "latest" ? "update" : "hits";
        const params = query ? [["keyword",query]] : [];
        params.push(["sort",sort],["page",page]);
        const url = this.query(this.config.search.url,params);
        return this.html(url,doc => {
            const rows = doc.querySelectorAll(this.config.search.selector).map(el => ({
                id:this.route(this.attr(el,"a.cover-wrap","href"),"comic"),
                title:this.required(this.text(el,"h3 a")),
                cover:this.attr(el,"img.cover","src") ? this.httpUrl(this.attr(el,"img.cover","src")) : ""
            }));
            let hasMore = false, maxPage = page;
            for (const link of doc.querySelectorAll("nav.pager a")) {
                const target = this.pagerIdentity(this.attr(link,null,"href"));
                if (target.sort !== sort || target.keyword !== query) throw new Error("Guazimanhua pagination query mismatch");
                if (this.text(link) === ">") {
                    if (hasMore || target.page !== page + 1) throw new Error("Non-progressing Guazimanhua next page");
                    hasMore = true;
                }
                maxPage = Math.max(maxPage,target.page);
            }
            if (hasMore && !rows.length) throw new Error("Empty nonterminal Guazimanhua page");
            return {comics:this.unique(rows).map(row=>new Comic(row)),hasMore,maxPage:hasMore ? maxPage : page};
        });
    };
    info = async id => this.html(this.route(id,"comic"),doc => {
        const author = doc.querySelectorAll("div.cinema-strip > div").find(el=>this.text(el,"span") === "作者");
        const genre = this.text(doc,"p.mobile-comic-tags");
        const cover = this.attr(doc,"img.mobile-comic-cover","src");
        return {title:this.required(this.text(doc,"div.mobile-comic-title")),
            subtitle:author ? this.text(author,"b") : "",description:this.text(doc,"p.mobile-comic-desc"),
            cover:cover ? this.httpUrl(cover) : "",tags:genre ? {Genre:[genre]} : {}};
    });
    loadChapters = async id => this.html(this.route(id,"comic"),doc => {
        const rows = doc.querySelectorAll(this.config.chapters.selector).map(el=>({
            id:this.route(this.attr(el,null,"href"),"chapter"),title:this.required(this.text(el))
        }));
        if (!rows.length) throw new Error("Missing Guazimanhua chapters");
        return this.chaptersObject(this.unique(rows).reverse());
    });
    images = async (comicId, epId) => {
        this.route(comicId,"comic");
        const url = this.route(epId,"chapter");
        return this.html(url,doc => {
            const images = doc.querySelectorAll(this.config.pages.selector).map(el=>this.httpUrl(this.attr(el,null,"src"),url));
            if (!images.length) throw new Error("Guazimanhua chapter has no readable images");
            return [...new Set(images)];
        });
    };

}
