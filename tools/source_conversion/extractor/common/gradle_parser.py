import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_STRING_LITERAL = r'"(?:\\.|[^"\\])*"'

MAX_STATIC_EXPANSION = 512
MAX_LITERAL_RESOLUTION_DEPTH = 16


class _UnresolvedValue:
    pass


_UNRESOLVED_VALUE = _UnresolvedValue()
_WHEN_ELSE = object()


class _LiteralMap:
    def __init__(self, entries: List[Tuple[Any, Any]]) -> None:
        self.entries = entries


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


def _mask_non_code(content: str) -> str:
    """Blank comments and literals while preserving offsets and newlines."""
    cleaned = _strip_comments(content)
    output = list(cleaned)
    state = "NORMAL"
    i = 0
    while i < len(cleaned):
        char = cleaned[i]
        triple = cleaned[i : i + 3]
        if state == "NORMAL":
            if triple == '"""':
                output[i : i + 3] = "   "
                state = "TRIPLE_QUOTE"
                i += 3
                continue
            if char == '"':
                output[i] = " "
                state = "QUOTE"
            elif char == "'":
                output[i] = " "
                state = "CHAR"
        elif state == "QUOTE":
            if char == "\\":
                output[i] = " "
                if i + 1 < len(output):
                    output[i + 1] = " "
                i += 2
                continue
            if char == '"':
                state = "NORMAL"
            output[i] = " "
        elif state == "CHAR":
            if char == "\\":
                output[i] = " "
                if i + 1 < len(output):
                    output[i + 1] = " "
                i += 2
                continue
            if char == "'":
                state = "NORMAL"
            output[i] = " "
        elif state == "TRIPLE_QUOTE":
            if triple == '"""':
                output[i : i + 3] = "   "
                state = "NORMAL"
                i += 3
                continue
            if char not in "\r\n":
                output[i] = " "
        i += 1
    return "".join(output)


def _brace_depth_at(content: str, index: int) -> int:
    masked = _mask_non_code(content)
    return masked[:index].count("{") - masked[:index].count("}")


def _block_body(content: str) -> str:
    opening_index = _mask_non_code(content).find("{")
    if opening_index < 0:
        return content
    closing_index = _find_matching_delimiter(content, opening_index, "{", "}")
    if closing_index is None:
        return content
    return content[opening_index + 1 : closing_index]


def _find_matching_opening(
    content: str,
    closing_index: int,
    opening: str,
    closing: str,
) -> Optional[int]:
    depth = 0
    for index in range(closing_index, -1, -1):
        char = content[index]
        if char == closing:
            depth += 1
        elif char == opening:
            depth -= 1
            if depth == 0:
                return index
    return None


def _split_top_level(content: str, delimiter: str) -> List[str]:
    masked = _mask_non_code(content)
    parts: List[str] = []
    start = 0
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    i = 0
    while i < len(masked):
        char = masked[i]
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
        elif (
            masked.startswith(delimiter, i)
            and paren_depth == 0
            and bracket_depth == 0
            and brace_depth == 0
        ):
            parts.append(content[start:i].strip())
            start = i + len(delimiter)
            i += len(delimiter)
            continue
        i += 1
    parts.append(content[start:].strip())
    return parts


def _collect_local_bindings(
    content: str,
) -> Tuple[Dict[str, str], set[str]]:
    """Collect direct immutable local RHS text without evaluating Kotlin."""
    masked = _mask_non_code(content)
    bindings: Dict[str, str] = {}
    invalid: set[str] = set()
    pattern = re.compile(r"\b(val|var)\s+([A-Za-z_]\w*)\s*=")
    for match in pattern.finditer(masked):
        if _brace_depth_at(content, match.start()) != 0:
            continue
        kind, name = match.group(1), match.group(2)
        expression_start = match.end()
        while expression_start < len(content) and content[expression_start].isspace():
            expression_start += 1
        call_match = re.match(r"(?:listOf|mapOf)\s*\(", masked[expression_start:])
        if call_match:
            opening_index = masked.find("(", expression_start)
            closing_index = _find_matching_delimiter(
                content, opening_index, "(", ")"
            )
            if closing_index is None:
                expression_end = len(content)
            else:
                expression_end = closing_index + 1
        else:
            expression_end = expression_start
            while expression_end < len(content) and content[expression_end] not in "\r\n;":
                expression_end += 1
        if kind != "val" or name in bindings or name in invalid:
            invalid.add(name)
            bindings.pop(name, None)
            continue
        bindings[name] = content[expression_start:expression_end].strip()
    return bindings, invalid


