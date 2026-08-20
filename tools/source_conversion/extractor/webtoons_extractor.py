#!/usr/bin/env python3
"""
webtoons_extractor.py - Deterministic Kotlin-to-IR Extractor for Webtoons (English Pilot)

Extracts Intermediate Representation (IR) v0.1 JSON from the local Keiyoushi
Webtoons extension source without modifying upstream files.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional

COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def get_git_commit(repo_path: str) -> str:
    """Get the immutable Git commit SHA of the upstream repository."""
    try:
        commit = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            stderr=subprocess.PIPE,
            text=True,
        ).strip()
        if commit == "HEAD" or not COMMIT_HASH_RE.match(commit):
            raise ValueError(f"Invalid Git commit SHA obtained: '{commit}'")
        return commit
    except Exception as e:
        raise RuntimeError(f"Failed to obtain Git commit from '{repo_path}': {e}")


def get_upstream_license(repo_path: str) -> str:
    """Detect the upstream repository license from LICENSE file."""
    license_path = os.path.join(repo_path, "LICENSE")
    if os.path.exists(license_path):
        with open(license_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "Apache License" in content and "Version 2.0" in content:
                return "Apache-2.0"
            if "MIT License" in content:
                return "MIT"
    return "Apache-2.0"


def extract_webtoons_ir(
    extensions_root: str,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract IR v0.1 dictionary from the local Webtoons extension files."""
    webtoons_dir = os.path.join(extensions_root, "src", "all", "webtoons")
    build_gradle_path = os.path.join(webtoons_dir, "build.gradle.kts")
    kt_source_path = os.path.join(
        webtoons_dir,
        "src",
        "eu",
        "kanade",
        "tachiyomi",
        "extension",
        "all",
        "webtoons",
        "Webtoons.kt",
    )
    dto_source_path = os.path.join(
        webtoons_dir,
        "src",
        "eu",
        "kanade",
        "tachiyomi",
        "extension",
        "all",
        "webtoons",
        "Dto.kt",
    )

    # 1. Assert required source files exist
    for path, desc in [
        (build_gradle_path, "build.gradle.kts"),
        (kt_source_path, "Webtoons.kt"),
        (dto_source_path, "Dto.kt"),
    ]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Required Webtoons upstream file not found: {path} ({desc})")

    # 2. Parse build.gradle.kts
    with open(build_gradle_path, "r", encoding="utf-8") as f:
        gradle_content = f.read()

    name_match = re.search(r'name\s*=\s*"([^"]+)"', gradle_content)
    version_code_match = re.search(r"versionCode\s*=\s*(\d+)", gradle_content)
    lib_version_match = re.search(r'libVersion\s*=\s*"([^"]+)"', gradle_content)
    content_warning_match = re.search(r"contentWarning\s*=\s*ContentWarning\.([A-Z]+)", gradle_content)
    base_url_match = re.search(r'baseUrl\s*=\s*"([^"]+)"', gradle_content)

    if not name_match:
        raise ValueError("Could not extract 'name' from build.gradle.kts")
    if not version_code_match or not lib_version_match:
        raise ValueError("Could not extract version info from build.gradle.kts")
    if not content_warning_match:
        raise ValueError("Could not extract contentWarning from build.gradle.kts")
    if not base_url_match:
        raise ValueError("Could not extract baseUrl from build.gradle.kts")

    ext_name = name_match.group(1).replace(".com", "")  # "Webtoons"
    version_code = version_code_match.group(1)
    lib_version = lib_version_match.group(1)
    upstream_version = f"{lib_version}.{version_code}"
    content_warning = content_warning_match.group(1)
    base_url = base_url_match.group(1)

    # 3. Parse Webtoons.kt
    with open(kt_source_path, "r", encoding="utf-8") as f:
        kt_content = f.read()

    pkg_match = re.search(r"package\s+([a-zA-Z0-9_.]+)", kt_content)
    if not pkg_match:
        raise ValueError("Could not extract package name from Webtoons.kt")
    package_name = pkg_match.group(1)

    mobile_url_match = re.search(r'val\s+mobileUrl\s*=\s*"([^"]+)"', kt_content)
    if not mobile_url_match:
        raise ValueError("Could not extract mobileUrl from Webtoons.kt")
    mobile_url = mobile_url_match.group(1)

    # Assert expected cookies in Webtoons.kt
    if '"ageGatePass" to "true"' not in kt_content or '"needGDPR" to "false"' not in kt_content:
        raise ValueError("Expected Webtoons cookies (ageGatePass/needGDPR) not found in Webtoons.kt")

    cookies = [
        {"domain": "webtoons.com", "name": "ageGatePass", "value": "true"},
        {"domain": "webtoons.com", "name": "locale", "value": "en"},
        {"domain": "webtoons.com", "name": "needGDPR", "value": "false"},
    ]

    # Assert expected Referer header
    if 'set("Referer", "$baseUrl/")' not in kt_content:
        raise ValueError("Expected Referer header setup not found in Webtoons.kt")
    headers = {
        "Referer": "https://www.webtoons.com/",
    }

    # Popular / explore extraction
    if 'popularMangaRequest' not in kt_content or '".webtoon_list li a"' not in kt_content:
        raise ValueError("Expected popularMangaRequest or selector not found in Webtoons.kt")

    explore = {
        "popular": {
            "url": "{{baseUrl}}/{{langCode}}/ranking/trending",
            "method": "GET",
            "selector": ".webtoon_list li a",
            "fields": {
                "title": ".title",
                "url": "@href",
                "thumbnail": "img@src",
            },
        },
        "latest": {
            "url": "{{baseUrl}}/{{langCode}}/originals/{{day}}?sortOrder=UPDATE",
            "method": "GET",
            "selector": ".webtoon_list li a",
            "fields": {
                "title": ".title",
                "url": "@href",
                "thumbnail": "img@src",
            },
        },
    }

    # Search extraction
    if 'searchMangaRequest' not in kt_content or 'addQueryParameter("keyword", query)' not in kt_content:
        raise ValueError("Expected search request patterns not found in Webtoons.kt")

    search = {
        "url": "{{baseUrl}}/{{langCode}}/search?keyword={{query}}&page={{page}}",
        "method": "GET",
        "selector": ".webtoon_list li a",
        "fields": {
            "title": ".title",
            "url": "@href",
            "thumbnail": "img@src",
        },
    }

    # Comic details extraction
    if 'mangaDetailsParse' not in kt_content or 'h1.subj, h3.subj' not in kt_content:
        raise ValueError("Expected details parse selectors not found in Webtoons.kt")

    details = {
        "url": "{{comicUrl}}",
        "method": "GET",
        "selector": ".detail_header .info",
        "fields": {
            "title": "h1.subj, h3.subj",
            "author": ".author, .author_area",
            "description": "#_asideDetail p.summary",
            "thumbnail": ".detail_header .thmb img@src",
            "status": "#_asideDetail p.day_info",
        },
        "manualPatchRequired": True,
    }

    # Chapters extraction (JSON endpoint)
    if 'addPathSegments("api/v1")' not in kt_content or 'addPathSegment("episodes")' not in kt_content:
        raise ValueError("Expected chapter API endpoints not found in Webtoons.kt")

    # Verify Dto.kt defines EpisodeList structure
    with open(dto_source_path, "r", encoding="utf-8") as f:
        dto_content = f.read()
    if "episodeList: List<Episode>" not in dto_content:
        raise ValueError("Expected episodeList definition not found in Dto.kt")

    # Chapter parsing in Kotlin uses complex regex (episodeNoRegex) and season numbering offset logic
    # that requires a manual JS patch in Phase 1
    chapters = {
        "url": "{{mobileUrl}}/api/v1/webtoon/{{titleId}}/episodes?pageSize=99999",
        "method": "GET",
        "isJson": True,
        "listPath": "result.episodeList",
        "fields": {
            "url": "viewerLink",
            "name": "episodeTitle",
            "date": "exposureDateMillis",
        },
        "manualPatchRequired": True,
    }

    # Pages extraction
    if 'div#_imageList > img' not in kt_content or 'data-url' not in kt_content:
        raise ValueError("Expected page list image selectors not found in Webtoons.kt")

    # Page list in Kotlin also has MotionToon and AuthorNotes branches
    pages = {
        "url": "{{chapterUrl}}",
        "method": "GET",
        "selector": "div#_imageList > img",
        "fields": {
            "imageUrl": "@data-url",
        },
        "manualPatchRequired": True,
    }

    # 4. Provenance
    upstream_commit = get_git_commit(extensions_root)
    upstream_license = get_upstream_license(extensions_root)

    if not timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    provenance = {
        "type": "converted",
        "upstreamProject": "keiyoushi",
        "upstreamPackage": package_name,
        "upstreamCommit": upstream_commit,
        "upstreamVersion": upstream_version,
        "upstreamLicense": upstream_license,
        "converterVersion": "0.1.0",
        "generatedTimestamp": timestamp,
    }

    # 5. Assemble IR v0.1
    ir_data = {
        "schemaVersion": "0.1.0",
        "id": "en_webtoons",
        "name": ext_name,
        "languages": ["en"],
        "contentOrigins": [],
        "contentWarning": content_warning,
        "sourceType": "hybrid",
        "requiresAuth": False,
        "requiresWebView": False,
        "status": "ONGOING",
        "baseUrl": base_url,
        "mobileUrl": mobile_url,
        "headers": headers,
        "cookies": cookies,
        "explore": explore,
        "search": search,
        "details": details,
        "chapters": chapters,
        "pages": pages,
        "provenance": provenance,
    }

    return ir_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract IR v0.1 JSON from Keiyoushi Webtoons extension."
    )
    parser.add_argument(
        "--extensions-root",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "extensions-source")
        ),
        help="Path to extensions-source repository root.",
    )
    parser.add_argument(
        "--output",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "sources_ir", "webtoons.json")
        ),
        help="Output path for the generated webtoons.json IR file.",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="Optional ISO timestamp override for deterministic testing.",
    )

    args = parser.parse_args()

    extensions_root = os.path.abspath(args.extensions_root)
    output_path = os.path.abspath(args.output)

    print(f"[*] Extracting Webtoons IR from: {extensions_root}")
    print(f"[*] Target output: {output_path}")

    try:
        ir_data = extract_webtoons_ir(extensions_root, timestamp=args.timestamp)
    except Exception as e:
        print(f"[!] Extraction failed: {e}", file=sys.stderr)
        return 1

    # Ensure output parent directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ir_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[+] Successfully extracted Webtoons IR to {output_path}")
    print(f"    - ID: {ir_data['id']}")
    print(f"    - Language: {ir_data['languages']}")
    print(f"    - Upstream Version: {ir_data['provenance']['upstreamVersion']}")
    print(f"    - Upstream Commit: {ir_data['provenance']['upstreamCommit']}")
    print(f"    - Manual Patch Required: chapters={ir_data['chapters'].get('manualPatchRequired')}, pages={ir_data['pages'].get('manualPatchRequired')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
