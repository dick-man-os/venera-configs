// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi7151191693036508367Source extends ComicSource {
    name = "GlobalComix";
    key = "keiyoushi_7151191693036508367";
    version = "1.0.0";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_7151191693036508367","name":"GlobalComix","languages":["zh-Hans"],"contentOrigins":[],"contentWarning":"MIXED","sourceType":"api","baseUrl":"https://globalcomix.com","mobileUrl":"https://globalcomix.com","requiresAuth":false,"requiresWebView":false,"familyContract":"globalcomix-v1","headers":{"Referer":"https://globalcomix.com/","Origin":"https://globalcomix.com","x-gc-client":"gck_d0f170d5729446dcb3b55e6b3ebc7bf6","x-gc-identmode":"cookie"},"explore":{"popular":{"url":"https://api.globalcomix.com/v1/comics","method":"GET"},"latest":{"url":"https://api.globalcomix.com/v1/comics","method":"GET"}},"search":{"url":"https://api.globalcomix.com/v1/comics","method":"GET","query":{"lang_id[]":"cn"},"pagination":{"page":"p","hasNext":"payload.pagination.page < payload.pagination.total_pages"}},"details":{"url":"https://api.globalcomix.com/v1/read/{slug}","method":"GET","fields":{"title":"payload.results.name","thumbnail":"payload.results.image_url"}},"chapters":{"url":"https://api.globalcomix.com/v1/comics/{comicId}/releases","method":"GET","query":{"lang_id":"cn","all":"true"},"listPath":"payload.results","access":"exclude premium_only == 1","order":"response"},"pages":{"url":"https://api.globalcomix.com/v1/readV2/{chapterId}","method":"GET","listPath":"payload.results.page_objects","fields":{"imageUrl":"desktop_image_url"},"access":"reject paid chapter or any paid page","order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.all.globalcomix","upstreamSourceId":"7151191693036508367","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.4.4","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-07T06:50:33Z"},"artifactId":"globalcomix_zh_hans","version":"1.0.0"};
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
    comicIdentity = item => {
        const number = String(item.id ?? "");
        if (!/^\d+$/.test(number)) throw new Error("Missing comic ID");
        const slug = this.required(item.slug);
        return number + "/" + encodeURIComponent(slug);
    };
    splitIdentity = id => {
        const match = String(id).match(/^(\d+)\/([^/]+)$/);
        if (!match) throw new Error("Invalid GlobalComix identity");
        return match;
    };
    manga = item => new Comic({
        id: this.comicIdentity(item), title: this.required(item.name),
        cover: this.absolute(item.image_url || ""), description: item.description || "",
        subtitle: item.artist ? item.artist.roman_name ?? item.artist.name ?? "" : ""
    });
    catalog = async (kind, keyword, page) => {
        const op = this.config.search;
        const values = [["lang_id[]", op.query["lang_id[]"]], ["p", page]];
        if (kind === "latest") values.push(["sort", "recent"]);
        if (kind === "search") values.push(["sort", "relevance"], ["q", keyword]);
        const body = await this.json(this.query(op.url, values));
        if (!body?.payload) throw new Error("Missing GlobalComix payload");
        const p = body.payload.pagination;
        if (!p || !Number.isInteger(p.page) || !Number.isInteger(p.total_pages) || p.page !== page)
            throw new Error("Invalid GlobalComix pagination");
        return {comics: this.unique(this.array(body.payload.results).map(this.manga)), hasMore: p.page < p.total_pages};
    };
    info = async id => {
        const match = this.splitIdentity(id);
        const url = this.config.details.url.replace("{slug}", match[2]);
        const body = await this.json(url);
        const item = body?.payload?.results;
        if (!item || String(item.id) !== match[1]) throw new Error("Comic identity mismatch");
        return this.manga(item);
    };
    loadChapters = async id => {
        const match = this.splitIdentity(id), op = this.config.chapters;
        const url = this.query(op.url.replace("{comicId}", match[1]), Object.entries(op.query));
        const body = await this.json(url);
        if (!body?.payload) throw new Error("Missing GlobalComix chapters");
        const p = body.payload.pagination;
        if (p && p.page < p.total_pages) throw new Error("Incomplete all-releases response");
        return this.chaptersObject(this.array(body.payload.results).filter(ch => ch.premium_only !== 1).map(ch => ({
            id: this.required(ch.key), title: [ch.chapter ? "Ch." + ch.chapter : "", ch.title ? (ch.chapter ? "- " : "") + ch.title : ""].filter(Boolean).join(" ")
        })));
    };
    images = async (comicId, epId) => {
        this.splitIdentity(comicId);
        const body = await this.json(this.config.pages.url.replace("{chapterId}", encodeURIComponent(this.required(epId))));
        const chapter = body?.payload?.results;
        if (!chapter) throw new Error("Missing chapter payload");
        if (chapter.key !== epId) throw new Error("Chapter identity mismatch");
        if (chapter.premium_only === 1) throw new Error("Paid chapter");
        const pages = this.array(chapter.page_objects);
        if (pages.some(p => p.is_page_paid !== false)) throw new Error("Paid or unknown page access");
        return pages.map(p => this.absolute(this.required(p.desktop_image_url)));
    };

}
