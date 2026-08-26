import copy
import json
import sys
import unittest
from pathlib import Path


repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.validator.validate_inventory import (
    validate_inventory_data,
)


PROJECT = "keiyoushi/extensions-source"
COMMIT = "5e06c412c0264b18120fd963fdd6efb529f3fa29"


def snapshot(project=PROJECT, commit=COMMIT):
    return {"project": project, "commit": commit}


def candidate(**changes):
    value = {
        "project": PROJECT,
        "sourceId": "123456789",
        "module": "all.sample",
        "name": "Sample",
        "upstreamLang": "all",
        "compatibility": {
            "metadataResolution": "static",
            "extraction": "generic",
            "patchRequired": False,
        },
    }
    value.update(changes)
    return value


def unresolved_module(**changes):
    value = {
        "project": PROJECT,
        "module": "all.dynamic",
        "reason": {"code": "dynamic-source-instances"},
    }
    value.update(changes)
    return value


def inventory(*candidate_values, upstreams=None, unresolved_modules=None):
    return {
        "schemaVersion": "1.0",
        "upstreams": [snapshot()] if upstreams is None else upstreams,
        "candidates": list(candidate_values),
        "unresolvedModules": (
            [] if unresolved_modules is None else unresolved_modules
        ),
    }


def registry_artifact(artifact_id, project=None, source_id=None, **extra):
    value = {
        "artifactId": artifact_id,
        "runtimeKey": extra.pop("runtimeKey", artifact_id),
        "providerId": extra.pop("providerId", artifact_id),
        "implementation": {"producer": "manual"},
    }
    if project is not None and source_id is not None:
        value["upstream"] = {
            "project": project,
            "module": "all.sample",
            "sourceId": source_id,
            "version": "1.0.0",
            "extensionLib": "1.0",
            "commit": COMMIT,
        }
    value.update(extra)
    return value


