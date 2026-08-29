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
        mat._check_collisions(plan, self.repo_root)
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
                    mat._check_collisions(self.valid_plan, self.repo_root)
                path.unlink()

        registry = self.read_json(self.repo_root / "sources_registry.json")
        registry["artifacts"].append({"artifactId": "test_artifact"})
        self.write_json(self.repo_root / "sources_registry.json", registry)
        with self.assertRaisesRegex(mat.MaterializationError, "already exists in registry"):
            mat._check_collisions(self.valid_plan, self.repo_root)

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
            mat._check_collisions(self.valid_plan, self.repo_root)

    def test_manual_patch_ir_is_rejected_without_patch_consumption(self):
        with self.assertRaisesRegex(mat.MaterializationError, "requires manual patching"):
            mat._compose_final_js(
                {"pages": {"manualPatchRequired": True}}, b"generated"
            )


if __name__ == '__main__':
    unittest.main()
