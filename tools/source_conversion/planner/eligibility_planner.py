#!/usr/bin/env python3
"""Build a deterministic, read-only source eligibility plan."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.source_conversion.validator.validate_inventory import (  # noqa: E402
    validate_inventory_data,
)
from tools.source_conversion.validator.validate_registry import (  # noqa: E402
    validate_registry_data,
)


PLANNER_RULE_VERSION = "1.0"
CANONICAL_PROJECT = "keiyoushi/extensions-source"
DEFAULT_INVENTORY_PATH = (
    REPO_ROOT
    / "tools"
    / "source_conversion"
    / "inventory"
    / "upstream_inventory.json"
)
DEFAULT_REGISTRY_PATH = REPO_ROOT / "sources_registry.json"

ELIGIBILITY_ROUTES = ("E0", "E1", "E2", "E3", "E4", "E5", "E6")
PATCH_STATES = ("not-required", "required", "unknown")

EXTRACTION_ELIGIBILITY = {
    "generic": ("E1", "inventory-generic-extraction"),
    "adapter": ("E2", "inventory-existing-adapter"),
    "manual": ("E4", "inventory-manual-extraction"),
    "unsupported": ("E5", "inventory-required-core-unsupported"),
}

# These patterns report bounded lexical evidence only. They never upgrade or
# downgrade E0-E6 eligibility.
CAPABILITY_PATTERNS = (
    (
        "credentials-or-token-flow",
        (
            re.compile(
                r"\b(?:username|password|accessToken|refreshToken|oauth|bearerToken)\b",
                re.IGNORECASE,
            ),
            re.compile(r'\bAuthorization\b'),
        ),
    ),
    (
        "webview-or-quickjs",
        (re.compile(r"\b(?:WebView|WebViewActivity|QuickJs|quickJs)\b"),),
    ),
    (
        "crypto-or-decoder",
        (
            re.compile(
                r"\b(?:Cipher|MessageDigest|SecretKeySpec|CryptoJS|decrypt|decoder?)\b",
                re.IGNORECASE,
            ),
            re.compile(r"Base64\s*\.\s*decode"),
        ),
    ),
    (
        "request-signing",
        (
            re.compile(
                r"\b(?:HmacSHA\w*|signature|signRequest|requestSignature|signedRequest)\b",
                re.IGNORECASE,
            ),
        ),
    ),
    (
        "image-interceptor",
        (
            re.compile(
                r"\b(?:ImageInterceptor|imageInterceptor|InterceptImage|ImageDecoder|imageDecoder)\b"
            ),
        ),
    ),
    (
        "user-configuration",
        (
            re.compile(
                r"\b(?:ConfigurableSource|PreferenceScreen|EditTextPreference|ListPreference|SwitchPreferenceCompat|getPreferences|preferences)\b"
            ),
        ),
    ),
    (
        "static-local-catalog",
        (
            re.compile(r"\bsourceList\s*=\s*listOf\s*\("),
            re.compile(r"Observable\s*\.\s*just\s*\(\s*MangasPage"),
        ),
    ),
)

MANGACATALOG_PROJECT = "keiyoushi/extensions-source"
MANGACATALOG_THEME = "mangacatalog"
MANGACATALOG_REVIEW_MODULES = (
    "en.readblackclovermangaonline",
    "en.readfairytailedenszeromangaonline",
    "en.readjujutsukaisenmangaonline",
    "en.readkingdommangaonline",
    "en.readnanatsunotaizai7deadlysinsmangaonline",
    "en.readonepiecemangaonline",
    "en.readsololevelingmangamanhwaonline",
    "en.readtokyoghoulretokyoghoulmangaonline",
)


class PlannerError(ValueError):
    """A deterministic fail-closed planner error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _diagnostic_summary(diagnostics: Iterable[Any]) -> str:
    return "; ".join(
        f"{item.code}:{item.subject}" for item in diagnostics
    )


