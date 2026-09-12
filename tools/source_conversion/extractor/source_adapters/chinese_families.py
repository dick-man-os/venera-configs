"""Closed, exact-upstream extraction contracts for reviewed Chinese instances.

No Kotlin or downloaded JavaScript is executed. Other instances and pins retain
their existing dispatch until separately reviewed.
"""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

MANIFEST = json.loads(Path(__file__).with_name("chinese_contracts.json").read_text(encoding="utf-8"))
PIN = MANIFEST["commit"]
MCCMS_MODULES = {"zh.manhuawu", "zh.miaoqu", "zh.sixmh"}
MANGA18_MODULES = {"zh.hanman18"}
ENABLED = {
    "all.globalcomix", "all.namicomi", "zh.dongmanmanhua", "zh.iqiyi",
    "all.yellownote", "all.mangadex", *MCCMS_MODULES, *MANGA18_MODULES,
    "zh.guazimanhua", "zh.terrahistoricus", "zh.bh3",
}


def family_name(module):
    if module in MCCMS_MODULES:
        return "mccms"
    if module in MANGA18_MODULES:
        return "manga18"
    return module.split(".")[-1]


def reviewed_locale(candidate):
    entry = MANIFEST["families"][candidate["module"]]
    return entry.get("canonicalLocale", candidate.get("canonicalLocale", candidate["upstreamLang"]))


def candidate_contract(candidate, commit):
    if commit != PIN or candidate.get("project") != "keiyoushi/extensions-source":
        return None
    module = candidate.get("module")
    if module not in ENABLED:
        return None
    for expected in MANIFEST["families"][module]["candidates"]:
        if candidate == expected:
            return family_name(module) + "-v1"
    return None


def adapter_name(candidate):
    for module in sorted(ENABLED):
        for expected in MANIFEST["families"][module]["candidates"]:
            if all(candidate.get(k) == expected.get(k) for k in
                   ("project", "module", "sourceId", "upstreamLang")):
                return family_name(module)
    return None


