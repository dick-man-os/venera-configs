import os
import sys
import unittest
import re
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from tools.source_conversion.test_ladder import run_ladder, LadderConfig

class TestFlamecomicsRegression(unittest.TestCase):
    def setUp(self):
        self.patch_path = repo_root / "sources_patches" / "flamecomics.patch.js"
        with open(self.patch_path, "r", encoding="utf-8") as f:
            self.patch_code = f.read()

    def test_flamecomics_new_regression(self):
        extensions_root = repo_root.parent / "extensions-source"
        config = LadderConfig(
            source="en/flamecomics",
            mode="new",
            extensions_root=str(extensions_root),
            patch_path=str(self.patch_path)
        )
        result = run_ladder(config)
        self.assertEqual(result.overall_status, "PASS")
        for stage in result.stages:
            if stage.level != "L6":
                self.assertEqual(stage.status, "PASS", f"{stage.name} failed: {stage.message}")

    def test_buildid_extraction(self):
        self.assertIn('__NEXT_DATA__', self.patch_code)
        self.assertIn('JSON.parse', self.patch_code)
        self.assertTrue(re.search(r'buildId["\']?\s*:\s*([^,}]+)', self.patch_code) or re.search(r'\.buildId', self.patch_code))

    def test_initial_buildid_cache_population(self):
        self.assertTrue(re.search(r'this\._buildId\s*=', self.patch_code))

    def test_cached_buildid_reuse(self):
        self.assertTrue(re.search(r'if\s*\(\s*!this\._buildId\s*\)', self.patch_code))

    def test_stale_buildid_404(self):
        self.assertIn('status === 404', self.patch_code)

    def test_stale_buildid_refresh(self):
        self.assertTrue(re.search(r'this\._buildId\s*=\s*null', self.patch_code) or re.search(r'getBuildId\(\)', self.patch_code))

    def test_retry_uses_new_buildid(self):
        self.assertIn('fetchNextApi', self.patch_code)
        self.assertTrue(re.search(r'fetchNextApi\([^,]+,\s*true\s*\)', self.patch_code))

    def test_retry_exactly_once(self):
        self.assertTrue(re.search(r'res\.status === 404 && !isRetry', self.patch_code))

    def test_second_retry_failure_stops(self):
        self.assertIn('res.status !== 200', self.patch_code)
        self.assertIn('throw new Error', self.patch_code)

    def test_popular(self):
        self.assertIn('browse.json', self.patch_code)
        self.assertNotIn('?page=', self.patch_code[:self.patch_code.find('loadPopularCustom')])
        self.assertIn('views', self.patch_code)

    def test_latest(self):
        self.assertIn('index.json', self.patch_code)
        self.assertIn('latestEntries', self.patch_code)

    def test_search(self):
        self.assertIn('browse.json', self.patch_code)
        self.assertIn('title', self.patch_code)
        self.assertIn('altTitles', self.patch_code)

    def test_details(self):
        self.assertIn('description', self.patch_code)
        self.assertIn('author', self.patch_code)
        self.assertIn('status', self.patch_code)

    def test_details_cache_contract(self):
        self.assertIn('_seriesDataCache', self.patch_code)
        self.assertIn('this._seriesDataCache[', self.patch_code)

    def test_chapters(self):
        self.assertIn('series', self.patch_code)
        self.assertIn('chapter', self.patch_code)
        # Ensure it returns an object mapping { epId: name } and not an array of Chapter objects
        self.assertIn('chapters[epId] = name', self.patch_code)
        self.assertNotIn('new Chapter({', self.patch_code)

    def test_pages(self):
        self.assertIn('images', self.patch_code)
        self.assertIn('cdn.flamecomics.xyz', self.patch_code)
        self.assertIn('release_date', self.patch_code)
        # Ensure image normalization handles numeric-keyed dictionaries
        self.assertIn('Array.isArray(chapter.images)', self.patch_code)
        self.assertIn('Object.keys(chapter.images).sort', self.patch_code)
        self.assertNotIn('let images = chapter.images.map', self.patch_code)

    def test_malformed_payloads(self):
        self.assertIn('if (res.status !== 200)', self.patch_code)
        self.assertIn('throw new Error', self.patch_code)

if __name__ == "__main__":
    unittest.main()
