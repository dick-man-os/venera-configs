import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_STRING_LITERAL = r'"(?:\\.|[^"\\])*"'


def _find_matching_delimiter(
    content: str,
    opening_index: int,
    opening: str,
    closing: str,
) -> Optional[int]:
    depth = 0
    state = "NORMAL"
    block_comment_depth = 0
    i = opening_index

    while i < len(content):
        char = content[i]
        pair = content[i : i + 2]
        triple = content[i : i + 3]

        if state == "NORMAL":
            if triple == '"""':
                state = "TRIPLE_QUOTE"
                i += 3
                continue
            if char == '"':
                state = "QUOTE"
            elif char == "'":
                state = "CHAR"
            elif pair == "//":
                state = "LINE_COMMENT"
                i += 2
                continue
            elif pair == "/*":
                state = "BLOCK_COMMENT"
                block_comment_depth = 1
                i += 2
                continue
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return i
        elif state == "QUOTE":
            if char == "\\":
                i += 2
                continue
            if char == '"':
                state = "NORMAL"
        elif state == "CHAR":
            if char == "\\":
                i += 2
                continue
            if char == "'":
                state = "NORMAL"
        elif state == "TRIPLE_QUOTE":
            if triple == '"""':
                state = "NORMAL"
                i += 3
                continue
        elif state == "LINE_COMMENT":
            if char == "\n":
                state = "NORMAL"
        elif state == "BLOCK_COMMENT":
            if pair == "/*":
                block_comment_depth += 1
                i += 2
                continue
            if pair == "*/":
                block_comment_depth -= 1
                i += 2
                if block_comment_depth == 0:
                    state = "NORMAL"
                continue
        i += 1

    return None


