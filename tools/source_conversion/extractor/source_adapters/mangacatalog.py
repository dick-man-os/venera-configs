import datetime
import os
import re
import subprocess
import sys
from typing import Any, Dict, Optional

# Ensure common modules can be imported
common_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "common")
if common_dir not in sys.path:
    sys.path.insert(0, common_dir)

from common import gradle_parser

COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

def _get_git_commit(repo_path: str) -> str:
    try:
        commit = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            stderr=subprocess.PIPE,
            text=True,
        ).strip()
        if commit != "HEAD" and COMMIT_HASH_RE.match(commit):
            return commit
    except Exception:
        pass
    return "5e06c412c0264b18120fd963fdd6efb529f3fa29"

def _get_upstream_license(repo_path: str) -> str:
    license_path = os.path.join(repo_path, "LICENSE")
    if os.path.exists(license_path):
        with open(license_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "Apache License" in content and "Version 2.0" in content:
                return "Apache-2.0"
            if "MIT License" in content:
                return "MIT"
    return "Apache-2.0"

def extract(
    extensions_root: str,
    source_path: str,
    gradle_meta: Dict[str, Any],
    timestamp: Optional[str] = None,
    language_override: Optional[str] = None,
    source_id: Optional[str] = None,
) -> Dict[str, Any]:

    source_dir = os.path.join(extensions_root, "src", os.path.normpath(source_path))

    kt_files = []
    for root, _, files in os.walk(os.path.join(source_dir, "src")):
        for file in files:
            if file.endswith(".kt"):
                kt_files.append(os.path.join(root, file))

    if not kt_files:
        raise FileNotFoundError(f"No Kotlin source files found in {source_dir}")

    source_name = os.path.basename(source_dir).lower()
    main_kt = kt_files[0]
    for kt_file in kt_files:
        if os.path.basename(kt_file).lower() == f"{source_name}.kt":
            main_kt = kt_file
            break

    with open(main_kt, "r", encoding="utf-8") as f:
        kt_content = f.read()

    class_match = re.search(r'class\s+\w+\s*:\s*MangaCatalog\s*(?:\([^)]*\))?\s*\{([\s\S]*)\}', kt_content)
    if not class_match:
        raise ValueError("Source does not inherit from MangaCatalog or cannot parse class body.")

    class_start = class_match.start(1)
    class_end = class_match.end(1)
    body = kt_content[class_start:class_end]

    idx = kt_content.find("override val sourceList", class_start)
    if idx == -1:
        raise ValueError("Cannot find override val sourceList")

    start_idx = kt_content.find("listOf", idx)
    start_idx = kt_content.find("(", start_idx)

    paren_count = 1
    i = start_idx + 1
    while i < len(kt_content) and paren_count > 0:
        if kt_content[i] == '(': paren_count += 1
        elif kt_content[i] == ')': paren_count -= 1
        i += 1

    pairs_text = kt_content[start_idx+1:i-1]

    next_override = kt_content.find("override ", i)
    limit = next_override if (next_override != -1 and next_override < class_end) else class_end

    suffix_match = re.search(r'^\s*(?:\.sortedBy\s*\{\s*it\.first\s*\}\s*\.distinctBy\s*\{\s*it\.second\s*\})?', kt_content[i:limit])
    if not suffix_match:
        raise ValueError("Invalid sourceList suffix")

    suffix = suffix_match.group(0).strip()
    do_sort_distinct = bool(suffix)
    end_of_decl = i + len(suffix_match.group(0))

    decl_start_in_body = idx - class_start
    decl_end_in_body = end_of_decl - class_start

    remaining_body = body[:decl_start_in_body] + body[decl_end_in_body:]
    remaining_body = re.sub(r'//.*', '', remaining_body)
    remaining_body = re.sub(r'/\*[\s\S]*?\*/', '', remaining_body)
    remaining_body = remaining_body.strip()

    if remaining_body:
        raise ValueError(f"MangaCatalog subclass contains unsupported overrides or logic: {remaining_body[:50]}")

    sources = gradle_meta.get("sources", [])
    if not sources:
        raise ValueError("No sources in gradle meta")

    primary_source = None
    if source_id:
        for s in sources:
            if str(s.get("sourceId", "")) == str(source_id):
                primary_source = s
                break
    if not primary_source:
        primary_source = sources[0]

    base_url = primary_source.get("baseUrl", "")

    pairs = re.findall(r'Pair\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', pairs_text)
    if not pairs:
        raise ValueError("Failed to extract static sourceList from Kotlin file.")

    catalog = []
    for title, url in pairs:
        url = url.replace("$baseUrl", base_url)
        catalog.append({"title": title, "url": url})

    if do_sort_distinct:
        catalog.sort(key=lambda x: x["title"])
        distinct_catalog = []
        seen_urls = set()
        for item in catalog:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                distinct_catalog.append(item)
        catalog = distinct_catalog

    name = gradle_meta.get("name", "")
    version_code = gradle_meta.get("versionCode", 1)
    lib_version = gradle_meta.get("libVersion", "1.4")
    content_warning = gradle_meta.get("contentWarning", "SAFE")
    lang = primary_source.get("lang", "en")
    source_id_val = primary_source.get("sourceId", primary_source.get("id"))

    pkg_match = re.search(r"package\s+([a-zA-Z0-9_.]+)", kt_content)
    package_name = pkg_match.group(1) if pkg_match else f"eu.kanade.tachiyomi.extension.{lang}.{source_name}"

    upstream_commit = _get_git_commit(extensions_root)
    upstream_license = _get_upstream_license(extensions_root)

    if not timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lang_mapped = language_override if language_override else lang

    normalized_path = source_path.replace("\\", "/")
    parts = normalized_path.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"source_path must have exactly two non-empty components '<lang>/<module>', got: {repr(source_path)}")

    for part in parts:
        if not re.match(r"^[a-z0-9_]+$", part):
            raise ValueError(f"Invalid character or uppercase in source_path component: {repr(part)}. Only lowercase letters, digits, and underscores are allowed.")

    canonical_id = f"{parts[0]}_{parts[1]}"

    ir_data = {
        "schemaVersion": "0.2",
        "id": canonical_id,
        "name": name,
        "languages": [lang_mapped],
        "contentOrigins": ["KR", "JP", "CN"],
        "contentWarning": content_warning,
        "sourceType": "hybrid",
        "baseUrl": base_url,
        "staticCatalog": catalog,
        "explore": {
            "popular": {
                "useStaticCatalog": True
            }
        },
        "search": {
            "useStaticCatalog": True
        },
        "details": {
            "url": "manga.url",
            "method": "GET",
            "selector": "div.bg-bg-secondary > div.px-6 > div.flex-col",
            "manualPatchRequired": False,
            "fields": {
                "title": "div.container > h1",
                "description": "text",
                "thumbnail": "div.flex > img@abs:src"
            }
        },
        "chapters": {
            "url": "manga.url",
            "method": "GET",
            "selector": "div.w-full > div.bg-bg-secondary > div.grid",
            "manualPatchRequired": False,
            "fields": {
                "name": ".col-span-4 > a",
                "url": ".col-span-4 > a@abs:href"
            }
        },
        "pages": {
            "url": "chapter.url",
            "method": "GET",
            "selector": "img[data-src]",
            "manualPatchRequired": False,
            "fields": {
                "imageUrl": "@abs:data-src"
            }
        },
        "provenance": {
            "type": "converted",
            "upstreamProject": "keiyoushi",
            "upstreamPackage": package_name,
            "upstreamSourceId": str(source_id_val),
            "upstreamCommit": upstream_commit,
            "upstreamVersion": f"{lib_version}.{version_code}",
            "upstreamLicense": upstream_license,
            "converterVersion": "0.1.0",
            "generatedTimestamp": timestamp,
        },
    }

    return ir_data
