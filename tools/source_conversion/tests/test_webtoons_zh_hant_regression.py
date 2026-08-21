import copy
import json
import sys
import unittest
from pathlib import Path


repo_root = Path(__file__).resolve().parents[3]
extractor_dir = repo_root / "tools" / "source_conversion" / "extractor"
generator_dir = repo_root / "tools" / "source_conversion" / "generator"
patcher_dir = repo_root / "tools" / "source_conversion" / "patcher"
for tool_dir in (extractor_dir, generator_dir, patcher_dir):
    sys.path.insert(0, str(tool_dir))

from js_generator import generate_venera_js
from js_patcher import patch_js
from webtoons_extractor import extract_webtoons_ir


class TestWebtoonsZhHantRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extensions_root = repo_root.parent / "extensions-source"
        cls.ir_path = repo_root / "sources_ir" / "webtoons_zh_hant.json"
        cls.base_path = repo_root / "sources_generated" / "webtoons_zh_hant.base.js"
        cls.patch_path = repo_root / "sources_patches" / "webtoons_zh_hant.patch.js"
        cls.final_path = repo_root / "webtoons_zh_hant.js"

        cls.canonical_ir = json.loads(cls.ir_path.read_text(encoding="utf-8"))
        cls.canonical_base = cls.base_path.read_text(encoding="utf-8")
        cls.canonical_patch = cls.patch_path.read_text(encoding="utf-8")
        cls.canonical_final = cls.final_path.read_text(encoding="utf-8")

    def test_zh_hant_ir_is_canonical_extractor_output(self):
        extracted = extract_webtoons_ir(
            str(self.extensions_root),
            timestamp=self.canonical_ir["provenance"]["generatedTimestamp"],
            language="zh-Hant",
            source_version="1.0.0",
        )

        expected = copy.deepcopy(self.canonical_ir)
        expected.pop("artifactId", None)
        self.assertEqual(extracted, expected)

    def test_zh_hant_base_and_final_are_canonical_producer_outputs(self):
        generated = generate_venera_js(self.canonical_ir)
        composed = patch_js(generated, self.canonical_patch)

        self.assertEqual(generated, self.canonical_base)
        self.assertEqual(composed, self.canonical_final)

    def test_zh_hant_runtime_contract(self):
        locale_cookie = next(
            cookie for cookie in self.canonical_ir["cookies"] if cookie["name"] == "locale"
        )

        self.assertEqual(self.canonical_ir["id"], "zh-Hant_webtoons")
        self.assertEqual(self.canonical_ir["version"], "1.0.0")
        self.assertEqual(self.canonical_ir["languages"], ["zh-Hant"])
        self.assertEqual(locale_cookie["value"], "zh_TW")

        self.assertIn('key = "zh_Hant_webtoons"', self.canonical_final)
        self.assertIn('version = "1.0.0"', self.canonical_final)
        self.assertIn("/zh-hant/ranking/trending", self.canonical_final)
        self.assertIn("/zh-hant/originals/${day}?sortOrder=UPDATE", self.canonical_final)
        self.assertIn("/zh-hant/search?keyword=${encodeURIComponent(keyword)}", self.canonical_final)
        self.assertIn('.webtoon_list li a', self.canonical_final)
        self.assertIn('/api/v1/${type}/${titleId}/episodes?pageSize=99999', self.canonical_final)
        self.assertIn('readingLanguageCode=zh-hant', self.canonical_final)
        self.assertIn('div#_imageList > img', self.canonical_final)
        self.assertIn('el.attributes["data-url"]', self.canonical_final)

    def test_english_extractor_profile_remains_structurally_identical(self):
        english_ir_path = repo_root / "sources_ir" / "webtoons.json"
        expected = json.loads(english_ir_path.read_text(encoding="utf-8"))
        extracted = extract_webtoons_ir(
            str(self.extensions_root),
            timestamp=expected["provenance"]["generatedTimestamp"],
        )

        expected_without_release = copy.deepcopy(expected)
        expected_without_release.pop("artifactId", None)
        expected_without_release.pop("version", None)
        self.assertEqual(extracted, expected_without_release)

    def test_index_contains_each_webtoons_key_once(self):
        index = json.loads((repo_root / "index.json").read_text(encoding="utf-8"))
        english = [entry for entry in index if entry.get("key") == "en_webtoons"]
        zh_hant = [entry for entry in index if entry.get("key") == "zh_Hant_webtoons"]

        self.assertEqual(len(english), 1)
        self.assertEqual(english[0]["version"], "1.0.1")
        self.assertEqual(english[0]["fileName"], "webtoons.js")
        self.assertEqual(len(zh_hant), 1)
        self.assertEqual(zh_hant[0]["version"], "1.0.0")
        self.assertEqual(zh_hant[0]["fileName"], "webtoons_zh_hant.js")


if __name__ == "__main__":
    unittest.main()
