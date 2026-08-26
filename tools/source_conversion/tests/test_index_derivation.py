import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.validator.validate_registry import (
    IndexDerivationError,
    derive_index,
    main as validate_registry_main,
    validate_repository,
)


def artifact(artifact_id, runtime_key, **extra):
    value = {
        "artifactId": artifact_id,
        "runtimeKey": runtime_key,
        "providerId": artifact_id,
        "implementation": {"producer": "manual"},
    }
    value.update(extra)
    return value


def final_js(name, key, version):
    fields = [
        "class TestSource extends ComicSource {",
        f'    name = "{name}"',
        f'    key = "{key}"',
    ]
    if version is not None:
        fields.append(f'    version = "{version}"')
    fields.append("}")
    return "\n".join(fields) + "\n"


class TestIndexDerivation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_registry(self, artifacts):
        (self.root / "sources_registry.json").write_text(
            json.dumps(
                {"schemaVersion": "1.0", "artifacts": artifacts},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def write_source(self, artifact_id, name, key, version):
        (self.root / f"{artifact_id}.js").write_text(
            final_js(name, key, version),
            encoding="utf-8",
        )

    def write_index(self, entries):
        (self.root / "index.json").write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_canonical_field_ownership_and_registry_order(self):
        artifacts = [
            artifact(
                "zeta",
                "zeta_runtime",
                catalogName="Catalog Zeta",
                catalogDescription="Catalog-only description",
            ),
            artifact("alpha", "alpha_runtime"),
        ]
        self.write_registry(artifacts)
        self.write_source("zeta", "Runtime Zeta", "zeta_runtime", "9.8.7")
        self.write_source("alpha", "Runtime Alpha", "alpha_runtime", "1.2.3")

        entries = derive_index(self.root)

        self.assertEqual(
            [entry["fileName"] for entry in entries],
            ["zeta.js", "alpha.js"],
        )
        self.assertEqual(
            entries[0],
            {
                "name": "Catalog Zeta",
                "fileName": "zeta.js",
                "key": "zeta_runtime",
                "version": "9.8.7",
                "description": "Catalog-only description",
            },
        )
        self.assertEqual(
            entries[1],
            {
                "name": "Runtime Alpha",
                "fileName": "alpha.js",
                "key": "alpha_runtime",
                "version": "1.2.3",
            },
        )
        self.assertNotIn("description", entries[1])

    def test_duplicate_runtime_keys_remain_distinct_copy_manga_artifacts(self):
        shared = {"sharedRuntimeKeyGroup": "copy_manga"}
        artifacts = [
            artifact("copy_manga", "copy_manga", compatibility=shared),
            artifact(
                "copy_manga_multi_accounts",
                "copy_manga",
                compatibility=shared,
                catalogName="拷贝漫画(多账号)",
            ),
        ]
        self.write_registry(artifacts)
        self.write_source("copy_manga", "拷贝漫画", "copy_manga", "1.4.1")
        self.write_source(
            "copy_manga_multi_accounts",
            "拷贝漫画M",
            "copy_manga",
            "1.4.1",
        )

        entries = derive_index(self.root)

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            [entry["fileName"] for entry in entries],
            ["copy_manga.js", "copy_manga_multi_accounts.js"],
        )
        self.assertEqual([entry["key"] for entry in entries], ["copy_manga"] * 2)

    def test_runtime_key_mismatch_fails_closed(self):
        self.write_registry([artifact("sample", "registry_key")])
        self.write_source("sample", "Sample", "runtime_key", "1.0.0")

        with self.assertRaises(IndexDerivationError) as caught:
            derive_index(self.root)

        self.assertTrue(
            any(item.code == "RUNTIME_KEY_MISMATCH" for item in caught.exception.diagnostics)
        )

    def test_missing_final_js_fails_closed(self):
        self.write_registry([artifact("missing", "missing")])

        with self.assertRaises(IndexDerivationError) as caught:
            derive_index(self.root)

        self.assertTrue(
            any(item.code == "ARTIFACT_FILE_MISSING" for item in caught.exception.diagnostics)
        )

    def test_malformed_final_js_fails_closed(self):
        self.write_registry([artifact("malformed", "malformed")])
        self.write_source("malformed", "Malformed", "malformed", "1.0.0")
        with (self.root / "malformed.js").open("a", encoding="utf-8") as handle:
            handle.write("}\n")

        with self.assertRaises(IndexDerivationError) as caught:
            derive_index(self.root)

        self.assertTrue(
            any(item.code == "FINAL_JS_MALFORMED" for item in caught.exception.diagnostics)
        )

    def canonical_fixture(self):
        artifacts = [
            artifact("first", "first"),
            artifact("second", "second"),
        ]
        self.write_registry(artifacts)
        self.write_source("first", "First", "first", "1.0.0")
        self.write_source("second", "Second", "second", "2.0.0")
        return derive_index(self.root)

    def test_stale_checked_in_version_is_detected(self):
        entries = self.canonical_fixture()
        entries[0]["version"] = "0.9.0"
        self.write_index(entries)

        result = validate_repository(self.root)

        self.assertEqual(len(result.with_code("INDEX_VERSION_MISMATCH")), 1)

    def test_check_index_mode_is_non_writing_and_fails_on_drift(self):
        entries = self.canonical_fixture()
        entries[0]["version"] = "0.9.0"
        self.write_index(entries)
        before = (self.root / "index.json").read_bytes()

        with redirect_stdout(io.StringIO()):
            exit_code = validate_registry_main(
                ["--repo-root", str(self.root), "--check-index"]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual((self.root / "index.json").read_bytes(), before)

    def test_default_mode_is_non_writing(self):
        entries = self.canonical_fixture()
        entries[0]["version"] = "0.9.0"
        self.write_index(entries)
        before = (self.root / "index.json").read_bytes()

        with redirect_stdout(io.StringIO()):
            exit_code = validate_registry_main(["--repo-root", str(self.root)])

        self.assertEqual(exit_code, 0)
        self.assertEqual((self.root / "index.json").read_bytes(), before)

    def test_write_index_replaces_stale_data_exactly_and_is_idempotent(self):
        canonical = self.canonical_fixture()
        stale = [dict(entry) for entry in reversed(canonical)]
        stale[0]["version"] = "0.0.1"
        stale[0]["legacyField"] = "must not survive"
        self.write_index(stale)

        with redirect_stdout(io.StringIO()):
            first_exit = validate_registry_main(
                ["--repo-root", str(self.root), "--write-index"]
            )
        first_bytes = (self.root / "index.json").read_bytes()

        self.assertEqual(first_exit, 0)
        self.assertEqual(json.loads(first_bytes), canonical)
        self.assertEqual(
            first_bytes,
            (json.dumps(canonical, ensure_ascii=False, indent=4) + "\n").encode("utf-8"),
        )

        with redirect_stdout(io.StringIO()):
            second_exit = validate_registry_main(
                ["--repo-root", str(self.root), "--write-index"]
            )

        self.assertEqual(second_exit, 0)
        self.assertEqual((self.root / "index.json").read_bytes(), first_bytes)

    def assert_write_refused(self):
        before = (self.root / "index.json").read_bytes()
        with redirect_stdout(io.StringIO()):
            exit_code = validate_registry_main(
                ["--repo-root", str(self.root), "--write-index"]
            )
        self.assertEqual(exit_code, 1)
        self.assertEqual((self.root / "index.json").read_bytes(), before)

    def test_write_refuses_duplicate_artifact_identity(self):
        self.write_registry(
            [artifact("duplicate", "duplicate"), artifact("duplicate", "duplicate")]
        )
        self.write_source("duplicate", "Duplicate", "duplicate", "1.0.0")
        self.write_index([{"stale": True}])
        self.assert_write_refused()

    def test_write_refuses_missing_final_js(self):
        self.write_registry([artifact("missing", "missing")])
        self.write_index([{"stale": True}])
        self.assert_write_refused()

    def test_write_refuses_malformed_final_js(self):
        self.write_registry([artifact("malformed", "malformed")])
        self.write_source("malformed", "Malformed", "malformed", "1.0.0")
        with (self.root / "malformed.js").open("a", encoding="utf-8") as handle:
            handle.write("}\n")
        self.write_index([{"stale": True}])
        self.assert_write_refused()

    def test_write_refuses_runtime_key_mismatch(self):
        self.write_registry([artifact("sample", "registry_key")])
        self.write_source("sample", "Sample", "runtime_key", "1.0.0")
        self.write_index([{"stale": True}])
        self.assert_write_refused()

    def test_write_preserves_shared_keys_order_and_optional_descriptions(self):
        shared = {"sharedRuntimeKeyGroup": "copy_manga"}
        artifacts = [
            artifact(
                "copy_manga_multi_accounts",
                "copy_manga",
                compatibility=shared,
                catalogName="拷贝漫画(多账号)",
                catalogDescription="Multi-account source",
            ),
            artifact("copy_manga", "copy_manga", compatibility=shared),
        ]
        self.write_registry(artifacts)
        self.write_source(
            "copy_manga_multi_accounts", "Runtime Multi", "copy_manga", "1.4.1"
        )
        self.write_source("copy_manga", "拷贝漫画", "copy_manga", "1.4.1")
        self.write_index(
            [
                {
                    "name": "Stale borrowed name",
                    "fileName": "copy_manga.js",
                    "key": "copy_manga",
                    "version": "0.0.0",
                    "description": "stale description",
                    "legacy": True,
                }
            ]
        )

        with redirect_stdout(io.StringIO()):
            exit_code = validate_registry_main(
                ["--repo-root", str(self.root), "--write-index"]
            )
        written = json.loads((self.root / "index.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            [entry["fileName"] for entry in written],
            ["copy_manga_multi_accounts.js", "copy_manga.js"],
        )
        self.assertEqual([entry["key"] for entry in written], ["copy_manga"] * 2)
        self.assertEqual(written[0]["description"], "Multi-account source")
        self.assertNotIn("description", written[1])
        self.assertEqual(written[1]["name"], "拷贝漫画")
        self.assertTrue(all("legacy" not in entry for entry in written))

    def test_description_drift_is_detected(self):
        artifacts = [
            artifact(
                "described",
                "described",
                catalogDescription="Canonical description",
            )
        ]
        self.write_registry(artifacts)
        self.write_source("described", "Described", "described", "1.0.0")
        entries = derive_index(self.root)
        entries[0].pop("description")
        self.write_index(entries)

        result = validate_repository(self.root)

        self.assertEqual(len(result.with_code("INDEX_DESCRIPTION_MISMATCH")), 1)

    def test_unexpected_index_entry_is_detected(self):
        entries = self.canonical_fixture()
        self.write_source("extra", "Extra", "extra", "1.0.0")
        entries.append(
            {
                "name": "Extra",
                "fileName": "extra.js",
                "key": "extra",
                "version": "1.0.0",
            }
        )
        self.write_index(entries)

        result = validate_repository(self.root)

        self.assertEqual(len(result.with_code("INDEX_ENTRY_EXTRA")), 1)

    def test_missing_index_entry_is_detected(self):
        entries = self.canonical_fixture()
        self.write_index(entries[:-1])

        result = validate_repository(self.root)

        self.assertEqual(len(result.with_code("INDEX_ENTRY_MISSING")), 1)

    def test_ordering_drift_is_detected(self):
        entries = self.canonical_fixture()
        self.write_index(list(reversed(entries)))

        result = validate_repository(self.root)

        self.assertEqual(len(result.with_code("INDEX_ORDER_MISMATCH")), 1)


if __name__ == "__main__":
    unittest.main()