def _validate_inputs(inventory: Any, registry: Any) -> None:
    registry_result = validate_registry_data(registry)
    if registry_result.errors:
        raise PlannerError(
            "REGISTRY_INVALID", _diagnostic_summary(registry_result.errors)
        )

    inventory_result = validate_inventory_data(inventory, registry)
    if inventory_result.errors:
        raise PlannerError(
            "INVENTORY_INVALID", _diagnostic_summary(inventory_result.errors)
        )


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlannerError("INPUT_READ_FAILED", str(exc)) from exc


def _run_git(root: Path, *args: str) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={root}",
        "-C",
        str(root),
        *args,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise PlannerError("UPSTREAM_GIT_FAILED", str(exc)) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PlannerError("UPSTREAM_GIT_FAILED", detail)
    return result.stdout.strip()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(
        str(right.resolve())
    )


def validate_upstream_checkout(
    extensions_root: Path, inventory: Mapping[str, Any], project: str
) -> str:
    """Prove that the read-only checkout is the clean inventory-pinned tree."""
    root = extensions_root.resolve()
    snapshots = {
        item["project"]: item["commit"] for item in inventory["upstreams"]
    }
    if project not in snapshots:
        raise PlannerError(
            "UPSTREAM_PROJECT_MISSING",
            f"Inventory has no pinned snapshot for {project}.",
        )

    top_level = Path(_run_git(root, "rev-parse", "--show-toplevel"))
    if not _same_path(top_level, root):
        raise PlannerError(
            "UPSTREAM_ROOT_INVALID",
            "The supplied extensions root is not the Git top-level.",
        )

    head = _run_git(root, "rev-parse", "HEAD")
    expected = snapshots[project]
    if head != expected:
        raise PlannerError(
            "UPSTREAM_PIN_MISMATCH",
            f"Expected {expected}, found {head}.",
        )

    status = _run_git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise PlannerError(
            "UPSTREAM_WORKTREE_DIRTY",
            "The pinned upstream checkout has local changes.",
        )
    return head


def _signals_in_text(text: str) -> set[str]:
    return {
        signal
        for signal, patterns in CAPABILITY_PATTERNS
        if any(pattern.search(text) for pattern in patterns)
    }


def _scan_units(
    common_root: Path, unit_roots: Mapping[tuple[str, str], Path]
) -> dict[tuple[str, str], tuple[str, ...]]:
    """Scan a source tree once and attribute files to explicit unit roots."""
    roots_by_path: dict[Path, tuple[str, str]] = {}
    for key, unit_root in unit_roots.items():
        resolved = unit_root.resolve()
        if not resolved.is_dir():
            raise PlannerError(
                "UPSTREAM_SOURCE_MISSING",
                f"Expected upstream source directory is missing: {resolved}",
            )
        roots_by_path[resolved] = key

    signals_by_unit: dict[tuple[str, str], set[str]] = {
        key: set() for key in unit_roots
    }
    common = common_root.resolve()
    files = sorted(
        (
            path
            for path in common.rglob("*")
            if path.is_file() and path.suffix in {".kt", ".kts"}
        ),
        key=lambda path: path.relative_to(common).as_posix(),
    )
    for path in files:
        parent = path.parent.resolve()
        unit = None
        while parent != common.parent:
            unit = roots_by_path.get(parent)
            if unit is not None or parent == common:
                break
            parent = parent.parent
        if unit is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PlannerError("UPSTREAM_SOURCE_READ_FAILED", str(exc)) from exc
        signals_by_unit[unit].update(_signals_in_text(text))
    return {
        key: tuple(sorted(signals))
        for key, signals in sorted(signals_by_unit.items())
    }