def _find_named_block_spans(content: str, name: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    state = "NORMAL"
    block_comment_depth = 0
    i = 0

    while i < len(content):
        char = content[i]
        pair = content[i : i + 2]
        triple = content[i : i + 3]

        if state == "NORMAL":
            if triple == '"""':
                state = "TRIPLE_QUOTE"
                i += 3
                continue
            if char == '"':
                state = "QUOTE"
            elif char == "'":
                state = "CHAR"
            elif pair == "//":
                state = "LINE_COMMENT"
                i += 2
                continue
            elif pair == "/*":
                state = "BLOCK_COMMENT"
                block_comment_depth = 1
                i += 2
                continue
            elif content.startswith(name, i):
                before = content[i - 1] if i else ""
                after_index = i + len(name)
                after = content[after_index] if after_index < len(content) else ""
                if not (before.isalnum() or before == "_") and not (
                    after.isalnum() or after == "_"
                ):
                    block_start = after_index
                    while block_start < len(content) and content[block_start].isspace():
                        block_start += 1
                    if block_start < len(content) and content[block_start] == "{":
                        block_end = _find_matching_delimiter(
                            content, block_start, "{", "}"
                        )
                        if block_end is not None:
                            spans.append((i, block_end + 1))
                            i = block_end + 1
                            continue
        elif state == "QUOTE":
            if char == "\\":
                i += 2
                continue
            if char == '"':
                state = "NORMAL"
        elif state == "CHAR":
            if char == "\\":
                i += 2
                continue
            if char == "'":
                state = "NORMAL"
        elif state == "TRIPLE_QUOTE":
            if triple == '"""':
                state = "NORMAL"
                i += 3
                continue
        elif state == "LINE_COMMENT":
            if char == "\n":
                state = "NORMAL"
        elif state == "BLOCK_COMMENT":
            if pair == "/*":
                block_comment_depth += 1
                i += 2
                continue
            if pair == "*/":
                block_comment_depth -= 1
                i += 2
                if block_comment_depth == 0:
                    state = "NORMAL"
                continue
        i += 1

    return spans


def _strip_comments(content: str) -> str:
    output = list(content)
    state = "NORMAL"
    block_comment_depth = 0
    i = 0

    while i < len(content):
        char = content[i]
        pair = content[i : i + 2]
        triple = content[i : i + 3]

        if state == "NORMAL":
            if triple == '"""':
                state = "TRIPLE_QUOTE"
                i += 3
                continue
            if char == '"':
                state = "QUOTE"
            elif char == "'":
                state = "CHAR"
            elif pair == "//":
                state = "LINE_COMMENT"
                output[i] = output[i + 1] = " "
                i += 2
                continue
            elif pair == "/*":
                state = "BLOCK_COMMENT"
                block_comment_depth = 1
                output[i] = output[i + 1] = " "
                i += 2
                continue
        elif state == "QUOTE":
            if char == "\\":
                i += 2
                continue
            if char == '"':
                state = "NORMAL"
        elif state == "CHAR":
            if char == "\\":
                i += 2
                continue
            if char == "'":
                state = "NORMAL"
        elif state == "TRIPLE_QUOTE":
            if triple == '"""':
                state = "NORMAL"
                i += 3
                continue
        elif state == "LINE_COMMENT":
            if char == "\n":
                state = "NORMAL"
            else:
                output[i] = " "
        elif state == "BLOCK_COMMENT":
            if pair == "/*":
                block_comment_depth += 1
                output[i] = output[i + 1] = " "
                i += 2
                continue
            if pair == "*/":
                block_comment_depth -= 1
                output[i] = output[i + 1] = " "
                i += 2
                if block_comment_depth == 0:
                    state = "NORMAL"
                continue
            if char not in "\r\n":
                output[i] = " "
        i += 1

    return "".join(output)


def _blank_spans(content: str, spans: List[Tuple[int, int]]) -> str:
    chars = list(content)
    for start, end in spans:
        for index in range(start, end):
            if chars[index] not in "\r\n":
                chars[index] = " "
    return "".join(chars)


def _direct_nested_block_spans(content: str) -> List[Tuple[int, int]]:
    opening_index = content.find("{")
    if opening_index < 0:
        return []

    nested_spans: List[Tuple[int, int]] = []
    state = "NORMAL"
    block_comment_depth = 0
    i = opening_index + 1
    while i < len(content):
        char = content[i]
        pair = content[i : i + 2]
        triple = content[i : i + 3]
        if state == "NORMAL":
            if triple == '"""':
                state = "TRIPLE_QUOTE"
                i += 3
                continue
            if char == '"':
                state = "QUOTE"
            elif char == "'":
                state = "CHAR"
            elif pair == "//":
                state = "LINE_COMMENT"
                i += 2
                continue
            elif pair == "/*":
                state = "BLOCK_COMMENT"
                block_comment_depth = 1
                i += 2
                continue
            elif char == "{":
                closing_index = _find_matching_delimiter(content, i, "{", "}")
                if closing_index is None:
                    break
                nested_spans.append((i, closing_index + 1))
                i = closing_index + 1
                continue
        elif state == "QUOTE":
            if char == "\\":
                i += 2
                continue
            if char == '"':
                state = "NORMAL"
        elif state == "CHAR":
            if char == "\\":
                i += 2
                continue
            if char == "'":
                state = "NORMAL"
        elif state == "TRIPLE_QUOTE":
            if triple == '"""':
                state = "NORMAL"
                i += 3
                continue
        elif state == "LINE_COMMENT":
            if char == "\n":
                state = "NORMAL"
        elif state == "BLOCK_COMMENT":
            if pair == "/*":
                block_comment_depth += 1
                i += 2
                continue
            if pair == "*/":
                block_comment_depth -= 1
                i += 2
                if block_comment_depth == 0:
                    state = "NORMAL"
                continue
        i += 1
    return nested_spans


def _direct_block_content(content: str) -> str:
    return _blank_spans(content, _direct_nested_block_spans(content))


def _assignment_expression(content: str, key: str) -> Tuple[bool, Optional[str]]:
    cleaned = _strip_comments(content)
    match = re.search(
        rf"(?m)(?:^|[;{{])[ \t]*(?:this\.)?{re.escape(key)}\s*=\s*([^\r\n;}}]+)",
        cleaned,
    )
    if not match:
        return False, None
    return True, match.group(1).strip()


def _parse_string_literal(expression: Optional[str]) -> Optional[str]:
    if expression is None or not re.fullmatch(_STRING_LITERAL, expression):
        return None
    if re.search(r"(?<!\\)\$", expression):
        return None
    try:
        return json.loads(expression.replace(r"\$", "$"))
    except json.JSONDecodeError:
        return None


def _string_assignment(content: str, key: str) -> Tuple[bool, Optional[str]]:
    present, expression = _assignment_expression(content, key)
    return present, _parse_string_literal(expression)


def _integer_assignment(
    content: str,
    key: str,
    *,
    allow_long_suffix: bool = False,
) -> Tuple[bool, Optional[int], Optional[str]]:
    present, expression = _assignment_expression(content, key)
    if not present or expression is None:
        return present, None, None
    suffix = "L?" if allow_long_suffix else ""
    match = re.fullmatch(rf"(-?\d+){suffix}", expression)
    if not match:
        return True, None, expression
    literal = match.group(1)
    return True, int(literal), literal


def _find_call_arguments(content: str, name: str) -> List[str]:
    direct_content = _direct_block_content(content)
    cleaned = _strip_comments(direct_content)
    searchable = re.sub(_STRING_LITERAL, lambda match: " " * len(match.group(0)), cleaned)
    searchable = re.sub(
        r'""".*?"""',
        lambda match: "".join(
            char if char in "\r\n" else " " for char in match.group(0)
        ),
        searchable,
        flags=re.DOTALL,
    )
    calls: List[str] = []
    for match in re.finditer(rf"\b{re.escape(name)}\s*\(", searchable):
        opening_index = searchable.find("(", match.start())
        closing_index = _find_matching_delimiter(
            cleaned, opening_index, "(", ")"
        )
        if closing_index is not None:
            calls.append(direct_content[opening_index + 1 : closing_index])
    return calls


def _split_arguments(content: str) -> List[str]:
    cleaned = _strip_comments(content)
    arguments: List[str] = []
    start = 0
    state = "NORMAL"
    depth = 0
    i = 0

    while i < len(cleaned):
        char = cleaned[i]
        triple = cleaned[i : i + 3]
        if state == "NORMAL":
            if triple == '"""':
                state = "TRIPLE_QUOTE"
                i += 3
                continue
            if char == '"':
                state = "QUOTE"
            elif char == "'":
                state = "CHAR"
            elif char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
            elif char == "," and depth == 0:
                token = content[start:i].strip()
                if token:
                    arguments.append(token)
                start = i + 1
        elif state == "QUOTE":
            if char == "\\":
                i += 2
                continue
            if char == '"':
                state = "NORMAL"
        elif state == "CHAR":
            if char == "\\":
                i += 2
                continue
            if char == "'":
                state = "NORMAL"
        elif state == "TRIPLE_QUOTE":
            if triple == '"""':
                state = "NORMAL"
                i += 3
                continue
        i += 1

    token = content[start:].strip()
    if token:
        arguments.append(token)
    return arguments


def _compute_source_id(name: str, lang: str, version_id: int) -> str:
    key = f"{name.lower()}/{lang}/{version_id}"
    digest_prefix = hashlib.md5(key.encode("utf-8")).digest()[:8]
    value = int.from_bytes(digest_prefix, byteorder="big") & ((1 << 63) - 1)
    return str(value)


def _parse_base_url(source_block: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "baseUrlMode": "unresolved",
        "defaultBaseUrl": None,
        "baseUrlResolved": False,
        "mirrors": [],
    }
    unresolved: List[str] = []

    direct_source = _direct_block_content(source_block)
    assignment_present, static_url = _string_assignment(direct_source, "baseUrl")
    direct_nested_ends = {
        end for _, end in _direct_nested_block_spans(source_block)
    }
    base_url_blocks = [
        span
        for span in _find_named_block_spans(source_block, "baseUrl")
        if span[1] in direct_nested_ends
    ]
    if assignment_present and base_url_blocks:
        raise ValueError("source { } cannot declare both baseUrl = and baseUrl { }")

    if assignment_present:
        result["baseUrlMode"] = "static"
        if static_url is not None:
            result["defaultBaseUrl"] = static_url
            result["baseUrl"] = static_url
            result["baseUrlResolved"] = True
        else:
            _, expression = _assignment_expression(direct_source, "baseUrl")
            result["baseUrlExpression"] = expression
            unresolved.append("baseUrl")
    elif base_url_blocks:
        if len(base_url_blocks) != 1:
            raise ValueError("source { } must contain at most one baseUrl { } block")
        start, end = base_url_blocks[0]
        base_url_block = source_block[start:end]
        mirror_calls = _find_call_arguments(base_url_block, "mirrors")
        custom_calls = _find_call_arguments(base_url_block, "custom")
        if mirror_calls and custom_calls:
            raise ValueError("baseUrl { } cannot mix mirrors(...) and custom(...)")
        if len(mirror_calls) > 1 or len(custom_calls) > 1:
            raise ValueError("baseUrl { } must declare exactly one URL mode")

        if mirror_calls:
            result["baseUrlMode"] = "mirrors"
            arguments = _split_arguments(mirror_calls[0])
            if not arguments:
                raise ValueError("mirrors(...) requires at least one URL")

            labeled_flags = []
            mirrors = []
            for argument in arguments:
                pair_match = re.fullmatch(
                    rf"\s*({_STRING_LITERAL})\s+to\s+({_STRING_LITERAL})\s*",
                    argument,
                )
                if pair_match:
                    labeled_flags.append(True)
                    label = _parse_string_literal(pair_match.group(1))
                    url = _parse_string_literal(pair_match.group(2))
                    if label is not None and url is not None:
                        mirrors.append({"label": label, "url": url})
                    else:
                        mirrors.append({"unresolvedExpression": argument})
                        unresolved.append("baseUrl.mirrors")
                    continue

                labeled_flags.append(False)
                url = _parse_string_literal(argument)
                if url is not None:
                    mirrors.append({"url": url})
                else:
                    mirrors.append({"unresolvedExpression": argument})
                    unresolved.append("baseUrl.mirrors")

            if any(labeled_flags) and not all(labeled_flags):
                raise ValueError("Mixed labeled and unlabeled mirrors are not permitted.")
            result["mirrors"] = mirrors
            if mirrors and "url" in mirrors[0]:
                result["defaultBaseUrl"] = mirrors[0]["url"]
                result["baseUrl"] = mirrors[0]["url"]
            result["baseUrlResolved"] = not unresolved
        elif custom_calls:
            result["baseUrlMode"] = "custom"
            result["customBaseUrl"] = True
            arguments = _split_arguments(custom_calls[0])
            if len(arguments) != 1:
                raise ValueError("custom(...) requires exactly one default URL")
            default_url = _parse_string_literal(arguments[0])
            if default_url is not None:
                result["defaultBaseUrl"] = default_url
                result["baseUrl"] = default_url
                result["baseUrlResolved"] = True
            else:
                result["baseUrlExpression"] = arguments[0]
                unresolved.append("baseUrl.custom")
        else:
            unresolved.append("baseUrl")
    else:
        unresolved.append("baseUrl")

    if unresolved:
        result["unresolved"] = list(dict.fromkeys(unresolved))
    return result


def _parse_source(source_block: str, extension_name: Optional[str]) -> Dict[str, Any]:
    source: Dict[str, Any] = {}
    unresolved: List[str] = []
    direct_source = _direct_block_content(source_block)

    name_present, declared_name = _string_assignment(direct_source, "name")
    if name_present:
        source["declaredName"] = declared_name
        source["name"] = declared_name
        source["nameIsDefault"] = False
        if declared_name is None:
            unresolved.append("name")
    else:
        source["declaredName"] = None
        source["name"] = extension_name
        source["nameIsDefault"] = True
        if extension_name is None:
            unresolved.append("name")

    lang_present, lang = _string_assignment(direct_source, "lang")
    source["lang"] = lang
    if not lang_present or lang is None:
        unresolved.append("lang")

    version_present, version_value, _ = _integer_assignment(
        direct_source, "versionId"
    )
    if version_present:
        source["versionId"] = version_value
        if version_value is None:
            unresolved.append("versionId")
    effective_version_id = version_value if version_present else 1
    source["effectiveVersionId"] = effective_version_id

    id_present, _, id_literal = _integer_assignment(
        direct_source, "id", allow_long_suffix=True
    )
    if id_present:
        source["id"] = id_literal
        source["sourceId"] = id_literal
        source["sourceIdKind"] = "explicit" if id_literal is not None else "unresolved"
        if id_literal is None:
            unresolved.append("id")
    elif (
        source.get("name") is not None
        and lang is not None
        and effective_version_id is not None
    ):
        source["sourceId"] = _compute_source_id(
            source["name"], lang, effective_version_id
        )
        source["sourceIdKind"] = "generated"
    else:
        source["sourceId"] = None
        source["sourceIdKind"] = "unresolved"
        unresolved.append("sourceId")

    base_url = _parse_base_url(source_block)
    source.update(base_url)
    unresolved.extend(base_url.get("unresolved", []))
    if unresolved:
        source["unresolved"] = list(dict.fromkeys(unresolved))
    return source


def _infer_extensions_root(build_gradle_path: Path) -> Optional[Path]:
    for parent in build_gradle_path.resolve().parents:
        if (parent / "lib-multisrc").is_dir() and (parent / "src").is_dir():
            return parent
    return None


def _top_level_block(content: str) -> str:
    keiyoushi_blocks = _find_named_block_spans(content, "keiyoushi")
    if not keiyoushi_blocks:
        return _blank_spans(content, _find_named_block_spans(content, "source"))
    if len(keiyoushi_blocks) != 1:
        raise ValueError("Expected exactly one keiyoushi { } block")
    start, end = keiyoushi_blocks[0]
    block = content[start:end]
    return _direct_block_content(block)


def _parse_theme_metadata(theme_name: str, extensions_root: Optional[Path]) -> Dict[str, Any]:
    theme_metadata: Dict[str, Any] = {"name": theme_name, "resolved": False}
    if extensions_root is None:
        theme_metadata["unresolvedReason"] = "extensions root could not be inferred"
        return theme_metadata

    theme_build = extensions_root / "lib-multisrc" / theme_name / "build.gradle.kts"
    if not theme_build.is_file():
        theme_metadata["unresolvedReason"] = "theme build.gradle.kts not found"
        return theme_metadata

    content = theme_build.read_text(encoding="utf-8")
    top_level = _top_level_block(content)
    base_present, base_version_code, _ = _integer_assignment(
        top_level, "baseVersionCode"
    )
    lib_present, lib_version = _string_assignment(top_level, "libVersion")
    theme_metadata.update(
        {
            "baseVersionCode": base_version_code,
            "libVersion": lib_version,
        }
    )
    if base_present and base_version_code is not None and lib_present and lib_version:
        theme_metadata["resolved"] = True
    else:
        theme_metadata["unresolvedReason"] = "theme version metadata is not static"
    return theme_metadata


def parse_gradle_metadata(
    build_gradle_path: str,
    extensions_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse statically recoverable metadata from a Keiyoushi Gradle module."""
    build_path = Path(build_gradle_path)
    content = build_path.read_text(encoding="utf-8")
    top_level = _top_level_block(content)
    keiyoushi_blocks = _find_named_block_spans(content, "keiyoushi")
    source_region = (
        content[keiyoushi_blocks[0][0] : keiyoushi_blocks[0][1]]
        if keiyoushi_blocks
        else content
    )
    source_spans = _find_named_block_spans(source_region, "source")

    metadata: Dict[str, Any] = {
        "sources": [],
        "is_multisrc": False,
        "is_modern": False,
        "is_legacy": False,
        "version_classification": "UNKNOWN",
    }
    unresolved: List[str] = []

    name_present, name = _string_assignment(top_level, "name")
    metadata["name"] = name
    if not name_present or name is None:
        unresolved.append("name")

    version_present, version_code, _ = _integer_assignment(top_level, "versionCode")
    metadata["versionCode"] = version_code
    if not version_present or version_code is None:
        unresolved.append("versionCode")

    lib_present, lib_version = _string_assignment(top_level, "libVersion")
    metadata["libVersion"] = lib_version
    if not lib_present or lib_version is None:
        unresolved.append("libVersion")

    warning_present, warning_expression = _assignment_expression(
        top_level, "contentWarning"
    )
    warning_match = (
        re.fullmatch(r"ContentWarning\.([A-Z_]+)", warning_expression)
        if warning_expression
        else None
    )
    metadata["contentWarning"] = warning_match.group(1) if warning_match else None
    if not warning_present or warning_match is None:
        unresolved.append("contentWarning")

    theme_present, theme = _string_assignment(top_level, "theme")
    metadata["theme"] = theme
    if theme_present and theme is None:
        unresolved.append("theme")
        _, theme_expression = _assignment_expression(top_level, "theme")
        metadata["themeExpression"] = theme_expression
    metadata["is_multisrc"] = theme_present

    if lib_version == "1.6":
        metadata["is_modern"] = True
        metadata["version_classification"] = "MODERN_KEISOURCE"
    elif lib_version == "1.4":
        metadata["is_legacy"] = True
        metadata["version_classification"] = "LEGACY_HTTPSOURCE"

    root = Path(extensions_root) if extensions_root else _infer_extensions_root(build_path)
    derived_version_code = version_code
    version_reason = None
    if theme_present and theme is None:
        derived_version_code = None
        version_reason = "theme is not statically recoverable"
    elif theme is not None:
        theme_metadata = _parse_theme_metadata(theme, root)
        metadata["themeMetadata"] = theme_metadata
        if not theme_metadata["resolved"]:
            derived_version_code = None
            version_reason = theme_metadata["unresolvedReason"]
        elif lib_version != theme_metadata["libVersion"]:
            derived_version_code = None
            version_reason = "extension and theme libVersion values do not match"
        elif version_code is not None:
            derived_version_code = theme_metadata["baseVersionCode"] + version_code

    metadata["derivedVersionCode"] = derived_version_code
    if lib_version is not None and derived_version_code is not None:
        metadata["version"] = f"{lib_version}.{derived_version_code}"
        metadata["versionResolution"] = "resolved"
    else:
        metadata["version"] = None
        metadata["versionResolution"] = "unresolved"
        metadata["versionUnresolvedReason"] = version_reason or (
            "libVersion or versionCode is not statically recoverable"
        )
        unresolved.append("version")

    for start, end in source_spans:
        metadata["sources"].append(_parse_source(source_region[start:end], name))

    if unresolved:
        metadata["unresolved"] = list(dict.fromkeys(unresolved))
    return metadata
