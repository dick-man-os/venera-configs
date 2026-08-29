import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


from tools.source_conversion.planner.eligibility_planner import (
    MANGACATALOG_REVIEW_MODULES,
    PlannerError,
    build_plan,
    main,
    scan_upstream_capabilities,
    serialize_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT = "keiyoushi/extensions-source"
COMMIT = "5e06c412c0264b18120fd963fdd6efb529f3fa29"


def candidate(
    source_id="1",
    module="en.sample",
    *,
    name="Sample",
    lang="en",
    extraction="unclassified",
    patch_required=None,
    theme=None,
    content_warning=None,
):
    compatibility = {
        "metadataResolution": "static",
        "extraction": extraction,
    }
    if patch_required is not None:
        compatibility["patchRequired"] = patch_required
    value = {
        "project": PROJECT,
        "sourceId": source_id,
        "module": module,
        "name": name,
        "upstreamLang": lang,
        "compatibility": compatibility,
    }
    if theme is not None:
        value["theme"] = theme
    if content_warning is not None:
        value["contentWarning"] = content_warning
    return value


def inventory(*candidates, unresolved_modules=None):
    return {
        "schemaVersion": "1.0",
        "upstreams": [{"project": PROJECT, "commit": COMMIT}],
        "candidates": list(candidates),
        "unresolvedModules": list(unresolved_modules or []),
    }


def registry_artifact(
    artifact_id,
    source_id,
    *,
    module="en.sample",
):
    return {
        "artifactId": artifact_id,
        "runtimeKey": artifact_id,
        "providerId": artifact_id,
        "implementation": {"producer": "manual"},
        "upstream": {
            "project": PROJECT,
            "module": module,
            "sourceId": source_id,
            "version": "1.0.0",
            "extensionLib": "1.0",
            "commit": COMMIT,
        },
    }


def registry(*artifacts):
    if not artifacts:
        artifacts = (
            {
                "artifactId": "unrelated",
                "runtimeKey": "unrelated",
                "providerId": "unrelated",
                "implementation": {"producer": "manual"},
            },
        )
    return {"schemaVersion": "1.0", "artifacts": list(artifacts)}


def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)


def shared_unit_members(plan):
    modules = {
        (family["project"], module)
        for family in plan["families"]
        for module in family["memberModules"]
    }
    candidates = {
        (candidate["project"], candidate["sourceId"])
        for candidate in plan["candidates"]
        if (candidate["project"], candidate["module"]) in modules
    }
    return modules, candidates


