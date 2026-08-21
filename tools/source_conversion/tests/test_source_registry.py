import copy
import json
import sys
import unittest
from pathlib import Path


repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.patcher.js_patcher import patch_js
from tools.source_conversion.validator.validate_ir import validate_ir_data
from tools.source_conversion.validator.validate_registry import (
    is_bcp47_locale,
    validate_registry_data,
    validate_repository,
)


EXPECTED_RUNTIME_KEYS = {
    "baozi": "baozi",
    "ccc": "ccc",
    "comic_walker": "comic_walker",
    "comicabc": "zh_Hant_comicabc",
    "comick": "comick",
    "copy_manga": "copy_manga",
    "copy_manga_multi_accounts": "copy_manga",
    "ehentai": "ehentai",
    "flamecomics": "en_flamecomics",
    "goda": "goda",
    "happy": "happy",
    "hcomic": "hcomic",
    "hitomi": "hitomi",
    "hot_manga": "hot_manga",
    "ikmmh": "ikmmh",
    "jcomic": "jcomic",
    "jm": "jm",
    "kavita": "kavita",
    "komga": "komga",
    "komiic": "Komiic",
    "lanraragi": "lanraragi",
    "manga_dex": "manga_dex",
    "manhuagui": "ManHuaGui",
    "manhuaren": "manhuaren",
    "manhuashe": "zh_Hans_manhuashe",
    "manwaba": "manwaba",
    "mh1234": "mh1234",
    "mh18": "mh18",
    "mxs": "mxs",
    "mycomic": "mycomic",
    "nhentai": "nhentai",
    "picacg": "picacg",
    "shonen_jump_plus": "shonen_jump_plus",
    "webtoons": "en_webtoons",
    "webtoons_zh_hant": "zh_Hant_webtoons",
    "wnacg": "wnacg",
    "ykmh": "ykmh",
    "zaimanhua": "zaimanhua",
}

CONVERTED_ARTIFACTS = {
    "comicabc",
    "flamecomics",
    "manhuashe",
    "webtoons",
    "webtoons_zh_hant",
}

EXPECTED_CONVERTED_UPSTREAM = {
    "webtoons": ("2522335540328470744", "1.4.57", "1.4"),
    "webtoons_zh_hant": ("2959982438613576472", "1.4.57", "1.4"),
    "manhuashe": ("6230622879116184108", "1.6.1", "1.6"),
    "comicabc": ("8110122805257580230", "1.4.3", "1.4"),
    "flamecomics": ("8531542650987673943", "1.4.50", "1.4"),
}


class TestSourceRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_path = repo_root / "sources_registry.json"
        cls.schema_path = (
            repo_root
            / "tools"
            / "source_conversion"
            / "schema"
            / "source_registry.schema.json"
        )
        cls.registry = json.loads(cls.registry_path.read_text(encoding="utf-8"))
        cls.schema = json.loads(cls.schema_path.read_text(encoding="utf-8"))
        cls.artifacts = cls.registry["artifacts"]
        cls.by_id = {item["artifactId"]: item for item in cls.artifacts}

    def test_registry_schema_validation(self):
        result = validate_registry_data(self.registry)
        self.assertEqual(result.errors, ())
        self.assertFalse(self.schema["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["artifact"]["additionalProperties"])
        self.assertFalse(self.schema["$defs"]["upstream"]["additionalProperties"])
        source_id_schema = self.schema["$defs"]["upstream"]["properties"]["sourceId"]
        self.assertEqual(source_id_schema["type"], "string")

        invalid = copy.deepcopy(self.registry)
        invalid["artifacts"][0]["typoField"] = True
        self.assertTrue(validate_registry_data(invalid).with_code("SCHEMA_UNKNOWN_FIELD"))

    def test_all_38_catalog_artifacts_are_registered(self):
        index = json.loads((repo_root / "index.json").read_text(encoding="utf-8"))
        indexed_ids = {Path(entry["fileName"]).stem for entry in index}
        self.assertEqual(len(self.artifacts), 38)
        self.assertEqual(set(self.by_id), indexed_ids)

    def test_artifact_ids_are_unique(self):
        artifact_ids = [item["artifactId"] for item in self.artifacts]
        self.assertEqual(len(artifact_ids), len(set(artifact_ids)))
        self.assertFalse(validate_registry_data(self.registry).with_code("DUPLICATE_ARTIFACT_ID"))

    def test_artifact_id_filename_linkage(self):
        for artifact_id in self.by_id:
            final_path = repo_root / f"{artifact_id}.js"
            self.assertTrue(final_path.is_file(), artifact_id)
            self.assertEqual(final_path.stem, artifact_id)
        result = validate_repository(repo_root)
        self.assertFalse(result.with_code("ARTIFACT_FILE_MISSING"))

    def test_existing_runtime_keys_are_frozen(self):
        actual = {item["artifactId"]: item["runtimeKey"] for item in self.artifacts}
        self.assertEqual(actual, EXPECTED_RUNTIME_KEYS)
        result = validate_repository(repo_root)
        self.assertFalse(result.with_code("RUNTIME_KEY_MISMATCH"))

    def test_copy_manga_shared_runtime_slot_is_explicitly_reported(self):
        result = validate_repository(repo_root)
        reports = result.with_code("SHARED_RUNTIME_KEY")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].severity, "REPORT")
        self.assertEqual(reports[0].subject, "copy_manga")
        self.assertIn("copy_manga_multi_accounts", reports[0].message)
        self.assertFalse(result.with_code("DUPLICATE_RUNTIME_KEY"))

    def test_unique_runtime_key_must_not_declare_shared_group(self):
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [copy.deepcopy(self.by_id["komiic"])],
        }
        registry["artifacts"][0]["compatibility"] = {
            "sharedRuntimeKeyGroup": "copy_manga"
        }

        result = validate_registry_data(registry)

        errors = result.with_code("UNNECESSARY_SHARED_RUNTIME_KEY_GROUP")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].severity, "ERROR")
        self.assertEqual(errors[0].subject, "komiic")

    def test_duplicate_runtime_key_without_group_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["copy_manga"]),
            copy.deepcopy(self.by_id["copy_manga_multi_accounts"]),
        ]
        for artifact in artifacts:
            artifact.pop("compatibility")

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        errors = result.with_code("DUPLICATE_RUNTIME_KEY")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].severity, "ERROR")
        self.assertIn("<missing>", errors[0].message)

    def test_duplicate_runtime_key_with_partial_grouping_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["copy_manga"]),
            copy.deepcopy(self.by_id["copy_manga_multi_accounts"]),
        ]
        artifacts[1].pop("compatibility")

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        self.assertEqual(len(result.with_code("DUPLICATE_RUNTIME_KEY")), 1)
        self.assertEqual(
            len(result.with_code("INVALID_SHARED_RUNTIME_KEY_GROUP")), 1
        )

    def test_shared_group_spanning_different_runtime_keys_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["komiic"]),
            copy.deepcopy(self.by_id["baozi"]),
        ]
        for artifact in artifacts:
            artifact["compatibility"] = {
                "sharedRuntimeKeyGroup": "cross_runtime_group"
            }

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        errors = result.with_code("INVALID_SHARED_RUNTIME_KEY_GROUP")
        self.assertEqual(len(errors), 1)
        self.assertIn("spans runtimeKeys", errors[0].message)
        self.assertEqual(
            len(result.with_code("UNNECESSARY_SHARED_RUNTIME_KEY_GROUP")), 2
        )

    def test_duplicate_runtime_key_split_across_groups_is_rejected(self):
        artifacts = [
            copy.deepcopy(self.by_id["copy_manga"]),
            copy.deepcopy(self.by_id["copy_manga_multi_accounts"]),
        ]
        artifacts[0]["compatibility"]["sharedRuntimeKeyGroup"] = "copy_group_a"
        artifacts[1]["compatibility"]["sharedRuntimeKeyGroup"] = "copy_group_b"

        result = validate_registry_data(
            {"schemaVersion": "1.0", "artifacts": artifacts}
        )

        self.assertEqual(len(result.with_code("DUPLICATE_RUNTIME_KEY")), 1)
        self.assertEqual(
            len(result.with_code("INVALID_SHARED_RUNTIME_KEY_GROUP")), 2
        )

    def test_upstream_source_ids_are_json_strings(self):
        upstream_records = [item["upstream"] for item in self.artifacts if "upstream" in item]
        self.assertEqual(len(upstream_records), 5)
        self.assertTrue(all(isinstance(item["sourceId"], str) for item in upstream_records))

        invalid = copy.deepcopy(self.registry)
        invalid["artifacts"][-1]["upstream"]["sourceId"] = 8531542650987673943
        errors = validate_registry_data(invalid).with_code("SCHEMA_FIELD_VALUE")
        self.assertTrue(any("upstream.sourceId" in error.message for error in errors))

    def test_current_converted_upstream_metadata_anchors(self):
        actual = {
            artifact_id: (
                self.by_id[artifact_id]["upstream"]["sourceId"],
                self.by_id[artifact_id]["upstream"]["version"],
                self.by_id[artifact_id]["upstream"]["extensionLib"],
            )
            for artifact_id in CONVERTED_ARTIFACTS
        }
        self.assertEqual(actual, EXPECTED_CONVERTED_UPSTREAM)

    def test_bcp47_locale_acceptance_and_rejection(self):
        for locale in ("en", "zh-Hans", "zh-Hant"):
            self.assertTrue(is_bcp47_locale(locale), locale)
        for locale in ("zh_Hant", "ZH-hant", "zh-hans", "english", ""):
            self.assertFalse(is_bcp47_locale(locale), locale)

        invalid = copy.deepcopy(self.registry)
        invalid["artifacts"][-1]["locales"] = ["zh_Hant"]
        self.assertTrue(validate_registry_data(invalid).with_code("INVALID_LOCALE"))

    def test_registry_ir_artifact_linkage(self):
        links = {}
        for ir_path in sorted((repo_root / "sources_ir").glob("*.json")):
            ir = json.loads(ir_path.read_text(encoding="utf-8"))
            links[ir_path.stem] = ir["artifactId"]
        self.assertEqual(set(links), CONVERTED_ARTIFACTS)
        self.assertTrue(all(stem == artifact_id for stem, artifact_id in links.items()))

        result = validate_repository(repo_root)
        linkage_errors = {
            "IR_ARTIFACT_LINK_MISSING",
            "IR_ARTIFACT_FILENAME_MISMATCH",
            "IR_ARTIFACT_UNREGISTERED",
            "DUPLICATE_IR_ARTIFACT_LINK",
            "REGISTRY_IR_LINK_MISSING",
        }
        self.assertFalse([d for d in result.errors if d.code in linkage_errors])

    def test_ir_v0_2_version_schema_compatibility(self):
        schema_path = (
            repo_root
            / "tools"
            / "source_conversion"
            / "schema"
            / "ir_v0_2.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertIn("version", schema["properties"])
        self.assertEqual(
            schema["properties"]["version"]["pattern"],
            "^[0-9]+\\.[0-9]+\\.[0-9]+$",
        )
        for artifact_id in ("comicabc", "flamecomics", "manhuashe"):
            ir = json.loads(
                (repo_root / "sources_ir" / f"{artifact_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(validate_ir_data(ir), [], artifact_id)

    def test_index_mismatches_are_reported_without_mutation(self):
        index_path = repo_root / "index.json"
        before = index_path.read_bytes()
        result = validate_repository(repo_root)
        after = index_path.read_bytes()
        self.assertEqual(after, before)
        self.assertEqual(len(result.with_code("INDEX_NAME_MISMATCH")), 2)
        self.assertEqual(len(result.with_code("INDEX_VERSION_MISMATCH")), 4)
        self.assertEqual(len(result.with_code("INDEX_KEY_MISMATCH")), 0)
        self.assertTrue(all(d.severity == "WARNING" for d in result.warnings))

    def test_registry_linkage_does_not_change_generated_or_final_sources(self):
        tracked_paths = []
        for artifact_id in sorted(CONVERTED_ARTIFACTS):
            tracked_paths.extend(
                [
                    repo_root / "sources_generated" / f"{artifact_id}.base.js",
                    repo_root / f"{artifact_id}.js",
                ]
            )
        before = {path: path.read_bytes() for path in tracked_paths}

        for artifact_id in sorted(CONVERTED_ARTIFACTS):
            ir = json.loads(
                (repo_root / "sources_ir" / f"{artifact_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            base_path = repo_root / "sources_generated" / f"{artifact_id}.base.js"
            patch_path = repo_root / "sources_patches" / f"{artifact_id}.patch.js"
            final_path = repo_root / f"{artifact_id}.js"
            generated = generate_venera_js(ir)
            self.assertEqual(generated, base_path.read_text(encoding="utf-8"), artifact_id)
            composed = patch_js(generated, patch_path.read_text(encoding="utf-8"))
            self.assertEqual(composed, final_path.read_text(encoding="utf-8"), artifact_id)

        validate_repository(repo_root)
        after = {path: path.read_bytes() for path in tracked_paths}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
