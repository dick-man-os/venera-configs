import os
import tempfile
import sys
import unittest
from typing import Dict, Any

current_dir = os.path.dirname(os.path.abspath(__file__))
extractor_dir = os.path.join(os.path.dirname(current_dir), "extractor")
sys.path.insert(0, extractor_dir)

import generic_html_extractor

class TestLegacyHttpSourceExtractor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_kt(self, name: str, content: str) -> str:
        path = os.path.join(self.temp_dir.name, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_modern_dispatch_does_not_enter_legacy(self):
        # A modern KeiSource should not use HttpSource legacy methods
        kt = """
        package eu.kanade.tachiyomi.extension.zh.modern
        import keiyoushi.annotation.Source

        @Source
        class ModernSource : KeiSource() {
            override val baseUrl = "https://modern.com"

            // This is a legacy method, should be ignored by modern dispatch
            override fun popularMangaRequest(page: Int): Request = GET("$baseUrl/pop")
            override fun popularMangaParse(response: Response): MangasPage {
                return MangasPage(emptyList(), false)
            }
        }
        """
        path = self._write_kt("ModernSource.kt", kt)
        gradle_meta = {"name": "Modern", "version": "1.6"}

        ir = generic_html_extractor.extract(path, gradle_meta, "timestamp", "zh")
        # Since getPopularManga isn't there, popular should be empty
        self.assertNotIn("popular", ir.get("explore", {}))

    def test_legacy_dispatch_uses_legacy_methods(self):
        kt = """
        package eu.kanade.tachiyomi.extension.zh.legacy
        import keiyoushi.annotation.Source

        @Source
        class LegacySource : HttpSource() {
            override val baseUrl = "https://legacy.com"

            override fun popularMangaRequest(page: Int): Request = GET("$baseUrl/pop-$page")
            override fun popularMangaParse(response: Response): MangasPage {
                val document = response.asJsoup()
                val mangas = document.select(".manga-list a").map { element ->
                    SManga.create().apply {
                        title = element.text()
                        setUrlWithoutDomain(element.absUrl("href"))
                        thumbnail_url = element.selectFirst("img")!!.attr("src")
                    }
                }
                val hasNextPage = document.selectFirst(".next") != null
                return MangasPage(mangas, hasNextPage)
            }

            override fun mangaDetailsParse(response: Response): SManga = SManga.create().apply {
                val document = response.asJsoup()
                title = document.selectFirst(".title")!!.text()
                description = document.selectFirst(".desc")!!.text()
                thumbnail_url = document.selectFirst(".cover img")!!.attr("src")
            }
        }
        """
        path = self._write_kt("LegacySource.kt", kt)
        gradle_meta = {"name": "Legacy", "version": "1.4"}

        ir = generic_html_extractor.extract(path, gradle_meta, "timestamp", "zh")

        # Check Popular
        self.assertIn("popular", ir.get("explore", {}))
        pop = ir["explore"]["popular"]
        self.assertEqual(pop["method"], "GET")
        self.assertEqual(pop["url"], "{{baseUrl}}/pop-{{page}}")
        self.assertEqual(pop["selector"], ".manga-list a")

        # Check Details
        details = ir["details"]
        self.assertFalse(details.get("manualPatchRequired", True))
        self.assertEqual(details["fields"]["title"], ".title")

    def test_unknown_classification_fails_closed(self):
        kt = """
        package eu.kanade.tachiyomi.extension.zh.unknown
        import keiyoushi.annotation.Source

        @Source
        class UnknownSource : WeirdSource() {
        }
        """
        path = self._write_kt("UnknownSource.kt", kt)
        gradle_meta = {"name": "Unknown", "version": "1.5"} # Weird version

        with self.assertRaises(ValueError) as context:
            generic_html_extractor.extract(path, gradle_meta, "timestamp", "zh")
        self.assertIn("Unknown or inconsistent source classification", str(context.exception))

    def test_contradictory_classification_fails_closed(self):
        kt_http = "class ContradictorySource : HttpSource() {}"
        path_http = self._write_kt("HttpSource.kt", kt_http)
        with self.assertRaises(ValueError) as context:
            generic_html_extractor.extract(path_http, {"version": "1.6"}, "timestamp", "zh")
        self.assertIn("Contradictory classification", str(context.exception))

        kt_kei = "class ContradictorySource : KeiSource() {}"
        path_kei = self._write_kt("KeiSource.kt", kt_kei)
        with self.assertRaises(ValueError) as context:
            generic_html_extractor.extract(path_kei, {"version": "1.4"}, "timestamp", "zh")
        self.assertIn("Contradictory classification", str(context.exception))

    def test_explicit_zh_hant_override(self):
        kt = """
        package eu.kanade.tachiyomi.extension.zh.hant
        class HantSource : HttpSource() {}
        """
        path = self._write_kt("HantSource.kt", kt)
        gradle_meta = {"name": "Hant", "version": "1.4"}

        ir = generic_html_extractor.extract(path, gradle_meta, "timestamp", "zh", language_override="zh-Hant")
        self.assertEqual(ir["languages"], ["zh-Hant"])

    def test_default_zh_remains_unchanged(self):
        kt = """
        package eu.kanade.tachiyomi.extension.zh.hans
        class HansSource : HttpSource() {}
        """
        path = self._write_kt("HansSource.kt", kt)
        gradle_meta = {"name": "Hans", "version": "1.4"}

        ir = generic_html_extractor.extract(path, gradle_meta, "timestamp", "zh")
        self.assertEqual(ir["languages"], ["zh-Hans"])

    def test_custom_chapter_url_manipulation_manual_patch(self):
        kt = """
        package eu.kanade.tachiyomi.extension.zh.legacy
        class LegacySource : HttpSource() {
            override fun chapterListParse(response: Response): List<SChapter> {
                val document = response.asJsoup()
                return document.select(".chapters a").map { element ->
                    SChapter.create().apply {
                        name = element.text()
                        val onclick = element.attr("onclick")
                        val params = onclick.substringAfter("cview('").substringBefore("'")
                        url = "https://custom.com/ch-$params"
                    }
                }
            }
        }
        """
        path = self._write_kt("LegacySource.kt", kt)
        gradle_meta = {"name": "Legacy", "version": "1.4"}

        ir = generic_html_extractor.extract(path, gradle_meta, "timestamp", "zh")
        self.assertTrue(ir["chapters"].get("manualPatchRequired", False))

    def test_quickjs_page_parsing_manual_patch(self):
        kt = """
        package eu.kanade.tachiyomi.extension.zh.legacy
        class LegacySource : HttpSource() {
            override fun pageListParse(response: Response): List<Page> {
                val html = response.body.string()
                val quickJs = QuickJs.create()
                return emptyList()
            }
        }
        """
        path = self._write_kt("LegacySource.kt", kt)
        gradle_meta = {"name": "Legacy", "version": "1.4"}

        ir = generic_html_extractor.extract(path, gradle_meta, "timestamp", "zh")
        self.assertTrue(ir["pages"].get("manualPatchRequired", False))

if __name__ == "__main__":
    unittest.main()
