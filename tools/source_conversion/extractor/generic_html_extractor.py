#!/usr/bin/env python3
import os
import re
from typing import Any, Dict, List, Optional
from common import kotlin_parser, selector_analyzer

def _map_language(lang: str) -> List[str]:
    if lang == "zh":
        return ["zh-Hans"]
    return [lang]

def _extract_url_template(body: str, method_name: str) -> Optional[str]:
    # e.g. client.get("$baseUrl/category/order/hits/page/$page")
    match = re.search(r'client\.get\("([^"]+)"\)', body)
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

def _extract_list_parser(content: str, method_body: str) -> Dict[str, Any]:
    # find the helper function called, e.g., return parseManga(document)
    helper_match = re.search(r'return\s+([a-zA-Z0-9_]+)\(', method_body)
    if not helper_match:
        return {"manualPatchRequired": True}
    helper_name = helper_match.group(1)

    helper_body = kotlin_parser.extract_method_body(content, helper_name)
    if not helper_body:
        return {"manualPatchRequired": True}

    # Extract selector: document.select("div.comic-list > div.comic-item")
    sel_match = re.search(r'document\.select\("([^"]+)"\)', helper_body)
    if not sel_match:
        return {"manualPatchRequired": True}
    list_selector = sel_match.group(1)

    fields = {}

    # Extract title: element.selectFirst("h3 a")!!.text()
    title_match = re.search(r'title\s*=\s*element\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?text\(\)', helper_body)
    if title_match:
        fields["title"] = title_match.group(1)

    # Extract url: setUrlWithoutDomain(element.selectFirst("a")!!.absUrl("href"))
    url_match = re.search(r'setUrlWithoutDomain\(element\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?(?:absUrl|attr)\("([^"]+)"\)\)', helper_body)
    if url_match:
        fields["url"] = f"{url_match.group(1)}@{url_match.group(2)}"

    # Extract cover: thumbnail_url = element.selectFirst("img")!!.attr("src")
    cover_match = re.search(r'thumbnail_url\s*=\s*element\.selectFirst\("([^"]+)"\)(?:\?\.)?(?:!!\.)?(?:absUrl|attr)\("([^"]+)"\)', helper_body)
    if cover_match:
        fields["thumbnail"] = f"{cover_match.group(1)}@{cover_match.group(2)}"

    pagination = None
    # Extract hasNext logic:
    # val nextPage = document.selectFirst("div.pagination > a.next")!!.attr("href")
    # val currentPage = document.selectFirst("div.pagination > a.on")!!.attr("href")
    # return MangasPage(mangas, nextPage != currentPage)
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

    res = {
        "selector": list_selector,
        "fields": fields,
        "manualPatchRequired": False
    }
    if pagination:
        res["pagination"] = pagination
    return res

def _extract_details(content: str) -> Dict[str, Any]:
    body = kotlin_parser.extract_method_body(content, "fetchMangaUpdate")
    if not body:
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

def _extract_chapters(content: str) -> Dict[str, Any]:
    body = kotlin_parser.extract_method_body(content, "fetchMangaUpdate")
    if not body:
        return {"manualPatchRequired": True}

    # val chapters = document.select("#chapter-list > div.chapter-item > a").map { ...
    sel_match = re.search(r'val\s+chapters\s*=\s*document\.select\("([^"]+)"\)\.map', body)
    if not sel_match:
        return {"manualPatchRequired": True}
    selector = sel_match.group(1)

    fields = {}
    url_match = re.search(r'setUrlWithoutDomain\(element\.(?:absUrl|attr)\("([^"]+)"\)\)', body)
    if url_match:
        fields["url"] = f"@{url_match.group(1)}"

    name_match = re.search(r'name\s*=\s*element\.text\(\)', body)
    if name_match:
        fields["name"] = "text"

    reverse = ".asReversed()" in body

    return {
        "url": "{{comicUrl}}",
        "method": "GET",
        "isJson": False,
        "selector": selector,
        "fields": fields,
        "reverse": reverse,
        "manualPatchRequired": False
    }

def _extract_pages(content: str) -> Dict[str, Any]:
    body = kotlin_parser.extract_method_body(content, "getPageList")
    if not body:
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


def extract(kt_path: str, gradle_meta: Dict[str, Any], timestamp: str, raw_lang: str) -> Dict[str, Any]:
    with open(kt_path, "r", encoding="utf-8") as f:
        content = f.read()

    explore = {}

    pop_body = kotlin_parser.extract_method_body(content, "getPopularManga")
    if pop_body:
        pop_url = _extract_url_template(pop_body, "getPopularManga")
        if pop_url:
            pop_data = _extract_list_parser(content, pop_body)
            pop_data["url"] = pop_url
            pop_data["method"] = "GET"
            explore["popular"] = pop_data

    lat_body = kotlin_parser.extract_method_body(content, "getLatestUpdates")
    if lat_body:
        lat_url = _extract_url_template(lat_body, "getLatestUpdates")
        if lat_url:
            lat_data = _extract_list_parser(content, lat_body)
            lat_data["url"] = lat_url
            lat_data["method"] = "GET"
            explore["latest"] = lat_data

    search = {}
    search_body = kotlin_parser.extract_method_body(content, "getSearchMangaList")
    if search_body:
        search_url = _extract_url_template(search_body, "getSearchMangaList")
        if search_url:
            search_data = _extract_list_parser(content, search_body)
            search_data["url"] = search_url
            search_data["method"] = "GET"
            search = search_data

    details = _extract_details(content)
    chapters = _extract_chapters(content)
    pages = _extract_pages(content)

    kt_facts = kotlin_parser.parse_kotlin_source(kt_path)

    name = gradle_meta.get("name", "Unknown")
    languages = _map_language(raw_lang)

    base_url = "https://example.com"
    base_url_match = re.search(r'val\s+baseUrl\s*=\s*"([^"]+)"', content)
    if base_url_match:
        base_url = base_url_match.group(1)
    else:
        # Fallback to gradle
        base_url = gradle_meta.get("baseUrl", base_url)

    mirrors = []
    if "sources" in gradle_meta and gradle_meta["sources"]:
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
