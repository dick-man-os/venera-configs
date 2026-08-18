import os
import re
import sys
import unittest
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.test_ladder import run_ladder, LadderConfig
from tools.source_conversion.validator.static_js_validator import validate_js_file


class TestComicabcRegression(unittest.TestCase):
    def setUp(self):
        self.patch_path = repo_root / "sources_patches" / "comicabc.patch.js"
        self.final_js_path = repo_root / "comicabc.js"
        self.base_js_path = repo_root / "sources_generated" / "comicabc.base.js"
        self.venerax_test_path = repo_root.parent / "VeneraX" / "test" / "comicabc_runtime_validation_test.dart"

        with open(self.patch_path, "r", encoding="utf-8") as f:
            self.patch_code = f.read()

        with open(self.final_js_path, "r", encoding="utf-8") as f:
            self.final_code = f.read()

    def test_comicabc_ladder_regression(self):
        """Test that Comicabc passes L0-L5 ladder stages."""
        extensions_root = repo_root.parent / "extensions-source"
        config = LadderConfig(
            source="zh/comicabc",
            mode="new",
            extensions_root=str(extensions_root),
            patch_path=str(self.patch_path),
        )
        result = run_ladder(config)
        self.assertEqual(result.overall_status, "PASS")
        for stage in result.stages:
            if stage.level != "L6":
                self.assertEqual(
                    stage.status, "PASS", f"{stage.name} failed: {stage.message}"
                )

    def test_public_loadchapters_bridge(self):
        """Verify loadChapters is defined exactly once in final JS and bridges to parseChaptersCustom."""
        # Must be in patch
        self.assertIn("loadChapters", self.patch_code)
        self.assertTrue(
            re.search(
                r"loadChapters\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{?\s*(?:return\s+)?this\.parseChaptersCustom\(",
                self.patch_code,
            ),
            "loadChapters in patch must bridge to parseChaptersCustom",
        )

        # In final JS, ensure exactly ONE definition of loadChapters
        matches = re.findall(r"\bloadChapters\s*=", self.final_code)
        self.assertEqual(
            len(matches),
            1,
            f"Expected exactly 1 loadChapters assignment in final comicabc.js, found {len(matches)}",
        )

        # Ensure parseChaptersCustom exists in patch and final JS
        self.assertIn("parseChaptersCustom", self.patch_code)
        self.assertIn("parseChaptersCustom", self.final_code)

    def test_absolute_cover_normalization(self):
        """Verify cover URLs are normalized to absolute URLs using baseUrl without double-prefixing."""
        # Search cover normalization
        self.assertIn("coverSrc.startsWith", self.patch_code)
        self.assertIn("ZhhantComicabcSource.baseUrl", self.patch_code)
        self.assertTrue(
            re.search(
                r'if\s*\(\s*coverSrc\.startsWith\([\'"]\/[\'"]\)\s*\)\s*\{\s*coverSrc\s*=\s*`\$\{ZhhantComicabcSource\.baseUrl\}\$\{coverSrc\}`',
                self.patch_code,
            ),
            "Search cover normalization must prefix baseUrl only for relative paths",
        )

        # Details cover normalization
        self.assertTrue(
            re.search(
                r'if\s*\(\s*comicDetails\.cover\s*&&\s*comicDetails\.cover\.startsWith\([\'"]\/[\'"]\)\s*\)\s*\{\s*comicDetails\.cover\s*=\s*`\$\{ZhhantComicabcSource\.baseUrl\}\$\{comicDetails\.cover\}`',
                self.patch_code,
            ),
            "Details cover normalization must prefix baseUrl only for relative paths",
        )

    def test_chapter_sanitization(self):
        """Verify chapter labels are sanitized against inline scripts and document artifacts."""
        # parseChaptersCustom must strip inline scripts, document.*, isnew(), getElementById
        self.assertIn("parseChaptersCustom", self.patch_code)
        self.assertTrue(
            "/<script" in self.patch_code or "replace(/<script" in self.patch_code,
            "Chapter parsing must strip <script> tags",
        )
        self.assertTrue(
            r"/document\." in self.patch_code or "document." in self.patch_code,
            "Chapter parsing must strip document.* calls",
        )
        self.assertTrue(
            r"/isnew\(" in self.patch_code or "isnew(" in self.patch_code,
            "Chapter parsing must strip isnew() artifacts",
        )
        self.assertTrue(
            r"/getElementById\(" in self.patch_code or "getElementById(" in self.patch_code,
            "Chapter parsing must strip getElementById artifacts",
        )

    def test_no_acceptance_fallback(self):
        """Verify the VeneraX runtime E2E test contains no fabricated fallback IDs/chapters."""
        if not self.venerax_test_path.exists():
            self.skipTest(f"VeneraX test file not found at {self.venerax_test_path}")

        with open(self.venerax_test_path, "r", encoding="utf-8") as f:
            dart_test_code = f.read()

        # Must NOT assign hardcoded mock fallback chapter IDs
        self.assertFalse(
            re.search(
                r"(?:firstChapterId|realEpId|epId)\s*=\s*['\"]/view/9154-1\.html['\"]",
                dart_test_code,
            ),
            "Runtime test must not assign hardcoded /view/9154-1.html fallback",
        )
        self.assertFalse(
            re.search(
                r"(?:firstChapterId|realEpId|epId)\s*=\s*['\"]dummy['\"]",
                dart_test_code,
            ),
            "Runtime test must not assign dummy fallback IDs",
        )
        self.assertNotIn(
            "Mock a chapter ID",
            dart_test_code,
            "Runtime test must not mock chapter IDs",
        )

        # Must derive realEpId from loadComicInfo chapter map
        self.assertTrue(
            re.search(r"realEpId\s*=\s*keys\.(?:last|first)", dart_test_code),
            "Runtime test must obtain realEpId directly from returned chapter keys",
        )

    def test_final_js_static_validation(self):
        """Verify final comicabc.js passes static JS validation."""
        self.assertTrue(
            self.final_js_path.exists(),
            f"final comicabc.js does not exist at {self.final_js_path}",
        )
        is_valid = validate_js_file(str(self.final_js_path), phase="final")
        self.assertTrue(is_valid, "Final comicabc.js failed static JS validation")


if __name__ == "__main__":
    unittest.main()
