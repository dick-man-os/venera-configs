#!/usr/bin/env python3
"""
static_js_validator.py - Static AST/Regex Analyzer for Venera Generated JS

Enforces the Venera JS safety matrix:
- Detects unresolved MANUAL_PATCH_REQUIRED markers
- Prevents usage of UNSUPPORTED browser/Node.js APIs
- Flags VERIFY APIs (e.g. fetch)
"""

import argparse
import os
import re
import sys
from typing import List

UNSUPPORTED_PATTERNS = [
    (r"\bwindow\b", "window global is not available in QuickJS"),
    (r"\bdocument\b(?!\.dispose)", "browser document global is not available (use HtmlDocument)"),
    (r"\bDOMParser\b", "DOMParser is not available (use HtmlDocument)"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest is not available (use Network)"),
    (r"\bnew URL\(", "URL constructor is not natively bound"),
    (r"\bURLSearchParams\b", "URLSearchParams is not natively bound"),
    (r"\bTextEncoder\b", "TextEncoder is not natively bound"),
    (r"\bTextDecoder\b", "TextDecoder is not natively bound"),
    (r"\batob\(", "atob is not natively bound"),
    (r"\bbtoa\(", "btoa is not natively bound"),
    (r"\bcrypto\b", "crypto is not natively bound"),
    (r"\bBuffer\b", "Node.js Buffer is not available"),
    (r"\brequire\(", "Node.js require is not available"),
]

VERIFY_PATTERNS = [
    (r"\bfetch\(", "fetch is available via polyfill, but requires manual verification for correctness"),
]

def validate_js_file(file_path: str, phase: str = "final") -> bool:
    if not os.path.exists(file_path):
        print(f"Error: JS file not found: {file_path}", file=sys.stderr)
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    errors: List[str] = []
    warnings: List[str] = []

    lines = content.split('\n')
    for i, line in enumerate(lines):
        line_num = i + 1

        # Check FAIL CLOSED markers
        if ("MANUAL_PATCH_REQUIRED" in line or "MANUAL PATCH REQUIRED" in line):
            if phase == "final":
                errors.append(f"Line {line_num}: Unresolved MANUAL_PATCH_REQUIRED marker found.")

        # Check UNSUPPORTED APIs
        for pattern, reason in UNSUPPORTED_PATTERNS:
            if "document" in pattern and ".dispose()" in line:
                continue
            if line.strip().startswith("//") or line.strip().startswith("*"):
                continue

            if re.search(pattern, line):
                errors.append(f"Line {line_num}: UNSUPPORTED API usage '{pattern}'. Reason: {reason}")

        # Check VERIFY APIs
        for pattern, reason in VERIFY_PATTERNS:
            if line.strip().startswith("//") or line.strip().startswith("*"):
                continue
            if re.search(pattern, line):
                warnings.append(f"Line {line_num}: VERIFY API usage '{pattern}'. Reason: {reason}")

    if warnings:
        print(f"[WARN] {file_path} raised {len(warnings)} warnings:", file=sys.stderr)
        for w in warnings:
            print(f"  - {w}", file=sys.stderr)

    if errors:
        print(f"[FAIL] {file_path} failed static JS validation ({len(errors)} errors):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return False

    print(f"[PASS] {file_path} is statically valid.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Static validator for generated Venera JS.")
    parser.add_argument("--phase", choices=["base", "final"], default="final", help="Validation phase (base or final)")
    parser.add_argument("files", nargs="+", help="Path(s) to JS file(s) to validate.")
    args = parser.parse_args()

    all_passed = True
    for file_path in args.files:
        if not validate_js_file(file_path, phase=args.phase):
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