def operation_contract(family, locale, base, candidate=None):
    """Stable per-operation declarative evidence consumed by the family emitter."""
    lang = ({"zh-Hans": "cn", "zh-Hant": "zh"}[locale] if family == "globalcomix"
            else locale.lower())
    if family == "globalcomix":
        api = "https://api.globalcomix.com/v1"
        return {
            "explore": {
                "popular": {"url": api + "/comics", "method": "GET"},
                "latest": {"url": api + "/comics", "method": "GET"}},
            "search": {"url": api + "/comics", "method": "GET",
                       "query": {"lang_id[]": lang}, "pagination": {"page": "p", "hasNext": "payload.pagination.page < payload.pagination.total_pages", "maxPage": "max(1, payload.pagination.total_pages)"}},
            "details": {"url": api + "/read/{slug}", "method": "GET", "fields": {"title": "payload.results.name", "thumbnail": "payload.results.image_url"}},
            "chapters": {"url": api + "/comics/{comicId}/releases", "method": "GET",
                         "query": {"lang_id": lang, "all": "true"}, "listPath": "payload.results",
                         "access": "exclude premium_only == 1", "order": "response"},
            "pages": {"url": api + "/readV2/{chapterId}", "method": "GET",
                      "listPath": "payload.results.page_objects", "fields": {"imageUrl": "desktop_image_url"},
                      "access": "reject paid chapter or any paid page", "order": "response"}}
    if family == "namicomi":
        api = "https://api.namicomi.com"
        return {
            "explore": {"popular": {"url": api + "/title/search", "method": "GET"}, "latest": {"url": api + "/title/search", "method": "GET"}},
            "search": {"url": api + "/title/search", "method": "GET", "query": {"availableTranslatedLanguages[]": lang},
                       "pagination": {"limit": 20, "offset": "(page-1)*20", "hasNext": "meta.limit + meta.offset < meta.total", "maxPage": "max(1, ceil(meta.total / meta.limit))"}},
            "details": {"url": api + "/title/{comicId}", "method": "GET", "fields": {"title": "data.attributes.title", "description": "data.attributes.description"}},
            "chapters": {"url": api + "/chapter", "method": "GET", "query": {"translatedLanguages[]": lang},
                         "pagination": {"limit": 200, "offset": 0, "hasNext": "meta.limit + meta.offset < meta.total"},
                         "access": {"url": api + "/gating/check", "method": "POST", "chunkSize": 200, "allow": "data.attributes.map[id] === true"},
                         "order": "oldest first; reverse complete volume desc, chapter desc response"},
            "pages": {"url": api + "/images/chapter/{chapterId}?newQualities=true", "method": "GET",
                      "fields": {"imageUrl": "data.baseUrl/chapter/{chapterId}/{data.hash}/source/{data.source[].filename}"},
                      "access": "gating check and HTTP 402 rejection", "order": "response"}}
    if family == "dongmanmanhua":
        return {
            "explore": {"popular": {"url": base + "/dailySchedule", "method": "GET", "maxPage": 1},
                        "latest": {"url": base + "/dailySchedule?sortOrder=UPDATE&webtoonCompleteType=ONGOING", "method": "GET", "maxPage": 1}},
            "search": {"url": base + "/search", "method": "GET",
                       "selector": "#content > div.card_wrap.search ul:not(#filterLayer) li a",
                       "pagination": {"nextSelector": "div.more_area, div.paginate a[onclick] + a"}},
            "details": {"url": "{comicId}", "method": "GET", "fields": {"title": "h1.subj, h3.subj", "description": "#_asideDetail p.summary"}},
            "chapters": {"url": "{comicId}", "method": "GET", "selector": "ul#_listUl li",
                         "pagination": {"nextSelector": "div.paginate a[onclick] + a"}, "order": "oldest first; reverse complete newest-first response"},
            "pages": {"url": "{chapterId}", "method": "GET", "selector": "div#_imageList > img", "fields": {"imageUrl": "@data-url"}, "order": "response"}}
    if family == "iqiyi":
        return {
            "explore": {"popular": {"url": base + "/category/全部_-1_-1_9_{page}/", "method": "GET"},
                        "latest": {"url": base + "/category/全部_-1_-1_4_{page}/", "method": "GET"}},
            "search": {"url": base + "/search-keyword={query}_{page}", "method": "GET", "selector": "ul.stacksList > li.stacksBook",
                       "pagination": {"nextSelector": "div.mod-page > a.a1", "textContains": "下一页"}},
            "details": {"url": "{comicId}", "method": "GET", "fields": {"title": "div.detail-tit > h1", "description": "p.detail-docu"}},
            "chapters": {"url": base + "/catalog/{detailId}/", "method": "GET", "isJson": True, "listPath": "data.episodes", "reverse": True,
                         "fields": {"url": "/reader/{comicId}_{episodeId}.html", "name": "{episodeOrder} {episodeTitle}"}},
            "pages": {"url": "{chapterId}", "method": "GET", "selector": "ul.main-container > li.main-item > img",
                      "fields": {"imageUrl": "@data-original, fallback @src"}, "access": "reject div.main > p.pay-title", "order": "response"}}
    if family == "yellownote":
        return {
            "explore": {"popular": {"url": base + "/photos/sort-hot/{page}.html", "method": "GET"},
                        "latest": {"url": base + "/photos/{page}.html", "method": "GET"}},
            "search": {"url": base + "/photos/keyword-{query}/{page}.html", "method": "GET",
                       "selector": "div.list.photo-list > div.item.photo, div.list.amateur-list > div.item.amateur",
                       "pagination": {"nextSelector": "div.pager:first-of-type > a.pager-next"}},
            "details": {"url": "{comicId}", "method": "GET", "selector": "div.info-card.photo-detail"},
            "chapters": {"url": "{comicId}", "method": "GET", "synthetic": "last pager number down to 1", "order": "descending page"},
            "pages": {"url": "{chapterId}", "method": "GET",
                      "selector": "div.list.photo-items > div.item.photo-image, div.list.amateur-items > div.item.amateur-image",
                      "fields": {"imageUrl": "div.img background-image URL; original quality _600x0.webp -> .jpg"}, "order": "response"}}
    if family == "mangadex":
        api = "https://api.mangadex.org"
        return {
            "explore": {"popular": {"url": api + "/manga", "method": "GET"},
                        "latest": {"url": api + "/chapter", "method": "GET",
                                   "pagination": {"limit": 100, "offset": "(page-1)*100", "hasNext": "limit+offset < total", "maxPage": "max(1, ceil(total / limit))"}}},
            "search": {"url": api + "/manga", "method": "GET",
                       "query": {"availableTranslatedLanguage[]": "zh-hk" if locale == "zh-Hant" else "zh"},
                       "pagination": {"limit": 20, "offset": "(page-1)*20", "hasNext": "limit+offset < total", "maxPage": "max(1, ceil(total / limit))"}},
            "details": {"url": api + "/manga/{comicId}", "method": "GET", "fields": {"title": "data.attributes.title", "description": "data.attributes.description"}},
            "chapters": {"url": api + "/manga/{comicId}/feed", "method": "GET",
                         "pagination": {"limit": 500, "offset": 0, "hasNext": "limit+offset < total"},
                         "access": "exclude future/empty/unavailable; reject external chapter with zero pages", "order": "oldest first; reverse complete volume desc, chapter desc response"},
            "pages": {"url": api + "/at-home/server/{chapterId}", "method": "GET",
                      "fields": {"imageUrl": "baseUrl/data/{chapter.hash}/{chapter.data[]}"},
                      "refresh": "at-home server after 300000 milliseconds", "order": "response"}}
    if family == "mccms":
        source_id = candidate["sourceId"] if candidate else None
        variants = {
            "3279300917142951720": {
                "variant": "default", "listing": ".common-comic-item",
                "title": ".comic__title > a", "cover": "img", "coverAttr": "data-original",
                "detailsRoot": ".de-info__box", "detailTitle": ".comic-title",
                "detailCover": "img", "detailCoverAttr": "src", "detailAuthor": ".name",
                "detailDescription": ".intro-total", "detailTags": ".comic-status a",
                "chapters": ".chapter__list-box > li", "chapterName": "a",
                "chapterOrder": "oldest-first", "reader": "html-lazy",
                "readerSelector": "img[data-original]", "readerAttr": "data-original",
                "detailsBase": "desktop", "pagination": "paired-links"},
            "116946528518438525": {
                "variant": "miaoqu", "listing": "#mangawrap > li",
                "title": ".manga-name", "link": "a", "cover": "a",
                "coverAttr": "style-background-url", "detailsRoot": ".infobox",
                "detailTitle": ".title", "detailCover": "img", "detailCoverAttr": "src",
                "detailDescription": ".text", "detailTags": ".tage",
                "chapters": "ul.list > li", "chapterName": "a",
                "chapterOrder": "oldest-first", "reader": "miaoqu-xor-base64",
                "detailsBase": "mobile", "pagination": "next-id"},
            "5183325399429659419": {
                "variant": "sixmh", "listing": "div.cy_list_mh ul",
                "title": "li.title > a", "cover": "img", "coverAttr": "src",
                "detailsRoot": "div.cy_info", "detailTitle": "div.cy_title",
                "detailCover": "div.cy_info_cover > a > img.pic", "detailCoverAttr": "src",
                "detailAuthor": "div.cy_xinxi span:first-child > a",
                "detailDescription": "div.cy_desc #comic-description",
                "detailTags": "div.cy_xinxi:nth-child(2) span:first-child > a",
                "chapters": "ul#mh-chapter-list-ol-0 li.chapter__item", "chapterName": "a",
                "chapterOrder": "newest-first", "reader": "sixmh-aes-cbc",
                "detailsBase": "desktop", "pagination": "paired-links"},
        }
        fields = variants.get(source_id)
        if fields is None:
            raise ValueError("Unknown reviewed MCCMS candidate")
        return {
            "explore": {
                "popular": {"url": base + "/category/order/hits/page/{page}", "method": "GET"},
                "latest": {"url": base + "/category/order/addtime/page/{page}", "method": "GET"}},
            "search": {"url": base + "/search/{query}/{page}", "method": "GET",
                       "selector": fields["listing"],
                       "pagination": {"mode": fields["pagination"]}, "fields": fields},
            "details": {"url": "{comicId}", "method": "GET", "selector": fields["detailsRoot"],
                        "fields": fields},
            "chapters": {"url": "{comicId}", "method": "GET", "selector": fields["chapters"],
                         "fields": {"name": fields["chapterName"]}, "order": fields["chapterOrder"]},
            "pages": {"url": "{chapterId}", "method": "GET", "decoder": fields["reader"],
                      "selector": fields.get("readerSelector", ""),
                      "fields": {"imageUrl": fields.get("readerAttr", "")}, "order": "response"}}
    if family == "manga18":
        fields = {
            "listing": "div.story_item", "title": "div.mg_info > div.mg_name a",
            "link": "div.mg_info > div.mg_name a", "cover": "img", "coverAttr": "src",
            "infoRoot": "div.detail_listInfo", "detailTitle": "div.detail_name > h1",
            "detailCover": "div.detail_avatar > img", "detailCoverAttr": "src",
            "detailDescription": "div.detail_reviewContent",
            "detailTags": "div.info_value > a[href*=\"/manga-list/\"]",
            "chapters": "div.chapter_box .item", "chapterOrder": "newest-first",
            "reader": "slides-path-base64", "rejectDirectoryUrls": True,
        }
        return {
            "explore": {
                "popular": {"url": base + "/list-manga/{page}?order_by=views", "method": "GET"},
                "latest": {"url": base + "/list-manga/{page}", "method": "GET"}},
            "search": {"url": base + "/list-manga/{page}?search={query}", "method": "GET",
                       "selector": fields["listing"],
                       "pagination": {"nextSelector": ".pagination > li:last-child:not(.active)"},
                       "fields": fields},
            "details": {"url": "{comicId}", "method": "GET", "selector": fields["infoRoot"],
                        "fields": fields},
            "chapters": {"url": "{comicId}", "method": "GET", "selector": fields["chapters"],
                         "order": fields["chapterOrder"]},
            "pages": {"url": "{chapterId}", "method": "GET", "decoder": fields["reader"],
                      "rejectDirectoryUrls": True, "order": "response"}}
    if family == "guazimanhua":
        return {
            "explore": {"popular": {"url": base + "/category.php?sort=hits&page={page}", "method": "GET"},
                        "latest": {"url": base + "/category.php?sort=update&page={page}", "method": "GET"}},
            "search": {"url": base + "/category.php", "method": "GET", "selector": "article.card",
                       "pagination": {"nextSelector": "nav.pager a", "nextText": ">", "maxPage": "same-query numeric pager links"}},
            "details": {"url": "{comicId}", "method": "GET", "fields": {"title": "div.mobile-comic-title", "cover": "img.mobile-comic-cover[src]", "description": "p.mobile-comic-desc"}},
            "chapters": {"url": "{comicId}", "method": "GET", "selector": "section.mobile-comic-all-chapters div.mobile-chapter-grid a", "order": "newest-first; dedupe then reverse"},
            "pages": {"url": "{chapterId}", "method": "GET", "selector": "section.reader-images img", "fields": {"imageUrl": "src"}, "order": "response"}}
    if family == "terrahistoricus":
        return {
            "explore": {"popular": {"url": base + "/api/comic", "method": "GET"},
                        "latest": {"url": base + "/api/recentUpdate", "method": "GET"}},
            "search": {"url": base + "/api/comic", "method": "GET", "topics": ["terra-historicus", "talos-ii-historicus"],
                       "filter": "native title over both complete topic catalogs", "pagination": {"maxPage": 1}},
            "details": {"url": "{comicId}", "method": "GET", "fields": {"title": "data.title", "cover": "data.cover", "description": "data.subtitle + data.introduction"}},
            "chapters": {"url": "{comicId}", "method": "GET", "listPath": "data.episodes", "identity": "opaque string cid", "order": "newest-first; dedupe then reverse"},
            "pages": {"url": "{chapterId}", "method": "GET", "listPath": "data.pageInfos", "fields": {"imageUrl": "{chapterId}/page?pageNum={1-based index}"}, "resolution": "async onImageLoad: code0 data.url; no signed URL persistence", "order": "response"}}
    if family == "bh3":
        return {
            "explore": {"popular": {"url": base + "/book", "method": "GET", "maxPage": 1}},
            "search": {"url": base + "/book", "method": "GET", "selector": "a[href*=book]", "filter": "normalized native title over complete finite catalog", "pagination": {"maxPage": 1}},
            "details": {"url": "{comicId}", "method": "GET", "fields": {"title": "div.title", "cover": "img.cover[src]", "description": "div.detail_info1"}},
            "chapters": {"url": "{comicId}/get_chapter", "method": "GET", "isJson": True, "listPath": "$", "identity": "bookid/chapterid strings", "order": "newest-first; dedupe then reverse"},
            "pages": {"url": "{chapterId}", "method": "GET", "selector": "img.lazy.comic_img", "fields": {"imageUrl": "data-original"}, "order": "response"}}
    raise ValueError("Unknown reviewed family")