def _resolve_interpolated_string(
    expression: str,
    bindings: Dict[str, str],
    invalid_bindings: set[str],
    scope: Dict[str, Any],
    stack: Tuple[str, ...],
    depth: int,
) -> Any:
    sentinel = "__CODEX_ESCAPED_DOLLAR_7C3L__"
    protected = expression.replace(r"\$", sentinel)
    try:
        decoded = json.loads(protected)
    except json.JSONDecodeError:
        return _UNRESOLVED_VALUE

    interpolation = re.compile(r"\$(?:\{([A-Za-z_]\w*)\}|([A-Za-z_]\w*))")
    output: List[str] = []
    cursor = 0
    for match in interpolation.finditer(decoded):
        output.append(decoded[cursor : match.start()])
        name = match.group(1) or match.group(2)
        value = _resolve_expression(
            name,
            bindings,
            invalid_bindings,
            scope,
            stack=stack,
            depth=depth + 1,
        )
        if value is _UNRESOLVED_VALUE or isinstance(value, (list, _LiteralMap)):
            return _UNRESOLVED_VALUE
        output.append(str(value))
        cursor = match.end()
    output.append(decoded[cursor:])
    result = "".join(output)
    if "$" in result:
        return _UNRESOLVED_VALUE
    return result.replace(sentinel, "$")


def _resolve_expression(
    expression: str,
    bindings: Dict[str, str],
    invalid_bindings: set[str],
    scope: Dict[str, Any],
    *,
    stack: Tuple[str, ...] = (),
    depth: int = 0,
) -> Any:
    """Resolve only the bounded literal grammar; all other syntax is opaque."""
    if depth > MAX_LITERAL_RESOLUTION_DEPTH:
        return _UNRESOLVED_VALUE
    expression = expression.strip()
    if not expression:
        return _UNRESOLVED_VALUE

    concatenated = _split_top_level(expression, "+")
    if len(concatenated) > 1:
        values = [
            _resolve_expression(
                item,
                bindings,
                invalid_bindings,
                scope,
                stack=stack,
                depth=depth + 1,
            )
            for item in concatenated
        ]
        if any(value is _UNRESOLVED_VALUE or not isinstance(value, str) for value in values):
            return _UNRESOLVED_VALUE
        return "".join(values)

    if re.fullmatch(_STRING_LITERAL, expression):
        return _resolve_interpolated_string(
            expression, bindings, invalid_bindings, scope, stack, depth
        )

    integer_match = re.fullmatch(r"(-?\d+)L?", expression)
    if integer_match:
        return int(integer_match.group(1))

    identifier_match = re.fullmatch(r"[A-Za-z_]\w*", expression)
    if identifier_match:
        name = identifier_match.group(0)
        if name in scope:
            return scope[name]
        if name in invalid_bindings or name not in bindings or name in stack:
            return _UNRESOLVED_VALUE
        return _resolve_expression(
            bindings[name],
            bindings,
            invalid_bindings,
            scope,
            stack=stack + (name,),
            depth=depth + 1,
        )

    call_match = re.fullmatch(r"(listOf|mapOf)\s*\((.*)\)", expression, re.DOTALL)
    if not call_match:
        return _UNRESOLVED_VALUE
    call_name, arguments_text = call_match.group(1), call_match.group(2)
    arguments = _split_arguments(arguments_text)
    if call_name == "listOf":
        values: List[Any] = []
        for argument in arguments:
            value = _resolve_expression(
                argument,
                bindings,
                invalid_bindings,
                scope,
                stack=stack,
                depth=depth + 1,
            )
            if value is _UNRESOLVED_VALUE or isinstance(value, (list, _LiteralMap)):
                return _UNRESOLVED_VALUE
            values.append(value)
        return values

    entries: List[Tuple[Any, Any]] = []
    seen_keys: set[Any] = set()
    for argument in arguments:
        pair = _split_top_level(argument, " to ")
        if len(pair) != 2:
            return _UNRESOLVED_VALUE
        key = _resolve_expression(
            pair[0],
            bindings,
            invalid_bindings,
            scope,
            stack=stack,
            depth=depth + 1,
        )
        value = _resolve_expression(
            pair[1],
            bindings,
            invalid_bindings,
            scope,
            stack=stack,
            depth=depth + 1,
        )
        if (
            key is _UNRESOLVED_VALUE
            or value is _UNRESOLVED_VALUE
            or isinstance(key, (list, _LiteralMap))
            or isinstance(value, (list, _LiteralMap))
            or key in seen_keys
        ):
            return _UNRESOLVED_VALUE
        seen_keys.add(key)
        entries.append((key, value))
    return _LiteralMap(entries)