class TestUpstreamInventory(unittest.TestCase):
    def assert_valid(self, data, registry=None):
        result = validate_inventory_data(data, registry)
        self.assertEqual(result.errors, (), result.diagnostics)
        return result

    def assert_has_code(self, data, code, registry=None):
        result = validate_inventory_data(data, registry)
        self.assertTrue(result.with_code(code), result.diagnostics)
        return result

    def test_valid_minimal_candidate(self):
        self.assert_valid(inventory(candidate()))

    def test_root_upstream_snapshot_is_required(self):
        data = inventory(candidate())
        data.pop("upstreams")
        self.assert_has_code(data, "SCHEMA_REQUIRED_FIELD")

    def test_root_upstream_commit_is_required_hash_string(self):
        self.assert_has_code(
            inventory(candidate(), upstreams=[{"project": PROJECT}]),
            "SCHEMA_REQUIRED_FIELD",
        )
        self.assert_has_code(
            inventory(candidate(), upstreams=[snapshot(commit="")]),
            "SCHEMA_FIELD_VALUE",
        )

    def test_duplicate_root_project_snapshot_is_rejected(self):
        data = inventory(
            candidate(),
            upstreams=[snapshot(), snapshot(commit="0123456789abcdef")],
        )
        self.assert_has_code(data, "UPSTREAM_PROJECT_DUPLICATE")

    def test_candidate_project_must_reference_declared_snapshot(self):
        self.assert_has_code(
            inventory(candidate(project="other/extensions-source")),
            "UPSTREAM_PROJECT_UNDECLARED",
        )

    def test_unresolved_module_project_must_reference_declared_snapshot(self):
        data = inventory(
            unresolved_modules=[
                unresolved_module(project="other/extensions-source")
            ]
        )
        self.assert_has_code(data, "UPSTREAM_PROJECT_UNDECLARED")

    def test_unresolved_module_can_exist_without_source_id(self):
        issue = unresolved_module()
        self.assertNotIn("sourceId", issue)
        self.assert_valid(inventory(unresolved_modules=[issue]))

    def test_unresolved_modules_do_not_participate_in_candidate_identity(self):
        issue = unresolved_module()
        data = inventory(unresolved_modules=[issue, copy.deepcopy(issue)])
        result = self.assert_valid(data)
        self.assertFalse(result.with_code("CANDIDATE_IDENTITY_DUPLICATE"))

    def test_empty_candidates_and_unresolved_modules_is_rejected(self):
        self.assert_has_code(inventory(), "INVENTORY_RECORDS_EMPTY")

    def test_duplicate_project_source_id_fails_closed(self):
        data = inventory(
            candidate(module="all.first"),
            candidate(module="all.renamed"),
        )
        self.assert_has_code(data, "CANDIDATE_IDENTITY_DUPLICATE")

    def test_same_source_id_in_different_projects_is_distinct(self):
        other_project = "other/extensions-source"
        data = inventory(
            candidate(),
            candidate(project=other_project),
            upstreams=[snapshot(), snapshot(project=other_project)],
        )
        self.assert_valid(data)

    def test_module_is_required_but_not_part_of_candidate_identity(self):
        missing_module = candidate()
        missing_module.pop("module")
        self.assert_has_code(
            inventory(missing_module), "SCHEMA_REQUIRED_FIELD"
        )
        self.assert_has_code(
            inventory(
                candidate(module="all.before"),
                candidate(module="all.after"),
            ),
            "CANDIDATE_IDENTITY_DUPLICATE",
        )

    def test_source_id_must_be_a_json_string(self):
        self.assert_has_code(
            inventory(candidate(sourceId=123456789)), "SCHEMA_FIELD_TYPE"
        )

    def test_raw_all_language_and_omitted_locale_are_valid(self):
        value = candidate(upstreamLang="all")
        self.assertNotIn("canonicalLocale", value)
        self.assert_valid(inventory(value))

    def test_validation_does_not_implicitly_normalize_locale(self):
        data = inventory(candidate(upstreamLang="all"))
        before = copy.deepcopy(data)
        self.assert_valid(data)
        self.assertEqual(data, before)
        self.assertNotIn("canonicalLocale", data["candidates"][0])

    def test_metadata_resolution_enum_is_for_identified_evidence(self):
        compatibility = candidate()["compatibility"]
        compatibility["metadataResolution"] = "unresolved"
        self.assert_has_code(
            inventory(candidate(compatibility=compatibility)),
            "SCHEMA_FIELD_VALUE",
        )

    def test_extraction_enum_is_validated(self):
        compatibility = candidate()["compatibility"]
        compatibility["extraction"] = "automatic"
        self.assert_has_code(
            inventory(candidate(compatibility=compatibility)),
            "SCHEMA_FIELD_VALUE",
        )

    def test_unclassified_extraction_may_omit_patch_required(self):
        compatibility = {
            "metadataResolution": "static",
            "extraction": "unclassified",
        }
        self.assert_valid(inventory(candidate(compatibility=compatibility)))

    def test_all_classified_extraction_modes_remain_valid(self):
        for extraction in ("generic", "adapter", "manual", "unsupported"):
            with self.subTest(extraction=extraction):
                compatibility = {
                    "metadataResolution": "evaluated",
                    "extraction": extraction,
                    "patchRequired": False,
                }
                self.assert_valid(
                    inventory(candidate(compatibility=compatibility))
                )

    def test_classified_candidate_may_explicitly_set_patch_required_false(self):
        compatibility = {
            "metadataResolution": "evaluated",
            "extraction": "generic",
            "patchRequired": False,
        }
        self.assert_valid(inventory(candidate(compatibility=compatibility)))

    def test_omitted_patch_required_is_not_defaulted_or_injected(self):
        compatibility = {
            "metadataResolution": "static",
            "extraction": "unclassified",
        }
        data = inventory(candidate(compatibility=compatibility))
        before = copy.deepcopy(data)
        self.assert_valid(data)
        self.assertEqual(data, before)
        self.assertNotIn(
            "patchRequired", data["candidates"][0]["compatibility"]
        )

    def test_patch_required_can_coexist_with_adapter_extraction(self):
        compatibility = {
            "metadataResolution": "evaluated",
            "extraction": "adapter",
            "patchRequired": True,
        }
        self.assert_valid(inventory(candidate(compatibility=compatibility)))

    def test_imported_artifact_ids_is_not_persisted_candidate_truth(self):
        self.assert_valid(inventory(candidate()))
        self.assert_has_code(
            inventory(candidate(importedArtifactIds=["sample"])),
            "SCHEMA_UNKNOWN_FIELD",
        )

    def test_registry_cross_validation_derives_zero_one_or_many_matches(self):
        data = inventory(
            candidate(sourceId="100", module="all.zero"),
            candidate(sourceId="200", module="all.one"),
            candidate(sourceId="300", module="all.many"),
        )
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [
                registry_artifact("one", PROJECT, "200"),
                registry_artifact("many_a", PROJECT, "300"),
                registry_artifact("many_b", PROJECT, "300"),
            ],
        }
        result = self.assert_valid(data, registry)
        matches = {
            join.source_id: join.artifact_ids for join in result.registry_joins
        }
        self.assertEqual(matches["100"], ())
        self.assertEqual(matches["200"], ("one",))
        self.assertEqual(matches["300"], ("many_a", "many_b"))

    def test_registry_join_uses_only_project_source_id(self):
        other_project = "other/extensions-source"
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [
                registry_artifact(
                    "sample",
                    PROJECT,
                    "123456789",
                    runtimeKey="shared_key",
                    catalogName="Same Name",
                    siteUrl="https://same.example",
                ),
                registry_artifact(
                    "sample_variant",
                    PROJECT,
                    "123456789",
                    runtimeKey="different_key",
                ),
                registry_artifact(
                    "identity_decoy",
                    other_project,
                    "123456789",
                    runtimeKey="shared_key",
                    catalogName="Same Name",
                    siteUrl="https://same.example",
                ),
            ],
        }
        result = self.assert_valid(inventory(candidate()), registry)
        self.assertEqual(
            result.registry_joins[0].artifact_ids,
            ("sample", "sample_variant"),
        )

    def test_runtime_key_never_affects_registry_join(self):
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [
                registry_artifact(
                    "matching_identity", PROJECT, "123456789", runtimeKey="x"
                ),
                registry_artifact(
                    "same_runtime_decoy",
                    "other/extensions-source",
                    "123456789",
                    runtimeKey="x",
                ),
            ],
        }
        result = self.assert_valid(inventory(candidate()), registry)
        self.assertEqual(
            result.registry_joins[0].artifact_ids, ("matching_identity",)
        )

    def test_invalid_or_ambiguous_registry_mapping_fails_closed(self):
        invalid = registry_artifact("sample")
        invalid["upstream"] = {"project": PROJECT, "sourceId": 123456789}
        self.assert_has_code(
            inventory(candidate()),
            "REGISTRY_UPSTREAM_INVALID",
            {"schemaVersion": "1.0", "artifacts": [invalid]},
        )

        duplicate_registry = {
            "schemaVersion": "1.0",
            "artifacts": [
                registry_artifact("sample", PROJECT, "123456789"),
                registry_artifact("sample", PROJECT, "123456789"),
            ],
        }
        self.assert_has_code(
            inventory(candidate()),
            "REGISTRY_ARTIFACT_ID_DUPLICATE",
            duplicate_registry,
        )

    def test_runtime_key_is_not_an_inventory_identity_field(self):
        self.assert_valid(inventory(candidate()))
        self.assert_has_code(
            inventory(candidate(runtimeKey="not_identity")),
            "SCHEMA_UNKNOWN_FIELD",
        )

    def test_validation_is_pure_and_has_no_index_semantics(self):
        data = inventory(candidate())
        registry = {
            "schemaVersion": "1.0",
            "artifacts": [
                registry_artifact("sample", PROJECT, "123456789")
            ],
        }
        before_data = json.dumps(data, sort_keys=True)
        before_registry = json.dumps(registry, sort_keys=True)
        self.assert_valid(data, registry)
        self.assertEqual(json.dumps(data, sort_keys=True), before_data)
        self.assertEqual(json.dumps(registry, sort_keys=True), before_registry)

    def test_schema_declares_corrected_root_and_candidate_ownership(self):
        schema_path = (
            repo_root
            / "tools"
            / "source_conversion"
            / "schema"
            / "upstream_inventory.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        candidate_schema = schema["$defs"]["candidate"]
        compatibility_schema = schema["$defs"]["compatibility"]

        self.assertEqual(
            set(schema["required"]),
            {"schemaVersion", "upstreams", "candidates", "unresolvedModules"},
        )
        self.assertEqual(
            candidate_schema["properties"]["sourceId"]["type"], "string"
        )
        for excluded in ("runtimeKey", "commit", "importedArtifactIds"):
            self.assertNotIn(excluded, candidate_schema["properties"])
        self.assertEqual(
            compatibility_schema["properties"]["metadataResolution"]["enum"],
            ["static", "evaluated"],
        )
        self.assertEqual(
            set(compatibility_schema["required"]),
            {"metadataResolution", "extraction"},
        )
        self.assertEqual(
            compatibility_schema["properties"]["extraction"]["enum"],
            ["unclassified", "generic", "adapter", "manual", "unsupported"],
        )


if __name__ == "__main__":
    unittest.main()
