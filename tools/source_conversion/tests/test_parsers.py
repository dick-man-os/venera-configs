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
        self.assertEqual(meta["versionCode"], 1)
        self.assertEqual(meta["libVersion"], "1.6")
        self.assertEqual(meta["contentWarning"], "SAFE")
        self.assertEqual(meta["version"], "1.6.1")
        self.assertTrue(meta["is_modern"])
        self.assertEqual(meta["version_classification"], "MODERN_KEISOURCE")
        self.assertEqual(len(meta["sources"]), 1)
        self.assertEqual(meta["sources"][0]["name"], "Test Source")
        self.assertEqual(meta["sources"][0]["id"], "12345")
        self.assertEqual(meta["sources"][0]["sourceId"], "12345")
        self.assertEqual(meta["sources"][0]["sourceIdKind"], "explicit")
        self.assertEqual(meta["sources"][0]["baseUrlMode"], "static")
        self.assertTrue(meta["sources"][0]["baseUrlResolved"])
        self.assertEqual(meta["sources"][0]["baseUrl"], "https://example.com")

    def test_default_source_name_and_generated_id(self):
        content = """
        keiyoushi {
            name = "Webtoons.com"
            versionCode = 57
            libVersion = "1.4"
            contentWarning = ContentWarning.SAFE
            source {
                lang = "en"
                baseUrl = "https://www.webtoons.com"
            }
        }
        """
        meta = parse_gradle_metadata(self.write_temp_file(content))
        source = meta["sources"][0]
        self.assertEqual(source["name"], "Webtoons.com")
        self.assertTrue(source["nameIsDefault"])
        self.assertEqual(source["sourceId"], "2522335540328470744")
        self.assertEqual(source["sourceIdKind"], "generated")

    def test_explicit_large_source_id_is_decimal_string_and_version_id_is_captured(self):
        content = """
        keiyoushi {
            name = "Large ID"
            versionCode = 9
            libVersion = "1.6"
            contentWarning = ContentWarning.MIXED
            source {
                lang = "en"
                id = 9223372036854775806L
                versionId = 7
                baseUrl = "https://large.example"
            }
        }
        """
        source = parse_gradle_metadata(self.write_temp_file(content))["sources"][0]
        self.assertEqual(source["id"], "9223372036854775806")
        self.assertEqual(source["sourceId"], "9223372036854775806")
        self.assertEqual(source["versionId"], 7)
        self.assertEqual(source["effectiveVersionId"], 7)

    def test_theme_metadata_and_version_composition(self):
        root = self.temp_dir.name
        extension_dir = os.path.join(root, "src", "en", "themed")
        theme_dir = os.path.join(root, "lib-multisrc", "madara")
        os.makedirs(extension_dir)
        os.makedirs(theme_dir)
        extension_path = os.path.join(extension_dir, "build.gradle.kts")
        theme_path = os.path.join(theme_dir, "build.gradle.kts")
        with open(extension_path, "w", encoding="utf-8") as f:
            f.write("""
            keiyoushi {
                name = "Themed"
                versionCode = 3
                libVersion = "1.4"
                contentWarning = ContentWarning.SAFE
                theme = "madara"
                source {
                    lang = "en"
                    baseUrl = "https://themed.example"
                }
            }
            """)
        with open(theme_path, "w", encoding="utf-8") as f:
            f.write("""
            keiyoushi {
                baseVersionCode = 52
                libVersion = "1.4"
            }
            """)

        meta = parse_gradle_metadata(extension_path, extensions_root=root)
        self.assertEqual(meta["theme"], "madara")
        self.assertTrue(meta["is_multisrc"])
        self.assertTrue(meta["themeMetadata"]["resolved"])
        self.assertEqual(meta["themeMetadata"]["baseVersionCode"], 52)
        self.assertEqual(meta["derivedVersionCode"], 55)
        self.assertEqual(meta["version"], "1.4.55")

    def test_unresolved_theme_version_is_not_guessed(self):
        content = """
        keiyoushi {
            name = "Missing Theme"
            versionCode = 2
            libVersion = "1.6"
            contentWarning = ContentWarning.SAFE
            theme = "not-checked-out"
            source {
                lang = "en"
                baseUrl = "https://missing.example"
            }
        }
        """
        meta = parse_gradle_metadata(self.write_temp_file(content))
        self.assertEqual(meta["theme"], "not-checked-out")
        self.assertEqual(meta["versionResolution"], "unresolved")
        self.assertIsNone(meta["version"])
        self.assertIn("version", meta["unresolved"])

    def test_dynamic_theme_is_multisrc_and_version_is_unresolved(self):
        content = """
        keiyoushi {
            name = "Dynamic Theme"
            versionCode = 2
            libVersion = "1.6"
            contentWarning = ContentWarning.SAFE
            theme = providers.gradleProperty("themeName").get()
            source {
                lang = "en"
                baseUrl = "https://dynamic-theme.example"
            }
        }
        """
        meta = parse_gradle_metadata(self.write_temp_file(content))
        self.assertTrue(meta["is_multisrc"])
        self.assertIsNone(meta["theme"])
        self.assertEqual(meta["versionResolution"], "unresolved")
        self.assertIn("theme", meta["unresolved"])

    def test_multiple_source_blocks(self):
        content = """
        keiyoushi {
            name = "Test Multi"
            versionCode = 2
            libVersion = "1.4"
            source {
                name = "Src1"
                lang = "en"
                baseUrl = "https://a.com"
            }
            source {
                name = "Src2"
                lang = "fr"
                versionId = 2
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
        self.assertEqual(meta["sources"][0]["lang"], "en")
        self.assertEqual(meta["sources"][1]["lang"], "fr")
        self.assertEqual(meta["sources"][1]["versionId"], 2)
        self.assertEqual(meta["sources"][0]["baseUrl"], "https://a.com")
        self.assertEqual(meta["sources"][1]["baseUrl"], "https://b.com")

    def test_source_blocks_are_scoped_to_authoritative_keiyoushi_block(self):
        content = r'''
        // source { name = "Commented Outside" }
        /* source { name = "Block Commented Outside" } */
        val outsideText = "source { name = \"String Outside\" }"
        val outsideTriple = """source { name = "Triple String Outside" }"""
        unrelated {
            source {
                name = "Nested Outside"
                lang = "xx"
                baseUrl = "https://nested-outside.example"
            }
        }
        source {
            name = "Direct Outside"
            lang = "yy"
            baseUrl = "https://direct-outside.example"
        }
        keiyoushi {
            name = "Scoped"
            versionCode = 1
            libVersion = "1.6"
            contentWarning = ContentWarning.SAFE
            // source { name = "Commented Inside" }
            /* source { name = "Block Commented Inside" } */
            val insideText = "source { name = \"String Inside\" }"
            val insideTriple = """source { name = "Triple String Inside" }"""
            source {
                name = "Authoritative"
                lang = "en"
                baseUrl = "https://authoritative.example"
            }
        }
        '''
        meta = parse_gradle_metadata(self.write_temp_file(content))
        self.assertEqual(len(meta["sources"]), 1)
        self.assertEqual(meta["sources"][0]["name"], "Authoritative")
        self.assertEqual(meta["sources"][0]["lang"], "en")
        self.assertEqual(
            meta["sources"][0]["baseUrl"], "https://authoritative.example"
        )

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
        self.assertEqual(src1["baseUrlMode"], "mirrors")
        self.assertEqual(src1["defaultBaseUrl"], "https://cn.baozimh.com")
        self.assertTrue(src1["baseUrlResolved"])
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

    def test_custom_base_url(self):
        content = """
        source {
            name = "Custom"
            lang = "en"
            baseUrl {
                custom("https://custom.example")
            }
        }
        """
        source = parse_gradle_metadata(self.write_temp_file(content))["sources"][0]
        self.assertEqual(source["baseUrlMode"], "custom")
        self.assertEqual(source["defaultBaseUrl"], "https://custom.example")
        self.assertTrue(source["baseUrlResolved"])
        self.assertTrue(source["customBaseUrl"])

    def test_dynamic_base_url_is_reported_unresolved(self):
        content = """
        keiyoushi {
            name = "Dynamic"
            versionCode = 1
            libVersion = "1.6"
            contentWarning = ContentWarning.SAFE
            source {
                lang = "en"
                baseUrl = "https://$host"
            }
        }
        """
        source = parse_gradle_metadata(self.write_temp_file(content))["sources"][0]
        self.assertEqual(source["baseUrlMode"], "static")
        self.assertFalse(source["baseUrlResolved"])
        self.assertIsNone(source["defaultBaseUrl"])
        self.assertIn("baseUrl", source["unresolved"])

    def test_generated_source_id_matches_authoritative_unicode_fixture(self):
        content = """
        keiyoushi {
            name = "Manhuashe"
            versionCode = 1
            libVersion = "1.6"
            contentWarning = ContentWarning.MIXED
            source {
                name = "漫画社"
                lang = "zh"
                baseUrl = "https://www.311s.com"
            }
        }
        """
        source = parse_gradle_metadata(self.write_temp_file(content))["sources"][0]
        self.assertEqual(source["sourceId"], "6230622879116184108")

    def test_literal_source_template_expands_and_claims_only_matching_conditional_id(self):
        content = """
        keiyoushi {
            name = "Template"
            versionCode = 1
            libVersion = "1.4"
            contentWarning = ContentWarning.SAFE
            listOf("en", "fr").forEach { langCode ->
                source {
                    lang = langCode
                    baseUrl = "https://template.example"
                    when (langCode) {
                        "fr" -> id = 9000000000000000000L
                    }
                }
            }
        }
        """
        sources = parse_gradle_metadata(self.write_temp_file(content))["sources"]
        self.assertEqual([source["lang"] for source in sources], ["en", "fr"])
        self.assertEqual(sources[0]["sourceIdKind"], "generated")
        self.assertEqual(sources[1]["sourceId"], "9000000000000000000")
        self.assertEqual(sources[1]["sourceIdKind"], "explicit")

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
