// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi1163192659786040070Source extends ComicSource {
    name = "NamiComi（简体中文）";
    key = "keiyoushi_1163192659786040070";
    version = "1.0.2";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_1163192659786040070","name":"NamiComi（简体中文）","languages":["zh-Hans"],"contentOrigins":[],"contentWarning":"SAFE","sourceType":"api","baseUrl":"https://namicomi.com","mobileUrl":"https://namicomi.com","requiresAuth":false,"requiresWebView":false,"familyContract":"namicomi-v1","headers":{"Referer":"https://namicomi.com/","Origin":"https://namicomi.com"},"explore":{"popular":{"url":"https://api.namicomi.com/title/search","method":"GET"},"latest":{"url":"https://api.namicomi.com/title/search","method":"GET"}},"search":{"url":"https://api.namicomi.com/title/search","method":"GET","query":{"availableTranslatedLanguages[]":"zh-hans"},"pagination":{"limit":20,"offset":"(page-1)*20","hasNext":"meta.limit + meta.offset < meta.total","maxPage":"max(1, ceil(meta.total / meta.limit))"}},"details":{"url":"https://api.namicomi.com/title/{comicId}","method":"GET","fields":{"title":"data.attributes.title","description":"data.attributes.description"}},"chapters":{"url":"https://api.namicomi.com/chapter","method":"GET","query":{"translatedLanguages[]":"zh-hans"},"pagination":{"limit":200,"offset":0,"hasNext":"meta.limit + meta.offset < meta.total"},"access":{"url":"https://api.namicomi.com/gating/check","method":"POST","chunkSize":200,"allow":"data.attributes.map[id] === true"},"order":"oldest first; reverse complete volume desc, chapter desc response"},"pages":{"url":"https://api.namicomi.com/images/chapter/{chapterId}?newQualities=true","method":"GET","fields":{"imageUrl":"data.baseUrl/chapter/{chapterId}/{data.hash}/source/{data.source[].filename}"},"access":"gating check and HTTP 402 rejection","order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.all.namicomi","upstreamSourceId":"1163192659786040070","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.4.6","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-08T16:25:36Z"},"artifactId":"namicomi_zh_hans","version":"1.0.2"};
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
    includes = () => ["cover_art", "organization", "tag", "primary_tag", "secondary_tag"].map(v => ["includes[]", v]);
    externalLocale = () => this.locale.toLowerCase();
    manga = item => {
        const a = item.attributes;
        if (!a?.title || typeof a.title !== "object") throw new Error("Missing title map");
        const title = a.title[this.externalLocale()] ?? Object.values(a.title)[0];
        const rel = this.array(item.relationships || []);
        const cover = rel.find(r => r.type === "cover_art")?.attributes?.fileName;
        const authors = [...new Set(rel.filter(r => r.type === "organization").map(r => r.attributes?.name).filter(Boolean))];
        return new Comic({id: this.required(item.id), title: this.required(title),
            cover: cover ? "https://uploads.namicomi.com/covers/" + encodeURIComponent(item.id) + "/" + encodeURIComponent(cover) : "",
            subtitle: authors.join(", "), description: a.description?.[this.externalLocale()] ?? a.description?.en ?? ""});
    };
    pagination = (body, expectedOffset) => {
        const m = body.meta;
        if (!m || !Number.isSafeInteger(m.limit) || m.limit <= 0 || !Number.isSafeInteger(m.offset) ||
            m.offset !== expectedOffset || !Number.isSafeInteger(m.total) || m.total < 0) throw new Error("Invalid pagination");
        return m.offset + m.limit < m.total;
    };
    catalog = async (kind, keyword, page) => {
        const offset = (page - 1) * 20;
        const values = [["limit", 20], ["offset", offset],
            ["availableTranslatedLanguages[]", this.externalLocale()], ...this.includes()];
        if (kind === "search") { values.push(["order[publishedAt]", "desc"], ["includedTagsMode", "and"], ["excludedTagsMode", "or"]); if (keyword.trim()) values.push(["title", keyword.replace(/\s/g, " ")]); }
        else values.push(["order[" + (kind === "popular" ? "views" : "publishedAt") + "]", "desc"]);
        const body = await this.json(this.query(this.config.search.url, values));
        if (body === null) return {comics: [], hasMore: false, maxPage: Math.max(1, page - 1)};
        const more = this.pagination(body, offset);
        if (body.meta.limit !== 20) throw new Error("Unexpected catalog page size");
        return {comics: this.unique(this.array(body.data).map(this.manga)), hasMore: more,
            maxPage: Math.max(1, Math.ceil(body.meta.total / body.meta.limit))};
    };
    info = async id => {
        const url = this.query(this.config.details.url.replace("{comicId}", encodeURIComponent(this.required(id))), this.includes());
        const body = await this.json(url);
        if (body?.data?.id !== id) throw new Error("Comic identity mismatch");
        return this.manga(body.data);
    };
    access = async ids => {
        const result = Object.create(null);
        for (let start = 0; start < ids.length; start += 200) {
            const chunk = ids.slice(start, start + 200);
            const body = await this.json(this.config.chapters.access.url,
                {entities: chunk.map(id => ({entityId: id, entityType: "chapter"}))});
            const map = body?.data?.attributes?.map;
            if (!map || typeof map !== "object") throw new Error("Missing access map");
            for (const id of chunk) {
                if (!Object.prototype.hasOwnProperty.call(map, id) || typeof map[id] !== "boolean") throw new Error("Unknown chapter access");
                result[id] = map[id];
            }
        }
        return result;
    };
    loadChapters = async id => {
        this.required(id);
        const rows = [], seen = new Set();
        let offset = 0, ended = false;
        for (let pass = 0; pass < 1000; pass++) {
            const values = [["titleId", id], ["includes[]", "organization"], ["limit", 200], ["offset", offset],
                ["translatedLanguages[]", this.externalLocale()], ["order[volume]", "desc"], ["order[chapter]", "desc"]];
            const body = await this.json(this.query(this.config.chapters.url, values));
            if (body === null) { if (offset) throw new Error("Incomplete chapter pagination"); ended = true; break; }
            const data = this.array(body.data), more = this.pagination(body, offset);
            const before = seen.size;
            for (const chapter of data) seen.add(this.required(chapter.id));
            if ((offset || more) && seen.size === before) throw new Error("Non-progressing chapter pagination");
            rows.push(...data);
            if (!more) { ended = true; break; }
            if (!data.length) throw new Error("Non-progressing chapter pagination");
            offset += body.meta.limit;
        }
        if (!ended) throw new Error("Chapter traversal bound exceeded");
        const unique = this.unique(rows);
        if (!unique.length) return {};
        const access = await this.access(unique.map(c => this.required(c.id)));
        // Convert the complete upstream newest-first list once, after identity deduplication.
        return this.chaptersObject(unique.filter(c => access[c.id] === true).reverse().map(c => {
            const a = c.attributes;
            if (!a) throw new Error("Missing chapter attributes");
            const parts = [a.volume ? "Vol." + a.volume : "", a.chapter ? "Ch." + a.chapter : ""].filter(Boolean);
            if (a.name) { if (parts.length) parts.push("-"); parts.push(a.name); }
            return {id: c.id, title: parts.join(" ")};
        }));
    };
    images = async (comicId, epId) => {
        const access = await this.access([this.required(epId)]);
        if (!access[epId]) throw new Error("Chapter access denied");
        const body = await this.json(this.config.pages.url.replace("{chapterId}", encodeURIComponent(epId)));
        if (!body) throw new Error("Missing page response");
        if (body.data === null || body.data === undefined) return [];
        const data = body.data;
        const prefix = this.absolute(this.required(data.baseUrl)).replace(/\/$/, "") + "/chapter/" +
            encodeURIComponent(epId) + "/" + encodeURIComponent(this.required(data.hash)) + "/source/";
        return this.array(data.source).map(image => prefix + encodeURIComponent(this.required(image.filename)));
    };

}
