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
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "tools" / "source_conversion" / "extractor"))
sys.path.insert(0, str(repo_root / "tools" / "source_conversion" / "generator"))
sys.path.insert(0, str(repo_root / "tools" / "source_conversion" / "validator"))

from tools.source_conversion.extractor.common import gradle_parser
from tools.source_conversion.extractor.extract import dispatch_extraction
from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.validator.validate_ir import validate_ir_data
from tools.source_conversion.validator.static_js_validator import validate_js_file
from tools.source_conversion.validator.validate_registry import validate_registry_data, _derive_index_entries, inspect_final_js

# --- Constants & Patterns ---
ARTIFACT_ID_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
LOCAL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SOURCE_ID_RE = re.compile(r"^[0-9]+$")

class MaterializationError(Exception):
    pass

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def write_json(path: Path, data: Any, indent: int = 4):
    with path.open("w", encoding="utf-8", newline="") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")

def check_path_traversal(value: str, field_name: str):
    if not isinstance(value, str):
        return
    if ".." in value or "/" in value or "\\" in value:
        raise MaterializationError(f"Path traversal detected in {field_name}: {value}")
    if os.path.isabs(value):
        raise MaterializationError(f"Absolute path detected in {field_name}: {value}")

def _parse_plan(plan_path: Path) -> dict:
    plan = load_json(plan_path)
    if plan.get("schemaVersion") != "1":
        raise MaterializationError(f"Unsupported schemaVersion: {plan.get('schemaVersion')}")

    # Strict validation of unknown fields at top level
    allowed_top_level = {"schemaVersion", "upstream", "generatedTimestamp", "artifacts"}
    for k in plan:
        if k not in allowed_top_level:
            raise MaterializationError(f"Unknown top-level field in plan: {k}")

    if "upstream" not in plan or "project" not in plan["upstream"] or "commit" not in plan["upstream"]:
        raise MaterializationError("Plan must contain upstream.project and upstream.commit")

    allowed_upstream = {"project", "commit"}
    for k in plan["upstream"]:
        if k not in allowed_upstream:
            raise MaterializationError(f"Unknown upstream field in plan: {k}")

    if "generatedTimestamp" not in plan:
        raise MaterializationError("Plan must contain generatedTimestamp")

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

    artifacts = plan.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise MaterializationError("Plan artifacts must be a list")

    seen_artifacts = set()
    seen_sources = set()

    allowed_artifact_fields = {"sourceId", "artifactId", "providerId", "localVersion", "moduleAssert"}

    for item in artifacts:
        for k in item:
            if k not in allowed_artifact_fields:
                raise MaterializationError(f"Unknown artifact field in plan: {k}")

        source_id = item.get("sourceId")
        artifact_id = item.get("artifactId")
        provider_id = item.get("providerId")
        local_version = item.get("localVersion")

        if not source_id or not str(source_id).strip():
            raise MaterializationError("Missing sourceId in plan artifact")
        source_id = str(source_id)
        if not SOURCE_ID_RE.fullmatch(source_id):
            raise MaterializationError(f"Invalid sourceId format: {source_id}")

        if not artifact_id or not ARTIFACT_ID_RE.fullmatch(artifact_id):
            raise MaterializationError(f"Invalid or missing artifactId: {artifact_id}")

        if not provider_id or not ARTIFACT_ID_RE.fullmatch(provider_id):
            raise MaterializationError(f"Invalid or missing providerId: {provider_id}")

        if not local_version or not LOCAL_VERSION_RE.fullmatch(local_version):
            raise MaterializationError(f"Invalid or missing localVersion: {local_version}")

        check_path_traversal(artifact_id, "artifactId")
        check_path_traversal(provider_id, "providerId")

        if artifact_id in seen_artifacts:
            raise MaterializationError(f"Duplicate artifactId in plan: {artifact_id}")
        seen_artifacts.add(artifact_id)

        if source_id in seen_sources:
            raise MaterializationError(f"Duplicate sourceId in plan: {source_id}")
        seen_sources.add(source_id)

        item["sourceId"] = source_id # ensure string

    return plan