def scan_upstream_capabilities(
    extensions_root: Path,
    inventory: Mapping[str, Any],
    project: str,
) -> tuple[
    dict[tuple[str, str], tuple[str, ...]],
    dict[tuple[str, str], tuple[str, ...]],
]:
    """Scan explicit module and theme source units without executing code."""
    root = extensions_root.resolve()
    modules = sorted(
        {
            item["module"]
            for item in (*inventory["candidates"], *inventory["unresolvedModules"])
            if item["project"] == project
        }
    )
    themes = sorted(
        {
            item["theme"]
            for item in inventory["candidates"]
            if item["project"] == project and "theme" in item
        }
    )

    module_signals = _scan_units(
        root / "src",
        {
            (project, module): root
            / "src"
            / Path(*module.split("."))
            for module in modules
        },
    )
    theme_signals = _scan_units(
        root / "lib-multisrc",
        {
            (project, theme): root / "lib-multisrc" / theme
            for theme in themes
        },
    )
    return module_signals, theme_signals


def _registry_join_map(
    inventory: Mapping[str, Any], registry: Mapping[str, Any]
) -> dict[tuple[str, str], tuple[str, ...]]:
    inventory_matches: defaultdict[tuple[str, str], list[Mapping[str, Any]]] = (
        defaultdict(list)
    )
    for candidate in inventory["candidates"]:
        inventory_matches[(candidate["project"], candidate["sourceId"])].append(
            candidate
        )

    registered: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
    for artifact in registry["artifacts"]:
        upstream = artifact.get("upstream")
        if upstream is None:
            continue
        identity = (upstream["project"], upstream["sourceId"])
        matches = inventory_matches.get(identity, [])
        if len(matches) != 1:
            raise PlannerError(
                "REGISTERED_MAPPING_NOT_EXACT",
                f"Registered identity {identity[0]}:{identity[1]} resolves to "
                f"{len(matches)} candidates.",
            )
        registered[identity].append(artifact["artifactId"])

    for identity, artifact_ids in sorted(registered.items()):
        if len(artifact_ids) != 1:
            raise PlannerError(
                "REGISTERED_MAPPING_AMBIGUOUS",
                f"Registered identity {identity[0]}:{identity[1]} is owned by "
                f"{len(artifact_ids)} artifacts.",
            )
    return {
        identity: tuple(sorted(artifact_ids))
        for identity, artifact_ids in registered.items()
    }


def _patch_state(compatibility: Mapping[str, Any]) -> tuple[str, str]:
    if compatibility.get("patchRequired") is True:
        return "required", "inventory-patch-required"
    if compatibility.get("patchRequired") is False:
        return "not-required", "inventory-patch-not-required"
    return "unknown", "patch-evidence-unknown"


def _aggregate_patch_state(states: Iterable[str]) -> str:
    values = tuple(states)
    if values and all(value == "not-required" for value in values):
        return "not-required"
    if values and all(value == "required" for value in values):
        return "required"
    return "unknown"


def _eligibility_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(item["eligibility"] for item in records)
    return {route: counts.get(route, 0) for route in ELIGIBILITY_ROUTES}


def _patch_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(item["patchState"] for item in records)
    return {state: counts.get(state, 0) for state in PATCH_STATES}


def _candidate_signals(
    candidate: Mapping[str, Any],
    module_signals: Mapping[tuple[str, str], Iterable[str]],
    theme_signals: Mapping[tuple[str, str], Iterable[str]],
) -> tuple[str, ...]:
    signals = set(
        module_signals.get((candidate["project"], candidate["module"]), ())
    )
    theme = candidate.get("theme")
    if theme is not None:
        signals.update(theme_signals.get((candidate["project"], theme), ()))
    return tuple(sorted(signals))


