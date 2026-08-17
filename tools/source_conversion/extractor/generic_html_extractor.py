#!/usr/bin/env python3
import os
import re
from typing import Any, Dict, List, Optional
from common import kotlin_parser, selector_analyzer

def _map_language(lang: str, language_override: Optional[str] = None) -> List[str]:
    if language_override:
        return [language_override]
    if lang == "zh":
        return ["zh-Hans"]
    return [lang]

def _extract_url_template(body: str) -> Optional[str]:
    # e.g. client.get("$baseUrl/category/order/hits/page/$page") or GET(...)
    match = re.search(r'client\.get\("([^"]+)"\)', body)
    if not match:
        match = re.search(r'GET\("([^"]+)"', body)
    if not match:
        return None
    url = match.group(1)
    url = url.replace("$baseUrl", "{{baseUrl}}")
    url = url.replace("${baseUrl}", "{{baseUrl}}")
    url = url.replace("$page", "{{page}}")
    url = url.replace("${page}", "{{page}}")
    url = url.replace("$query", "{{query}}")
    url = url.replace("${query}", "{{query}}")
    return url

def _has_unsupported_logic(body: str) -> bool:
    if "QuickJs" in body:
        return True
    if "client.newCall" in body:
        return True
    # If there's some complex URL substring manipulation that we don't support generically
    if "substringAfter" in body and "cview" in body:
        return True
    return False

def _extract_list_parser(content: str, method_body: str, source_type: str, parse_method_name: Optional[str] = None) -> Dict[str, Any]:
    if source_type == "MODERN":
        # find the helper function called, e.g., return parseManga(document)
        helper_match = re.search(r'return\s+([a-zA-Z0-9_]+)\(', method_body)
        if not helper_match:
            return {"manualPatchRequired": True}
        helper_name = helper_match.group(1)
        helper_body = kotlin_parser.extract_method_body(content, helper_name)
    else:
        # LEGACY: the method_body is from the Request method, we need the Parse method body
        helper_body = kotlin_parser.extract_method_body(content, parse_method_name) if parse_method_name else None

    if not helper_body:
        return {"manualPatchRequired": True}

    if _has_unsupported_logic(helper_body):
        return {"manualPatchRequired": True}

    # Extract selector: document.select("div.comic-list > div.comic-item")
    # or document.select(".container .row a.comicpic_col6")
    sel_match = re.search(r'document\.select\("([^"]+)"\)', helper_body)
    if not sel_match:
        return {"manualPatchRequired": True}
    list_selector = sel_match.group(1)

    fields = {}

    # Extract title: element.selectFirst("h3 a")!!.text()
    title_match = re.search(r'title\s*=\s*element\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?text\(\)', helper_body)
    if title_match:
        fields["title"] = title_match.group(1)
    else:
        # Check without selectFirst e.g. element.text()
        if re.search(r'title\s*=\s*element\.text\(\)', helper_body):
            fields["title"] = "text"

    # Extract url: setUrlWithoutDomain(element.selectFirst("a")!!.absUrl("href"))
    url_match = re.search(r'setUrlWithoutDomain\(element\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?(?:absUrl|attr)\("([^"]+)"\)\)', helper_body)
    if url_match:
        fields["url"] = f"{url_match.group(1)}@{url_match.group(2)}"
    else:
        # e.g. setUrlWithoutDomain(element.absUrl("href"))
        url_match2 = re.search(r'setUrlWithoutDomain\(element\.(?:absUrl|attr)\("([^"]+)"\)\)', helper_body)
        if url_match2:
            fields["url"] = f"@{url_match2.group(1)}"

    # Extract cover: thumbnail_url = element.selectFirst("img")!!.attr("src")
    cover_match = re.search(r'thumbnail_url\s*=\s*element\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?(?:absUrl|attr)\("([^"]+)"\)', helper_body)
    if cover_match:
        fields["thumbnail"] = f"{cover_match.group(1)}@{cover_match.group(2)}"
    else:
        cover_match2 = re.search(r'thumbnail_url\s*=\s*element\.(?:absUrl|attr)\("([^"]+)"\)', helper_body)
        if cover_match2:
            fields["thumbnail"] = f"@{cover_match2.group(1)}"

    pagination = None
    # Extract hasNext logic:
    next_match = re.search(r'val\s+nextPage\s*=\s*document\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?attr\("([^"]+)"\)', helper_body)
    curr_match = re.search(r'val\s+currentPage\s*=\s*document\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?attr\("([^"]+)"\)', helper_body)
    return_match = re.search(r'return\s+MangasPage\([^,]+,\s*nextPage\s*!=\s*currentPage\)', helper_body)

    if next_match and curr_match and return_match and next_match.group(2) == curr_match.group(2):
        pagination = {
            "hasNextStrategy": "compareAttributes",
            "nextSelector": next_match.group(1),
            "currentSelector": curr_match.group(1),
            "attribute": next_match.group(2)
        }
    else:
        # Check for simple boolean hasNext logic
        # val hasNextPage = document.selectFirst("div.pager a span.mdi-skip-next") != null
        has_next_match = re.search(r'val\s+hasNextPage\s*=\s*document\.selectFirst\("([^"]+)"\)\s*!=\s*null', helper_body)
        if has_next_match:
            pagination = {
                "hasNextStrategy": "elementExists",
                "nextSelector": has_next_match.group(1)
            }

    res = {
        "selector": list_selector,
        "fields": fields,
        "manualPatchRequired": False
    }
    if pagination:
        res["pagination"] = pagination
    return res

