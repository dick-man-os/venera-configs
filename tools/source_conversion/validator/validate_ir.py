#!/usr/bin/env python3
"""
validate_ir.py - Deterministic Validator for Venera Comic Source IR v0.1 & v0.2

Uses strictly standard Python library components to validate Intermediate
Representation (IR) JSON definitions for converted comic sources.
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

ALLOWED_LANGUAGES = {"zh-Hans", "zh-Hant", "ko", "en"}
ALLOWED_ORIGINS = {"KR", "CN", "JP"}
ALLOWED_CONTENT_WARNINGS = {"SAFE", "MIXED", "NSFW"}
ALLOWED_SOURCE_TYPES = {"api", "html", "hybrid"}
ALLOWED_STATUSES = {"ONGOING", "COMPLETED", "UNKNOWN", "PAUSED", "DISCONTINUED"}
ALLOWED_PROVENANCE_TYPES = {"converted", "native", "hybrid"}
ALLOWED_METHODS = {"GET", "POST"}

COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
SCHEMA_VERSION_RE = re.compile(r"^0\.[12](\.[0-9]+)?$")


def validate_ir_data(data: Any) -> List[str]:
    """Validate a parsed IR JSON data dictionary. Returns a list of error messages."""
    errors: List[str] = []

    if not isinstance(data, dict):
        return ["IR root must be a JSON object."]

    # Required top-level fields
    required_fields = [
        "schemaVersion",
        "id",
        "name",
        "languages",
        "contentOrigins",
        "contentWarning",
        "sourceType",
        "baseUrl",
        "explore",
        "search",
        "details",
        "chapters",
        "pages",
    ]

    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required top-level field: '{field}'")

    # Check unknown top-level fields
    known_fields = set(required_fields) | {
        "version",
        "requiresAuth",
        "requiresWebView",
        "status",
        "lastVerified",
        "mobileUrl",
        "mirrors",
        "headers",
        "cookies",
        "provenance",
    }
    for field in data:
        if field not in known_fields:
            errors.append(f"Unknown top-level property: '{field}'")

    # version
    if "version" in data:
        v = data["version"]
        if not isinstance(v, str) or not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", v):
            errors.append(
                f"Field 'version' must be a semantic version string (e.g., '1.0.0') (got: {repr(v)})"
            )

    # schemaVersion
    if "schemaVersion" in data:
        sv = data["schemaVersion"]
        if not isinstance(sv, str) or not SCHEMA_VERSION_RE.match(sv):
            errors.append(
                f"Field 'schemaVersion' must be a string matching '0.1' or '0.2' (got: {repr(sv)})"
            )

    # id & name
    if "id" in data:
        if not isinstance(data["id"], str) or not data["id"].strip():
            errors.append("Field 'id' must be a non-empty string.")
    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip():
            errors.append("Field 'name' must be a non-empty string.")

    # languages
    if "languages" in data:
        langs = data["languages"]
        if not isinstance(langs, list) or len(langs) == 0:
            errors.append("Field 'languages' must be a non-empty array of strings.")
        else:
            if len(langs) != len(set(langs)):
                errors.append("Field 'languages' contains duplicate entries.")
            for idx, lang in enumerate(langs):
                if not isinstance(lang, str):
                    errors.append(f"Language at index {idx} must be a string.")
                elif lang not in ALLOWED_LANGUAGES:
                    errors.append(
                        f"Unsupported language code '{lang}' at index {idx}. Allowed: {sorted(ALLOWED_LANGUAGES)}"
                    )

    # contentOrigins
    if "contentOrigins" in data:
        origins = data["contentOrigins"]
        if not isinstance(origins, list):
            errors.append("Field 'contentOrigins' must be an array of strings.")
        else:
            if len(origins) != len(set(origins)):
                errors.append("Field 'contentOrigins' contains duplicate entries.")
            for idx, origin in enumerate(origins):
                if not isinstance(origin, str):
                    errors.append(f"Origin at index {idx} must be a string.")
                elif origin not in ALLOWED_ORIGINS:
                    errors.append(
                        f"Unsupported contentOrigin '{origin}' at index {idx}. Allowed: {sorted(ALLOWED_ORIGINS)}"
                    )

    # contentWarning
    if "contentWarning" in data:
        cw = data["contentWarning"]
        if cw not in ALLOWED_CONTENT_WARNINGS:
            errors.append(
                f"Field 'contentWarning' must be one of {sorted(ALLOWED_CONTENT_WARNINGS)} (got: {repr(cw)})"
            )

    # sourceType
    if "sourceType" in data:
        st = data["sourceType"]
        if st not in ALLOWED_SOURCE_TYPES:
            errors.append(
                f"Field 'sourceType' must be one of {sorted(ALLOWED_SOURCE_TYPES)} (got: {repr(st)})"
            )

    # URLs and mirrors
    base_url = data.get("baseUrl")
    if "baseUrl" in data:
        if not isinstance(base_url, str) or not (
            base_url.startswith("http://") or base_url.startswith("https://")
        ):
            errors.append("Field 'baseUrl' must be a valid HTTP/HTTPS URL string.")

    if "mirrors" in data:
        mirrors = data["mirrors"]
        if not isinstance(mirrors, list) or len(mirrors) == 0:
            errors.append("Field 'mirrors' must be a non-empty array.")
        else:
            seen_urls = set()
            for idx, m in enumerate(mirrors):
                if not isinstance(m, dict):
                    errors.append(f"Mirror at index {idx} must be an object.")
                else:
                    url = m.get("url")
                    if not url or not isinstance(url, str):
                        errors.append(f"Mirror at index {idx} missing required string property 'url'.")
                    else:
                        if url in seen_urls:
                            errors.append(f"Duplicate mirror URL '{url}' at index {idx}.")
                        seen_urls.add(url)

                    label = m.get("label")
                    if label is not None and not isinstance(label, str):
                        errors.append(f"Mirror at index {idx} 'label' must be a string if present.")

            # Semantic validation: first mirror MUST be the baseUrl
            if len(mirrors) > 0 and isinstance(mirrors[0], dict):
                first_url = mirrors[0].get("url")
                if first_url and isinstance(base_url, str) and first_url != base_url:
                    errors.append(f"First mirror URL '{first_url}' must exactly match baseUrl '{base_url}'.")

    # ... remaining checks remain identical
    if "mobileUrl" in data:
        if not isinstance(data["mobileUrl"], str) or not (
            data["mobileUrl"].startswith("http://") or data["mobileUrl"].startswith("https://")
        ):
            errors.append("Field 'mobileUrl' must be a valid HTTP/HTTPS URL string.")

    if "headers" in data:
        headers = data["headers"]
        if not isinstance(headers, dict):
            errors.append("Field 'headers' must be an object/dict.")
        else:
            for k, v in headers.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    errors.append(f"Header '{k}' must map a string key to a string value.")

    if "cookies" in data:
        cookies = data["cookies"]
        if not isinstance(cookies, list):
            errors.append("Field 'cookies' must be an array.")
        else:
            for idx, c in enumerate(cookies):
                if not isinstance(c, dict):
                    errors.append(f"Cookie at index {idx} must be an object.")
                else:
                    for req_k in ["domain", "name", "value"]:
                        if req_k not in c or not isinstance(c[req_k], str):
                            errors.append(
                                f"Cookie at index {idx} missing required string property '{req_k}'."
                            )

    if "explore" in data:
        explore = data["explore"]
        if not isinstance(explore, dict):
            errors.append("Field 'explore' must be an object/dict mapping tab names to definitions.")
        else:
            for tab_name, tab_def in explore.items():
                if not isinstance(tab_def, dict):
                    errors.append(f"Explore tab '{tab_name}' must be an object.")
                elif not tab_def.get("manualPatchRequired", False):
                    if "url" not in tab_def or not isinstance(tab_def["url"], str):
                        errors.append(f"Explore tab '{tab_name}' requires 'url' string.")
                    if "method" in tab_def and tab_def["method"] not in ALLOWED_METHODS:
                        errors.append(f"Explore tab '{tab_name}' has invalid method '{tab_def['method']}'.")

    if "search" in data:
        search = data["search"]
        if not isinstance(search, dict):
            errors.append("Field 'search' must be an object.")
        elif not search.get("manualPatchRequired", False):
            if "url" not in search or not isinstance(search["url"], str):
                errors.append("Field 'search' requires 'url' string.")
            if "method" not in search or search["method"] not in ALLOWED_METHODS:
                errors.append(f"Field 'search' requires 'method' to be one of {sorted(ALLOWED_METHODS)}.")

    if "details" in data:
        details = data["details"]
        if not isinstance(details, dict):
            errors.append("Field 'details' must be an object.")
        elif not details.get("manualPatchRequired", False):
            if "url" not in details or not isinstance(details["url"], str):
                errors.append("Field 'details' requires 'url' string.")
            if "method" not in details or details["method"] not in ALLOWED_METHODS:
                errors.append(f"Field 'details' requires 'method' to be one of {sorted(ALLOWED_METHODS)}.")

    if "chapters" in data:
        chapters = data["chapters"]
        if not isinstance(chapters, dict):
            errors.append("Field 'chapters' must be an object.")
        elif not chapters.get("manualPatchRequired", False):
            if "url" not in chapters or not isinstance(chapters["url"], str):
                errors.append("Field 'chapters' requires 'url' string.")
            if "method" in chapters and chapters["method"] not in ALLOWED_METHODS:
                errors.append(f"Field 'chapters' has invalid method '{chapters['method']}'.")

    if "pages" in data:
        pages = data["pages"]
        if not isinstance(pages, dict):
            errors.append("Field 'pages' must be an object.")
        elif not pages.get("manualPatchRequired", False):
            if "url" not in pages or not isinstance(pages["url"], str):
                errors.append("Field 'pages' requires 'url' string.")
            if "method" in pages and pages["method"] not in ALLOWED_METHODS:
                errors.append(f"Field 'pages' has invalid method '{pages['method']}'.")

    if "provenance" in data:
        prov = data["provenance"]
        if not isinstance(prov, dict):
            errors.append("Field 'provenance' must be an object.")
        else:
            prov_reqs = [
                "type",
                "upstreamProject",
                "upstreamCommit",
                "upstreamVersion",
                "upstreamLicense",
                "converterVersion",
                "generatedTimestamp",
            ]
            for pr in prov_reqs:
                if pr not in prov or not isinstance(prov[pr], str):
                    errors.append(f"Provenance missing required string field '{pr}'.")

            if "type" in prov and prov["type"] not in ALLOWED_PROVENANCE_TYPES:
                errors.append(
                    f"Provenance 'type' must be one of {sorted(ALLOWED_PROVENANCE_TYPES)} (got: {repr(prov.get('type'))})"
                )

            commit = prov.get("upstreamCommit", "")
            if commit == "HEAD":
                errors.append(
                    "Provenance 'upstreamCommit' must be an immutable Git commit SHA, NOT 'HEAD'."
                )
            elif commit and not COMMIT_HASH_RE.match(commit):
                errors.append(
                    f"Provenance 'upstreamCommit' must be a valid 7-40 char hex commit hash (got: {repr(commit)})."
                )

    return errors


def validate_file(file_path: str) -> bool:
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[FAIL] {file_path}: Invalid JSON - {e}", file=sys.stderr)
        return False

    errors = validate_ir_data(data)
    if errors:
        print(f"[FAIL] {file_path} failed IR validation ({len(errors)} errors):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return False

    print(f"[PASS] {file_path} is valid IR.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Venera Source IR JSON file.")
    parser.add_argument("files", nargs="+", help="Path(s) to IR JSON file(s) to validate.")
    args = parser.parse_args()

    all_passed = True
    for file_path in args.files:
        if not validate_file(file_path):
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
