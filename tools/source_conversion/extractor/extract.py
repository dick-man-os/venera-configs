#!/usr/bin/env python3
"""
extract.py - Generic Extraction CLI for Keiyoushi Sources (Milestone 7B-1)
"""

import argparse
import datetime
import json
import os
import sys
from typing import Dict, Any

from common import gradle_parser
from common import kotlin_parser
from common import selector_analyzer

def resolve_source_dir(extensions_root: str, source_path: str) -> str:
    """Resolve the source directory deterministically."""
    path = os.path.join(extensions_root, "src", source_path)
    if not os.path.isdir(path):
        raise FileNotFoundError(f"Source directory not found: {path}")
    return path

def extract_generic(extensions_root: str, source_path: str, timestamp: str = None, language_override: str = None) -> Dict[str, Any]:
    """Perform generic extraction on a source."""
    source_dir = resolve_source_dir(extensions_root, source_path)
    build_gradle_path = os.path.join(source_dir, "build.gradle.kts")

    if not os.path.exists(build_gradle_path):
        raise FileNotFoundError(f"build.gradle.kts not found in {source_dir}")

    gradle_meta = gradle_parser.parse_gradle_metadata(build_gradle_path)

    # Try to find the main Kotlin file. This is heuristic for the generic path
    # since we don't know the exact package. Usually it's in src/eu/kanade/tachiyomi/extension/...
    kt_files = []
    for root, _, files in os.walk(os.path.join(source_dir, "src")):
        for file in files:
            if file.endswith(".kt") and file not in ["Dto.kt", "Filters.kt"]:
                kt_files.append(os.path.join(root, file))

    if not kt_files:
        raise FileNotFoundError(f"No Kotlin source files found in {source_dir}")

    # Heuristic: the file with the same name as the source
    source_name = os.path.basename(source_dir).lower()
    main_kt = kt_files[0]
    for kt_file in kt_files:
        if os.path.basename(kt_file).lower() == f"{source_name}.kt":
            main_kt = kt_file
            break

    if not timestamp:
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    import generic_html_extractor

    lang = source_path.split("/")[0] if "/" in source_path else "en"
    ir_data = generic_html_extractor.extract(main_kt, gradle_meta, timestamp, lang, language_override)

    try:
        import subprocess
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=extensions_root, text=True
        ).strip()
        ir_data["provenance"]["upstreamCommit"] = commit
    except Exception:
        pass

    return ir_data

def main() -> int:
    parser = argparse.ArgumentParser(description="Generic Extraction CLI for Keiyoushi Sources.")
    parser.add_argument(
        "--source",
        required=True,
        help="Source path relative to src/ (e.g., 'all/webtoons', 'zh/happymh')."
    )
    parser.add_argument(
        "--extensions-root",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "extensions-source")
        ),
        help="Path to extensions-source repository root."
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for the generated IR file."
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="Optional ISO timestamp override for deterministic testing."
    )
    parser.add_argument(
        "--language-override",
        default=None,
        help="Explicit semantic language override (e.g. zh-Hant)."
    )

    args = parser.parse_args()

    extensions_root = os.path.abspath(args.extensions_root)
    output_path = os.path.abspath(args.output)
    source_path = args.source

    print(f"[*] Extracting source '{source_path}' from: {extensions_root}")
    print(f"[*] Target output: {output_path}")

    try:
        if source_path == "all/webtoons":
            print("[*] Dispatching to Webtoons adapter...")
            from source_adapters import webtoons
            ir_data = webtoons.extract(extensions_root, timestamp=args.timestamp)
        elif source_path == "zh/comicabc":
            print("[*] Dispatching to Comicabc adapter...")
            from source_adapters import comicabc
            ir_data = comicabc.extract(extensions_root, timestamp=args.timestamp)
        else:
            print("[*] Using generic extraction pathway...")
            ir_data = extract_generic(extensions_root, source_path, timestamp=args.timestamp, language_override=args.language_override)

    except Exception as e:
        print(f"[!] Extraction failed: {e}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ir_data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[+] Successfully extracted IR to {output_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
