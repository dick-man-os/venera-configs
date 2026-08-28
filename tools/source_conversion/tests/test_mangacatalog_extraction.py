import os
import sys
import unittest
from unittest import mock

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.dirname(current_dir)
extractor_dir = os.path.join(tools_dir, "extractor")
validator_dir = os.path.join(tools_dir, "validator")
generator_dir = os.path.join(tools_dir, "generator")
schema_dir = os.path.join(tools_dir, "schema")

sys.path.insert(0, extractor_dir)
sys.path.insert(0, validator_dir)
sys.path.insert(0, generator_dir)

import extract
from source_adapters import mangacatalog
import js_generator

# We use the built-in validator which corresponds to the schema rules
from validate_ir import validate_ir_data

class TestMangaCatalogExtraction(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.gradle_meta = {
            "name": "Synthetic Manga",
            "versionCode": 2,
            "libVersion": "1.4",
            "versionResolution": "resolved",
            "version": "1.4.2",
            "contentWarning": "SAFE",
            "theme": "mangacatalog",
            "sources": [
                {
                    "lang": "en",
                    "baseUrl": "https://synthetic.com",
                    "sourceId": "12345"
                }
            ]
        }

    def validate_schema(self, ir):
        # We simulate schema validation using the python validator validate_ir_data
        errors = validate_ir_data(ir)
        if errors:
            return False, "\n".join(errors)
        return True, None

    def test_plain_list_preserves_order_and_duplicates(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zebra", "$baseUrl/manga/zebra/"),
                Pair("Apple", "$baseUrl/manga/apple/"),
                Pair("Zebra", "$baseUrl/manga/zebra/")
            )
        }
        """

        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            ir_data = mangacatalog.extract(
                "/dummy/path",
                "en/synthetic",
                gradle_meta=self.gradle_meta,
                timestamp="2026-08-27T00:00:00Z"
            )

            self.assertEqual(ir_data["staticCatalog"], [
                {"title": "Zebra", "url": "https://synthetic.com/manga/zebra/"},
                {"title": "Apple", "url": "https://synthetic.com/manga/apple/"},
                {"title": "Zebra", "url": "https://synthetic.com/manga/zebra/"}
            ])



    def test_sortedby_distinctby_is_reproduced(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zulu", "$baseUrl/manga/shared/"),
                Pair("Apple", "$baseUrl/manga/apple/"),
                Pair("Alpha", "$baseUrl/manga/shared/")
            ).sortedBy { it.first }.distinctBy { it.second }
        }
        """

        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            ir_data = mangacatalog.extract(
                "/dummy/path",
                "en/synthetic",
                gradle_meta=self.gradle_meta,
                timestamp="2026-08-27T00:00:00Z"
            )

            self.assertEqual(ir_data["staticCatalog"], [
                {"title": "Alpha", "url": "https://synthetic.com/manga/shared/"},
                {"title": "Apple", "url": "https://synthetic.com/manga/apple/"}
            ])

    def test_manga_details_parse_override_rejected(self):
        kt_content = """
        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Apple", "$baseUrl/manga/apple/")
            )
            override fun mangaDetailsParse(response: Response): SManga {
                return SManga.create()
            }
        }
        """
        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            with self.assertRaises(ValueError) as context:
                mangacatalog.extract("/dummy/path", "en/synthetic", gradle_meta=self.gradle_meta)

            self.assertIn("unsupported overrides", str(context.exception))

    def test_unknown_behavioral_override_rejected(self):
        kt_content = """
        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Apple", "$baseUrl/manga/apple/")
            )
            override fun pageListParse(response: Response): List<Page> {
                return emptyList()
            }
        }
        """
        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            with self.assertRaises(ValueError) as context:
                mangacatalog.extract("/dummy/path", "en/synthetic", gradle_meta=self.gradle_meta)

            self.assertIn("unsupported overrides", str(context.exception))



    def test_schema_validates_static_catalog(self):
        import jsonschema
        import json
        with open(os.path.join(schema_dir, "ir_v0_2.schema.json"), "r", encoding="utf-8") as f:
            schema = json.load(f)

        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)

        base_ir = {
            "schemaVersion": "0.2",
            "id": "en_test",
            "name": "Test",
            "languages": ["en"],
            "baseUrl": "https://test.com",
            "contentOrigins": ["KR"],
            "sourceType": "hybrid",
            "contentWarning": "SAFE",
            "details": {"url": "a", "method": "GET", "selector": "a"},
            "chapters": {"url": "a", "method": "GET", "selector": "a"},
            "pages": {"url": "a", "method": "GET", "selector": "a"},
            "explore": {"pop": {"url": "a", "method": "GET", "selector": "a"}},
            "search": {"url": "a", "method": "GET", "selector": "a"},
            "provenance": {
                "type": "converted",
                "upstreamProject": "p",
                "upstreamPackage": "p",
                "upstreamCommit": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                "upstreamVersion": "1",
                "upstreamLicense": "MIT",
                "converterVersion": "1",
                "generatedTimestamp": "2024-01-01T00:00:00Z"
            }
        }

        # 1. valid static configuration passes
        valid_static = {**base_ir, "staticCatalog": [{"title": "A", "url": "a"}], "search": {"useStaticCatalog": True}, "explore": {"pop": {"useStaticCatalog": True}}}
        validator.validate(valid_static)

        # 2. useStaticCatalog=true without staticCatalog fails
        static_no_cat = {**base_ir, "search": {"useStaticCatalog": True}}
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            validator.validate(static_no_cat)

        # 3. ordinary HTTP configuration passes
        validator.validate(base_ir)

        # 4. useStaticCatalog absent stays on HTTP semantics; malformed HTTP fails
        http_malformed = {**base_ir, "search": {"selector": "a"}}
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            validator.validate(http_malformed)

        # 5. mixed Explore containing a static tab without root staticCatalog fails
        mixed_explore_no_cat = {**base_ir, "explore": {"pop": {"useStaticCatalog": True}, "latest": {"url": "a", "method": "GET", "selector": "a"}}}
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            validator.validate(mixed_explore_no_cat)

        # 6. static Search containing forbidden network fields fails
        static_search_forbidden = {**base_ir, "staticCatalog": [{"title": "A", "url": "a"}], "search": {"useStaticCatalog": True, "url": "a"}}
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            validator.validate(static_search_forbidden)

    def test_generator_static_catalog_semantics(self):
        import quickjs
        ir = {
            "schemaVersion": "0.2",
            "id": "en_synthetic",
            "name": "Synthetic Manga",
            "languages": ["en"],
            "baseUrl": "https://synthetic.com",
            "staticCatalog": [
                {"title": "Zebra", "url": "https://synthetic.com/manga/shared/"},
                {"title": "Apple", "url": "https://synthetic.com/manga/apple/"},
                {"title": "Zed", "url": "https://synthetic.com/manga/shared/"}
            ],
            "explore": {
                "popular": {
                    "useStaticCatalog": True
                }
            },
            "search": {
                "useStaticCatalog": True
            },
            "details": {"url": "a", "method": "GET", "selector": "a"},
            "chapters": {"url": "a", "method": "GET", "selector": "a"},
            "pages": {"url": "a", "method": "GET", "selector": "a"},
            "provenance": {
                "type": "converted",
                "upstreamProject": "p",
                "upstreamPackage": "p",
                "upstreamCommit": "a1b2c3d",
                "upstreamVersion": "1",
                "upstreamLicense": "MIT",
                "converterVersion": "1",
                "generatedTimestamp": "T"
            }
        }

        js_code = js_generator.generate_venera_js(ir)

        stub_code = """
        class ComicSource { constructor() {} }
        class Comic { constructor(data) { Object.assign(this, data); } }
        class Request { constructor(url, options) { this.url = url; this.options = options; } }
        class Cookie {}
        const Network = {
            get: (url) => { throw new Error("NETWORK_INVOKED"); },
            setCookies: () => {}
        };
        """

        full_code = stub_code + "\n" + js_code + """
        const source = new EnSyntheticSource();

        function assertExplore() {
            if (source.explore.length !== 1) throw new Error("Latest is not absent/unsupported");
            if (source.explore[0].title !== "Popular") throw new Error("Expected Popular");

            return source.explore[0].load(1).then(pop => {
                if (pop.hasMore !== false) throw new Error("hasMore is not false");
                const titles = pop.comics.map(c => c.title);
                if (titles.join(",") !== "Zebra,Apple,Zed") throw new Error("Order or duplicates not preserved: " + titles);
            });
        }

        function assertSearch() {
            // search for 'e' - matches Zebra, Apple, Zed
            return source.search.load("E", {}, 1).then(search1 => {
                if (search1.hasMore !== false) throw new Error("hasMore is not false");
                const titles1 = search1.comics.map(c => c.title);
                if (titles1.join(",") !== "Zebra,Apple,Zed") throw new Error("Case insensitive multi-match or relative order failed: " + titles1);

                // search for 'a' - matches Zebra, Apple
                return source.search.load("a", {}, 1);
            }).then(search2 => {
                if (search2.hasMore !== false) throw new Error("hasMore is not false");
                const titles2 = search2.comics.map(c => c.title);
                if (titles2.join(",") !== "Zebra,Apple") throw new Error("Case insensitive title match or order failed: " + titles2);

                // Ensure URL is not searched
                return source.search.load("https://synthetic", {}, 1);
            }).then(search3 => {
                if (search3.comics.length !== 0) throw new Error("URL was searched inappropriately");
            });
        }

        let p1 = assertExplore();
        let p2 = assertSearch();
        Promise.all([p1, p2]).then(() => {
            done();
        }).catch(err => {
            fail(err.message);
        });
        """

        ctx = quickjs.Context()

        done_called = False
        fail_msg = None

        def js_done():
            nonlocal done_called
            done_called = True

        def js_fail(msg):
            nonlocal fail_msg
            fail_msg = msg

        ctx.add_callable("done", js_done)
        ctx.add_callable("fail", js_fail)

        ctx.eval(full_code)

        while ctx.execute_pending_job():
            pass

        if fail_msg:
            self.fail(fail_msg)
        self.assertTrue(done_called, "The assertions did not complete.")

    def test_canonical_identity_derivation(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zebra", "$baseUrl/manga/zebra/")
            )
        }
        """

        cases = [
            ("en/readblackclovermangaonline", "Read Black Clover Manga Online", "en_readblackclovermangaonline"),
            ("en/readfairytailedenszeromangaonline", "Read Fairy Tail & Edens Zero Manga Online", "en_readfairytailedenszeromangaonline"),
            ("en/readjujutsukaisenmangaonline", "Read Jujutsu Kaisen Manga Online", "en_readjujutsukaisenmangaonline"),
            ("en/readkingdommangaonline", "Read Kingdom Manga Online", "en_readkingdommangaonline"),
            ("en/readnanatsunotaizai7deadlysinsmangaonline", "Read Nanatsu no Taizai 7 Deadly Sins Manga Online", "en_readnanatsunotaizai7deadlysinsmangaonline"),
            ("en/readonepiecemangaonline", "Read One Piece Manga Online", "en_readonepiecemangaonline"),
            ("en/readsololevelingmangamanhwaonline", "Read Solo Leveling Manga Manhwa Online", "en_readsololevelingmangamanhwaonline"),
            ("en/readtokyoghoulretokyoghoulmangaonline", "Read Tokyo Ghoul Re & Tokyo Ghoul Manga Online", "en_readtokyoghoulretokyoghoulmangaonline")
        ]

        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            for source_path, display_name, expected_id in cases:
                gradle_meta = {
                    "name": display_name,
                    "versionCode": 1,
                    "libVersion": "1.4",
                    "versionResolution": "resolved",
                    "version": "1.4.1",
                    "contentWarning": "SAFE",
                    "theme": "mangacatalog",
                    "sources": [
                        {
                            "lang": "en",
                            "baseUrl": "https://synthetic.com",
                            "sourceId": "12345"
                        }
                    ]
                }

                ir_data = mangacatalog.extract(
                    "/dummy/path",
                    source_path,
                    gradle_meta=gradle_meta,
                    timestamp="2026-08-27T00:00:00Z"
                )

                self.assertEqual(ir_data["id"], expected_id, f"Failed for {source_path}")


    def test_invalid_canonical_identity_rejected(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zebra", "$baseUrl/manga/zebra/")
            )
        }
        """

        bad_cases = [
            "../evil",
            "en/../evil",
            "en/foo/bar",
            "/en/foo",
            "C:\\evil\\foo",
            "en/Foo",
            "en/foo-bar",
            "en/foo&bar",
            "en/foo bar",
            "en//foo"
        ]

        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            for bad_path in bad_cases:
                with self.assertRaises(ValueError, msg=f"Failed to reject: {bad_path}"):
                    mangacatalog.extract(
                        "/dummy/path",
                        bad_path,
                        gradle_meta=self.gradle_meta,
                        timestamp="2026-08-27T00:00:00Z"
                    )

    def test_grammar_and_js_generation(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zebra", "/manga/zebra/")
            )
        }
        """

        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            ir_data = mangacatalog.extract(
                "/dummy/path",
                "en/synthetic",
                gradle_meta=self.gradle_meta,
                timestamp="2026-08-27T00:00:00Z"
            )

            # 1. & 2. & 3. Prove IR extraction produces valid grammar
            thumbnail = ir_data["details"]["fields"]["thumbnail"]
            chapter_url = ir_data["chapters"]["fields"]["url"]
            image_url = ir_data["pages"]["fields"]["imageUrl"]

            # Must NOT use thumbnailUrl contract
            self.assertNotIn("thumbnailUrl", ir_data["details"]["fields"])

            self.assertEqual(thumbnail, "div.flex > img@abs:src")
            self.assertEqual(chapter_url, ".col-span-4 > a@abs:href")
            self.assertEqual(image_url, "@abs:data-src")

            # 4. Feed through generator
            js_code = js_generator.generate_venera_js(ir_data)

            # 5. Must NOT contain malformed expressions
            self.assertNotIn("attributes['.col-span-4 > a@abs:href']", js_code)
            self.assertNotIn("attributes['div.flex > img@abs:src']", js_code)
            self.assertNotIn("attributes['@abs:data-src']", js_code)

            # 6. Positively prove semantic behavior uses generator's canonical selector + attribute

            # Cover generated assertion
            cover_fragment = "let cover = (doc.querySelector('div.flex > img') ? (doc.querySelector('div.flex > img').attributes['abs:src'] || '') : '');"
            self.assertIn(cover_fragment, js_code)
            self.assertNotIn(".detail_header .thmb img", js_code)

            # Chapter generated assertion
            chapter_fragment = "id: (el.querySelector('.col-span-4 > a') ? (el.querySelector('.col-span-4 > a').attributes['abs:href'] || '') : ''),"
            self.assertIn(chapter_fragment, js_code)

            # Page generated assertion
            page_fragment = 'let images = imgElements.map(el => el.attributes["abs:data-src"]).filter(Boolean);'
            self.assertIn(page_fragment, js_code)

    def test_resolved_version_extracted_exactly(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zebra", "/manga/zebra/")
            )
        }
        """
        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            gradle_meta = {**self.gradle_meta, "versionResolution": "resolved", "version": "1.4.12"}

            ir_data = mangacatalog.extract(
                "/dummy/path",
                "en/synthetic",
                gradle_meta=gradle_meta,
                timestamp="2026-08-27T00:00:00Z"
            )

            self.assertEqual(ir_data["provenance"]["upstreamVersion"], "1.4.12")

    def test_lower_level_version_code_ignored(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zebra", "/manga/zebra/")
            )
        }
        """
        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            gradle_meta = {
                **self.gradle_meta,
                "versionResolution": "resolved",
                "version": "1.4.15", # Authoritative
                "libVersion": "1.2", # Should be ignored
                "versionCode": 3     # Should be ignored
            }

            ir_data = mangacatalog.extract(
                "/dummy/path",
                "en/synthetic",
                gradle_meta=gradle_meta,
                timestamp="2026-08-27T00:00:00Z"
            )

            self.assertEqual(ir_data["provenance"]["upstreamVersion"], "1.4.15")
            self.assertNotEqual(ir_data["provenance"]["upstreamVersion"], "1.2.3")

    def test_fails_closed_on_invalid_version_metadata(self):
        kt_content = """
        package eu.kanade.tachiyomi.extension.en.synthetic
        import eu.kanade.tachiyomi.multisrc.mangacatalog.MangaCatalog

        class SyntheticManga : MangaCatalog() {
            override val sourceList = listOf(
                Pair("Zebra", "/manga/zebra/")
            )
        }
        """
        with mock.patch('os.walk') as mock_walk, \
             mock.patch('os.path.exists', return_value=True), \
             mock.patch('builtins.open', mock.mock_open(read_data=kt_content)), \
             mock.patch('source_adapters.mangacatalog._get_git_commit', return_value="abcdef"), \
             mock.patch('source_adapters.mangacatalog._get_upstream_license', return_value="MIT"):

            mock_walk.return_value = [("/src", [], ["SyntheticManga.kt"])]

            cases = [
                # missing versionResolution
                {**self.gradle_meta, "versionResolution": None, "version": "1.4.1"},
                # unresolved versionResolution
                {**self.gradle_meta, "versionResolution": "unresolved", "version": "1.4.1"},
                # missing version
                {**self.gradle_meta, "versionResolution": "resolved", "version": None},
                # empty-string version
                {**self.gradle_meta, "versionResolution": "resolved", "version": "   "},
                # non-string version
                {**self.gradle_meta, "versionResolution": "resolved", "version": 123},
            ]

            # Remove keys where None means missing entirely to test that as well
            missing_resolution = self.gradle_meta.copy()
            if "versionResolution" in missing_resolution:
                del missing_resolution["versionResolution"]
            cases.append(missing_resolution)

            missing_version = {**self.gradle_meta, "versionResolution": "resolved"}
            if "version" in missing_version:
                del missing_version["version"]
            cases.append(missing_version)

            for i, bad_meta in enumerate(cases):
                with self.subTest(i=i, meta=bad_meta):
                    with self.assertRaises(ValueError):
                        mangacatalog.extract(
                            "/dummy/path",
                            "en/synthetic",
                            gradle_meta=bad_meta,
                            timestamp="2026-08-27T00:00:00Z"
                        )

if __name__ == '__main__':
    unittest.main()
