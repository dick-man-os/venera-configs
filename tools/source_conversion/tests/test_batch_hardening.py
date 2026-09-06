import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import jsonschema
from tools.source_conversion.tests import test_eligibility_planner as fixtures
from tools.source_conversion.tests import test_materializer as transaction_fixtures
from tools.source_conversion.planner import eligibility_planner as planner
from tools.source_conversion.planner.batch_reporting import add_batch_report
from tools.source_conversion.extractor.common.locales import normalize_locale, locale_matches
from tools.source_conversion.validator.validate_batch_report import validate_batch_report, SCHEMA_PATH
from tools.source_conversion.validator.validate_ir import validate_ir_data
from tools.source_conversion.materializer import materialize as mat


class TestBatchReport(unittest.TestCase):
    def report(self, candidates, registry=None, **kwargs):
        inv = fixtures.inventory(*candidates)
        reg = registry or fixtures.registry()
        return add_batch_report(planner.build_plan(inv, reg), inv, reg, **kwargs)["batch"]

    def mixed(self):
        return [fixtures.candidate("4", "zh.generic", lang="zh"),
                fixtures.candidate("3", "en.safe", lang="en", extraction="generic"),
                fixtures.candidate("2", "zh.simplified", lang="zh-Hans", extraction="generic"),
                fixtures.candidate("1", "zh.traditional", lang="zh-Hant", extraction="generic")]

    def test_traditional_filter(self):
        report = self.report(self.mixed(), locales=["zh-Hant"])
        self.assertEqual([r["sourceId"] for r in report["candidates"]], ["1"])

    def test_simplified_filter(self):
        report = self.report(self.mixed(), locales=["zh-Hans"])
        self.assertEqual([r["sourceId"] for r in report["candidates"]], ["2"])

    def test_english_filter(self):
        self.assertEqual(self.report(self.mixed(), locales=["en"])["candidates"][0]["sourceId"], "3")

    def test_normalization_and_regional_evidence(self):
        for raw, expected in [("ZH_hANT", "zh-Hant"), ("zh-tw", "zh-TW"), ("pt-br", "pt-BR"), ("es-419", "es-419"), ("zh", "zh")]:
            self.assertEqual(normalize_locale(raw), expected)
        self.assertTrue(locale_matches("zh-TW", "zh-Hant"))
        self.assertFalse(locale_matches("zh", "zh-Hans"))
        self.assertIsNone(normalize_locale("all"))

    def test_canonical_evidence_wins_over_raw_zh(self):
        row = fixtures.candidate(lang="zh")
        row["canonicalLocale"] = "zh-Hant"
        self.assertEqual(self.report([row], locales=["zh-Hant"])["candidates"][0]["upstreamLang"], "zh")

    def test_generic_zh_not_hidden(self):
        report = self.report(self.mixed(), locales=["zh-Hant"])
        self.assertEqual(report["unresolvedLocales"][0]["sourceId"], "4")
        report = self.report(self.mixed(), locales=["zh-Hant"], include_unresolved_locales=True)
        self.assertEqual([r["sourceId"] for r in report["candidates"]], ["1", "4"])

    def test_future_locales(self):
        for locale in ["fr", "ja", "pt-BR", "es-419", "fil"]:
            row = fixtures.candidate(lang=locale, extraction="generic")
            self.assertEqual(self.report([row], locales=[locale])["candidates"][0]["state"], "ELIGIBLE")

    def test_deterministic_mixed_order_and_filters(self):
        rows = self.mixed()
        first = self.report(rows, locales=["zh-Hans", "en", "zh-Hant"])
        second = self.report(list(reversed(rows)), locales=["en", "zh-Hant", "zh-Hans", "en"])
        self.assertEqual(json.dumps(first, ensure_ascii=False), json.dumps(second, ensure_ascii=False))
        self.assertEqual([r["sourceId"] for r in first["candidates"]], ["1", "2", "3"])

    def test_eligible_requires_reviewed_identity_plan(self):
        row = self.report([fixtures.candidate(extraction="generic")])["candidates"][0]
        self.assertEqual((row["state"], row["action"]), ("ELIGIBLE", "review-create"))
        for field in ("artifactId", "runtimeKey", "providerId", "proposedLocalVersion"):
            self.assertIsNone(row[field])

    def test_unsupported_theme(self):
        row = self.report([fixtures.candidate(theme="missingfamily")])["candidates"][0]
        self.assertEqual(row["eligibility"], "E3")
        self.assertEqual(row["state"], "UNSUPPORTED_ADAPTER")
        self.assertIn("missing-family-adapter", row["reasonCodes"])

    def test_supported_theme_uses_dispatch_rules(self):
        row = self.report([fixtures.candidate(lang="zh-Hant", theme="mangacatalog")])["candidates"][0]
        self.assertEqual((row["adapter"], row["state"]), ("mangacatalog", "ELIGIBLE"))

    def test_explicit_unsupported(self):
        self.assertEqual(self.report([fixtures.candidate(extraction="unsupported")])["candidates"][0]["state"], "UNSUPPORTED_ADAPTER")

    def test_patch_required(self):
        row = self.report([fixtures.candidate(extraction="generic", patch_required=True)])["candidates"][0]
        self.assertEqual((row["state"], row["patchStatus"]), ("PATCH_REQUIRED", "PATCH_REQUIRED"))

    def test_unknown_metadata(self):
        self.assertEqual(self.report([fixtures.candidate(lang="all")])["candidates"][0]["state"], "UNRESOLVED_METADATA")

    def test_imported_kept_as_skip(self):
        row = self.report([fixtures.candidate()], fixtures.registry(fixtures.registry_artifact("local", "1")))["candidates"][0]
        self.assertEqual((row["state"], row["artifactId"], row["action"]), ("ALREADY_IMPORTED", "local", "skip"))

    def test_version_comparison_separates_upstream_and_local(self):
        for version, state, relation in [("1.0.0", "ALREADY_IMPORTED", "same"), ("1.0.10", "UPDATE_AVAILABLE", "newer"), ("0.9.9", "BLOCKED", "older")]:
            candidate = fixtures.candidate()
            candidate["version"] = version
            row = self.report([candidate], fixtures.registry(fixtures.registry_artifact("local", "1")))["candidates"][0]
            self.assertEqual((row["state"], row["versionRelation"]), (state, relation))
            self.assertIsNone(row["proposedLocalVersion"])

    def test_retired_is_blocked_without_guessing_live_health(self):
        artifact = fixtures.registry_artifact("local", "1")
        artifact["supportStatus"] = "retired"
        row = self.report([fixtures.candidate()], fixtures.registry(artifact))["candidates"][0]
        self.assertEqual((row["state"], row["health"]), ("BLOCKED", "unknown"))

    def test_shared_runtime_group_preserves_artifacts(self):
        first, second = fixtures.registry_artifact("first", "1"), fixtures.registry_artifact("second", "2")
        for row in (first, second):
            row["runtimeKey"] = "shared"
            row["providerId"] = "shared"
            row["compatibility"] = {"sharedRuntimeKeyGroup": "shared"}
        report = self.report([fixtures.candidate("1"), fixtures.candidate("2")], fixtures.registry(first, second))
        self.assertEqual([r["artifactId"] for r in report["candidates"]], ["first", "second"])
        self.assertEqual(report["sharedRuntimeKeyGroups"][0]["artifactIds"], ["first", "second"])

    def test_ambiguous_upstream_identity_fails_closed(self):
        with self.assertRaises(planner.PlannerError):
            self.report([fixtures.candidate(), fixtures.candidate()])

    def test_ambiguous_registry_ownership_fails_closed(self):
        with self.assertRaises(planner.PlannerError):
            self.report([fixtures.candidate()], fixtures.registry(fixtures.registry_artifact("one", "1"), fixtures.registry_artifact("two", "1")))

    def test_one_scan_failure_retains_other_candidates(self):
        rows = self.mixed()
        report = self.report(rows, scan_errors={("module", fixtures.PROJECT, "zh.traditional"): ("upstream-source-read-failed",)})
        self.assertEqual([r["state"] for r in report["candidates"]][:3], ["ERROR", "ELIGIBLE", "ELIGIBLE"])

    def test_scan_isolation_and_legacy_strict_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src/en/good").mkdir(parents=True)
            (root / "src/en/good/source.kt").write_text("val password = 1")
            inv = fixtures.inventory(fixtures.candidate("1", "en.missing"), fixtures.candidate("2", "en.good"))
            errors = {}
            modules, _ = planner.scan_upstream_capabilities(root, inv, fixtures.PROJECT, errors=errors)
            self.assertIn(("module", fixtures.PROJECT, "en.missing"), errors)
            self.assertIn("credentials-or-token-flow", modules[(fixtures.PROJECT, "en.good")])
            with self.assertRaises(planner.PlannerError):
                planner.scan_upstream_capabilities(root, inv, fixtures.PROJECT)

    def test_lexical_flags_are_review_evidence(self):
        inv = fixtures.inventory(fixtures.candidate())
        reg = fixtures.registry()
        base = planner.build_plan(inv, reg, module_signals={(fixtures.PROJECT, "en.sample"): ["webview-or-quickjs", "credentials-or-token-flow"]})
        row = add_batch_report(base, inv, reg)["batch"]["candidates"][0]
        self.assertTrue(row["authReview"] and row["jsHeavyReview"])
        self.assertIsNone(row["authRequired"])
        self.assertEqual(row["eligibility"], "E6")

    def test_content_warning_preserved_for_all_locales(self):
        for locale in ("zh-Hant", "zh-Hans", "en", "fr"):
            row = fixtures.candidate(lang=locale, content_warning="NSFW", extraction="generic")
            self.assertEqual(self.report([row])["candidates"][0]["contentWarning"], "NSFW")

    def test_eligibility_and_source_selection(self):
        report = self.report(self.mixed(), eligibility=["E1"], source_ids=["2"])
        self.assertEqual([r["sourceId"] for r in report["candidates"]], ["2"])

    def test_invalid_locale_filter_rejected(self):
        with self.assertRaises(planner.PlannerError):
            self.report(self.mixed(), locales=["all"])

    def test_schema_and_semantic_validation(self):
        report = self.report(self.mixed())
        jsonschema.Draft202012Validator(json.loads(SCHEMA_PATH.read_text())).validate(report)
        self.assertEqual(validate_batch_report(report), [])
        bad = copy.deepcopy(report)
        bad["candidates"][0]["action"] = "publish"
        self.assertTrue(validate_batch_report(bad))
        bad = copy.deepcopy(report)
        bad["summary"]["candidates"] += 1
        self.assertTrue(validate_batch_report(bad))
        bad = copy.deepcopy(report)
        bad["publication"]["manifest"] = ["unexpected.js"]
        self.assertTrue(validate_batch_report(bad))

    def test_report_is_read_only_and_has_no_proposed_production_delta(self):
        report = self.report(self.mixed())
        self.assertEqual(report["publication"], {"mode":"read-only", "manifest":[], "registryDelta":[], "indexDelta":[]})

    def test_local_patch_and_catalog_overrides_are_retained(self):
        artifact = fixtures.registry_artifact("local", "1")
        artifact.update({"catalogName":"自訂名稱", "catalogDescription":"自訂說明", "implementation":{"producer":"generated-with-patch"}})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sources_patches").mkdir()
            (root / "sources_ir").mkdir()
            (root / "sources_patches/local.patch.js").write_text("custom patch")
            (root / "local.js").write_text('class Source extends ComicSource {\n name = "Name"\n key = "local"\n version = "1.2.3"\n}')
            (root / "sources_ir/local.json").write_text('{"requiresAuth":true}')
            before = {p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()}
            report = self.report([fixtures.candidate()], fixtures.registry(artifact), repo_root=root)
            row = report["candidates"][0]
            self.assertEqual((row["patchStatus"],row["catalogName"]), ("PATCH_EXISTS","自訂名稱"))
            self.assertTrue(row["authRequired"])
            self.assertEqual(before, {p.relative_to(root):p.read_bytes() for p in root.rglob("*") if p.is_file()})


    def test_batch_cli_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inv, reg = root / "inventory.json", root / "sources_registry.json"
            inv.write_text(json.dumps(fixtures.inventory(*self.mixed())))
            reg.write_text(json.dumps(fixtures.registry()))
            before = {path.name:path.read_bytes() for path in root.iterdir()}
            out, err = io.StringIO(), io.StringIO()
            with patch.object(planner, "validate_upstream_checkout"), patch.object(planner, "scan_upstream_capabilities", return_value=({}, {})), redirect_stdout(out), redirect_stderr(err):
                result = planner.main(["--inventory",str(inv),"--registry",str(reg),"--extensions-root",str(root),"--locale","zh-Hant"])
            self.assertEqual(result, 0, err.getvalue())
            report = json.loads(out.getvalue())
            self.assertEqual(report["schemaVersion"], "1.1")
            self.assertEqual(report["batch"]["summary"]["candidates"], 1)
            self.assertEqual(before, {path.name:path.read_bytes() for path in root.iterdir()})

    def test_unreadable_source_does_not_erase_good_module_signals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("good", "bad"):
                (root / f"src/en/{name}").mkdir(parents=True)
            (root / "src/en/bad/Source.kt").write_bytes(b"\xff\xfe")
            (root / "src/en/good/Source.kt").write_text("val password = 1")
            inv = fixtures.inventory(fixtures.candidate("1","en.bad"), fixtures.candidate("2","en.good"))
            errors = {}
            signals, _ = planner.scan_upstream_capabilities(root, inv, fixtures.PROJECT, errors=errors)
            self.assertEqual(errors[("module", fixtures.PROJECT, "en.bad")], ("upstream-source-read-failed",))
            self.assertIn("credentials-or-token-flow", signals[(fixtures.PROJECT,"en.good")])

    def test_malformed_local_ir_is_a_source_error(self):
        artifact = fixtures.registry_artifact("local", "1")
        artifact["implementation"] = {"producer":"generated"}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "sources_ir").mkdir()
            (root / "local.js").write_text('class Source extends ComicSource {\n name = "Name"\n key = "local"\n version = "1.2.3"\n}')
            (root / "sources_ir/local.json").write_text("[]")
            report = self.report([fixtures.candidate(), fixtures.candidate("2", "en.good", extraction="generic")], fixtures.registry(artifact), repo_root=root)
            self.assertEqual([row["state"] for row in report["candidates"]], ["ERROR", "ELIGIBLE"])


