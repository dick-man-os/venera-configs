import os
import sys
import json
import difflib
import tempfile
import unittest
from pathlib import Path

# Add tools directory to sys.path so we can import run_ladder
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.test_ladder import run_ladder, LadderConfig

class TestWebtoonsRegression(unittest.TestCase):
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

            ir_structural_equality = canon_ir == temp_ir
            ir_byte_identical = canon_ir_bytes == temp_ir_bytes

            print(f"IR STRUCTURAL EQUALITY: {ir_structural_equality}")
            print(f"IR BYTE IDENTICAL: {ir_byte_identical}")

            self.assertTrue(ir_structural_equality, "IR structurally differs!")
            # Note: We won't strictly fail byte equality here for IR in case of newline mismatch on checkout,
            # but we print it. The ladder itself performs a filecmp.
            # We follow user request to assert it though.
            self.assertTrue(ir_byte_identical, "IR byte identical differs!")

            print("[*] Comparing Base JS...")
            with open(canonical_js_path, "r", encoding="utf-8") as f:
                canon_js_bytes = f.read()

            temp_js_path = os.path.join(temp_dir, "temp.base.js")
            self.assertTrue(os.path.exists(temp_js_path), "BASE JS BYTE IDENTICAL: False (temp file missing)")

            with open(temp_js_path, "r", encoding="utf-8") as f:
                temp_js_bytes = f.read()

            base_js_byte_identical = canon_js_bytes == temp_js_bytes
            print(f"BASE JS BYTE IDENTICAL: {base_js_byte_identical}")

            if not base_js_byte_identical:
                diff = difflib.unified_diff(canon_js_bytes.splitlines(), temp_js_bytes.splitlines(), fromfile='canonical', tofile='generated')
                print('\n'.join(diff))
            self.assertTrue(base_js_byte_identical, "Base JS differs!")

            print("[*] Comparing Final JS...")
            with open(canonical_final_path, "r", encoding="utf-8") as f:
                canon_final_bytes = f.read()

            temp_final_path = os.path.join(temp_dir, "temp.final.js")
            self.assertTrue(os.path.exists(temp_final_path), "FINAL WEBTOONS JS BYTE IDENTICAL: False (temp file missing)")

            with open(temp_final_path, "r", encoding="utf-8") as f:
                temp_final_bytes = f.read()

            final_js_byte_identical = canon_final_bytes == temp_final_bytes
            print(f"FINAL WEBTOONS JS BYTE IDENTICAL: {final_js_byte_identical}")

            if not final_js_byte_identical:
                diff = difflib.unified_diff(canon_final_bytes.splitlines(), temp_final_bytes.splitlines(), fromfile='canonical', tofile='generated')
                print('\n'.join(diff))
            self.assertTrue(final_js_byte_identical, "Final JS differs!")

            if result.overall_status != "PASS":
                print("Webtoons regression assertions passed, but overall ladder result failed.")
                for stage in result.stages:
                    print(f"[{stage.status}] {stage.level} - {stage.name}: {stage.message}")
                if hasattr(result, 'error_message') and result.error_message:
                    print(result.error_message)

            self.assertEqual(result.overall_status, "PASS")

if __name__ == "__main__":
    unittest.main()
