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
        self.assertIn('${this.baseUrl}/search?q=${encodeURIComponent(keyword)}', js)

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
        self.assertIn('return await this.loadPopularCustom(page);', js)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: loadPopularCustom must be implemented in patch layer.");', js)

    def test_fail_closed_search(self):
        ir = self.get_base_ir()
        ir["search"]["manualPatchRequired"] = True
        js = generate_venera_js(ir)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: loadSearchCustom must be implemented in patch layer.");', js)

    def test_fail_closed_details(self):
        ir = self.get_base_ir()
        ir["details"]["manualPatchRequired"] = True
        js = generate_venera_js(ir)
        self.assertIn("throw new Error('MANUAL PATCH REQUIRED: parseDetailsCustom must be implemented in patch layer.');", js)

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

    def test_chapter_object_generation(self):
        ir = self.get_base_ir()
        ir["chapters"]["isJson"] = False
        ir["chapters"]["selector"] = "div.chapter-list li a"
        ir["chapters"]["fields"] = {"url": "@href", "name": "text"}
        ir["chapters"]["reverse"] = True
        js = generate_venera_js(ir)
        self.assertIn("let chaptersObj = {};", js)
        self.assertIn("chaptersList.reverse();", js)
        self.assertIn("chaptersObj[ch.id] = ch.title", js)
        self.assertIn("return this.parseChaptersCustom(chaptersObj, res.body);", js)

    def test_chapter_object_generation_no_reverse(self):
        ir = self.get_base_ir()
        ir["chapters"]["isJson"] = False
        ir["chapters"]["selector"] = "div.chapter-list li a"
        ir["chapters"]["fields"] = {"url": "@href", "name": "text"}
        ir["chapters"]["reverse"] = False
        js = generate_venera_js(ir)
        self.assertNotIn("chaptersList.reverse();", js)

    def test_safe_partial_details(self):
        ir = self.get_base_ir()
        ir["details"]["manualPatchRequired"] = False
        ir["details"]["fields"] = {"title": "h1", "description": "p", "thumbnail": "img@src"}
        ir["details"]["selector"] = "html"
        js = generate_venera_js(ir)
        self.assertIn('let titleEl = doc.querySelector("h1");', js)
        self.assertIn('let descEl = doc.querySelector("p");', js)
        self.assertNotIn("parseDetailsCustom", js)

    def test_pagination_generation(self):
        ir = self.get_base_ir()
        ir["explore"]["popular"] = {
            "url": "https://example.com/popular/{{page}}",
            "selector": "div.comic-item",
            "fields": {"url": "a@href", "title": "h3 a", "thumbnail": "img@src"},
            "pagination": {
                "hasNextStrategy": "compareAttributes",
                "nextSelector": "a.next",
                "currentSelector": "a.current",
                "attribute": "href"
            }
        }
        js = generate_venera_js(ir)
        self.assertIn('let nextEl = doc.querySelector("a.next");', js)
        self.assertIn('let currEl = doc.querySelector("a.current");', js)
        self.assertIn('let hasNext = nextEl && currEl && nextEl.attributes["href"] !== currEl.attributes["href"];', js)
        self.assertIn('let outMaxPage = hasNext ? page + 1 : page;', js)

    def test_text_field_grammar(self):
        ir = self.get_base_ir()
        ir["chapters"]["isJson"] = False
        ir["chapters"]["selector"] = "div.chapter-list li a"
        ir["chapters"]["fields"] = {"url": "@href", "name": "text"}
        js = generate_venera_js(ir)
        self.assertIn('title: (el.text || \'\'),', js)

    def test_key_sanitization(self):
        cases = [
            ("zh-Hans_manhuashe", "zh_Hans_manhuashe"),
            ("zh-Hant_example", "zh_Hant_example"),
            ("en_webtoons", "en_webtoons"),
            ("some-source--with---hyphens", "some_source_with_hyphens"),
            ("en", "en")
        ]

        for input_id, expected_key in cases:
            ir = self.get_base_ir()
            ir["id"] = input_id
            js = generate_venera_js(ir)
            self.assertIn(f'key = "{expected_key}"', js)

    def test_route_language_comes_from_ir_metadata(self):
        ir = self.get_base_ir()
        ir["id"] = "zh-Hant_webtoons"
        ir["languages"] = ["zh-Hant"]
        ir["explore"]["popular"] = {
            "url": "{{baseUrl}}/{{langCode}}/ranking/trending",
            "selector": ".webtoon_list li a",
            "fields": {},
        }
        ir["search"]["url"] = "{{baseUrl}}/{{langCode}}/search?keyword={{query}}"

        js = generate_venera_js(ir)

        self.assertIn("/zh-hant/ranking/trending", js)
        self.assertIn("/zh-hant/search?keyword=", js)
        self.assertNotIn("/en/ranking/trending", js)

    def test_image_load_custom_false(self):
        ir = self.get_base_ir()
        ir["pages"]["imageLoadPatchRequired"] = False
        js = generate_venera_js(ir)
        self.assertIn("onImageLoad: (url, comicId, epId) => ({", js)
        self.assertNotIn("onImageLoadCustom(url, comicId, epId)", js)

    def test_image_load_custom_true(self):
        ir = self.get_base_ir()
        ir["pages"]["imageLoadPatchRequired"] = True
        js = generate_venera_js(ir)
        self.assertIn("return this.onImageLoadCustom(url, comicId, epId);", js)
        self.assertIn('throw new Error("MANUAL PATCH REQUIRED: onImageLoadCustom must be implemented in patch layer.");', js)
        # Should not have duplicate definitions
        self.assertEqual(js.count("onImageLoad: (url, comicId, epId)"), 1)

if __name__ == "__main__":
    unittest.main()