def _resolve_candidates(plan: dict, inventory_path: Path) -> dict:
    inventory = load_json(inventory_path)

    upstream_project = plan["upstream"]["project"]
    upstream_commit = plan["upstream"]["commit"]

    found_upstream = False
    for up in inventory.get("upstreams", []):
        if up.get("project") == upstream_project:
            if up.get("commit") != upstream_commit:
                raise MaterializationError(f"Inventory commit {up.get('commit')} does not match plan commit {upstream_commit}")
            found_upstream = True
            break

    if not found_upstream:
        raise MaterializationError(f"Project {upstream_project} not found in inventory upstreams")

    candidates = inventory.get("candidates", [])
    resolved = {}

    for item in plan["artifacts"]:
        source_id = item["sourceId"]
        matches = [c for c in candidates if c.get("project") == upstream_project and str(c.get("sourceId")) == source_id]

        if not matches:
            raise MaterializationError(f"No inventory candidate found for sourceId {source_id}")
        if len(matches) > 1:
            raise MaterializationError(f"Multiple inventory candidates found for sourceId {source_id}")

        match = matches[0]

        # Enforce COMPATIBLE boundary
        if match.get("compatibility") != "COMPATIBLE":
            raise MaterializationError(f"Candidate for sourceId {source_id} is not COMPATIBLE: {match.get('compatibility')}")

        if "moduleAssert" in item and item["moduleAssert"]:
            if match.get("module") != item["moduleAssert"]:
                raise MaterializationError(f"moduleAssert failed for sourceId {source_id}: expected {item['moduleAssert']}, got {match.get('module')}")

        resolved[source_id] = match

    return resolved

def _check_collisions(plan: dict, repo: Path):
    registry_path = repo / "sources_registry.json"
    if registry_path.exists():
        registry = load_json(registry_path)
        existing_artifacts = {a.get("artifactId") for a in registry.get("artifacts", []) if isinstance(a, dict)}
        for item in plan["artifacts"]:
            if item["artifactId"] in existing_artifacts:
                raise MaterializationError(f"Collision: artifactId {item['artifactId']} already exists in registry")

    for item in plan["artifacts"]:
        aid = item["artifactId"]
        if (repo / f"{aid}.js").exists():
            raise MaterializationError(f"Collision: {aid}.js already exists in repository root")
        if (repo / "sources_ir" / f"{aid}.json").exists():
            raise MaterializationError(f"Collision: sources_ir/{aid}.json already exists")
        if (repo / "sources_generated" / f"{aid}.base.js").exists():
            raise MaterializationError(f"Collision: sources_generated/{aid}.base.js already exists")

def _verify_extensions_checkout(extensions_root: Path, expected_commit: str):
    try:
        actual_commit = subprocess.check_output(
            ["git", "-C", str(extensions_root), "rev-parse", "HEAD"], text=True
        ).strip()
    except subprocess.CalledProcessError as e:
        raise MaterializationError(f"Failed to query extensions checkout HEAD: {e}")

    if actual_commit != expected_commit:
        raise MaterializationError(f"Extensions checkout HEAD ({actual_commit}) does not match expected ({expected_commit})")

    try:
        status = subprocess.check_output(
            ["git", "-C", str(extensions_root), "status", "--porcelain"], text=True
        )
        if status.strip():
            raise MaterializationError(f"Extensions checkout is dirty. Clean state required.")
    except subprocess.CalledProcessError as e:
        raise MaterializationError(f"Failed to query extensions checkout status: {e}")

def _extract_to_temp(item: dict, candidate: dict, timestamp: str, extensions_root: Path) -> dict:
    source_path = candidate["module"]
    ir_data = dispatch_extraction(
        extensions_root=str(extensions_root),
        source_path=source_path,
        timestamp=timestamp,
        language_override=candidate.get("canonicalLocale"),
        source_id=item["sourceId"]
    )

    ir_data["artifactId"] = item["artifactId"]
    ir_data["version"] = item["localVersion"]

    return ir_data

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

