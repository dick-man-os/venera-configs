import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.source_conversion.inventory.generate_static_inventory import (
    CANONICAL_COMMIT,
    CANONICAL_INVENTORY_PATH,
    CANONICAL_PROJECT,
    InventoryGenerationError,
    _generate_deterministic,
    _normalized_github_project,
    _validate_canonical_request,
    _validate_inventory_snapshot,
    classify_inventory_drift,
    run_canonical,
    serialize_inventory,
    validate_canonical_checkout,
)


def candidate(source_id="1", module="en.sample", name="Sample", **extra):
    value = {
        "project": CANONICAL_PROJECT,
        "sourceId": source_id,
        "module": module,
        "name": name,
        "upstreamLang": "en",
        "compatibility": {
            "metadataResolution": "static",
            "extraction": "unclassified",
        },
    }
    value.update(extra)
    return value


def unresolved(module, reason):
    return {
        "project": CANONICAL_PROJECT,
        "module": module,
        "reason": {"code": reason},
    }


def inventory(*candidates, commit=CANONICAL_COMMIT, unresolved_modules=None):
    return {
        "schemaVersion": "1.0",
        "upstreams": [{"project": CANONICAL_PROJECT, "commit": commit}],
        "candidates": list(candidates),
        "unresolvedModules": list(unresolved_modules or []),
    }


def registry_artifact(artifact_id="sample", source_id="1"):
    return {
        "artifactId": artifact_id,
        "runtimeKey": "not-an-inventory-identity",
        "implementation": {"producer": "manual"},
        "upstream": {"project": CANONICAL_PROJECT, "sourceId": source_id},
    }


def registry(*artifacts):
    return {"schemaVersion": "1.0", "artifacts": list(artifacts)}


class TestCanonicalProvenance(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name).resolve()

    def tearDown(self):
        self.temp_dir.cleanup()

    def git_probe(self, remote_name="upstream", remote_url=None, head=CANONICAL_COMMIT):
        url = remote_url or "https://github.com/keiyoushi/extensions-source.git"

        def probe(_root, *arguments):
            if arguments == ("rev-parse", "--show-toplevel"):
                return str(self.root)
            if arguments == ("rev-parse", "--verify", "HEAD"):
                return head
            if arguments == ("remote",):
                return remote_name
            if arguments == ("remote", "get-url", "--all", remote_name):
                return url
            raise AssertionError(arguments)

        return probe

    def test_wrong_project(self):
        with self.assertRaisesRegex(InventoryGenerationError, "canonical project"):
            _validate_canonical_request("other/extensions-source", CANONICAL_COMMIT)

    def test_malformed_requested_pin(self):
        for value in ("0" * 39, "g" * 40, CANONICAL_COMMIT.upper()):
            with self.subTest(value=value):
                with self.assertRaisesRegex(InventoryGenerationError, "requested pin"):
                    _validate_canonical_request(CANONICAL_PROJECT, value)

    def test_wrong_head(self):
        with patch(
            "tools.source_conversion.inventory.generate_static_inventory._run_git",
            side_effect=self.git_probe(head="0" * 40),
        ):
            with self.assertRaisesRegex(InventoryGenerationError, "HEAD mismatch"):
                validate_canonical_checkout(self.root, CANONICAL_COMMIT)

    def test_wrong_git_root(self):
        def probe(_root, *arguments):
            if arguments == ("rev-parse", "--show-toplevel"):
                return str(self.root.parent)
            raise AssertionError(arguments)

        with patch(
            "tools.source_conversion.inventory.generate_static_inventory._run_git",
            side_effect=probe,
        ):
            with self.assertRaisesRegex(InventoryGenerationError, "not the Git worktree root"):
                validate_canonical_checkout(self.root, CANONICAL_COMMIT)

    def test_remote_name_independence(self):
        with patch(
            "tools.source_conversion.inventory.generate_static_inventory._run_git",
            side_effect=self.git_probe(remote_name="mirror"),
        ):
            resolved, commit = validate_canonical_checkout(self.root, CANONICAL_COMMIT)
        self.assertEqual((resolved, commit), (self.root, CANONICAL_COMMIT))

    def test_unacceptable_repository_remote_identity(self):
        with patch(
            "tools.source_conversion.inventory.generate_static_inventory._run_git",
            side_effect=self.git_probe(
                remote_url="https://github.com/example/extensions-source.git"
            ),
        ):
            with self.assertRaisesRegex(InventoryGenerationError, "no configured fetch remote"):
                validate_canonical_checkout(self.root, CANONICAL_COMMIT)

    def test_normalized_https_and_ssh_upstream_urls(self):
        for value in (
            "https://github.com/keiyoushi/extensions-source.git",
            "git@github.com:keiyoushi/extensions-source.git",
            "ssh://git@github.com/keiyoushi/extensions-source.git",
        ):
            with self.subTest(value=value):
                self.assertEqual(_normalized_github_project(value), CANONICAL_PROJECT)


