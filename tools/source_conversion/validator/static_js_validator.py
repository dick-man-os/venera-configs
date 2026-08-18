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

class JSScanner:
    def __init__(self, code: str):
        self.code = code
        self.pos = 0
        self.length = len(code)
        self.executable_code = []
        self.throw_messages = []
        self.brace_balance = 0
        self.errors = []
        # template state tracking for ${}
        self.template_depths = []

    def scan(self):
        while self.pos < self.length:
            char = self.code[self.pos]

            if char == "'":
                self.executable_code.append(" ")
                self.pos += 1
                self.scan_string("'")
            elif char == '"':
                self.executable_code.append(" ")
                self.pos += 1
                self.scan_string('"')
            elif char == '`':
                self.executable_code.append(" ")
                self.pos += 1
                self.scan_template()
            elif char == '/' and self.pos + 1 < self.length and self.code[self.pos+1] == '/':
                self.executable_code.append(" ")
                self.scan_line_comment()
            elif char == '/' and self.pos + 1 < self.length and self.code[self.pos+1] == '*':
                self.executable_code.append(" ")
                self.scan_block_comment()
            elif char == '/':
                # check if division or regex
                if self.is_regex_context():
                    self.executable_code.append(" ")
                    self.scan_regex()
                else:
                    self.executable_code.append(char)
                    self.pos += 1
            elif char == '{':
                self.brace_balance += 1
                self.executable_code.append(char)
                self.pos += 1
            elif char == '}':
                self.brace_balance -= 1
                self.executable_code.append(char)
                self.pos += 1
                if self.template_depths and self.brace_balance == self.template_depths[-1]:
                    # Return to template context
                    self.template_depths.pop()
                    self.executable_code.append(" ")
                    self.scan_template()
            elif self.code[self.pos:self.pos+5] == 'throw':
                # look ahead for 'throw new Error("MANUAL PATCH REQUIRED...")'
                self.executable_code.append('throw')
                self.pos += 5
                self.scan_throw()
            else:
                self.executable_code.append(char)
                self.pos += 1

        if self.brace_balance != 0:
            self.errors.append(f"Structural validation failed: Brace balance is {self.brace_balance} (extra/missing '}}')")

        return "".join(self.executable_code)

    def scan_string(self, quote):
        while self.pos < self.length:
            if self.code[self.pos] == '\\':
                self.pos += 2
                continue
            if self.code[self.pos] == quote:
                self.pos += 1
                break
            self.pos += 1

    def scan_template(self):
        while self.pos < self.length:
            if self.code[self.pos] == '\\':
                self.pos += 2
                continue
            if self.code[self.pos:self.pos+2] == '${':
                self.pos += 2
                self.template_depths.append(self.brace_balance)
                self.brace_balance += 1
                self.executable_code.append('${')
                return # back to normal scan
            if self.code[self.pos] == '`':
                self.pos += 1
                break
            self.pos += 1

    def scan_line_comment(self):
        while self.pos < self.length and self.code[self.pos] != '\n':
            self.pos += 1

    def scan_block_comment(self):
        self.pos += 2
        while self.pos < self.length:
            if self.code[self.pos:self.pos+2] == '*/':
                self.pos += 2
                break
            self.pos += 1

    def scan_regex(self):
        self.pos += 1 # skip '/'
        in_class = False
        while self.pos < self.length:
            c = self.code[self.pos]
            if c == '\\':
                self.pos += 2
                continue
            if c == '[':
                in_class = True
            elif c == ']':
                in_class = False
            elif c == '/' and not in_class:
                self.pos += 1
                # skip flags
                while self.pos < self.length and self.code[self.pos].isalpha():
                    self.pos += 1
                break
            self.pos += 1

    def scan_throw(self):
        # We just grab the next ~150 chars to see if it's our throw
        text = self.code[self.pos:self.pos+150]
        if "MANUAL PATCH REQUIRED" in text or "MANUAL_PATCH_REQUIRED" in text:
            self.throw_messages.append(text)

    def is_regex_context(self):
        # Very simple heuristic: if previous non-whitespace char is one of:
        # ( = [ , : ; ! & | ? {
        # then it's a regex. Otherwise division.
        # Also `return` keyword
        idx = len(self.executable_code) - 1
        while idx >= 0 and self.executable_code[idx].isspace():
            idx -= 1
        if idx < 0: return True
        c = self.executable_code[idx]
        if c in '(={[<,:;!&|?+-*':
            return True
        # Check for keywords ending
        if c.isalpha():
            # Grab the word
            word = ""
            while idx >= 0 and self.executable_code[idx].isalpha():
                word = self.executable_code[idx] + word
                idx -= 1
            if word in ('return', 'typeof', 'yield', 'await', 'case', 'throw'):
                return True
        return False

def validate_js_file(file_path: str, phase: str = "final") -> bool:
    if not os.path.exists(file_path):
        print(f"Error: JS file not found: {file_path}", file=sys.stderr)
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    scanner = JSScanner(content)
    exec_code = scanner.scan()

    errors: List[str] = list(scanner.errors)
    warnings: List[str] = []

    if phase == "final":
        for msg in scanner.throw_messages:
            if "MANUAL PATCH REQUIRED" in msg or "MANUAL_PATCH_REQUIRED" in msg:
                errors.append(f"Unresolved MANUAL_PATCH_REQUIRED hook found: {msg.strip()[:50]}")

    lines = exec_code.split('\n')
    for i, line in enumerate(lines):
        line_num = i + 1

        # Check UNSUPPORTED APIs
        for pattern, reason in UNSUPPORTED_PATTERNS:
            if re.search(pattern, line):
                errors.append(f"Line {line_num}: UNSUPPORTED API usage '{pattern}'. Reason: {reason}")

        # Check VERIFY APIs
        for pattern, reason in VERIFY_PATTERNS:
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