def _build_registry_record(plan_item: dict, candidate: dict, ir_data: dict, final_js_metadata: dict, plan: dict) -> dict:
    record = {
        "artifactId": plan_item["artifactId"],
        "runtimeKey": final_js_metadata["key"],
    }

    # Deriving fields authoritatively
    # ir_data represents the canonical extracted source config
    if "name" in ir_data:
        record["catalogName"] = ir_data["name"]
    elif "name" in candidate:
        record["catalogName"] = candidate["name"]
    else:
        raise MaterializationError("Missing authoritative catalogName")

    if "languages" in ir_data and ir_data["languages"]:
        record["locales"] = ir_data["languages"]

    record["providerId"] = plan_item["providerId"]

    if "baseUrl" in ir_data:
        record["siteUrl"] = ir_data["baseUrl"]

    if "contentWarning" in candidate:
        record["contentWarning"] = candidate["contentWarning"]
    elif "contentWarning" in ir_data:
        record["contentWarning"] = ir_data["contentWarning"]

    if "sourceType" not in ir_data:
        raise MaterializationError("Missing authoritative sourceType in extracted IR")

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
    if "extensionLib" in candidate:
        upstream["extensionLib"] = candidate["extensionLib"]
    upstream["commit"] = plan["upstream"]["commit"]
    if "theme" in candidate:
        upstream["theme"] = candidate["theme"]
    record["upstream"] = upstream

    return record

def _build_proposed_registry(existing_registry: dict, new_records: list) -> dict:
    proposed = copy.deepcopy(existing_registry)
    if "artifacts" not in proposed:
        proposed["artifacts"] = []
    proposed["artifacts"].extend(new_records)

    return proposed

def _derive_proposed_index(proposed_registry: dict, inspected_metadata: dict) -> list:
    artifacts = [item for item in proposed_registry.get("artifacts", []) if isinstance(item, dict)]
    entries = _derive_index_entries(artifacts, inspected_metadata)
    if entries is None:
        raise MaterializationError("Proposed index derivation failed")
    return entries

def _compute_digest(plan: dict, targets: list) -> str:
    normalized_plan = {
        "schemaVersion": plan["schemaVersion"],
        "upstream": {
            "project": plan["upstream"]["project"],
            "commit": plan["upstream"]["commit"]
        },
        "generatedTimestamp": plan["generatedTimestamp"],
        "artifacts": []
    }
    for item in plan["artifacts"]:
        norm_item = {
            "sourceId": item["sourceId"],
            "artifactId": item["artifactId"],
            "providerId": item["providerId"],
            "localVersion": item["localVersion"]
        }
        if "moduleAssert" in item:
            norm_item["moduleAssert"] = item["moduleAssert"]
        normalized_plan["artifacts"].append(norm_item)

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
    fingerprint = {}
    reg_path = repo / "sources_registry.json"
    if reg_path.exists():
        fingerprint["registry"] = hashlib.sha256(reg_path.read_bytes()).hexdigest()
    else:
        fingerprint["registry"] = None

    idx_path = repo / "index.json"
    if idx_path.exists():
        fingerprint["index"] = hashlib.sha256(idx_path.read_bytes()).hexdigest()
    else:
        fingerprint["index"] = None
    return fingerprint

