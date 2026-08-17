import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

def parse_gradle_metadata(build_gradle_path: str) -> Dict[str, Any]:
    """Parse a Keiyoushi build.gradle.kts file for extension metadata."""
    with open(build_gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata = {
        "sources": [],
        "is_multisrc": False,
        "is_modern": False,
        "is_legacy": False,
        "version_classification": "UNKNOWN"
    }

    # Extract top-level Keiyoushi metadata
    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
    metadata["name"] = name_match.group(1) if name_match else None

    version_code_match = re.search(r"versionCode\s*=\s*(\d+)", content)
    metadata["versionCode"] = int(version_code_match.group(1)) if version_code_match else None

    lib_version_match = re.search(r'libVersion\s*=\s*"([^"]+)"', content)
    metadata["libVersion"] = lib_version_match.group(1) if lib_version_match else None

    content_warning_match = re.search(r"contentWarning\s*=\s*ContentWarning\.([A-Z_]+)", content)
    metadata["contentWarning"] = content_warning_match.group(1) if content_warning_match else "SAFE"

    # Detect multisrc
    theme_match = re.search(r'themePkg\s*=\s*"([^"]+)"|themeClass\s*=\s*"([^"]+)"', content)
    if theme_match or 'ext-multisrc' in content or 'multisrcLibrary' in content or 'theme' in content.lower():
        if re.search(r'project\(":lib-multisrc:', content):
            metadata["is_multisrc"] = True

    # Detect modern vs legacy precisely
    if metadata["libVersion"]:
        if metadata["libVersion"] == "1.6":
            metadata["is_modern"] = True
            metadata["version_classification"] = "MODERN_KEISOURCE"
        elif metadata["libVersion"] == "1.4":
            metadata["is_legacy"] = True
            metadata["version_classification"] = "LEGACY_HTTPSOURCE"

    # String/comment-safe brace scanner
    blocks = []
    state = "NORMAL"
    brace_depth = 0
    in_source = False
    source_start_idx = -1

    i = 0
    while i < len(content):
        c = content[i]
        if state == "NORMAL":
            if c == '"':
                if content[i:i+3] == '"""':
                    state = "TRIPLE_QUOTE"
                    i += 2
                else:
                    state = "QUOTE"
            elif c == '/' and i + 1 < len(content):
                if content[i+1] == '/':
                    state = "LINE_COMMENT"
                    i += 1
                elif content[i+1] == '*':
                    state = "BLOCK_COMMENT"
                    i += 1
            else:
                if not in_source and content[i:i+6] == "source" and brace_depth == 0:
                    m = re.match(r'source\s*\{', content[i:])
                    if m:
                        in_source = True
                        source_start_idx = i
                        brace_depth = 1
                        i += len(m.group(0))
                        continue
                elif in_source:
                    if c == '{':
                        brace_depth += 1
                    elif c == '}':
                        brace_depth -= 1
                        if brace_depth == 0:
                            blocks.append(content[source_start_idx:i+1])
                            in_source = False

        elif state == "QUOTE":
            if c == '\\':
                state = "QUOTE_ESCAPE"
            elif c == '"':
                state = "NORMAL"
        elif state == "QUOTE_ESCAPE":
            state = "QUOTE"
        elif state == "TRIPLE_QUOTE":
            if c == '"' and content[i:i+3] == '"""':
                state = "NORMAL"
                i += 2
        elif state == "LINE_COMMENT":
            if c == '\n':
                state = "NORMAL"
        elif state == "BLOCK_COMMENT":
            if c == '*' and i + 1 < len(content) and content[i+1] == '/':
                state = "NORMAL"
                i += 1
        i += 1


    sources = []
    for source_block in blocks:
        source_meta = {}

        s_name = re.search(r'name\s*=\s*"([^"]+)"', source_block)
        if s_name:
            source_meta["name"] = s_name.group(1)

        s_lang = re.search(r'lang\s*=\s*"([^"]+)"', source_block)
        if s_lang:
            source_meta["lang"] = s_lang.group(1)

        s_id = re.search(r'id\s*=\s*([0-9L-]+)', source_block)
        if s_id:
            val = s_id.group(1)
            if val.endswith('L'): val = val[:-1]
            source_meta["id"] = int(val)

        s_versionId = re.search(r'versionId\s*=\s*(\d+)', source_block)
        if s_versionId:
            source_meta["versionId"] = int(s_versionId.group(1))

        s_base_url_simple = re.search(r'baseUrl\s*=\s*"([^"]+)"', source_block)
        if s_base_url_simple:
            source_meta["baseUrl"] = s_base_url_simple.group(1)
        else:
            mirrors_match = re.search(r'mirrors\s*\((.*?)\)', source_block, re.DOTALL)
            custom_match = re.search(r'custom\s*\(', source_block)
            if mirrors_match:
                inner_text = mirrors_match.group(1)

                labeled_matches = re.findall(r'"([^"]+)"\s*to\s*"([^"]+)"', inner_text)

                # Check for unlabeled matches
                # We need to be careful to not count URLs inside labeled matches as unlabeled matches.
                # A safe way is to remove labeled matches from inner_text first.
                stripped_text = re.sub(r'"[^"]+"\s*to\s*"[^"]+"', '', inner_text)
                unlabeled_matches = re.findall(r'"([^"]+)"', stripped_text)

                if labeled_matches and unlabeled_matches:
                    raise ValueError("Mixed labeled and unlabeled mirrors are not permitted.")

                if labeled_matches:
                    mirrors = []
                    for label, url in labeled_matches:
                        mirrors.append({"label": label, "url": url})
                    if mirrors:
                        source_meta["baseUrl"] = mirrors[0]["url"]
                        source_meta["mirrors"] = mirrors
                else:
                    unlabeled_matches = re.findall(r'"([^"]+)"', inner_text)
                    if unlabeled_matches:
                        mirrors = []
                        for url in unlabeled_matches:
                            mirrors.append({"url": url})
                        source_meta["baseUrl"] = mirrors[0]["url"]
                        source_meta["mirrors"] = mirrors
            if custom_match:
                source_meta["customBaseUrl"] = True

        sources.append(source_meta)

    metadata["sources"] = sources
    return metadata
