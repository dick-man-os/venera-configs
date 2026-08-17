import os
import sys
import unittest
import tempfile

# Add extractor to path
current_dir = os.path.dirname(os.path.abspath(__file__))
extractor_dir = os.path.join(os.path.dirname(current_dir), "extractor")
sys.path.insert(0, extractor_dir)

from common.gradle_parser import parse_gradle_metadata
from common.selector_analyzer import analyze_selector
from common.kotlin_parser import extract_method_body

class TestParsers(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_temp_file(self, content):
        path = os.path.join(self.temp_dir.name, "build.gradle.kts")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_one_source_block(self):
        content = """
        keiyoushi {
            name = "Test"
            versionCode = 1
            libVersion = "1.6"
            contentWarning = ContentWarning.SAFE
            source {
                name = "Test Source"
                lang = "en"
                baseUrl = "https://example.com"
                id = 12345L
            }
        }
        """
        path = self.write_temp_file(content)
        meta = parse_gradle_metadata(path)
        self.assertEqual(meta["name"], "Test")
        self.assertTrue(meta["is_modern"])
        self.assertEqual(meta["version_classification"], "MODERN_KEISOURCE")
        self.assertEqual(len(meta["sources"]), 1)
        self.assertEqual(meta["sources"][0]["name"], "Test Source")
        self.assertEqual(meta["sources"][0]["id"], 12345)
        self.assertEqual(meta["sources"][0]["baseUrl"], "https://example.com")

    def test_multiple_source_blocks(self):
        content = """
        keiyoushi {
            name = "Test Multi"
            versionCode = 2
            libVersion = "1.4"
            source {
                name = "Src1"
                baseUrl = "https://a.com"
            }
            source {
                name = "Src2"
                baseUrl = "https://b.com"
            }
        }
        """
        path = self.write_temp_file(content)
        meta = parse_gradle_metadata(path)
        self.assertTrue(meta["is_legacy"])
        self.assertEqual(meta["version_classification"], "LEGACY_HTTPSOURCE")
        self.assertEqual(len(meta["sources"]), 2)
        self.assertEqual(meta["sources"][0]["name"], "Src1")
        self.assertEqual(meta["sources"][1]["name"], "Src2")

    def test_mirrors_custom_detection(self):
        content = """
        source {
            name = "Baozi"
            baseUrl {
                mirrors(
                    "https://cn.baozimh.com",
                    "https://tw.baozimh.com"
                )
            }
        }
        """
        path = self.write_temp_file(content)
        meta = parse_gradle_metadata(path)
        self.assertEqual(len(meta["sources"]), 1)

        src1 = meta["sources"][0]
        self.assertEqual(src1["baseUrl"], "https://cn.baozimh.com")
        self.assertIn("mirrors", src1)
        self.assertEqual(len(src1["mirrors"]), 2)
        self.assertEqual(src1["mirrors"][0]["url"], "https://cn.baozimh.com")
        self.assertNotIn("label", src1["mirrors"][0])

    def test_labeled_mirrors(self):
        content = """
        source {
            name = "Labeled"
            baseUrl {
                mirrors(
                    "Main" to "https://main.com",
                    "Backup" to "https://backup.com"
                )
            }
        }
        """
        path = self.write_temp_file(content)
        meta = parse_gradle_metadata(path)
        src = meta["sources"][0]
        self.assertEqual(src["baseUrl"], "https://main.com")
        self.assertEqual(len(src["mirrors"]), 2)
        self.assertEqual(src["mirrors"][0]["label"], "Main")
        self.assertEqual(src["mirrors"][0]["url"], "https://main.com")

    def test_mixed_mirrors_raises(self):
        content = """
        source {
            baseUrl {
                mirrors(
                    "https://main.com",
                    "Backup" to "https://backup.com"
                )
            }
        }
        """
        path = self.write_temp_file(content)
        with self.assertRaises(ValueError):
            parse_gradle_metadata(path)

    def test_brace_scanner_comment_string(self):
        content = """
        // source { "broken" }
        /* source {
        } */
        source {
            name = "Real Source"
            baseUrl = "https://real.com"
            // }
            val x = "{}"
        }
        """
        path = self.write_temp_file(content)
        meta = parse_gradle_metadata(path)
        self.assertEqual(len(meta["sources"]), 1)
        self.assertEqual(meta["sources"][0]["baseUrl"], "https://real.com")

    def test_selector_analyzer_safe(self):
        self.assertEqual(analyze_selector(".class #id")["classification"], "SAFE")
        self.assertEqual(analyze_selector("div > p + span ~ a")["classification"], "SAFE")
        self.assertEqual(analyze_selector("a[href*='comic']")["classification"], "SAFE")
        self.assertEqual(analyze_selector(":first-child")["classification"], "SAFE")
        self.assertEqual(analyze_selector(":nth-child(2)")["classification"], "SAFE")
        self.assertEqual(analyze_selector(":not(.class)")["classification"], "SAFE")

    def test_selector_analyzer_complex_not(self):
        res = analyze_selector(":not(.class > div)")
        self.assertEqual(res["classification"], "TRANSFORMABLE")

    def test_selector_analyzer_nth_of_type(self):
        res = analyze_selector("div.info:nth-of-type(2)")
        self.assertEqual(res["classification"], "MANUAL_PATCH_REQUIRED")

    def test_selector_analyzer_contains(self):
        res = analyze_selector("a:contains(Read)")
        self.assertEqual(res["classification"], "MANUAL_PATCH_REQUIRED")

    def test_selector_analyzer_eq(self):
        res = analyze_selector("div.chapter:eq(1)")
        self.assertEqual(res["classification"], "TRANSFORMABLE")
        self.assertIn(".querySelectorAll()[n]", res["suggestion"])

    def test_extract_method_body_same_line_expression(self):
        content = """
        fun popularMangaRequest(page: Int): Request = GET("url")
        fun other() {}
        """
        body = extract_method_body(content, "popularMangaRequest")
        self.assertEqual(body, 'GET("url")')

    def test_extract_method_body_next_line_expression(self):
        content = """
        fun popularMangaRequest(page: Int): Request =
            GET("url")
        fun other() {}
        """
        body = extract_method_body(content, "popularMangaRequest")
        self.assertEqual(body, 'GET("url")')

    def test_extract_method_body_next_line_apply_block(self):
        content = """
        fun mangaDetailsParse(response: Response): SManga =
            SManga.create().apply {
                title = "test"
            }
        fun other() {}
        """
        body = extract_method_body(content, "mangaDetailsParse")
        self.assertIn('title = "test"', body)
        self.assertIn('apply {', body)
        self.assertNotIn('fun other()', body)

    def test_extract_method_body_adjacent_method_not_captured(self):
        content = """
        fun mangaDetailsParse(response: Response): SManga = SManga.create().apply { title = "test" }
        fun other() = GET("other")
        """
        body = extract_method_body(content, "mangaDetailsParse")
        self.assertNotIn('GET("other")', body)

        body_other = extract_method_body(content, "other")
        self.assertEqual(body_other, 'GET("other")')

if __name__ == "__main__":
    unittest.main()
