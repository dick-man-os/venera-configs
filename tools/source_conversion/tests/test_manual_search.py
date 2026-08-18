import os
import sys
import unittest
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
generator_dir = os.path.join(os.path.dirname(current_dir), "generator")
sys.path.insert(0, generator_dir)
from js_generator import generate_venera_js, validate_ir_data

extractor_dir = os.path.join(os.path.dirname(current_dir), "extractor")
sys.path.insert(0, extractor_dir)
from generic_html_extractor import extract

class TestManualSearch(unittest.TestCase):

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

    def test_ordinary_generic_search_validates(self):
        ir = self.get_base_ir()
        ir["search"] = {
            "url": "https://test.com/search?q={{query}}",
            "method": "GET",
            "selector": "div.item",
            "fields": {
                "title": "text",
                "url": "@href"
            }
        }
        self.assertEqual(len(validate_ir_data(ir)), 0)

    def test_manual_only_search_validates(self):
        ir = self.get_base_ir()
        ir["search"] = {
            "manualPatchRequired": True
        }
        self.assertEqual(len(validate_ir_data(ir)), 0)

    def test_empty_search_fails(self):
        ir = self.get_base_ir()
        ir["search"] = {}
        errors = validate_ir_data(ir)
        self.assertTrue(len(errors) > 0)

    def test_manual_only_search_generates_no_fake_url(self):
        ir = self.get_base_ir()
        ir["search"] = {
            "manualPatchRequired": True
        }
        js = generate_venera_js(ir)
        self.assertIn("return await this.loadSearchCustom(keyword, options, page);", js)
        self.assertNotIn("Network.get", js[js.find("search = {"):js.find("comic = {")])

    def test_structural_patch_composition_works(self):
        ir = self.get_base_ir()
        ir["search"] = {
            "manualPatchRequired": True
        }
        js = generate_venera_js(ir)
        self.assertIn("loadSearchCustom = async (keyword, options, page) => {", js)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: loadSearchCustom must be implemented in patch layer.");', js)

    def test_existing_modern_generic_search_unchanged(self):
        ir = self.get_base_ir()
        ir["search"] = {
            "url": "https://test.com/search?q={{query}}",
            "method": "GET",
            "selector": "div.item",
            "fields": {
                "title": "text",
                "url": "@href"
            }
        }
        js = generate_venera_js(ir)
        self.assertIn("Network.get", js)

    def test_comicabc_imperative_search_emits_manual_patch(self):
        # We simulate the extractor behavior for an imperative search
        import tempfile
        kt_code = """
        package eu.kanade.tachiyomi.extension.zh.comicabc
        import eu.kanade.tachiyomi.network.GET
        class Comicabc : ParsedHttpSource() {
            override val name = "Comicabc"
            override val baseUrl = "https://example.com"
            override val lang = "zh"
            override val supportsLatest = true
            override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
                val url = baseUrl.toHttpUrlOrNull()!!.newBuilder()
                url.addQueryParameter("q", query)
                return GET(url.toString(), headers)
            }
        }
        """
        with tempfile.NamedTemporaryFile("w", suffix=".kt", delete=False) as f:
            f.write(kt_code)
            tmp_path = f.name

        try:
            ir = extract(tmp_path, {"name": "comicabc", "version": "1.4", "pkg": "eu"}, "1.4", "zh", None)
            self.assertTrue(ir["search"].get("manualPatchRequired", False))
        finally:
            os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
