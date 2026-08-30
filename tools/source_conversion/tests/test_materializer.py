import copy
import hashlib
import inspect
import io
import json
import os
import shutil
import tempfile
import unittest
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch, MagicMock

import tools.source_conversion.materializer.materialize as mat

REPO_ROOT = Path(__file__).resolve().parents[3]

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
            "schemaVersion": "1.0",
            "upstreams": [
                {
                    "project": "keiyoushi/extensions-source",
                    "commit": self.commit_hash
                }
            ],
            "candidates": [
                {
                    "project": "keiyoushi/extensions-source",
                    "sourceId": "1234",
                    "module": "en.testsource",
                    "extensionLib": "1.4",
                    "name": "Test Source",
                    "upstreamLang": "en",
                    "compatibility": {
                        "metadataResolution": "static",
                        "extraction": "generic",
                        "patchRequired": False
                    }
                },
                {
                    "project": "keiyoushi/extensions-source",
                    "sourceId": "5678",
                    "module": "en.testsource2",
                    "extensionLib": "1.4",
                    "name": "Test Source 2",
                    "upstreamLang": "en",
                    "compatibility": {
                        "metadataResolution": "static",
                        "extraction": "generic",
                        "patchRequired": False
                    }
                }
            ],
            "unresolvedModules": []
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
        self.valid_ir_template["provenance"]["upstreamCommit"] = self.commit_hash

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
        inv["candidates"][0]["compatibility"]["extraction"] = "unsupported"
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [{
                "artifactId": "existing",
                "runtimeKey": "existing",
                "providerId": "existing",
                "implementation": {"producer": "manual"}
            }]
        }
        with self.assertRaisesRegex(mat.MaterializationError, "canonical route E5"):
            mat._resolve_candidates(self.valid_plan, inv, registry)

    def test_dirty_upstream_checkout_rejects(self):
        (self.extensions_root / "dirty.txt").write_text("dirty")
        subprocess.run(["git", "add", "dirty.txt"], cwd=str(self.extensions_root), check=True)
        with self.assertRaisesRegex(mat.MaterializationError, "WORKTREE_DIRTY"):
            mat._verify_extensions_checkout(
                self.extensions_root,
                self.valid_inventory,
                "keiyoushi/extensions-source",
                self.commit_hash,
            )

    def test_upstream_head_mismatch_rejects(self):
        inventory = copy.deepcopy(self.valid_inventory)
        inventory["upstreams"][0]["commit"] = "0" * 40
        with self.assertRaisesRegex(mat.MaterializationError, "UPSTREAM_PIN_MISMATCH"):
            mat._verify_extensions_checkout(
                self.extensions_root,
                inventory,
                "keiyoushi/extensions-source",
                "0" * 40,
            )

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

        cand = {"module": "en.test"}
        plan_item = self.valid_plan["artifacts"][0]
        cand["extensionLib"] = "1.4"
        rec = mat._build_registry_record(
            plan_item,
            cand,
            ir,
            {"name": "IR Name", "key": "test_key", "version": "1.0.0"},
            self.valid_plan,
        )
        self.assertEqual(rec["catalogName"], "IR Name")
        self.assertEqual(rec["runtimeKey"], "test_key")
        self.assertEqual(rec["upstream"]["version"], "1.2.3")
        self.assertEqual(rec["implementation"]["transport"], "api")

    def test_missing_authoritative_transport_rejects(self):
        ir = copy.deepcopy(self.valid_ir_template)
        del ir["sourceType"]

        cand = {"module": "en.test", "extensionLib": "1.4"}
        plan_item = self.valid_plan["artifacts"][0]
        with self.assertRaisesRegex(mat.MaterializationError, "Missing authoritative sourceType"):
            mat._build_registry_record(
                plan_item,
                cand,
                ir,
                {"name": "IR Name", "key": "test_key", "version": "1.0.0"},
                self.valid_plan,
            )

class TestIntegration(MaterializerTestBase):
    def setUp(self):
        super().setUp()
        (self.repo_root / "existing.js").write_text(
            'class ExistingSource extends ComicSource {\n'
            '    name = "Existing"\n'
            '    key = "existing"\n'
            '    version = "1.0.0"\n'
            '}\n',
            encoding="utf-8",
        )
        self.write_json(
            self.repo_root / "sources_registry.json",
            {
                "schemaVersion": "1.0",
                "artifacts": [{
                    "artifactId": "existing",
                    "runtimeKey": "existing",
                    "providerId": "existing",
                    "implementation": {"producer": "manual"}
                }]
            },
        )
        mat.write_index(self.repo_root)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_check_mode_zero_live_writes(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        ret = mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 0)

        self.assertFalse((self.repo_root / "test_artifact.js").exists())
        self.assertFalse((self.repo_root / "sources_ir" / "test_artifact.json").exists())
        self.assertFalse((self.repo_root / "sources_generated" / "test_artifact.base.js").exists())

        registry = self.read_json(self.repo_root / "sources_registry.json")
        self.assertEqual(len(registry["artifacts"]), 1)

        index = self.read_json(self.repo_root / "index.json")
        self.assertEqual(len(index), 1)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_write_mode_integration(self, mock_dispatch):
        mock_dispatch.return_value = copy.deepcopy(self.valid_ir_template)

        ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 0)

        self.assertTrue((self.repo_root / "test_artifact.js").exists())
        self.assertTrue((self.repo_root / "sources_ir" / "test_artifact.json").exists())
        self.assertTrue((self.repo_root / "sources_generated" / "test_artifact.base.js").exists())

        registry = self.read_json(self.repo_root / "sources_registry.json")
        self.assertEqual(len(registry["artifacts"]), 2)
        self.assertEqual(registry["artifacts"][1]["artifactId"], "test_artifact")
        self.assertEqual(registry["artifacts"][1]["upstream"]["version"], "1.2.3")

        index = self.read_json(self.repo_root / "index.json")
        self.assertEqual(len(index), 2)
        self.assertEqual(index[1]["fileName"], "test_artifact.js")

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
        self.assertEqual(len(registry["artifacts"]), 3)

        index = self.read_json(self.repo_root / "index.json")
        self.assertEqual(len(index), 3)

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

        fingerprint = mat._capture_preflight_fingerprint(self.repo_root)
        targets = []
        for relative_path in (
            "sources_ir/test_artifact.json",
            "sources_generated/test_artifact.base.js",
            "test_artifact.js",
            "sources_registry.json",
            "index.json",
        ):
            payload = (td / relative_path).read_bytes()
            targets.append({
                "relativePath": relative_path,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "byteLength": len(payload),
            })

        (self.repo_root / "unrelated").mkdir()
        (self.repo_root / "unrelated" / "file.txt").write_text("keep")

        orig_reg_bytes = (self.repo_root / "sources_registry.json").read_bytes()
        orig_idx_bytes = (self.repo_root / "index.json").read_bytes()

        orig_link = os.link
        def fail_on_js(src, dst):
            if str(dst).endswith(".js") and not str(dst).endswith("base.js"):
                raise Exception("mock fail on js")
            return orig_link(src, dst)

        with patch.object(mat.os, 'link', side_effect=fail_on_js):
            with self.assertRaisesRegex(mat.MaterializationError, "rollback successful"):
                mat._promote_transaction(
                    self.repo_root,
                    td,
                    plan,
                    fingerprint,
                    targets,
                )

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
            mat._check_preconditions(self.valid_plan, self.repo_root, {})

    def test_collision_existing_js(self):
        (self.repo_root / "test_artifact.js").write_text("")
        with self.assertRaisesRegex(mat.MaterializationError, "already exists in repository root"):
            mat._check_preconditions(self.valid_plan, self.repo_root, {})

    def test_collision_existing_ir(self):
        (self.repo_root / "sources_ir").mkdir()
        (self.repo_root / "sources_ir" / "test_artifact.json").write_text("")
        with self.assertRaisesRegex(mat.MaterializationError, "sources_ir/test_artifact.json already exists"):
            mat._check_preconditions(self.valid_plan, self.repo_root, {})

    def test_collision_existing_base_js(self):
        (self.repo_root / "sources_generated").mkdir()
        (self.repo_root / "sources_generated" / "test_artifact.base.js").write_text("")
        with self.assertRaisesRegex(mat.MaterializationError, "sources_generated/test_artifact.base.js already exists"):
            mat._check_preconditions(self.valid_plan, self.repo_root, {})

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

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            out1 = mock_stdout.getvalue()

        digest1 = None
        for line in out1.splitlines():
            if '"transactionDigest"' in line:
                digest1 = line.split('"')[3]
                break

        with patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            out2 = mock_stdout.getvalue()

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

