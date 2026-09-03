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

    def run_image_config(self, url, comic_id="comic", ep_id="chapter"):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for regression")

        harness = r"""
const fs = require("fs");
const vm = require("vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
globalThis.ComicSource = class ComicSource {};
globalThis.HtmlDocument = class HtmlDocument {};
globalThis.Network = class Network {};

const sourcePath = process.argv[1];
const code = fs.readFileSync(sourcePath, "utf8") +
    "\n;globalThis.__Source = EnReadjujutsukaisenmangaonlineSource;";
vm.runInThisContext(code, { filename: sourcePath });
const source = new globalThis.__Source();
process.stdout.write(JSON.stringify(
    source.comic.onImageLoad(input.url, input.comicId, input.epId)
));
"""
        result = subprocess.run(
            [node, "-e", harness, str(self.final_js_path)],
            input=json.dumps({"url": url, "comicId": comic_id, "epId": ep_id}),
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

    def test_live_chapter_shapes_preserve_first_middle_last(self):
        fixtures = {
            "272.5": ([
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10271500/0197848f-614d-7deb-9012-fc1f1554165b/1.jpeg",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10271500/0197848f-614d-7deb-9012-fc1f1554165b/12.jpeg",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10271500/0197848f-614d-7deb-9012-fc1f1554165b/22.jpeg",
            ], True),
            "271": ([
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10271000/1.jpeg?t=1727680641",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10271000/11.jpeg?t=1727680641",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10271000/21.jpeg?t=1727680641",
            ], True),
            "111": ([
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10111000/1.jpeg",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10111000/11.jpeg",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10111000/21.jpeg",
            ], False),
            "0.1": ([
                "https://cdn.readjujutsukaisen.com/file/mangap/5162/10001000/1.jpeg",
                "https://cdn.readjujutsukaisen.com/file/mangap/5162/10001000/30.jpeg",
                "https://cdn.readjujutsukaisen.com/file/mangap/5162/10001000/58.jpeg",
            ], False),
            "1": ([
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10001000/1.jpeg?t=1660901592",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10001000/30.jpeg?t=1660901592",
                "https://cdn.readjujutsukaisen.com/file/mangap/2085/10001000/58.jpeg?t=1660901592",
            ], False),
        }

        for chapter, (urls, has_trailing_cr) in fixtures.items():
            with self.subTest(chapter=chapter):
                trailing_cr = "\r" if has_trailing_cr else ""
                mock_images = [
                    {"attributes": {"src": urls[0] + trailing_cr}},
                    {
                        "attributes": {
                            "src": "data:image/gif;base64,R0lGODlhAQ...",
                            "data-src": urls[1] + trailing_cr,
                        }
                    },
                    {
                        "attributes": {
                            "src": "data:image/gif;base64,R0lGODlhAQ...",
                            "data-src": urls[2],
                        }
                    },
                ]
                self.assertEqual(self.run_parser(mock_images), urls)

    def test_whitespace_is_removed_before_deduplication(self):
        clean = "https://cdn.readjujutsukaisen.com/file/mangap/2085/10271500/0197848f-614d-7deb-9012-fc1f1554165b/12.jpeg"
        mock_images = [
            {
                "attributes": {
                    "src": "data:image/gif;base64,R0lGODlhAQ...",
                    "data-src": clean + "\r",
                }
            },
            {"attributes": {"src": clean}},
        ]
        self.assertEqual(self.run_parser(mock_images), [clean])

    def test_image_hook_preserves_url_and_base_referer(self):
        url = "https://cdn.readjujutsukaisen.com/file/mangap/2085/10111000/1.jpeg"
        self.assertEqual(
            self.run_image_config(url),
            {
                "url": url,
                "headers": {"Referer": "https://ww6.readjujutsukaisen.com/"},
            },
        )

    def test_case7_load_chapters(self):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for regression")

        harness = r"""
const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

globalThis.ComicSource = class ComicSource {};
globalThis.HtmlDocument = class HtmlDocument {
    constructor(html) {
        this.html = html;
    }
    querySelectorAll(sel) {
        if (sel === 'div.w-full > div.bg-bg-secondary > div.grid') {
            return input.mockElements.map(el => ({
                querySelector: (q) => {
                    if (q === '.col-span-4 > a') {
                        return {
                            attributes: { 'href': el.url },
                            text: el.title
                        };
                    }
                    return null;
                }
            }));
        }
        return [];
    }
    dispose() {}
};
globalThis.Network = class Network {
    static async get(url, headers) {
        return { status: 200, body: '<html></html>' };
    }
};

const sourcePath = process.argv[1];
const code = fs.readFileSync(sourcePath, 'utf8') + '\n;globalThis.__Source = EnReadjujutsukaisenmangaonlineSource;';
vm.runInThisContext(code, { filename: sourcePath });
const source = new globalThis.__Source();

source.loadChapters('https://example.com/').then(chapters => {
    process.stdout.write(JSON.stringify(chapters));
}).catch(err => {
    console.error(err);
    process.exit(1);
});
"""

        mock_elements = [
            {'url': '/manga/jujutsu-kaisen-0/chapter-1/', 'title': 'Chapter 1'},
            {'url': '/manga/jujutsu-kaisen-0/chapter-2/', 'title': 'Chapter 2'}
        ]

        import subprocess
        result = subprocess.run(
            [node, "-e", harness, str(self.final_js_path)],
            input=json.dumps({"mockElements": mock_elements}),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        res = json.loads(result.stdout)
        self.assertEqual(res, {
            "https://example.com/manga/jujutsu-kaisen-0/chapter-1/": "Chapter 1",
            "https://example.com/manga/jujutsu-kaisen-0/chapter-2/": "Chapter 2"
        })

if __name__ == "__main__":

    unittest.main()
