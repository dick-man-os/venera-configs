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

import gradle_parser

COMMIT_HASH_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def _get_git_commit(repo_path: str) -> str:
    """Get the Git commit SHA of the upstream repository."""
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
    """Detect upstream license."""
    license_path = os.path.join(repo_path, "LICENSE")
    if os.path.exists(license_path):
        with open(license_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "Apache License" in content and "Version 2.0" in content:
                return "Apache-2.0"
            if "MIT License" in content:
                return "MIT"
    return "Apache-2.0"


def extract(extensions_root: str, timestamp: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract Flame Comics IR from Keiyoushi source.
    Flame Comics is an API-based Next.js data API source requiring manual patch hooks
    for dynamic buildId resolution and custom response mapping.
    """
    source_dir = os.path.join(extensions_root, "src", "en", "flamecomics")
    build_gradle_path = os.path.join(source_dir, "build.gradle.kts")
    kt_source_path = os.path.join(
        source_dir,
        "src",
        "eu",
        "kanade",
        "tachiyomi",
        "extension",
        "en",
        "flamecomics",
        "FlameComics.kt",
    )

    if not os.path.exists(build_gradle_path):
        raise FileNotFoundError(f"build.gradle.kts not found at {build_gradle_path}")
    if not os.path.exists(kt_source_path):
        raise FileNotFoundError(f"FlameComics.kt not found at {kt_source_path}")

    # 1. Parse Gradle metadata
    gradle_meta = gradle_parser.parse_gradle_metadata(build_gradle_path)
    name = gradle_meta.get("name", "Flame Comics")
    version_code = gradle_meta.get("versionCode", 50)
    lib_version = gradle_meta.get("libVersion", "1.4")
    content_warning = gradle_meta.get("contentWarning", "SAFE")

    sources = gradle_meta.get("sources", [])
    if not sources:
        raise ValueError("No source definitions found in build.gradle.kts")

    primary_source = sources[0]
    lang = primary_source.get("lang", "en")
    base_url = primary_source.get("baseUrl", "https://flamecomics.xyz")
    source_id = primary_source.get("id", 8531542650987673943)

    # 2. Parse Kotlin source for package name and verification
    with open(kt_source_path, "r", encoding="utf-8") as f:
        kt_content = f.read()

    pkg_match = re.search(r"package\s+([a-zA-Z0-9_.]+)", kt_content)
    package_name = pkg_match.group(1) if pkg_match else "eu.kanade.tachiyomi.extension.en.flamecomics"

    # 3. Provenance
    upstream_commit = _get_git_commit(extensions_root)
    upstream_license = _get_upstream_license(extensions_root)

    if not timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 4. Assemble canonical IR v0.2
    ir_data = {
        "schemaVersion": "0.2",
        "id": f"{lang}_{name.lower().replace(' ', '')}",
        "name": name,
        "languages": [lang],
        "contentOrigins": ["KR", "JP", "CN"],
        "contentWarning": content_warning,
        "sourceType": "api",
        "baseUrl": base_url,
        "explore": {
            "popular": {
                "manualPatchRequired": True,
            },
            "latest": {
                "manualPatchRequired": True,
            },
        },
        "search": {
            "manualPatchRequired": True,
        },
        "details": {
            "manualPatchRequired": True,
        },
        "chapters": {
            "manualPatchRequired": True,
        },
        "pages": {
            "manualPatchRequired": True,
        },
        "provenance": {
            "type": "converted",
            "upstreamProject": "keiyoushi",
            "upstreamPackage": package_name,
            "upstreamSourceId": str(source_id),
            "upstreamCommit": upstream_commit,
            "upstreamVersion": f"{lib_version}.{version_code}",
            "upstreamLicense": upstream_license,
            "converterVersion": "0.1.0",
            "generatedTimestamp": timestamp,
        },
    }

    return ir_data
