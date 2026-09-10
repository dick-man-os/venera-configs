// Converted from the exact upstream commit in config.provenance.
// Apache-2.0 upstream; bounded family contract. No downloaded code is executed.
class Keiyoushi1493666528525752601Source extends ComicSource {
    name = "MangaDex（繁體中文）";
    key = "keiyoushi_1493666528525752601";
    version = "1.0.1";
    minAppVersion = "1.6.0";
    url = "";
    config = {"schemaVersion":"0.2","id":"keiyoushi_1493666528525752601","name":"MangaDex（繁體中文）","languages":["zh-Hant"],"contentOrigins":[],"contentWarning":"MIXED","sourceType":"api","baseUrl":"https://mangadex.org","mobileUrl":"https://mangadex.org","requiresAuth":false,"requiresWebView":false,"familyContract":"mangadex-v1","headers":{"Referer":"https://mangadex.org/","Origin":"https://mangadex.org"},"explore":{"popular":{"url":"https://api.mangadex.org/manga","method":"GET"},"latest":{"url":"https://api.mangadex.org/chapter","method":"GET","pagination":{"limit":100,"offset":"(page-1)*100","hasNext":"limit+offset < total","maxPage":"max(1, ceil(total / limit))"}}},"search":{"url":"https://api.mangadex.org/manga","method":"GET","query":{"availableTranslatedLanguage[]":"zh-hk"},"pagination":{"limit":20,"offset":"(page-1)*20","hasNext":"limit+offset < total","maxPage":"max(1, ceil(total / limit))"}},"details":{"url":"https://api.mangadex.org/manga/{comicId}","method":"GET","fields":{"title":"data.attributes.title","description":"data.attributes.description"}},"chapters":{"url":"https://api.mangadex.org/manga/{comicId}/feed","method":"GET","pagination":{"limit":500,"offset":0,"hasNext":"limit+offset < total"},"access":"exclude future/empty/unavailable; reject external chapter with zero pages","order":"oldest first; reverse complete volume desc, chapter desc response"},"pages":{"url":"https://api.mangadex.org/at-home/server/{chapterId}","method":"GET","fields":{"imageUrl":"baseUrl/data/{chapter.hash}/{chapter.data[]}"},"refresh":"at-home server after 300000 milliseconds","order":"response"},"provenance":{"type":"converted","upstreamProject":"keiyoushi","upstreamPackage":"eu.kanade.tachiyomi.extension.all.mangadex","upstreamSourceId":"1493666528525752601","upstreamCommit":"5a0261c718cd6d5ecf14963d837f29024c792398","upstreamVersion":"1.4.212","upstreamLicense":"Apache-2.0","converterVersion":"0.1.0","generatedTimestamp":"2026-09-09T00:00:00Z"},"artifactId":"mangadex_zh_hant","version":"1.0.1"};
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
    dexLocale = () => this.locale === "zh-Hant" ? "zh-hk" : "zh";
    uuid = value => {
        const id = String(value).replace(/^\/(?:manga|chapter)\//,"");
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) throw new Error("Invalid MangaDex UUID");
        return id;
    };
    rating = () => ["safe","suggestive"].map(value=>["contentRating[]",value]);
    allRatings = () => ["safe","suggestive","erotica","pornographic"].map(value=>["contentRating[]",value]);
    blockedGroups = () => [
        "5fed0576-8b94-4f9a-b6a7-08eecd69800d","06a9fecb-b608-4f19-b93c-7caab06b7f44",
        "8d8ecf83-8d42-4f8c-add8-60963f9f28d9","caa63201-4a17-4b7f-95ff-ed884a2b7e60",
        "319c1b10-cbd0-4f55-a46e-c4ee17e65139","4f1de6a2-f0c5-4ac5-bce5-02c7dbb67deb"
    ].map(id=>["excludedGroups[]",id]);
    manga = item => {
        const id=this.uuid(item.id), a=item.attributes, lang=this.dexLocale();
        if (!a?.title || typeof a.title !== "object") throw new Error("Missing title");
        const title = a.title[lang] ?? (a.altTitles || []).find(t=>t[lang])?.[lang] ?? Object.values(a.title)[0] ?? (a.altTitles || []).find(t=>t.en)?.en;
        const rel=this.array(item.relationships || []);
        const file=rel.find(r=>r.type === "cover_art")?.attributes?.fileName;
        const authors=[...new Set(rel.filter(r=>r.type === "author" || r.type === "artist").map(r=>r.attributes?.name).filter(Boolean))];
        return new Comic({id:"/manga/"+id,title:this.required(title),
            cover:file ? "https://uploads.mangadex.org/covers/"+id+"/"+encodeURIComponent(file) : "",
            description:a.description?.[lang] ?? a.description?.en ?? "",subtitle:authors.join(", ")});
    };
    pagination = (body, offset) => {
        if (!body || !Number.isSafeInteger(body.limit) || body.limit <= 0 || body.offset !== offset ||
            !Number.isSafeInteger(body.total) || body.total < 0) throw new Error("Invalid MangaDex pagination");
        return body.offset+body.limit < body.total;
    };
    catalogPagination = (body, offset, size) => {
        const hasMore=this.pagination(body,offset);
        if (body.limit !== size) throw new Error("Unexpected MangaDex page size");
        return {hasMore,maxPage:Math.max(1,Math.ceil(body.total/size))};
    };
    catalog = async (kind, keyword, page) => {
        const lang=this.dexLocale(), offset=(page-1)*(kind === "latest" ? 100 : 20);
        if (kind === "latest") {
            const body=await this.json(this.query("https://api.mangadex.org/chapter",[
                ["offset",offset],["limit",100],["translatedLanguage[]",lang],["order[publishAt]","desc"],
                ["includeFutureUpdates",0],["includeFuturePublishAt",0],["includeEmptyPages",0],...this.rating(),...this.blockedGroups()]));
            if (body === null) return {comics:[],hasMore:false,maxPage:Math.max(1,page-1)};
            const pagination=this.catalogPagination(body,offset,100);
            const ids=[...new Set(this.array(body.data).flatMap(c=>this.array(c.relationships || []))
                .filter(r=>r.type === "manga").map(r=>this.uuid(r.id)))];
            if (!ids.length) return {comics:[],...pagination};
            const titles=await this.json(this.query(this.config.search.url,[["includes[]","cover_art"],["limit",ids.length],
                ...this.rating(),...ids.map(id=>["ids[]",id])]));
            const map=new Map(this.array(titles?.data).map(m=>[m.id,m]));
            return {comics:ids.filter(id=>map.has(id)).map(id=>this.manga(map.get(id))),...pagination};
        }
        const params=[["limit",20],["offset",offset],["includes[]","cover_art"],
            ["availableTranslatedLanguage[]",lang],...this.rating()];
        params.push(["order["+(kind === "popular" ? "followedCount" : "relevance")+"]","desc"]);
        if (kind === "search" && keyword.trim()) params.push(["title",keyword.replace(/\s/g," ").trim()]);
        const body=await this.json(this.query(this.config.search.url,params));
        if (body === null) return {comics:[],hasMore:false,maxPage:Math.max(1,page-1)};
        return {comics:this.unique(this.array(body.data).map(this.manga)),...this.catalogPagination(body,offset,20)};
    };
    info = async id => {
        const uuid=this.uuid(id);
        const body=await this.json(this.query(this.config.details.url.replace("{comicId}",uuid),
            [["includes[]","cover_art"],["includes[]","author"],["includes[]","artist"]]));
        if (body?.data?.id !== uuid) throw new Error("Comic identity mismatch");
        return this.manga(body.data);
    };
    loadChapters = async id => {
        const uuid=this.uuid(id), rows=[], seen=new Set();
        let offset=0, ended=false;
        for(let pass=0;pass<1000;pass++) {
            const body=await this.json(this.query(this.config.chapters.url.replace("{comicId}",uuid),[
                ["includes[]","scanlation_group"],["includes[]","user"],["limit",500],["offset",offset],
                ["translatedLanguage[]",this.dexLocale()],["order[volume]","desc"],["order[chapter]","desc"],
                ["includeFuturePublishAt",0],["includeEmptyPages",0],["includeUnavailable",0],...this.allRatings()]));
            if(body === null) { if(offset) throw new Error("Incomplete chapter pagination"); ended=true; break; }
            const data=this.array(body.data), more=this.pagination(body,offset);
            const before=seen.size;
            for(const chapter of data) seen.add(this.uuid(chapter.id));
            if((offset || more) && seen.size === before) throw new Error("Non-progressing chapter pagination");
            rows.push(...data);
            if(!more) { ended=true; break; }
            if(!data.length) throw new Error("Non-progressing chapter pagination");
            offset+=body.limit;
        }
        if(!ended) throw new Error("Chapter traversal bound exceeded");
        // Preserve upstream decimal/special/volume ordering, inverted only after all pages.
        return this.chaptersObject(this.unique(rows).reverse().filter(c=>{
            if(!c.attributes) throw new Error("Missing chapter attributes");
            return !c.attributes.isUnavailable && !(c.attributes.externalUrl != null && c.attributes.pages === 0);
        }).map(c=>{
            const a=c.attributes, parts=[a.volume ? "Vol."+a.volume : "",a.chapter ? "Ch."+a.chapter : ""].filter(Boolean);
            if(a.title) { if(parts.length) parts.push("-"); parts.push(a.title); }
            return {id:"/chapter/"+this.uuid(c.id),title:parts.join(" ")};
        }));
    };
    pageServers = new Map();
    server = async epId => {
        const id=this.uuid(epId), old=this.pageServers.get(id);
        if(old && Date.now()-old.time <= 300000) return old;
        const body=await this.json(this.config.pages.url.replace("{chapterId}",id));
        if(!body?.chapter) throw new Error("Missing page-server data");
        const value={time:Date.now(),base:this.absolute(this.required(body.baseUrl)).replace(/\/$/,""),
            hash:this.required(body.chapter.hash),files:this.array(body.chapter.data)};
        this.pageServers.set(id,value);
        return value;
    };
    images = async (comicId,epId) => {
        this.uuid(comicId);
        this.pageServers.delete(this.uuid(epId));
        const data=await this.server(epId);
        return data.files.map(file=>data.base+"/data/"+encodeURIComponent(data.hash)+"/"+encodeURIComponent(this.required(file)));
    };
    refreshImage = async (url,comicId,epId) => {
        const data=await this.server(epId), suffix=String(url).match(/\/data\/[^/]+\/[^/?#]+$/)?.[0];
        if(!suffix) throw new Error("Invalid MangaDex image URL");
        return {url:data.base+suffix,headers:this.headers};
    };
    init() { this.comic.onImageLoad=(url,comicId,epId)=>this.refreshImage(url,comicId,epId); }

}