def _execute_pass(plan: dict, resolved: dict, extensions_root: Path, repo: Path, temp_dir: Path) -> dict:
    targets = []
    inspected = {}
    new_records = []

    existing_registry = {"schemaVersion": "1.0", "artifacts": []}
    reg_path = repo / "sources_registry.json"
    if reg_path.exists():
        existing_registry = load_json(reg_path)

    existing_artifacts = [item for item in existing_registry.get("artifacts", []) if isinstance(item, dict)]

    # Read existing final JS files to resolve index derivation
    for art in existing_artifacts:
        aid = art.get("artifactId")
        js_path = repo / f"{aid}.js"
        if js_path.exists():
            inspected[aid] = inspect_final_js(js_path)

    for item in plan["artifacts"]:
        candidate = resolved[item["sourceId"]]
        ir_data = _extract_to_temp(item, candidate, plan["generatedTimestamp"], extensions_root)
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
        inspected[item["artifactId"]] = final_js_metadata

        record = _build_registry_record(item, candidate, ir_data, final_js_metadata, plan)
        new_records.append(record)

    proposed_registry = _build_proposed_registry(existing_registry, new_records)
    registry_path = temp_dir / "sources_registry.json"
    write_json(registry_path, proposed_registry, indent=2)
    targets.append({
        "relativePath": "sources_registry.json",
        "sourcePath": registry_path,
        "sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
        "byteLength": registry_path.stat().st_size
    })

    proposed_index = _derive_proposed_index(proposed_registry, inspected)
    index_path = temp_dir / "index.json"
    write_json(index_path, proposed_index, indent=4)
    targets.append({
        "relativePath": "index.json",
        "sourcePath": index_path,
        "sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "byteLength": index_path.stat().st_size
    })

    return {
        "targets": targets,
        "proposed_registry": proposed_registry,
        "proposed_index": proposed_index
    }

def _promote_transaction(repo: Path, transaction_dir: Path, plan: dict, preflight_fingerprint: dict):
    # Stale-state guard
    current_fingerprint = _capture_preflight_fingerprint(repo)
    if current_fingerprint != preflight_fingerprint:
        raise MaterializationError("Stale-state guard failed: registry or index changed before promotion.")

    for item in plan["artifacts"]:
        aid = item["artifactId"]
        if (repo / f"{aid}.js").exists():
            raise MaterializationError(f"Stale-state guard failed: {aid}.js appeared before promotion.")
        if (repo / "sources_ir" / f"{aid}.json").exists():
            raise MaterializationError(f"Stale-state guard failed: sources_ir/{aid}.json appeared before promotion.")
        if (repo / "sources_generated" / f"{aid}.base.js").exists():
            raise MaterializationError(f"Stale-state guard failed: sources_generated/{aid}.base.js appeared before promotion.")

    registry_target = transaction_dir / "sources_registry.json"
    index_target = transaction_dir / "index.json"

    if not registry_target.exists() or not index_target.exists():
        raise MaterializationError("Missing registry or index in prepared transaction")

    registry_live = repo / "sources_registry.json"
    index_live = repo / "index.json"

    orig_registry_bytes = registry_live.read_bytes() if registry_live.exists() else None
    orig_index_bytes = index_live.read_bytes() if index_live.exists() else None

    # 1. new artifact files
    # 2. shared registry/index commit-state files LAST

    # Target relatives (excluding registry/index)
    artifact_targets = []
    for item in plan["artifacts"]:
        aid = item["artifactId"]
        artifact_targets.append(f"sources_ir/{aid}.json")
        artifact_targets.append(f"sources_generated/{aid}.base.js")
        artifact_targets.append(f"{aid}.js")

    created_siblings = []
    created_final_paths = []
    created_directories = []

    try:
        # Create temporary siblings on the SAME filesystem and os.replace
        for rel_path in artifact_targets:
            source_path = transaction_dir / rel_path
            dest_path = repo / rel_path
            sibling_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

            if not dest_path.parent.exists():
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if dest_path.parent not in created_directories:
                    created_directories.append(dest_path.parent)

            shutil.copy2(source_path, sibling_path)
            created_siblings.append(sibling_path)

        for rel_path in ["sources_registry.json", "index.json"]:
            source_path = transaction_dir / rel_path
            dest_path = repo / rel_path
            sibling_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

            if not dest_path.parent.exists():
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                if dest_path.parent not in created_directories:
                    created_directories.append(dest_path.parent)

            shutil.copy2(source_path, sibling_path)
            created_siblings.append(sibling_path)

        # Atomic promotion phase
        # New artifact files first
        for rel_path in artifact_targets:
            dest_path = repo / rel_path
            sibling_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
            os.replace(sibling_path, dest_path)
            created_siblings.remove(sibling_path)
            created_final_paths.append(dest_path)

        # Shared files last
        for rel_path in ["sources_registry.json", "index.json"]:
            dest_path = repo / rel_path
            sibling_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
            os.replace(sibling_path, dest_path)
            created_siblings.remove(sibling_path)
            created_final_paths.append(dest_path)

    except Exception as e:
        # Rollback
        if orig_registry_bytes is not None:
            # write temporary then atomic replace to avoid partial registry
            r_tmp = registry_live.with_suffix(".tmp.rollback")
            r_tmp.write_bytes(orig_registry_bytes)
            os.replace(r_tmp, registry_live)
        else:
            if registry_live.exists(): registry_live.unlink()

        if orig_index_bytes is not None:
            i_tmp = index_live.with_suffix(".tmp.rollback")
            i_tmp.write_bytes(orig_index_bytes)
            os.replace(i_tmp, index_live)
        else:
            if index_live.exists(): index_live.unlink()

        # Remove every transaction-created published file
        for path in created_final_paths:
            if path.exists():
                path.unlink()

        # Remove every transaction-owned temporary sibling
        for path in created_siblings:
            if path.exists():
                path.unlink()

        # Best-effort remove empty directories created by this transaction
        for p in reversed(created_directories):
            try:
                p.rmdir()
            except OSError:
                pass

        raise MaterializationError(f"Promotion failed, rollback successful: {e}")

