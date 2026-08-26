#!/usr/bin/env python3
"""Generate a deterministic static inventory from a pinned extensions checkout."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.source_conversion.extractor.common.gradle_parser import (  # noqa: E402
    parse_gradle_metadata,
)
from tools.source_conversion.validator.validate_inventory import (  # noqa: E402
    validate_inventory_data,
)


MODULE_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")
HTTP_SCHEMES = {"http", "https"}
CONTENT_WARNINGS = {"SAFE", "MIXED", "NSFW"}
COMPATIBILITY = {
    "metadataResolution": "static",
    "extraction": "unclassified",
}


class InventoryGenerationError(RuntimeError):
    """Raised when deterministic inventory generation must fail closed."""


def discover_modules(extensions_root: Path) -> list[tuple[str, Path]]:
    """Return module locators and Gradle files in stable repository order."""
    source_root = extensions_root / "src"
    if not source_root.is_dir():
        raise InventoryGenerationError(
            f"Extensions source root has no src directory: {extensions_root}"
        )

    discovered: list[tuple[str, Path]] = []
    module_paths: dict[str, Path] = {}
    build_files = sorted(
        source_root.rglob("build.gradle.kts"),
        key=lambda path: path.relative_to(source_root).as_posix(),
    )
    for build_file in build_files:
        relative_parent = build_file.relative_to(source_root).parent
        raw_module = ".".join(relative_parent.parts)
        module = raw_module.lower()
        if not MODULE_RE.fullmatch(module):
            raise InventoryGenerationError(
                "Unsupported module layout for "
                f"{build_file.relative_to(extensions_root).as_posix()}"
            )
        previous_path = module_paths.get(module)
        if previous_path is not None:
            raise InventoryGenerationError(
                "Module locator collision after lowercase normalization: "
                f"{previous_path.relative_to(extensions_root).as_posix()} and "
                f"{build_file.relative_to(extensions_root).as_posix()}"
            )
        module_paths[module] = build_file
        discovered.append((module, build_file))
    return discovered


def read_git_head(extensions_root: Path) -> str:
    """Read the checkout HEAD without changing repository or Git state."""
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={extensions_root.resolve()}",
                "rev-parse",
                "--verify",
                "HEAD",
            ],
            cwd=extensions_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise InventoryGenerationError(f"Unable to execute Git: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "git rev-parse failed"
        raise InventoryGenerationError(f"Unable to resolve upstream HEAD: {detail}")
    commit = result.stdout.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{7,64}", commit):
        raise InventoryGenerationError(f"Git returned an invalid HEAD: {commit!r}")
    return commit


def _is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in HTTP_SCHEMES and bool(parsed.netloc)


def _candidate_from_source(
    *, project: str, module: str, metadata: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any] | None:
    source_id = source.get("sourceId")
    name = source.get("name")
    lang = source.get("lang")
    if not (
        isinstance(source_id, str)
        and source_id.isdecimal()
        and isinstance(name, str)
        and bool(name)
        and isinstance(lang, str)
        and bool(lang)
    ):
        return None

    candidate: dict[str, Any] = {
        "project": project,
        "sourceId": source_id,
        "module": module,
        "name": name,
        "upstreamLang": lang,
    }
    base_url = source.get("baseUrl")
    if source.get("baseUrlResolved") is True and _is_http_url(base_url):
        candidate["baseUrl"] = base_url
    content_warning = metadata.get("contentWarning")
    if content_warning in CONTENT_WARNINGS:
        candidate["contentWarning"] = content_warning
    theme = metadata.get("theme")
    if isinstance(theme, str) and theme:
        candidate["theme"] = theme
    version = metadata.get("version")
    if metadata.get("versionResolution") == "resolved" and isinstance(version, str):
        candidate["version"] = version
    extension_lib = metadata.get("libVersion")
    if isinstance(extension_lib, str) and re.fullmatch(r"[0-9]+\.[0-9]+", extension_lib):
        candidate["extensionLib"] = extension_lib
    candidate["compatibility"] = dict(COMPATIBILITY)
    return candidate


def generate_inventory(
    extensions_root: Path | str, project: str, commit: str
) -> dict[str, Any]:
    """Generate and validate one static inventory snapshot."""
    root = Path(extensions_root).resolve()
    candidates: list[dict[str, Any]] = []
    unresolved_modules: list[dict[str, Any]] = []

    for module, build_file in discover_modules(root):
        try:
            metadata = parse_gradle_metadata(str(build_file), extensions_root=str(root))
        except (OSError, UnicodeError, ValueError):
            unresolved_modules.append(
                {
                    "project": project,
                    "module": module,
                    "reason": {"code": "static-parse-error"},
                }
            )
            continue

        sources = metadata.get("sources")
        if not isinstance(sources, list) or not sources:
            unresolved_modules.append(
                {
                    "project": project,
                    "module": module,
                    "reason": {"code": "no-source-blocks"},
                }
            )
            continue

        module_has_unresolved_source = False
        for source in sources:
            if not isinstance(source, Mapping):
                module_has_unresolved_source = True
                continue
            candidate = _candidate_from_source(
                project=project,
                module=module,
                metadata=metadata,
                source=source,
            )
            if candidate is None:
                module_has_unresolved_source = True
            else:
                candidates.append(candidate)
        if module_has_unresolved_source:
            unresolved_modules.append(
                {
                    "project": project,
                    "module": module,
                    "reason": {"code": "unresolved-required-metadata"},
                }
            )

    candidates.sort(
        key=lambda item: (
            item["project"],
            item["sourceId"],
            item["module"],
            item["name"],
            item["upstreamLang"],
        )
    )
    unresolved_modules.sort(
        key=lambda item: (
            item["project"],
            item["module"],
            item["reason"]["code"],
        )
    )
    inventory = {
        "schemaVersion": "1.0",
        "upstreams": [{"project": project, "commit": commit}],
        "candidates": candidates,
        "unresolvedModules": unresolved_modules,
    }
    validation = validate_inventory_data(inventory)
    if validation.errors:
        details = "; ".join(
            f"{item.code} {item.subject}: {item.message}"
            for item in validation.errors
        )
        raise InventoryGenerationError(f"Generated inventory is invalid: {details}")
    return inventory


def generate_from_checkout(
    extensions_root: Path | str,
    project: str,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    """Read checkout HEAD, enforce an optional exact pin, and generate inventory."""
    root = Path(extensions_root).resolve()
    actual_commit = read_git_head(root)
    if expected_commit is not None and actual_commit != expected_commit.lower():
        raise InventoryGenerationError(
            "Pinned commit mismatch: "
            f"expected {expected_commit.lower()}, found {actual_commit}"
        )
    return generate_inventory(root, project, actual_commit)


def serialize_inventory(inventory: Mapping[str, Any]) -> bytes:
    """Return canonical UTF-8 JSON: two-space indent and one LF at EOF."""
    return (json.dumps(inventory, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_output(payload: bytes, output: Path | None, extensions_root: Path) -> None:
    if output is None:
        sys.stdout.buffer.write(payload)
        return
    resolved_output = output.resolve()
    resolved_upstream = extensions_root.resolve()
    if resolved_output == resolved_upstream or resolved_upstream in resolved_output.parents:
        raise InventoryGenerationError("Output path must be outside extensions-source")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_bytes(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic static upstream inventory without executing Gradle."
        )
    )
    parser.add_argument(
        "--extensions-root",
        required=True,
        type=Path,
        help="Pinned extensions-source checkout root.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Inventory project identifier, for example keiyoushi/extensions-source.",
    )
    parser.add_argument(
        "--expected-commit",
        help="Optional exact HEAD guard; generation fails if it does not match.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Explicit output file. Omit to write canonical JSON to stdout.",
    )
    args = parser.parse_args(argv)

    try:
        inventory = generate_from_checkout(
            args.extensions_root,
            args.project,
            expected_commit=args.expected_commit,
        )
        _write_output(
            serialize_inventory(inventory), args.output, args.extensions_root
        )
    except InventoryGenerationError as exc:
        print(f"[ERROR] INVENTORY_GENERATION_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