def _extract_details(content: str, method_name: str) -> Dict[str, Any]:
    body = kotlin_parser.extract_method_body(content, method_name)
    if not body:
        return {"manualPatchRequired": True}

    if _has_unsupported_logic(body):
        return {"manualPatchRequired": True}

    fields = {}
    manual_required = False

    # Title
    title_match = re.search(r'title\s*=\s*document\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?text\(\)', body)
    if title_match:
        sel = title_match.group(1)
        if selector_analyzer.analyze_selector(sel)["classification"] != "SAFE":
            manual_required = True
        else:
            fields["title"] = sel

    # Cover
    cover_match = re.search(r'thumbnail_url\s*=\s*document\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?(?:absUrl|attr)\("([^"]+)"\)', body)
    if cover_match:
        sel = cover_match.group(1)
        if selector_analyzer.analyze_selector(sel)["classification"] != "SAFE":
            manual_required = True
        else:
            fields["thumbnail"] = f"{sel}@{cover_match.group(2)}"

    # Description
    desc_match = re.search(r'description\s*=\s*document\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?text\(\)', body)
    if desc_match:
        sel = desc_match.group(1)
        if selector_analyzer.analyze_selector(sel)["classification"] != "SAFE":
            manual_required = True
        else:
            fields["description"] = sel

    # Author (known manual)
    author_match = re.search(r'author\s*=\s*document\.selectFirst\("([^"]+)"\)', body)
    if author_match:
        sel = author_match.group(1)
        if selector_analyzer.analyze_selector(sel)["classification"] != "SAFE":
            manual_required = True

    # Status (known manual mapping)
    if 'status = when' in body:
        manual_required = True

    return {
        "url": "{{comicUrl}}",
        "method": "GET",
        "selector": "html",
        "fields": fields,
        "manualPatchRequired": manual_required
    }

def _extract_chapters(content: str, method_name: str) -> Dict[str, Any]:
    body = kotlin_parser.extract_method_body(content, method_name)
    if not body:
        return {"manualPatchRequired": True}

    if _has_unsupported_logic(body):
        return {"manualPatchRequired": True}

    # val chapters = document.select("#chapter-list > div.chapter-item > a").map { ...
    sel_match = re.search(r'document\.select\("([^"]+)"\)\.map', body)
    if not sel_match:
        return {"manualPatchRequired": True}
    selector = sel_match.group(1)

    fields = {}
    url_match = re.search(r'setUrlWithoutDomain\(element\.(?:absUrl|attr)\("([^"]+)"\)\)', body)
    if url_match:
        fields["url"] = f"@{url_match.group(1)}"
    else:
        # Check if URL is manually constructed, indicating a manual patch requirement
        if "url = " in body:
            return {"manualPatchRequired": True}

    name_match = re.search(r'name\s*=\s*element\.text\(\)', body)
    if name_match:
        fields["name"] = "text"

    reverse = ".asReversed()" in body or ".reversed()" in body

    return {
        "url": "{{comicUrl}}",
        "method": "GET",
        "isJson": False,
        "selector": selector,
        "fields": fields,
        "reverse": reverse,
        "manualPatchRequired": False
    }

def _extract_pages(content: str, method_name: str) -> Dict[str, Any]:
    body = kotlin_parser.extract_method_body(content, method_name)
    if not body:
        return {"manualPatchRequired": True}

    if _has_unsupported_logic(body):
        return {"manualPatchRequired": True}

    # return document.select("div.comic-content > img").mapIndexed { index, it -> Page(..., imageUrl = it.attr("src")) }
    sel_match = re.search(r'document\.select\("([^"]+)"\)', body)
    if not sel_match:
        return {"manualPatchRequired": True}

    attr_match = re.search(r'imageUrl\s*=\s*(?:it|element)\.attr\("([^"]+)"\)', body)
    if not attr_match:
        return {"manualPatchRequired": True}

    return {
        "url": "{{chapterUrl}}",
        "method": "GET",
        "selector": sel_match.group(1),
        "fields": {
            "imageUrl": f"@{attr_match.group(1)}"
        },
        "manualPatchRequired": False
    }

