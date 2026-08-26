#!/usr/bin/env python3
"""Validate the development-time source taxonomy registry and catalog linkage."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

try:
    from .static_js_validator import JSScanner
except ImportError:  # Direct script execution from this directory.
    from static_js_validator import JSScanner


ARTIFACT_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
RUNTIME_KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")
BCP47_LOCALE_RE = re.compile(
    r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$"
)
MODULE_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")
SOURCE_ID_RE = re.compile(r"^[0-9]+$")
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
EXTENSION_LIB_RE = re.compile(r"^[0-9]+\.[0-9]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
PROJECT_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

ROOT_FIELDS = {"schemaVersion", "artifacts"}
ARTIFACT_FIELDS = {
    "artifactId",
    "runtimeKey",
    "catalogName",
    "catalogDescription",
    "locales",
    "providerId",
    "siteUrl",
    "contentWarning",
    "implementation",
    "upstream",
    "supportStatus",
    "compatibility",
}
IMPLEMENTATION_FIELDS = {"producer", "transport"}
UPSTREAM_FIELDS = {
    "project",
    "module",
    "sourceId",
    "version",
    "extensionLib",
    "commit",
    "theme",
}
COMPATIBILITY_FIELDS = {"sharedRuntimeKeyGroup"}

PRODUCERS = {"manual", "generated", "generated-with-patch"}
TRANSPORTS = {"api", "html", "hybrid"}
CONTENT_WARNINGS = {"SAFE", "MIXED", "NSFW"}
SUPPORT_STATUSES = {"active", "needs-rescue", "retired"}

SEVERITY_ORDER = {"ERROR": 0, "WARNING": 1, "REPORT": 2}


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    diagnostics: tuple[Diagnostic, ...]

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == "ERROR")

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == "WARNING")

    @property
    def reports(self) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == "REPORT")

    def with_code(self, code: str) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.code == code)


class IndexDerivationError(ValueError):
    """Raised when canonical index entries cannot be derived safely."""

    def __init__(self, diagnostics: Iterable[Diagnostic]):
        self.diagnostics = tuple(diagnostics)
        message = "; ".join(
            f"{item.code} {item.subject}: {item.message}"
            for item in self.diagnostics
        )
        super().__init__(message or "Canonical index derivation failed.")


def _result(diagnostics: Iterable[Diagnostic]) -> ValidationResult:
    ordered = sorted(
        diagnostics,
        key=lambda d: (SEVERITY_ORDER[d.severity], d.code, d.subject, d.message),
    )
    return ValidationResult(tuple(ordered))


def _add(
    diagnostics: list[Diagnostic],
    severity: str,
    code: str,
    subject: str,
    message: str,
) -> None:
    diagnostics.append(Diagnostic(severity, code, subject, message))


def is_bcp47_locale(value: Any) -> bool:
    """Return whether value uses the bounded source-instance locale grammar."""
    return isinstance(value, str) and BCP47_LOCALE_RE.fullmatch(value) is not None


def _check_unknown_fields(
    diagnostics: list[Diagnostic],
    value: Mapping[str, Any],
    allowed: set[str],
    subject: str,
) -> None:
    for field in sorted(set(value) - allowed):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_UNKNOWN_FIELD",
            subject,
            f"Unknown field '{field}'.",
        )


def _check_required_fields(
    diagnostics: list[Diagnostic],
    value: Mapping[str, Any],
    required: set[str],
    subject: str,
) -> None:
    for field in sorted(required - set(value)):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_REQUIRED_FIELD",
            subject,
            f"Missing required field '{field}'.",
        )


def _check_pattern_string(
    diagnostics: list[Diagnostic],
    value: Any,
    pattern: re.Pattern[str],
    field: str,
    subject: str,
) -> None:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field '{field}' has an invalid value: {value!r}.",
        )


def _validate_implementation(
    diagnostics: list[Diagnostic], value: Any, subject: str
) -> None:
    if not isinstance(value, dict):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_TYPE",
            subject,
            "Field 'implementation' must be an object.",
        )
        return
    _check_unknown_fields(diagnostics, value, IMPLEMENTATION_FIELDS, subject)
    _check_required_fields(diagnostics, value, {"producer"}, subject)
    producer = value.get("producer")
    if producer not in PRODUCERS:
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field 'implementation.producer' must be one of {sorted(PRODUCERS)}.",
        )
    if "transport" in value and value["transport"] not in TRANSPORTS:
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field 'implementation.transport' must be one of {sorted(TRANSPORTS)}.",
        )


def _validate_upstream(diagnostics: list[Diagnostic], value: Any, subject: str) -> None:
    if not isinstance(value, dict):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_TYPE",
            subject,
            "Field 'upstream' must be an object.",
        )
        return
    _check_unknown_fields(diagnostics, value, UPSTREAM_FIELDS, subject)
    _check_required_fields(
        diagnostics,
        value,
        {"project", "module", "sourceId", "version", "extensionLib", "commit"},
        subject,
    )
    checks = (
        ("project", PROJECT_RE),
        ("module", MODULE_RE),
        ("sourceId", SOURCE_ID_RE),
        ("version", SEMVER_RE),
        ("extensionLib", EXTENSION_LIB_RE),
        ("commit", COMMIT_RE),
    )
    for field, pattern in checks:
        if field in value:
            _check_pattern_string(diagnostics, value[field], pattern, f"upstream.{field}", subject)
    if "theme" in value and (
        not isinstance(value["theme"], str) or not value["theme"].strip()
    ):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_VALUE",
            subject,
            "Field 'upstream.theme' must be a non-empty string.",
        )


def _validate_compatibility(
    diagnostics: list[Diagnostic], value: Any, subject: str
) -> None:
    if not isinstance(value, dict):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_TYPE",
            subject,
            "Field 'compatibility' must be an object.",
        )
        return
    _check_unknown_fields(diagnostics, value, COMPATIBILITY_FIELDS, subject)
    _check_required_fields(diagnostics, value, {"sharedRuntimeKeyGroup"}, subject)
    if "sharedRuntimeKeyGroup" in value:
        _check_pattern_string(
            diagnostics,
            value["sharedRuntimeKeyGroup"],
            RUNTIME_KEY_RE,
            "compatibility.sharedRuntimeKeyGroup",
            subject,
        )


def _validate_artifact(
    diagnostics: list[Diagnostic], artifact: Any, position: int
) -> None:
    subject = f"artifacts[{position}]"
    if not isinstance(artifact, dict):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_TYPE",
            subject,
            "Artifact entry must be an object.",
        )
        return

    artifact_id = artifact.get("artifactId")
    if isinstance(artifact_id, str):
        subject = artifact_id

    _check_unknown_fields(diagnostics, artifact, ARTIFACT_FIELDS, subject)
    _check_required_fields(
        diagnostics,
        artifact,
        {"artifactId", "runtimeKey", "providerId", "implementation"},
        subject,
    )

    if "artifactId" in artifact:
        _check_pattern_string(
            diagnostics, artifact["artifactId"], ARTIFACT_ID_RE, "artifactId", subject
        )
    if "runtimeKey" in artifact:
        _check_pattern_string(
            diagnostics, artifact["runtimeKey"], RUNTIME_KEY_RE, "runtimeKey", subject
        )
    for field in ("catalogName", "catalogDescription"):
        if field not in artifact:
            continue
        value = artifact[field]
        if not isinstance(value, str):
            _add(
                diagnostics,
                "ERROR",
                "SCHEMA_FIELD_TYPE",
                subject,
                f"Field '{field}' must be a string.",
            )
        elif not value:
            _add(
                diagnostics,
                "ERROR",
                "SCHEMA_FIELD_VALUE",
                subject,
                f"Field '{field}' must not be empty.",
            )
    if "providerId" in artifact:
        _check_pattern_string(
            diagnostics, artifact["providerId"], ARTIFACT_ID_RE, "providerId", subject
        )

    if "locales" in artifact:
        locales = artifact["locales"]
        if not isinstance(locales, list) or not locales:
            _add(
                diagnostics,
                "ERROR",
                "SCHEMA_FIELD_TYPE",
                subject,
                "Field 'locales' must be a non-empty array.",
            )
        else:
            if len(locales) != len({repr(locale) for locale in locales}):
                _add(
                    diagnostics,
                    "ERROR",
                    "DUPLICATE_LOCALE",
                    subject,
                    "Field 'locales' contains duplicate entries.",
                )
            for locale in locales:
                if not is_bcp47_locale(locale):
                    _add(
                        diagnostics,
                        "ERROR",
                        "INVALID_LOCALE",
                        subject,
                        f"Locale {locale!r} is not in the accepted source-instance locale form.",
                    )

    if "siteUrl" in artifact:
        site_url = artifact["siteUrl"]
        parsed = urlparse(site_url) if isinstance(site_url, str) else None
        if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            _add(
                diagnostics,
                "ERROR",
                "SCHEMA_FIELD_VALUE",
                subject,
                f"Field 'siteUrl' must be an absolute HTTP/HTTPS URL: {site_url!r}.",
            )

    if "contentWarning" in artifact and artifact["contentWarning"] not in CONTENT_WARNINGS:
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field 'contentWarning' must be one of {sorted(CONTENT_WARNINGS)}.",
        )
    if "supportStatus" in artifact and artifact["supportStatus"] not in SUPPORT_STATUSES:
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field 'supportStatus' must be one of {sorted(SUPPORT_STATUSES)}.",
        )

    if "implementation" in artifact:
        _validate_implementation(diagnostics, artifact["implementation"], subject)
    if "upstream" in artifact:
        _validate_upstream(diagnostics, artifact["upstream"], subject)
    if "compatibility" in artifact:
        _validate_compatibility(diagnostics, artifact["compatibility"], subject)


def _validate_runtime_key_groups(
    diagnostics: list[Diagnostic], artifacts: Sequence[Mapping[str, Any]]
) -> None:
    runtime_groups: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    shared_groups: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)

    for artifact in artifacts:
        runtime_key = artifact.get("runtimeKey")
        if isinstance(runtime_key, str):
            runtime_groups[runtime_key].append(artifact)

        compatibility = artifact.get("compatibility")
        shared_group = (
            compatibility.get("sharedRuntimeKeyGroup")
            if isinstance(compatibility, dict)
            else None
        )
        if isinstance(shared_group, str):
            shared_groups[shared_group].append(artifact)

    for shared_group, members in sorted(shared_groups.items()):
        artifact_ids = sorted(str(item.get("artifactId")) for item in members)
        runtime_keys = sorted(
            {
                str(item.get("runtimeKey"))
                for item in members
                if isinstance(item.get("runtimeKey"), str)
            }
        )
        if len(members) < 2:
            _add(
                diagnostics,
                "ERROR",
                "INVALID_SHARED_RUNTIME_KEY_GROUP",
                shared_group,
                f"sharedRuntimeKeyGroup {shared_group!r} has only {len(members)} member: {artifact_ids}; expected at least two.",
            )
        if len(runtime_keys) != 1:
            _add(
                diagnostics,
                "ERROR",
                "INVALID_SHARED_RUNTIME_KEY_GROUP",
                shared_group,
                f"sharedRuntimeKeyGroup {shared_group!r} spans runtimeKeys {runtime_keys}; expected exactly one shared runtimeKey.",
            )

    for runtime_key, members in sorted(runtime_groups.items()):
        artifact_ids = sorted(str(item.get("artifactId")) for item in members)
        declarations = []
        for item in members:
            compatibility = item.get("compatibility")
            declarations.append(
                compatibility.get("sharedRuntimeKeyGroup")
                if isinstance(compatibility, dict)
                else None
            )

        if len(members) == 1:
            if isinstance(declarations[0], str):
                _add(
                    diagnostics,
                    "ERROR",
                    "UNNECESSARY_SHARED_RUNTIME_KEY_GROUP",
                    artifact_ids[0],
                    f"Artifact {artifact_ids[0]!r} has unique runtimeKey {runtime_key!r} and must not declare sharedRuntimeKeyGroup {declarations[0]!r}.",
                )
            continue

        declared_groups = {value for value in declarations if isinstance(value, str)}
        one_group = len(declared_groups) == 1 and all(
            isinstance(value, str) for value in declarations
        )
        shared_group = next(iter(declared_groups)) if one_group else None
        shared_members = shared_groups.get(shared_group, []) if shared_group else []
        group_runtime_keys = {
            item.get("runtimeKey")
            for item in shared_members
            if isinstance(item.get("runtimeKey"), str)
        }
        valid_group = (
            one_group
            and len(shared_members) >= 2
            and group_runtime_keys == {runtime_key}
        )

        if valid_group:
            _add(
                diagnostics,
                "REPORT",
                "SHARED_RUNTIME_KEY",
                runtime_key,
                f"Artifacts {artifact_ids} share runtimeKey {runtime_key!r} through explicit sharedRuntimeKeyGroup {shared_group!r}.",
            )
        else:
            rendered_declarations = sorted(
                "<missing>" if value is None else repr(value) for value in declarations
            )
            _add(
                diagnostics,
                "ERROR",
                "DUPLICATE_RUNTIME_KEY",
                runtime_key,
                f"Artifacts {artifact_ids} share runtimeKey {runtime_key!r} but do not all participate in one valid sharedRuntimeKeyGroup; declarations: {rendered_declarations}.",
            )


def validate_registry_data(data: Any) -> ValidationResult:
    """Validate registry structure without reading repository artifacts."""
    diagnostics: list[Diagnostic] = []
    if not isinstance(data, dict):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_ROOT_TYPE",
            "registry",
            "Registry root must be an object.",
        )
        return _result(diagnostics)

    _check_unknown_fields(diagnostics, data, ROOT_FIELDS, "registry")
    _check_required_fields(diagnostics, data, ROOT_FIELDS, "registry")
    if data.get("schemaVersion") != "1.0":
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_VERSION",
            "registry",
            "Field 'schemaVersion' must equal '1.0'.",
        )

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list):
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_TYPE",
            "registry",
            "Field 'artifacts' must be an array.",
        )
        return _result(diagnostics)
    if not artifacts:
        _add(
            diagnostics,
            "ERROR",
            "SCHEMA_FIELD_VALUE",
            "registry",
            "Field 'artifacts' must contain at least one artifact.",
        )

    for position, artifact in enumerate(artifacts):
        _validate_artifact(diagnostics, artifact, position)

    positions: defaultdict[str, list[int]] = defaultdict(list)
    for position, artifact in enumerate(artifacts):
        if isinstance(artifact, dict) and isinstance(artifact.get("artifactId"), str):
            positions[artifact["artifactId"]].append(position)
    for artifact_id, found_positions in sorted(positions.items()):
        if len(found_positions) > 1:
            _add(
                diagnostics,
                "ERROR",
                "DUPLICATE_ARTIFACT_ID",
                artifact_id,
                f"artifactId occurs at positions {found_positions}.",
            )

    valid_artifacts = [item for item in artifacts if isinstance(item, dict)]
    _validate_runtime_key_groups(diagnostics, valid_artifacts)

    return _result(diagnostics)


JS_FIELDS = {
    field: re.compile(
        rf"^\s*(?:static\s+)?{field}\s*=\s*([\"'])([^\"'\r\n]+)\1\s*;?\s*$",
        re.MULTILINE,
    )
    for field in ("name", "key", "version")
}


def inspect_final_js(path: Path) -> dict[str, str | None]:
    body = path.read_text(encoding="utf-8")
    scanner = JSScanner(body)
    scanner.scan()
    if scanner.errors:
        raise ValueError("; ".join(scanner.errors))
    class_pattern = r"^\s*class\s+\w+\s+extends\s+ComicSource\s*\{"
    if re.search(class_pattern, body, re.MULTILINE) is None:
        raise ValueError("Final JS has no inspectable ComicSource class declaration.")
    return {
        field: (match.group(2) if (match := pattern.search(body)) else None)
        for field, pattern in JS_FIELDS.items()
    }


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate_runtime_artifacts(
    diagnostics: list[Diagnostic],
    repo_root: Path,
    artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, str | None]]:
    inspected: dict[str, dict[str, str | None]] = {}

    for artifact in artifacts:
        artifact_id = artifact.get("artifactId")
        runtime_key = artifact.get("runtimeKey")
        if not isinstance(artifact_id, str) or not ARTIFACT_ID_RE.fullmatch(artifact_id):
            continue

        final_path = repo_root / f"{artifact_id}.js"
        if not final_path.is_file():
            _add(
                diagnostics,
                "ERROR",
                "ARTIFACT_FILE_MISSING",
                artifact_id,
                f"Expected final JS filename '{artifact_id}.js' does not exist.",
            )
            continue

        try:
            metadata = inspect_final_js(final_path)
        except ValueError as exc:
            _add(
                diagnostics,
                "ERROR",
                "FINAL_JS_MALFORMED",
                artifact_id,
                str(exc),
            )
            continue
        except (OSError, UnicodeError) as exc:
            _add(
                diagnostics,
                "ERROR",
                "FINAL_JS_READ_FAILED",
                artifact_id,
                str(exc),
            )
            continue
        inspected[artifact_id] = metadata
        for field in ("name", "key", "version"):
            if metadata[field] is None:
                _add(
                    diagnostics,
                    "ERROR",
                    "FINAL_JS_METADATA_MISSING",
                    artifact_id,
                    f"Final JS has no inspectable '{field}' field.",
                )
        if metadata["key"] is not None and metadata["key"] != runtime_key:
            _add(
                diagnostics,
                "ERROR",
                "RUNTIME_KEY_MISMATCH",
                artifact_id,
                f"Registry runtimeKey {runtime_key!r} != final JS key {metadata['key']!r}.",
            )

    return inspected


def _derive_index_entries(
    artifacts: Sequence[Mapping[str, Any]],
    inspected: Mapping[str, Mapping[str, str | None]],
) -> list[dict[str, str]] | None:
    """Build canonical index entries in registry order from validated inputs."""
    entries: list[dict[str, str]] = []
    for artifact in artifacts:
        artifact_id = artifact.get("artifactId")
        runtime_key = artifact.get("runtimeKey")
        catalog_name = artifact.get("catalogName")
        catalog_description = artifact.get("catalogDescription")
        if not isinstance(artifact_id, str) or not isinstance(runtime_key, str):
            return None
        if catalog_name is not None and not isinstance(catalog_name, str):
            return None
        if catalog_description is not None and not isinstance(catalog_description, str):
            return None

        metadata = inspected.get(artifact_id)
        if metadata is None:
            return None
        runtime_name = metadata.get("name")
        final_key = metadata.get("key")
        runtime_version = metadata.get("version")
        if not all(
            isinstance(value, str) and value
            for value in (runtime_name, final_key, runtime_version)
        ):
            return None
        if final_key != runtime_key:
            return None

        entry = {
            "name": catalog_name if catalog_name is not None else runtime_name,
            "fileName": f"{artifact_id}.js",
            "key": runtime_key,
            "version": runtime_version,
        }
        if catalog_description is not None:
            entry["description"] = catalog_description
        entries.append(entry)
    return entries


def derive_index(repo_root: Path | str) -> list[dict[str, str]]:
    """Derive the complete canonical index without reading or writing index.json."""
    root = Path(repo_root).resolve()
    registry_path = root / "sources_registry.json"
    diagnostics: list[Diagnostic] = []
    try:
        registry = _load_json(registry_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _add(diagnostics, "ERROR", "REGISTRY_READ_FAILED", registry_path.name, str(exc))
        raise IndexDerivationError(diagnostics) from exc

    registry_result = validate_registry_data(registry)
    diagnostics.extend(registry_result.errors)
    if diagnostics:
        raise IndexDerivationError(diagnostics)

    artifacts = [item for item in registry["artifacts"] if isinstance(item, dict)]
    inspected = _validate_runtime_artifacts(diagnostics, root, artifacts)
    if diagnostics:
        raise IndexDerivationError(diagnostics)

    entries = _derive_index_entries(artifacts, inspected)
    if entries is None:
        _add(
            diagnostics,
            "ERROR",
            "INDEX_DERIVATION_FAILED",
            "sources_registry.json",
            "Validated registry and final JS metadata did not produce a complete index.",
        )
        raise IndexDerivationError(diagnostics)
    return entries


def write_index(repo_root: Path | str) -> list[dict[str, str]]:
    """Atomically replace index.json with a fully derived canonical document."""
    root = Path(repo_root).resolve()
    entries = derive_index(root)
    payload = json.dumps(entries, ensure_ascii=False, indent=4) + "\n"
    index_path = root / "index.json"
    temp_path: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{index_path.name}.",
            suffix=".tmp",
            dir=index_path.parent,
        )
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, index_path)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return entries


def _validate_ir_linkage(
    diagnostics: list[Diagnostic],
    repo_root: Path,
    artifacts_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    linked: defaultdict[str, list[str]] = defaultdict(list)
    ir_dir = repo_root / "sources_ir"
    for ir_path in sorted(ir_dir.glob("*.json"), key=lambda path: path.name):
        try:
            ir = _load_json(ir_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            _add(diagnostics, "ERROR", "IR_READ_FAILED", ir_path.name, str(exc))
            continue
        artifact_id = ir.get("artifactId") if isinstance(ir, dict) else None
        if not isinstance(artifact_id, str):
            _add(
                diagnostics,
                "ERROR",
                "IR_ARTIFACT_LINK_MISSING",
                ir_path.name,
                "Converted IR has no string artifactId linkage.",
            )
            continue
        linked[artifact_id].append(ir_path.name)
        if artifact_id != ir_path.stem:
            _add(
                diagnostics,
                "ERROR",
                "IR_ARTIFACT_FILENAME_MISMATCH",
                ir_path.name,
                f"IR artifactId {artifact_id!r} != IR filename stem {ir_path.stem!r}.",
            )
        registry_artifact = artifacts_by_id.get(artifact_id)
        if registry_artifact is None:
            _add(
                diagnostics,
                "ERROR",
                "IR_ARTIFACT_UNREGISTERED",
                ir_path.name,
                f"IR links to unregistered artifactId {artifact_id!r}.",
            )
        elif registry_artifact.get("implementation", {}).get("producer") == "manual":
            _add(
                diagnostics,
                "ERROR",
                "IR_PRODUCER_MISMATCH",
                ir_path.name,
                f"IR-linked artifact {artifact_id!r} is marked as manually produced.",
            )

    for artifact_id, ir_names in sorted(linked.items()):
        if len(ir_names) > 1:
            _add(
                diagnostics,
                "ERROR",
                "DUPLICATE_IR_ARTIFACT_LINK",
                artifact_id,
                f"Multiple IR files link to the artifact: {sorted(ir_names)}.",
            )

    for artifact_id, artifact in sorted(artifacts_by_id.items()):
        producer = artifact.get("implementation", {}).get("producer")
        if producer in {"generated", "generated-with-patch"} and artifact_id not in linked:
            _add(
                diagnostics,
                "ERROR",
                "REGISTRY_IR_LINK_MISSING",
                artifact_id,
                "Generated artifact has no converted IR linkage.",
            )


def _validate_index(
    diagnostics: list[Diagnostic],
    repo_root: Path,
    canonical_index: Sequence[Mapping[str, str]],
) -> None:
    index_path = repo_root / "index.json"
    try:
        index = _load_json(index_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _add(diagnostics, "ERROR", "INDEX_READ_FAILED", "index.json", str(exc))
        return
    if not isinstance(index, list):
        _add(
            diagnostics,
            "ERROR",
            "INDEX_ROOT_TYPE",
            "index.json",
            "Catalog index root must be an array.",
        )
        return

    seen_files: set[str] = set()
    actual_by_file: dict[str, Mapping[str, Any]] = {}
    actual_order: list[str] = []
    for position, entry in enumerate(index):
        subject = f"index[{position}]"
        if not isinstance(entry, dict):
            _add(diagnostics, "ERROR", "INDEX_ENTRY_TYPE", subject, "Entry must be an object.")
            continue
        file_name = entry.get("fileName")
        if not isinstance(file_name, str) or Path(file_name).name != file_name or not file_name.endswith(".js"):
            _add(
                diagnostics,
                "ERROR",
                "INDEX_FILENAME_INVALID",
                subject,
                f"fileName must be a root-level .js filename: {file_name!r}.",
            )
            continue
        subject = file_name
        if file_name in seen_files:
            _add(
                diagnostics,
                "ERROR",
                "INDEX_FILENAME_DUPLICATE",
                subject,
                "Catalog fileName occurs more than once.",
            )
            continue
        seen_files.add(file_name)
        actual_by_file[file_name] = entry
        actual_order.append(file_name)
        final_path = repo_root / file_name
        if not final_path.is_file():
            _add(
                diagnostics,
                "ERROR",
                "INDEX_FILE_MISSING",
                subject,
                "Catalog fileName does not exist.",
            )

    expected_by_file = {entry["fileName"]: entry for entry in canonical_index}
    expected_order = [entry["fileName"] for entry in canonical_index]
    for file_name in expected_order:
        if file_name not in actual_by_file:
            _add(
                diagnostics,
                "WARNING",
                "INDEX_ENTRY_MISSING",
                file_name,
                "Canonical registry artifact is missing from index.json; index.json was not changed.",
            )

    for file_name in actual_order:
        if file_name not in expected_by_file:
            _add(
                diagnostics,
                "WARNING",
                "INDEX_ENTRY_EXTRA",
                file_name,
                "index.json contains no matching canonical registry artifact; index.json was not changed.",
            )

    if set(actual_order) == set(expected_order) and actual_order != expected_order:
        _add(
            diagnostics,
            "WARNING",
            "INDEX_ORDER_MISMATCH",
            "index.json",
            f"Catalog fileName order {actual_order!r} != canonical registry order {expected_order!r}; index.json was not changed.",
        )

    missing = object()
    for file_name in expected_order:
        entry = actual_by_file.get(file_name)
        expected = expected_by_file[file_name]
        if entry is None:
            continue
        comparisons = (
            ("name", "INDEX_NAME_MISMATCH"),
            ("key", "INDEX_KEY_MISMATCH"),
            ("version", "INDEX_VERSION_MISMATCH"),
            ("description", "INDEX_DESCRIPTION_MISMATCH"),
        )
        for field, code in comparisons:
            actual_value = entry.get(field, missing)
            expected_value = expected.get(field, missing)
            if actual_value != expected_value:
                rendered_actual = "<absent>" if actual_value is missing else repr(actual_value)
                rendered_expected = "<absent>" if expected_value is missing else repr(expected_value)
                _add(
                    diagnostics,
                    "WARNING",
                    code,
                    file_name,
                    f"Catalog {field} {rendered_actual} != canonical {field} {rendered_expected}; index.json was not changed.",
                )

        unexpected_fields = sorted(set(entry) - set(expected))
        if unexpected_fields:
            _add(
                diagnostics,
                "WARNING",
                "INDEX_FIELDS_EXTRA",
                file_name,
                f"Catalog entry has non-canonical fields {unexpected_fields}; index.json was not changed.",
            )


def validate_repository(repo_root: Path | str) -> ValidationResult:
    """Validate the canonical registry and its read-only repository relationships."""
    root = Path(repo_root).resolve()
    registry_path = root / "sources_registry.json"
    diagnostics: list[Diagnostic] = []
    try:
        registry = _load_json(registry_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _add(diagnostics, "ERROR", "REGISTRY_READ_FAILED", registry_path.name, str(exc))
        return _result(diagnostics)

    registry_result = validate_registry_data(registry)
    diagnostics.extend(registry_result.diagnostics)
    if not isinstance(registry, dict) or not isinstance(registry.get("artifacts"), list):
        return _result(diagnostics)

    artifacts = [item for item in registry["artifacts"] if isinstance(item, dict)]
    artifacts_by_id = {
        item["artifactId"]: item
        for item in artifacts
        if isinstance(item.get("artifactId"), str)
    }
    inspected = _validate_runtime_artifacts(diagnostics, root, artifacts)
    _validate_ir_linkage(diagnostics, root, artifacts_by_id)
    canonical_index = (
        None
        if registry_result.errors
        else _derive_index_entries(artifacts, inspected)
    )
    if canonical_index is not None:
        _validate_index(diagnostics, root, canonical_index)
    return _result(diagnostics)


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate sources_registry.json and report catalog/runtime drift."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root(),
        help="venera-configs repository root (defaults to the current checkout).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-index",
        action="store_true",
        help="Exit non-zero when the checked-in index differs from canonical derivation; never writes index.json.",
    )
    mode.add_argument(
        "--write-index",
        action="store_true",
        help="Atomically replace index.json with the fully derived canonical catalog.",
    )
    args = parser.parse_args(argv)
    if args.write_index:
        try:
            entries = write_index(args.repo_root)
        except IndexDerivationError as exc:
            for diagnostic in exc.diagnostics:
                print(
                    f"[{diagnostic.severity}] {diagnostic.code} {diagnostic.subject}: "
                    f"{diagnostic.message}"
                )
            print(
                "SUMMARY "
                f"errors={len(exc.diagnostics)} warnings=0 reports=0"
            )
            return 1
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            print(f"[ERROR] INDEX_WRITE_FAILED index.json: {exc}")
            print("SUMMARY errors=1 warnings=0 reports=0")
            return 1
        print(f"WROTE index.json entries={len(entries)}")
        print("SUMMARY errors=0 warnings=0 reports=1")
        return 0

    result = validate_repository(args.repo_root)
    for diagnostic in result.diagnostics:
        print(
            f"[{diagnostic.severity}] {diagnostic.code} {diagnostic.subject}: "
            f"{diagnostic.message}"
        )
    print(
        "SUMMARY "
        f"errors={len(result.errors)} "
        f"warnings={len(result.warnings)} "
        f"reports={len(result.reports)}"
    )
    index_drift = any(
        diagnostic.code.startswith("INDEX_")
        for diagnostic in result.warnings
    )
    return 1 if result.errors or (args.check_index and index_drift) else 0


if __name__ == "__main__":
    sys.exit(main())