class TransactionContext:
    def __init__(self, repo: Path, temp_dir: str):
        self.repo = repo
        self.temp_dir = temp_dir
        self.preflight_fingerprint = _capture_preflight_fingerprint(repo)

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2C Canonical Materializer")
    parser.add_argument("--mode", choices=["check", "write"], required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--extensions-root", type=Path, required=True)

    args = parser.parse_args(argv)

    try:
        plan = _parse_plan(args.plan)
        inventory_path = args.repo_root / "tools" / "source_conversion" / "inventory" / "upstream_inventory.json"

        # Verify extensions checkout provenance BEFORE extracting
        _verify_extensions_checkout(args.extensions_root, plan["upstream"]["commit"])

        resolved = _resolve_candidates(plan, inventory_path)
        _check_collisions(plan, args.repo_root)

        with tempfile.TemporaryDirectory() as td:
            ctx = TransactionContext(args.repo_root, td)

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

            # Full Linkage Validation of the prepared transaction
            from tools.source_conversion.validator.validate_registry import _validate_runtime_artifacts, _validate_ir_linkage

            val = validate_registry_data(res1["proposed_registry"])
            diagnostics = list(val.diagnostics)

            if val.errors:
                raise MaterializationError(f"Proposed transaction schema validation failed: {val.errors}")

            artifacts = [item for item in res1["proposed_registry"].get("artifacts", []) if isinstance(item, dict)]
            artifacts_by_id = {
                item["artifactId"]: item
                for item in artifacts
                if isinstance(item.get("artifactId"), str)
            }

            _validate_runtime_artifacts(diagnostics, pass1_dir, artifacts)
            _validate_ir_linkage(diagnostics, pass1_dir, artifacts_by_id)

            linkage_errors = [d for d in diagnostics if d.severity == "ERROR"]
            if linkage_errors:
                raise MaterializationError(f"Proposed transaction linkage validation failed: {linkage_errors}")

            targets_no_local_path = []
            for t in res1["targets"]:
                targets_no_local_path.append({
                    "relativePath": t["relativePath"],
                    "sha256": t["sha256"],
                    "byteLength": t["byteLength"]
                })

            digest = _compute_digest(plan, targets_no_local_path)

            report = {
                "mode": args.mode,
                "upstreamProject": plan["upstream"]["project"],
                "upstreamCommit": plan["upstream"]["commit"],
                "generatedTimestamp": plan["generatedTimestamp"],
                "transactionDigest": digest,
                "artifacts": plan["artifacts"],
                "targets": targets_no_local_path,
                "validation": "PASS",
                "determinism": "PASS"
            }

            if args.mode == "write":
                _promote_transaction(args.repo_root, pass1_dir, plan, ctx.preflight_fingerprint)
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
