import unittest
import json
import os
from tools.source_conversion.validator.validate_ir import validate_ir_data
from tools.source_conversion.generator.js_generator import generate_venera_js

class TestSourceVersionContract(unittest.TestCase):
    def setUp(self):
        self.base_ir = {
            "schemaVersion": "0.1",
            "id": "test_source",
            "name": "Test Source",
            "languages": ["en"],
            "contentOrigins": ["KR"],
            "contentWarning": "SAFE",
            "sourceType": "api",
            "baseUrl": "https://test.com",
            "explore": {},
            "search": {"url": "https://test.com/search", "method": "GET", "manualPatchRequired": False},
            "details": {"url": "https://test.com/detail", "method": "GET", "manualPatchRequired": False},
            "chapters": {"url": "https://test.com/chapters", "method": "GET", "manualPatchRequired": False},
            "pages": {"url": "https://test.com/pages", "method": "GET", "manualPatchRequired": False}
        }

    def test_ir_without_version_generates_1_0_0(self):
        js = generate_venera_js(self.base_ir)
        self.assertIn('version = "1.0.0"', js)

    def test_ir_with_version_generates_correct_version(self):
        ir = dict(self.base_ir)
        ir["version"] = "1.0.1"
        js = generate_venera_js(ir)
        self.assertIn('version = "1.0.1"', js)

    def test_validator_accepts_valid_version(self):
        ir = dict(self.base_ir)
        ir["version"] = "2.3.4"
        errors = validate_ir_data(ir)
        self.assertEqual(len(errors), 0, f"Validator returned errors: {errors}")

    def test_validator_rejects_malformed_version(self):
        invalid_versions = ["", "abc", "1", "1.0"]
        for v in invalid_versions:
            ir = dict(self.base_ir)
            ir["version"] = v
            errors = validate_ir_data(ir)
            self.assertGreater(len(errors), 0, f"Validator should reject version: '{v}'")

    def test_schema_accepts_valid_optional_version(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "schema", "ir_v0_1.schema.json")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        self.assertIn("version", schema.get("properties", {}))
        self.assertNotIn("version", schema.get("required", []))

        import re
        pattern = schema["properties"]["version"]["pattern"]
        self.assertIsNotNone(re.match(pattern, "1.0.1"))

    def test_existing_ir_without_version_remains_valid(self):
        ir = dict(self.base_ir)
        if "version" in ir:
            del ir["version"]

        errors = validate_ir_data(ir)
        self.assertEqual(len(errors), 0, "Existing IR without version should validate cleanly")

        js = generate_venera_js(ir)
        self.assertIn('version = "1.0.0"', js, "Existing IR without version should generate 1.0.0")

    def test_deterministic_generation(self):
        ir = dict(self.base_ir)
        ir["version"] = "1.2.3"
        js1 = generate_venera_js(ir)
        js2 = generate_venera_js(ir)
        self.assertEqual(js1, js2)

if __name__ == '__main__':
    unittest.main()
