// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi3279300917142951720Source extends ComicSource {
    name = "漫画屋";
    key = "keiyoushi_3279300917142951720";
    version = "1.0.0";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_3279300917142951720","name":"漫画屋","languages":["zh-Hans"],"contentOrigins":[],"contentWarning":"SAFE","sourceType":"html","baseUrl":"https://www.mhua5.com","mobileUrl":"https://m.mhua5.com","requiresAuth":false,"requiresWebView":false,"familyContract":"mccms-v1","headers":{"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"},"explore":{"popular":{"url":"https://www.mhua5.com/category/order/hits/page/{page}","method":"GET"},"latest":{"url":"https://www.mhua5.com/category/order/addtime/page/{page}","method":"GET"}},"search":{"url":"https://www.mhua5.com/search/{query}/{page}","method":"GET","selector":".common-comic-item","pagination":{"mode":"paired-links"},"fields":{"variant":"default","listing":".common-comic-item","title":".comic__title > a","cover":"img","coverAttr":"data-original","detailsRoot":".de-info__box","detailTitle":".comic-title","detailCover":"img","detailCoverAttr":"src","detailAuthor":".name","detailDescription":".intro-total","detailTags":".comic-status a","chapters":".chapter__list-box > li","chapterName":"a","chapterOrder":"oldest-first","reader":"html-lazy","readerSelector":"img[data-original]","readerAttr":"data-original","detailsBase":"desktop","pagination":"paired-links"}},"details":{"url":"{comicId}","method":"GET","selector":".de-info__box","fields":{"variant":"default","listing":".common-comic-item","title":".comic__title > a","cover":"img","coverAttr":"data-original","detailsRoot":".de-info__box","detailTitle":".comic-title","detailCover":"img","detailCoverAttr":"src","detailAuthor":".name","detailDescription":".intro-total","detailTags":".comic-status a","chapters":".chapter__list-box > li","chapterName":"a","chapterOrder":"oldest-first","reader":"html-lazy","readerSelector":"img[data-original]","readerAttr":"data-original","detailsBase":"desktop","pagination":"paired-links"}},"chapters":{"url":"{comicId}","method":"GET","selector":".chapter__list-box > li","fields":{"name":"a"},"order":"oldest-first"},"pages":{"url":"{chapterId}","method":"GET","decoder":"html-lazy","selector":"img[data-original]","fields":{"imageUrl":"data-original"},"order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.zh.manhuawu","upstreamSourceId":"3279300917142951720","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.4.9","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-11T03:59:34Z"},"artifactId":"manhuawu","version":"1.0.0"};
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
    get variant() { return this.config.search.fields.variant; }
    origin = base => this.absolute("/", base).replace(/\/$/, "");
    sourceId = (value, base) => {
        const absolute = this.absolute(String(value || "").trim(), base);
        const origin = this.origin(this.baseUrl + "/");
        const id = absolute.startsWith(origin + "/") ? absolute.slice(origin.length) : absolute;
        return id.replace(/^\/index\.php(?=\/)/, "");
    };
    pageUrl = (id, mobile = false) => this.absolute(id, (mobile ? this.config.mobileUrl : this.baseUrl) + "/");
    styleImage = value => String(value || "").match(/background\s*:\s*url\((['\"]?)(.*?)\1\)/i)?.[2] || "";
    imageList = (values, base) => {
        const seen = new Set(), result = [];
        for (const value of values) {
            const url = this.absolute(String(value || "").trim(), base);
            if (url && !seen.has(url)) { seen.add(url); result.push(url); }
        }
        return result;
    };
    hasNext = (doc, request) => {
        if (this.config.search.pagination.mode === "next-id") {
            const next = doc.querySelector("#next");
            const href = next ? this.attr(next, null, "href") : "";
            return !!href && this.absolute(href, request) !== request;
        }
        const buttons = doc.querySelectorAll("#Pagination a, .NewPages a");
        if (buttons.length < 2) return false;
        const previous = this.attr(buttons[buttons.length - 2], null, "href");
        const last = this.attr(buttons[buttons.length - 1], null, "href");
        return !!previous && !!last && this.absolute(previous, request) !== this.absolute(last, request);
    };
    catalog = async (kind, keyword, page) => {
        if (kind === "search" && !keyword.trim()) return {comics:[],hasMore:false};
        const operation = kind === "search" ? this.config.search : this.config.explore[kind];
        const url = operation.url.replace("{page}", page).replace("{query}", encodeURIComponent(keyword.trim()));
        const fields = this.config.search.fields;
        return this.html(url, (doc, request) => {
            const rows = doc.querySelectorAll(fields.listing).map(el => {
                const link = el.querySelector(fields.link || fields.title);
                const title = this.text(el, fields.title);
                const href = link ? this.attr(link, null, "href") : "";
                const coverNode = el.querySelector(fields.cover);
                const coverValue = !coverNode ? "" : fields.coverAttr === "style-background-url"
                    ? this.styleImage(this.attr(coverNode, null, "style")) : this.attr(coverNode, null, fields.coverAttr);
                if (!title || !href) return null;
                return new Comic({id:this.sourceId(href, request),title,cover:this.absolute(coverValue,request),
                    tags:this.config.contentWarning === "NSFW" ? ["NSFW"] : []});
            }).filter(Boolean);
            return {comics:this.unique(rows),hasMore:this.hasNext(doc,request)};
        });
    };
    info = async id => {
        const fields = this.config.details.fields;
        const mobile = fields.detailsBase === "mobile";
        return this.html(this.pageUrl(id, mobile), (doc, request) => {
            const root = doc.querySelector(fields.detailsRoot);
            if (!root) throw new Error("Could not find MCCMS details");
            let subtitle = this.text(root, fields.detailAuthor), tags = [];
            let description = this.text(fields.variant === "miaoqu" ? doc : root, fields.detailDescription);
            if (fields.variant === "miaoqu") {
                for (const item of root.querySelectorAll(fields.detailTags)) {
                    const value = this.text(item);
                    if (value.startsWith("作者：")) subtitle = value.slice(3).trim();
                    if (value.startsWith("类型：")) tags = item.querySelectorAll("a").map(x => this.text(x)).filter(Boolean);
                    if (value.startsWith("更新于")) description = value + (description ? "\n\n" + description : "");
                }
            } else if (fields.variant === "sixmh") {
                const rows = root.querySelectorAll("div.cy_xinxi");
                subtitle = rows[0] ? this.text(rows[0], "span:first-child > a") : "";
                tags = rows[1] ? rows[1].querySelectorAll("span:first-child > a").map(x => this.text(x)).filter(Boolean) : [];
            } else {
                tags = root.querySelectorAll(fields.detailTags).map(x => this.text(x)).filter(Boolean);
            }
            const cover = this.attr(root, fields.detailCover, fields.detailCoverAttr);
            return {title:this.required(this.text(root,fields.detailTitle)),subtitle,description,
                cover:this.absolute(cover,request),tags:tags.length ? {Genre:tags} : {}};
        });
    };
    loadChapters = async id => {
        const fields = this.config.details.fields;
        const url = this.pageUrl(id, fields.detailsBase === "mobile");
        return this.html(url, (doc, request) => {
            let rows = doc.querySelectorAll(this.config.chapters.selector).map(el => {
                const link = el.querySelector("a");
                const href = link ? this.attr(link, null, "href") : "";
                const title = link ? this.text(link) : "";
                return href && title ? {id:this.sourceId(href,request),title} : null;
            }).filter(Boolean);
            rows = this.unique(rows);
            if (this.config.chapters.order === "newest-first") rows.reverse();
            return this.chaptersObject(rows);
        });
    };
    rawReader = async (url, allowServerError = false) => {
        const res = await Network.get(url, this.headers);
        if (res.status !== 200 && !(allowServerError && res.status === 500)) throw new Error("HTTP " + res.status);
        return String(res.body || "");
    };
    decodeMiaoqu = (body, epId) => {
        const cid = Number(String(epId).match(/(\d+)\.html(?:[?#].*)?$/)?.[1]);
        if (!Number.isSafeInteger(cid)) throw new Error("Invalid Miaoqu chapter identity");
        const match = body.match(/var\s+DATA\s*=\s*'([^']+)'/);
        if (!match) throw new Error("Missing Miaoqu reader data");
        const keys = ["8-bXd9iN","8-RXyjry","8-oYvwVy","8-4ZY57U","8-mbJpU7","8-6MM2Ei","8-54TiQr","8-Ph5xx9","8-bYgePR","8-Z9A3bW"];
        const key = keys[cid % 10], bytes = new Uint8Array(Convert.decodeBase64(match[1]));
        for (let i=0;i<bytes.length;i++) bytes[i] ^= key.charCodeAt(i & 7);
        const decoded = Convert.decodeUtf8(Convert.decodeBase64(Convert.decodeUtf8(bytes.buffer)));
        return this.array(JSON.parse(decoded)).map(item => this.required(item.url));
    };
    decodeSixmh = body => {
        const match = body.match(/params\s*=\s*'([A-Za-z0-9+/=]+)'/);
        if (!match) throw new Error("Missing SixMH reader data");
        const raw = new Uint8Array(Convert.decodeBase64(match[1]));
        if (raw.length <= 16 || (raw.length - 16) % 16) throw new Error("Malformed SixMH reader data");
        const decrypted = new Uint8Array(Convert.decryptAesCbc(raw.slice(16).buffer, Convert.encodeUtf8("9S8$vJnU2ANeSRoF"), raw.slice(0,16).buffer));
        const padding = decrypted[decrypted.length - 1];
        if (padding < 1 || padding > 16 || padding > decrypted.length) throw new Error("Invalid SixMH padding");
        for (let i=decrypted.length-padding;i<decrypted.length;i++) if (decrypted[i] !== padding) throw new Error("Invalid SixMH padding");
        const data = JSON.parse(Convert.decodeUtf8(decrypted.slice(0,-padding).buffer));
        return this.array(data.images).map(value => this.required(value));
    };
    images = async (comicId, epId) => {
        const decoder = this.config.pages.decoder;
        const mobile = decoder === "miaoqu-xor-base64";
        const url = this.pageUrl(epId, mobile);
        if (decoder === "html-lazy") return this.html(url, (doc, request) =>
            this.imageList(doc.querySelectorAll(this.config.pages.selector).map(el => this.attr(el,null,this.config.pages.fields.imageUrl)),request));
        const body = await this.rawReader(url, mobile);
        const values = decoder === "miaoqu-xor-base64" ? this.decodeMiaoqu(body,epId) : this.decodeSixmh(body);
        return this.imageList(values,url);
    };

}
