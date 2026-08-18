import os
import sys
import unittest
import tempfile

# Add validator to path
current_dir = os.path.dirname(os.path.abspath(__file__))
validator_dir = os.path.join(os.path.dirname(current_dir), "validator")
sys.path.insert(0, validator_dir)
from static_js_validator import validate_js_file

class TestStaticValidator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_temp_file(self, content):
        path = os.path.join(self.temp_dir.name, "test.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_valid_js(self):
        content = """
        class MySource {
            load() {
                let doc = new HtmlDocument("<html></html>");
                let elements = doc.querySelectorAll("div");
                doc.dispose();
                return elements;
            }
        }
        """
        path = self.write_temp_file(content)
        self.assertTrue(validate_js_file(path))

    def test_unresolved_manual_patch_final(self):
        content = """
        class MySource {
            load() {
                throw new Error("MANUAL_PATCH_REQUIRED: implement me");
            }
        }
        """
        path = self.write_temp_file(content)
        self.assertFalse(validate_js_file(path, phase="final"))

    def test_unresolved_manual_patch_legacy_final(self):
        content = """
        class MySource {
            load() {
                throw new Error("MANUAL PATCH REQUIRED: implement me");
            }
        }
        """
        path = self.write_temp_file(content)
        self.assertFalse(validate_js_file(path, phase="final"))

    def test_unresolved_manual_patch_base(self):
        content = """
        class MySource {
            load() {
                throw new Error("MANUAL PATCH REQUIRED: implement me");
            }
        }
        """
        path = self.write_temp_file(content)
        self.assertTrue(validate_js_file(path, phase="base"))

    def test_unsupported_window(self):
        content = """
        class MySource {
            load() {
                return window.location.href;
            }
        }
        """
        path = self.write_temp_file(content)
        self.assertFalse(validate_js_file(path))

    def test_unsupported_document(self):
        content = """
        class MySource {
            load() {
                return document.querySelector("div");
            }
        }
        """
        path = self.write_temp_file(content)
        self.assertFalse(validate_js_file(path))

    def test_allowed_document_dispose(self):
        content = """
        class MySource {
            load() {
                let doc = new HtmlDocument("");
                doc.dispose();
            }
        }
        """
        path = self.write_temp_file(content)
        self.assertTrue(validate_js_file(path))

    def test_verify_fetch(self):
        content = """
        class MySource {
            async load() {
                let r = await fetch("url");
            }
        }
        """
        path = self.write_temp_file(content)
        # Verify APIs don't fail validation, they just warn
        self.assertTrue(validate_js_file(path))

    # --- Lexical Scanner Recovery Tests ---

    def test_lexical_executable_document_location_fails(self):
        content = 'const x = document.location.href;'
        path = self.write_temp_file(content)
        self.assertFalse(validate_js_file(path))

    def test_lexical_masked_document_location_passes(self):
        content = '''
        const a = "document.location";
        const b = /document\.location/g;
        // document.location
        /* document.location */
        '''
        path = self.write_temp_file(content)
        self.assertTrue(validate_js_file(path))

    def test_lexical_template_raw_text_passes(self):
        content = 'const a = `The value of document.location is hidden`;'
        path = self.write_temp_file(content)
        self.assertTrue(validate_js_file(path))

    def test_lexical_template_interpolation_fails(self):
        content = 'const a = `The value is ${document.location}`;'
        path = self.write_temp_file(content)
        self.assertFalse(validate_js_file(path))

    def test_lexical_division_vs_regex(self):
        content = '''
        const a = 5 / 2;
        const b = /document\.location/g;
        '''
        path = self.write_temp_file(content)
        self.assertTrue(validate_js_file(path))

    def test_lexical_structural_brace_balance_fails(self):
        content_extra = 'class A { load() { } } }'
        path1 = self.write_temp_file(content_extra)
        self.assertFalse(validate_js_file(path1))

        content_missing = 'class A { load() { '
        path2 = self.write_temp_file(content_missing)
        self.assertFalse(validate_js_file(path2))

    def test_lexical_braces_inside_masked_regions(self):
        content = '''
        class A {
            load() {
                const a = "}";
                const b = /{/;
                // }
                /* { */
                const c = `${ { x: 1 }.x }`;
            }
        }
        '''
        path = self.write_temp_file(content)
        self.assertTrue(validate_js_file(path))

if __name__ == "__main__":
    unittest.main()
