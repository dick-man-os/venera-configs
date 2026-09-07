"""Selection and local publication evidence for the canonical eligibility report.

Unpublished local identities remain unresolved until an explicit materializer
plan is reviewed. This module never writes source or transaction files.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path

from tools.source_conversion.extractor.common.locales import candidate_locale, locale_matches, normalize_locale
from tools.source_conversion.extractor.common.dispatch_rules import adapter_for_candidate, THEME_ADAPTERS
from tools.source_conversion.validator.validate_registry import inspect_final_js

STATES = ("ELIGIBLE", "ALREADY_IMPORTED", "UPDATE_AVAILABLE", "UNSUPPORTED_ADAPTER",
          "UNRESOLVED_METADATA", "PATCH_REQUIRED", "BLOCKED", "ERROR")


def _counts(values):
    return dict(sorted(Counter(values).items()))


def _artifact_details(registry, repo_root):
    details, groups = {}, defaultdict(list)
    for artifact in sorted(registry["artifacts"], key=lambda item: item["artifactId"]):
        aid = artifact["artifactId"]
        producer = artifact["implementation"]["producer"]
        patch_path = f"sources_patches/{aid}.patch.js"
        result = {
            "artifactId": aid, "runtimeKey": artifact["runtimeKey"],
            "providerId": artifact["providerId"], "fileName": f"{aid}.js",
            "catalogName": artifact.get("catalogName"),
            "catalogDescription": artifact.get("catalogDescription"),
            "locales": artifact.get("locales", []), "producer": producer,
            "supportStatus": artifact.get("supportStatus"), "currentLocalVersion": None,
            "currentUpstreamVersion": artifact.get("upstream", {}).get("version"),
            "sharedRuntimeKeyGroup": artifact.get("compatibility", {}).get("sharedRuntimeKeyGroup"),
            "patchPath": patch_path if producer == "generated-with-patch" else None,
            "patchStatus": "PATCH_EXISTS" if producer == "generated-with-patch" else "unknown",
            "requiresAuth": None, "requiresWebView": None, "errors": [],
            "upstreamIdentity": ({key: artifact["upstream"][key] for key in ("project", "sourceId", "module")}
                                 if "upstream" in artifact else None),
        }
        if repo_root is not None:
            try:
                final = Path(repo_root) / f"{aid}.js"
                metadata = inspect_final_js(final)
                if not metadata.get("name") or not metadata.get("version") or metadata.get("key") != artifact["runtimeKey"]:
                    raise ValueError("runtime-identity-mismatch")
                result["currentLocalVersion"] = metadata.get("version")
                result["catalogName"] = artifact.get("catalogName", metadata.get("name"))
                patch_exists = (Path(repo_root) / patch_path).is_file()
                result["patchStatus"] = "PATCH_EXISTS" if patch_exists else "NO_PATCH"
                result["patchPath"] = patch_path if patch_exists else None
                if producer == "generated-with-patch" and not patch_exists:
                    result["errors"].append("required-patch-missing")
                if producer in {"generated", "generated-with-patch"}:
                    ir_path = Path(repo_root) / "sources_ir" / f"{aid}.json"
                    ir = json.loads(ir_path.read_text(encoding="utf-8"))
                    if not isinstance(ir, dict):
                        raise ValueError("IR must be an object")
                    for field in ("requiresAuth", "requiresWebView"):
                        value = ir.get(field)
                        if value is not None and type(value) is not bool:
                            raise ValueError("Invalid IR capability type")
                        result[field] = value
            except (OSError, UnicodeError, ValueError, TypeError, KeyError):
                result["errors"].append("local-artifact-read-or-identity-error")
        details[aid] = result
        if result["sharedRuntimeKeyGroup"]:
            groups[result["sharedRuntimeKeyGroup"]].append(aid)
    return details, [{"group": group, "artifactIds": members,
                      "runtimeKey": details[members[0]]["runtimeKey"]}
                     for group, members in sorted(groups.items())]


def _version_relation(current, proposed):
    if current is None or proposed is None:
        return "unknown"
    old, new = tuple(map(int, current.split("."))), tuple(map(int, proposed.split(".")))
    return "same" if old == new else "newer" if new > old else "older"


def add_batch_report(plan, inventory, registry, *, locales=(), eligibility=(), source_ids=(),
                     include_unresolved_locales=False, repo_root=None, scan_errors=None):
    from tools.source_conversion.planner.eligibility_planner import PlannerError
    if any(normalize_locale(value) is None for value in locales):
        raise PlannerError("LOCALE_FILTER_INVALID", "Locale filters require a concrete language tag.")
    requested = sorted(set(normalize_locale(value) for value in locales))
    routes, ids = sorted(set(eligibility)), sorted(set(source_ids))
    raw = {(item["project"], item["sourceId"]): item for item in inventory["candidates"]}
    artifacts, groups = _artifact_details(registry, repo_root)
    registered = {item["artifactId"]: item for item in registry["artifacts"]}
    pins = {item["project"]: item["commit"] for item in plan["upstreams"]}
    errors = scan_errors or {}
    records, unresolved_locales = [], []
    for candidate in plan["candidates"]:
        key = (candidate["project"], candidate["sourceId"])
        evidence = raw[key]
        locale = candidate_locale(evidence)
        unresolved = locale is None or locale == "zh"
        if unresolved:
            unresolved_locales.append({"project": key[0], "sourceId": key[1], "module": candidate["module"],
                                       "upstreamLang": candidate["upstreamLang"], "locale": locale})
        if requested and not any(locale_matches(locale, value) for value in requested):
            if not (include_unresolved_locales and unresolved):
                continue
        if (routes and candidate["eligibility"] not in routes) or (ids and candidate["sourceId"] not in ids):
            continue
        joined = candidate["registryJoin"]["artifactIds"]
        local = artifacts[joined[0]] if joined else None
        adapter = adapter_for_candidate(evidence, commit=pins[key[0]])
        signals = candidate["staticEvidence"]["capabilitySignals"]
        reasons = []
        candidate_errors = sorted(set(
            tuple(errors.get(("module", key[0], candidate["module"]), ()))
            + tuple(errors.get(("theme", key[0], candidate.get("theme")), ()))
        ))
        if local:
            candidate_errors = sorted(set(candidate_errors + local["errors"]))
        relation = _version_relation(local["currentUpstreamVersion"] if local else None, evidence.get("version"))
        patch_status = local["patchStatus"] if local else (
            "PATCH_REQUIRED" if candidate["patchState"] == "required" else
            "NO_PATCH" if candidate["patchState"] == "not-required" else "unknown")
        if candidate_errors:
            state = "ERROR"
            reasons.extend(candidate_errors)
        elif local:
            if local["supportStatus"] in {"retired", "needs-rescue"}:
                state = "BLOCKED"
                reasons.append("registry-" + local["supportStatus"])
            elif relation == "older":
                state = "BLOCKED"
                reasons.append("upstream-version-backward")
            else:
                state = "UPDATE_AVAILABLE" if relation == "newer" else "ALREADY_IMPORTED"
                reasons.append("existing-artifact-protected")
                upstream = registered[joined[0]]["upstream"]
                if upstream["commit"] != pins[key[0]] or upstream["module"] != candidate["module"]:
                    reasons.append("upstream-refresh-review-required")
                if local["producer"] != "generated" or patch_status == "PATCH_EXISTS":
                    reasons.append("manual-or-patch-backed-source-protected")
        elif patch_status == "PATCH_REQUIRED" or candidate["eligibility"] == "E4":
            state = "PATCH_REQUIRED"
            reasons.append("manual-patch-review-required")
        elif candidate["eligibility"] == "E5" or (candidate.get("theme") and
                candidate["theme"] not in THEME_ADAPTERS and adapter == "generic-html"):
            state = "UNSUPPORTED_ADAPTER"
            reasons.append("required-core-unsupported" if candidate["eligibility"] == "E5" else "missing-family-adapter")
        elif locale is None:
            state = "UNRESOLVED_METADATA"
            reasons.append("source-locale-unresolved")
        elif candidate["eligibility"] in {"E1", "E2"} or (candidate["eligibility"] == "E3" and adapter != "generic-html"):
            state = "ELIGIBLE"
            reasons.append("explicit-identity-plan-and-materializer-check-required")
        else:
            state = "UNRESOLVED_METADATA"
            reasons.append("extraction-evidence-unresolved")
        warnings = list(signals)
        if locale == "zh":
            warnings.append("chinese-script-unresolved")
        if local and local["sharedRuntimeKeyGroup"]:
            warnings.append("shared-runtime-key-review")
        if "contentWarning" not in candidate:
            warnings.append("content-warning-unknown")
        records.append({
            "project": key[0], "sourceId": key[1], "module": candidate["module"],
            "name": candidate["name"], "upstreamLang": candidate["upstreamLang"], "locale": locale,
            "artifactId": local["artifactId"] if local else None, "runtimeKey": local["runtimeKey"] if local else None,
            "providerId": local["providerId"] if local else None, "fileName": local["fileName"] if local else None,
            "catalogName": local["catalogName"] if local else candidate["name"],
            "imported": bool(local), "eligibility": candidate["eligibility"], "state": state,
            "adapter": adapter, "family": "theme:" + candidate["theme"] if "theme" in candidate else "module:" + candidate["module"],
            "action": "review-create" if state == "ELIGIBLE" else "review-update" if state == "UPDATE_AVAILABLE" else "skip",
            "reasonCodes": sorted(reasons), "warnings": sorted(set(warnings)),
            "contentWarning": candidate.get("contentWarning"),
            "currentLocalVersion": local["currentLocalVersion"] if local else None,
            "currentUpstreamVersion": local["currentUpstreamVersion"] if local else None,
            "proposedUpstreamVersion": evidence.get("version"), "versionRelation": relation,
            "proposedLocalVersion": None, "patchStatus": patch_status, "patchPath": local["patchPath"] if local else None,
            "sharedRuntimeKeyGroup": local["sharedRuntimeKeyGroup"] if local else None,
            "authRequired": local["requiresAuth"] if local else (False if "exact-pin-reviewed-family-contract" in candidate["reasonCodes"] else None),
            "authReview": "credentials-or-token-flow" in signals, "jsHeavyReview": "webview-or-quickjs" in signals,
            "health": "unknown",
        })
    batch = {
        "schemaVersion": "1.0", "selection": {"locales": requested, "eligibility": routes,
            "sourceIds": ids, "includeUnresolvedLocales": include_unresolved_locales},
        "candidates": records, "unresolvedLocales": unresolved_locales,
        "unresolvedModules": sorted(inventory["unresolvedModules"], key=lambda item:(item["project"], item["module"], item["reason"]["code"])),
        "existingArtifacts": list(artifacts.values()), "sharedRuntimeKeyGroups": groups,
        "summary": {"candidates": len(records), "states": {state:sum(item["state"] == state for item in records) for state in STATES},
                    "adapters": _counts(item["adapter"] for item in records),
                    "locales": _counts(item["locale"] or "unresolved" for item in records),
                    "imported": sum(item["imported"] for item in records),
                    "authReview": sum(item["authReview"] for item in records),
                    "jsHeavyReview": sum(item["jsHeavyReview"] for item in records),
                    "sharedRuntimeKey": sum(item["sharedRuntimeKeyGroup"] is not None for item in records)},
        "publication": {"mode": "read-only", "manifest": [], "registryDelta": [], "indexDelta": []},
    }
    from tools.source_conversion.validator.validate_batch_report import validate_batch_report
    problems = validate_batch_report(batch)
    if problems:
        raise PlannerError("BATCH_REPORT_INVALID", "; ".join(problems))
    plan = dict(plan)
    plan["schemaVersion"] = "1.1"
    plan["batch"] = batch
    return plan