def _direct_named_spans(content: str, name: str) -> List[Tuple[int, int]]:
    return [
        span
        for span in _find_named_block_spans(content, name)
        if _brace_depth_at(content, span[0]) == 0
    ]


def _find_direct_foreach_spans(content: str) -> List[Dict[str, Any]]:
    masked = _mask_non_code(content)
    loops: List[Dict[str, Any]] = []
    for match in re.finditer(r"\.forEach\s*\{", masked):
        dot_index = match.start()
        if _brace_depth_at(content, dot_index) != 0:
            continue
        opening_brace = masked.find("{", dot_index)
        closing_brace = _find_matching_delimiter(
            content, opening_brace, "{", "}"
        )
        if closing_brace is None:
            continue

        receiver_end = dot_index
        cursor = receiver_end - 1
        while cursor >= 0 and masked[cursor].isspace():
            cursor -= 1
        receiver_start = cursor
        if cursor >= 0 and masked[cursor] == ")":
            opening_paren = _find_matching_opening(masked, cursor, "(", ")")
            if opening_paren is None:
                receiver_start = cursor
            else:
                receiver_start = opening_paren - 1
                while receiver_start >= 0 and (
                    masked[receiver_start].isalnum() or masked[receiver_start] == "_"
                ):
                    receiver_start -= 1
                receiver_start += 1
        else:
            while receiver_start >= 0 and (
                masked[receiver_start].isalnum() or masked[receiver_start] == "_"
            ):
                receiver_start -= 1
            receiver_start += 1

        arrow_index = None
        for arrow in re.finditer(r"->", masked[opening_brace + 1 : closing_brace]):
            candidate = opening_brace + 1 + arrow.start()
            if _brace_depth_at(content, candidate) == 1:
                arrow_index = candidate
                break
        if arrow_index is None:
            binder_text = "it"
            body_start = opening_brace + 1
        else:
            binder_text = content[opening_brace + 1 : arrow_index].strip()
            body_start = arrow_index + 2

        loops.append(
            {
                "start": receiver_start,
                "end": closing_brace + 1,
                "receiver": content[receiver_start:receiver_end].strip(),
                "binder": binder_text,
                "body_start": body_start,
                "body_end": closing_brace,
            }
        )
    return loops


def _loop_scope(binder: str, value: Any) -> Optional[Dict[str, Any]]:
    identifier = re.fullmatch(r"[A-Za-z_]\w*", binder)
    if identifier and not isinstance(value, tuple):
        return {binder: value}
    destructured = re.fullmatch(
        r"\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*\)", binder
    )
    if destructured and isinstance(value, tuple) and len(value) == 2:
        return {destructured.group(1): value[0], destructured.group(2): value[1]}
    return None