class TestStrictPlanAudit(MaterializerTestBase):
    def _assert_invalid(self, plan):
        self.write_json(self.plan_path, plan)
        with self.assertRaises(mat.MaterializationError):
            mat._parse_plan(self.plan_path)

    def test_root_upstream_artifact_and_field_types_fail_closed(self):
        cases = [
            [],
            {**self.valid_plan, "upstream": []},
            {**self.valid_plan, "artifacts": "invalid"},
            {**self.valid_plan, "artifacts": ["invalid"]},
        ]
        for value in cases:
            with self.subTest(value=value):
                self._assert_invalid(value)

        mutations = (
            lambda p: p["upstream"].__setitem__("project", 1),
            lambda p: p["upstream"].__setitem__("commit", []),
            lambda p: p["artifacts"][0].__setitem__("sourceId", 1234),
            lambda p: p["artifacts"][0].__setitem__("artifactId", 1),
            lambda p: p["artifacts"][0].__setitem__("providerId", []),
            lambda p: p["artifacts"][0].__setitem__("localVersion", 1),
            lambda p: p["artifacts"][0].__setitem__("moduleAssert", None),
        )
        for mutate in mutations:
            plan = copy.deepcopy(self.valid_plan)
            mutate(plan)
            with self.subTest(plan=plan):
                self._assert_invalid(plan)

    def test_all_required_fields_are_enforced(self):
        for field in ("schemaVersion", "upstream", "generatedTimestamp", "artifacts"):
            plan = copy.deepcopy(self.valid_plan)
            del plan[field]
            with self.subTest(field=field):
                self._assert_invalid(plan)

        for field in ("project", "commit"):
            plan = copy.deepcopy(self.valid_plan)
            del plan["upstream"][field]
            with self.subTest(field=field):
                self._assert_invalid(plan)

        for field in ("sourceId", "artifactId", "providerId", "localVersion"):
            plan = copy.deepcopy(self.valid_plan)
            del plan["artifacts"][0][field]
            with self.subTest(field=field):
                self._assert_invalid(plan)

    def test_malformed_commit_project_and_timestamp_fail_closed(self):
        changes = (
            ("project", " "),
            ("commit", "abc"),
            ("commit", "A" * 40),
        )
        for field, value in changes:
            plan = copy.deepcopy(self.valid_plan)
            plan["upstream"][field] = value
            with self.subTest(field=field, value=value):
                self._assert_invalid(plan)

        for timestamp in (
            "2024-05-10 12:34:56",
            "2024-05-10T12:34:56+00:00",
            "2024-02-30T12:34:56Z",
            "2024-05-10T25:00:00Z",
            123,
        ):
            plan = copy.deepcopy(self.valid_plan)
            plan["generatedTimestamp"] = timestamp
            with self.subTest(timestamp=timestamp):
                self._assert_invalid(plan)

    def test_path_lexical_semver_and_whitespace_rules_fail_closed(self):
        mutations = (
            lambda p: p["artifacts"][0].__setitem__("artifactId", "../escape"),
            lambda p: p["artifacts"][0].__setitem__("providerId", "C:\\escape"),
            lambda p: p["artifacts"][0].__setitem__("artifactId", "Bad-Id"),
            lambda p: p["artifacts"][0].__setitem__("providerId", "bad id"),
            lambda p: p["artifacts"][0].__setitem__("localVersion", "1.0"),
            lambda p: p["artifacts"][0].__setitem__("localVersion", "1.0.0-beta"),
            lambda p: p["artifacts"][0].__setitem__("moduleAssert", "../module"),
            lambda p: p["artifacts"][0].__setitem__("moduleAssert", " "),
        )
        for mutate in mutations:
            plan = copy.deepcopy(self.valid_plan)
            mutate(plan)
            with self.subTest(plan=plan):
                self._assert_invalid(plan)

        for field in ("sourceId", "artifactId", "providerId", "localVersion"):
            plan = copy.deepcopy(self.valid_plan)
            plan["artifacts"][0][field] = " "
            with self.subTest(field=field):
                self._assert_invalid(plan)

    def test_empty_artifacts_and_duplicate_targets_fail_closed(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"] = []
        self._assert_invalid(plan)

        duplicate = copy.deepcopy(self.valid_plan["artifacts"][0])
        duplicate["sourceId"] = "9999"
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"].append(duplicate)
        self._assert_invalid(plan)

    def test_provider_identity_is_nonunique_under_registry_contract(self):
        second = copy.deepcopy(self.valid_plan["artifacts"][0])
        second["sourceId"] = "9999"
        second["artifactId"] = "other_artifact"
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"].append(second)
        self.write_json(self.plan_path, plan)
        self.assertEqual(len(mat._parse_plan(self.plan_path)["artifacts"]), 2)


class TestCanonicalEligibilityAudit(MaterializerTestBase):
    def _registry(self):
        return {
            "schemaVersion": "1.0",
            "artifacts": [{
                "artifactId": "existing",
                "runtimeKey": "existing",
                "providerId": "existing",
                "implementation": {"producer": "manual"},
            }],
        }

    def test_structured_compatibility_calls_canonical_planner(self):
        self.assertNotIn("COMPATIBLE", json.dumps(self.valid_inventory))
        with patch.object(
            mat.eligibility_planner,
            "build_plan",
            wraps=mat.eligibility_planner.build_plan,
        ) as planner:
            resolved = mat._resolve_candidates(
                self.valid_plan, self.valid_inventory, self._registry()
            )
        self.assertEqual(resolved["1234"]["module"], "en.testsource")
        planner.assert_called_once()

    def test_real_canonical_e3_mangacatalog_candidate_is_accepted(self):
        inventory = mat.load_json(
            REPO_ROOT
            / "tools"
            / "source_conversion"
            / "inventory"
            / "upstream_inventory.json"
        )
        registry = mat.load_json(REPO_ROOT / "sources_registry.json")
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
        registry["artifacts"] = [a for a in registry["artifacts"] if a["artifactId"] not in e4b_ids]
        source_id = "6485938153129890061"
        plan = {
            "schemaVersion": "1",
            "upstream": {
                "project": "keiyoushi/extensions-source",
                "commit": "5e06c412c0264b18120fd963fdd6efb529f3fa29",
            },
            "generatedTimestamp": "2023-01-01T00:00:00Z",
            "artifacts": [{
                "sourceId": source_id,
                "artifactId": "canonical_e3_probe",
                "providerId": "canonical_e3_probe",
                "localVersion": "1.0.0",
                "moduleAssert": "en.readblackclovermangaonline",
            }],
        }
        resolved = mat._resolve_candidates(plan, inventory, registry)
        self.assertEqual(resolved[source_id]["theme"], "mangacatalog")
        self.assertIsInstance(resolved[source_id]["compatibility"], dict)

    def test_e6_and_e4_candidates_fail_closed(self):
        for extraction, expected in (("unclassified", "E6"), ("manual", "E4")):
            inventory = copy.deepcopy(self.valid_inventory)
            inventory["candidates"][0]["compatibility"]["extraction"] = extraction
            with self.subTest(extraction=extraction):
                with self.assertRaisesRegex(mat.MaterializationError, expected):
                    mat._resolve_candidates(
                        self.valid_plan, inventory, self._registry()
                    )

    def test_patch_required_candidate_fails_before_dispatch(self):
        inventory = copy.deepcopy(self.valid_inventory)
        inventory["candidates"][0]["compatibility"]["patchRequired"] = True
        with patch.object(mat, "dispatch_extraction") as dispatch:
            with self.assertRaisesRegex(mat.MaterializationError, "requires a patch"):
                mat._resolve_candidates(
                    self.valid_plan, inventory, self._registry()
                )
        dispatch.assert_not_called()

    def test_malformed_structured_compatibility_fails_planner_validation(self):
        inventory = copy.deepcopy(self.valid_inventory)
        inventory["candidates"][0]["compatibility"] = "COMPATIBLE"
        with self.assertRaisesRegex(mat.MaterializationError, "planner rejected"):
            mat._resolve_candidates(self.valid_plan, inventory, self._registry())

    def test_module_assert_mismatch_fails_closed(self):
        plan = copy.deepcopy(self.valid_plan)
        plan["artifacts"][0]["moduleAssert"] = "en.wrong"
        with self.assertRaisesRegex(mat.MaterializationError, "moduleAssert failed"):
            mat._resolve_candidates(plan, self.valid_inventory, self._registry())


class TestDispatchAndMetadataAudit(MaterializerTestBase):
    def test_module_locator_is_translated_then_canonical_dispatch_owns_family(self):
        item = copy.deepcopy(self.valid_plan["artifacts"][0])
        candidate = copy.deepcopy(self.valid_inventory["candidates"][0])
        with patch.object(mat, "dispatch_extraction", return_value={}) as dispatch:
            result = mat._extract_to_temp(
                item, candidate, "2023-01-01T00:00:00Z", self.extensions_root
            )
        self.assertEqual(dispatch.call_args.kwargs["source_path"], "en/testsource")
        self.assertEqual(result["artifactId"], "test_artifact")
        source = inspect.getsource(mat._extract_to_temp).lower()
        self.assertIn("dispatch_extraction", source)
        for family in ("webtoons", "comicabc", "flamecomics", "mangacatalog"):
            self.assertNotIn(family, source)

    def test_missing_source_type_never_defaults_to_hybrid(self):
        ir = copy.deepcopy(self.valid_ir_template)
        del ir["sourceType"]
        candidate = copy.deepcopy(self.valid_inventory["candidates"][0])
        with self.assertRaisesRegex(mat.MaterializationError, "sourceType"):
            mat._build_registry_record(
                self.valid_plan["artifacts"][0],
                candidate,
                ir,
                {"name": "Test", "key": "test", "version": "1.0.0"},
                self.valid_plan,
            )

    def test_missing_extension_lib_fails_closed(self):
        candidate = copy.deepcopy(self.valid_inventory["candidates"][0])
        del candidate["extensionLib"]
        with self.assertRaisesRegex(mat.MaterializationError, "extensionLib"):
            mat._build_registry_record(
                self.valid_plan["artifacts"][0],
                candidate,
                self.valid_ir_template,
                {"name": "Test", "key": "test", "version": "1.0.0"},
                self.valid_plan,
            )

    def test_extracted_provenance_relationships_fail_closed(self):
        candidate = copy.deepcopy(self.valid_inventory["candidates"][0])
        candidate["version"] = "1.2.3"
        candidate["canonicalLocale"] = "en"
        candidate["contentWarning"] = "SAFE"
        base = copy.deepcopy(self.valid_ir_template)
        base["provenance"]["upstreamSourceId"] = "1234"
        mutations = (
            lambda ir: ir["provenance"].__setitem__("upstreamCommit", "0" * 40),
            lambda ir: ir["provenance"].__setitem__("upstreamSourceId", "9999"),
            lambda ir: ir["provenance"].__setitem__("upstreamVersion", "9.9.9"),
            lambda ir: ir["provenance"].__setitem__("generatedTimestamp", "2024-01-01T00:00:00Z"),
            lambda ir: ir.__setitem__("languages", ["zh-Hant"]),
            lambda ir: ir.__setitem__("contentWarning", "NSFW"),
        )
        for mutate in mutations:
            ir = copy.deepcopy(base)
            mutate(ir)
            with self.subTest(ir=ir):
                with self.assertRaises(mat.MaterializationError):
                    mat._validate_extracted_identity(
                        self.valid_plan["artifacts"][0],
                        candidate,
                        ir,
                        self.valid_plan,
                    )

    def test_final_js_identity_must_match_ir_and_reviewed_version(self):
        candidate = copy.deepcopy(self.valid_inventory["candidates"][0])
        for metadata in (
            {"name": "Wrong", "key": "test", "version": "1.0.0"},
            {"name": "Test Source", "key": "test", "version": "2.0.0"},
        ):
            with self.subTest(metadata=metadata):
                with self.assertRaises(mat.MaterializationError):
                    mat._build_registry_record(
                        self.valid_plan["artifacts"][0],
                        candidate,
                        self.valid_ir_template,
                        metadata,
                        self.valid_plan,
                    )


class RealMaterializerTestBase(MaterializerTestBase):
    def setUp(self):
        super().setUp()
        self._add_generic_source_and_commit()
        self.commit_hash = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=self.extensions_root,
            text=True,
        ).strip()
        self.valid_plan["upstream"]["commit"] = self.commit_hash
        self.valid_plan["artifacts"][0]["moduleAssert"] = "en.genericsafe"
        self.valid_inventory["upstreams"][0]["commit"] = self.commit_hash
        candidate = self.valid_inventory["candidates"][0]
        candidate.update({
            "module": "en.genericsafe",
            "name": "GenericSafe",
            "canonicalLocale": "en",
            "contentWarning": "SAFE",
            "version": "1.6.4",
            "extensionLib": "1.6",
        })
        self.valid_ir_template["provenance"]["upstreamCommit"] = self.commit_hash
        self.write_json(self.plan_path, self.valid_plan)
        self.write_json(self.inventory_path, self.valid_inventory)
        self._create_live_baseline()

    def _add_generic_source_and_commit(self):
        source_dir = self.extensions_root / "src" / "en" / "genericsafe"
        kotlin_dir = (
            source_dir
            / "src"
            / "eu"
            / "kanade"
            / "tachiyomi"
            / "extension"
            / "en"
            / "genericsafe"
        )
        kotlin_dir.mkdir(parents=True)
        (source_dir / "build.gradle.kts").write_text(
            '''
keiyoushi {
    name = "Generic Extension"
    versionCode = 4
    libVersion = "1.6"
    contentWarning = ContentWarning.SAFE
    source {
        name = "GenericSafe"
        lang = "en"
        id = 1234L
        baseUrl { mirrors("https://genericsafe.com") }
    }
}
''',
            encoding="utf-8",
        )
        (kotlin_dir / "GenericSafe.kt").write_text(
            '''
package eu.kanade.tachiyomi.extension.en.genericsafe

import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.KeiSource
import org.jsoup.nodes.Document

class GenericSafe : KeiSource() {
    override val baseUrl = "https://genericsafe.com"

    override suspend fun getPopularManga(page: Int): MangasPage {
        val response = client.get("$baseUrl/popular/$page")
        val document = response.asJsoup()
        return parseManga(document)
    }

    private fun parseManga(document: Document): MangasPage {
        val mangas = document.select("div.comic-list > div.comic-item").map { element ->
            SManga.create().apply {
                title = element.selectFirst("h3 a")!!.text()
                setUrlWithoutDomain(element.selectFirst("a")!!.absUrl("href"))
                thumbnail_url = element.selectFirst("img")!!.attr("src")
            }
        }
        val nextPage = document.selectFirst("div.pagination > a.next")!!.attr("href")
        val currentPage = document.selectFirst("div.pagination > a.on")!!.attr("href")
        return MangasPage(mangas, nextPage != currentPage)
    }

    override suspend fun getLatestUpdates(page: Int): MangasPage {
        val response = client.get("$baseUrl/latest/$page")
        val document = response.asJsoup()
        return parseManga(document)
    }

    override suspend fun getSearchMangaList(page: Int, query: String): MangasPage {
        val response = client.get("$baseUrl/search/$query/$page")
        val document = response.asJsoup()
        return parseManga(document)
    }

    override suspend fun fetchMangaUpdate(document: Document): String {
        title = document.selectFirst("h1")!!.text()
        thumbnail_url = document.selectFirst("img")!!.attr("src")
        description = document.selectFirst("p")!!.text()
        author = document.selectFirst("div.author")!!.text()
        val chapters = document.select("div.chapter-list li a").map { element ->
            SChapter.create().apply {
                name = element.text()
                setUrlWithoutDomain(element.attr("href"))
            }
        }.asReversed()
        return chapters
    }

    override suspend fun getPageList(document: Document): List<Page> {
        return document.select("div.comic-content > img").mapIndexed { index, it ->
            Page(index, imageUrl = it.attr("src"))
        }
    }
}
''',
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.extensions_root, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "-m",
                "generic fixture",
            ],
            cwd=self.extensions_root,
            check=True,
        )

    def _create_live_baseline(self):
        (self.repo_root / "existing.js").write_text(
            'class ExistingSource extends ComicSource {\n'
            '    name = "Existing"\n'
            '    key = "existing"\n'
            '    version = "1.0.0"\n'
            '}\n',
            encoding="utf-8",
        )
        self.write_json(
            self.repo_root / "sources_registry.json",
            {
                "schemaVersion": "1.0",
                "artifacts": [{
                    "artifactId": "existing",
                    "runtimeKey": "existing",
                    "catalogName": "Existing",
                    "providerId": "existing",
                    "implementation": {"producer": "manual"},
                }],
            },
        )
        mat.write_index(self.repo_root)

    def _run_real(self, mode):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = mat.main([
                "--mode", mode,
                "--plan", str(self.plan_path),
                "--repo-root", str(self.repo_root),
                "--extensions-root", str(self.extensions_root),
            ])
        return result, stdout.getvalue(), stderr.getvalue()

    def _snapshot_live_tree(self):
        snapshot = {}
        for path in sorted(self.repo_root.rglob("*")):
            relative = path.relative_to(self.repo_root).as_posix()
            snapshot[relative + ("/" if path.is_dir() else "")] = (
                None if path.is_dir() else path.read_bytes()
            )
        return snapshot

    def _prepare_real_pass(self):
        plan = mat._parse_plan(self.plan_path)
        inventory = mat.load_json(self.inventory_path)
        registry = mat.load_json(self.repo_root / "sources_registry.json")
        mat._validate_live_repository(self.repo_root)
        resolved = mat._resolve_candidates(plan, inventory, registry)
        mat._verify_extensions_checkout(
            self.extensions_root,
            inventory,
            "keiyoushi/extensions-source",
            self.commit_hash,
        )
        mat._check_preconditions(plan, self.repo_root, {})
        fingerprint = mat._capture_preflight_fingerprint(self.repo_root)
        transaction = tempfile.TemporaryDirectory()
        self.addCleanup(transaction.cleanup)
        transaction_dir = Path(transaction.name)
        result = mat._execute_pass(
            plan,
            resolved,
            self.extensions_root,
            self.repo_root,
            transaction_dir,
        )
        return plan, fingerprint, transaction_dir, result

    def _assert_no_real_outputs(self):
        self.assertFalse((self.repo_root / "test_artifact.js").exists())
        self.assertFalse(
            (self.repo_root / "sources_ir" / "test_artifact.json").exists()
        )
        self.assertFalse(
            (self.repo_root / "sources_generated" / "test_artifact.base.js").exists()
        )