def extract(kt_path: str, gradle_meta: Dict[str, Any], timestamp: str, raw_lang: str, language_override: Optional[str] = None) -> Dict[str, Any]:
    with open(kt_path, "r", encoding="utf-8") as f:
        content = f.read()

    kt_facts = kotlin_parser.parse_kotlin_source(kt_path)
    base_class = kt_facts.get("base_class")

    version = str(gradle_meta.get("version", ""))
    is_kei = (base_class == "KeiSource")
    is_http = (base_class == "HttpSource")
    is_16 = version.startswith("1.6")
    is_14 = version.startswith("1.4")

    if is_kei and is_14:
        raise ValueError(f"Contradictory classification: base_class={base_class} + version={version}")
    if is_http and is_16:
        raise ValueError(f"Contradictory classification: base_class={base_class} + version={version}")

    if is_kei or is_16:
        source_type = "MODERN"
    elif is_http or is_14:
        source_type = "LEGACY"
    else:
        raise ValueError(f"Unknown or inconsistent source classification: base_class={base_class}, version={version}")

    explore = {}
    search = {}
    details = {}
    chapters = {}
    pages = {}

    if source_type == "MODERN":
        pop_body = kotlin_parser.extract_method_body(content, "getPopularManga")
        if pop_body:
            pop_url = _extract_url_template(pop_body)
            if pop_url:
                pop_data = _extract_list_parser(content, pop_body, source_type)
                pop_data["url"] = pop_url
                pop_data["method"] = "GET"
                explore["popular"] = pop_data

        lat_body = kotlin_parser.extract_method_body(content, "getLatestUpdates")
        if lat_body:
            lat_url = _extract_url_template(lat_body)
            if lat_url:
                lat_data = _extract_list_parser(content, lat_body, source_type)
                lat_data["url"] = lat_url
                lat_data["method"] = "GET"
                explore["latest"] = lat_data

        search_body = kotlin_parser.extract_method_body(content, "getSearchMangaList")
        if search_body:
            search_url = _extract_url_template(search_body)
            if search_url:
                search_data = _extract_list_parser(content, search_body, source_type)
                search_data["url"] = search_url
                search_data["method"] = "GET"
                search = search_data

        details = _extract_details(content, "fetchMangaUpdate")
        chapters = _extract_chapters(content, "fetchMangaUpdate")
        pages = _extract_pages(content, "getPageList")

    else:
        # LEGACY
        pop_req_body = kotlin_parser.extract_method_body(content, "popularMangaRequest")
        if pop_req_body:
            pop_url = _extract_url_template(pop_req_body)
            if pop_url:
                pop_data = _extract_list_parser(content, pop_req_body, source_type, "popularMangaParse")
                pop_data["url"] = pop_url
                pop_data["method"] = "GET"
                explore["popular"] = pop_data

        lat_req_body = kotlin_parser.extract_method_body(content, "latestUpdatesRequest")
        if lat_req_body:
            lat_url = _extract_url_template(lat_req_body)
            if lat_url:
                lat_data = _extract_list_parser(content, lat_req_body, source_type, "latestUpdatesParse")
                lat_data["url"] = lat_url
                lat_data["method"] = "GET"
                explore["latest"] = lat_data

        search_req_body = kotlin_parser.extract_method_body(content, "searchMangaRequest")
        if search_req_body:
            search_url = _extract_url_template(search_req_body)
            if search_url:
                search_data = _extract_list_parser(content, search_req_body, source_type, "searchMangaParse")
                search_data["url"] = search_url
                search_data["method"] = "GET"
                search = search_data

        details = _extract_details(content, "mangaDetailsParse")
        chapters = _extract_chapters(content, "chapterListParse")
        pages = _extract_pages(content, "pageListParse")


    name = gradle_meta.get("name", "Unknown")
    languages = _map_language(raw_lang, language_override)

    base_url = "https://example.com"
    base_url_match = re.search(r'val\s+baseUrl\s*=\s*"([^"]+)"', content)
    if base_url_match:
        base_url = base_url_match.group(1)
    else:
        base_url = gradle_meta.get("baseUrl", base_url)

    mirrors = []
    if "sources" in gradle_meta and gradle_meta["sources"]:
        if "baseUrl" in gradle_meta["sources"][0]:
            base_url = gradle_meta["sources"][0]["baseUrl"]
        mirrors = gradle_meta["sources"][0].get("mirrors", [])

    if mirrors:
        base_url = mirrors[0]["url"]

    ir = {
        "schemaVersion": "0.2",
        "id": f"{languages[0]}_{name.lower()}",
        "name": name,
        "languages": languages,
        "contentOrigins": ["CN"] if raw_lang == "zh" else ["JP"],
        "contentWarning": gradle_meta.get("contentWarning", "SAFE"),
        "sourceType": "html",
        "baseUrl": base_url,
        "explore": explore,
        "search": search,
        "details": details,
        "chapters": chapters,
        "pages": pages,
        "provenance": {
            "type": "converted",
            "upstreamProject": "keiyoushi",
            "upstreamPackage": kt_facts.get("package", "unknown"),
            "upstreamCommit": "unknown", # Filled by extract.py
            "upstreamVersion": gradle_meta.get("version", "1.0"),
            "upstreamLicense": "Apache-2.0",
            "converterVersion": "0.1.0",
            "generatedTimestamp": timestamp
        }
    }

    if mirrors:
        ir["mirrors"] = mirrors

    return ir
