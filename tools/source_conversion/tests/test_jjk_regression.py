import os
import sys
import json
import shutil
import subprocess
import unittest
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]

class TestJjkRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.final_js_path = repo_root / "readjujutsukaisenmangaonline.js"
        if not cls.final_js_path.exists():
            raise unittest.SkipTest("readjujutsukaisenmangaonline.js not found")

    def run_parser(self, mock_images, html='<div class="js-pages-container"></div>', fallback_images=[]):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for regression")

        harness = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
globalThis.ComicSource = class ComicSource {};
globalThis.HtmlDocument = class HtmlDocument {
    constructor(html) {
        this.html = html;
    }
    querySelector(sel) {
        if (sel === "div.js-pages-container" && this.html.includes("js-pages-container")) {
            return {
                querySelectorAll: (q) => {
                    if (q === "img.js-page") {
                        return input.mockImages;
                    }
                    return [];
                }
            };
        }
        return null;
    }
    dispose() {}
};
globalThis.Network = class Network {};

const sourcePath = process.argv[1];
const code = fs.readFileSync(sourcePath, "utf8") +
    "\n;globalThis.__Source = EnReadjujutsukaisenmangaonlineSource;";
vm.runInThisContext(code, { filename: sourcePath });
const source = new globalThis.__Source();
process.stdout.write(JSON.stringify(source.parsePagesCustom(input.fallbackImages, input.html)));
"""
        result = subprocess.run(
            [node, "-e", harness, str(self.final_js_path)],
            input=json.dumps(
                {"html": html, "mockImages": mock_images, "fallbackImages": fallback_images}
            ),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_case1_page1(self):
        # src = real HTTPS image, data-src absent
        mock_images = [
            {"attributes": {"src": "https://cdn.readjujutsukaisen.com/1.jpeg"}}
        ]
        res = self.run_parser(mock_images)
        self.assertEqual(res, ["https://cdn.readjujutsukaisen.com/1.jpeg"])

    def test_case2_lazy_page(self):
        # src = placeholder, data-src = real HTTPS image
        mock_images = [
            {"attributes": {"src": "data:image/gif;base64,R0lGODlhAQ...", "data-src": "https://cdn.readjujutsukaisen.com/2.jpeg"}}
        ]
        res = self.run_parser(mock_images)
        self.assertEqual(res, ["https://cdn.readjujutsukaisen.com/2.jpeg"])

    def test_case3_noscript_duplicate(self):
        # Page 2 has a lazy-load image and a noscript fallback image
        mock_images = [
            {"attributes": {"src": "data:image/gif...", "data-src": "https://cdn.readjujutsukaisen.com/2.jpeg"}},
            {"attributes": {"src": "https://cdn.readjujutsukaisen.com/2.jpeg"}}
        ]
        res = self.run_parser(mock_images)
        # Deduplication must leave exactly one
        self.assertEqual(res, ["https://cdn.readjujutsukaisen.com/2.jpeg"])

    def test_case4_unrelated_image(self):
        # Unrelated images (like ads/logos outside reader container) are excluded because our mock matches img.js-page inside div.js-pages-container.
        # Here we just ensure data URI placeholders aren't emitted.
        mock_images = [
            {"attributes": {"src": "data:image/gif;base64,123"}}
        ]
        res = self.run_parser(mock_images)
        self.assertEqual(res, [])

    def test_case5_ordering(self):
        # Page 1, page 2 lazy, page 2 noscript, page 3 lazy
        mock_images = [
            {"attributes": {"src": "https://cdn.readjujutsukaisen.com/1.jpeg"}},
            {"attributes": {"src": "data:image...", "data-src": "https://cdn.readjujutsukaisen.com/2.jpeg"}},
            {"attributes": {"src": "https://cdn.readjujutsukaisen.com/2.jpeg"}},
            {"attributes": {"src": "data:image...", "data-src": "https://cdn.readjujutsukaisen.com/3.jpeg"}},
            {"attributes": {"src": "https://cdn.readjujutsukaisen.com/3.jpeg"}},
        ]
        res = self.run_parser(mock_images)
        self.assertEqual(res, [
            "https://cdn.readjujutsukaisen.com/1.jpeg",
            "https://cdn.readjujutsukaisen.com/2.jpeg",
            "https://cdn.readjujutsukaisen.com/3.jpeg",
        ])

    def test_case6_url_header_compatibility(self):
        # verify relative URLs are resolved (using baseUrl)
        mock_images = [
            {"attributes": {"src": "/relative/path.jpeg"}}
        ]
        res = self.run_parser(mock_images)
        self.assertEqual(res, ["https://ww6.readjujutsukaisen.com/relative/path.jpeg"])

if __name__ == "__main__":
    unittest.main()
