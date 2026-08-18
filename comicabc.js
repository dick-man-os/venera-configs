/**
 * @file zh-Hant_comicabc.base.js
 * Generated automatically by Venera Source Converter v0.1.0
 *
 * Upstream Project: keiyoushi
 * Upstream Package: eu.kanade.tachiyomi.extension.zh.comicabc
 * Upstream Commit:  5e06c412c0264b18120fd963fdd6efb529f3fa29
 * Upstream Version: 1.0
 * Upstream License: Apache-2.0
 */

/** @type {import('./_venera_.js')} */

class ZhhantComicabcSource extends ComicSource {
    name = "Comicabc"
    key = "zh_Hant_comicabc"
    version = "1.0.0"
    minAppVersion = "1.6.0"

    static baseUrl = "https://www.8comic.com"
    static mobileUrl = "https://m.webtoons.com"

    static headers = {

    }

    // Explore / Discovery Sections
    explore = [
        {
            title: "Popular",
            type: "multiPageComicList",
            load: async (page) => {
                let res = await Network.get(`${ZhhantComicabcSource.baseUrl}/comic/h-{{page}}.html`, ZhhantComicabcSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load popular comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll(".container .row a.comicpic_col6");
                let comics = elements.map(el => new Comic({
                    id: (el.attributes['href'] || ''),
                    title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
                    cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
                }));
                doc.dispose();
                return {
                    comics: comics,
                    maxPage: 1,
                };
            }
        },
        {
            title: "Latest",
            type: "multiPageComicList",
            load: async (page) => {
                let res = await Network.get(`${ZhhantComicabcSource.baseUrl}/comic/u-{{page}}.html`, ZhhantComicabcSource.headers);
                if (res.status !== 200) {
                    throw new Error(`Failed to load latest comics, status: ${res.status}`);
                }
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll(".container .row .cat2_list a");
                let comics = elements.map(el => new Comic({
                    id: (el.attributes['href'] || ''),
                    title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
                    cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
                }));
                doc.dispose();
                return {
                    comics: comics,
                    maxPage: 1,
                };
            }
        }
    ]

    // Search
    search = {
        load: async (keyword, options, page) => {
            return await this.loadSearchCustom(keyword, options, page);
        }
    }

    // Comic Details and Reader Loading
    comic = {
        loadInfo: async (id) => {
            let url = id.startsWith("http") ? id : `${ZhhantComicabcSource.baseUrl}${id}`;
            let res = await Network.get(url, ZhhantComicabcSource.headers);
            if (res.status !== 200) {
                throw new Error(`Failed to load comic details, status: ${res.status}`);
            }
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector(".item_content_box .h2");
            let authorEl = doc.querySelector(".author") || doc.querySelector(".author_area");
            let descEl = doc.querySelector(".item_content_box .item_info_detail");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = (doc.querySelector('.item-cover img') ? (doc.querySelector('.item-cover img').attributes['src'] || '') : '');


            let chapters = await this.loadChapters(id);

            let comicDetails = new ComicDetails({
                title: title,
                subtitle: author,
                subTitle: author,
                cover: cover,
                description: description,
                tags: {},
                chapters: chapters,
            });

            comicDetails = this.parseDetailsCustom(comicDetails, doc);
            doc.dispose();
            return comicDetails;
        },

        loadEp: async (comicId, epId) => {
            return await this.loadEpCustom(comicId, epId);
        },

        onImageLoad: (url, comicId, epId) => {
            if (this.onImageLoadCustom) {
                return this.onImageLoadCustom(url, comicId, epId);
            }
            return {
                url: url,
                headers: {
                    ...ZhhantComicabcSource.headers,
                    "Referer": `${ZhhantComicabcSource.baseUrl}/`,
                },
            };
        },

        onThumbnailLoad: (url) => ({
            url: url,
            headers: {
                ...ZhhantComicabcSource.headers,
                "Referer": `${ZhhantComicabcSource.baseUrl}/`,
            },
        }),
    }

    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    loadSearchCustom = async (keyword, options, page) => {
        let url = `${ZhhantComicabcSource.baseUrl}/member/search.aspx?key=${encodeURIComponent(keyword)}&page=${page}`;
        let res = await Network.get(url, ZhhantComicabcSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load search results, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll(".container a.comicpic_col6");
        let comics = elements.map(el => new Comic({
            id: (el.attributes['href'] || ''),
            title: (el.querySelector('li.nowraphide') ? el.querySelector('li.nowraphide').text : ''),
            cover: (el.querySelector('img') ? (el.querySelector('img').attributes['src'] || '') : ''),
        }));
        let hasNextPage = doc.querySelector("div.pager a span.mdi-skip-next") !== null;
        doc.dispose();
        return {
            comics: comics,
            maxPage: hasNextPage ? page + 1 : page,
        };
    }

    parseDetailsCustom = (comicDetails, htmlDoc) => {
        let authorEl = htmlDoc.querySelector(".item_content_box .item-info-author");
        if (authorEl && authorEl.text) {
            let author = authorEl.text;
            if (author.includes("作者: ")) {
                author = author.substring(author.indexOf("作者: ") + 4).trim();
            } else if (author.includes("作者：")) {
                author = author.substring(author.indexOf("作者：") + 3).trim();
            } else if (author.includes("作者:")) {
                author = author.substring(author.indexOf("作者:") + 3).trim();
            }
            comicDetails.subtitle = author;
            comicDetails.subTitle = author;
        }

        let statusEl = htmlDoc.querySelector(".item_content_box .item-info-status");
        if (statusEl && statusEl.text) {
            let statusText = statusEl.text.trim();
            if (statusText === "連載中") {
                comicDetails.status = 1;
            } else if (statusText === "已完結") {
                comicDetails.status = 2;
            } else {
                comicDetails.status = 0;
            }
        }
        return comicDetails;
    }

    loadChapters = async (comicUrl) => {
        let url = comicUrl.startsWith("http") ? comicUrl : `${ZhhantComicabcSource.baseUrl}${comicUrl}`;
        let res = await Network.get(url, ZhhantComicabcSource.headers);
        if (res.status !== 200) {
            throw new Error(`Failed to load chapters, status: ${res.status}`);
        }
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("#chapters a, .comic_chapters a");

        let chaptersList = [];

        for (let el of elements) {
            let name = el.text || "";
            let onclick = el.attributes["onclick"] || "";
            let chapterUrl = "";

            if (onclick.includes("cview")) {
                let params = onclick.split("cview('")[1].split("'")[0];
                let comicId = params.split("-")[0];
                let chapterId = el.attributes["ch"] || (params.includes("-") ? params.replace('.html','').split("-")[1] : "1");

                if (!comicId || !chapterId) continue;

                chapterUrl = `${ZhhantComicabcSource.baseUrl}/view/${comicId}.html?ch=${chapterId}`;
            } else {
                let href = el.attributes["href"] || "";
                if (href.startsWith("http")) {
                    chapterUrl = href;
                } else if (href) {
                    if (href.startsWith("/")) {
                        chapterUrl = `${ZhhantComicabcSource.baseUrl}${href}`;
                    } else {
                        chapterUrl = href;
                    }
                }
            }
            if (chapterUrl) {
                chaptersList.push({ id: chapterUrl, title: name });
            }
        }

        chaptersList.reverse();
        let chaptersObj = {};
        for (let ch of chaptersList) {
            chaptersObj[ch.id] = ch.title;
        }

        doc.dispose();
        return chaptersObj;
    }

    loadEpCustom = async (comicId, epId) => {
        let url = epId.startsWith("http") ? epId : `${ZhhantComicabcSource.baseUrl}${epId}`;
        let pageListHeaders = {
            ...ZhhantComicabcSource.headers,
            "Referer": comicId.startsWith("http") ? comicId : `${ZhhantComicabcSource.baseUrl}/`
        };
        let res = await Network.get(url, pageListHeaders);
        if (res.status !== 200) {
            throw new Error(`Failed to load episode, status: ${res.status}`);
        }

        let html = res.body;

        let scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
        let match;
        let targetScriptContent = "";
        while ((match = scriptRegex.exec(html)) !== null) {
            if (match[1].includes("var ch=request")) {
                targetScriptContent = match[1];
                break;
            }
        }

        if (!targetScriptContent) {
            throw new Error("无法找到包含图片数据的脚本 (var ch=request)");
        }

        let scriptContent = targetScriptContent
            .replace(/document\.location/g, `'${url}'`);

        let srcMatch = scriptContent.match(/\.src\s*=\s*(unescape\(.*?\));/);
        let urlCreationLogic = "";

        scriptContent = scriptContent.split('spp();')[0];

        if (srcMatch) {
            urlCreationLogic = srcMatch[1].replace(/\bpg\b/g, 'p');
            // Remove the actual .src assignment to prevent it from failing if ge is weird
            scriptContent = scriptContent.replace(/\w+\([^)]+\)\.src\s*=\s*unescape\(.*?\);+/, "");
        } else {
            // Fallback for old spp() logic if they revert
            let matchVar = scriptContent.match(/var\s+([a-zA-Z0-9_]+)\s*=\s*['"].*?\.jpg['"]\s*;/);
            if (!matchVar) {
                throw new Error("Cannot find dynamic url variable");
            }
            urlCreationLogic = "eval(" + matchVar[1] + ")";
        }

        let J_JS_FUNCTIONS = `
function lc(l){if(l.length!=2)return l;var az="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";var a=l.substring(0,1);var b=l.substring(1,2);if(a=="Z")return 8000+az.indexOf(b);else return az.indexOf(a)*52+az.indexOf(b)}
function su(a,b,c){var e=(a+'').substring(b,b+c);return(e);}
function nn(n){return n<10?'00'+n:n<100?'0'+n:n;}
function mm(p){return(parseInt((p-1)/10)%10)+(((p-1)%10)*3)}
`;

        let scriptToExecute = `
var document = { getElementById: function() { return { style: {}, innerHTML: "", src: "" }; } };
${J_JS_FUNCTIONS}
${scriptContent}

var urls = [];
for (var p = 1; p <= ps; p++) {
    var imgUrl = ${urlCreationLogic};
    urls.push('https:' + imgUrl);
}
return urls;
`;
        let getUrls = new Function(scriptToExecute);
        let images = getUrls();

        return { images: images };
    }

    onImageLoadCustom = (url, comicId, epId) => {
        return {
            url: url,
            headers: {
                ...ZhhantComicabcSource.headers,
                "Referer": "https://articles.onemoreplace.tw/",
            }
        };
    }
}
