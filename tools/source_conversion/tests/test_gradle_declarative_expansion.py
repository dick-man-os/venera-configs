import os
import sys
import tempfile
import unittest


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACTOR_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "extractor")
if EXTRACTOR_DIR not in sys.path:
    sys.path.insert(0, EXTRACTOR_DIR)

from common.gradle_parser import (  # noqa: E402
    MAX_STATIC_EXPANSION,
    parse_gradle_metadata,
)


class TestBoundedDeclarativeGradleExpansion(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def parse(self, body, *, name="Extension"):
        path = os.path.join(self.temp_dir.name, "build.gradle.kts")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                f'''keiyoushi {{
    name = "{name}"
    versionCode = 1
    libVersion = "1.6"
    contentWarning = ContentWarning.SAFE
{body}
}}
'''
            )
        return parse_gradle_metadata(path)

    def assert_unresolved_template(self, body):
        sources = self.parse(body)["sources"]
        self.assertEqual(len(sources), 1)
        self.assertIsNone(sources[0]["sourceId"])
        self.assertEqual(sources[0]["sourceIdKind"], "unresolved")
        self.assertIn("staticExpansion", sources[0]["unresolved"])

    def test_inline_literal_list_and_direct_foreach_expand_in_order(self):
        sources = self.parse(
            '''    listOf("fr", "en").forEach { language ->
        source { lang = language; baseUrl = "https://example.com" }
    }'''
        )["sources"]
        self.assertEqual([source["lang"] for source in sources], ["fr", "en"])

    def test_named_immutable_list_binding_expands(self):
        sources = self.parse(
            '''    val languages = listOf("en", "ja")
    languages.forEach {
        source { lang = it; baseUrl = "https://example.com" }
    }'''
        )["sources"]
        self.assertEqual([source["lang"] for source in sources], ["en", "ja"])

    def test_literal_map_expands(self):
        sources = self.parse(
            '''    mapOf("en" to "www", "fr" to "fr").forEach { (lang, sub) ->
        source { lang = lang; baseUrl = "https://$sub.example.com" }
    }'''
        )["sources"]
        self.assertEqual([source["lang"] for source in sources], ["en", "fr"])

    def test_named_map_destructuring_expands(self):
        sources = self.parse(
            '''    val locales = mapOf("en" to "en_us", "ja" to "ja_jp")
    locales.forEach { (langCode, locale) ->
        source {
            lang = langCode
            baseUrl = "https://example.com/$locale/"
        }
    }'''
        )["sources"]
        self.assertEqual(
            [source["baseUrl"] for source in sources],
            ["https://example.com/en_us/", "https://example.com/ja_jp/"],
        )

    def test_loop_binding_can_supply_name_and_raw_lang(self):
        sources = self.parse(
            '''    listOf("all", "other").forEach { value ->
        source { name = value; lang = value; baseUrl = "https://example.com" }
    }'''
        )["sources"]
        self.assertEqual(
            [(source["name"], source["lang"]) for source in sources],
            [("all", "all"), ("other", "other")],
        )

    def test_bounded_string_interpolation_uses_literal_bindings(self):
        source = self.parse(
            '''    val domain = "example.com"
    listOf("en").forEach { lang ->
        source { lang = lang; baseUrl = "https://$lang.$domain" }
    }'''
        )["sources"][0]
        self.assertEqual(source["baseUrl"], "https://en.example.com")

    def test_bounded_string_concatenation_uses_literal_bindings(self):
        source = self.parse(
            '''    val domain = "example.com"
    listOf("en").forEach { lang ->
        source { lang = lang; baseUrl = "https://" + domain + "/" + lang }
    }'''
        )["sources"][0]
        self.assertEqual(source["baseUrl"], "https://example.com/en")

    def test_local_literal_constant_can_supply_direct_source_base_url(self):
        source = self.parse(
            '''    val siteUrl = "https://example.com"
    source { lang = "en"; baseUrl = siteUrl }'''
        )["sources"][0]
        self.assertEqual(source["baseUrl"], "https://example.com")

    def test_fixed_literal_version_id_is_used_for_generated_identity(self):
        source = self.parse(
            '''    listOf("en").forEach {
        source { lang = it; versionId = 2; baseUrl = "https://example.com" }
    }'''
        )["sources"][0]
        self.assertEqual(source["versionId"], 2)
        self.assertEqual(source["effectiveVersionId"], 2)
        self.assertEqual(source["sourceIdKind"], "generated")

    def test_conditional_explicit_id_matching_branch(self):
        source = self.parse(
            '''    listOf("en").forEach { lang ->
        source {
            lang = lang
            baseUrl = "https://example.com"
            if (lang == "en") id = 123L
        }
    }'''
        )["sources"][0]
        self.assertEqual(source["sourceId"], "123")
        self.assertEqual(source["sourceIdKind"], "explicit")

    def test_conditional_explicit_id_nonmatching_branch_uses_auto_id(self):
        source = self.parse(
            '''    listOf("fr").forEach { lang ->
        source {
            lang = lang
            baseUrl = "https://example.com"
            if (lang == "en") id = 123L
        }
    }'''
        )["sources"][0]
        self.assertEqual(source["sourceIdKind"], "generated")
        self.assertNotEqual(source["sourceId"], "123")

    def test_conditional_source_name_changes_candidate_and_auto_id(self):
        sources = self.parse(
            '''    listOf("de", "en").forEach { lang ->
        source {
            lang = lang
            baseUrl = "https://example.com"
            if (lang == "de") name = "Deutscher Name"
        }
    }''',
            name="Default Name",
        )["sources"]
        self.assertEqual([source["name"] for source in sources], ["Deutscher Name", "Default Name"])
        self.assertNotEqual(sources[0]["sourceId"], sources[1]["sourceId"])

    def test_deterministic_when_branch_selects_explicit_id(self):
        sources = self.parse(
            '''    listOf("en", "fr", "ja").forEach { lang ->
        source {
            lang = lang
            baseUrl = "https://example.com"
            when (lang) {
                "en" -> id = 10L
                "fr" -> id = 20L
            }
        }
    }'''
        )["sources"]
        self.assertEqual(
            [source["sourceIdKind"] for source in sources],
            ["explicit", "explicit", "generated"],
        )
        self.assertEqual([source["sourceId"] for source in sources[:2]], ["10", "20"])

    def test_literal_not_equal_branch_can_select_base_url(self):
        source = self.parse(
            '''    listOf("fr").forEach { lang ->
        source {
            lang = lang
            if (lang != "en") baseUrl = "https://fr.example.com"
        }
    }'''
        )["sources"][0]
        self.assertEqual(source["baseUrl"], "https://fr.example.com")
        self.assertTrue(source["baseUrlResolved"])

    def test_auto_id_uses_expanded_final_name_lang_and_version(self):
        expanded = self.parse(
            '''    listOf("en").forEach { lang ->
        source { name = "Final"; lang = lang; versionId = 3; baseUrl = "https://example.com" }
    }'''
        )["sources"][0]
        ordinary = self.parse(
            '''    source { name = "Final"; lang = "en"; versionId = 3; baseUrl = "https://example.com" }'''
        )["sources"][0]
        self.assertEqual(expanded["sourceId"], ordinary["sourceId"])

    def test_mixed_static_and_expanded_sources_are_both_preserved(self):
        sources = self.parse(
            '''    source { name = "Static"; lang = "en"; id = 1L; baseUrl = "https://one.example" }
    listOf("fr", "de").forEach { lang ->
        source { lang = lang; baseUrl = "https://many.example" }
    }'''
        )["sources"]
        self.assertEqual([source["lang"] for source in sources], ["en", "fr", "de"])

    def test_unsupported_item_invalidates_complete_collection(self):
        self.assert_unresolved_template(
            '''    listOf("en", helper()).forEach { lang ->
        source { lang = lang; baseUrl = "https://example.com" }
    }'''
        )

    def test_provider_collection_remains_unresolved(self):
        self.assert_unresolved_template(
            '''    providers.gradleProperty("langs").get().forEach { lang ->
        source { lang = lang; baseUrl = "https://example.com" }
    }'''
        )

    def test_environment_collection_remains_unresolved(self):
        self.assert_unresolved_template(
            '''    System.getenv("LANGS").forEach { lang ->
        source { lang = lang; baseUrl = "https://example.com" }
    }'''
        )

    def test_arbitrary_helper_collection_remains_unresolved(self):
        self.assert_unresolved_template(
            '''    helper().forEach {
        source { lang = "en"; id = 1L; baseUrl = "https://example.com" }
    }'''
        )

    def test_source_nested_in_arbitrary_callback_is_not_reinterpreted_as_static(self):
        self.assert_unresolved_template(
            '''    helper {
        source { lang = "en"; id = 1L; baseUrl = "https://example.com" }
    }'''
        )

    def test_filesystem_collection_remains_unresolved(self):
        self.assert_unresolved_template(
            '''    file("langs.txt").readLines().forEach { lang ->
        source { lang = lang; baseUrl = "https://example.com" }
    }'''
        )

    def test_mutable_collection_binding_remains_unresolved(self):
        self.assert_unresolved_template(
            '''    var languages = listOf("en", "fr")
    languages.forEach { lang ->
        source { lang = lang; baseUrl = "https://example.com" }
    }'''
        )

    def test_collection_filter_remains_unresolved(self):
        self.assert_unresolved_template(
            '''    listOf("en", "fr").filter { it == "en" }.forEach { lang ->
        source { lang = lang; baseUrl = "https://example.com" }
    }'''
        )

    def test_map_transformation_remains_unresolved(self):
        self.assert_unresolved_template(
            '''    mapOf("en" to "www").mapValues { it.value }.forEach { (lang, sub) ->
        source { lang = lang; baseUrl = "https://$sub.example.com" }
    }'''
        )

    def test_unresolved_branch_predicate_invalidates_source(self):
        self.assert_unresolved_template(
            '''    listOf("en").forEach { lang ->
        source {
            lang = lang
            baseUrl = "https://example.com"
            if (lang == helper()) id = 123L
        }
    }'''
        )

    def test_cyclic_local_binding_fails_closed(self):
        self.assert_unresolved_template(
            '''    val first = second
    val second = first
    first.forEach { lang ->
        source { lang = lang; baseUrl = "https://example.com" }
    }'''
        )

    def test_expansion_limit_overflow_fails_closed(self):
        languages = ", ".join(f'"l{index}"' for index in range(MAX_STATIC_EXPANSION + 1))
        with self.assertRaisesRegex(ValueError, "MAX_STATIC_EXPANSION"):
            self.parse(
                f'''    listOf({languages}).forEach {{ lang ->
        source {{ lang = lang; baseUrl = "https://example.com" }}
    }}'''
            )

    def test_simple_static_source_behavior_is_unchanged(self):
        source = self.parse(
            '''    source { name = "Static"; lang = "en"; id = 99L; baseUrl = "https://example.com" }'''
        )["sources"][0]
        self.assertEqual(
            (source["name"], source["lang"], source["sourceId"], source["baseUrl"]),
            ("Static", "en", "99", "https://example.com"),
        )


if __name__ == "__main__":
    unittest.main()
