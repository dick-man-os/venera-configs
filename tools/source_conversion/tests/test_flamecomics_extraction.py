import os
import sys
import unittest
import json

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.dirname(current_dir)
extractor_dir = os.path.join(tools_dir, "extractor")
validator_dir = os.path.join(tools_dir, "validator")
generator_dir = os.path.join(tools_dir, "generator")

sys.path.insert(0, extractor_dir)
sys.path.insert(0, validator_dir)
sys.path.insert(0, generator_dir)

from source_adapters import flamecomics
from validate_ir import validate_ir_data
from js_generator import generate_venera_js


class TestFlameComicsExtraction(unittest.TestCase):

    def setUp(self):
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[3]
        self.extensions_root = str(repo_root.parent / "extensions-source")

    def test_flamecomics_extraction_identity(self):
        """Verify deterministic extraction produces expected source identity."""
        ir = flamecomics.extract(self.extensions_root, timestamp="2026-08-18T12:00:00Z")
        self.assertEqual(ir["schemaVersion"], "0.2")
        self.assertEqual(ir["id"], "en_flamecomics")
        self.assertEqual(ir["name"], "Flame Comics")
        self.assertEqual(ir["languages"], ["en"])
        self.assertEqual(ir["contentOrigins"], ["KR", "JP", "CN"])
        self.assertEqual(ir["contentWarning"], "SAFE")
        self.assertEqual(ir["sourceType"], "api")
        self.assertEqual(ir["baseUrl"], "https://flamecomics.xyz")

    def test_flamecomics_manual_patch_boundaries(self):
        """Verify all required manual-patch boundaries are present and true."""
        ir = flamecomics.extract(self.extensions_root, timestamp="2026-08-18T12:00:00Z")
        self.assertTrue(ir["explore"]["popular"].get("manualPatchRequired", False))
        self.assertTrue(ir["explore"]["latest"].get("manualPatchRequired", False))
        self.assertTrue(ir["search"].get("manualPatchRequired", False))
        self.assertTrue(ir["details"].get("manualPatchRequired", False))
        self.assertTrue(ir["chapters"].get("manualPatchRequired", False))
        self.assertTrue(ir["pages"].get("manualPatchRequired", False))

    def test_flamecomics_provenance(self):
        """Verify provenance metadata extraction."""
        ir = flamecomics.extract(self.extensions_root, timestamp="2026-08-18T12:00:00Z")
        prov = ir["provenance"]
        self.assertEqual(prov["type"], "converted")
        self.assertEqual(prov["upstreamProject"], "keiyoushi")
        self.assertEqual(prov["upstreamPackage"], "eu.kanade.tachiyomi.extension.en.flamecomics")
        self.assertEqual(prov["upstreamSourceId"], "8531542650987673943")
        self.assertEqual(prov["upstreamVersion"], "1.4.50")
        self.assertEqual(prov["upstreamLicense"], "Apache-2.0")
        self.assertEqual(prov["converterVersion"], "0.1.0")
        self.assertEqual(prov["generatedTimestamp"], "2026-08-18T12:00:00Z")

    def test_flamecomics_ir_validates(self):
        """Verify extracted IR passes the canonical IR schema validator."""
        ir = flamecomics.extract(self.extensions_root, timestamp="2026-08-18T12:00:00Z")
        errors = validate_ir_data(ir)
        self.assertEqual(len(errors), 0, f"IR validation errors: {errors}")

    def test_flamecomics_deterministic_byte_identical(self):
        """Verify rerunning extraction produces byte-identical IR output."""
        ir1 = flamecomics.extract(self.extensions_root, timestamp="2026-08-18T12:00:00Z")
        ir2 = flamecomics.extract(self.extensions_root, timestamp="2026-08-18T12:00:00Z")
        s1 = json.dumps(ir1, indent=2, ensure_ascii=False)
        s2 = json.dumps(ir2, indent=2, ensure_ascii=False)
        self.assertEqual(s1, s2)

    def test_flamecomics_base_js_generation(self):
        """Verify Base JS can be generated cleanly from the extracted IR."""
        ir = flamecomics.extract(self.extensions_root, timestamp="2026-08-18T12:00:00Z")
        js = generate_venera_js(ir)
        self.assertIn("class EnFlamecomicsSource extends ComicSource", js)
        self.assertIn('name = "Flame Comics"', js)
        self.assertIn('key = "en_flamecomics"', js)
        self.assertIn("loadPopularCustom", js)
        self.assertIn("loadLatestCustom", js)
        self.assertIn("loadSearchCustom", js)
        self.assertIn("loadEpCustom", js)

    def test_flamecomics_extractor_routing(self):
        """Verify extract.py routes en/flamecomics to the flamecomics adapter."""
        import tempfile
        import subprocess

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            temp_out = f.name

        try:
            cmd = [
                sys.executable,
                os.path.join(extractor_dir, "extract.py"),
                "--source", "en/flamecomics",
                "--extensions-root", self.extensions_root,
                "--output", temp_out,
                "--timestamp", "2026-08-18T12:00:00Z"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"extract.py failed: {res.stderr}")
            self.assertIn("Dispatching to Flame Comics adapter...", res.stdout)
            with open(temp_out, "r", encoding="utf-8") as f:
                saved_ir = json.load(f)
            self.assertEqual(saved_ir["id"], "en_flamecomics")
        finally:
            if os.path.exists(temp_out):
                os.remove(temp_out)


if __name__ == "__main__":
    unittest.main()