class TestBatchTransactionSafety(transaction_fixtures.RealMaterializerTestBase):
    def run_mode(self, mode, digest=None):
        args = ["--mode", mode, "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)]
        if digest is not None:
            args += ["--expected-digest", digest]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = mat.main(args)
        marker = '{\n  "mode"'
        report = json.loads(out.getvalue()[out.getvalue().index(marker):]) if marker in out.getvalue() else None
        return status, report, err.getvalue()

    def test_create_requires_reviewed_digest(self):
        before = self._snapshot_live_tree()
        status, _, err = self.run_mode("write")
        self.assertEqual(status, 1)
        self.assertIn("requires --expected-digest", err)
        self.assertEqual(before, self._snapshot_live_tree())

    def test_create_rejects_wrong_digest(self):
        status, _, err = self.run_mode("write", "wrong")
        self.assertEqual(status, 1)
        self.assertIn("expected digest", err)
        self._assert_no_real_outputs()

    def test_create_binds_inventory_bytes(self):
        status, report, err = self.run_mode("check")
        self.assertEqual(status, 0, err)
        self.inventory_path.write_bytes(self.inventory_path.read_bytes() + b" ")
        status, _, err = self.run_mode("write", report["transactionDigest"])
        self.assertEqual(status, 1)
        self.assertIn("expected digest", err)
        self._assert_no_real_outputs()

    def test_create_binds_patch_set(self):
        status, report, err = self.run_mode("check")
        self.assertEqual(status, 0, err)
        (self.repo_root / "sources_patches").mkdir()
        (self.repo_root / "sources_patches/existing.patch.js").write_text("// reviewed custom code")
        status, _, err = self.run_mode("write", report["transactionDigest"])
        self.assertEqual(status, 1)
        self.assertIn("expected digest", err)

    def test_exact_manifest_and_deltas_match_written_bytes(self):
        before = self._snapshot_live_tree()
        status, report, err = self.run_mode("check")
        self.assertEqual(status, 0, err)
        self.assertEqual(before, self._snapshot_live_tree())
        expected = ["index.json", "sources_generated/test_artifact.base.js", "sources_ir/test_artifact.json", "sources_registry.json", "test_artifact.js"]
        self.assertEqual([r["relativePath"] for r in report["targets"]], expected)
        self.assertEqual([r["identity"] for r in report["registryDelta"]], ["test_artifact"])
        self.assertEqual([r["identity"] for r in report["indexDelta"]], ["test_artifact.js"])
        self.assertEqual(report["digestVersion"], "2")
        schema = json.loads(SCHEMA_PATH.with_name("materialization_report.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(report)
        self.assertIn("tools/source_conversion/inventory/upstream_inventory.json", [r["relativePath"] for r in report["reviewState"]])
        status, written, err = self.run_mode("write", report["transactionDigest"])
        self.assertEqual(status, 0, err)
        self.assertEqual(report["targets"], written["targets"])
        self.assertEqual(report["registryDelta"][0]["after"], self.read_json(self.repo_root / "sources_registry.json")["artifacts"][-1])

    def test_candidate_failures_are_all_reported_with_no_publication(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"].append({"sourceId":"5678", "artifactId":"second", "providerId":"second", "localVersion":"1.0.0"})
        self.write_json(self.plan_path, plan)
        calls = []
        def fail(item, *args):
            calls.append(item["sourceId"])
            raise ValueError("synthetic extraction failure")
        before = self._snapshot_live_tree()
        with patch.object(mat, "_extract_to_temp", side_effect=fail):
            status, _, err = self.run_mode("check")
        self.assertEqual(status, 1)
        self.assertEqual(sorted(calls), ["1234", "5678"])
        self.assertIn("sourceId=1234", err)
        self.assertIn("sourceId=5678", err)
        self.assertEqual(before, self._snapshot_live_tree())

    def test_review_digest_binds_tooling(self):
        state = mat._capture_preflight_fingerprint(self.repo_root)
        key = "tools/source_conversion/generator/js_generator.py"
        self.assertIn(key, state)
        plan = mat._parse_plan(self.plan_path)
        first = mat._review_digest(plan, [], state)
        state[key] = "0" * 64
        self.assertNotEqual(first, mat._review_digest(plan, [], state))


    def test_missing_extracted_source_id_is_rejected(self):
        ir = copy.deepcopy(self.valid_ir_template)
        ir["provenance"].pop("upstreamSourceId", None)
        with self.assertRaisesRegex(mat.MaterializationError, "sourceId"):
            mat._validate_extracted_identity(self.valid_plan["artifacts"][0], self.valid_inventory["candidates"][0], ir, self.valid_plan)

    def test_raw_locale_mismatch_is_rejected_without_canonical_field(self):
        ir = copy.deepcopy(self.valid_ir_template)
        candidate = copy.deepcopy(self.valid_inventory["candidates"][0])
        candidate.pop("canonicalLocale")
        candidate.pop("version")
        candidate["upstreamLang"] = "zh-Hant"
        with self.assertRaisesRegex(mat.MaterializationError, "languages"):
            mat._validate_extracted_identity(self.valid_plan["artifacts"][0], candidate, ir, self.valid_plan)

    def test_permuted_batch_plan_has_identical_check_bytes(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"].append({"sourceId":"5678","artifactId":"second","providerId":"second","localVersion":"1.0.0"})
        def extract(item, candidate, timestamp, extensions_root):
            ir = copy.deepcopy(self.valid_ir_template)
            ir.update({"artifactId":item["artifactId"],"id":"source_"+item["sourceId"],"version":item["localVersion"]})
            ir["provenance"].update({"upstreamSourceId":item["sourceId"],"upstreamVersion":candidate.get("version","1.2.3")})
            return ir
        with patch.object(mat, "_extract_to_temp", side_effect=extract):
            self.write_json(self.plan_path, plan)
            status, first, err = self.run_mode("check")
            self.assertEqual(status, 0, err)
            plan["artifacts"].reverse()
            self.write_json(self.plan_path, plan)
            status, second, err = self.run_mode("check")
            self.assertEqual(status, 0, err)
        self.assertEqual(json.dumps(first), json.dumps(second))


    def test_create_supplies_source_mobile_url_without_changing_legacy_ir(self):
        for locale in ("zh-Hant", "zh-Hans", "en", "fr"):
            source_ir = copy.deepcopy(self.valid_ir_template)
            source_ir["languages"] = [locale]
            source_ir.pop("mobileUrl", None)
            with patch.object(mat, "dispatch_extraction", return_value=copy.deepcopy(source_ir)):
                prepared = mat._extract_to_temp(
                    self.valid_plan["artifacts"][0],
                    self.valid_inventory["candidates"][0],
                    self.valid_plan["generatedTimestamp"], self.extensions_root)
            self.assertEqual(prepared["mobileUrl"], source_ir["baseUrl"])
            self.assertNotIn("mobileUrl", source_ir)

    def test_check_stdout_is_byte_deterministic_and_parseable_json(self):
        outputs = []
        arguments = ["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)]
        for _ in range(2):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = mat.main(arguments)
            self.assertEqual(status, 0, err.getvalue())
            json.loads(out.getvalue())
            outputs.append(out.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        self.assertNotIn(str(self.repo_root), outputs[0])


class TestLocaleExtraction(unittest.TestCase):
    def test_ir_language_schema_accepts_future_locales(self):
        base = json.loads((fixtures.REPO_ROOT / "tools/source_conversion/tests/fixtures/v0.2_ir.json").read_text())
        for locale in ("zh", "zh-Hant", "zh-Hans", "en", "fr", "es-419", "pt-BR"):
            base["languages"] = [locale]
            self.assertFalse([error for error in validate_ir_data(base) if "language" in error])
        for locale in ("all", "other", "zh-hant", "xx_YY"):
            base["languages"] = [locale]
            self.assertTrue([error for error in validate_ir_data(base) if "language" in error])

    def test_generic_identity_and_language_use_selected_source(self):
        from generic_html_extractor import extract
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Source.kt"
            path.write_text("package sample\nclass Source : KeiSource() {}")
            meta = {"libVersion":"1.6", "version":"1.6.1", "contentWarning":"NSFW", "sources":[
                {"name":"漫畫甲", "lang":"zh-Hant", "sourceId":"1", "baseUrl":"https://example.test", "baseUrlResolved":True},
                {"name":"漫畫乙", "lang":"zh-Hans", "sourceId":"2", "baseUrl":"https://example.test", "baseUrlResolved":True}]}
            first = extract(str(path), meta, "2026-01-01T00:00:00Z", "all", source_id="1")
            second = extract(str(path), meta, "2026-01-01T00:00:00Z", "all", source_id="2")
            self.assertEqual(first["languages"], ["zh-Hant"])
            self.assertEqual(second["languages"], ["zh-Hans"])
            self.assertNotEqual(first["id"], second["id"])
            meta["sources"][0]["name"] = "改名"
            renamed = extract(str(path), meta, "2026-01-01T00:00:00Z", "all", source_id="1")
            self.assertEqual(first["id"], renamed["id"])

    def test_generic_file_fallback_is_sorted(self):
        from tools.source_conversion.extractor import extract as dispatcher
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "src/en/sample"
            (source / "src").mkdir(parents=True)
            (source / "build.gradle.kts").write_text("// fixture")
            for name in ("Z.kt", "A.kt"):
                (source / "src" / name).write_text("class Source")
            with patch.object(dispatcher.os, "walk", return_value=[(str(source / "src"), [], ["Z.kt", "A.kt"])]), patch("generic_html_extractor.extract", return_value={"provenance":{}}) as extract, patch("subprocess.check_output", return_value="a"*40):
                dispatcher.extract_generic(str(root), "en/sample", timestamp="2026-01-01T00:00:00Z", gradle_meta={})
            self.assertEqual(Path(extract.call_args.args[0]).name, "A.kt")