def _candidate_record(
    candidate: Mapping[str, Any],
    family_ids: tuple[str, ...],
    registry_joins: Mapping[tuple[str, str], tuple[str, ...]],
    module_signals: Mapping[tuple[str, str], Iterable[str]],
    theme_signals: Mapping[tuple[str, str], Iterable[str]],
) -> dict[str, Any]:
    identity = (candidate["project"], candidate["sourceId"])
    artifact_ids = registry_joins.get(identity, ())
    compatibility = candidate["compatibility"]
    patch_state, patch_reason = _patch_state(compatibility)

    if artifact_ids:
        eligibility = "E0"
        eligibility_reason = "registered-upstream-identity"
    elif compatibility["extraction"] in EXTRACTION_ELIGIBILITY:
        eligibility, eligibility_reason = EXTRACTION_ELIGIBILITY[
            compatibility["extraction"]
        ]
    elif family_ids:
        eligibility = "E3"
        eligibility_reason = "explicit-shared-family"
    else:
        eligibility = "E6"
        eligibility_reason = "insufficient-static-evidence"

    record: dict[str, Any] = {
        "project": candidate["project"],
        "sourceId": candidate["sourceId"],
        "module": candidate["module"],
        "name": candidate["name"],
        "upstreamLang": candidate["upstreamLang"],
    }
    for field in ("canonicalLocale", "contentWarning", "theme"):
        if field in candidate:
            record[field] = candidate[field]
    record.update(
        {
            "eligibility": eligibility,
            "patchState": patch_state,
            "reasonCodes": sorted((eligibility_reason, patch_reason)),
            "staticEvidence": {
                "metadataResolution": compatibility["metadataResolution"],
                "extraction": compatibility["extraction"],
                "capabilitySignals": list(
                    _candidate_signals(
                        candidate, module_signals, theme_signals
                    )
                ),
            },
            "registryJoin": {
                "status": "registered" if artifact_ids else "unregistered",
                "artifactIds": list(artifact_ids),
            },
        }
    )
    return record


