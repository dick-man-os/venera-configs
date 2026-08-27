import os
import sys
import unittest
import json
import tempfile
import subprocess
from copy import deepcopy

current_dir = os.path.dirname(os.path.abspath(__file__))
validator_dir = os.path.join(os.path.dirname(current_dir), "validator")
generator_dir = os.path.join(os.path.dirname(current_dir), "generator")
sys.path.insert(0, validator_dir)
sys.path.insert(0, generator_dir)

from validate_ir import validate_ir_data
from js_generator import generate_venera_js

class TestValidateIR(unittest.TestCase):
    def setUp(self):
        self.base_v01 = {
            "schemaVersion": "0.1",
            "id": "test_source",
            "name": "Test Source",
            "languages": ["en"],
            "contentOrigins": ["KR"],
            "contentWarning": "SAFE",
            "sourceType": "html",
            "baseUrl": "https://example.com",
            "explore": {
                "popular": {
                    "url": "https://example.com/popular",
                    "method": "GET"
                }
            },
            "search": {
                "url": "https://example.com/search",
                "method": "GET"
            },
            "details": {
                "url": "https://example.com/details",
                "method": "GET"
            },
            "chapters": {
                "url": "https://example.com/chapters",
                "method": "GET"
            },
            "pages": {
                "url": "https://example.com/pages",
                "method": "GET"
            }
        }

    def test_valid_v01_http_ir(self):
        errors = validate_ir_data(self.base_v01)
        self.assertEqual(errors, [])

    def test_malformed_v01_invalid(self):
        bad_ir = deepcopy(self.base_v01)
        del bad_ir["baseUrl"]
        errors = validate_ir_data(bad_ir)
        self.assertTrue(any("Missing required top-level field: 'baseUrl'" in e for e in errors))

        bad_ir2 = deepcopy(self.base_v01)
        bad_ir2["explore"]["popular"]["method"] = "PUT"
        errors2 = validate_ir_data(bad_ir2)
        self.assertTrue(any("has invalid method" in e for e in errors2))

    def test_valid_v02_static_ir(self):
        v02_ir = deepcopy(self.base_v01)
        v02_ir["schemaVersion"] = "0.2"
        v02_ir["staticCatalog"] = [{"title": "test", "url": "/1"}]
        v02_ir["explore"]["popular"]["useStaticCatalog"] = True
        del v02_ir["explore"]["popular"]["url"]
        del v02_ir["explore"]["popular"]["method"]
        v02_ir["search"]["useStaticCatalog"] = True
        del v02_ir["search"]["url"]
        del v02_ir["search"]["method"]
        errors = validate_ir_data(v02_ir)
        self.assertEqual(errors, [])

    def test_v02_use_static_without_catalog_fails(self):
        v02_ir = deepcopy(self.base_v01)
        v02_ir["schemaVersion"] = "0.2"
        v02_ir["explore"]["popular"]["useStaticCatalog"] = True
        del v02_ir["explore"]["popular"]["url"]
        del v02_ir["explore"]["popular"]["method"]
        errors = validate_ir_data(v02_ir)
        self.assertTrue(any("uses staticCatalog but root 'staticCatalog' is missing" in e for e in errors))

    def test_contradictory_v02_static_http_fails(self):
        v02_ir = deepcopy(self.base_v01)
        v02_ir["schemaVersion"] = "0.2"
        v02_ir["staticCatalog"] = []
        v02_ir["explore"]["popular"]["useStaticCatalog"] = True
        # leaves url and method in place
        errors = validate_ir_data(v02_ir)
        self.assertTrue(any("has 'url' but 'useStaticCatalog' is true" in e for e in errors))
        self.assertTrue(any("has 'method' but 'useStaticCatalog' is true" in e for e in errors))

    def test_ordinary_v02_http_ir(self):
        v02_ir = deepcopy(self.base_v01)
        v02_ir["schemaVersion"] = "0.2"
        errors = validate_ir_data(v02_ir)
        self.assertEqual(errors, [])

    def test_schema_versions_strict(self):
        bad_versions = ["0.1.1", "0.1.0.0", "0.2.0", "0.2.1", "0.10", "0.20", "0.2foo", "0.1-beta", "0.3"]
        for bad_v in bad_versions:
            ir = deepcopy(self.base_v01)
            ir["schemaVersion"] = bad_v
            errors = validate_ir_data(ir)
            self.assertTrue(any("exactly '0.1', '0.1.0', or '0.2'" in e for e in errors), f"Failed to reject {bad_v}: {errors}")

    def test_static_catalog_malformed(self):
        # non-array
        ir = deepcopy(self.base_v01)
        ir["schemaVersion"] = "0.2"
        ir["staticCatalog"] = {}
        errors = validate_ir_data(ir)
        self.assertTrue(any("must be an array" in e for e in errors))

        # empty array
        ir["staticCatalog"] = []
        errors = validate_ir_data(ir)
        self.assertTrue(any("must contain at least 1 item" in e for e in errors))

        # non-object entry
        ir["staticCatalog"] = ["string"]
        errors = validate_ir_data(ir)
        self.assertTrue(any("staticCatalog[0] must be an object" in e for e in errors))

        # missing title
        ir["staticCatalog"] = [{"url": "a"}]
        errors = validate_ir_data(ir)
        self.assertTrue(any("missing required property 'title'" in e for e in errors))

        # missing url
        ir["staticCatalog"] = [{"title": "a"}]
        errors = validate_ir_data(ir)
        self.assertTrue(any("missing required property 'url'" in e for e in errors))

        # non-string title
        ir["staticCatalog"] = [{"title": 1, "url": "a"}]
        errors = validate_ir_data(ir)
        self.assertTrue(any("property 'title' must be a string" in e for e in errors))

        # non-string url
        ir["staticCatalog"] = [{"title": "a", "url": 1}]
        errors = validate_ir_data(ir)
        self.assertTrue(any("property 'url' must be a string" in e for e in errors))

        # unexpected property
        ir["staticCatalog"] = [{"title": "a", "url": "a", "extra": 1}]
        errors = validate_ir_data(ir)
        self.assertTrue(any("contains forbidden property 'extra'" in e for e in errors))

    def test_static_flag_malformed(self):
        ir = deepcopy(self.base_v01)
        ir["schemaVersion"] = "0.2"
        for bad_val in ["true", 1, None]:
            ir["explore"]["popular"]["useStaticCatalog"] = bad_val
            errors = validate_ir_data(ir)
            self.assertTrue(any("must be a boolean" in e for e in errors), f"Failed to reject {bad_val}")

    def test_static_contradictions(self):
        ir = deepcopy(self.base_v01)
        ir["schemaVersion"] = "0.2"
        ir["staticCatalog"] = [{"title": "a", "url": "a"}]

        for field in ["url", "method", "selector", "fields", "pagination"]:
            test_ir = deepcopy(ir)
            test_ir["search"]["useStaticCatalog"] = True
            # make sure the field exists
            test_ir["search"][field] = "value" if field != "fields" and field != "pagination" else {}
            errors = validate_ir_data(test_ir)
            self.assertTrue(any(f"has '{field}' but 'useStaticCatalog' is true" in e for e in errors), f"Failed for {field}")

    def test_root_dependency(self):
        # mixed explore without root staticCatalog
        ir = deepcopy(self.base_v01)
        ir["schemaVersion"] = "0.2"
        ir["explore"]["popular"]["useStaticCatalog"] = True
        del ir["explore"]["popular"]["url"]
        del ir["explore"]["popular"]["method"]
        ir["explore"]["latest"] = {"url": "a", "method": "GET"}
        errors = validate_ir_data(ir)
        self.assertTrue(any("uses staticCatalog but root 'staticCatalog' is missing" in e for e in errors))


    def test_existing_validation_warnings_not_broadened(self):
        ir = deepcopy(self.base_v01)
        ir["schemaVersion"] = "0.2"
        ir["unknownField"] = True
        errors = validate_ir_data(ir)
        self.assertTrue(any("Unknown top-level property: 'unknownField'" in e for e in errors))

    def test_cli_integration_v02_generation(self):
        v02_ir = deepcopy(self.base_v01)
        v02_ir["schemaVersion"] = "0.2"
        v02_ir["staticCatalog"] = [{"title": "test", "url": "/1"}]
        v02_ir["explore"]["popular"]["useStaticCatalog"] = True
        del v02_ir["explore"]["popular"]["url"]
        del v02_ir["explore"]["popular"]["method"]
        v02_ir["search"]["useStaticCatalog"] = True
        del v02_ir["search"]["url"]
        del v02_ir["search"]["method"]

        # Ensure it passes generation directly
        expected_js = generate_venera_js(v02_ir)

        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, "input.json")
            output_path = os.path.join(temp_dir, "output.js")

            with open(input_path, "w", encoding="utf-8") as f:
                json.dump(v02_ir, f)

            generator_script = os.path.join(generator_dir, "js_generator.py")
            cmd = [sys.executable, generator_script, "--input", input_path, "--output", output_path]

            # This should NOT fail (no --skip-validation flag used)
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"CLI generator failed: {result.stderr}")

            with open(output_path, "r", encoding="utf-8") as f:
                cli_output_js = f.read()

            self.assertEqual(cli_output_js, expected_js)


    def test_schema_versions_non_string_fail_cleanly(self):
        bad_versions = [[], {}, 1, None]
        for bad_v in bad_versions:
            ir = deepcopy(self.base_v01)
            ir["schemaVersion"] = bad_v
            errors = validate_ir_data(ir)
            self.assertTrue(any("must be a string exactly '0.1', '0.1.0', or '0.2'" in e for e in errors), f"Failed to cleanly reject {bad_v}")

    def test_manual_patch_required_does_not_bypass_static_validation(self):
        # Even if manualPatchRequired is True, static properties must be valid
        # 1. useStaticCatalog is not a boolean
        ir = deepcopy(self.base_v01)
        ir["schemaVersion"] = "0.2"
        ir["explore"]["popular"]["manualPatchRequired"] = True
        ir["explore"]["popular"]["useStaticCatalog"] = "true"
        errors = validate_ir_data(ir)
        self.assertTrue(any("must be a boolean" in e for e in errors))

        # 2. useStaticCatalog is 1
        ir["explore"]["popular"]["useStaticCatalog"] = 1
        errors = validate_ir_data(ir)
        self.assertTrue(any("must be a boolean" in e for e in errors))

        # 3. static mode without staticCatalog
        ir["explore"]["popular"]["useStaticCatalog"] = True
        errors = validate_ir_data(ir)
        self.assertTrue(any("uses staticCatalog but root 'staticCatalog' is missing" in e for e in errors))

        # 4. static + url, method, selector, fields, pagination
        ir["staticCatalog"] = [{"title": "a", "url": "a"}]
        for field in ["url", "method", "selector", "fields", "pagination"]:
            test_ir = deepcopy(ir)
            test_ir["explore"]["popular"][field] = "value" if field not in ["fields", "pagination"] else {}
            errors = validate_ir_data(test_ir)
            self.assertTrue(any(f"has '{field}' but 'useStaticCatalog' is true" in e for e in errors), f"Failed to reject static + {field}")

        # 5. Legitimate manualPatchRequired with no static fields works fine
        legit_ir = deepcopy(self.base_v01)
        legit_ir["schemaVersion"] = "0.2"
        legit_ir["explore"]["popular"]["manualPatchRequired"] = True
        del legit_ir["explore"]["popular"]["url"]
        del legit_ir["explore"]["popular"]["method"]
        errors = validate_ir_data(legit_ir)
        self.assertEqual(errors, [])


    def test_schema_version_010_supported(self):
        import json
        import os
        for ir_name in ["webtoons.json", "webtoons_zh_hant.json"]:
            path = os.path.join("sources_ir", ir_name)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    ir = json.load(f)
                errors = validate_ir_data(ir)
                self.assertEqual(errors, [], f"Expected existing IR {ir_name} to pass validation")

        ir = deepcopy(self.base_v01)
        ir["schemaVersion"] = "0.1.0"
        errors = validate_ir_data(ir)
        self.assertEqual(errors, [], "Expected mocked 0.1.0 IR to pass validation")

if __name__ == "__main__":
    unittest.main()