def make_ir(candidate, timestamp):
    family = family_name(candidate["module"])
    if candidate_contract(candidate, PIN) is None:
        raise ValueError("Candidate has no reviewed family contract")
    locale = reviewed_locale(candidate)
    base = candidate["baseUrl"]
    display_name = candidate["name"]
    if family in {"mangadex", "namicomi"}:
        display_name += "（" + {"zh-Hant": "繁體中文", "zh-Hans": "简体中文"}[locale] + "）"
    ir = {
        "schemaVersion": "0.2", "id": "keiyoushi_" + candidate["sourceId"],
        "name": display_name, "languages": [locale], "contentOrigins": [],
        "contentWarning": candidate["contentWarning"],
        "sourceType": "api" if family in {"globalcomix", "namicomi", "mangadex", "terrahistoricus"} else "hybrid" if family in {"iqiyi", "bh3"} else "html",
        "baseUrl": base, "mobileUrl": base.replace("//www.", "//m.") if family == "mccms" else base,
        "requiresAuth": False, "requiresWebView": False,
        "familyContract": family + "-v1",
        "headers": {"Referer": base + "/", "Origin": base},
        **operation_contract(family, locale, base, candidate),
        "provenance": {
            "type": "converted", "upstreamProject": "keiyoushi",
            "upstreamPackage": "eu.kanade.tachiyomi.extension." + candidate["module"],
            "upstreamSourceId": candidate["sourceId"], "upstreamCommit": PIN,
            "upstreamVersion": candidate["version"], "upstreamLicense": "Apache-2.0",
            "converterVersion": "0.1.0", "generatedTimestamp": timestamp}}
    if family == "globalcomix":
        ir["headers"].update({"x-gc-client": "gck_d0f170d5729446dcb3b55e6b3ebc7bf6", "x-gc-identmode": "cookie"})
    if family == "iqiyi":
        ir["headers"]["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    if family == "mccms":
        ir["headers"] = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"}
    if family in {"manga18", "terrahistoricus", "bh3"}:
        ir["headers"] = {"Referer": base + "/"}
    if family == "guazimanhua":
        ir["headers"] = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
    return ir


def validate_contract(ir):
    """Reject altered/partial contracts rather than silently ignoring IR fields."""
    key = ir.get("familyContract")
    if not isinstance(key, str):
        return ["familyContract must be a reviewed string"]
    provenance = ir.get("provenance")
    if not isinstance(provenance, dict):
        return ["Reviewed family provenance must be an object"]
    for module in sorted(ENABLED):
        for candidate in MANIFEST["families"][module]["candidates"]:
            if candidate["sourceId"] != provenance.get("upstreamSourceId"):
                continue
            expected = make_ir(candidate, provenance.get("generatedTimestamp"))
            # Local artifact/version belong to the explicit publication plan.
            actual = {k: v for k, v in ir.items() if k not in {"artifactId", "version"}}
            return [] if actual == expected else ["Reviewed family contract does not match exact candidate/operations/provenance"]
    return ["Unknown reviewed family candidate"]


def extract(extensions_root, source_path, timestamp=None, language_override=None, source_id=None):
    module = source_path.replace("\\", "/").replace("/", ".")
    if module not in ENABLED:
        raise ValueError("Unreviewed family")
    root = Path(extensions_root)
    commit = subprocess.check_output(["git", "-c", "safe.directory=" + root.resolve().as_posix(), "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if commit != PIN:
        raise ValueError("Family contract requires exact reviewed upstream pin")
    entry = MANIFEST["families"][module]
    for rel, digest in entry["files"].items():
        if hashlib.sha256((root / rel).read_bytes()).hexdigest() != digest:
            raise ValueError("Family contract source drift: " + rel)
    matches = [c for c in entry["candidates"] if c["sourceId"] == str(source_id)]
    if len(matches) != 1:
        raise ValueError("Exact reviewed source ID required")
    candidate = matches[0]
    locale = reviewed_locale(candidate)
    if language_override is not None and language_override != locale:
        raise ValueError("Family locale override conflicts with upstream identity")
    timestamp = timestamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return make_ir(candidate, timestamp)