def _expanded_source_blocks(
    content: str,
    bindings: Dict[str, str],
    invalid_bindings: set[str],
) -> List[Tuple[str, Dict[str, Any], bool]]:
    """Return source templates with literal loop scopes in source order."""
    source_spans = _find_named_block_spans(content, "source")
    loops = _find_direct_foreach_spans(content)
    events: List[Tuple[int, int, str, Dict[str, Any], bool]] = []
    handled: set[Tuple[int, int]] = set()
    sequence = 0
    expansion_count = 0

    for loop in loops:
        body = content[loop["body_start"] : loop["body_end"]]
        body_source_spans = _direct_named_spans(body, "source")
        body_deeplink_spans = _direct_named_spans(body, "deeplink")
        all_body_sources = _find_named_block_spans(body, "source")
        allowed = _blank_spans(body, body_source_spans + body_deeplink_spans)
        body_is_declarative = not _strip_comments(allowed).strip()
        body_is_declarative = body_is_declarative and (
            len(body_source_spans) == len(all_body_sources)
        )

        receiver_value = _resolve_expression(
            loop["receiver"], bindings, invalid_bindings, {}
        )
        if isinstance(receiver_value, _LiteralMap):
            values: Any = receiver_value.entries
        elif isinstance(receiver_value, list):
            values = receiver_value
        else:
            values = _UNRESOLVED_VALUE

        binder_names = re.findall(r"[A-Za-z_]\w*", loop["binder"])
        if any(name in bindings or name in invalid_bindings for name in binder_names):
            body_is_declarative = False

        global_loop_sources = [
            span
            for span in source_spans
            if loop["start"] <= span[0] and span[1] <= loop["end"]
        ]
        handled.update(global_loop_sources)
        if values is _UNRESOLVED_VALUE or not body_is_declarative:
            for start, end in body_source_spans or all_body_sources:
                absolute_start = loop["body_start"] + start
                events.append(
                    (
                        absolute_start,
                        sequence,
                        body[start:end],
                        {},
                        True,
                    )
                )
                sequence += 1
            continue

        expansion_count += len(values) * len(body_source_spans)
        if expansion_count > MAX_STATIC_EXPANSION:
            raise ValueError(
                f"Static source expansion exceeds MAX_STATIC_EXPANSION={MAX_STATIC_EXPANSION}"
            )
        for value_index, value in enumerate(values):
            scope = _loop_scope(loop["binder"], value)
            if scope is None:
                for start, end in body_source_spans:
                    events.append(
                        (
                            loop["body_start"] + start,
                            sequence,
                            body[start:end],
                            {},
                            True,
                        )
                    )
                    sequence += 1
                continue
            for start, end in body_source_spans:
                events.append(
                    (
                        loop["body_start"] + start,
                        sequence + value_index,
                        body[start:end],
                        scope,
                        False,
                    )
                )
            sequence += len(body_source_spans)

    for span in source_spans:
        if span in handled:
            continue
        start, end = span
        is_direct = _brace_depth_at(content, start) == 0
        events.append((start, sequence, content[start:end], {}, not is_direct))
        sequence += 1

    events.sort(key=lambda item: (item[0], item[1]))
    return [(block, scope, invalid) for _, _, block, scope, invalid in events]


_SOURCE_ASSIGNMENT_KEYS = {"name", "lang", "id", "versionId", "baseUrl"}


