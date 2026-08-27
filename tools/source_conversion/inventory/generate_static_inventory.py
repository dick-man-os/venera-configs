#!/usr/bin/env python3
"""Generate a deterministic static inventory from a pinned extensions checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.dont_write_bytecode = True

from tools.source_conversion.extractor.common.gradle_parser import (  # noqa: E402
    parse_gradle_metadata,
)
from tools.source_conversion.validator.validate_inventory import (  # noqa: E402
    validate_inventory_data,
)
from tools.source_conversion.validator.validate_registry import (  # noqa: E402
    validate_registry_data,
    validate_repository,
)


MODULE_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")
HTTP_SCHEMES = {"http", "https"}
CONTENT_WARNINGS = {"SAFE", "MIXED", "NSFW"}
COMPATIBILITY = {
    "metadataResolution": "static",
    "extraction": "unclassified",
}
CANONICAL_PROJECT = "keiyoushi/extensions-source"
CANONICAL_COMMIT = "5e06c412c0264b18120fd963fdd6efb529f3fa29"
CANONICAL_INVENTORY_PATH = (
    REPO_ROOT / "tools" / "source_conversion" / "inventory" / "upstream_inventory.json"
)
REGISTRY_PATH = REPO_ROOT / "sources_registry.json"
SUMMARY_LIST_LIMIT = 20


class InventoryGenerationError(RuntimeError):
    """Raised when deterministic inventory generation must fail closed."""


def _run_git(extensions_root: Path, *arguments: str) -> str:
    """Run one read-only Git query with a process-local ownership override."""
    root = extensions_root.resolve()
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={root}",
                *arguments,
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise InventoryGenerationError(f"Unable to execute Git: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"git {' '.join(arguments)} failed"
        raise InventoryGenerationError(detail)
    return result.stdout.strip()


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
        commit = _run_git(extensions_root, "rev-parse", "--verify", "HEAD").lower()
    except InventoryGenerationError as exc:
        raise InventoryGenerationError(f"Unable to resolve upstream HEAD: {exc}") from exc
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


def _normalized_github_project(remote_url: str) -> str | None:
    """Return owner/repository for ordinary GitHub HTTPS and SSH fetch URLs."""
    value = remote_url.strip().rstrip("/")
    scp_match = re.fullmatch(
        r"(?:[^@/\s]+@)?github\.com:(?P<path>[^\s]+)", value, re.IGNORECASE
    )
    if scp_match is not None:
        path = scp_match.group("path")
    else:
        parsed = urlparse(value)
        if parsed.scheme.lower() not in {"https", "ssh"}:
            return None
        if (parsed.hostname or "").lower() != "github.com":
            return None
        path = parsed.path.lstrip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    parts = path.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return "/".join(parts).lower()


def _validate_canonical_request(project: str, expected_commit: str | None) -> None:
    if project != CANONICAL_PROJECT:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: canonical project must be "
            f"{CANONICAL_PROJECT}, found {project!r}"
        )
    if expected_commit is None:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: canonical modes require --expected-commit"
        )
    if re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: canonical requested pin must be a full "
            f"lowercase 40-character Git commit, found {expected_commit!r}"
        )


def validate_canonical_checkout(
    extensions_root: Path | str, expected_commit: str
) -> tuple[Path, str]:
    """Prove that a supplied path is the intended pinned upstream Git root."""
    root = Path(extensions_root).resolve()
    if not root.is_dir():
        raise InventoryGenerationError(
            f"PROVENANCE_FAILED: upstream root is not a directory: {root}"
        )
    try:
        top_level = Path(_run_git(root, "rev-parse", "--show-toplevel")).resolve()
    except InventoryGenerationError as exc:
        raise InventoryGenerationError(
            f"PROVENANCE_FAILED: unable to resolve Git top-level: {exc}"
        ) from exc
    if os.path.normcase(str(top_level)) != os.path.normcase(str(root)):
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: supplied upstream path is not the Git worktree root; "
            f"supplied {root}, actual {top_level}"
        )

    actual_commit = read_git_head(root)
    if actual_commit != expected_commit:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: upstream HEAD mismatch: "
            f"expected {expected_commit}, found {actual_commit}"
        )

    try:
        remote_names = tuple(
            name for name in _run_git(root, "remote").splitlines() if name
        )
    except InventoryGenerationError as exc:
        raise InventoryGenerationError(
            f"PROVENANCE_FAILED: unable to inspect fetch remotes: {exc}"
        ) from exc
    matching_urls: list[str] = []
    inspected_urls: list[str] = []
    remote_errors: list[str] = []
    for remote_name in remote_names:
        try:
            urls = _run_git(root, "remote", "get-url", "--all", remote_name)
        except InventoryGenerationError as exc:
            remote_errors.append(f"{remote_name}: {exc}")
            continue
        for remote_url in urls.splitlines():
            if not remote_url:
                continue
            inspected_urls.append(remote_url)
            if _normalized_github_project(remote_url) == CANONICAL_PROJECT:
                matching_urls.append(remote_url)
    if not matching_urls:
        rendered = ", ".join(sorted(inspected_urls)) or "<none>"
        errors = "; ".join(sorted(remote_errors)) or "<none>"
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: no configured fetch remote identifies "
            f"{CANONICAL_PROJECT}; inspected {rendered}; remote errors {errors}"
        )
    return root, actual_commit


def _load_json_bytes(path: Path) -> tuple[bytes, Any]:
    try:
        payload = path.read_bytes()
        data = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryGenerationError(
            f"INVALID_INVENTORY_STATE: unable to read {path}: {exc}"
        ) from exc
    return payload, data


def _format_diagnostics(result: Any) -> str:
    return "; ".join(
        f"{item.code} {item.subject}: {item.message}" for item in result.errors
    )


def _load_registry() -> Any:
    try:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryGenerationError(
            f"REGISTRY_INTEGRATION_REGRESSION: unable to read registry: {exc}"
        ) from exc
    structure = validate_registry_data(registry)
    if structure.errors:
        raise InventoryGenerationError(
            "REGISTRY_INTEGRATION_REGRESSION: invalid registry state: "
            + _format_diagnostics(structure)
        )
    consistency = validate_repository(REPO_ROOT)
    if consistency.errors:
        raise InventoryGenerationError(
            "REGISTRY_INTEGRATION_REGRESSION: repository registry consistency failed: "
            + _format_diagnostics(consistency)
        )
    return registry


def _snapshot_provenance(
    inventory: Any,
    *,
    expected_project: str,
    expected_commit: str | None,
) -> tuple[str, str]:
    if not isinstance(inventory, Mapping):
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: snapshot root is not an object"
        )
    upstreams = inventory.get("upstreams")
    if not isinstance(upstreams, list) or len(upstreams) != 1:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: snapshot must declare exactly one upstream"
        )
    snapshot = upstreams[0]
    if not isinstance(snapshot, Mapping) or set(snapshot) != {"project", "commit"}:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: snapshot project/pin provenance is incomplete"
        )
    project = snapshot.get("project")
    commit = snapshot.get("commit")
    if project != expected_project:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: snapshot project mismatch: "
            f"expected {expected_project}, found {project!r}"
        )
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise InventoryGenerationError(
            f"PROVENANCE_FAILED: snapshot pin is not a full commit: {commit!r}"
        )
    if expected_commit is not None and commit != expected_commit:
        raise InventoryGenerationError(
            "PROVENANCE_FAILED: snapshot pin mismatch: "
            f"expected {expected_commit}, found {commit}"
        )
    return project, commit


def _registry_join_stats(
    inventory: Mapping[str, Any], registry: Any, *, require_complete: bool
) -> dict[str, Any]:
    result = validate_inventory_data(inventory, registry)
    if result.errors:
        prefix = (
            "REGISTRY_INTEGRATION_REGRESSION"
            if any(item.code.startswith("REGISTRY_") for item in result.errors)
            else "INVALID_INVENTORY_STATE"
        )
        raise InventoryGenerationError(f"{prefix}: {_format_diagnostics(result)}")

    joins = result.registry_joins
    ambiguous_joins = tuple(
        f"{item.project}:{item.source_id}"
        for item in joins
        if len(item.artifact_ids) > 1
    )
    candidate_counts: dict[tuple[str, str], int] = {}
    for candidate in inventory.get("candidates", []):
        identity = (candidate["project"], candidate["sourceId"])
        candidate_counts[identity] = candidate_counts.get(identity, 0) + 1

    missing_artifacts: list[str] = []
    multiple_candidate_artifacts: list[str] = []
    for artifact in registry.get("artifacts", []):
        upstream = artifact.get("upstream")
        if upstream is None:
            continue
        identity = (upstream.get("project"), upstream.get("sourceId"))
        count = candidate_counts.get(identity, 0)
        if count == 0:
            missing_artifacts.append(artifact["artifactId"])
        elif count > 1:
            multiple_candidate_artifacts.append(artifact["artifactId"])

    stats = {
        "joins": len(joins),
        "nonEmpty": sum(bool(item.artifact_ids) for item in joins),
        "empty": sum(not item.artifact_ids for item in joins),
        "ambiguous": len(ambiguous_joins),
        "ambiguousIdentities": tuple(sorted(ambiguous_joins)),
        "missingArtifacts": tuple(sorted(missing_artifacts)),
        "multipleCandidateArtifacts": tuple(sorted(multiple_candidate_artifacts)),
    }
    if require_complete and (
        stats["ambiguous"]
        or stats["missingArtifacts"]
        or stats["multipleCandidateArtifacts"]
    ):
        raise InventoryGenerationError(
            "REGISTRY_INTEGRATION_REGRESSION: "
            f"ambiguous joins={stats['ambiguous']}, "
            f"missing artifacts={list(stats['missingArtifacts'])}, "
            "artifacts resolving to multiple candidates="
            f"{list(stats['multipleCandidateArtifacts'])}"
        )
    return stats


def _validate_inventory_snapshot(
    inventory: Any,
    registry: Any,
    *,
    expected_project: str,
    expected_commit: str | None,
    require_complete_registry: bool,
) -> dict[str, Any]:
    result = validate_inventory_data(inventory)
    if result.errors:
        raise InventoryGenerationError(
            "INVALID_INVENTORY_STATE: " + _format_diagnostics(result)
        )
    _snapshot_provenance(
        inventory,
        expected_project=expected_project,
        expected_commit=expected_commit,
    )
    return _registry_join_stats(
        inventory, registry, require_complete=require_complete_registry
    )


def _generate_deterministic(
    extensions_root: Path, project: str, commit: str
) -> tuple[dict[str, Any], bytes]:
    first = generate_inventory(extensions_root, project, commit)
    second = generate_inventory(extensions_root, project, commit)
    first_bytes = serialize_inventory(first)
    second_bytes = serialize_inventory(second)
    if first_bytes != second_bytes:
        kind = (
            "serialization/order nondeterminism"
            if first == second
            else "generator semantic nondeterminism"
        )
        raise InventoryGenerationError(f"DETERMINISM_FAILED: {kind}")
    return first, first_bytes


def _candidate_map(inventory: Mapping[str, Any]) -> dict[tuple[str, str], Any]:
    return {
        (item["project"], item["sourceId"]): item
        for item in inventory.get("candidates", [])
    }


def _unresolved_map(inventory: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    return {
        (item["project"], item["module"]): item["reason"]["code"]
        for item in inventory.get("unresolvedModules", [])
    }


def _module_set(inventory: Mapping[str, Any]) -> set[tuple[str, str]]:
    return {
        (item["project"], item["module"])
        for field in ("candidates", "unresolvedModules")
        for item in inventory.get(field, [])
    }


def classify_inventory_drift(
    old: Mapping[str, Any], new: Mapping[str, Any]
) -> dict[str, tuple[str, ...]]:
    """Classify semantic changes without guessing candidate renames."""
    old_candidates = _candidate_map(old)
    new_candidates = _candidate_map(new)
    old_ids = set(old_candidates)
    new_ids = set(new_candidates)
    changed: list[str] = []
    missing = object()
    for identity in sorted(old_ids & new_ids):
        before = old_candidates[identity]
        after = new_candidates[identity]
        fields = tuple(
            sorted(
                field
                for field in set(before) | set(after)
                if before.get(field, missing) != after.get(field, missing)
            )
        )
        if fields:
            changed.append(f"{identity[0]}:{identity[1]} [{', '.join(fields)}]")

    old_unresolved = _unresolved_map(old)
    new_unresolved = _unresolved_map(new)
    old_unresolved_ids = set(old_unresolved)
    new_unresolved_ids = set(new_unresolved)
    reason_changes = tuple(
        f"{identity[0]}:{identity[1]} "
        f"[{old_unresolved[identity]} -> {new_unresolved[identity]}]"
        for identity in sorted(old_unresolved_ids & new_unresolved_ids)
        if old_unresolved[identity] != new_unresolved[identity]
    )
    old_modules = _module_set(old)
    new_modules = _module_set(new)

    render = lambda values: tuple(f"{a}:{b}" for a, b in sorted(values))
    return {
        "addedModules": render(new_modules - old_modules),
        "removedModules": render(old_modules - new_modules),
        "addedCandidates": render(new_ids - old_ids),
        "removedCandidates": render(old_ids - new_ids),
        "changedCandidates": tuple(changed),
        "addedUnresolved": render(new_unresolved_ids - old_unresolved_ids),
        "removedUnresolved": render(old_unresolved_ids - new_unresolved_ids),
        "changedUnresolvedReasons": reason_changes,
    }


def _inventory_counts(inventory: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        len(_module_set(inventory)),
        len(inventory.get("candidates", [])),
        len(inventory.get("unresolvedModules", [])),
    )


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _print_capped(label: str, values: tuple[str, ...]) -> None:
    print(f"{label} count={len(values)}")
    for value in values[:SUMMARY_LIST_LIMIT]:
        print(f"  {value}")
    if len(values) > SUMMARY_LIST_LIMIT:
        print(f"  ... {len(values) - SUMMARY_LIST_LIMIT} more")


def _print_review_summary(
    *,
    mode: str,
    expected_project: str,
    expected_commit: str,
    old: Mapping[str, Any] | None,
    old_bytes: bytes | None,
    new: Mapping[str, Any],
    new_bytes: bytes,
    old_registry: Mapping[str, Any] | None,
    new_registry: Mapping[str, Any],
) -> None:
    new_project, new_commit = _snapshot_provenance(
        new,
        expected_project=expected_project,
        expected_commit=expected_commit,
    )
    new_modules, new_candidates, new_unresolved = _inventory_counts(new)
    print(f"CANONICAL_INVENTORY_{mode.upper()}")
    if old is None:
        print("previous snapshot=absent")
        print(f"new project={new_project}")
        print(f"new pin={new_commit}")
        print(f"modules={new_modules}")
        print(f"candidates={new_candidates}")
        print(f"unresolvedModules={new_unresolved}")
        print(f"new SHA-256={_sha256(new_bytes)}")
    else:
        old_project, old_commit = _snapshot_provenance(
            old, expected_project=expected_project, expected_commit=None
        )
        old_modules, old_candidates, old_unresolved = _inventory_counts(old)
        print(f"old project={old_project}")
        print(f"new project={new_project}")
        print(f"old pin={old_commit}")
        print(f"new pin={new_commit}")
        print(f"old SHA-256={_sha256(old_bytes or b'')}")
        print(f"new SHA-256={_sha256(new_bytes)}")
        print(
            f"modules old={old_modules} new={new_modules} "
            f"delta={new_modules - old_modules:+d}"
        )
        print(
            f"candidates old={old_candidates} new={new_candidates} "
            f"delta={new_candidates - old_candidates:+d}"
        )
        print(
            f"unresolvedModules old={old_unresolved} new={new_unresolved} "
            f"delta={new_unresolved - old_unresolved:+d}"
        )
        drift = classify_inventory_drift(old, new)
        for label in (
            "addedModules",
            "removedModules",
            "addedCandidates",
            "removedCandidates",
            "changedCandidates",
            "addedUnresolved",
            "removedUnresolved",
            "changedUnresolvedReasons",
        ):
            _print_capped(label, drift[label])
    if old_registry is not None:
        print(
            "registry missing joins "
            f"old={len(old_registry['missingArtifacts'])} "
            f"new={len(new_registry['missingArtifacts'])}"
        )
        print(
            "registry ambiguous joins "
            f"old={old_registry['ambiguous']} new={new_registry['ambiguous']}"
        )
        _print_capped(
            "registryMissingAdded",
            tuple(
                sorted(
                    set(new_registry["missingArtifacts"])
                    - set(old_registry["missingArtifacts"])
                )
            ),
        )
        _print_capped(
            "registryMissingResolved",
            tuple(
                sorted(
                    set(old_registry["missingArtifacts"])
                    - set(new_registry["missingArtifacts"])
                )
            ),
        )
        _print_capped(
            "registryAmbiguousAdded",
            tuple(
                sorted(
                    set(new_registry["ambiguousIdentities"])
                    - set(old_registry["ambiguousIdentities"])
                )
            ),
        )
        _print_capped(
            "registryAmbiguousResolved",
            tuple(
                sorted(
                    set(old_registry["ambiguousIdentities"])
                    - set(new_registry["ambiguousIdentities"])
                )
            ),
        )
    print(
        "registry joins="
        f"{new_registry['joins']} non-empty={new_registry['nonEmpty']} "
        f"empty={new_registry['empty']} ambiguous={new_registry['ambiguous']} "
        "registered-multiple-candidates="
        f"{len(new_registry['multipleCandidateArtifacts'])}"
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def run_canonical(
    mode: str,
    extensions_root: Path | str,
    project: str,
    expected_commit: str | None,
    *,
    canonical_path: Path = CANONICAL_INVENTORY_PATH,
) -> int:
    """Run one guarded canonical materialization or non-mutating drift check."""
    if mode not in {"write", "check"}:
        raise ValueError(f"Unsupported canonical mode: {mode}")
    _validate_canonical_request(project, expected_commit)
    root, commit = validate_canonical_checkout(extensions_root, expected_commit)
    path = canonical_path.resolve()
    if mode == "check" and not path.is_file():
        raise InventoryGenerationError(
            f"CANONICAL_SNAPSHOT_MISSING: canonical inventory snapshot missing: {path}"
        )

    registry = _load_registry()
    old: Mapping[str, Any] | None = None
    old_bytes: bytes | None = None
    old_registry: Mapping[str, Any] | None = None
    if mode == "check":
        old_bytes, old_data = _load_json_bytes(path)
        old = old_data
        old_registry = _validate_inventory_snapshot(
            old,
            registry,
            expected_project=project,
            expected_commit=commit,
            require_complete_registry=True,
        )

    generated, generated_bytes = _generate_deterministic(root, project, commit)
    new_registry = _validate_inventory_snapshot(
        generated,
        registry,
        expected_project=project,
        expected_commit=commit,
        require_complete_registry=True,
    )

    if mode == "check":
        if old_bytes != generated_bytes:
            _print_review_summary(
                mode="check-drift",
                expected_project=project,
                expected_commit=commit,
                old=old,
                old_bytes=old_bytes,
                new=generated,
                new_bytes=generated_bytes,
                old_registry=old_registry,
                new_registry=new_registry,
            )
            if old == generated:
                raise InventoryGenerationError(
                    "CHECKED_IN_SERIALIZATION_DRIFT: semantic JSON is equal but "
                    "canonical bytes differ"
                )
            raise InventoryGenerationError(
                "CANONICAL_INVENTORY_DRIFT: checked-in snapshot has semantic drift"
            )
        _print_review_summary(
            mode="check",
            expected_project=project,
            expected_commit=commit,
            old=old,
            old_bytes=old_bytes,
            new=generated,
            new_bytes=generated_bytes,
            old_registry=old_registry,
            new_registry=new_registry,
        )
        return 0

    if path.is_file():
        old_bytes, old_data = _load_json_bytes(path)
        old = old_data
        old_registry = _validate_inventory_snapshot(
            old,
            registry,
            expected_project=project,
            expected_commit=None,
            require_complete_registry=False,
        )
    _print_review_summary(
        mode="bootstrap" if old is None else "write",
        expected_project=project,
        expected_commit=commit,
        old=old,
        old_bytes=old_bytes,
        new=generated,
        new_bytes=generated_bytes,
        old_registry=old_registry,
        new_registry=new_registry,
    )
    _atomic_write(path, generated_bytes)
    return 0


def _write_output(payload: bytes, output: Path | None, extensions_root: Path) -> None:
    if output is None:
        sys.stdout.buffer.write(payload)
        return
    resolved_output = output.resolve()
    resolved_upstream = extensions_root.resolve()
    if resolved_output == CANONICAL_INVENTORY_PATH.resolve():
        raise InventoryGenerationError(
            "Canonical inventory path may only be updated with --write"
        )
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
    canonical_modes = parser.add_mutually_exclusive_group()
    canonical_modes.add_argument(
        "--write",
        action="store_true",
        help="Atomically materialize the fixed canonical inventory snapshot.",
    )
    canonical_modes.add_argument(
        "--check",
        action="store_true",
        help="Non-mutatingly verify the fixed canonical inventory snapshot.",
    )
    args = parser.parse_args(argv)

    try:
        canonical_mode = "write" if args.write else "check" if args.check else None
        if canonical_mode is not None:
            if args.output is not None:
                raise InventoryGenerationError(
                    "Canonical --write/--check cannot be combined with --output"
                )
            return run_canonical(
                canonical_mode,
                args.extensions_root,
                args.project,
                args.expected_commit,
            )
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
