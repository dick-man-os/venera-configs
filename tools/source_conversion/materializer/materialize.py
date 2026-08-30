#!/usr/bin/env python3
"""
materialize.py - P2C Canonical Materializer
Transforms a reviewed local identity plan + canonical inventory + pinned upstream checkout
into a deterministic repository transaction.
"""

import argparse
import copy
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "tools" / "source_conversion" / "extractor"))
sys.path.insert(0, str(repo_root / "tools" / "source_conversion" / "generator"))
sys.path.insert(0, str(repo_root / "tools" / "source_conversion" / "validator"))

from tools.source_conversion.extractor.extract import dispatch_extraction
from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.planner import eligibility_planner
from tools.source_conversion.validator.validate_ir import validate_ir_data
from tools.source_conversion.validator.static_js_validator import validate_js_file
from tools.source_conversion.validator.validate_registry import (
    IndexDerivationError,
    inspect_final_js,
    validate_repository,
    write_index,
)

# --- Constants & Patterns ---
ARTIFACT_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
LOCAL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
UPDATE_VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
SOURCE_ID_RE = re.compile(r"^[0-9]+$")
PROJECT_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MODULE_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9]+)*$")
COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
MATERIALIZABLE_ELIGIBILITY = frozenset({"E1", "E2", "E3"})

class MaterializationError(Exception):
    pass

def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaterializationError(f"Failed to read JSON input {path}: {exc}") from exc

def write_json(path: Path, data: Any, indent: int = 4):
    with path.open("w", encoding="utf-8", newline="") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")

def check_path_traversal(value: str, field_name: str):
    if ".." in value or "/" in value or "\\" in value:
        raise MaterializationError(f"Path traversal detected in {field_name}: {value}")
    if os.path.isabs(value):
        raise MaterializationError(f"Absolute path detected in {field_name}: {value}")

def _parse_plan(plan_path: Path) -> dict:
    plan = load_json(plan_path)
    if not isinstance(plan, dict):
        raise MaterializationError("Plan root must be an object")

    allowed_top_level = {"schemaVersion", "upstream", "generatedTimestamp", "artifacts", "operation"}
    required_top_level = {"schemaVersion", "upstream", "generatedTimestamp", "artifacts"}
    missing_top_level = sorted(required_top_level - set(plan))
    if missing_top_level:
        raise MaterializationError(f"Missing top-level plan fields: {missing_top_level}")
    unknown_top_level = sorted(set(plan) - allowed_top_level)
    if unknown_top_level:
        raise MaterializationError(f"Unknown top-level field in plan: {unknown_top_level[0]}")

    if plan.get("schemaVersion") != "1":
        raise MaterializationError(f"Unsupported schemaVersion: {plan.get('schemaVersion')}")

    operation = plan.get("operation", "create")
    if operation not in ("create", "update"):
        raise MaterializationError(f"Unsupported operation: {operation}")

    upstream = plan["upstream"]
    if not isinstance(upstream, dict):
        raise MaterializationError("Plan upstream must be an object")

    allowed_upstream = {"project", "commit"}
    missing_upstream = sorted(allowed_upstream - set(upstream))
    if missing_upstream:
        raise MaterializationError(f"Missing upstream fields in plan: {missing_upstream}")
    unknown_upstream = sorted(set(upstream) - allowed_upstream)
    if unknown_upstream:
        raise MaterializationError(f"Unknown upstream field in plan: {unknown_upstream[0]}")

    project = upstream["project"]
    if not isinstance(project, str) or not PROJECT_RE.fullmatch(project):
        raise MaterializationError(f"Invalid upstream project: {project!r}")
    commit = upstream["commit"]
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise MaterializationError(f"Invalid upstream commit: {commit!r}")

    # Strict explicit UTC ISO-8601 timestamp validation
    ts_str = plan["generatedTimestamp"]
    if not isinstance(ts_str, str):
        raise MaterializationError("generatedTimestamp must be a string")
    # Require YYYY-MM-DDTHH:MM:SSZ
    ts_match = re.fullmatch(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts_str)
    if not ts_match:
        raise MaterializationError(f"generatedTimestamp must be in strict YYYY-MM-DDTHH:MM:SSZ format, got: {ts_str}")
    try:
        datetime.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        raise MaterializationError(f"Invalid timestamp date/time values: {ts_str}") from e

    artifacts = plan["artifacts"]
    if not isinstance(artifacts, list):
        raise MaterializationError("Plan artifacts must be a list")
    if not artifacts:
        raise MaterializationError("Plan artifacts must contain at least one artifact")

    seen_artifacts = set()
    seen_sources = set()

    if operation == "create":
        allowed_artifact_fields = {"sourceId", "artifactId", "providerId", "localVersion", "moduleAssert"}
        required_artifact_fields = {"sourceId", "artifactId", "providerId", "localVersion"}
    else:
        allowed_artifact_fields = {"sourceId", "artifactId", "providerId", "expectedCurrentLocalVersion", "newLocalVersion", "moduleAssert"}
        required_artifact_fields = {"sourceId", "artifactId", "providerId", "expectedCurrentLocalVersion", "newLocalVersion"}

    for position, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise MaterializationError(f"Plan artifact at position {position} must be an object")
        missing_artifact_fields = sorted(required_artifact_fields - set(item))
        if missing_artifact_fields:
            raise MaterializationError(
                f"Missing artifact fields at position {position}: {missing_artifact_fields}"
            )
        unknown_artifact_fields = sorted(set(item) - allowed_artifact_fields)
        if unknown_artifact_fields:
            raise MaterializationError(
                f"Unknown artifact field in plan: {unknown_artifact_fields[0]}"
            )

        source_id = item["sourceId"]
        artifact_id = item["artifactId"]
        provider_id = item["providerId"]

        if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
            raise MaterializationError(f"Invalid sourceId format: {source_id}")

        if not isinstance(artifact_id, str):
            raise MaterializationError(f"Invalid or missing artifactId: {artifact_id!r}")
        check_path_traversal(artifact_id, "artifactId")
        if not ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise MaterializationError(f"Invalid or missing artifactId: {artifact_id}")

        if not isinstance(provider_id, str):
            raise MaterializationError(f"Invalid or missing providerId: {provider_id!r}")
        check_path_traversal(provider_id, "providerId")
        if not ARTIFACT_ID_RE.fullmatch(provider_id):
            raise MaterializationError(f"Invalid or missing providerId: {provider_id}")

        if operation == "create":
            local_version = item["localVersion"]
            if not isinstance(local_version, str) or not LOCAL_VERSION_RE.fullmatch(local_version):
                raise MaterializationError(f"Invalid or missing localVersion: {local_version}")
        else:
            old_v = item["expectedCurrentLocalVersion"]
            new_v = item["newLocalVersion"]
            old_match = UPDATE_VERSION_RE.fullmatch(old_v) if isinstance(old_v, str) else None
            new_match = UPDATE_VERSION_RE.fullmatch(new_v) if isinstance(new_v, str) else None
            if old_match is None:
                raise MaterializationError(f"Invalid expectedCurrentLocalVersion: {old_v}")
            if new_match is None:
                raise MaterializationError(f"Invalid newLocalVersion: {new_v}")
            old_major, old_minor, old_patch = map(int, old_match.groups())
            new_major, new_minor, new_patch = map(int, new_match.groups())
            if (
                new_major != old_major
                or new_minor != old_minor
                or new_patch != old_patch + 1
            ):
                raise MaterializationError(
                    f"newLocalVersion {new_v} must be exactly the next patch after "
                    f"expectedCurrentLocalVersion {old_v}"
                )

        if "moduleAssert" in item:
            module_assert = item["moduleAssert"]
            if not isinstance(module_assert, str):
                raise MaterializationError("moduleAssert must be a string")
            check_path_traversal(module_assert, "moduleAssert")
            if not MODULE_RE.fullmatch(module_assert):
                raise MaterializationError(f"Invalid moduleAssert: {module_assert!r}")

        if artifact_id in seen_artifacts:
            raise MaterializationError(f"Duplicate artifactId in plan: {artifact_id}")
        seen_artifacts.add(artifact_id)

        if source_id in seen_sources:
            raise MaterializationError(f"Duplicate sourceId in plan: {source_id}")
        seen_sources.add(source_id)

    return plan

