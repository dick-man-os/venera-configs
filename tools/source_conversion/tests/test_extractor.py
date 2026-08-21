#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

# Add extractor to path
current_dir = os.path.dirname(os.path.abspath(__file__))
extractor_dir = os.path.join(os.path.dirname(current_dir), "extractor")
sys.path.insert(0, extractor_dir)

from generic_html_extractor import (
    _extract_chapters,
    _extract_list_parser,
    _extract_url_template,
    _select_gradle_source,
)

class TestExtractor(unittest.TestCase):
    def test_extract_url_template(self):
        body = 'client.get("$baseUrl/category/order/hits/page/$page")'
        url = _extract_url_template(body)
        self.assertEqual(url, "{{baseUrl}}/category/order/hits/page/{{page}}")

        body_query = 'client.get("$baseUrl/search/$query/$page")'
        url_query = _extract_url_template(body_query)
        self.assertEqual(url_query, "{{baseUrl}}/search/{{query}}/{{page}}")


    def test_extract_list_parser(self):
        body = 'return parseManga(document)'
        content = """
fun parseManga(document: Document): MangasPage {
    val mangas = document.select("div.comic-list > div.comic-item").map { element ->
        SChapter.create().apply {
            title = element.selectFirst("h3 a")!!.text()
            setUrlWithoutDomain(element.selectFirst("a")!!.absUrl("href"))
            thumbnail_url = element.selectFirst("img")!!.attr("src")
        }
    }
    val nextPage = document.selectFirst("div.pagination > a.next")!!.attr("href")
    val currentPage = document.selectFirst("div.pagination > a.on")!!.attr("href")
    return MangasPage(mangas, nextPage != currentPage)
}
        """
        res = _extract_list_parser(content, body, "MODERN")
        self.assertEqual(res["selector"], "div.comic-list > div.comic-item")
        self.assertEqual(res["fields"]["title"], "h3 a")
        self.assertEqual(res["fields"]["url"], "a@href")
        self.assertEqual(res["fields"]["thumbnail"], "img@src")
        self.assertFalse(res["manualPatchRequired"])

        self.assertIn("pagination", res)
        self.assertEqual(res["pagination"]["hasNextStrategy"], "compareAttributes")
        self.assertEqual(res["pagination"]["nextSelector"], "div.pagination > a.next")

    def test_extract_chapter_list_parser(self):
        content = """
fun fetchMangaUpdate(): String {
    val chapters = document.select("div.chapter-list li a").map { element ->
        SChapter.create().apply {
            name = element.text()
            setUrlWithoutDomain(element.attr("href"))
        }
    }.asReversed()
}
        """
        res = _extract_chapters(content, "fetchMangaUpdate")
        self.assertEqual(res["selector"], "div.chapter-list li a")
        self.assertEqual(res["fields"]["name"], "text")
        self.assertEqual(res["fields"]["url"], "@href")
        self.assertFalse(res["manualPatchRequired"])
        self.assertTrue(res.get("reverse", False))

    def test_extract_chapter_list_parser_no_reverse(self):
        content = """
fun fetchMangaUpdate(): String {
    val chapters = document.select("div.chapter-list li a").map { element ->
        SChapter.create().apply {
            name = element.text()
            setUrlWithoutDomain(element.attr("href"))
        }
    }
}
        """
        res = _extract_chapters(content, "fetchMangaUpdate")
        self.assertFalse(res.get("reverse", False))

    def test_extract_details_unsupported(self):
        from generic_html_extractor import _extract_details
        content = """
fun fetchMangaUpdate(): String {
    title = document.selectFirst("h1")!!.text()
    author = document.selectFirst("div.unsupported:contains(author)")
}
        """
        res = _extract_details(content, "fetchMangaUpdate")
        self.assertTrue(res["manualPatchRequired"])

    def test_extract_details_safe(self):
        from generic_html_extractor import _extract_details
        content = """
fun fetchMangaUpdate(): String {
    title = document.selectFirst("h1")!!.text()
    author = document.selectFirst("div.author")
}
        """
        res = _extract_details(content, "fetchMangaUpdate")
        self.assertFalse(res["manualPatchRequired"])

    def test_extract_pages(self):
        from generic_html_extractor import _extract_pages
        content = """
fun getPageList(): String {
    return document.select("div.comic-content > img").mapIndexed { index, it ->
        Page(index, imageUrl = it.attr("src"))
    }
}
        """
        res = _extract_pages(content, "getPageList")
        self.assertEqual(res["selector"], "div.comic-content > img")
        self.assertEqual(res["fields"]["imageUrl"], "@src")
        self.assertFalse(res["manualPatchRequired"])

    def test_map_language(self):
        from generic_html_extractor import _map_language
        self.assertEqual(_map_language("zh"), ["zh-Hans"])
        self.assertEqual(_map_language("en"), ["en"])

    def test_multiple_sources_use_unique_language_rule(self):
        metadata = {
            "sources": [
                {"name": "English", "lang": "en", "sourceId": "1"},
                {"name": "French", "lang": "fr", "sourceId": "2"},
            ]
        }
        selected = _select_gradle_source(metadata, "fr")
        self.assertEqual(selected["sourceId"], "2")

    def test_multiple_sources_can_be_selected_explicitly_by_source_id(self):
        metadata = {
            "sources": [
                {"name": "First", "lang": "en", "sourceId": "111"},
                {"name": "Second", "lang": "en", "sourceId": "222"},
            ]
        }
        selected = _select_gradle_source(metadata, "en", source_id="222")
        self.assertEqual(selected["name"], "Second")

    def test_ambiguous_multiple_sources_fail_closed(self):
        metadata = {
            "sources": [
                {"name": "First", "lang": "en", "sourceId": "111"},
                {"name": "Second", "lang": "en", "sourceId": "222"},
            ]
        }
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            _select_gradle_source(metadata, "en")

    def test_structured_metadata_drives_generic_identity_and_provenance(self):
        from generic_html_extractor import extract

        metadata = {
            "name": "Extension Name",
            "libVersion": "1.6",
            "version": "1.6.9",
            "contentWarning": "SAFE",
            "sources": [
                {
                    "name": "Per Source Name",
                    "lang": "en",
                    "sourceId": "9223372036854775806",
                    "baseUrlMode": "custom",
                    "defaultBaseUrl": "https://source.example",
                    "baseUrlResolved": True,
                    "mirrors": [],
                }
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".kt", encoding="utf-8", delete=False
        ) as fixture:
            fixture.write(
                "package example.selected\nclass SelectedSource : KeiSource() {}\n"
            )
            path = fixture.name
        try:
            ir = extract(path, metadata, "2026-08-21T00:00:00Z", "en")
        finally:
            os.unlink(path)

        self.assertEqual(ir["name"], "Per Source Name")
        self.assertEqual(ir["baseUrl"], "https://source.example")
        self.assertEqual(ir["provenance"]["upstreamVersion"], "1.6.9")
        self.assertEqual(
            ir["provenance"]["upstreamSourceId"], "9223372036854775806"
        )

if __name__ == '__main__':
    unittest.main()
