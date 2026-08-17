import re
from typing import Any, Dict, List, Optional

def parse_gradle_metadata(build_gradle_path: str) -> Dict[str, Any]:
    """Parse a Keiyoushi build.gradle.kts file for extension metadata."""
    with open(build_gradle_path, "r", encoding="utf-8") as f:
        content = f.read()

    metadata = {
        "sources": [],
        "is_multisrc": False,
        "is_modern": False,
        "is_legacy": False,
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
        # A more robust check for multisrc
        if re.search(r'project\(":lib-multisrc:', content):
            metadata["is_multisrc"] = True

    # Detect modern vs legacy
    if metadata["libVersion"]:
        if metadata["libVersion"].startswith("1.6") or metadata["libVersion"].startswith("1.5"):
            metadata["is_modern"] = True
        elif metadata["libVersion"].startswith("1.4") or metadata["libVersion"].startswith("1.3"):
            metadata["is_legacy"] = True

    # Extract source {} blocks
    # We will find all source blocks and extract them.
    # Source block looks like: source { ... }
    # Nested braces might be present (e.g. baseUrl { mirrors(...) })

    # A simple approach to find blocks that start with "source {" and end with "}" at the same indentation
    # Since we can't easily do nested braces with simple regex, we'll try an iterative bracket matcher
    # or just look for 'source {' and find the matching '}'

    sources = []

    idx = 0
    while True:
        idx = content.find("source {", idx)
        if idx == -1:
            break

        brace_count = 0
        end_idx = -1
        for i in range(idx + 6, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break

        if end_idx == -1:
            break

        source_block = content[idx:end_idx+1]
        idx = end_idx + 1

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

        # Check for baseUrl
        s_base_url_simple = re.search(r'baseUrl\s*=\s*"([^"]+)"', source_block)
        if s_base_url_simple:
            source_meta["baseUrl"] = s_base_url_simple.group(1)
        else:
            # Check for mirrors or custom
            mirrors_match = re.search(r'mirrors\s*\((.*?)\)', source_block, re.DOTALL)
            custom_match = re.search(r'custom\s*\(', source_block)
            if mirrors_match:
                urls = re.findall(r'"([^"]+)"', mirrors_match.group(1))
                if urls:
                    source_meta["baseUrl"] = urls[0]
                    source_meta["mirrors"] = urls
            if custom_match:
                source_meta["customBaseUrl"] = True

        sources.append(source_meta)

    metadata["sources"] = sources
    return metadata
