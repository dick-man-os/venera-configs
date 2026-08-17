#!/usr/bin/env python3
"""
js_patcher.py - Deterministic Source Patcher & Composer

Composes a base generated JavaScript source with a manual patch file to
produce a complete, production-ready Venera ComicSource.
"""

import argparse
import os
import sys

HOOK_HEADER = "    // =========================================================================\n    // Patch Hooks / Boundaries"


def patch_js(base_content: str, patch_content: str) -> str:
    """Replaces the placeholder patch hooks in base_content with patch_content."""
    if HOOK_HEADER not in base_content:
        raise ValueError(f"Base source does not contain required hook marker: '{HOOK_HEADER.strip()}'")

    # Split base content at hook header
    prefix, remainder = base_content.split(HOOK_HEADER, 1)

    # Find the closing brace of the class
    last_brace_idx = remainder.rfind("}")
    if last_brace_idx == -1:
        raise ValueError("Could not find closing class brace '}' in base source.")

    suffix = remainder[last_brace_idx:]

    # Clean patch content
    patch_clean = patch_content.rstrip() + "\n"

    composed = prefix + patch_clean + suffix
    return composed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compose a base generated Venera JS source with a manual patch file."
    )
    parser.add_argument(
        "--base",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "sources_generated", "webtoons.base.js")
        ),
        help="Path to generated base JavaScript source.",
    )
    parser.add_argument(
        "--patch",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "sources_patches", "webtoons.patch.js")
        ),
        help="Path to manual patch JavaScript file.",
    )
    parser.add_argument(
        "--output",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "webtoons.js")
        ),
        help="Path to output composed JavaScript source.",
    )

    args = parser.parse_args()

    base_path = os.path.abspath(args.base)
    patch_path = os.path.abspath(args.patch)
    output_path = os.path.abspath(args.output)

    print(f"[*] Reading base source from: {base_path}")
    print(f"[*] Reading patch source from: {patch_path}")
    print(f"[*] Target composed output: {output_path}")

    if not os.path.exists(base_path):
        print(f"[!] Error: Base source file not found: {base_path}", file=sys.stderr)
        return 1

    if not os.path.exists(patch_path):
        print(f"[!] Error: Patch file not found: {patch_path}", file=sys.stderr)
        return 1

    try:
        with open(base_path, "r", encoding="utf-8") as f:
            base_content = f.read()
        with open(patch_path, "r", encoding="utf-8") as f:
            patch_content = f.read()

        composed_js = patch_js(base_content, patch_content)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(composed_js)

        print(f"[+] Successfully composed patched source: {output_path}")
        return 0
    except Exception as e:
        print(f"[!] Composition failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