def _derive_mangacatalog_proposal(
    candidates: Sequence[Mapping[str, Any]],
    families: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    family_exists = any(
        family["project"] == MANGACATALOG_PROJECT
        and family["familyId"] == f"theme:{MANGACATALOG_THEME}"
        and family["eligibility"] == "E3"
        for family in families
    )
    if not family_exists:
        return []

    by_module: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        if (
            candidate["project"] == MANGACATALOG_PROJECT
            and candidate.get("theme") == MANGACATALOG_THEME
        ):
            by_module[candidate["module"]].append(candidate)

    members: list[dict[str, Any]] = []
    for module in MANGACATALOG_REVIEW_MODULES:
        matches = by_module.get(module, [])
        if len(matches) != 1 or matches[0]["eligibility"] != "E3":
            return []
        candidate = matches[0]
        member = {
            "project": candidate["project"],
            "sourceId": candidate["sourceId"],
            "module": candidate["module"],
            "upstreamLang": candidate["upstreamLang"],
        }
        if "contentWarning" in candidate:
            member["contentWarning"] = candidate["contentWarning"]
        members.append(member)

    return [
        {
            "proposalId": "mangacatalog-initial-review",
            "proposalType": "review-batch",
            "status": "review-only",
            "project": MANGACATALOG_PROJECT,
            "familyId": f"theme:{MANGACATALOG_THEME}",
            "technicalEligibility": "E3",
            "reasonCodes": [
                "accepted-bounded-review-rule",
                "requires-static-local-catalog-capability",
                "requires-theme-aware-extraction",
            ],
            "members": members,
        }
    ]


def build_plan(
    inventory: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    module_signals: Mapping[tuple[str, str], Iterable[str]] | None = None,
    theme_signals: Mapping[tuple[str, str], Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Build a pure deterministic report from validated input data."""
    _validate_inputs(inventory, registry)
    module_signals = module_signals or {}
    theme_signals = theme_signals or {}
    registry_joins = _registry_join_map(inventory, registry)

    raw_candidates = sorted(
        inventory["candidates"],
        key=lambda item: (
            item["project"],
            item["sourceId"],
            item["module"],
            item["name"],
            item["upstreamLang"],
        ),
    )
    candidates_by_module: defaultdict[
        tuple[str, str], list[Mapping[str, Any]]
    ] = defaultdict(list)
    candidates_by_theme: defaultdict[
        tuple[str, str], list[Mapping[str, Any]]
    ] = defaultdict(list)
    for candidate in raw_candidates:
        candidates_by_module[(candidate["project"], candidate["module"])].append(
            candidate
        )
        if "theme" in candidate:
            candidates_by_theme[(candidate["project"], candidate["theme"])].append(
                candidate
            )

    family_ids_by_identity: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    family_specs: list[tuple[str, str, str, list[Mapping[str, Any]]]] = []
    for (project, theme), members in sorted(candidates_by_theme.items()):
        family_id = f"theme:{theme}"
        family_specs.append((project, family_id, "upstream-theme", members))
        for candidate in members:
            family_ids_by_identity[(project, candidate["sourceId"])].add(family_id)
    for (project, module), members in sorted(candidates_by_module.items()):
        if len(members) < 2:
            continue
        family_id = f"module:{module}"
        family_specs.append(
            (project, family_id, "multi-candidate-module", members)
        )
        for candidate in members:
            family_ids_by_identity[(project, candidate["sourceId"])].add(family_id)

    candidate_records = [
        _candidate_record(
            candidate,
            tuple(
                sorted(
                    family_ids_by_identity[
                        (candidate["project"], candidate["sourceId"])
                    ]
                )
            ),
            registry_joins,
            module_signals,
            theme_signals,
        )
        for candidate in raw_candidates
    ]
    records_by_identity = {
        (item["project"], item["sourceId"]): item for item in candidate_records
    }
    records_by_module: defaultdict[
        tuple[str, str], list[Mapping[str, Any]]
    ] = defaultdict(list)
    for record in candidate_records:
        records_by_module[(record["project"], record["module"])].append(record)

    family_records: list[dict[str, Any]] = []
    for project, family_id, family_type, raw_members in sorted(
        family_specs, key=lambda item: (item[0], item[1], item[2])
    ):
        members = [
            records_by_identity[(item["project"], item["sourceId"])]
            for item in raw_members
        ]
        member_routes = {item["eligibility"] for item in members}
        if len(member_routes) == 1:
            eligibility = next(iter(member_routes))
            route_reason = "uniform-member-eligibility"
        else:
            eligibility = "E3"
            route_reason = "shared-family-with-member-overrides"
        family_reason = (
            "explicit-upstream-theme"
            if family_type == "upstream-theme"
            else "multi-candidate-module"
        )
        signals = sorted(
            {
                signal
                for item in members
                for signal in item["staticEvidence"]["capabilitySignals"]
            }
        )
        family_records.append(
            {
                "project": project,
                "familyId": family_id,
                "familyType": family_type,
                "memberModules": sorted({item["module"] for item in members}),
                "candidateCount": len(members),
                "eligibility": eligibility,
                "candidateEligibilityCounts": _eligibility_counts(members),
                "patchState": _aggregate_patch_state(
                    item["patchState"] for item in members
                ),
                "reasonCodes": sorted((family_reason, route_reason)),
                "capabilitySignals": signals,
            }
        )

    unresolved_by_module = {
        (item["project"], item["module"]): item
        for item in inventory["unresolvedModules"]
    }
    module_keys = sorted(set(records_by_module) | set(unresolved_by_module))
    module_records: list[dict[str, Any]] = []
    for project, module in module_keys:
        members = records_by_module.get((project, module), [])
        if not members:
            unresolved = unresolved_by_module[(project, module)]
            module_records.append(
                {
                    "project": project,
                    "module": module,
                    "candidateCount": 0,
                    "eligibility": "E6",
                    "candidateEligibilityCounts": {
                        route: 0 for route in ELIGIBILITY_ROUTES
                    },
                    "patchState": "unknown",
                    "reasonCodes": [
                        "insufficient-static-evidence",
                        "unresolved-upstream-module",
                    ],
                    "upstreamReasonCode": unresolved["reason"]["code"],
                    "capabilitySignals": list(
                        sorted(module_signals.get((project, module), ()))
                    ),
                }
            )
            continue

        routes = {item["eligibility"] for item in members}
        if len(routes) == 1:
            eligibility = next(iter(routes))
            reason = "uniform-candidate-eligibility"
        else:
            eligibility = "E3" if len(members) > 1 else "E6"
            reason = "module-with-candidate-overrides"
        module_records.append(
            {
                "project": project,
                "module": module,
                "candidateCount": len(members),
                "eligibility": eligibility,
                "candidateEligibilityCounts": _eligibility_counts(members),
                "patchState": _aggregate_patch_state(
                    item["patchState"] for item in members
                ),
                "reasonCodes": [reason],
                "capabilitySignals": sorted(
                    {
                        signal
                        for item in members
                        for signal in item["staticEvidence"]["capabilitySignals"]
                    }
                ),
            }
        )

    themed_candidates = [
        item for item in raw_candidates if "theme" in item
    ]
    summary = {
        "modules": len(module_records),
        "candidates": len(candidate_records),
        "unresolvedModules": len(inventory["unresolvedModules"]),
        "families": len(family_records),
        "themes": len(candidates_by_theme),
        "themeAssociatedModules": len(
            {(item["project"], item["module"]) for item in themed_candidates}
        ),
        "themeAssociatedCandidates": len(themed_candidates),
        "multiCandidateModules": sum(
            1 for members in candidates_by_module.values() if len(members) > 1
        ),
        "registryJoins": {
            "registeredCandidates": sum(
                item["registryJoin"]["status"] == "registered"
                for item in candidate_records
            ),
            "unregisteredCandidates": sum(
                item["registryJoin"]["status"] == "unregistered"
                for item in candidate_records
            ),
        },
        "eligibilityCounts": {
            "families": _eligibility_counts(family_records),
            "modules": _eligibility_counts(module_records),
            "candidates": _eligibility_counts(candidate_records),
        },
        "patchStateCounts": {
            "families": _patch_counts(family_records),
            "modules": _patch_counts(module_records),
            "candidates": _patch_counts(candidate_records),
        },
    }

    plan: dict[str, Any] = {
        "schemaVersion": "1.0",
        "plannerRuleVersion": PLANNER_RULE_VERSION,
        "upstreams": sorted(
            (
                {"project": item["project"], "commit": item["commit"]}
                for item in inventory["upstreams"]
            ),
            key=lambda item: (item["project"], item["commit"]),
        ),
        "summary": summary,
        "families": family_records,
        "modules": module_records,
        "candidates": candidate_records,
    }
    plan["proposals"] = _derive_mangacatalog_proposal(
        candidate_records, family_records
    )
    return plan


def serialize_plan(plan: Mapping[str, Any]) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2) + "\n"


def generate_plan(
    inventory_path: Path,
    registry_path: Path,
    extensions_root: Path,
    project: str,
) -> dict[str, Any]:
    inventory = _load_json(inventory_path)
    registry = _load_json(registry_path)
    _validate_inputs(inventory, registry)
    validate_upstream_checkout(extensions_root, inventory, project)
    module_signals, theme_signals = scan_upstream_capabilities(
        extensions_root, inventory, project
    )
    return build_plan(
        inventory,
        registry,
        module_signals=module_signals,
        theme_signals=theme_signals,
    )


def _write_stdout(value: str) -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", newline="\n")
    sys.stdout.write(value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic read-only eligibility/family plan as JSON."
        )
    )
    parser.add_argument(
        "--inventory", type=Path, default=DEFAULT_INVENTORY_PATH
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument(
        "--extensions-root",
        type=Path,
        required=True,
        help="Clean pinned extensions-source Git top-level.",
    )
    parser.add_argument("--project", default=CANONICAL_PROJECT)
    args = parser.parse_args(argv)

    try:
        plan = generate_plan(
            args.inventory, args.registry, args.extensions_root, args.project
        )
    except PlannerError as exc:
        print(f"[ERROR] {exc.code}: {exc}", file=sys.stderr)
        return 1

    _write_stdout(serialize_plan(plan))
    summary = plan["summary"]
    routes = summary["eligibilityCounts"]["candidates"]
    print(
        "SUMMARY "
        f"modules={summary['modules']} candidates={summary['candidates']} "
        f"families={summary['families']} "
        + " ".join(f"{route}={routes[route]}" for route in ELIGIBILITY_ROUTES),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
