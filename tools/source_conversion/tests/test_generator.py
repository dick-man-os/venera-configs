import os
import sys
import unittest
import tempfile

# Add generator and validator to path
current_dir = os.path.dirname(os.path.abspath(__file__))
generator_dir = os.path.join(os.path.dirname(current_dir), "generator")
sys.path.insert(0, generator_dir)
from js_generator import generate_venera_js

class TestGenerator(unittest.TestCase):

    def get_base_ir(self):
        return {
            "schemaVersion": "0.1",
            "id": "test_src",
            "name": "Test Source",
            "languages": ["en"],
            "contentOrigins": ["CN"],
            "contentWarning": "SAFE",
            "sourceType": "html",
            "baseUrl": "https://example.com",
            "explore": {},
            "search": {"url": "{{baseUrl}}/search?q={{query}}", "method": "GET", "fields": {}},
            "details": {"url": "https://example.com/comic/{{id}}", "method": "GET", "fields": {}},
            "chapters": {"url": "https://example.com/api/chapters/{{id}}", "method": "GET"},
            "pages": {"url": "https://example.com/api/pages/{{id}}", "method": "GET"}
        }

    def test_static_base_url(self):
        ir = self.get_base_ir()
        js = generate_venera_js(ir)
        self.assertNotIn("settings =", js)
        self.assertIn('static baseUrl = "https://example.com"', js)

    def test_unlabeled_mirrors(self):
        ir = self.get_base_ir()
        ir["mirrors"] = [
            {"url": "https://example.com"},
            {"url": "https://backup.example.com"}
        ]
        js = generate_venera_js(ir)

        # Test default is first mirror
        self.assertIn('default: "https://example.com"', js)

        # Test options array
        self.assertIn('type: "select"', js)
        self.assertIn('options: [', js)
        self.assertIn('{ value: "https://example.com", text: "example.com" }', js)
        self.assertIn('{ value: "https://backup.example.com", text: "backup.example.com" }', js)

        # Test getter
        self.assertIn('get baseUrl() {', js)
        self.assertIn("this.loadSetting('baseUrlSelection')", js)

        # Test generated url usages
        self.assertIn('${this.baseUrl}/search?q', js)

    def test_labeled_mirrors(self):
        ir = self.get_base_ir()
        ir["mirrors"] = [
            {"label": "Main", "url": "https://main.example.com"},
            {"label": "Backup", "url": "https://backup.example.com"}
        ]
        ir["baseUrl"] = "https://main.example.com"
        js = generate_venera_js(ir)

        self.assertIn('{ value: "https://main.example.com", text: "Main" }', js)
        self.assertIn('{ value: "https://backup.example.com", text: "Backup" }', js)
        self.assertIn('default: "https://main.example.com"', js)

    def test_fail_closed_explore(self):
        ir = self.get_base_ir()
        ir["explore"] = {
            "popular": {
                "manualPatchRequired": True
            }
        }
        js = generate_venera_js(ir)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: explore popular must be implemented in patch layer.");', js)

    def test_fail_closed_search(self):
        ir = self.get_base_ir()
        ir["search"]["manualPatchRequired"] = True
        js = generate_venera_js(ir)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: search load must be implemented in patch layer.");', js)

    def test_fail_closed_details(self):
        ir = self.get_base_ir()
        ir["details"]["manualPatchRequired"] = True
        js = generate_venera_js(ir)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: comic loadInfo must be implemented in patch layer.");', js)

    def test_fail_closed_chapters(self):
        ir = self.get_base_ir()
        ir["chapters"]["manualPatchRequired"] = True
        js = generate_venera_js(ir)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: parseChaptersCustom must be implemented in patch layer.");', js)

    def test_fail_closed_pages(self):
        ir = self.get_base_ir()
        ir["pages"]["manualPatchRequired"] = True
        js = generate_venera_js(ir)
        self.assertIn('let res = await Network.get', js)

if __name__ == "__main__":
    unittest.main()
