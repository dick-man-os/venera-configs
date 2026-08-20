import os
import sys
import json
import difflib
import tempfile
import unittest
import copy
import re
from pathlib import Path

# Add tools directory to sys.path so we can import run_ladder
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.test_ladder import run_ladder, LadderConfig

SOURCE_VERSION_PATTERN = re.compile(
    r'(?m)^(class EnWebtoonsSource extends ComicSource \{\r?\n'
    r'    name = "Webtoons"\r?\n'
    r'    key = "en_webtoons"\r?\n'
    r'    version = ")[^"\r\n]+(")$'
)

class TestWebtoonsRegression(unittest.TestCase):
    def normalize_source_version(self, source, label):
        normalized, replacements = SOURCE_VERSION_PATTERN.subn(
            r'\g<1>NORMALIZED\g<2>', source
        )
        self.assertEqual(
            replacements,
            1,
            f"{label} must contain exactly one EnWebtoonsSource version property",
        )
        return normalized

    def test_webtoons_golden_regression(self):
        # The canonical artifacts are in the venera-configs repo root (repo_root).
        canonical_ir_path = repo_root / "sources_ir" / "webtoons.json"
        canonical_js_path = repo_root / "sources_generated" / "webtoons.base.js"
        canonical_patch_path = repo_root / "sources_patches" / "webtoons.patch.js"
        canonical_final_path = repo_root / "webtoons.js"

        workspace_root = repo_root.parent
        extensions_root = workspace_root / "extensions-source"

        self.assertTrue(extensions_root.exists(), f"extensions-source must exist at {extensions_root}")

        config = LadderConfig(
            source="all/webtoons",
            mode="canonical",
            extensions_root=str(extensions_root),
            patch_path=str(canonical_patch_path),
            canonical_ir=str(canonical_ir_path),
            canonical_base=str(canonical_js_path),
            canonical_final=str(canonical_final_path)
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_ladder(config, override_temp_dir=temp_dir)

            for stage in result.stages:
                if stage.level != "L6":
                    self.assertEqual(stage.status, "PASS", f"{stage.name} failed: {stage.message}")

            # Now we independently assert equality
            print("[*] Comparing IRs...")
            with open(canonical_ir_path, "r", encoding="utf-8") as f:
                canon_ir_bytes = f.read()
                canon_ir = json.loads(canon_ir_bytes)

            temp_ir_path = os.path.join(temp_dir, "temp.json")
            self.assertTrue(os.path.exists(temp_ir_path), "IR STRUCTURAL EQUALITY: False (temp file missing)")

            with open(temp_ir_path, "r", encoding="utf-8") as f:
                temp_ir_bytes = f.read()
                temp_ir = json.loads(temp_ir_bytes)

            # Upstream extractor does not derive local source-release metadata ('version')
            canonical_structural = copy.deepcopy(canon_ir)
            extracted_structural = copy.deepcopy(temp_ir)
            canonical_structural.pop("version", None)
            extracted_structural.pop("version", None)

            ir_structural_equality = canonical_structural == extracted_structural

            print(f"IR STRUCTURAL EQUALITY: {ir_structural_equality}")

            self.assertTrue(ir_structural_equality, "IR structurally differs!")
            self.assertEqual(canon_ir.get("version"), "1.0.1", "Canonical Webtoons IR version must be 1.0.1")

            print("[*] Comparing Base JS...")
            with open(canonical_js_path, "r", encoding="utf-8") as f:
                canon_js_bytes = f.read()

            temp_js_path = os.path.join(temp_dir, "temp.base.js")
            self.assertTrue(os.path.exists(temp_js_path), "BASE JS BYTE IDENTICAL: False (temp file missing)")

            with open(temp_js_path, "r", encoding="utf-8") as f:
                temp_js_bytes = f.read()

            canon_base_normalized = self.normalize_source_version(canon_js_bytes, "Canonical base JS")
            temp_base_normalized = self.normalize_source_version(temp_js_bytes, "Generated base JS")

            base_js_identical = canon_base_normalized == temp_base_normalized
            print(f"BASE JS IDENTICAL (normalized version): {base_js_identical}")

            if not base_js_identical:
                diff = difflib.unified_diff(canon_base_normalized.splitlines(), temp_base_normalized.splitlines(), fromfile='canonical', tofile='generated')
                print('\n'.join(diff))
            self.assertTrue(base_js_identical, "Base JS differs!")

            print("[*] Comparing Final JS...")
            with open(canonical_final_path, "r", encoding="utf-8") as f:
                canon_final_bytes = f.read()

            temp_final_path = os.path.join(temp_dir, "temp.final.js")
            self.assertTrue(os.path.exists(temp_final_path), "FINAL WEBTOONS JS BYTE IDENTICAL: False (temp file missing)")

            with open(temp_final_path, "r", encoding="utf-8") as f:
                temp_final_bytes = f.read()

            canon_final_normalized = self.normalize_source_version(canon_final_bytes, "Canonical final JS")
            temp_final_normalized = self.normalize_source_version(temp_final_bytes, "Generated final JS")

            final_js_identical = canon_final_normalized == temp_final_normalized
            print(f"FINAL WEBTOONS JS IDENTICAL (normalized version): {final_js_identical}")

            if not final_js_identical:
                diff = difflib.unified_diff(canon_final_normalized.splitlines(), temp_final_normalized.splitlines(), fromfile='canonical', tofile='generated')
                print('\n'.join(diff))
            self.assertTrue(final_js_identical, "Final JS differs!")

if __name__ == "__main__":
    unittest.main()