def _resolve_candidates(
    plan: Mapping[str, Any],
    inventory: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> dict:
    operation = plan.get("operation", "create")
    upstream_project = plan["upstream"]["project"]
    upstream_commit = plan["upstream"]["commit"]

    try:
        eligibility_report = eligibility_planner.build_plan(inventory, registry)
    except eligibility_planner.PlannerError as exc:
        raise MaterializationError(
            f"Canonical eligibility planner rejected inputs ({exc.code}): {exc}"
        ) from exc

    upstreams = [
        item
        for item in eligibility_report["upstreams"]
        if item["project"] == upstream_project
    ]
    if len(upstreams) != 1:
        raise MaterializationError(
            f"Project {upstream_project} resolves to {len(upstreams)} inventory snapshots"
        )
    if upstreams[0]["commit"] != upstream_commit:
        raise MaterializationError(
            f"Inventory commit {upstreams[0]['commit']} does not match plan commit {upstream_commit}"
        )

    candidates = inventory["candidates"]
    eligibility_by_identity = {
        (item["project"], item["sourceId"]): item
        for item in eligibility_report["candidates"]
    }
    resolved = {}

    for item in plan["artifacts"]:
        source_id = item["sourceId"]
        matches = [
            candidate
            for candidate in candidates
            if candidate["project"] == upstream_project
            and candidate["sourceId"] == source_id
        ]

        if not matches:
            raise MaterializationError(f"No inventory candidate found for sourceId {source_id}")
        if len(matches) > 1:
            raise MaterializationError(f"Multiple inventory candidates found for sourceId {source_id}")

        match = matches[0]

        planned = eligibility_by_identity.get((upstream_project, source_id))
        if planned is None:
            raise MaterializationError(
                f"Canonical eligibility planner omitted sourceId {source_id}"
            )
        allowed = MATERIALIZABLE_ELIGIBILITY | ({"E0"} if operation == "update" else set())
        if planned["eligibility"] not in allowed:
            raise MaterializationError(
                f"Candidate for sourceId {source_id} has ineligible canonical route "
                f"{planned['eligibility']}: {planned['reasonCodes']}"
            )
        if planned["patchState"] == "required":
            raise MaterializationError(
                f"Candidate for sourceId {source_id} requires a patch, unsupported in P2C v0.1"
            )

        if "moduleAssert" in item:
            if match.get("module") != item["moduleAssert"]:
                raise MaterializationError(f"moduleAssert failed for sourceId {source_id}: expected {item['moduleAssert']}, got {match.get('module')}")

        resolved[source_id] = match

    return resolved


def _check_preconditions(plan: dict, repo: Path, resolved: dict):
    operation = plan.get("operation", "create")
    if operation == "create":
        registry_path = repo / "sources_registry.json"
        if registry_path.exists():
            registry = load_json(registry_path)
            existing_artifacts = {a.get("artifactId") for a in registry.get("artifacts", []) if isinstance(a, dict)}
            for item in plan["artifacts"]:
                if item["artifactId"] in existing_artifacts:
                    raise MaterializationError(f"Collision: artifactId {item['artifactId']} already exists in registry")

        index_path = repo / "index.json"
        if index_path.exists():
            index = load_json(index_path)
            if not isinstance(index, list):
                raise MaterializationError("Existing index root must be an array")
            indexed_files = {
                entry.get("fileName") for entry in index if isinstance(entry, dict)
            }
            for item in plan["artifacts"]:
                file_name = f"{item['artifactId']}.js"
                if file_name in indexed_files:
                    raise MaterializationError(
                        f"Collision: index already contains fileName {file_name}"
                    )

        for item in plan["artifacts"]:
            aid = item["artifactId"]
            if (repo / f"{aid}.js").exists():
                raise MaterializationError(f"Collision: {aid}.js already exists in repository root")
            if (repo / "sources_ir" / f"{aid}.json").exists():
                raise MaterializationError(f"Collision: sources_ir/{aid}.json already exists")
            if (repo / "sources_generated" / f"{aid}.base.js").exists():
                raise MaterializationError(f"Collision: sources_generated/{aid}.base.js already exists")
            if (repo / "sources_patches" / f"{aid}.patch.js").exists():
                raise MaterializationError(f"Collision: sources_patches/{aid}.patch.js already exists")
    else:
        registry_path = repo / "sources_registry.json"
        if not registry_path.exists():
            raise MaterializationError("sources_registry.json missing for UPDATE")
        registry = load_json(registry_path)
        existing_artifacts = {a.get("artifactId"): a for a in registry.get("artifacts", []) if isinstance(a, dict)}

        index_path = repo / "index.json"
        if not index_path.exists():
            raise MaterializationError("index.json missing for UPDATE")
        index = load_json(index_path)
        indexed_files = {entry.get("fileName") for entry in index if isinstance(entry, dict)}

        for item in plan["artifacts"]:
            aid = item["artifactId"]
            if aid not in existing_artifacts:
                raise MaterializationError(f"UPDATE rejected: artifactId {aid} not in registry")
            reg_art = existing_artifacts[aid]

            if f"{aid}.js" not in indexed_files:
                raise MaterializationError(f"UPDATE rejected: {aid}.js not in index")

            if not (repo / f"{aid}.js").is_file():
                raise MaterializationError(f"UPDATE rejected: {aid}.js missing")
            if not (repo / "sources_ir" / f"{aid}.json").is_file():
                raise MaterializationError(f"UPDATE rejected: sources_ir/{aid}.json missing")
            if not (repo / "sources_generated" / f"{aid}.base.js").is_file():
                raise MaterializationError(f"UPDATE rejected: sources_generated/{aid}.base.js missing")
            if (repo / "sources_patches" / f"{aid}.patch.js").exists():
                raise MaterializationError(f"UPDATE rejected: patch-backed artifact not supported")

            if reg_art.get("providerId") != item["providerId"]:
                raise MaterializationError("UPDATE rejected: providerId mismatch")

            old_ir = load_json(repo / "sources_ir" / f"{aid}.json")
            expected_ver = item["expectedCurrentLocalVersion"]
            if old_ir.get("version") != expected_ver:
                raise MaterializationError(f"UPDATE rejected: stale expectedCurrentLocalVersion {expected_ver} != {old_ir.get('version')}")

            if old_ir.get("manualPatchRequired") is True:
                raise MaterializationError("UPDATE rejected: manualPatchRequired is true")

            if reg_art.get("implementation", {}).get("producer") != "generated":
                raise MaterializationError("UPDATE rejected: artifact is not generated")

            up = reg_art.get("upstream", {})
            if up.get("project") != plan["upstream"]["project"]:
                raise MaterializationError("UPDATE rejected: upstream project mismatch")
            if up.get("module") != resolved[item["sourceId"]]["module"]:
                raise MaterializationError("UPDATE rejected: upstream module mismatch")
            if up.get("sourceId") != str(item["sourceId"]):
                raise MaterializationError("UPDATE rejected: upstream sourceId mismatch")
            if up.get("commit") != plan["upstream"]["commit"]:
                raise MaterializationError("UPDATE rejected: upstream commit mismatch")

def _verify_extensions_checkout(
    extensions_root: Path,
    inventory: Mapping[str, Any],
    project: str,
    expected_commit: str,
):
    try:
        actual_commit = eligibility_planner.validate_upstream_checkout(
            extensions_root, inventory, project
        )
    except eligibility_planner.PlannerError as exc:
        raise MaterializationError(
            f"Extensions checkout attestation failed ({exc.code}): {exc}"
        ) from exc

    if actual_commit != expected_commit:
        raise MaterializationError(f"Extensions checkout HEAD ({actual_commit}) does not match expected ({expected_commit})")

def _extract_to_temp(item: dict, candidate: dict, timestamp: str, extensions_root: Path) -> dict:
    source_path = "/".join(candidate["module"].split("."))
    ir_data = dispatch_extraction(
        extensions_root=str(extensions_root),
        source_path=source_path,
        timestamp=timestamp,
        language_override=candidate.get("canonicalLocale"),
        source_id=item["sourceId"]
    )
    if not isinstance(ir_data, dict):
        raise MaterializationError("Canonical extraction dispatch did not return an IR object")

    ir_data["artifactId"] = item["artifactId"]
    ir_data["version"] = item.get("newLocalVersion", item.get("localVersion"))

    return ir_data

def _validate_extracted_identity(
    plan_item: Mapping[str, Any],
    candidate: Mapping[str, Any],
    ir_data: Mapping[str, Any],
    plan: Mapping[str, Any],
):
    provenance = ir_data.get("provenance")
    if not isinstance(provenance, dict):
        raise MaterializationError("Extracted IR has no authoritative provenance object")
    if provenance.get("upstreamCommit") != plan["upstream"]["commit"]:
        raise MaterializationError(
            "Extracted IR upstreamCommit does not match the attested checkout commit"
        )
    source_id = provenance.get("upstreamSourceId")
    if source_id is not None and str(source_id) != plan_item["sourceId"]:
        raise MaterializationError(
            f"Extracted IR sourceId {source_id!r} does not match planned sourceId "
            f"{plan_item['sourceId']}"
        )
    if provenance.get("generatedTimestamp") != plan["generatedTimestamp"]:
        raise MaterializationError(
            "Extracted IR generatedTimestamp does not match the reviewed plan"
        )
    candidate_version = candidate.get("version")
    if candidate_version is not None and provenance.get("upstreamVersion") != candidate_version:
        raise MaterializationError(
            f"Extracted upstreamVersion {provenance.get('upstreamVersion')!r} does not "
            f"match inventory version {candidate_version!r}"
        )
    candidate_warning = candidate.get("contentWarning")
    if candidate_warning is not None and ir_data.get("contentWarning") != candidate_warning:
        raise MaterializationError(
            "Extracted contentWarning does not match canonical inventory evidence"
        )
    candidate_locale = candidate.get("canonicalLocale")
    if candidate_locale is not None and ir_data.get("languages") != [candidate_locale]:
        raise MaterializationError(
            "Extracted languages do not match canonicalLocale inventory evidence"
        )

def _validate_ir(ir_data: dict):
    errors = validate_ir_data(ir_data)
    if errors:
        raise MaterializationError(f"IR validation failed: {errors}")

def _generate_base_js(ir_data: dict) -> str:
    js_code = generate_venera_js(ir_data)
    return js_code

def _has_manual_patch(data: Any) -> bool:
    if isinstance(data, dict):
        if data.get("manualPatchRequired") is True:
            return True
        for v in data.values():
            if _has_manual_patch(v):
                return True
    elif isinstance(data, list):
        for v in data:
            if _has_manual_patch(v):
                return True
    return False

def _compose_final_js(ir_data: dict, base_js_bytes: bytes) -> bytes:
    if _has_manual_patch(ir_data):
        raise MaterializationError(f"Source {ir_data.get('id')} requires manual patching which is unsupported in v0.1")
    return base_js_bytes

def _build_registry_record(
    plan_item: dict,
    candidate: dict,
    ir_data: dict,
    final_js_metadata: dict,
    plan: dict,
    expected_runtime_key: str | None = None,
) -> dict:
    for field in ("name", "languages", "baseUrl", "contentWarning", "sourceType"):
        if field not in ir_data:
            raise MaterializationError(f"Missing authoritative {field} in extracted IR")
    if not candidate.get("extensionLib"):
        raise MaterializationError("Missing authoritative extensionLib in inventory candidate")
    for field in ("name", "key", "version"):
        if not final_js_metadata.get(field):
            raise MaterializationError(f"Final JS is missing authoritative {field} metadata")
    if final_js_metadata["name"] != ir_data["name"]:
        raise MaterializationError("Final JS name does not match extracted IR name")
    expected_new = plan_item.get("newLocalVersion", plan_item.get("localVersion"))
    if final_js_metadata["version"] != expected_new:
        raise MaterializationError("Final JS version does not match planned localVersion")

    if (
        plan.get("operation", "create") == "update"
        and final_js_metadata["key"] != expected_runtime_key
    ):
        raise MaterializationError("UPDATE rejected: runtimeKey mismatch")

    record = {
        "artifactId": plan_item["artifactId"],
        "runtimeKey": final_js_metadata["key"],
        "catalogName": ir_data["name"],
        "locales": ir_data["languages"],
        "providerId": plan_item["providerId"],
        "siteUrl": ir_data["baseUrl"],
        "contentWarning": ir_data["contentWarning"],
    }

    record["implementation"] = {
        "producer": "generated",
        "transport": ir_data["sourceType"]
    }

    if "upstreamVersion" not in ir_data.get("provenance", {}):
        raise MaterializationError("Missing authoritative upstreamVersion in extracted provenance")

    upstream = {
        "project": plan["upstream"]["project"],
        "module": candidate["module"],
        "sourceId": str(plan_item["sourceId"]),
        "version": ir_data["provenance"]["upstreamVersion"],
    }
    upstream["extensionLib"] = candidate["extensionLib"]
    upstream["commit"] = plan["upstream"]["commit"]
    if "theme" in candidate:
        upstream["theme"] = candidate["theme"]
    record["upstream"] = upstream

    return record

def _build_proposed_registry(existing_registry: dict, new_records: list, operation: str) -> dict:
    proposed = copy.deepcopy(existing_registry)
    if "artifacts" not in proposed:
        proposed["artifacts"] = []
    if operation == "update":
        replacements = {record["artifactId"]: record for record in new_records}
        updated_artifacts = []
        replaced_ids = set()
        for existing in proposed["artifacts"]:
            artifact_id = existing.get("artifactId")
            replacement = replacements.get(artifact_id)
            if replacement is None:
                updated_artifacts.append(existing)
                continue
            merged = copy.deepcopy(existing)
            merged.update(copy.deepcopy(replacement))
            updated_artifacts.append(merged)
            replaced_ids.add(artifact_id)
        if replaced_ids != set(replacements):
            missing = sorted(set(replacements) - replaced_ids)
            raise MaterializationError(
                f"UPDATE rejected: registry entries disappeared during preparation: {missing}"
            )
        proposed["artifacts"] = updated_artifacts
    else:
        proposed["artifacts"].extend(new_records)
    return proposed

def _blocking_diagnostics(result) -> tuple:
    return result.errors + result.warnings

def _format_diagnostics(diagnostics) -> str:
    return "; ".join(
        f"{item.code} {item.subject}: {item.message}" for item in diagnostics
    )

def _validate_live_repository(repo: Path):
    result = validate_repository(repo)
    blocking = _blocking_diagnostics(result)
    if blocking:
        raise MaterializationError(
            f"Live repository validation failed: {_format_diagnostics(blocking)}"
        )

def _stage_existing_transaction_inputs(
    repo: Path,
    transaction_dir: Path,
    existing_registry: Mapping[str, Any],
):
    try:
        for artifact in existing_registry["artifacts"]:
            artifact_id = artifact["artifactId"]
            source = repo / f"{artifact_id}.js"
            destination = transaction_dir / f"{artifact_id}.js"
            if not destination.exists() and source.exists():
                shutil.copy2(source, destination)

        existing_ir_dir = repo / "sources_ir"
        if existing_ir_dir.is_dir():
            staged_ir_dir = transaction_dir / "sources_ir"
            staged_ir_dir.mkdir(parents=True, exist_ok=True)
            for source in sorted(existing_ir_dir.glob("*.json"), key=lambda path: path.name):
                destination = staged_ir_dir / source.name
                if not destination.exists() and source.exists():
                    shutil.copy2(source, destination)
    except OSError as exc:
        raise MaterializationError(
            f"Failed to stage existing canonical inputs for transaction validation: {exc}"
        ) from exc

def _validate_prepared_transaction(transaction_dir: Path):
    result = validate_repository(transaction_dir)
    blocking = _blocking_diagnostics(result)
    if blocking:
        raise MaterializationError(
            f"Proposed transaction linkage validation failed: "
            f"{_format_diagnostics(blocking)}"
        )

def _update_current_state_paths(plan: Mapping[str, Any]) -> list[str]:
    paths = {"index.json", "sources_registry.json"}
    for item in plan["artifacts"]:
        artifact_id = item["artifactId"]
        paths.update({
            f"{artifact_id}.js",
            f"sources_generated/{artifact_id}.base.js",
            f"sources_ir/{artifact_id}.json",
        })
    return sorted(paths)


def _update_current_state(
    plan: Mapping[str, Any], preflight: Mapping[str, Any] | None
) -> list[dict[str, str]]:
    if preflight is None:
        raise MaterializationError("UPDATE digest requires current-state hashes")
    current_state = []
    for relative_path in _update_current_state_paths(plan):
        sha256 = preflight.get(relative_path)
        if not isinstance(sha256, str):
            raise MaterializationError(
                f"UPDATE digest current-state input missing: {relative_path}"
            )
        current_state.append({"relativePath": relative_path, "sha256": sha256})
    return current_state


def _compute_digest(plan: dict, targets: list, preflight: dict = None) -> str:
    normalized_plan = {
        "schemaVersion": plan["schemaVersion"],
        "upstream": {
            "project": plan["upstream"]["project"],
            "commit": plan["upstream"]["commit"]
        },
        "generatedTimestamp": plan["generatedTimestamp"],
        "artifacts": []
    }
    if "operation" in plan:
        normalized_plan["operation"] = plan["operation"]
    for item in plan["artifacts"]:
        norm_item = {
            "sourceId": item["sourceId"],
            "artifactId": item["artifactId"],
            "providerId": item["providerId"],
        }
        if plan.get("operation", "create") == "create":
            norm_item["localVersion"] = item["localVersion"]
        else:
            norm_item["expectedCurrentLocalVersion"] = item["expectedCurrentLocalVersion"]
            norm_item["newLocalVersion"] = item["newLocalVersion"]
        if "moduleAssert" in item:
            norm_item["moduleAssert"] = item["moduleAssert"]
        normalized_plan["artifacts"].append(norm_item)

    if plan.get("operation", "create") == "update":
        normalized_plan["currentState"] = _update_current_state(plan, preflight)

    # Ensure artifacts are sorted for determinism
    normalized_plan["artifacts"].sort(key=lambda x: x["artifactId"])

    normalized_targets = []
    for t in targets:
        normalized_targets.append({
            "relativePath": t["relativePath"],
            "sha256": t["sha256"],
            "byteLength": t["byteLength"]
        })

    sorted_targets = sorted(normalized_targets, key=lambda x: x["relativePath"])
    payload = {
        "plan": normalized_plan,
        "targets": sorted_targets
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return hashlib.sha256(payload_bytes).hexdigest()

def _capture_preflight_fingerprint(repo: Path) -> dict:
    fingerprint = {
        "sources_registry.json": None,
        "index.json": None,
    }
    paths = [repo / "sources_registry.json", repo / "index.json"]
    paths.extend(sorted(repo.glob("*.js"), key=lambda path: path.name))
    ir_dir = repo / "sources_ir"
    if ir_dir.is_dir():
        paths.extend(sorted(ir_dir.glob("*.json"), key=lambda path: path.name))
    generated_dir = repo / "sources_generated"
    if generated_dir.is_dir():
        paths.extend(sorted(generated_dir.glob("*.base.js"), key=lambda path: path.name))

    for path in paths:
        relative = path.relative_to(repo).as_posix()
        if path.is_file():
            fingerprint[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprint

def _execute_pass(plan: dict, resolved: dict, extensions_root: Path, repo: Path, temp_dir: Path) -> dict:
    targets = []
    new_records = []
    operation = plan.get("operation", "create")

    existing_registry = {"schemaVersion": "1.0", "artifacts": []}
    reg_path = repo / "sources_registry.json"
    if reg_path.exists():
        existing_registry = load_json(reg_path)
    existing_by_artifact_id = {
        artifact.get("artifactId"): artifact
        for artifact in existing_registry.get("artifacts", [])
        if isinstance(artifact, dict)
    }

    for item in plan["artifacts"]:
        candidate = resolved[item["sourceId"]]
        ir_data = _extract_to_temp(item, candidate, plan["generatedTimestamp"], extensions_root)
        _validate_extracted_identity(item, candidate, ir_data, plan)
        _validate_ir(ir_data)

        ir_path = temp_dir / "sources_ir" / f"{item['artifactId']}.json"
        ir_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(ir_path, ir_data, indent=2)
        targets.append({
            "relativePath": f"sources_ir/{item['artifactId']}.json",
            "sourcePath": ir_path,
            "sha256": hashlib.sha256(ir_path.read_bytes()).hexdigest(),
            "byteLength": ir_path.stat().st_size
        })

        base_js = _generate_base_js(ir_data)
        base_js_path = temp_dir / "sources_generated" / f"{item['artifactId']}.base.js"
        base_js_path.parent.mkdir(parents=True, exist_ok=True)
        base_js_path.write_text(base_js, encoding="utf-8")

        if not validate_js_file(str(base_js_path), phase="base"):
            raise MaterializationError(f"Base JS validation failed for {item['artifactId']}")

        targets.append({
            "relativePath": f"sources_generated/{item['artifactId']}.base.js",
            "sourcePath": base_js_path,
            "sha256": hashlib.sha256(base_js_path.read_bytes()).hexdigest(),
            "byteLength": base_js_path.stat().st_size
        })

        final_js_bytes = _compose_final_js(ir_data, base_js_path.read_bytes())
        final_js_path = temp_dir / f"{item['artifactId']}.js"
        final_js_path.parent.mkdir(parents=True, exist_ok=True)
        final_js_path.write_bytes(final_js_bytes)

        if not validate_js_file(str(final_js_path), phase="final"):
            raise MaterializationError(f"Final JS validation failed for {item['artifactId']}")

        targets.append({
            "relativePath": f"{item['artifactId']}.js",
            "sourcePath": final_js_path,
            "sha256": hashlib.sha256(final_js_bytes).hexdigest(),
            "byteLength": final_js_path.stat().st_size
        })

        final_js_metadata = inspect_final_js(final_js_path)

        existing_record = existing_by_artifact_id.get(item["artifactId"], {})
        expected_runtime_key = (
            existing_record.get("runtimeKey")
            if operation == "update"
            else None
        )
        record = _build_registry_record(
            item,
            candidate,
            ir_data,
            final_js_metadata,
            plan,
            expected_runtime_key,
        )
        new_records.append(record)

    proposed_registry = _build_proposed_registry(existing_registry, new_records, operation)
    registry_path = temp_dir / "sources_registry.json"
    write_json(registry_path, proposed_registry, indent=2)
    if operation == "create":
        targets.append({
            "relativePath": "sources_registry.json",
            "sourcePath": registry_path,
            "sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
            "byteLength": registry_path.stat().st_size
        })

    _stage_existing_transaction_inputs(repo, temp_dir, existing_registry)
    try:
        proposed_index = write_index(temp_dir)
    except IndexDerivationError as exc:
        raise MaterializationError(
            f"Canonical proposed index derivation failed: {exc}"
        ) from exc
    index_path = temp_dir / "index.json"
    targets.append({
        "relativePath": "index.json",
        "sourcePath": index_path,
        "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "byteLength": index_path.stat().st_size
    })

    _validate_prepared_transaction(temp_dir)

    return {
        "targets": targets,
        "proposed_registry": proposed_registry,
        "proposed_index": proposed_index
    }

def _artifact_target_paths(plan: Mapping[str, Any]) -> list[str]:
    paths = []
    for item in plan["artifacts"]:
        aid = item["artifactId"]
        paths.extend(
            (
                f"sources_ir/{aid}.json",
                f"sources_generated/{aid}.base.js",
                f"{aid}.js",
            )
        )
    return paths

def _assert_new_targets_absent(repo: Path, artifact_targets: Sequence[str], operation: str):
    if operation == "update":
        return
    for relative_path in artifact_targets:
        if (repo / relative_path).exists():
            raise MaterializationError(
                f"Stale-state guard failed: {relative_path} appeared before promotion."
            )

def _verify_prepared_target_manifest(
    transaction_dir: Path,
    plan: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]],
):
    expected_paths = set(_artifact_target_paths(plan)) | {"index.json"}
    if plan.get("operation", "create") == "create":
        expected_paths.add("sources_registry.json")
    targets_by_path = {target["relativePath"]: target for target in targets}
    if set(targets_by_path) != expected_paths or len(targets_by_path) != len(targets):
        raise MaterializationError("Prepared target manifest is incomplete or contains duplicates")

    for relative_path in sorted(expected_paths):
        source_path = transaction_dir / relative_path
        if not source_path.is_file():
            raise MaterializationError(
                f"Prepared transaction target is missing: {relative_path}"
            )
        payload = source_path.read_bytes()
        target = targets_by_path[relative_path]
        if len(payload) != target["byteLength"]:
            raise MaterializationError(
                f"Prepared transaction target length changed: {relative_path}"
            )
        if hashlib.sha256(payload).hexdigest() != target["sha256"]:
            raise MaterializationError(
                f"Prepared transaction target digest changed: {relative_path}"
            )

def _restore_bytes_atomically(path: Path, payload: bytes | None):
    if payload is None:
        path.unlink(missing_ok=True)
        return

    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".rollback.tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _replace_prepared_sibling(source: Path, destination: Path):
    os.replace(source, destination)

def _promote_transaction(
    repo: Path,
    transaction_dir: Path,
    plan: Mapping[str, Any],
    preflight_fingerprint: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]],
):
    _verify_prepared_target_manifest(transaction_dir, plan, targets)

    current_fingerprint = _capture_preflight_fingerprint(repo)
    if current_fingerprint != preflight_fingerprint:
        raise MaterializationError(
            "Stale-state guard failed: canonical live state changed before promotion."
        )

    operation = plan.get("operation", "create")
    artifact_targets = _artifact_target_paths(plan)
    shared_targets = (
        ("sources_registry.json", "index.json")
        if operation == "create"
        else ("index.json",)
    )
    _assert_new_targets_absent(repo, artifact_targets, operation)

    original_shared = {
        repo / relative_path: (
            (repo / relative_path).read_bytes()
            if (repo / relative_path).exists()
            else None
        )
        for relative_path in shared_targets
    }
    if operation == "update":
        for p in artifact_targets:
            dest = repo / p
            original_shared[dest] = dest.read_bytes() if dest.exists() else None

    prepared_siblings: dict[Path, Path] = {}
    published_artifacts: list[Path] = []
    promoted_shared: list[Path] = []
    created_directories = []

    try:
        for relative_path in (*artifact_targets, *shared_targets):
            source_path = transaction_dir / relative_path
            destination = repo / relative_path
            if not destination.parent.exists():
                try:
                    destination.parent.mkdir(parents=True, exist_ok=False)
                except FileExistsError:
                    pass
                else:
                    created_directories.append(destination.parent)

            descriptor, sibling_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
            )
            os.close(descriptor)
            sibling = Path(sibling_name)
            prepared_siblings[destination] = sibling
            shutil.copy2(source_path, sibling)
            if sibling.read_bytes() != source_path.read_bytes():
                raise MaterializationError(
                    f"Temporary publication copy mismatch: {relative_path}"
                )

        # This is the last complete live-state check before any target is published.
        if _capture_preflight_fingerprint(repo) != preflight_fingerprint:
            raise MaterializationError(
                "Stale-state guard failed: canonical live state changed during preparation."
            )
        _assert_new_targets_absent(repo, artifact_targets, operation)

        # Hard-linking a fully prepared sibling provides atomic CREATE without
        # overwriting a destination that appears concurrently.
        for relative_path in artifact_targets:
            destination = repo / relative_path
            sibling = prepared_siblings[destination]
            if operation == "update":
                _replace_prepared_sibling(sibling, destination)
            else:
                os.link(sibling, destination)
                sibling.unlink()
            published_artifacts.append(destination)
            del prepared_siblings[destination]

        # Shared commit-state files are atomically replaced last.
        for relative_path in shared_targets:
            destination = repo / relative_path
            sibling = prepared_siblings[destination]
            _replace_prepared_sibling(sibling, destination)
            promoted_shared.append(destination)
            del prepared_siblings[destination]

    except Exception as exc:
        rollback_errors = []

        for path in reversed(published_artifacts):
            try:
                if operation == "update":
                    _restore_bytes_atomically(path, original_shared.get(path))
                else:
                    path.unlink(missing_ok=True)
            except OSError as rollback_exc:
                rollback_errors.append(f"remove/restore {path}: {rollback_exc}")

        for path in reversed(promoted_shared):
            try:
                _restore_bytes_atomically(path, original_shared[path])
            except OSError as rollback_exc:
                rollback_errors.append(f"restore {path}: {rollback_exc}")

        for path in tuple(prepared_siblings.values()):
            try:
                path.unlink(missing_ok=True)
            except OSError as rollback_exc:
                rollback_errors.append(f"remove {path}: {rollback_exc}")

        for p in reversed(created_directories):
            try:
                p.rmdir()
            except OSError:
                pass

        if rollback_errors:
            raise MaterializationError(
                f"Promotion failed ({exc}); rollback incomplete: {rollback_errors}"
            ) from exc
        raise MaterializationError(
            f"Promotion failed, rollback successful: {exc}"
        ) from exc

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2C Canonical Materializer")
    parser.add_argument("--mode", choices=["check", "write"], required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--extensions-root", type=Path, required=True)
    parser.add_argument("--expected-digest", type=str, help="Expected transaction digest (required for UPDATE write)")

    args = parser.parse_args(argv)

    try:
        plan = _parse_plan(args.plan)
        inventory_path = args.repo_root / "tools" / "source_conversion" / "inventory" / "upstream_inventory.json"
        inventory = load_json(inventory_path)
        registry = load_json(args.repo_root / "sources_registry.json")

        _validate_live_repository(args.repo_root)
        resolved = _resolve_candidates(plan, inventory, registry)
        _verify_extensions_checkout(
            args.extensions_root,
            inventory,
            plan["upstream"]["project"],
            plan["upstream"]["commit"],
        )
        _check_preconditions(plan, args.repo_root, resolved)
        preflight_fingerprint = _capture_preflight_fingerprint(args.repo_root)

        with tempfile.TemporaryDirectory() as td:
            # Determinism Pass 1
            pass1_dir = Path(td) / "pass1"
            pass1_dir.mkdir()
            res1 = _execute_pass(plan, resolved, args.extensions_root, args.repo_root, pass1_dir)

            # Determinism Pass 2
            pass2_dir = Path(td) / "pass2"
            pass2_dir.mkdir()
            res2 = _execute_pass(plan, resolved, args.extensions_root, args.repo_root, pass2_dir)

            # Verify determinism
            t1 = {t["relativePath"]: t for t in res1["targets"]}
            t2 = {t["relativePath"]: t for t in res2["targets"]}

            if set(t1.keys()) != set(t2.keys()):
                raise MaterializationError("Determinism failed: Output files differ between passes")

            for path in t1:
                if t1[path]["sha256"] != t2[path]["sha256"]:
                    raise MaterializationError(f"Determinism failed: {path} hash differs between passes")

            # Re-attest both external inputs after preparation so CHECK reports
            # and WRITE promotion are bound to the same live/upstream state.
            _verify_extensions_checkout(
                args.extensions_root,
                inventory,
                plan["upstream"]["project"],
                plan["upstream"]["commit"],
            )
            if _capture_preflight_fingerprint(args.repo_root) != preflight_fingerprint:
                raise MaterializationError(
                    "Stale-state guard failed: canonical live state changed during preparation."
                )

            targets_no_local_path = []
            for t in res1["targets"]:
                targets_no_local_path.append({
                    "relativePath": t["relativePath"],
                    "sha256": t["sha256"],
                    "byteLength": t["byteLength"]
                })

            digest = _compute_digest(plan, targets_no_local_path, preflight_fingerprint)

            report = {
                "mode": args.mode,
                "operation": plan.get("operation", "create"),
                "upstreamProject": plan["upstream"]["project"],
                "upstreamCommit": plan["upstream"]["commit"],
                "generatedTimestamp": plan["generatedTimestamp"],
                "transactionDigest": digest,
                "artifacts": plan["artifacts"],
                "targets": targets_no_local_path,
                "validation": "PASS",
                "determinism": "PASS"
            }
            if plan.get("operation", "create") == "update":
                report["currentState"] = _update_current_state(
                    plan, preflight_fingerprint
                )

            if args.mode == "write":
                if plan.get("operation", "create") == "update":
                    if not args.expected_digest:
                        raise MaterializationError("UPDATE write mode requires --expected-digest")
                    if args.expected_digest != digest:
                        raise MaterializationError(f"UPDATE rejected: expected digest {args.expected_digest} does not match computed {digest}")

                _promote_transaction(
                    args.repo_root,
                    pass1_dir,
                    plan,
                    preflight_fingerprint,
                    res1["targets"],
                )
                print(f"[+] Wrote {len(res1['targets'])} files.")

            print(json.dumps(report, indent=2))
            return 0

    except MaterializationError as e:
        print(f"[!] ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
