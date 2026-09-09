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
ENABLED = {"all.globalcomix", "all.namicomi", "zh.dongmanmanhua", "zh.iqiyi", "all.yellownote", "all.mangadex"}


def candidate_contract(candidate, commit):
    if commit != PIN or candidate.get("project") != "keiyoushi/extensions-source":
        return None
    module = candidate.get("module")
    if module not in ENABLED:
        return None
    for expected in MANIFEST["families"][module]["candidates"]:
        if candidate == expected:
            return module.split(".")[-1] + "-v1"
    return None


def adapter_name(candidate):
    for module in sorted(ENABLED):
        for expected in MANIFEST["families"][module]["candidates"]:
            if all(candidate.get(k) == expected.get(k) for k in
                   ("project", "module", "sourceId", "upstreamLang")):
                return module.split(".")[-1]
    return None


def operation_contract(family, locale, base):
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
                         "order": "volume desc, chapter desc"},
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
                         "pagination": {"nextSelector": "div.paginate a[onclick] + a"}, "order": "response"},
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
                        "latest": {"url": api + "/chapter", "method": "GET"}},
            "search": {"url": api + "/manga", "method": "GET",
                       "query": {"availableTranslatedLanguage[]": "zh-hk" if locale == "zh-Hant" else "zh"},
                       "pagination": {"limit": 20, "offset": "(page-1)*20", "hasNext": "limit+offset < total"}},
            "details": {"url": api + "/manga/{comicId}", "method": "GET", "fields": {"title": "data.attributes.title", "description": "data.attributes.description"}},
            "chapters": {"url": api + "/manga/{comicId}/feed", "method": "GET",
                         "pagination": {"limit": 500, "offset": 0, "hasNext": "limit+offset < total"},
                         "access": "exclude future/empty/unavailable; reject external chapter with zero pages", "order": "volume desc, chapter desc"},
            "pages": {"url": api + "/at-home/server/{chapterId}", "method": "GET",
                      "fields": {"imageUrl": "baseUrl/data/{chapter.hash}/{chapter.data[]}"},
                      "refresh": "at-home server after 300000 milliseconds", "order": "response"}}
    raise ValueError("Unknown reviewed family")


def make_ir(candidate, timestamp):
    family = candidate["module"].split(".")[-1]
    if candidate_contract(candidate, PIN) is None:
        raise ValueError("Candidate has no reviewed family contract")
    locale = candidate.get("canonicalLocale", candidate["upstreamLang"])
    base = candidate["baseUrl"]
    ir = {
        "schemaVersion": "0.2", "id": "keiyoushi_" + candidate["sourceId"],
        "name": candidate["name"], "languages": [locale], "contentOrigins": [],
        "contentWarning": candidate["contentWarning"],
        "sourceType": "api" if family in {"globalcomix", "namicomi", "mangadex"} else "hybrid" if family == "iqiyi" else "html",
        "baseUrl": base, "mobileUrl": base, "requiresAuth": False, "requiresWebView": False,
        "familyContract": family + "-v1",
        "headers": {"Referer": base + "/", "Origin": base},
        **operation_contract(family, locale, base),
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
    locale = candidate.get("canonicalLocale", candidate["upstreamLang"])
    if language_override is not None and language_override != locale:
        raise ValueError("Family locale override conflicts with upstream identity")
    timestamp = timestamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return make_ir(candidate, timestamp)