class TestRealMaterializerModes(RealMaterializerTestBase):
    def test_checkout_commit_mismatch_fails_before_extraction(self):
        wrong_commit = "0" * 40
        plan = copy.deepcopy(self.valid_plan)
        plan["upstream"]["commit"] = wrong_commit
        inventory = copy.deepcopy(self.valid_inventory)
        inventory["upstreams"][0]["commit"] = wrong_commit
        self.write_json(self.plan_path, plan)
        self.write_json(self.inventory_path, inventory)
        with patch.object(mat, "dispatch_extraction") as dispatch:
            result, _, stderr = self._run_real("check")
        self.assertEqual(result, 1)
        self.assertIn("UPSTREAM_PIN_MISMATCH", stderr)
        dispatch.assert_not_called()

    def test_real_isolated_write_mode_keeps_prepared_directory_alive(self):
        result, stdout, stderr = self._run_real("write")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        self.assertIn('"validation": "PASS"', stdout)
        self.assertTrue((self.repo_root / "test_artifact.js").is_file())
        self.assertTrue(
            (self.repo_root / "sources_ir" / "test_artifact.json").is_file()
        )
        self.assertTrue(
            (self.repo_root / "sources_generated" / "test_artifact.base.js").is_file()
        )
        registry = self.read_json(self.repo_root / "sources_registry.json")
        self.assertEqual(registry["artifacts"][-1]["artifactId"], "test_artifact")
        index = self.read_json(self.repo_root / "index.json")
        self.assertEqual(index[-1]["fileName"], "test_artifact.js")
        self.assertFalse(any(self.repo_root.rglob("*.tmp")))
        self.assertFalse((self.repo_root / "sources_patches").exists())

    def test_real_check_mode_is_full_tree_zero_write(self):
        before = self._snapshot_live_tree()
        result, _, stderr = self._run_real("check")
        after = self._snapshot_live_tree()
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        self.assertEqual(before, after)

    def test_identical_real_transactions_have_stable_digest(self):
        digests = []
        for _ in range(2):
            result, stdout, stderr = self._run_real("check")
            self.assertEqual((result, stderr), (0, ""), msg=stderr)
            report_start = stdout.index('{\n  "mode"')
            report = json.loads(stdout[report_start:])
            digests.append(report["transactionDigest"])
        self.assertEqual(digests[0], digests[1])

    def test_create_check_still_targets_registry_and_index(self):
        result, stdout, stderr = self._run_real("check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        report_start = stdout.index('{\n  "mode"')
        report = json.loads(stdout[report_start:])
        self.assertEqual(
            [target["relativePath"] for target in report["targets"]],
            [
                "sources_ir/test_artifact.json",
                "sources_generated/test_artifact.base.js",
                "test_artifact.js",
                "sources_registry.json",
                "index.json",
            ],
        )

    def test_digest_covers_reviewed_semantics_not_machine_paths(self):
        plan = copy.deepcopy(self.valid_plan)
        targets = [{
            "relativePath": "test_artifact.js",
            "sha256": "a" * 64,
            "byteLength": 10,
            "sourcePath": "C:/random/one/test_artifact.js",
        }]
        baseline = mat._compute_digest(plan, targets)
        relocated = copy.deepcopy(targets)
        relocated[0]["sourcePath"] = "D:/different/two/test_artifact.js"
        self.assertEqual(baseline, mat._compute_digest(plan, relocated))

        mutations = (
            lambda p, t: p["artifacts"][0].__setitem__("moduleAssert", "en.changed"),
            lambda p, t: p["artifacts"][0].__setitem__("sourceId", "9999"),
            lambda p, t: p["artifacts"][0].__setitem__("artifactId", "changed_artifact"),
            lambda p, t: p["artifacts"][0].__setitem__("providerId", "changed_provider"),
            lambda p, t: p["artifacts"][0].__setitem__("localVersion", "2.0.0"),
            lambda p, t: p["upstream"].__setitem__("commit", "a" * 40),
            lambda p, t: t[0].__setitem__("sha256", "b" * 64),
        )
        for mutate in mutations:
            changed_plan = copy.deepcopy(plan)
            changed_targets = copy.deepcopy(targets)
            mutate(changed_plan, changed_targets)
            with self.subTest(plan=changed_plan, targets=changed_targets):
                self.assertNotEqual(
                    baseline,
                    mat._compute_digest(changed_plan, changed_targets),
                )

    def test_complete_transaction_negative_linkage_codes(self):
        _, _, transaction_dir, _ = self._prepare_real_pass()
        ir_path = transaction_dir / "sources_ir" / "test_artifact.json"
        ir = self.read_json(ir_path)
        del ir["artifactId"]
        self.write_json(ir_path, ir)
        with self.assertRaisesRegex(mat.MaterializationError, "IR_ARTIFACT_LINK_MISSING"):
            mat._validate_prepared_transaction(transaction_dir)

        plan, fingerprint, second_dir, result = self._prepare_real_pass()
        del plan, fingerprint, result
        (second_dir / "sources_ir" / "test_artifact.json").unlink()
        with self.assertRaisesRegex(mat.MaterializationError, "REGISTRY_IR_LINK_MISSING"):
            mat._validate_prepared_transaction(second_dir)

    def test_index_bytes_equal_canonical_write_index(self):
        _, _, transaction_dir, _ = self._prepare_real_pass()
        equivalent = self.root / "equivalent"
        equivalent.mkdir()
        shutil.copy2(
            transaction_dir / "sources_registry.json",
            equivalent / "sources_registry.json",
        )
        for source in transaction_dir.glob("*.js"):
            shutil.copy2(source, equivalent / source.name)
        mat.write_index(equivalent)
        self.assertEqual(
            (transaction_dir / "index.json").read_bytes(),
            (equivalent / "index.json").read_bytes(),
        )


class TestRealPromotionFailures(RealMaterializerTestBase):
    def test_stale_existing_final_js_also_aborts_before_publish(self):
        plan, fingerprint, transaction_dir, result = self._prepare_real_pass()
        existing_path = self.repo_root / "existing.js"
        mutated = existing_path.read_bytes() + b" "
        existing_path.write_bytes(mutated)
        with self.assertRaisesRegex(mat.MaterializationError, "Stale-state guard"):
            mat._promote_transaction(
                self.repo_root,
                transaction_dir,
                plan,
                fingerprint,
                result["targets"],
            )
        self._assert_no_real_outputs()
        self.assertEqual(existing_path.read_bytes(), mutated)

    def test_stale_registry_aborts_before_any_publish(self):
        plan, fingerprint, transaction_dir, result = self._prepare_real_pass()
        registry_path = self.repo_root / "sources_registry.json"
        mutated = registry_path.read_bytes() + b" "
        registry_path.write_bytes(mutated)
        with self.assertRaisesRegex(mat.MaterializationError, "Stale-state guard"):
            mat._promote_transaction(
                self.repo_root,
                transaction_dir,
                plan,
                fingerprint,
                result["targets"],
            )
        self._assert_no_real_outputs()
        self.assertEqual(registry_path.read_bytes(), mutated)

    def test_stale_index_aborts_before_any_publish(self):
        plan, fingerprint, transaction_dir, result = self._prepare_real_pass()
        index_path = self.repo_root / "index.json"
        mutated = index_path.read_bytes() + b" "
        index_path.write_bytes(mutated)
        with self.assertRaisesRegex(mat.MaterializationError, "Stale-state guard"):
            mat._promote_transaction(
                self.repo_root,
                transaction_dir,
                plan,
                fingerprint,
                result["targets"],
            )
        self._assert_no_real_outputs()
        self.assertEqual(index_path.read_bytes(), mutated)

    def test_partial_copy_failure_leaves_no_partial_destination(self):
        plan, fingerprint, transaction_dir, result = self._prepare_real_pass()
        original_registry = (self.repo_root / "sources_registry.json").read_bytes()
        original_index = (self.repo_root / "index.json").read_bytes()

        def partial_copy(_source, destination, *args, **kwargs):
            Path(destination).write_bytes(b"partial")
            raise OSError("injected partial copy")

        with patch.object(mat.shutil, "copy2", side_effect=partial_copy):
            with self.assertRaisesRegex(mat.MaterializationError, "rollback successful"):
                mat._promote_transaction(
                    self.repo_root,
                    transaction_dir,
                    plan,
                    fingerprint,
                    result["targets"],
                )
        self._assert_no_real_outputs()
        self.assertEqual(
            (self.repo_root / "sources_registry.json").read_bytes(),
            original_registry,
        )
        self.assertEqual((self.repo_root / "index.json").read_bytes(), original_index)
        self.assertFalse(any(self.repo_root.rglob("*.tmp")))

    def test_late_shared_failure_rolls_back_preexisting_bytes(self):
        plan, fingerprint, transaction_dir, result = self._prepare_real_pass()
        original_registry = (self.repo_root / "sources_registry.json").read_bytes()
        original_index = (self.repo_root / "index.json").read_bytes()
        original_replace = os.replace
        failed = False

        def fail_index_once(source, destination):
            nonlocal failed
            if Path(destination) == self.repo_root / "index.json" and not failed:
                failed = True
                raise OSError("injected index promotion failure")
            return original_replace(source, destination)

        with patch.object(mat.os, "replace", side_effect=fail_index_once):
            with self.assertRaisesRegex(mat.MaterializationError, "rollback successful"):
                mat._promote_transaction(
                    self.repo_root,
                    transaction_dir,
                    plan,
                    fingerprint,
                    result["targets"],
                )
        self._assert_no_real_outputs()
        self.assertEqual(
            (self.repo_root / "sources_registry.json").read_bytes(),
            original_registry,
        )
        self.assertEqual((self.repo_root / "index.json").read_bytes(), original_index)
        self.assertFalse(any(self.repo_root.rglob("*.tmp")))

    def test_concurrent_new_target_is_never_overwritten_or_removed(self):
        plan, fingerprint, transaction_dir, result = self._prepare_real_pass()
        original_link = os.link
        injected = False

        def race_link(source, destination):
            nonlocal injected
            if not injected:
                injected = True
                Path(destination).write_bytes(b"concurrent-owner")
            return original_link(source, destination)

        with patch.object(mat.os, "link", side_effect=race_link):
            with self.assertRaisesRegex(mat.MaterializationError, "rollback successful"):
                mat._promote_transaction(
                    self.repo_root,
                    transaction_dir,
                    plan,
                    fingerprint,
                    result["targets"],
                )
        raced_path = self.repo_root / mat._artifact_target_paths(plan)[0]
        self.assertEqual(raced_path.read_bytes(), b"concurrent-owner")

    def test_runtime_identity_collision_fails_before_publication(self):
        (self.repo_root / "existing.js").write_text(
            'class ExistingSource extends ComicSource {\n'
            '    name = "Existing"\n'
            '    key = "en_genericsafe"\n'
            '    version = "1.0.0"\n'
            '}\n',
            encoding="utf-8",
        )
        registry = self.read_json(self.repo_root / "sources_registry.json")
        registry["artifacts"][0]["runtimeKey"] = "en_genericsafe"
        self.write_json(self.repo_root / "sources_registry.json", registry)
        mat.write_index(self.repo_root)
        result, _, stderr = self._run_real("check")
        self.assertEqual(result, 1)
        self.assertIn("DUPLICATE_RUNTIME_KEY", stderr)
        self._assert_no_real_outputs()

    def test_filesystem_registry_index_and_patch_collisions(self):
        collision_paths = (
            self.repo_root / "test_artifact.js",
            self.repo_root / "sources_ir" / "test_artifact.json",
            self.repo_root / "sources_generated" / "test_artifact.base.js",
            self.repo_root / "sources_patches" / "test_artifact.patch.js",
        )
        for path in collision_paths:
            with self.subTest(path=path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"existing")
                with self.assertRaisesRegex(mat.MaterializationError, "Collision"):
                    mat._check_preconditions(self.valid_plan, self.repo_root, {})
                path.unlink()

        registry = self.read_json(self.repo_root / "sources_registry.json")
        registry["artifacts"].append({"artifactId": "test_artifact"})
        self.write_json(self.repo_root / "sources_registry.json", registry)
        with self.assertRaisesRegex(mat.MaterializationError, "already exists in registry"):
            mat._check_preconditions(self.valid_plan, self.repo_root, {})

        self._create_live_baseline()
        index = self.read_json(self.repo_root / "index.json")
        index.append({
            "name": "Collision",
            "fileName": "test_artifact.js",
            "key": "collision",
            "version": "1.0.0",
        })
        self.write_json(self.repo_root / "index.json", index)
        with self.assertRaisesRegex(mat.MaterializationError, "index already contains"):
            mat._check_preconditions(self.valid_plan, self.repo_root, {})

    def test_manual_patch_ir_is_rejected_without_patch_consumption(self):
        with self.assertRaisesRegex(mat.MaterializationError, "requires manual patching"):
            mat._compose_final_js(
                {"pages": {"manualPatchRequired": True}}, b"generated"
            )


if __name__ == '__main__':
    unittest.main()


class TestUpdateTransaction(MaterializerTestBase):
    def setUp(self):
        super().setUp()

        self.update_plan = copy.deepcopy(self.valid_plan)
        self.update_plan["operation"] = "update"
        del self.update_plan["artifacts"][0]["localVersion"]
        self.update_plan["artifacts"][0]["expectedCurrentLocalVersion"] = "1.0.0"
        self.update_plan["artifacts"][0]["newLocalVersion"] = "1.0.1"
        self.write_json(self.plan_path, self.update_plan)

        self.artifact_id = self.update_plan["artifacts"][0]["artifactId"]

        self.final_js_path = self.repo_root / f"{self.artifact_id}.js"
        self.final_js_path.write_text(
            'class ExistingSource extends ComicSource {\n'
            '    name = "Test Source"\n'
            f'    key = "en_test_artifact"\n'
            '    version = "1.0.0"\n'
            '}\n',
            encoding="utf-8"
        )

        (self.repo_root / "sources_generated").mkdir()
        self.base_js_path = self.repo_root / "sources_generated" / f"{self.artifact_id}.base.js"
        self.base_js_path.write_text(self.final_js_path.read_text(encoding="utf-8"), encoding="utf-8")

        (self.repo_root / "sources_ir").mkdir()
        self.ir_path = self.repo_root / "sources_ir" / f"{self.artifact_id}.json"
        self.old_ir = copy.deepcopy(self.valid_ir_template)
        self.old_ir["version"] = "1.0.0"
        self.write_json(self.ir_path, self.old_ir)

        self.registry_path = self.repo_root / "sources_registry.json"
        self.registry = {
            "schemaVersion": "1.0",
            "artifacts": [{
                "artifactId": self.artifact_id,
                "runtimeKey": "en_test_artifact",
                "providerId": "test_provider",
                "implementation": {"producer": "generated"},
                "upstream": {
                    "project": "keiyoushi/extensions-source",
                    "module": "en.testsource",
                    "sourceId": "1234",
                    "version": "1.2.3", "extensionLib": "1.4",
                    "commit": self.commit_hash,
                }
            }]
        }
        self.write_json(self.registry_path, self.registry)

        mat.write_index(self.repo_root)

        self.valid_ir_update = copy.deepcopy(self.valid_ir_template)
        self.valid_ir_update["version"] = "1.0.1"
        self.valid_ir_update["id"] = "en_test_artifact"
        self.valid_ir_update["name"] = "Test Source"

    def _configure_dispatch(self, mock_dispatch, runtime_override=None):
        def extract(**kwargs):
            source_id = kwargs["source_id"]
            ir_data = copy.deepcopy(self.valid_ir_update)
            if source_id == "5678":
                ir_data["artifactId"] = "test_artifact_two"
                ir_data["id"] = self.second_runtime_key
                ir_data["name"] = "Test Source 2"
            if runtime_override is not None:
                ir_data["id"] = runtime_override
            return ir_data

        mock_dispatch.side_effect = extract

    def _run_update(self, mock_dispatch, mode, expected_digest=None):
        self._configure_dispatch(mock_dispatch)
        arguments = [
            "--mode", mode,
            "--plan", str(self.plan_path),
            "--repo-root", str(self.repo_root),
            "--extensions-root", str(self.extensions_root),
        ]
        if expected_digest is not None:
            arguments.extend(["--expected-digest", expected_digest])
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = mat.main(arguments)
        report = None
        marker = '{\n  "mode"'
        if marker in stdout.getvalue():
            report = json.loads(stdout.getvalue()[stdout.getvalue().index(marker):])
        return result, report, stderr.getvalue()

    def _add_second_artifact(self, *, shared_runtime_key=False, include_in_plan=True):
        artifact_id = "test_artifact_two"
        self.second_runtime_key = (
            "en_test_artifact" if shared_runtime_key else "en_test_artifact_two"
        )
        second_plan_item = {
            "sourceId": "5678",
            "artifactId": artifact_id,
            "providerId": "test_provider_two",
            "expectedCurrentLocalVersion": "1.0.0",
            "newLocalVersion": "1.0.1",
        }
        if include_in_plan:
            self.update_plan["artifacts"].append(second_plan_item)
            self.write_json(self.plan_path, self.update_plan)

        final_path = self.repo_root / f"{artifact_id}.js"
        final_path.write_text(
            'class ExistingSourceTwo extends ComicSource {\n'
            '    name = "Test Source 2"\n'
            f'    key = "{self.second_runtime_key}"\n'
            '    version = "1.0.0"\n'
            '}\n',
            encoding="utf-8",
        )
        base_path = self.repo_root / "sources_generated" / f"{artifact_id}.base.js"
        base_path.write_bytes(final_path.read_bytes())
        ir_data = copy.deepcopy(self.old_ir)
        ir_data.update({
            "artifactId": artifact_id,
            "id": self.second_runtime_key,
            "name": "Test Source 2",
        })
        self.write_json(self.repo_root / "sources_ir" / f"{artifact_id}.json", ir_data)

        compatibility = None
        if shared_runtime_key:
            compatibility = {"sharedRuntimeKeyGroup": "en_test_artifact"}
            self.registry["artifacts"][0]["compatibility"] = copy.deepcopy(
                compatibility
            )
        record = {
            "artifactId": artifact_id,
            "runtimeKey": self.second_runtime_key,
            "providerId": "test_provider_two",
            "implementation": {"producer": "generated"},
            "upstream": {
                "project": "keiyoushi/extensions-source",
                "module": "en.testsource2",
                "sourceId": "5678",
                "version": "1.2.3",
                "extensionLib": "1.4",
                "commit": self.commit_hash,
            },
        }
        if compatibility is not None:
            record["compatibility"] = compatibility
        self.registry["artifacts"].append(record)
        self.write_json(self.registry_path, self.registry)
        mat.write_index(self.repo_root)
        return second_plan_item

    def _prepare_update_transaction(self, mock_dispatch):
        self._configure_dispatch(mock_dispatch)
        plan = mat._parse_plan(self.plan_path)
        inventory = mat.load_json(self.inventory_path)
        registry = mat.load_json(self.registry_path)
        resolved = mat._resolve_candidates(plan, inventory, registry)
        mat._check_preconditions(plan, self.repo_root, resolved)
        fingerprint = mat._capture_preflight_fingerprint(self.repo_root)
        transaction = tempfile.TemporaryDirectory()
        self.addCleanup(transaction.cleanup)
        transaction_dir = Path(transaction.name)
        result = mat._execute_pass(
            plan,
            resolved,
            self.extensions_root,
            self.repo_root,
            transaction_dir,
        )
        return plan, fingerprint, transaction_dir, result

    def _snapshot_update_state(self, plan=None):
        if plan is None:
            plan = mat._parse_plan(self.plan_path)
        return {
            relative_path: (self.repo_root / relative_path).read_bytes()
            for relative_path in mat._update_current_state_paths(plan)
        }

    def _snapshot_tree(self):
        return {
            path.relative_to(self.repo_root).as_posix(): path.read_bytes()
            for path in sorted(self.repo_root.rglob("*"))
            if path.is_file()
        }

    def _assert_exact_update_state(self, expected):
        actual = {
            relative_path: (self.repo_root / relative_path).read_bytes()
            for relative_path in expected
        }
        self.assertEqual(actual, expected)
        artifact_payloads = [
            payload
            for relative_path, payload in actual.items()
            if relative_path not in {"sources_registry.json"}
        ]
        self.assertFalse(any(b'"1.0.1"' in payload for payload in artifact_payloads))
        self.assertFalse(
            any(
                path.is_file() and path.name.endswith(".tmp")
                for path in self.repo_root.rglob("*")
            )
        )

    def _assert_precondition_error(self, expected_message):
        plan = mat._parse_plan(self.plan_path)
        resolved = {
            candidate["sourceId"]: candidate
            for candidate in self.valid_inventory["candidates"]
        }
        with self.assertRaisesRegex(mat.MaterializationError, expected_message):
            mat._check_preconditions(plan, self.repo_root, resolved)

    def _assert_fault_rollback(self, mock_dispatch, injected_replace):
        plan, fingerprint, transaction_dir, result = self._prepare_update_transaction(
            mock_dispatch
        )
        before = self._snapshot_update_state(plan)
        with patch.object(
            mat, "_replace_prepared_sibling", side_effect=injected_replace
        ):
            with self.assertRaisesRegex(
                mat.MaterializationError, "rollback successful"
            ):
                mat._promote_transaction(
                    self.repo_root,
                    transaction_dir,
                    plan,
                    fingerprint,
                    result["targets"],
                )
        self._assert_exact_update_state(before)

    def _assert_reviewed_state_change_rejected(self, mock_dispatch, relative_path):
        result, report, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        live_path = self.repo_root / relative_path
        live_path.write_bytes(live_path.read_bytes() + b"\n")
        changed_state = self._snapshot_update_state()
        result, _, stderr = self._run_update(
            mock_dispatch, "write", report["transactionDigest"]
        )
        self.assertEqual(result, 1)
        self.assertIn("expected digest", stderr)
        self._assert_exact_update_state(changed_state)

    def test_update_version_accepts_exact_next_patch(self):
        parsed = mat._parse_plan(self.plan_path)
        self.assertEqual(parsed["artifacts"][0]["newLocalVersion"], "1.0.1")

    def test_update_version_accepts_patch_carry_without_minor_change(self):
        self.update_plan["artifacts"][0]["expectedCurrentLocalVersion"] = "1.0.9"
        self.update_plan["artifacts"][0]["newLocalVersion"] = "1.0.10"
        self.write_json(self.plan_path, self.update_plan)
        parsed = mat._parse_plan(self.plan_path)
        self.assertEqual(parsed["artifacts"][0]["newLocalVersion"], "1.0.10")

    def test_update_version_rejects_same_version(self):
        self.update_plan["artifacts"][0]["newLocalVersion"] = "1.0.0"
        self.write_json(self.plan_path, self.update_plan)
        with self.assertRaisesRegex(mat.MaterializationError, "exactly the next patch"):
            mat._parse_plan(self.plan_path)

    def test_update_version_rejects_decrease(self):
        self.update_plan["artifacts"][0]["expectedCurrentLocalVersion"] = "1.0.1"
        self.update_plan["artifacts"][0]["newLocalVersion"] = "1.0.0"
        self.write_json(self.plan_path, self.update_plan)
        with self.assertRaisesRegex(mat.MaterializationError, "exactly the next patch"):
            mat._parse_plan(self.plan_path)

    def test_update_version_rejects_minor_change(self):
        self.update_plan["artifacts"][0]["newLocalVersion"] = "1.1.0"
        self.write_json(self.plan_path, self.update_plan)
        with self.assertRaisesRegex(mat.MaterializationError, "exactly the next patch"):
            mat._parse_plan(self.plan_path)

    def test_update_version_rejects_major_change(self):
        self.update_plan["artifacts"][0]["newLocalVersion"] = "2.0.0"
        self.write_json(self.plan_path, self.update_plan)
        with self.assertRaisesRegex(mat.MaterializationError, "exactly the next patch"):
            mat._parse_plan(self.plan_path)

    def test_update_version_rejects_skipped_patch(self):
        self.update_plan["artifacts"][0]["newLocalVersion"] = "1.0.2"
        self.write_json(self.plan_path, self.update_plan)
        with self.assertRaisesRegex(mat.MaterializationError, "exactly the next patch"):
            mat._parse_plan(self.plan_path)

    def test_update_version_rejects_non_release_semver(self):
        rejected = ("1.0", "1.0.1-alpha", "1.0.1+build", "01.0.1")
        for version in rejected:
            with self.subTest(version=version):
                plan = copy.deepcopy(self.update_plan)
                plan["artifacts"][0]["newLocalVersion"] = version
                self.write_json(self.plan_path, plan)
                with self.assertRaisesRegex(
                    mat.MaterializationError, "Invalid newLocalVersion"
                ):
                    mat._parse_plan(self.plan_path)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_check_target_manifest_is_publication_minimal(
        self, mock_dispatch
    ):
        result, report, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        self.assertEqual(
            [target["relativePath"] for target in report["targets"]],
            [
                "sources_ir/test_artifact.json",
                "sources_generated/test_artifact.base.js",
                "test_artifact.js",
                "index.json",
            ],
        )
        self.assertNotIn(
            "sources_registry.json",
            {target["relativePath"] for target in report["targets"]},
        )
        self.assertFalse(
            any(
                "sources_patches/" in target["relativePath"]
                for target in report["targets"]
            )
        )

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_multi_artifact_update_check_has_exactly_seven_targets(
        self, mock_dispatch
    ):
        self._add_second_artifact(include_in_plan=True)
        result, report, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        self.assertEqual(
            [target["relativePath"] for target in report["targets"]],
            [
                "sources_ir/test_artifact.json",
                "sources_generated/test_artifact.base.js",
                "test_artifact.js",
                "sources_ir/test_artifact_two.json",
                "sources_generated/test_artifact_two.base.js",
                "test_artifact_two.js",
                "index.json",
            ],
        )
        self.assertEqual(len(report["targets"]), 7)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_successful_update_never_publishes_registry(self, mock_dispatch):
        result, report, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        registry_before = self.registry_path.read_bytes()
        registry_hash_before = hashlib.sha256(registry_before).hexdigest()
        registry_mtime_before = self.registry_path.stat().st_mtime_ns
        original_replace = mat._replace_prepared_sibling
        destinations = []

        def record_publication(source, destination):
            destinations.append(Path(destination))
            return original_replace(source, destination)

        with patch.object(
            mat, "_replace_prepared_sibling", side_effect=record_publication
        ):
            result, write_report, stderr = self._run_update(
                mock_dispatch, "write", report["transactionDigest"]
            )
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        self.assertEqual(report["targets"], write_report["targets"])
        self.assertEqual(
            destinations,
            [
                self.ir_path,
                self.base_js_path,
                self.final_js_path,
                self.repo_root / "index.json",
            ],
        )
        registry_after = self.registry_path.read_bytes()
        self.assertEqual(registry_after, registry_before)
        self.assertEqual(
            hashlib.sha256(registry_after).hexdigest(), registry_hash_before
        )
        self.assertEqual(
            self.registry_path.stat().st_mtime_ns, registry_mtime_before
        )

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_digest_binds_root_js(self, mock_dispatch):
        self._assert_reviewed_state_change_rejected(
            mock_dispatch, f"{self.artifact_id}.js"
        )

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_digest_binds_generated_base_js(self, mock_dispatch):
        self._assert_reviewed_state_change_rejected(
            mock_dispatch,
            f"sources_generated/{self.artifact_id}.base.js",
        )

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_digest_binds_ir(self, mock_dispatch):
        self._assert_reviewed_state_change_rejected(
            mock_dispatch, f"sources_ir/{self.artifact_id}.json"
        )

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_digest_binds_index(self, mock_dispatch):
        self._assert_reviewed_state_change_rejected(mock_dispatch, "index.json")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_digest_binds_registry(self, mock_dispatch):
        result, report, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        self.registry_path.write_bytes(self.registry_path.read_bytes() + b"\n")
        changed_state = self._snapshot_update_state()
        with patch.object(
            mat, "_replace_prepared_sibling", wraps=mat._replace_prepared_sibling
        ) as publication:
            result, _, stderr = self._run_update(
                mock_dispatch, "write", report["transactionDigest"]
            )
        self.assertEqual(result, 1)
        self.assertIn("expected digest", stderr)
        publication.assert_not_called()
        self._assert_exact_update_state(changed_state)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_check_is_deterministic_and_zero_write(self, mock_dispatch):
        before = self._snapshot_tree()
        result1, report1, stderr1 = self._run_update(mock_dispatch, "check")
        middle = self._snapshot_tree()
        result2, report2, stderr2 = self._run_update(mock_dispatch, "check")
        after = self._snapshot_tree()
        self.assertEqual((result1, stderr1), (0, ""), msg=stderr1)
        self.assertEqual((result2, stderr2), (0, ""), msg=stderr2)
        self.assertEqual(before, middle)
        self.assertEqual(middle, after)
        self.assertEqual(report1["targets"], report2["targets"])
        self.assertEqual(report1["currentState"], report2["currentState"])
        self.assertEqual(
            report1["transactionDigest"], report2["transactionDigest"]
        )
        expected_paths = mat._update_current_state_paths(
            mat._parse_plan(self.plan_path)
        )
        self.assertEqual(
            [entry["relativePath"] for entry in report1["currentState"]],
            expected_paths,
        )

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_check_write_byte_identity(self, mock_dispatch):
        result, report, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        _, _, transaction_dir, prepared = self._prepare_update_transaction(
            mock_dispatch
        )
        proposed_bytes = {
            target["relativePath"]: (
                transaction_dir / target["relativePath"]
            ).read_bytes()
            for target in prepared["targets"]
        }
        result, write_report, stderr = self._run_update(
            mock_dispatch, "write", report["transactionDigest"]
        )
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        self.assertEqual(report["targets"], write_report["targets"])
        for relative_path, proposed in proposed_bytes.items():
            self.assertEqual((self.repo_root / relative_path).read_bytes(), proposed)

    def test_legacy_create_digest_matches_committed_head(self):
        head_source = subprocess.check_output(
            [
                "git",
                "show",
                "HEAD:tools/source_conversion/materializer/materialize.py",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
        )
        namespace = {
            "__file__": str(
                REPO_ROOT
                / "tools"
                / "source_conversion"
                / "materializer"
                / "materialize.py"
            ),
            "__name__": "committed_head_materializer",
        }
        exec(compile(head_source, namespace["__file__"], "exec"), namespace)
        plan = copy.deepcopy(self.valid_plan)
        targets = [
            {
                "relativePath": "test_artifact.js",
                "sha256": "a" * 64,
                "byteLength": 123,
                "sourcePath": Path("C:/machine-specific/check/test_artifact.js"),
            }
        ]
        self.assertNotIn("operation", plan)
        self.assertEqual(
            namespace["_compute_digest"](plan, targets),
            mat._compute_digest(plan, targets),
        )

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_succeeds_for_existing_generated_artifact(self, mock_dispatch):
        mock_dispatch.return_value = self.valid_ir_update

        import sys
        from io import StringIO
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            ret = mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            self.assertEqual(ret, 0)
            out = mock_stdout.getvalue()

        digest = None
        for line in out.splitlines():
            if '"transactionDigest"' in line:
                digest = line.split('"')[3]
                break
        self.assertIsNotNone(digest)

        ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root), "--expected-digest", digest])
        self.assertEqual(ret, 0)

        reg = self.read_json(self.registry_path)
        self.assertEqual(len(reg["artifacts"]), 1)
        self.assertEqual(reg["artifacts"][0]["upstream"]["version"], "1.2.3")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_nonexistent_artifact(self, mock_dispatch):
        self.registry["artifacts"][0]["artifactId"] = "other_id"
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("artifactId test_artifact not in registry")

    def test_update_rejects_missing_registry_file(self):
        self.registry_path.unlink()
        self._assert_precondition_error("sources_registry.json missing")

    def test_update_rejects_missing_registry_entry(self):
        self.registry["artifacts"] = []
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("artifactId test_artifact not in registry")

    def test_update_rejects_missing_root_js(self):
        self.final_js_path.unlink()
        self._assert_precondition_error("test_artifact.js missing")

    def test_update_rejects_missing_generated_base_js(self):
        self.base_js_path.unlink()
        self._assert_precondition_error(
            "sources_generated/test_artifact.base.js missing"
        )

    def test_update_rejects_missing_ir(self):
        self.ir_path.unlink()
        self._assert_precondition_error("sources_ir/test_artifact.json missing")

    def test_update_rejects_missing_index_file(self):
        (self.repo_root / "index.json").unlink()
        self._assert_precondition_error("index.json missing")

    def test_update_rejects_missing_index_entry(self):
        self.write_json(self.repo_root / "index.json", [])
        self._assert_precondition_error("test_artifact.js not in index")

    def test_update_rejects_non_generated_registry_record(self):
        self.registry["artifacts"][0]["implementation"]["producer"] = "manual"
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("artifact is not generated")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_stale_expected_version(self, mock_dispatch):
        self.old_ir["version"] = "1.0.5"
        self.write_json(self.ir_path, self.old_ir)
        self._assert_precondition_error("stale expectedCurrentLocalVersion")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_same_or_lower_new_version(self, mock_dispatch):
        plan = copy.deepcopy(self.update_plan)
        plan["artifacts"][0]["newLocalVersion"] = "1.0.0"
        self.write_json(self.plan_path, plan)
        ret = mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 1)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_provider_id_mismatch(self, mock_dispatch):
        self.registry["artifacts"][0]["providerId"] = "other_provider"
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("providerId mismatch")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_upstream_project_mismatch(self, mock_dispatch):
        self.registry["artifacts"][0]["upstream"]["project"] = "other/project"
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("upstream project mismatch")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_patch_backed_artifact(self, mock_dispatch):
        (self.repo_root / "sources_patches").mkdir()
        (self.repo_root / "sources_patches" / f"{self.artifact_id}.patch.js").write_text("")
        self._assert_precondition_error("patch-backed artifact not supported")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_check_is_zero_write(self, mock_dispatch):
        mock_dispatch.return_value = self.valid_ir_update
        before = mat._capture_preflight_fingerprint(self.repo_root)
        ret = mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 0)
        after = mat._capture_preflight_fingerprint(self.repo_root)
        self.assertEqual(before, after)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_write_wrong_digest_fails(self, mock_dispatch):
        mock_dispatch.return_value = self.valid_ir_update
        before = self._snapshot_update_state()
        ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root), "--expected-digest", "wrong"])
        self.assertEqual(ret, 1)
        self._assert_exact_update_state(before)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_fault_before_first_replacement_rolls_back(self, mock_dispatch):
        def fail_before_first(source, destination):
            raise OSError("fault before first replacement")

        self._assert_fault_rollback(mock_dispatch, fail_before_first)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_fault_after_first_replacement_rolls_back(self, mock_dispatch):
        original_replace = mat._replace_prepared_sibling
        replacements = 0

        def fail_after_first(source, destination):
            nonlocal replacements
            replacements += 1
            if replacements == 2:
                raise OSError("fault after first replacement")
            return original_replace(source, destination)

        self._assert_fault_rollback(mock_dispatch, fail_after_first)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_fault_after_root_js_replacement_rolls_back(self, mock_dispatch):
        original_replace = mat._replace_prepared_sibling
        index_path = self.repo_root / "index.json"

        def fail_after_root(source, destination):
            if Path(destination) == index_path:
                raise OSError("fault after root JS replacement")
            return original_replace(source, destination)

        self._assert_fault_rollback(mock_dispatch, fail_after_root)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_fault_after_generated_base_replacement_rolls_back(self, mock_dispatch):
        original_replace = mat._replace_prepared_sibling

        def fail_after_base(source, destination):
            if Path(destination) == self.final_js_path:
                raise OSError("fault after generated base replacement")
            return original_replace(source, destination)

        self._assert_fault_rollback(mock_dispatch, fail_after_base)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_fault_after_ir_replacement_rolls_back(self, mock_dispatch):
        original_replace = mat._replace_prepared_sibling

        def fail_after_ir(source, destination):
            if Path(destination) == self.base_js_path:
                raise OSError("fault after IR replacement")
            return original_replace(source, destination)

        self._assert_fault_rollback(mock_dispatch, fail_after_ir)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_fault_immediately_before_index_replacement_rolls_back(
        self, mock_dispatch
    ):
        original_replace = mat._replace_prepared_sibling
        index_path = self.repo_root / "index.json"

        def fail_before_index(source, destination):
            if Path(destination) == index_path:
                raise OSError("fault immediately before index replacement")
            return original_replace(source, destination)

        self._assert_fault_rollback(mock_dispatch, fail_before_index)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_fault_during_index_replacement_rolls_back(self, mock_dispatch):
        plan, fingerprint, transaction_dir, result = self._prepare_update_transaction(
            mock_dispatch
        )
        before = self._snapshot_update_state(plan)
        original_os_replace = mat.os.replace
        index_path = self.repo_root / "index.json"

        def fail_during_index(source, destination):
            if Path(destination) == index_path:
                raise OSError("fault during index replacement")
            return original_os_replace(source, destination)

        with patch.object(mat.os, "replace", side_effect=fail_during_index):
            with self.assertRaisesRegex(
                mat.MaterializationError, "rollback successful"
            ):
                mat._promote_transaction(
                    self.repo_root,
                    transaction_dir,
                    plan,
                    fingerprint,
                    result["targets"],
                )
        self._assert_exact_update_state(before)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_final_guard_rejects_changed_index_before_publication(
        self, mock_dispatch
    ):
        plan, fingerprint, transaction_dir, result = self._prepare_update_transaction(
            mock_dispatch
        )
        index_path = self.repo_root / "index.json"
        index_path.write_bytes(index_path.read_bytes() + b"\n")
        changed_state = self._snapshot_update_state(plan)
        with self.assertRaisesRegex(mat.MaterializationError, "Stale-state guard"):
            mat._promote_transaction(
                self.repo_root,
                transaction_dir,
                plan,
                fingerprint,
                result["targets"],
            )
        self._assert_exact_update_state(changed_state)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_final_guard_rejects_changed_registry_before_publication(
        self, mock_dispatch
    ):
        plan, fingerprint, transaction_dir, result = self._prepare_update_transaction(
            mock_dispatch
        )
        self.registry_path.write_bytes(self.registry_path.read_bytes() + b"\n")
        changed_state = self._snapshot_update_state(plan)
        with patch.object(
            mat, "_replace_prepared_sibling", wraps=mat._replace_prepared_sibling
        ) as publication:
            with self.assertRaisesRegex(mat.MaterializationError, "Stale-state guard"):
                mat._promote_transaction(
                    self.repo_root,
                    transaction_dir,
                    plan,
                    fingerprint,
                    result["targets"],
                )
        publication.assert_not_called()
        self._assert_exact_update_state(changed_state)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rollback(self, mock_dispatch):
        original_replace = mat._replace_prepared_sibling
        index_path = self.repo_root / "index.json"

        def fail_index_publication(source, destination):
            if Path(destination) == index_path:
                raise OSError("mock failure during live index replacement")
            return original_replace(source, destination)

        self._assert_fault_rollback(mock_dispatch, fail_index_publication)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_modified_file_after_check(self, mock_dispatch):
        mock_dispatch.return_value = self.valid_ir_update

        import sys
        from io import StringIO
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
            out = mock_stdout.getvalue()

        digest = None
        for line in out.splitlines():
            if '"transactionDigest"' in line:
                digest = line.split('"')[3]
                break

        self.final_js_path.write_text(self.final_js_path.read_text(encoding="utf-8") + "// change", encoding="utf-8")

        ret = mat.main(["--mode", "write", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root), "--expected-digest", digest])
        self.assertEqual(ret, 1)



    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_runtimeKey_mismatch(self, mock_dispatch):
        mismatched_ir = copy.deepcopy(self.valid_ir_update)
        mismatched_ir["id"] = "wrong_key"
        mock_dispatch.return_value = mismatched_ir
        ret = mat.main(["--mode", "check", "--plan", str(self.plan_path), "--repo-root", str(self.repo_root), "--extensions-root", str(self.extensions_root)])
        self.assertEqual(ret, 1)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_upstream_module_mismatch(self, mock_dispatch):
        self.registry["artifacts"][0]["upstream"]["module"] = "other.module"
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("upstream module mismatch")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_upstream_sourceId_mismatch(self, mock_dispatch):
        self.registry["artifacts"][0]["upstream"]["sourceId"] = "9999"
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("upstream sourceId mismatch")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_upstream_commit_mismatch(self, mock_dispatch):
        self.registry["artifacts"][0]["upstream"]["commit"] = "0" * 40
        self.write_json(self.registry_path, self.registry)
        self._assert_precondition_error("upstream commit mismatch")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_update_rejects_manualPatchRequired_true(self, mock_dispatch):
        self.old_ir["manualPatchRequired"] = True
        self.write_json(self.ir_path, self.old_ir)
        self._assert_precondition_error("manualPatchRequired is true")

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_multi_artifact_rollback_restores_all_artifacts(self, mock_dispatch):
        self._add_second_artifact(include_in_plan=True)
        original_replace = mat._replace_prepared_sibling
        second_ir_path = self.repo_root / "sources_ir" / "test_artifact_two.json"

        def fail_after_first_artifact(source, destination):
            if Path(destination) == second_ir_path:
                raise OSError("fault after first artifact was replaced")
            return original_replace(source, destination)

        self._assert_fault_rollback(mock_dispatch, fail_after_first_artifact)

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_shared_runtime_key_artifacts_cannot_cross_update(self, mock_dispatch):
        self._add_second_artifact(
            shared_runtime_key=True,
            include_in_plan=False,
        )
        sibling_paths = (
            "test_artifact_two.js",
            "sources_generated/test_artifact_two.base.js",
            "sources_ir/test_artifact_two.json",
        )
        sibling_before = {
            path: (self.repo_root / path).read_bytes() for path in sibling_paths
        }
        registry_before = self.read_json(self.registry_path)
        sibling_record_before = next(
            item
            for item in registry_before["artifacts"]
            if item["artifactId"] == "test_artifact_two"
        )
        index_before = self.read_json(self.repo_root / "index.json")
        sibling_index_before = next(
            item
            for item in index_before
            if item["fileName"] == "test_artifact_two.js"
        )

        result, report, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual((result, stderr), (0, ""), msg=stderr)
        result, _, stderr = self._run_update(
            mock_dispatch, "write", report["transactionDigest"]
        )
        self.assertEqual((result, stderr), (0, ""), msg=stderr)

        for path, payload in sibling_before.items():
            self.assertEqual((self.repo_root / path).read_bytes(), payload)
        registry_after = self.read_json(self.registry_path)
        by_id = {item["artifactId"]: item for item in registry_after["artifacts"]}
        self.assertEqual(by_id["test_artifact_two"], sibling_record_before)
        self.assertEqual(
            by_id["test_artifact"]["compatibility"],
            {"sharedRuntimeKeyGroup": "en_test_artifact"},
        )
        self.assertEqual(
            by_id["test_artifact"]["runtimeKey"],
            by_id["test_artifact_two"]["runtimeKey"],
        )
        index_after = self.read_json(self.repo_root / "index.json")
        sibling_index_after = next(
            item
            for item in index_after
            if item["fileName"] == "test_artifact_two.js"
        )
        self.assertEqual(sibling_index_after, sibling_index_before)
        self.assertIn(b'version = "1.0.1"', self.final_js_path.read_bytes())

    @patch('tools.source_conversion.materializer.materialize.dispatch_extraction')
    def test_shared_runtime_key_mixed_sibling_metadata_is_rejected(
        self, mock_dispatch
    ):
        self._add_second_artifact(
            shared_runtime_key=True,
            include_in_plan=False,
        )
        mixed_plan = copy.deepcopy(self.update_plan)
        mixed_plan["artifacts"][0]["sourceId"] = "5678"
        self.write_json(self.plan_path, mixed_plan)
        before = self._snapshot_tree()
        result, _, stderr = self._run_update(mock_dispatch, "check")
        self.assertEqual(result, 1)
        self.assertIn("upstream module mismatch", stderr)
        self.assertEqual(self._snapshot_tree(), before)
