// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi5092568988625041973Source extends ComicSource {
    name = "HANMAN18";
    key = "keiyoushi_5092568988625041973";
    version = "1.0.1";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_5092568988625041973","name":"HANMAN18","languages":["zh-Hant"],"contentOrigins":[],"contentWarning":"NSFW","sourceType":"html","baseUrl":"https://hanman18.com","mobileUrl":"https://hanman18.com","requiresAuth":false,"requiresWebView":false,"familyContract":"manga18-v1","headers":{"Referer":"https://hanman18.com/"},"explore":{"popular":{"url":"https://hanman18.com/list-manga/{page}?order_by=views","method":"GET"},"latest":{"url":"https://hanman18.com/list-manga/{page}","method":"GET"}},"search":{"url":"https://hanman18.com/list-manga/{page}?search={query}","method":"GET","selector":"div.story_item","pagination":{"nextSelector":".pagination > li:last-child:not(.active)"},"fields":{"listing":"div.story_item","title":"div.mg_info > div.mg_name a","link":"div.mg_info > div.mg_name a","cover":"img","coverAttr":"src","infoRoot":"div.detail_listInfo","detailTitle":"div.detail_name > h1","detailCover":"div.detail_avatar > img","detailCoverAttr":"src","detailDescription":"div.detail_reviewContent","detailTags":"div.info_value > a[href*=\"/manga-list/\"]","chapters":"div.chapter_box .item","chapterOrder":"newest-first","reader":"slides-path-base64","rejectDirectoryUrls":true}},"details":{"url":"{comicId}","method":"GET","selector":"div.detail_listInfo","fields":{"listing":"div.story_item","title":"div.mg_info > div.mg_name a","link":"div.mg_info > div.mg_name a","cover":"img","coverAttr":"src","infoRoot":"div.detail_listInfo","detailTitle":"div.detail_name > h1","detailCover":"div.detail_avatar > img","detailCoverAttr":"src","detailDescription":"div.detail_reviewContent","detailTags":"div.info_value > a[href*=\"/manga-list/\"]","chapters":"div.chapter_box .item","chapterOrder":"newest-first","reader":"slides-path-base64","rejectDirectoryUrls":true}},"chapters":{"url":"{comicId}","method":"GET","selector":"div.chapter_box .item","order":"newest-first"},"pages":{"url":"{chapterId}","method":"GET","decoder":"slides-path-base64","rejectDirectoryUrls":true,"order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.zh.hanman18","upstreamSourceId":"5092568988625041973","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.4.3","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-12T00:00:00Z"},"artifactId":"hanman18","version":"1.0.1"};
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
    origin = base => this.absolute("/", base).replace(/\/$/, "");
    sourceId = (value, base) => {
        const absolute = this.absolute(String(value || "").trim(), base);
        const origin = this.origin(this.baseUrl + "/");
        return absolute.startsWith(origin + "/") ? absolute.slice(origin.length) : absolute;
    };
    pageUrl = id => this.absolute(id, this.baseUrl + "/");
    catalog = async (kind, keyword, page) => {
        if (kind === "search" && !keyword.trim()) return {comics:[],hasMore:false};
        const operation = kind === "search" ? this.config.search : this.config.explore[kind];
        const url = operation.url.replace("{page}", page).replace("{query}", encodeURIComponent(keyword.trim()));
        const fields = this.config.search.fields;
        return this.html(url, (doc, request) => {
            const rows = doc.querySelectorAll(fields.listing).map(el => {
                const link = el.querySelector(fields.link);
                const title = this.text(el, fields.title);
                const href = link ? this.attr(link, null, "href") : "";
                const cover = this.attr(el, fields.cover, fields.coverAttr);
                if (!title || !href) return null;
                return new Comic({id:this.sourceId(href,request),title,cover:this.absolute(cover,request),tags:["NSFW"]});
            }).filter(Boolean);
            return {comics:this.unique(rows),hasMore:!!doc.querySelector(this.config.search.pagination.nextSelector)};
        });
    };
    info = async id => {
        const fields = this.config.details.fields;
        return this.html(this.pageUrl(id), (doc, request) => {
            const root = doc.querySelector(fields.infoRoot);
            if (!root) throw new Error("Could not find Manga18 details");
            let author = "", artist = "", alternate = "";
            for (const item of root.querySelectorAll("div.item")) {
                const label = this.text(item, "div.info_label").toLowerCase();
                const value = this.text(item, "div.info_value");
                if (label.includes("author") && value !== "Updating") author = value;
                if (label.includes("artist") && value !== "Updating") artist = value;
                if (label.includes("other name") && value !== "Updating") alternate = value;
            }
            let description = this.text(doc, fields.detailDescription);
            if (alternate) description += (description ? "\n\n" : "") + "Alternative Names:\n" + alternate;
            const tags = root.querySelectorAll(fields.detailTags).map(el => this.text(el)).filter(Boolean);
            const subtitle = [author,artist].filter(Boolean).join(", " );
            return {title:this.required(this.text(doc,fields.detailTitle)),subtitle,description,
                cover:this.absolute(this.attr(doc,fields.detailCover,fields.detailCoverAttr),request),
                tags:tags.length ? {Genre:tags} : {}};
        });
    };
    loadChapters = async id => this.html(this.pageUrl(id), (doc, request) => {
        let rows = doc.querySelectorAll(this.config.chapters.selector).map(el => {
            const link = el.querySelector("a");
            const href = link ? this.attr(link,null,"href") : "";
            const title = link ? this.text(link) : "";
            return href && title ? {id:this.sourceId(href,request),title} : null;
        }).filter(Boolean);
        rows = this.unique(rows);
        if (this.config.chapters.order === "newest-first") rows.reverse();
        return this.chaptersObject(rows);
    });
    decodePages = (body, request) => {
        const match = body.match(/var\s+slides_p_path\s*=\s*\[([\s\S]*?)\]\s*;/);
        if (!match) throw new Error("Missing Manga18 reader data");
        const encoded = [], pattern = /"([A-Za-z0-9+/=]+)"/g;
        let item; while ((item = pattern.exec(match[1])) !== null) encoded.push(item[1]);
        const seen = new Set(), images = [];
        for (const value of encoded) {
            const decoded = Convert.decodeUtf8(Convert.decodeBase64(value)).trim();
            const url = this.absolute(decoded,request);
            if (!url || url.split(/[?#]/)[0].endsWith("/") || seen.has(url)) continue;
            seen.add(url); images.push(url);
        }
        if (!images.length) throw new Error("HANMAN18: upstream chapter has no readable images");
        return images;
    };
    images = async (comicId, epId) => {
        const url = this.pageUrl(epId), response = await this.request(url);
        return this.decodePages(String(response.body || ""),url);
    };

}
