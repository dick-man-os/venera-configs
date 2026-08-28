import copy
import json
import os
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import tools.source_conversion.materializer.materialize as mat

class MaterializerTestBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.repo_root = self.root / "venera-configs"
        self.repo_root.mkdir()

        self.extensions_root = self.root / "extensions-source"
        self.extensions_root.mkdir()

        subprocess.run(["git", "init"], cwd=str(self.extensions_root), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (self.extensions_root / "dummy.txt").write_text("hello")
        subprocess.run(["git", "add", "dummy.txt"], cwd=str(self.extensions_root), check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"], cwd=str(self.extensions_root), check=True, stdout=subprocess.DEVNULL)

        self.commit_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(self.extensions_root), text=True).strip()

        self.plan_path = self.root / "plan.json"

        self.inventory_dir = self.repo_root / "tools" / "source_conversion" / "inventory"
        self.inventory_dir.mkdir(parents=True)
        self.inventory_path = self.inventory_dir / "upstream_inventory.json"

        self.valid_plan = {
            "schemaVersion": "1",
            "upstream": {
                "project": "keiyoushi/extensions-source",
                "commit": self.commit_hash
            },
            "generatedTimestamp": "2023-01-01T00:00:00Z",
            "artifacts": [
                {
                    "sourceId": "1234",
                    "artifactId": "test_artifact",
                    "providerId": "test_provider",
                    "localVersion": "1.0.0"
                }
            ]
        }

        self.valid_inventory = {
            "schemaVersion": "0.1",
            "upstreams": [
                {
                    "project": "keiyoushi/extensions-source",
                    "commit": self.commit_hash
                }
            ],
            "candidates": [
                {
                    "project": "keiyoushi/extensions-source",
                    "sourceId": 1234,
                    "module": "en.testsource",
                    "extensionLib": "1.4",
                    "name": "Test Source",
                    "upstreamLang": "en",
                    "compatibility": "COMPATIBLE"
                },
                {
                    "project": "keiyoushi/extensions-source",
                    "sourceId": 5678,
                    "module": "en.testsource2",
                    "extensionLib": "1.4",
                    "name": "Test Source 2",
                    "upstreamLang": "en",
                    "compatibility": "COMPATIBLE"
                }
            ]
        }

        self.valid_ir_template = {
            "schemaVersion": "0.2",
            "artifactId": "test_artifact",
            "id": "en_test_artifact",
            "version": "1.0.0",
            "name": "Test Source",
            "languages": ["en"],
            "contentOrigins": ["JP"],
            "contentWarning": "SAFE",
            "sourceType": "api",
            "baseUrl": "https://test.com",
            "explore": {
                "popular": {
                    "url": "https://test.com/popular",
                    "method": "GET",
                    "selector": ".popular",
                    "fields": {"title": ".title", "url": "@href", "thumbnail": "img@src"}
                }
            },
            "search": {
                "url": "https://test.com/search",
                "method": "GET",
                "selector": ".search",
                "fields": {"title": ".title", "url": "@href", "thumbnail": "img@src"}
            },
            "details": {
                "url": "https://test.com/details",
                "method": "GET",
                "selector": ".details",
                "fields": {"title": ".title", "thumbnail": "img@src"}
            },
            "chapters": {
                "url": "https://test.com/chapters",
                "method": "GET",
                "selector": ".chapters",
                "fields": {"name": ".name", "url": "@href"}
            },
            "pages": {
                "url": "https://test.com/pages",
                "method": "GET",
                "selector": ".pages",
                "fields": {"url": "img@src"}
            },
            "provenance": {
                "type": "converted",
                "upstreamProject": "keiyoushi",
                "upstreamPackage": "eu.kanade.tachiyomi.extension.en.test",
                "upstreamCommit": "1234567890abcdef1234567890abcdef12345678",
                "upstreamVersion": "1.2.3",
                "upstreamLicense": "Apache-2.0",
                "converterVersion": "0.1.0",
                "generatedTimestamp": "2023-01-01T00:00:00Z"
            }
        }

        self.write_json(self.plan_path, self.valid_plan)
        self.write_json(self.inventory_path, self.valid_inventory)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_json(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def read_json(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

class TestPlanParsing(MaterializerTestBase):
    def test_valid_plan_parsing(self):
        plan = mat._parse_plan(self.plan_path)
        self.assertEqual(plan["schemaVersion"], "1")

    def test_unknown_top_level_field(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["unknown"] = "value"
        self.write_json(self.plan_path, plan)
        with self.assertRaisesRegex(mat.MaterializationError, "Unknown top-level field"):
            mat._parse_plan(self.plan_path)

    def test_unknown_artifact_field(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"][0]["unknown"] = "value"
        self.write_json(self.plan_path, plan)
        with self.assertRaisesRegex(mat.MaterializationError, "Unknown artifact field"):
            mat._parse_plan(self.plan_path)

    def test_unknown_upstream_field(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["upstream"]["unknown"] = "value"
        self.write_json(self.plan_path, plan)
        with self.assertRaisesRegex(mat.MaterializationError, "Unknown upstream field"):
            mat._parse_plan(self.plan_path)

    def test_valid_utc_timestamp(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["generatedTimestamp"] = "2024-05-10T12:34:56Z"
        self.write_json(self.plan_path, plan)
        mat._parse_plan(self.plan_path)

    def test_invalid_utc_timestamp(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["generatedTimestamp"] = "2024-05-10 12:34:56"
        self.write_json(self.plan_path, plan)
        with self.assertRaisesRegex(mat.MaterializationError, "must be in strict"):
            mat._parse_plan(self.plan_path)

    def test_duplicate_artifact_id_in_plan(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"].append(copy.deepcopy(plan["artifacts"][0]))
        plan["artifacts"][1]["sourceId"] = "5678"
        self.write_json(self.plan_path, plan)
        with self.assertRaisesRegex(mat.MaterializationError, "Duplicate artifactId"):
            mat._parse_plan(self.plan_path)

    def test_duplicate_source_id_in_plan(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"].append(copy.deepcopy(plan["artifacts"][0]))
        plan["artifacts"][1]["artifactId"] = "other_artifact"
        self.write_json(self.plan_path, plan)
        with self.assertRaisesRegex(mat.MaterializationError, "Duplicate sourceId"):
            mat._parse_plan(self.plan_path)

class TestInventoryResolution(MaterializerTestBase):
    def test_non_compatible_candidate_rejection(self):
        inv = copy.deepcopy(self.valid_inventory)
        inv["candidates"][0]["compatibility"] = "PATCH_REQUIRED"
        self.write_json(self.inventory_path, inv)
        with self.assertRaisesRegex(mat.MaterializationError, "is not COMPATIBLE"):
            mat._resolve_candidates(self.valid_plan, self.inventory_path)

    def test_dirty_upstream_checkout_rejects(self):
        (self.extensions_root / "dirty.txt").write_text("dirty")
        subprocess.run(["git", "add", "dirty.txt"], cwd=str(self.extensions_root), check=True)
        with self.assertRaisesRegex(mat.MaterializationError, "Extensions checkout is dirty"):
            mat._verify_extensions_checkout(self.extensions_root, self.commit_hash)

    def test_upstream_head_mismatch_rejects(self):
        with self.assertRaisesRegex(mat.MaterializationError, "does not match expected"):
            mat._verify_extensions_checkout(self.extensions_root, "invalidhash")

class TestExtractionAndInjection(MaterializerTestBase):
    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_canonical_dispatch_function_used(self, mock_dispatch):
        ir = copy.deepcopy(self.valid_ir_template)
        ir["name"] = "IR Name"
        ir["provenance"]["upstreamVersion"] = "1.2.3"
        ir["sourceType"] = "api"
        ir["languages"] = ["en"]
        mock_dispatch.return_value = ir
        candidate = self.valid_inventory["candidates"][0]

        ir_data = mat._extract_to_temp(self.valid_plan["artifacts"][0], candidate, "time", self.extensions_root)

        self.assertEqual(ir_data["artifactId"], "test_artifact")
        self.assertEqual(ir_data["version"], "1.0.0")
        mock_dispatch.assert_called_once()

class TestRegistryConstruction(MaterializerTestBase):
    def test_registry_derives_authoritative_metadata(self):
        ir = copy.deepcopy(self.valid_ir_template)
        ir["name"] = "IR Name"
        ir["provenance"]["upstreamVersion"] = "1.2.3"
        ir["sourceType"] = "api"
        ir["languages"] = ["en"]

        cand = {"module": "en/test"}
        plan_item = self.valid_plan["artifacts"][0]
        rec = mat._build_registry_record(plan_item, cand, ir, {"key": "test_key"}, self.valid_plan)
        self.assertEqual(rec["catalogName"], "IR Name")
        self.assertEqual(rec["runtimeKey"], "test_key")
        self.assertEqual(rec["upstream"]["version"], "1.2.3")
        self.assertEqual(rec["implementation"]["transport"], "api")

    def test_missing_authoritative_transport_rejects(self):
        ir = copy.deepcopy(self.valid_ir_template)
        del ir["sourceType"]

        cand = {"module": "en/test"}
        plan_item = self.valid_plan["artifacts"][0]
        with self.assertRaisesRegex(mat.MaterializationError, "Missing authoritative sourceType"):
            mat._build_registry_record(plan_item, cand, ir, {"key": "test_key"}, self.valid_plan)

class TestIntegration(MaterializerTestBase):
    def setUp(self):
        super().setUp()
        self.write_json(self.repo_root / "sources_registry.json", {"schemaVersion": "1.0", "artifacts": []})
        self.write_json(self.repo_root / "index.json", [])

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_check_mode_zero_live_writes(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        ret = mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 0)

        self.assertFalse((self.repo_root / "test_artifact.js").exists())
        self.assertFalse((self.repo_root / "sources_ir" / "test_artifact.json").exists())
        self.assertFalse((self.repo_root / "sources_generated" / "test_artifact.base.js").exists())

        registry = self.read_json(self.repo_root / "sources_registry.json")
        self.assertEqual(len(registry["artifacts"]), 0)

        index = self.read_json(self.repo_root / "index.json")
        self.assertEqual(len(index), 0)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_write_mode_integration(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 0)

        self.assertTrue((self.repo_root / "test_artifact.js").exists())
        self.assertTrue((self.repo_root / "sources_ir" / "test_artifact.json").exists())
        self.assertTrue((self.repo_root / "sources_generated" / "test_artifact.base.js").exists())

        registry = self.read_json(self.repo_root / "sources_registry.json")
        self.assertEqual(len(registry["artifacts"]), 1)
        self.assertEqual(registry["artifacts"][0]["artifactId"], "test_artifact")
        self.assertEqual(registry["artifacts"][0]["upstream"]["version"], "1.2.3")

        index = self.read_json(self.repo_root / "index.json")
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["fileName"], "test_artifact.js")

        base_js = (self.repo_root / "sources_generated" / "test_artifact.base.js").read_bytes()
        final_js = (self.repo_root / "test_artifact.js").read_bytes()
        self.assertEqual(base_js, final_js)

        for p in self.repo_root.rglob("*.tmp"):
            self.fail(f"Temp sibling remains: {p}")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_multi_artifact_transaction(self, mock_dispatch):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"].append({
            "sourceId": "5678",
            "artifactId": "test_artifact_2",
            "providerId": "test_provider",
            "localVersion": "1.0.0"
        })
        self.write_json(self.plan_path, plan)

        def mock_dispatch_fn(extensions_root, source_path, timestamp, language_override, source_id, **kwargs):
            ir = copy.deepcopy(self.valid_ir_template)
            if source_id == 1234 or source_id == "1234":
                ir["id"] = "en_test_source_1"
                ir["name"] = "Test Source 1"
                ir["artifactId"] = "test_artifact"
            else:
                ir["id"] = "en_test_source_2"
                ir["name"] = "Test Source 2"
                ir["artifactId"] = "test_artifact_2"
            return ir

        mock_dispatch.side_effect = mock_dispatch_fn

        ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 0)

        self.assertTrue((self.repo_root / "test_artifact.js").exists())
        self.assertTrue((self.repo_root / "test_artifact_2.js").exists())

        registry = self.read_json(self.repo_root / "sources_registry.json")
        self.assertEqual(len(registry["artifacts"]), 2)

        index = self.read_json(self.repo_root / "index.json")
        self.assertEqual(len(index), 2)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_stale_registry_bytes_aborts(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        orig_bytes = (self.repo_root / "sources_registry.json").read_bytes()

        def mock_promote(*args, **kwargs):
            (self.repo_root / "sources_registry.json").write_text(json.dumps({"schemaVersion": "1.0", "artifacts": [{"fake": "data"}]}))
            mat._promote_transaction_orig(*args, **kwargs)

        mat._promote_transaction_orig = mat._promote_transaction
        with patch('tools.source_conversion.materializer.materialize._promote_transaction', side_effect=mock_promote):
            ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            self.assertNotEqual(ret, 0)

        self.assertFalse((self.repo_root / "test_artifact.js").exists())

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_stale_index_bytes_aborts(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        def mock_promote(*args, **kwargs):
            (self.repo_root / "index.json").write_text(json.dumps([{"fake": "data"}]))
            mat._promote_transaction_orig(*args, **kwargs)

        mat._promote_transaction_orig = mat._promote_transaction
        with patch('tools.source_conversion.materializer.materialize._promote_transaction', side_effect=mock_promote):
            ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            self.assertNotEqual(ret, 0)

        self.assertFalse((self.repo_root / "test_artifact.js").exists())

    def test_rollback_removes_all_outputs(self):
        plan = copy.deepcopy(self.valid_plan)
        td = Path(self.temp_dir.name) / "trans"
        td.mkdir()

        (td / "sources_ir").mkdir(parents=True)
        (td / "sources_ir" / "test_artifact.json").write_text("{}")
        (td / "sources_generated").mkdir(parents=True)
        (td / "sources_generated" / "test_artifact.base.js").write_text("")
        (td / "test_artifact.js").write_text("")
        (td / "sources_registry.json").write_text("{}")
        (td / "index.json").write_text("[]")

        ctx = mat.TransactionContext(self.repo_root, "")

        (self.repo_root / "unrelated").mkdir()
        (self.repo_root / "unrelated" / "file.txt").write_text("keep")

        orig_reg_bytes = (self.repo_root / "sources_registry.json").read_bytes()
        orig_idx_bytes = (self.repo_root / "index.json").read_bytes()

        orig_replace = os.replace
        def fail_on_js(src, dst):
            if str(dst).endswith(".js") and not str(dst).endswith("base.js"):
                raise Exception("mock fail on js")
            orig_replace(src, dst)

        with patch('os.replace', side_effect=fail_on_js):
            with self.assertRaisesRegex(mat.MaterializationError, "rollback successful"):
                mat._promote_transaction(self.repo_root, td, plan, ctx.preflight_fingerprint)

        self.assertFalse((self.repo_root / "test_artifact.js").exists())
        self.assertFalse((self.repo_root / "sources_ir" / "test_artifact.json").exists())
        self.assertFalse((self.repo_root / "sources_generated" / "test_artifact.base.js").exists())

        for p in self.repo_root.rglob("*.tmp"):
            self.fail(f"Temp sibling remains: {p}")

        self.assertTrue((self.repo_root / "unrelated" / "file.txt").exists())

        self.assertEqual((self.repo_root / "sources_registry.json").read_bytes(), orig_reg_bytes)
        self.assertEqual((self.repo_root / "index.json").read_bytes(), orig_idx_bytes)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_target_appearing_after_preflight_aborts(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        def mock_promote(*args, **kwargs):
            (self.repo_root / "test_artifact.js").write_text("sneaky")
            mat._promote_transaction_orig(*args, **kwargs)

        mat._promote_transaction_orig = mat._promote_transaction
        with patch('tools.source_conversion.materializer.materialize._promote_transaction', side_effect=mock_promote):
            ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            self.assertNotEqual(ret, 0)

        self.assertEqual((self.repo_root / "test_artifact.js").read_text(), "sneaky")

    def test_collision_existing_registry_artifact(self):
        reg = self.read_json(self.repo_root / "sources_registry.json")
        reg["artifacts"].append({"artifactId": "test_artifact"})
        self.write_json(self.repo_root / "sources_registry.json", reg)
        with self.assertRaisesRegex(mat.MaterializationError, "already exists in registry"):
            mat._check_collisions(self.valid_plan, self.repo_root)

    def test_collision_existing_js(self):
        (self.repo_root / "test_artifact.js").write_text("")
        with self.assertRaisesRegex(mat.MaterializationError, "already exists in repository root"):
            mat._check_collisions(self.valid_plan, self.repo_root)

    def test_collision_existing_ir(self):
        (self.repo_root / "sources_ir").mkdir()
        (self.repo_root / "sources_ir" / "test_artifact.json").write_text("")
        with self.assertRaisesRegex(mat.MaterializationError, "sources_ir/test_artifact.json already exists"):
            mat._check_collisions(self.valid_plan, self.repo_root)

    def test_collision_existing_base_js(self):
        (self.repo_root / "sources_generated").mkdir()
        (self.repo_root / "sources_generated" / "test_artifact.base.js").write_text("")
        with self.assertRaisesRegex(mat.MaterializationError, "sources_generated/test_artifact.base.js already exists"):
            mat._check_collisions(self.valid_plan, self.repo_root)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_manual_patch_required_fails(self, mock_dispatch):
        ir = copy.deepcopy(self.valid_ir_template)
        ir["manualPatchRequired"] = True
        mock_dispatch.return_value = ir

        ret = mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertNotEqual(ret, 0)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_digest_temp_root_stability(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        with patch('sys.stdout', new_callable=tempfile.SpooledTemporaryFile, mode='w+') as mock_stdout:
            mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            mock_stdout.seek(0)
            out1 = mock_stdout.read()

        digest1 = None
        for line in out1.splitlines():
            if '"transactionDigest"' in line:
                digest1 = line.split('"')[3]
                break

        with patch('sys.stdout', new_callable=tempfile.SpooledTemporaryFile, mode='w+') as mock_stdout:
            mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            mock_stdout.seek(0)
            out2 = mock_stdout.read()

        digest2 = None
        for line in out2.splitlines():
            if '"transactionDigest"' in line:
                digest2 = line.split('"')[3]
                break

        self.assertIsNotNone(digest1)
        self.assertEqual(digest1, digest2)

    def test_proposed_linkage_ir_artifact_missing(self):
        from tools.source_conversion.validator.validate_registry import _validate_ir_linkage

        td = Path(self.temp_dir.name) / "trans"
        td.mkdir()
        (td / "sources_ir").mkdir()
        ir = copy.deepcopy(self.valid_ir_template)
        del ir["artifactId"]
        self.write_json(td / "sources_ir" / "test_artifact.json", ir)

        artifacts_by_id = {"test_artifact": {"artifactId": "test_artifact"}}
        diagnostics = []
        _validate_ir_linkage(diagnostics, td, artifacts_by_id)

        self.assertTrue(any(d.code == "IR_ARTIFACT_LINK_MISSING" for d in diagnostics))

    def test_proposed_linkage_registry_ir_missing(self):
        from tools.source_conversion.validator.validate_registry import _validate_ir_linkage

        td = Path(self.temp_dir.name) / "trans"
        td.mkdir()
        (td / "sources_ir").mkdir()

        artifacts_by_id = {"test_artifact": {"artifactId": "test_artifact", "implementation": {"producer": "generated"}}}
        diagnostics = []
        _validate_ir_linkage(diagnostics, td, artifacts_by_id)

        self.assertTrue(any(d.code == "REGISTRY_IR_LINK_MISSING" for d in diagnostics))

if __name__ == '__main__':
    unittest.main()
