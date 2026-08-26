#!/usr/bin/env python3
"""Deterministically validate an upstream source-instance inventory."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


PROJECT_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SOURCE_ID_RE = re.compile(r"^[0-9]+$")
MODULE_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")
ARTIFACT_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
REASON_CODE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
BCP47_LOCALE_RE = re.compile(
    r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$"
)
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
EXTENSION_LIB_RE = re.compile(r"^[0-9]+\.[0-9]+$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")

ROOT_FIELDS = {"schemaVersion", "upstreams", "candidates", "unresolvedModules"}
UPSTREAM_SNAPSHOT_FIELDS = {"project", "commit"}
CANDIDATE_FIELDS = {
    "project",
    "sourceId",
    "module",
    "name",
    "upstreamLang",
    "canonicalLocale",
    "baseUrl",
    "contentWarning",
    "theme",
    "version",
    "extensionLib",
    "compatibility",
}
REQUIRED_CANDIDATE_FIELDS = {
    "project",
    "sourceId",
    "module",
    "name",
    "upstreamLang",
    "compatibility",
}
UNRESOLVED_MODULE_FIELDS = {"project", "module", "reason"}
UNRESOLVED_REASON_FIELDS = {"code"}
COMPATIBILITY_FIELDS = {"metadataResolution", "extraction", "patchRequired"}
REQUIRED_COMPATIBILITY_FIELDS = {"metadataResolution", "extraction"}

METADATA_RESOLUTIONS = {"static", "evaluated"}
EXTRACTION_MODES = {
    "unclassified",
    "generic",
    "adapter",
    "manual",
    "unsupported",
}
CONTENT_WARNINGS = {"SAFE", "MIXED", "NSFW"}
SEVERITY_ORDER = {"ERROR": 0}


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class RegistryJoin:
    project: str
    source_id: str
    artifact_ids: tuple[str, ...]


@dataclass(frozen=True)
class ValidationResult:
    diagnostics: tuple[Diagnostic, ...]
    registry_joins: tuple[RegistryJoin, ...] = ()

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "ERROR")

    def with_code(self, code: str) -> tuple[Diagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.code == code)


def _result(
    diagnostics: Iterable[Diagnostic],
    registry_joins: Iterable[RegistryJoin] = (),
) -> ValidationResult:
    return ValidationResult(
        tuple(
            sorted(
                diagnostics,
                key=lambda item: (
                    SEVERITY_ORDER[item.severity],
                    item.code,
                    item.subject,
                    item.message,
                ),
            )
        ),
        tuple(
            sorted(
                registry_joins,
                key=lambda item: (item.project, item.source_id),
            )
        ),
    )


def _add(
    diagnostics: list[Diagnostic], code: str, subject: str, message: str
) -> None:
    diagnostics.append(Diagnostic("ERROR", code, subject, message))


def _check_unknown_fields(
    diagnostics: list[Diagnostic],
    value: Mapping[str, Any],
    allowed: set[str],
    subject: str,
) -> None:
    for field in sorted(set(value) - allowed):
        _add(
            diagnostics,
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
) -> bool:
    if not isinstance(value, str):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            subject,
            f"Field '{field}' must be a string.",
        )
        return False
    if pattern.fullmatch(value) is None:
        _add(
            diagnostics,
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field '{field}' has an invalid value: {value!r}.",
        )
        return False
    return True


def _check_non_empty_string(
    diagnostics: list[Diagnostic], value: Any, field: str, subject: str
) -> None:
    if not isinstance(value, str):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            subject,
            f"Field '{field}' must be a string.",
        )
    elif not value:
        _add(
            diagnostics,
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field '{field}' must not be empty.",
        )


def _validate_compatibility(
    diagnostics: list[Diagnostic], value: Any, subject: str
) -> None:
    if not isinstance(value, dict):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            subject,
            "Field 'compatibility' must be an object.",
        )
        return

    _check_unknown_fields(diagnostics, value, COMPATIBILITY_FIELDS, subject)
    _check_required_fields(
        diagnostics, value, REQUIRED_COMPATIBILITY_FIELDS, subject
    )

    metadata_resolution = value.get("metadataResolution")
    if metadata_resolution not in METADATA_RESOLUTIONS:
        _add(
            diagnostics,
            "SCHEMA_FIELD_VALUE",
            subject,
            "Field 'compatibility.metadataResolution' must be one of "
            f"{sorted(METADATA_RESOLUTIONS)}.",
        )
    extraction = value.get("extraction")
    if extraction not in EXTRACTION_MODES:
        _add(
            diagnostics,
            "SCHEMA_FIELD_VALUE",
            subject,
            "Field 'compatibility.extraction' must be one of "
            f"{sorted(EXTRACTION_MODES)}.",
        )
    if "patchRequired" in value and not isinstance(value["patchRequired"], bool):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            subject,
            "Field 'compatibility.patchRequired' must be a boolean.",
        )


def _validate_upstream_snapshots(
    diagnostics: list[Diagnostic], value: Any
) -> set[str]:
    if not isinstance(value, list):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            "inventory",
            "Field 'upstreams' must be an array.",
        )
        return set()
    if not value:
        _add(
            diagnostics,
            "SCHEMA_FIELD_VALUE",
            "inventory",
            "Field 'upstreams' must contain at least one pinned project snapshot.",
        )

    declared: set[str] = set()
    for position, snapshot in enumerate(value):
        subject = f"upstreams[{position}]"
        if not isinstance(snapshot, dict):
            _add(
                diagnostics,
                "SCHEMA_FIELD_TYPE",
                subject,
                "Upstream snapshot entry must be an object.",
            )
            continue
        project = snapshot.get("project")
        if isinstance(project, str):
            subject = project
        _check_unknown_fields(
            diagnostics, snapshot, UPSTREAM_SNAPSHOT_FIELDS, subject
        )
        _check_required_fields(
            diagnostics, snapshot, UPSTREAM_SNAPSHOT_FIELDS, subject
        )
        project_valid = False
        if "project" in snapshot:
            project_valid = _check_pattern_string(
                diagnostics, snapshot["project"], PROJECT_RE, "project", subject
            )
        if "commit" in snapshot:
            _check_pattern_string(
                diagnostics, snapshot["commit"], COMMIT_RE, "commit", subject
            )
        if project_valid:
            if project in declared:
                _add(
                    diagnostics,
                    "UPSTREAM_PROJECT_DUPLICATE",
                    project,
                    "Pinned upstream project is declared more than once.",
                )
            declared.add(project)
    return declared


def _validate_unresolved_module(
    diagnostics: list[Diagnostic], value: Any, position: int
) -> str | None:
    subject = f"unresolvedModules[{position}]"
    if not isinstance(value, dict):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            subject,
            "Unresolved module entry must be an object.",
        )
        return None
    project = value.get("project")
    module = value.get("module")
    if isinstance(project, str) and isinstance(module, str):
        subject = f"{project}:{module}"
    _check_unknown_fields(
        diagnostics, value, UNRESOLVED_MODULE_FIELDS, subject
    )
    _check_required_fields(
        diagnostics, value, UNRESOLVED_MODULE_FIELDS, subject
    )
    project_valid = False
    if "project" in value:
        project_valid = _check_pattern_string(
            diagnostics, value["project"], PROJECT_RE, "project", subject
        )
    if "module" in value:
        _check_pattern_string(
            diagnostics, value["module"], MODULE_RE, "module", subject
        )
    if "reason" in value:
        reason = value["reason"]
        if not isinstance(reason, dict):
            _add(
                diagnostics,
                "SCHEMA_FIELD_TYPE",
                subject,
                "Field 'reason' must be an object.",
            )
        else:
            _check_unknown_fields(
                diagnostics, reason, UNRESOLVED_REASON_FIELDS, subject
            )
            _check_required_fields(
                diagnostics, reason, UNRESOLVED_REASON_FIELDS, subject
            )
            if "code" in reason:
                _check_pattern_string(
                    diagnostics,
                    reason["code"],
                    REASON_CODE_RE,
                    "reason.code",
                    subject,
                )
    return project if project_valid else None


def _validate_candidate(
    diagnostics: list[Diagnostic], candidate: Any, position: int
) -> tuple[str, str] | None:
    subject = f"candidates[{position}]"
    if not isinstance(candidate, dict):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            subject,
            "Candidate entry must be an object.",
        )
        return None

    project = candidate.get("project")
    source_id = candidate.get("sourceId")
    if isinstance(project, str) and isinstance(source_id, str):
        subject = f"{project}:{source_id}"

    _check_unknown_fields(diagnostics, candidate, CANDIDATE_FIELDS, subject)
    _check_required_fields(
        diagnostics, candidate, REQUIRED_CANDIDATE_FIELDS, subject
    )

    identity_valid = True
    if "project" in candidate:
        identity_valid &= _check_pattern_string(
            diagnostics, candidate["project"], PROJECT_RE, "project", subject
        )
    else:
        identity_valid = False
    if "sourceId" in candidate:
        identity_valid &= _check_pattern_string(
            diagnostics, candidate["sourceId"], SOURCE_ID_RE, "sourceId", subject
        )
    else:
        identity_valid = False
    if "module" in candidate:
        _check_pattern_string(
            diagnostics, candidate["module"], MODULE_RE, "module", subject
        )
    for field in ("name", "upstreamLang"):
        if field in candidate:
            _check_non_empty_string(diagnostics, candidate[field], field, subject)

    if "canonicalLocale" in candidate:
        _check_pattern_string(
            diagnostics,
            candidate["canonicalLocale"],
            BCP47_LOCALE_RE,
            "canonicalLocale",
            subject,
        )
    if "baseUrl" in candidate:
        base_url = candidate["baseUrl"]
        parsed = urlparse(base_url) if isinstance(base_url, str) else None
        if (
            not isinstance(base_url, str)
            or parsed is None
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):
            _add(
                diagnostics,
                "SCHEMA_FIELD_VALUE",
                subject,
                "Field 'baseUrl' must be an absolute HTTP/HTTPS URL.",
            )
    if "contentWarning" in candidate and candidate["contentWarning"] not in CONTENT_WARNINGS:
        _add(
            diagnostics,
            "SCHEMA_FIELD_VALUE",
            subject,
            f"Field 'contentWarning' must be one of {sorted(CONTENT_WARNINGS)}.",
        )
    if "theme" in candidate:
        _check_non_empty_string(diagnostics, candidate["theme"], "theme", subject)
    for field, pattern in (
        ("version", SEMVER_RE),
        ("extensionLib", EXTENSION_LIB_RE),
    ):
        if field in candidate:
            _check_pattern_string(
                diagnostics, candidate[field], pattern, field, subject
            )
    if "compatibility" in candidate:
        _validate_compatibility(diagnostics, candidate["compatibility"], subject)

    if identity_valid:
        return candidate["project"], candidate["sourceId"]
    return None


def _registry_join_map(
    diagnostics: list[Diagnostic], registry: Any
) -> dict[tuple[str, str], set[str]] | None:
    if not isinstance(registry, dict) or not isinstance(registry.get("artifacts"), list):
        _add(
            diagnostics,
            "REGISTRY_SHAPE_INVALID",
            "sources_registry.json",
            "Registry root must contain an 'artifacts' array.",
        )
        return None

    joined: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    all_artifact_ids: set[str] = set()
    for position, artifact in enumerate(registry["artifacts"]):
        if not isinstance(artifact, dict):
            _add(
                diagnostics,
                "REGISTRY_ARTIFACT_INVALID",
                f"artifacts[{position}]",
                "Registry artifact entry must be an object.",
            )
            continue
        artifact_id = artifact.get("artifactId")
        subject = artifact_id if isinstance(artifact_id, str) else f"artifacts[{position}]"
        if (
            not isinstance(artifact_id, str)
            or ARTIFACT_ID_RE.fullmatch(artifact_id) is None
        ):
            _add(
                diagnostics,
                "REGISTRY_ARTIFACT_INVALID",
                subject,
                "Registry artifactId must be a normalized string.",
            )
            continue
        if artifact_id in all_artifact_ids:
            _add(
                diagnostics,
                "REGISTRY_ARTIFACT_ID_DUPLICATE",
                artifact_id,
                "Registry artifactId is ambiguous.",
            )
        all_artifact_ids.add(artifact_id)
        upstream = artifact.get("upstream")
        if upstream is None:
            continue
        if not isinstance(upstream, dict):
            _add(
                diagnostics,
                "REGISTRY_UPSTREAM_INVALID",
                artifact_id,
                "Registry upstream metadata must be an object.",
            )
            continue
        project = upstream.get("project")
        source_id = upstream.get("sourceId")
        if (
            not isinstance(project, str)
            or PROJECT_RE.fullmatch(project) is None
            or not isinstance(source_id, str)
            or SOURCE_ID_RE.fullmatch(source_id) is None
        ):
            _add(
                diagnostics,
                "REGISTRY_UPSTREAM_INVALID",
                artifact_id,
                "Registry upstream join metadata requires valid string project and sourceId fields.",
            )
            continue
        joined[(project, source_id)].add(artifact_id)
    return dict(joined)


def _cross_validate_registry(
    diagnostics: list[Diagnostic], candidates: list[Any], registry: Any
) -> tuple[RegistryJoin, ...]:
    joined = _registry_join_map(diagnostics, registry)
    if joined is None:
        return ()

    results: list[RegistryJoin] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        project = candidate.get("project")
        source_id = candidate.get("sourceId")
        if (
            not isinstance(project, str)
            or not isinstance(source_id, str)
            or PROJECT_RE.fullmatch(project) is None
            or SOURCE_ID_RE.fullmatch(source_id) is None
        ):
            continue
        results.append(
            RegistryJoin(
                project,
                source_id,
                tuple(sorted(joined.get((project, source_id), set()))),
            )
        )
    return tuple(results)


def validate_inventory_data(
    data: Any, registry: Any | None = None
) -> ValidationResult:
    """Validate parsed inventory data, optionally cross-checking a parsed registry."""
    diagnostics: list[Diagnostic] = []
    if not isinstance(data, dict):
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            "inventory",
            "Inventory root must be an object.",
        )
        return _result(diagnostics)

    _check_unknown_fields(diagnostics, data, ROOT_FIELDS, "inventory")
    _check_required_fields(diagnostics, data, ROOT_FIELDS, "inventory")
    if data.get("schemaVersion") != "1.0":
        _add(
            diagnostics,
            "SCHEMA_FIELD_VALUE",
            "inventory",
            "Field 'schemaVersion' must equal '1.0'.",
        )

    declared_projects = _validate_upstream_snapshots(
        diagnostics, data.get("upstreams")
    )

    candidate_value = data.get("candidates")
    candidates: list[Any]
    if not isinstance(candidate_value, list):
        candidates = []
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            "inventory",
            "Field 'candidates' must be an array.",
        )
    else:
        candidates = candidate_value

    unresolved_value = data.get("unresolvedModules")
    unresolved_modules: list[Any]
    if not isinstance(unresolved_value, list):
        unresolved_modules = []
        _add(
            diagnostics,
            "SCHEMA_FIELD_TYPE",
            "inventory",
            "Field 'unresolvedModules' must be an array.",
        )
    else:
        unresolved_modules = unresolved_value

    if (
        isinstance(candidate_value, list)
        and isinstance(unresolved_value, list)
        and not candidates
        and not unresolved_modules
    ):
        _add(
            diagnostics,
            "INVENTORY_RECORDS_EMPTY",
            "inventory",
            "At least one resolved candidate or unresolved module is required.",
        )

    seen_identities: dict[tuple[str, str], int] = {}
    for position, candidate in enumerate(candidates):
        identity = _validate_candidate(diagnostics, candidate, position)
        if identity is None:
            continue
        if identity[0] not in declared_projects:
            _add(
                diagnostics,
                "UPSTREAM_PROJECT_UNDECLARED",
                f"{identity[0]}:{identity[1]}",
                "Candidate project has no root pinned upstream snapshot.",
            )
        if identity in seen_identities:
            first_position = seen_identities[identity]
            _add(
                diagnostics,
                "CANDIDATE_IDENTITY_DUPLICATE",
                f"{identity[0]}:{identity[1]}",
                "Duplicate upstream candidate identity (project, sourceId) at "
                f"candidates[{first_position}] and candidates[{position}].",
            )
        else:
            seen_identities[identity] = position

    for position, unresolved_module in enumerate(unresolved_modules):
        project = _validate_unresolved_module(
            diagnostics, unresolved_module, position
        )
        if project is not None and project not in declared_projects:
            module = (
                unresolved_module.get("module", "<unknown>")
                if isinstance(unresolved_module, dict)
                else "<unknown>"
            )
            _add(
                diagnostics,
                "UPSTREAM_PROJECT_UNDECLARED",
                f"{project}:{module}",
                "Unresolved module project has no root pinned upstream snapshot.",
            )

    registry_joins: tuple[RegistryJoin, ...] = ()
    if registry is not None:
        registry_joins = _cross_validate_registry(
            diagnostics, candidates, registry
        )
    return _result(diagnostics, registry_joins)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an upstream inventory without network or build execution."
    )
    parser.add_argument("inventory", type=Path, help="Inventory JSON file to validate.")
    parser.add_argument(
        "--registry",
        type=Path,
        help="Optional sources_registry.json for explicit upstream identity joins.",
    )
    args = parser.parse_args(argv)

    try:
        inventory = _load_json(args.inventory)
        registry = _load_json(args.registry) if args.registry is not None else None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"[ERROR] JSON_READ_FAILED: {exc}")
        print("SUMMARY errors=1")
        return 1

    result = validate_inventory_data(inventory, registry)
    for diagnostic in result.diagnostics:
        print(
            f"[{diagnostic.severity}] {diagnostic.code} {diagnostic.subject}: "
            f"{diagnostic.message}"
        )
    for join in result.registry_joins:
        print(
            "[REPORT] REGISTRY_JOIN "
            f"{join.project}:{join.source_id}: artifactIds={list(join.artifact_ids)!r}"
        )
    print(
        f"SUMMARY errors={len(result.errors)} "
        f"registryJoins={len(result.registry_joins)}"
    )
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
