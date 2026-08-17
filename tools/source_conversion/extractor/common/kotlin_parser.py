import re
from typing import Any, Dict, List, Optional

def parse_kotlin_source(kt_path: str) -> Dict[str, Any]:
    """Parse a Keiyoushi Kotlin source file for structural facts using targeted regex."""
    with open(kt_path, "r", encoding="utf-8") as f:
        content = f.read()

    facts = {
        "package": None,
        "class_name": None,
        "base_class": None,
        "has_source_annotation": False,
        "has_headers_builder": False,
        "has_cookies": False,
        "methods": {
            "GET": False,
            "POST": False,
        },
        "overrides": {
            "popularManga": False,
            "latestUpdates": False,
            "searchManga": False,
            "mangaDetails": False,
            "chapterList": False,
            "pageList": False,
        },
        "uses_json": False,
        "imports": [],
    }

    # Package
    pkg_match = re.search(r"^package\s+([a-zA-Z0-9_.]+)", content, re.MULTILINE)
    if pkg_match:
        facts["package"] = pkg_match.group(1)

    # Class and Base Class
    class_match = re.search(r"class\s+([A-Za-z0-9_]+)\s*(?:\([^)]*\))?\s*:\s*([A-Za-z0-9_]+)", content)
    if class_match:
        facts["class_name"] = class_match.group(1)
        facts["base_class"] = class_match.group(2)

    # @Source Annotation
    if re.search(r"@Source\b", content):
        facts["has_source_annotation"] = True

    # Headers
    if "headersBuilder(" in content or "headersBuilder()" in content or 'Headers.Builder' in content:
        facts["has_headers_builder"] = True

    # Cookies
    if "Cookie.Builder" in content or "addCookie" in content or "CookieManager" in content:
        facts["has_cookies"] = True

    # HTTP Methods
    if "GET(" in content or ".get(" in content:
        facts["methods"]["GET"] = True
    if "POST(" in content or ".post(" in content:
        facts["methods"]["POST"] = True

    # Overrides/Methods presence
    if "popularMangaRequest" in content or "popularMangaParse" in content:
        facts["overrides"]["popularManga"] = True
    if "latestUpdatesRequest" in content or "latestUpdatesParse" in content:
        facts["overrides"]["latestUpdates"] = True
    if "searchMangaRequest" in content or "searchMangaParse" in content:
        facts["overrides"]["searchManga"] = True
    if "mangaDetailsParse" in content:
        facts["overrides"]["mangaDetails"] = True
    if "chapterListParse" in content:
        facts["overrides"]["chapterList"] = True
    if "pageListParse" in content:
        facts["overrides"]["pageList"] = True

    # JSON parsing
    if "parseAs<" in content or "json.decodeFromString" in content or "kotlinx.serialization" in content:
        facts["uses_json"] = True

import re
from typing import Any, Dict, List, Optional

def parse_kotlin_source(kt_path: str) -> Dict[str, Any]:
    """Parse a Keiyoushi Kotlin source file for structural facts using targeted regex."""
    with open(kt_path, "r", encoding="utf-8") as f:
        content = f.read()

    facts = {
        "package": None,
        "class_name": None,
        "base_class": None,
        "has_source_annotation": False,
        "has_headers_builder": False,
        "has_cookies": False,
        "methods": {
            "GET": False,
            "POST": False,
        },
        "overrides": {
            "popularManga": False,
            "latestUpdates": False,
            "searchManga": False,
            "mangaDetails": False,
            "chapterList": False,
            "pageList": False,
        },
        "uses_json": False,
        "imports": [],
    }

    # Package
    pkg_match = re.search(r"^package\s+([a-zA-Z0-9_.]+)", content, re.MULTILINE)
    if pkg_match:
        facts["package"] = pkg_match.group(1)

    # Class and Base Class
    class_match = re.search(r"class\s+([A-Za-z0-9_]+)\s*(?:\([^)]*\))?\s*:\s*([A-Za-z0-9_]+)", content)
    if class_match:
        facts["class_name"] = class_match.group(1)
        facts["base_class"] = class_match.group(2)

    # @Source Annotation
    if re.search(r"@Source\b", content):
        facts["has_source_annotation"] = True

    # Headers
    if "headersBuilder(" in content or "headersBuilder()" in content or 'Headers.Builder' in content:
        facts["has_headers_builder"] = True

    # Cookies
    if "Cookie.Builder" in content or "addCookie" in content or "CookieManager" in content:
        facts["has_cookies"] = True

    # HTTP Methods
    if "GET(" in content or ".get(" in content:
        facts["methods"]["GET"] = True
    if "POST(" in content or ".post(" in content:
        facts["methods"]["POST"] = True

    # Overrides/Methods presence
    if "popularMangaRequest" in content or "popularMangaParse" in content:
        facts["overrides"]["popularManga"] = True
    if "latestUpdatesRequest" in content or "latestUpdatesParse" in content:
        facts["overrides"]["latestUpdates"] = True
    if "searchMangaRequest" in content or "searchMangaParse" in content:
        facts["overrides"]["searchManga"] = True
    if "mangaDetailsParse" in content:
        facts["overrides"]["mangaDetails"] = True
    if "chapterListParse" in content:
        facts["overrides"]["chapterList"] = True
    if "pageListParse" in content:
        facts["overrides"]["pageList"] = True

    # JSON parsing
    if "parseAs<" in content or "json.decodeFromString" in content or "kotlinx.serialization" in content:
        facts["uses_json"] = True

    # Imports (shared libs, utils)
    imports = re.findall(r"^import\s+([a-zA-Z0-9_.]+)", content, re.MULTILINE)
    for imp in imports:
        if imp.startswith("keiyoushi.") or imp.startswith("app.tachiyomi.lib."):
            facts["imports"].append(imp)

    # Extract all string literals that look like CSS selectors (naive approach, mostly for analysis)
    # We won't fully extract them here unless requested, but we can look for csslib indicators
    # We will rely on selector_analyzer for the actual analysis of provided selectors

    return facts


def extract_method_body(content: str, method_name: str) -> Optional[str]:
    """
    Extracts the body of a Kotlin method given its name.
    This handles balanced curly braces as well as expression bodies (e.g. fun ... = ...).
    """
    decl_pattern = re.compile(rf"fun\s+{method_name}\s*\([^)]*\)(?:(?!\bfun\b)[^{{=])*([{{=])")
    match = decl_pattern.search(content)
    if not match:
        return None

    char_found = match.group(1)
    idx = match.end()

    if char_found == '=':
        while idx < len(content) and content[idx].isspace():
            idx += 1

        start_of_expr = idx
        while idx < len(content):
            c = content[idx]
            if c == '{' or c == '\n':
                break
            idx += 1

        if idx < len(content) and content[idx] == '{':
            start_idx = idx
            is_expression_block = True
        else:
            return content[start_of_expr:idx].strip()
    else:
        start_idx = match.end() - 1
        start_of_expr = start_idx + 1
        is_expression_block = False

    brace_count = 0
    in_string = False
    escape = False

    for i in range(start_idx, len(content)):
        char = content[i]
        if in_string:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                if is_expression_block:
                    return content[start_of_expr:i + 1].strip()
                else:
                    return content[start_idx + 1:i].strip()

    return None