class TestEligibilityPlannerUnit(unittest.TestCase):
    def test_repeated_output_is_byte_identical(self):
        source = inventory(
            candidate("2", "en.second", theme="sampletheme"),
            candidate("1", "en.first", theme="sampletheme"),
        )
        first = serialize_plan(build_plan(source, registry()))
        second = serialize_plan(build_plan(copy.deepcopy(source), registry()))
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))

    def test_normal_cli_invocation_is_non_mutating(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_path = root / "inventory.json"
            registry_path = root / "registry.json"
            extensions_root = root / "extensions-source"
            extensions_root.mkdir()
            inventory_path.write_text(
                json.dumps(inventory(candidate())), encoding="utf-8"
            )
            registry_path.write_text(json.dumps(registry()), encoding="utf-8")

            def snapshot():
                return {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in sorted(root.rglob("*"))
                    if path.is_file()
                }

            before = snapshot()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch(
                "tools.source_conversion.planner.eligibility_planner.validate_upstream_checkout"
            ), patch(
                "tools.source_conversion.planner.eligibility_planner.scan_upstream_capabilities",
                return_value=({}, {}),
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                result = main(
                    [
                        "--inventory",
                        str(inventory_path),
                        "--registry",
                        str(registry_path),
                        "--extensions-root",
                        str(extensions_root),
                    ]
                )

            self.assertEqual(result, 0, stderr.getvalue())
            self.assertEqual(before, snapshot())
            serialized = stdout.getvalue()
            report = json.loads(serialized)
            self.assertEqual(report["summary"]["candidates"], 1)
            self.assertIn("SUMMARY modules=1 candidates=1", stderr.getvalue())
            for path in (root.resolve(), extensions_root.resolve()):
                rendered = str(path)
                self.assertNotIn(rendered, serialized)
                self.assertNotIn(json.dumps(rendered)[1:-1], serialized)
            forbidden_metadata_keys = {
                "timestamp",
                "createdAt",
                "generatedAt",
                "generatedTimestamp",
                "runId",
                "randomId",
                "executionId",
            }
            self.assertFalse(
                forbidden_metadata_keys.intersection(all_keys(report))
            )

    def test_report_preserves_project_and_pin_provenance(self):
        plan = build_plan(inventory(candidate()), registry())
        self.assertEqual(
            plan["upstreams"], [{"project": PROJECT, "commit": COMMIT}]
        )

    def test_duplicate_canonical_identity_fails_closed(self):
        with self.assertRaises(PlannerError) as raised:
            build_plan(
                inventory(
                    candidate("1", "en.before"),
                    candidate("1", "en.after"),
                ),
                registry(),
            )
        self.assertEqual(raised.exception.code, "INVENTORY_INVALID")

    def test_e0_uses_exact_registry_identity_join(self):
        plan = build_plan(
            inventory(candidate("7")),
            registry(registry_artifact("registered_sample", "7")),
        )
        record = plan["candidates"][0]
        self.assertEqual(record["eligibility"], "E0")
        self.assertEqual(
            record["registryJoin"],
            {"status": "registered", "artifactIds": ["registered_sample"]},
        )

    def test_unregistered_candidate_has_explicit_empty_join(self):
        plan = build_plan(inventory(candidate("7")), registry())
        self.assertEqual(
            plan["candidates"][0]["registryJoin"],
            {"status": "unregistered", "artifactIds": []},
        )

    def test_missing_and_ambiguous_registered_mappings_fail_closed(self):
        with self.assertRaises(PlannerError) as missing:
            build_plan(
                inventory(candidate("1")),
                registry(registry_artifact("missing", "2")),
            )
        self.assertEqual(missing.exception.code, "REGISTERED_MAPPING_NOT_EXACT")

        with self.assertRaises(PlannerError) as ambiguous:
            build_plan(
                inventory(candidate("1")),
                registry(
                    registry_artifact("first", "1"),
                    registry_artifact("second", "1"),
                ),
            )
        self.assertEqual(
            ambiguous.exception.code, "REGISTERED_MAPPING_AMBIGUOUS"
        )

    def test_explicit_theme_derives_family_relationship(self):
        plan = build_plan(
            inventory(
                candidate("1", "en.first", theme="madara"),
                candidate("2", "es.second", theme="madara"),
            ),
            registry(),
        )
        family = plan["families"][0]
        self.assertEqual(family["familyId"], "theme:madara")
        self.assertEqual(family["familyType"], "upstream-theme")
        self.assertEqual(family["memberModules"], ["en.first", "es.second"])
        self.assertTrue(
            all(item["eligibility"] == "E3" for item in plan["candidates"])
        )

    def test_multi_candidate_module_derives_family_relationship(self):
        plan = build_plan(
            inventory(
                candidate("1", "all.shared", lang="en"),
                candidate("2", "all.shared", lang="zh"),
            ),
            registry(),
        )
        family = plan["families"][0]
        self.assertEqual(family["familyId"], "module:all.shared")
        self.assertEqual(family["familyType"], "multi-candidate-module")
        self.assertEqual(family["candidateCount"], 2)

    def test_theme_and_multi_candidate_families_share_one_deduplicated_unit(self):
        members = (
            candidate("2", "all.overlap", theme="madara", lang="zh"),
            candidate("1", "all.overlap", theme="madara", lang="en"),
        )
        first = build_plan(inventory(*members), registry())
        second = build_plan(inventory(*reversed(members)), registry())

        self.assertEqual(
            [family["familyId"] for family in first["families"]],
            ["module:all.overlap", "theme:madara"],
        )
        self.assertEqual(
            {family["familyId"] for family in first["families"]},
            {"module:all.overlap", "theme:madara"},
        )
        self.assertTrue(
            all(
                family["memberModules"] == ["all.overlap"]
                and family["candidateCount"] == 2
                for family in first["families"]
            )
        )
        shared_modules, shared_candidates = shared_unit_members(first)
        self.assertEqual(shared_modules, {(PROJECT, "all.overlap")})
        self.assertEqual(
            shared_candidates, {(PROJECT, "1"), (PROJECT, "2")}
        )
        self.assertEqual(len(first["candidates"]), 2)
        self.assertEqual(
            len(
                {
                    (item["project"], item["sourceId"])
                    for item in first["candidates"]
                }
            ),
            2,
        )
        self.assertEqual(
            first["summary"]["eligibilityCounts"]["candidates"]["E3"], 2
        )
        self.assertEqual(serialize_plan(first), serialize_plan(second))

    def test_family_module_and_candidate_ordering_is_explicit(self):
        plan = build_plan(
            inventory(
                candidate("20", "en.zeta", theme="ztheme"),
                candidate("31", "en.multi"),
                candidate("10", "en.alpha", theme="atheme"),
                candidate("30", "en.multi"),
            ),
            registry(),
        )
        self.assertEqual(
            [item["familyId"] for item in plan["families"]],
            ["module:en.multi", "theme:atheme", "theme:ztheme"],
        )
        self.assertEqual(
            [item["module"] for item in plan["modules"]],
            ["en.alpha", "en.multi", "en.zeta"],
        )
        self.assertEqual(
            [item["sourceId"] for item in plan["candidates"]],
            ["10", "20", "30", "31"],
        )

    def test_insufficient_evidence_remains_e6(self):
        record = build_plan(inventory(candidate()), registry())["candidates"][0]
        self.assertEqual(record["eligibility"], "E6")
        self.assertIn("insufficient-static-evidence", record["reasonCodes"])

    def test_e5_requires_explicit_unsupported_core_evidence(self):
        record = build_plan(
            inventory(candidate(extraction="unsupported")), registry()
        )["candidates"][0]
        self.assertEqual(record["eligibility"], "E5")
        self.assertIn(
            "inventory-required-core-unsupported", record["reasonCodes"]
        )

    def test_capability_signal_alone_does_not_imply_e5(self):
        record = build_plan(
            inventory(candidate()),
            registry(),
            module_signals={(PROJECT, "en.sample"): ("webview-or-quickjs",)},
        )["candidates"][0]
        self.assertEqual(record["eligibility"], "E6")
        self.assertEqual(
            record["staticEvidence"]["capabilitySignals"],
            ["webview-or-quickjs"],
        )

    def test_static_scanner_attributes_only_explicit_source_units(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            module_root = root / "src" / "en" / "sample"
            theme_root = root / "lib-multisrc" / "madara"
            module_root.mkdir(parents=True)
            theme_root.mkdir(parents=True)
            (module_root / "build.gradle.kts").write_text(
                "val engine = QuickJs.create()\n", encoding="utf-8"
            )
            (theme_root / "Theme.kt").write_text(
                "val sourceList = listOf(name to baseUrl)\n"
                "val page = Observable.just(MangasPage(items, false))\n",
                encoding="utf-8",
            )
            source = inventory(candidate(theme="madara"))

            module_signals, theme_signals = scan_upstream_capabilities(
                root, source, PROJECT
            )

            self.assertEqual(
                module_signals[(PROJECT, "en.sample")],
                ("webview-or-quickjs",),
            )
            self.assertEqual(
                theme_signals[(PROJECT, "madara")],
                ("static-local-catalog",),
            )

    def test_explicit_compatibility_routes_are_preserved(self):
        for extraction, expected in (
            ("generic", "E1"),
            ("adapter", "E2"),
            ("manual", "E4"),
        ):
            with self.subTest(extraction=extraction):
                record = build_plan(
                    inventory(candidate(extraction=extraction)), registry()
                )["candidates"][0]
                self.assertEqual(record["eligibility"], expected)

    def test_patch_state_defaults_unknown_and_uses_only_explicit_evidence(self):
        unknown = build_plan(inventory(candidate()), registry())["candidates"][0]
        not_required = build_plan(
            inventory(candidate(patch_required=False)), registry()
        )["candidates"][0]
        required = build_plan(
            inventory(candidate(patch_required=True)), registry()
        )["candidates"][0]
        self.assertEqual(unknown["patchState"], "unknown")
        self.assertEqual(not_required["patchState"], "not-required")
        self.assertEqual(required["patchState"], "required")
        self.assertEqual(
            unknown["eligibility"], required["eligibility"],
            "Patch state must remain orthogonal to eligibility.",
        )

    def test_report_never_generates_runtime_or_artifact_identity(self):
        plan = build_plan(
            inventory(candidate("7")),
            registry(registry_artifact("existing_artifact", "7")),
        )
        keys = set(all_keys(plan))
        self.assertNotIn("runtimeKey", keys)
        self.assertNotIn("artifactId", keys)
        self.assertNotIn("sharedRuntimeKeyGroup", keys)
        self.assertEqual(
            plan["candidates"][0]["registryJoin"]["artifactIds"],
            ["existing_artifact"],
        )

    def test_raw_zh_is_not_normalized(self):
        record = build_plan(
            inventory(candidate(lang="zh")), registry()
        )["candidates"][0]
        self.assertEqual(record["upstreamLang"], "zh")
        self.assertNotIn("canonicalLocale", record)

    def test_content_warning_does_not_change_technical_eligibility(self):
        safe = build_plan(
            inventory(candidate(theme="madara", content_warning="SAFE")),
            registry(),
        )["candidates"][0]
        nsfw = build_plan(
            inventory(candidate(theme="madara", content_warning="NSFW")),
            registry(),
        )["candidates"][0]
        self.assertEqual(safe["eligibility"], nsfw["eligibility"])
        self.assertEqual(safe["eligibility"], "E3")


class TestEligibilityPlannerCurrentPin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(
            (
                REPO_ROOT
                / "tools"
                / "source_conversion"
                / "inventory"
                / "upstream_inventory.json"
            ).read_text(encoding="utf-8")
        )
        cls.registry = json.loads(
            (REPO_ROOT / "sources_registry.json").read_text(encoding="utf-8")
        )
        cls.plan = build_plan(cls.inventory, cls.registry)


    def _get_pre_e4b_registry(self):
        import copy
        reg = copy.deepcopy(self.registry)
        e4b_ids = {
            "readblackclovermangaonline",
            "readfairytailedenszeromangaonline",
            "readjujutsukaisenmangaonline",
            "readkingdommangaonline",
            "readnanatsunotaizai7deadlysinsmangaonline",
            "readonepiecemangaonline",
            "readsololevelingmangamanhwaonline",
            "readtokyoghoulretokyoghoulmangaonline",
        }
        reg["artifacts"] = [a for a in reg["artifacts"] if a["artifactId"] not in e4b_ids]
        return reg
    def test_current_pin_family_derivation_regression(self):
        summary = self.plan["summary"]
        self.assertEqual(summary["modules"], 1368)
        self.assertEqual(summary["candidates"], 2128)
        self.assertEqual(summary["unresolvedModules"], 0)
        self.assertEqual(summary["themes"], 64)
        self.assertEqual(summary["themeAssociatedModules"], 725)
        self.assertEqual(summary["themeAssociatedCandidates"], 836)
        self.assertEqual(summary["multiCandidateModules"], 77)
        self.assertEqual(summary["families"], 141)

    def test_current_pin_shared_unit_e0_precedence_regression(self):
        shared_modules, shared_candidates = shared_unit_members(self.plan)
        self.assertEqual(len(shared_modules), 784)
        self.assertEqual(len(shared_candidates), 1544)

        overrides = {
            "2522335540328470744": "webtoons",
            "2959982438613576472": "webtoons_zh_hant",
            "6485938153129890061": "readblackclovermangaonline",
            "1330793582354406642": "readfairytailedenszeromangaonline",
            "808850989053853006": "readjujutsukaisenmangaonline",
            "7952360835727640966": "readkingdommangaonline",
            "3945031984510180731": "readnanatsunotaizai7deadlysinsmangaonline",
            "1061544757733451419": "readonepiecemangaonline",
            "1374366734159205648": "readsololevelingmangamanhwaonline",
            "6468833665354206027": "readtokyoghoulretokyoghoulmangaonline",
        }
        webtoons_family = next(
            family
            for family in self.plan["families"]
            if family["familyId"] == "module:all.webtoons"
        )
        self.assertIn("all.webtoons", webtoons_family["memberModules"])

        candidates_by_id = {
            item["sourceId"]: item for item in self.plan["candidates"]
        }
        for source_id, artifact_id in overrides.items():
            item = candidates_by_id[source_id]
            self.assertIn((item["project"], source_id), shared_candidates)
            if artifact_id.startswith("webtoons"):
                self.assertEqual(item["module"], "all.webtoons")
            self.assertEqual(item["eligibility"], "E0")
            self.assertEqual(
                item["registryJoin"]["artifactIds"], [artifact_id]
            )

        e3_candidates = {
            (item["project"], item["sourceId"])
            for item in self.plan["candidates"]
            if item["eligibility"] == "E3"
        }
        override_identities = {
            (PROJECT, source_id) for source_id in overrides
        }
        self.assertEqual(
            shared_candidates - override_identities, e3_candidates
        )
        self.assertEqual(len(shared_candidates) - len(overrides), 1534)

    def test_current_pin_classification_count_regression(self):
        counts = self.plan["summary"]["eligibilityCounts"]
        self.assertEqual(
            counts["families"],
            {"E0": 0, "E1": 0, "E2": 0, "E3": 141, "E4": 0, "E5": 0, "E6": 0},
        )
        self.assertEqual(
            counts["modules"],
            {"E0": 11, "E1": 0, "E2": 0, "E3": 776, "E4": 0, "E5": 0, "E6": 581},
        )
        self.assertEqual(
            counts["candidates"],
            {"E0": 13, "E1": 0, "E2": 0, "E3": 1534, "E4": 0, "E5": 0, "E6": 581},
        )
        self.assertEqual(
            self.plan["summary"]["patchStateCounts"]["candidates"],
            {"not-required": 0, "required": 0, "unknown": 2128},
        )

    def test_complete_cli_scanner_is_byte_deterministic_and_non_writing(self):
        extensions_root = REPO_ROOT.parent / "extensions-source"
        canonical_inventory = (
            REPO_ROOT
            / "tools"
            / "source_conversion"
            / "inventory"
            / "upstream_inventory.json"
        )
        canonical_registry = REPO_ROOT / "sources_registry.json"

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory_path = root / "upstream_inventory.json"
            registry_path = root / "sources_registry.json"
            inventory_path.write_bytes(canonical_inventory.read_bytes())
            registry_path.write_bytes(canonical_registry.read_bytes())

            def snapshot():
                return {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in sorted(root.rglob("*"))
                    if path.is_file()
                }

            def invoke():
                stdout = io.StringIO()
                stderr = io.StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = main(
                        [
                            "--inventory",
                            str(inventory_path),
                            "--registry",
                            str(registry_path),
                            "--extensions-root",
                            str(extensions_root),
                        ]
                    )
                self.assertEqual(result, 0, stderr.getvalue())
                return stdout.getvalue().encode("utf-8"), stderr.getvalue()

            before = snapshot()
            first, first_summary = invoke()
            second, second_summary = invoke()
            self.assertEqual(first, second)
            self.assertEqual(first_summary, second_summary)
            self.assertEqual(len(first), 2237181)
            self.assertEqual(
                hashlib.sha256(first).hexdigest(),
                "cd610bc27f031ad1206082c6ca6262ffef027adc53a65859eef68e423b36f500",
            )
            self.assertEqual(before, snapshot())

    def test_current_pin_e0_regression(self):
        registered = {
            item["registryJoin"]["artifactIds"][0]
            for item in self.plan["candidates"]
            if item["registryJoin"]["status"] == "registered"
        }
        self.assertEqual(
            registered,
            {
                "webtoons",
                "webtoons_zh_hant",
                "manhuashe",
                "comicabc",
                "flamecomics",
                "readblackclovermangaonline",
                "readfairytailedenszeromangaonline",
                "readjujutsukaisenmangaonline",
                "readkingdommangaonline",
                "readnanatsunotaizai7deadlysinsmangaonline",
                "readonepiecemangaonline",
                "readsololevelingmangamanhwaonline",
                "readtokyoghoulretokyoghoulmangaonline",
            },
        )
        self.assertEqual(
            self.plan["summary"]["registryJoins"],
            {"registeredCandidates": 13, "unregisteredCandidates": 2115},
        )

    def test_mangacatalog_proposal_is_report_only(self):
        self.assertEqual(len(self.plan["proposals"]), 0)
        plan = build_plan(self.inventory, self._get_pre_e4b_registry())
        self.assertEqual(len(plan["proposals"]), 1)
        proposal = plan["proposals"][0]
        self.assertEqual(proposal["status"], "review-only")
        self.assertEqual(proposal["technicalEligibility"], "E3")
        self.assertEqual(
            tuple(item["module"] for item in proposal["members"]),
            MANGACATALOG_REVIEW_MODULES,
        )
        forbidden = {
            "artifactId",
            "runtimeKey",
            "importStatus",
            "generatedJsPath",
        }
        self.assertFalse(forbidden.intersection(all_keys(proposal)))

    def test_mangacatalog_proposal_is_not_safe_filtered(self):
        changed = copy.deepcopy(self.inventory)
        for item in changed["candidates"]:
            if item["module"] == MANGACATALOG_REVIEW_MODULES[0]:
                item["contentWarning"] = "NSFW"
                break
        else:
            self.fail("Current-pin MangaCatalog proposal member is missing.")

        plan = build_plan(changed, self._get_pre_e4b_registry())
        self.assertEqual(len(plan["proposals"]), 1)
        proposal = plan["proposals"][0]
        first_member = proposal["members"][0]
        self.assertEqual(first_member["module"], MANGACATALOG_REVIEW_MODULES[0])
        self.assertEqual(first_member["contentWarning"], "NSFW")

    def test_mangacatalog_proposal_is_all_or_nothing(self):
        missing_member = copy.deepcopy(self.inventory)
        missing_module = MANGACATALOG_REVIEW_MODULES[0]
        missing_member["candidates"] = [
            item
            for item in missing_member["candidates"]
            if item["module"] != missing_module
        ]

        no_longer_e3 = copy.deepcopy(self.inventory)
        changed_module = MANGACATALOG_REVIEW_MODULES[1]
        for item in no_longer_e3["candidates"]:
            if item["module"] == changed_module:
                item["compatibility"]["extraction"] = "manual"
                break
        else:
            self.fail("Current-pin MangaCatalog proposal member is missing.")

        pre_reg = self._get_pre_e4b_registry()
        missing_plan = build_plan(missing_member, pre_reg)
        changed_plan = build_plan(no_longer_e3, pre_reg)
        self.assertEqual(missing_plan["proposals"], [])
        self.assertEqual(changed_plan["proposals"], [])
        self.assertNotIn(
            missing_module,
            {item["module"] for item in missing_plan["candidates"]},
        )
        changed_candidate = next(
            item
            for item in changed_plan["candidates"]
            if item["module"] == changed_module
        )
        self.assertEqual(changed_candidate["eligibility"], "E4")
        forbidden = {"artifactId", "runtimeKey", "importStatus"}
        self.assertFalse(forbidden.intersection(all_keys(missing_plan)))
        self.assertFalse(forbidden.intersection(all_keys(changed_plan)))


if __name__ == "__main__":
    unittest.main()