def _assignment_only_values(
    content: str,
    bindings: Dict[str, str],
    invalid_bindings: set[str],
    scope: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    stripped = _strip_comments(content).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        stripped = stripped[1:-1]
    statements = []
    for line in _split_top_level(stripped, ";"):
        statements.extend(part.strip() for part in line.splitlines() if part.strip())
    values: Dict[str, Any] = {}
    for statement in statements:
        match = re.fullmatch(
            r"(?:this\.)?([A-Za-z_]\w*)\s*=\s*(.+)", statement, re.DOTALL
        )
        if not match or match.group(1) not in _SOURCE_ASSIGNMENT_KEYS:
            return None
        key, expression = match.group(1), match.group(2)
        if key in values:
            return None
        value = _resolve_expression(
            expression, bindings, invalid_bindings, scope
        )
        if value is _UNRESOLVED_VALUE or isinstance(value, (list, _LiteralMap)):
            return None
        values[key] = value
    return values


def _literal_predicate(
    expression: str,
    bindings: Dict[str, str],
    invalid_bindings: set[str],
    scope: Dict[str, Any],
) -> Optional[bool]:
    match = re.fullmatch(
        rf"\s*([A-Za-z_]\w*)\s*(==|!=)\s*({_STRING_LITERAL}|-?\d+L?)\s*",
        expression,
    )
    if not match:
        return None
    binding_name, operator, literal_expression = match.groups()
    if binding_name not in scope and binding_name not in bindings:
        return None
    left = _resolve_expression(
        binding_name, bindings, invalid_bindings, scope
    )
    right = _resolve_expression(
        literal_expression, bindings, invalid_bindings, scope
    )
    if left is _UNRESOLVED_VALUE or right is _UNRESOLVED_VALUE:
        return None
    return (left == right) if operator == "==" else (left != right)


def _conditional_consequence(
    content: str, start: int
) -> Tuple[str, int]:
    cursor = start
    while cursor < len(content) and content[cursor].isspace():
        cursor += 1
    if cursor < len(content) and content[cursor] == "{":
        end = _find_matching_delimiter(content, cursor, "{", "}")
        if end is None:
            return content[cursor:], len(content)
        return content[cursor : end + 1], end + 1
    end = cursor
    while end < len(content) and content[end] not in "\r\n;":
        end += 1
    return content[cursor:end], end


def _parse_when_branches(
    content: str,
    bindings: Dict[str, str],
    invalid_bindings: set[str],
    scope: Dict[str, Any],
) -> Optional[List[Tuple[Any, Dict[str, Any]]]]:
    branch_pattern = re.compile(
        rf"(?m)^\s*(else|{_STRING_LITERAL}|-?\d+L?)\s*->"
    )
    matches = [
        match
        for match in branch_pattern.finditer(_strip_comments(content))
        if _brace_depth_at(content, match.start()) == 0
    ]
    if not matches or _strip_comments(content[: matches[0].start()]).strip():
        return None

    branches: List[Tuple[Any, Dict[str, Any]]] = []
    seen_labels: List[Any] = []
    for index, match in enumerate(matches):
        label_expression = match.group(1)
        consequence_start = match.end()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        consequence_text = content[consequence_start:next_start].strip()
        if consequence_text.endswith(","):
            consequence_text = consequence_text[:-1].rstrip()
        values = _assignment_only_values(
            consequence_text, bindings, invalid_bindings, scope
        )
        if values is None:
            return None
        if label_expression == "else":
            label: Any = _WHEN_ELSE
        else:
            label = _resolve_expression(
                label_expression, bindings, invalid_bindings, scope
            )
            if label is _UNRESOLVED_VALUE:
                return None
        if label in seen_labels:
            return None
        seen_labels.append(label)
        branches.append((label, values))
    return branches


def _conditional_assignments(
    source_block: str,
    bindings: Dict[str, str],
    invalid_bindings: set[str],
    scope: Dict[str, Any],
) -> Tuple[str, Dict[str, Any], bool]:
    """Evaluate direct literal if/when metadata assignments and blank them."""
    opening_index = _mask_non_code(source_block).find("{")
    if opening_index < 0:
        return source_block, {}, False
    closing_index = _find_matching_delimiter(
        source_block, opening_index, "{", "}"
    )
    if closing_index is None:
        return source_block, {}, False
    body_start = opening_index + 1
    body = source_block[body_start:closing_index]
    masked = _mask_non_code(body)
    spans: List[Tuple[int, int]] = []
    selected: Dict[str, Any] = {}
    safe = True

    conditional_tokens = [
        match
        for match in re.finditer(r"\b(if|when)\s*\(", masked)
        if _brace_depth_at(body, match.start()) == 0
    ]
    consumed_until = -1
    for token in conditional_tokens:
        if token.start() < consumed_until:
            continue
        opening_paren = masked.find("(", token.start())
        closing_paren = _find_matching_delimiter(
            body, opening_paren, "(", ")"
        )
        if closing_paren is None:
            safe = False
            continue
        subject = body[opening_paren + 1 : closing_paren]

        if token.group(1) == "if":
            predicate = _literal_predicate(
                subject, bindings, invalid_bindings, scope
            )
            consequence, consequence_end = _conditional_consequence(
                body, closing_paren + 1
            )
            then_values = _assignment_only_values(
                consequence, bindings, invalid_bindings, scope
            )
            else_values: Dict[str, Any] = {}
            cursor = consequence_end
            while cursor < len(body) and body[cursor].isspace():
                cursor += 1
            full_end = consequence_end
            if masked.startswith("else", cursor):
                alternative, alternative_end = _conditional_consequence(
                    body, cursor + 4
                )
                parsed_else = _assignment_only_values(
                    alternative, bindings, invalid_bindings, scope
                )
                if parsed_else is None:
                    safe = False
                else:
                    else_values = parsed_else
                full_end = alternative_end
            if predicate is None or then_values is None:
                safe = False
            else:
                chosen = then_values if predicate else else_values
                if any(key in selected for key in chosen):
                    safe = False
                selected.update(chosen)
            spans.append((body_start + token.start(), body_start + full_end))
            consumed_until = full_end
            continue

        cursor = closing_paren + 1
        while cursor < len(body) and body[cursor].isspace():
            cursor += 1
        if cursor >= len(body) or body[cursor] != "{":
            safe = False
            continue
        when_end = _find_matching_delimiter(body, cursor, "{", "}")
        if when_end is None:
            safe = False
            continue
        subject_match = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*", subject)
        subject_value = (
            _resolve_expression(
                subject_match.group(1), bindings, invalid_bindings, scope
            )
            if subject_match
            else _UNRESOLVED_VALUE
        )
        branches = _parse_when_branches(
            body[cursor + 1 : when_end], bindings, invalid_bindings, scope
        )
        if subject_value is _UNRESOLVED_VALUE or branches is None:
            safe = False
        else:
            chosen: Dict[str, Any] = {}
            fallback: Dict[str, Any] = {}
            for label, values in branches:
                if label is _WHEN_ELSE:
                    fallback = values
                elif label == subject_value:
                    chosen = values
            if not chosen:
                chosen = fallback
            if any(key in selected for key in chosen):
                safe = False
            selected.update(chosen)
        spans.append((body_start + token.start(), body_start + when_end + 1))
        consumed_until = when_end + 1

    return _blank_spans(source_block, spans), selected, safe


def _compute_source_id(name: str, lang: str, version_id: int) -> str:
    key = f"{name.lower()}/{lang}/{version_id}"
    digest_prefix = hashlib.md5(key.encode("utf-8")).digest()[:8]
    value = int.from_bytes(digest_prefix, byteorder="big") & ((1 << 63) - 1)
    return str(value)


def _parse_base_url(
    source_block: str,
    bindings: Optional[Dict[str, str]] = None,
    invalid_bindings: Optional[set[str]] = None,
    scope: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "baseUrlMode": "unresolved",
        "defaultBaseUrl": None,
        "baseUrlResolved": False,
        "mirrors": [],
    }
    unresolved: List[str] = []

    bindings = bindings or {}
    invalid_bindings = invalid_bindings or set()
    scope = scope or {}
    direct_source = _direct_block_content(source_block)
    assignment_present, base_url_expression = _assignment_expression(
        direct_source, "baseUrl"
    )
    resolved_url = (
        _resolve_expression(
            base_url_expression, bindings, invalid_bindings, scope
        )
        if base_url_expression is not None
        else _UNRESOLVED_VALUE
    )
    static_url = resolved_url if isinstance(resolved_url, str) else None
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
            result["baseUrlExpression"] = base_url_expression
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
                pair = _split_top_level(argument, " to ")
                if len(pair) == 2:
                    labeled_flags.append(True)
                    label = _resolve_expression(
                        pair[0], bindings, invalid_bindings, scope
                    )
                    url = _resolve_expression(
                        pair[1], bindings, invalid_bindings, scope
                    )
                    if isinstance(label, str) and isinstance(url, str):
                        mirrors.append({"label": label, "url": url})
                    else:
                        mirrors.append({"unresolvedExpression": argument})
                        unresolved.append("baseUrl.mirrors")
                    continue

                labeled_flags.append(False)
                url = _resolve_expression(
                    argument, bindings, invalid_bindings, scope
                )
                if isinstance(url, str):
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
            default_url = _resolve_expression(
                arguments[0], bindings, invalid_bindings, scope
            )
            if isinstance(default_url, str):
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


def _parse_source(
    source_block: str,
    extension_name: Optional[str],
    *,
    bindings: Optional[Dict[str, str]] = None,
    invalid_bindings: Optional[set[str]] = None,
    scope: Optional[Dict[str, Any]] = None,
    force_unresolved: bool = False,
) -> Dict[str, Any]:
    source: Dict[str, Any] = {}
    unresolved: List[str] = []
    bindings = bindings or {}
    invalid_bindings = invalid_bindings or set()
    scope = scope or {}
    conditioned_source, conditional_values, conditionals_safe = (
        _conditional_assignments(
            source_block, bindings, invalid_bindings, scope
        )
    )
    if not conditionals_safe:
        force_unresolved = True
    direct_source = _direct_block_content(conditioned_source)

    def resolved_assignment(key: str) -> Tuple[bool, Any]:
        present, expression = _assignment_expression(direct_source, key)
        if key in conditional_values:
            if present:
                return True, _UNRESOLVED_VALUE
            return True, conditional_values[key]
        if not present or expression is None:
            return present, _UNRESOLVED_VALUE
        return True, _resolve_expression(
            expression, bindings, invalid_bindings, scope
        )

    name_present, name_value = resolved_assignment("name")
    declared_name = name_value if isinstance(name_value, str) else None
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

    lang_present, lang_value = resolved_assignment("lang")
    lang = lang_value if isinstance(lang_value, str) else None
    source["lang"] = lang
    if not lang_present or lang is None:
        unresolved.append("lang")

    version_present, raw_version_value = resolved_assignment("versionId")
    version_value = raw_version_value if isinstance(raw_version_value, int) else None
    if version_present:
        source["versionId"] = version_value
        if version_value is None:
            unresolved.append("versionId")
    effective_version_id = version_value if version_present else 1
    source["effectiveVersionId"] = effective_version_id

    id_present, id_value = resolved_assignment("id")
    id_literal = str(id_value) if isinstance(id_value, int) else None
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

    base_url = _parse_base_url(
        conditioned_source, bindings, invalid_bindings, scope
    )
    if "baseUrl" in conditional_values:
        conditional_base_url = conditional_values["baseUrl"]
        if base_url.get("baseUrlMode") != "unresolved" or not isinstance(
            conditional_base_url, str
        ):
            base_url = {
                "baseUrlMode": "unresolved",
                "defaultBaseUrl": None,
                "baseUrlResolved": False,
                "mirrors": [],
                "unresolved": ["baseUrl"],
            }
        else:
            base_url = {
                "baseUrlMode": "static",
                "defaultBaseUrl": conditional_base_url,
                "baseUrl": conditional_base_url,
                "baseUrlResolved": True,
                "mirrors": [],
            }
    source.update(base_url)
    unresolved.extend(base_url.get("unresolved", []))
    if force_unresolved:
        source["sourceId"] = None
        source["sourceIdKind"] = "unresolved"
        unresolved.extend(["sourceId", "staticExpansion"])
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
        _block_body(content[keiyoushi_blocks[0][0] : keiyoushi_blocks[0][1]])
        if keiyoushi_blocks
        else content
    )
    local_bindings, invalid_bindings = _collect_local_bindings(source_region)
    expanded_sources = _expanded_source_blocks(
        source_region, local_bindings, invalid_bindings
    )

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

    for source_block, scope, force_unresolved in expanded_sources:
        metadata["sources"].append(
            _parse_source(
                source_block,
                name,
                bindings=local_bindings,
                invalid_bindings=invalid_bindings,
                scope=scope,
                force_unresolved=force_unresolved,
            )
        )

    if unresolved:
        metadata["unresolved"] = list(dict.fromkeys(unresolved))
    return metadata
