import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.source_conversion.inventory.generate_static_inventory import (
    InventoryGenerationError,
    generate_from_checkout,
    generate_inventory,
    read_git_head,
    serialize_inventory,
)
from tools.source_conversion.validator.validate_inventory import (
    validate_inventory_data,
)


PROJECT = "keiyoushi/extensions-source"
COMMIT = "5e06c412c0264b18120fd963fdd6efb529f3fa29"


class TestStaticInventoryGenerator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_module(self, module: str, content: str) -> Path:
        build_file = self.root / "src" / Path(*module.split(".")) / "build.gradle.kts"
        build_file.parent.mkdir(parents=True, exist_ok=True)
        build_file.write_text(content, encoding="utf-8", newline="\n")
        return build_file

    def static_source(
        self,
        *,
        name: str = "Static Source",
        lang: str = "en",
        source_id: str | None = "12345",
        url: str = "https://static.example",
    ) -> str:
        id_line = f"id = {source_id}L" if source_id is not None else ""
        return f'''keiyoushi {{
    name = "Extension"
    versionCode = 2
    libVersion = "1.6"
    contentWarning = ContentWarning.SAFE
    source {{
        name = "{name}"
        lang = "{lang}"
        {id_line}
        baseUrl = "{url}"
    }}
}}
'''

    def generate(self):
        return generate_inventory(self.root, PROJECT, COMMIT)

    def snapshot_files(self):
        return {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }

    def test_one_statically_resolvable_source(self):
        self.write_module("en.static", self.static_source())
        candidate = self.generate()["candidates"][0]
        self.assertEqual(candidate["name"], "Static Source")
        self.assertEqual(candidate["baseUrl"], "https://static.example")
        self.assertEqual(candidate["compatibility"]["metadataResolution"], "static")

    def test_static_candidate_extraction_is_unclassified(self):
        self.write_module("en.unclassified", self.static_source())
        compatibility = self.generate()["candidates"][0]["compatibility"]
        self.assertEqual(compatibility["extraction"], "unclassified")

    def test_unclassified_candidate_omits_patch_required(self):
        self.write_module("en.unknownpatch", self.static_source())
        compatibility = self.generate()["candidates"][0]["compatibility"]
        self.assertNotIn("patchRequired", compatibility)

    def test_explicit_source_id_is_preserved_as_string(self):
        self.write_module("en.explicit", self.static_source(source_id="9223372036854775806"))
        self.assertEqual(self.generate()["candidates"][0]["sourceId"], "9223372036854775806")

    def test_auto_computed_source_id_uses_existing_parser_algorithm(self):
        self.write_module(
            "en.generated",
            self.static_source(name="Webtoons.com", source_id=None),
        )
        self.assertEqual(self.generate()["candidates"][0]["sourceId"], "2522335540328470744")

    def test_multiple_static_source_blocks_in_one_module(self):
        self.write_module(
            "en.multi",
            '''keiyoushi {
    name = "Multi"
    versionCode = 1
    libVersion = "1.6"
    contentWarning = ContentWarning.MIXED
    source { name = "One"; lang = "en"; id = 1L; baseUrl = "https://one.example" }
    source { name = "Two"; lang = "fr"; id = 2L; baseUrl = "https://two.example" }
}
''',
        )
        inventory = self.generate()
        self.assertEqual([item["sourceId"] for item in inventory["candidates"]], ["1", "2"])
        self.assertEqual(inventory["unresolvedModules"], [])

    def test_literal_source_construction_is_statically_expanded(self):
        self.write_module(
            "all.dynamic",
            '''keiyoushi {
    name = "Dynamic"
    versionCode = 1
    libVersion = "1.6"
    listOf("en", "fr").forEach { langCode ->
        source { lang = langCode; baseUrl = "https://dynamic.example" }
    }
}
''',
        )
        inventory = self.generate()
        self.assertEqual(
            {candidate["upstreamLang"] for candidate in inventory["candidates"]},
            {"en", "fr"},
        )
        self.assertEqual(inventory["unresolvedModules"], [])

    def test_unresolved_module_emits_no_guessed_candidate(self):
        self.write_module(
            "all.dynamic",
            '''keiyoushi {
    name = "Dynamic"
    versionCode = 1
    libVersion = "1.6"
    source { lang = providers.gradleProperty("lang").get() }
}
''',
        )
        inventory = self.generate()
        self.assertEqual(inventory["candidates"], [])
        self.assertNotIn("sourceId", inventory["unresolvedModules"][0])

    def test_raw_all_language_is_preserved(self):
        self.write_module("all.raw", self.static_source(lang="all"))
        self.assertEqual(self.generate()["candidates"][0]["upstreamLang"], "all")

    def test_canonical_locale_is_not_guessed_for_all(self):
        self.write_module("all.raw", self.static_source(lang="all"))
        self.assertNotIn("canonicalLocale", self.generate()["candidates"][0])

    def test_candidate_identity_is_project_and_source_id(self):
        self.write_module("en.identity", self.static_source(source_id="400"))
        candidate = self.generate()["candidates"][0]
        self.assertEqual((candidate["project"], candidate["sourceId"]), (PROJECT, "400"))

    def test_module_locator_uses_contract_lowercase_normalization(self):
        self.write_module("id.Luvyaa", self.static_source(source_id="402"))
        self.assertEqual(self.generate()["candidates"][0]["module"], "id.luvyaa")

    def test_module_change_does_not_change_candidate_identity(self):
        self.write_module("en.before", self.static_source(source_id="401"))
        before = self.generate()["candidates"][0]
        (self.root / "src" / "en" / "before").rename(self.root / "src" / "en" / "after")
        after = self.generate()["candidates"][0]
        self.assertEqual((before["project"], before["sourceId"]), (after["project"], after["sourceId"]))
        self.assertNotEqual(before["module"], after["module"])

    def test_duplicate_candidate_identity_fails_closed(self):
        self.write_module("en.first", self.static_source(source_id="500"))
        self.write_module("en.second", self.static_source(source_id="500"))
        with self.assertRaisesRegex(InventoryGenerationError, "CANDIDATE_IDENTITY_DUPLICATE"):
            self.generate()

    def test_duplicate_expanded_candidate_identity_fails_closed(self):
        self.write_module(
            "all.duplicate",
            '''keiyoushi {
    name = "Duplicate"
    versionCode = 1
    libVersion = "1.6"
    contentWarning = ContentWarning.SAFE
    listOf("en", "en").forEach { lang ->
        source { lang = lang; baseUrl = "https://duplicate.example" }
    }
}
''',
        )
        with self.assertRaisesRegex(InventoryGenerationError, "CANDIDATE_IDENTITY_DUPLICATE"):
            self.generate()

    def test_static_candidate_survives_unsupported_template_in_same_module(self):
        self.write_module(
            "all.mixed",
            '''keiyoushi {
    name = "Mixed"
    versionCode = 1
    libVersion = "1.6"
    contentWarning = ContentWarning.SAFE
    source { name = "Static"; lang = "en"; id = 42L; baseUrl = "https://static.example" }
    helper().forEach { lang ->
        source { lang = lang; baseUrl = "https://dynamic.example" }
    }
}
''',
        )
        inventory = self.generate()
        self.assertEqual([item["sourceId"] for item in inventory["candidates"]], ["42"])
        self.assertEqual(
            inventory["unresolvedModules"][0]["reason"]["code"],
            "unresolved-required-metadata",
        )

    def test_candidate_order_is_deterministic(self):
        self.write_module("en.zed", self.static_source(name="Zed", source_id="20"))
        self.write_module("en.alpha", self.static_source(name="Alpha", source_id="10"))
        self.assertEqual(
            [item["sourceId"] for item in self.generate()["candidates"]],
            ["10", "20"],
        )

    def test_unresolved_module_order_is_deterministic(self):
        self.write_module("fr.zed", "keiyoushi { name = \"Zed\" }")
        self.write_module("all.alpha", "keiyoushi { name = \"Alpha\" }")
        self.assertEqual(
            [item["module"] for item in self.generate()["unresolvedModules"]],
            ["all.alpha", "fr.zed"],
        )

    def test_repeated_serialization_is_byte_identical(self):
        self.write_module("zh.repeat", self.static_source(name="漫画社", lang="zh"))
        first = serialize_inventory(self.generate())
        second = serialize_inventory(self.generate())
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertNotIn(b"\r\n", first)

    def test_repeated_expanded_serialization_is_byte_identical(self):
        self.write_module(
            "all.repeat",
            '''keiyoushi {
    name = "Repeat"
    versionCode = 1
    libVersion = "1.6"
    contentWarning = ContentWarning.SAFE
    listOf("fr", "en", "de").forEach { lang ->
        source { lang = lang; baseUrl = "https://repeat.example/$lang" }
    }
}
''',
        )
        first = serialize_inventory(self.generate())
        second = serialize_inventory(self.generate())
        self.assertEqual(first, second)
        self.assertEqual(
            json.loads(first)["candidates"],
            sorted(
                json.loads(first)["candidates"],
                key=lambda item: (
                    item["project"],
                    item["sourceId"],
                    item["module"],
                    item["name"],
                    item["upstreamLang"],
                ),
            ),
        )

    def test_pinned_commit_is_recorded_at_root_only(self):
        self.write_module("en.pin", self.static_source())
        inventory = self.generate()
        self.assertEqual(inventory["upstreams"], [{"project": PROJECT, "commit": COMMIT}])
        self.assertNotIn("commit", inventory["candidates"][0])

    @patch(
        "tools.source_conversion.inventory.generate_static_inventory.read_git_head",
        return_value="0123456789abcdef0123456789abcdef01234567",
    )
    def test_expected_commit_mismatch_fails_closed(self, _read_head):
        with self.assertRaisesRegex(InventoryGenerationError, "Pinned commit mismatch"):
            generate_from_checkout(self.root, PROJECT, expected_commit=COMMIT)

    @patch("tools.source_conversion.inventory.generate_static_inventory.subprocess.run")
    def test_git_head_probe_uses_process_local_safe_directory(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = COMMIT + "\n"
        run.return_value.stderr = ""
        self.assertEqual(read_git_head(self.root), COMMIT)
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["git", "-c"])
        self.assertEqual(command[2], f"safe.directory={self.root.resolve()}")
        self.assertEqual(command[3:], ["rev-parse", "--verify", "HEAD"])

    def test_generated_inventory_validates(self):
        self.write_module("en.valid", self.static_source())
        result = validate_inventory_data(self.generate())
        self.assertEqual(result.errors, (), result.diagnostics)

    def test_registry_join_is_derived_without_imported_artifact_ids(self):
        self.write_module("en.join", self.static_source(source_id="700"))
        inventory = self.generate()
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [
                {
                    "artifactId": "joined",
                    "runtimeKey": "not_identity",
                    "catalog": {"name": "Joined", "version": "1.0.0"},
                    "upstream": {"project": PROJECT, "sourceId": "700"},
                    "implementation": {"producer": "manual"},
                }
            ],
        }
        result = validate_inventory_data(inventory, registry)
        self.assertEqual(result.errors, (), result.diagnostics)
        self.assertEqual(result.registry_joins[0].artifact_ids, ("joined",))
        self.assertNotIn("importedArtifactIds", inventory["candidates"][0])

    def test_runtime_key_never_enters_inventory(self):
        self.write_module("en.runtime", self.static_source(source_id="800"))
        serialized = json.loads(serialize_inventory(self.generate()))
        self.assertNotIn("runtimeKey", serialized["candidates"][0])

    def test_generator_does_not_modify_upstream_fixture_files(self):
        self.write_module("en.readonly", self.static_source())
        before = copy.deepcopy(self.snapshot_files())
        self.generate()
        self.assertEqual(self.snapshot_files(), before)


if __name__ == "__main__":
    unittest.main()
