import os
import sys
import unittest
import re
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
generator_dir = os.path.join(os.path.dirname(current_dir), "generator")
sys.path.insert(0, generator_dir)
from js_generator import generate_venera_js

class TestPageInterpolation(unittest.TestCase):
    def test_explore_page_interpolation(self):
        ir = {
            "schemaVersion": "0.1",
            "id": "test_src",
            "name": "Test Source",
            "languages": ["en"],
            "contentOrigins": ["CN"],
            "contentWarning": "SAFE",
            "sourceType": "html",
            "baseUrl": "https://example.com",
            "explore": {
                "popular": {
                    "url": "{{baseUrl}}/comic/h-{{page}}.html",
                    "selector": "div.comic-item",
                    "fields": {"url": "a@href"},
                    "manualPatchRequired": False,
                    "pagination": {"hasNextStrategy": "none"}
                }
            }
        }
        js = generate_venera_js(ir)

        # 1. Must not leave literal {{page}}
        self.assertNotIn('{{page}}', js)

        # 2. Extract the URL assignment logic inside popular.load
        match = re.search(r'Network\.get\(`([^`]+)`', js)
        self.assertIsNotNone(match, "Could not find url assignment in generated JS")
        url_template = match.group(1)

        # Prove it interpolates page values correctly
        def simulate_js_template(template, base_url, page):
            return template.replace('${TestSrcSource.baseUrl}', base_url).replace('${page}', str(page))

        page1_url = simulate_js_template(url_template, "https://example.com", 1)
        self.assertEqual(page1_url, "https://example.com/comic/h-1.html")

        page2_url = simulate_js_template(url_template, "https://example.com", 2)
        self.assertEqual(page2_url, "https://example.com/comic/h-2.html")

    def test_committed_manhuashe_pagination_release(self):
        repo_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))

        with open(os.path.join(repo_root, "sources_ir", "manhuashe.json"), encoding="utf-8") as f:
            ir = json.load(f)
        with open(os.path.join(repo_root, "sources_generated", "manhuashe.base.js"), encoding="utf-8") as f:
            base_js = f.read()
        with open(os.path.join(repo_root, "manhuashe.js"), encoding="utf-8") as f:
            final_js = f.read()
        with open(os.path.join(repo_root, "index.json"), encoding="utf-8") as f:
            index = json.load(f)

        expected_version = "1.0.1"
        popular_path = "/category/order/hits/page/${page}"
        latest_path = "/category/order/addtime/page/${page}"

        self.assertEqual(ir["version"], expected_version)
        for artifact in (base_js, final_js):
            self.assertIn(popular_path, artifact)
            self.assertIn(latest_path, artifact)

        self.assertNotIn("/category/order/hits/page/{{page}}", final_js)
        self.assertNotIn("/category/order/addtime/page/{{page}}", final_js)

        version_match = re.search(r'version = "([^"]+)"', final_js)
        self.assertIsNotNone(version_match)
        index_entry = next(item for item in index if item["fileName"] == "manhuashe.js")
        self.assertEqual(version_match.group(1), expected_version)
        self.assertEqual(index_entry["version"], expected_version)

if __name__ == '__main__':
    unittest.main()
