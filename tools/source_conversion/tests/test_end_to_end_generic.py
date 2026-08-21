#!/usr/bin/env python3
import os
import subprocess
import json
import unittest
import tempfile
import sys
import importlib.util

# Ensure test_ladder is importable
current_dir = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.dirname(current_dir)
spec = importlib.util.spec_from_file_location("ladder", os.path.join(tools_dir, "test_ladder.py"))
ladder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ladder)

class TestEndToEndGeneric(unittest.TestCase):
    def setUp(self):
        self.venera_configs_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _create_fixture(self, tmpdir_path, is_safe=True):
        ext_root = os.path.join(tmpdir_path, "extensions-source")
        src_dir = os.path.join(ext_root, "src", "en", "generic-safe")
        src_main_dir = os.path.join(src_dir, "src", "eu", "kanade", "tachiyomi", "extension", "en", "genericsafe")
        os.makedirs(src_main_dir, exist_ok=True)

        gradle_kts = """
keiyoushi {
    name = "Generic Extension"
    versionCode = 4
    libVersion = "1.6"
    contentWarning = ContentWarning.SAFE
    source {
        name = "GenericSafe"
        lang = "en"
        id = 123456789L
        baseUrl { mirrors("https://genericsafe.com") }
    }
}
"""

        details_selector = 'document.selectFirst("div.unsupported:contains(author)")' if not is_safe else 'document.selectFirst("div.author")!!.text()'

        kt_source = f"""
package eu.kanade.tachiyomi.extension.en.genericsafe

import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.KeiSource
import org.jsoup.nodes.Document

class GenericSafe : KeiSource() {{
    override val baseUrl = "https://genericsafe.com"

    override suspend fun getPopularManga(page: Int): MangasPage {{
        val response = client.get("$baseUrl/popular/$page")
        val document = response.asJsoup()
        return parseManga(document)
    }}

    private fun parseManga(document: Document): MangasPage {{
        val mangas = document.select("div.comic-list > div.comic-item").map {{ element ->
            SManga.create().apply {{
                title = element.selectFirst("h3 a")!!.text()
                setUrlWithoutDomain(element.selectFirst("a")!!.absUrl("href"))
                thumbnail_url = element.selectFirst("img")!!.attr("src")
            }}
        }}
        val nextPage = document.selectFirst("div.pagination > a.next")!!.attr("href")
        val currentPage = document.selectFirst("div.pagination > a.on")!!.attr("href")
        return MangasPage(mangas, nextPage != currentPage)
    }}

    override suspend fun getLatestUpdates(page: Int): MangasPage {{
        val response = client.get("$baseUrl/latest/$page")
        val document = response.asJsoup()
        return parseManga(document)
    }}

    override suspend fun getSearchMangaList(page: Int, query: String): MangasPage {{
        val response = client.get("$baseUrl/search/$query/$page")
        val document = response.asJsoup()
        return parseManga(document)
    }}

    override suspend fun fetchMangaUpdate(document: Document): String {{
        title = document.selectFirst("h1")!!.text()
        thumbnail_url = document.selectFirst("img")!!.attr("src")
        description = document.selectFirst("p")!!.text()
        author = {details_selector}

        val chapters = document.select("div.chapter-list li a").map {{ element ->
            SChapter.create().apply {{
                name = element.text()
                setUrlWithoutDomain(element.attr("href"))
            }}
        }}.asReversed()
        return chapters
    }}

    override suspend fun getPageList(document: Document): List<Page> {{
        return document.select("div.comic-content > img").mapIndexed {{ index, it ->
            Page(index, imageUrl = it.attr("src"))
        }}
    }}
}}
"""
        with open(os.path.join(src_dir, "build.gradle.kts"), "w", encoding="utf-8") as f:
            f.write(gradle_kts)
        with open(os.path.join(src_main_dir, "GenericSafe.kt"), "w", encoding="utf-8") as f:
            f.write(kt_source)

        # Init git so upstreamCommit works
        subprocess.run(["git", "init"], cwd=ext_root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=ext_root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=ext_root, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=ext_root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=ext_root, capture_output=True)

        return ext_root

    def _create_patch(self, tmpdir_path):
        patch_file = os.path.join(tmpdir_path, "patch.js")
        patch_content = """
    parseDetailsCustom = (comicDetails, htmlDoc) => {
        comicDetails.subtitle = "Patched Author";
        return comicDetails;
    }
"""
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(patch_content)
        return patch_file

    def test_safe_pipeline_generic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_root = self._create_fixture(tmpdir, is_safe=True)

            config = ladder.LadderConfig(
                source="en/generic-safe",
                mode="new",
                extensions_root=ext_root
            )

            res = ladder.run_ladder(config, override_temp_dir=tmpdir)
            if res.overall_status != "PASS":
                print([(s.level, s.status, s.message) for s in res.stages])
            self.assertEqual(res.overall_status, "PASS")

            statuses = {s.level: s.status for s in res.stages}
            self.assertEqual(statuses["L0"], "PASS")
            self.assertEqual(statuses["L1"], "PASS")
            self.assertEqual(statuses["L2"], "PASS")
            self.assertEqual(statuses["L3"], "PASS")
            self.assertEqual(statuses["L4"], "PASS")
            self.assertEqual(statuses["L5"], "PASS")
            self.assertEqual(statuses["L6"], "NOT_APPLICABLE")

    def test_partial_patch_pipeline_generic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_root = self._create_fixture(tmpdir, is_safe=False)
            patch_file = self._create_patch(tmpdir)

            config = ladder.LadderConfig(
                source="en/generic-safe",
                mode="new",
                extensions_root=ext_root,
                patch_path=patch_file
            )

            res = ladder.run_ladder(config, override_temp_dir=tmpdir)

            self.assertEqual(res.overall_status, "PASS")
            statuses = {s.level: s.status for s in res.stages}
            self.assertEqual(statuses["L0"], "PASS")
            self.assertEqual(statuses["L1"], "PASS")
            self.assertEqual(statuses["L2"], "PASS")
            self.assertEqual(statuses["L3"], "PASS")
            self.assertEqual(statuses["L4"], "PASS")
            self.assertEqual(statuses["L5"], "PASS")
            self.assertEqual(statuses["L6"], "NOT_APPLICABLE")

    def test_missing_patch_pipeline_generic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_root = self._create_fixture(tmpdir, is_safe=False)

            config = ladder.LadderConfig(
                source="en/generic-safe",
                mode="new",
                extensions_root=ext_root
            )

            res = ladder.run_ladder(config, override_temp_dir=tmpdir)

            self.assertEqual(res.overall_status, "FAIL")
            statuses = {s.level: s.status for s in res.stages}
            self.assertEqual(statuses["L0"], "PASS")
            self.assertEqual(statuses["L1"], "PASS")
            self.assertEqual(statuses["L2"], "PASS")
            self.assertEqual(statuses["L3"], "PASS")
            self.assertEqual(statuses["L4"], "FAIL")
            self.assertEqual(statuses["L5"], "SKIP")

if __name__ == "__main__":
    unittest.main()