class TestDeterminismAndDrift(unittest.TestCase):
    def test_deterministic_double_generation_success(self):
        value = inventory(candidate())
        with patch(
            "tools.source_conversion.inventory.generate_static_inventory.generate_inventory",
            side_effect=[value, copy.deepcopy(value)],
        ):
            generated, payload = _generate_deterministic(
                Path("."), CANONICAL_PROJECT, CANONICAL_COMMIT
            )
        self.assertEqual((generated, payload), (value, serialize_inventory(value)))

    def test_byte_nondeterminism_failure(self):
        first = inventory(candidate())
        second = {
            "upstreams": copy.deepcopy(first["upstreams"]),
            "schemaVersion": first["schemaVersion"],
            "candidates": copy.deepcopy(first["candidates"]),
            "unresolvedModules": [],
        }
        self.assertEqual(first, second)
        with patch(
            "tools.source_conversion.inventory.generate_static_inventory.generate_inventory",
            side_effect=[first, second],
        ):
            with self.assertRaisesRegex(InventoryGenerationError, "serialization/order"):
                _generate_deterministic(Path("."), CANONICAL_PROJECT, CANONICAL_COMMIT)

    def test_semantic_nondeterminism_failure(self):
        with patch(
            "tools.source_conversion.inventory.generate_static_inventory.generate_inventory",
            side_effect=[
                inventory(candidate(name="Before")),
                inventory(candidate(name="After")),
            ],
        ):
            with self.assertRaisesRegex(InventoryGenerationError, "semantic nondeterminism"):
                _generate_deterministic(Path("."), CANONICAL_PROJECT, CANONICAL_COMMIT)

    def test_semantic_candidate_drift(self):
        drift = classify_inventory_drift(
            inventory(candidate(name="Before")),
            inventory(candidate(name="After")),
        )
        self.assertEqual(
            drift["changedCandidates"], (f"{CANONICAL_PROJECT}:1 [name]",)
        )

    def test_module_and_candidate_additions_and_removals(self):
        drift = classify_inventory_drift(
            inventory(candidate("1", "en.before")),
            inventory(candidate("2", "fr.after")),
        )
        self.assertEqual(drift["removedModules"], (f"{CANONICAL_PROJECT}:en.before",))
        self.assertEqual(drift["addedModules"], (f"{CANONICAL_PROJECT}:fr.after",))
        self.assertEqual(drift["removedCandidates"], (f"{CANONICAL_PROJECT}:1",))
        self.assertEqual(drift["addedCandidates"], (f"{CANONICAL_PROJECT}:2",))

    def test_unresolved_additions_removals_and_reason_changes(self):
        before = inventory(
            candidate(),
            unresolved_modules=[
                unresolved("en.removed", "no-source-blocks"),
                unresolved("en.changed", "static-parse-error"),
            ],
        )
        after = inventory(
            candidate(),
            unresolved_modules=[
                unresolved("en.added", "no-source-blocks"),
                unresolved("en.changed", "unresolved-required-metadata"),
            ],
        )
        drift = classify_inventory_drift(before, after)
        self.assertEqual(drift["addedUnresolved"], (f"{CANONICAL_PROJECT}:en.added",))
        self.assertEqual(
            drift["removedUnresolved"], (f"{CANONICAL_PROJECT}:en.removed",)
        )
        self.assertIn(
            "static-parse-error -> unresolved-required-metadata",
            drift["changedUnresolvedReasons"][0],
        )


class TestCanonicalValidation(unittest.TestCase):
    def validate(self, value, registry_value, require_complete=True):
        return _validate_inventory_snapshot(
            value,
            registry_value,
            expected_project=CANONICAL_PROJECT,
            expected_commit=CANONICAL_COMMIT,
            require_complete_registry=require_complete,
        )

    def test_duplicate_identity_rejection(self):
        value = inventory(candidate(), candidate(module="fr.duplicate"))
        with self.assertRaisesRegex(InventoryGenerationError, "CANDIDATE_IDENTITY_DUPLICATE"):
            self.validate(value, registry())

    def test_registry_missing_resolution(self):
        with self.assertRaisesRegex(InventoryGenerationError, "missing artifacts"):
            self.validate(
                inventory(candidate()), registry(registry_artifact(source_id="999"))
            )

    def test_registry_ambiguous_resolution(self):
        with self.assertRaisesRegex(InventoryGenerationError, "ambiguous joins=1"):
            self.validate(
                inventory(candidate()),
                registry(registry_artifact("first"), registry_artifact("second")),
            )


class TestCanonicalLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.path = self.root / "upstream_inventory.json"
        self.generated = inventory(candidate())
        self.registry = registry(registry_artifact())

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_mode(self, mode, generated=None, expected_commit=CANONICAL_COMMIT):
        value = self.generated if generated is None else generated
        with (
            patch(
                "tools.source_conversion.inventory.generate_static_inventory.validate_canonical_checkout",
                return_value=(self.root, expected_commit),
            ),
            patch(
                "tools.source_conversion.inventory.generate_static_inventory._load_registry",
                return_value=self.registry,
            ),
            patch(
                "tools.source_conversion.inventory.generate_static_inventory._generate_deterministic",
                return_value=(value, serialize_inventory(value)),
            ),
            redirect_stdout(io.StringIO()) as output,
        ):
            result = run_canonical(
                mode,
                self.root,
                CANONICAL_PROJECT,
                expected_commit,
                canonical_path=self.path,
            )
        return result, output.getvalue()

    def test_bootstrap_write(self):
        result, output = self.run_mode("write")
        self.assertEqual(result, 0)
        self.assertEqual(self.path.read_bytes(), serialize_inventory(self.generated))
        self.assertIn("previous snapshot=absent", output)

    def test_absent_snapshot_check_failure(self):
        with self.assertRaisesRegex(InventoryGenerationError, "canonical inventory snapshot missing"):
            self.run_mode("check")
        self.assertFalse(self.path.exists())

    def test_write_idempotence(self):
        self.run_mode("write")
        first = self.path.read_bytes()
        self.run_mode("write")
        self.assertEqual(self.path.read_bytes(), first)

    def test_write_allows_old_pin_to_new_pin_transition(self):
        old_pin = "1" * 40
        new_pin = "2" * 40
        previous = inventory(candidate(), commit=old_pin)
        generated = inventory(candidate(), commit=new_pin)
        self.path.write_bytes(serialize_inventory(previous))

        result, output = self.run_mode(
            "write", generated=generated, expected_commit=new_pin
        )

        self.assertEqual(result, 0)
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(
            written["upstreams"],
            [{"project": CANONICAL_PROJECT, "commit": new_pin}],
        )
        self.assertIn(f"old pin={old_pin}", output)
        self.assertIn(f"new pin={new_pin}", output)

    def test_check_rejects_old_snapshot_against_new_requested_pin(self):
        old_pin = "1" * 40
        new_pin = "2" * 40
        previous = inventory(candidate(), commit=old_pin)
        generated = inventory(candidate(), commit=new_pin)
        self.path.write_bytes(serialize_inventory(previous))
        before = self.path.read_bytes()

        with self.assertRaisesRegex(InventoryGenerationError, "snapshot pin mismatch"):
            self.run_mode("check", generated=generated, expected_commit=new_pin)

        self.assertEqual(self.path.read_bytes(), before)

    def test_check_is_non_mutating(self):
        self.path.write_bytes(serialize_inventory(self.generated))
        before = self.path.read_bytes()
        result, _output = self.run_mode("check")
        self.assertEqual(result, 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_exact_canonical_path(self):
        self.assertEqual(
            CANONICAL_INVENTORY_PATH.relative_to(Path(__file__).resolve().parents[3]).as_posix(),
            "tools/source_conversion/inventory/upstream_inventory.json",
        )

    def test_byte_only_serialization_drift(self):
        self.path.write_text(
            json.dumps(self.generated, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(InventoryGenerationError, "CHECKED_IN_SERIALIZATION_DRIFT"):
            self.run_mode("check")
        self.assertEqual(self.path.read_bytes(), before)

    def test_semantic_inventory_drift(self):
        self.path.write_bytes(serialize_inventory(inventory(candidate(name="Before"))))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(InventoryGenerationError, "CANONICAL_INVENTORY_DRIFT"):
            self.run_mode("check")
        self.assertEqual(self.path.read_bytes(), before)

    def test_atomic_refusal_does_not_replace_invalid_input(self):
        self.path.write_bytes(serialize_inventory(self.generated))
        before = self.path.read_bytes()
        invalid = inventory(candidate(), candidate(module="fr.duplicate"))
        with self.assertRaisesRegex(InventoryGenerationError, "CANDIDATE_IDENTITY_DUPLICATE"):
            self.run_mode("write", invalid)
        self.assertEqual(self.path.read_bytes(), before)

    def test_exact_lf_canonical_output(self):
        self.run_mode("write")
        payload = self.path.read_bytes()
        self.assertTrue(payload.endswith(b"\n"))
        self.assertFalse(payload.endswith(b"\n\n"))
        self.assertNotIn(b"\r\n", payload)

    def test_runtime_key_absent_from_canonical_candidates(self):
        self.run_mode("write")
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("runtimeKey", written["candidates"][0])


if __name__ == "__main__":
    unittest.main()
