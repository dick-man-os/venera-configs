import os
import sys
import unittest
import re

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

if __name__ == '__main__':
    unittest.main()
