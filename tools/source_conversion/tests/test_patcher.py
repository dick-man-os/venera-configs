import unittest
from tools.source_conversion.patcher.js_patcher import patch_js

class TestJsPatcher(unittest.TestCase):
    def test_patch_composition_strips_blank_lines(self):
        base = """class Dummy {
    // =========================================================================
    // Patch Hooks / Boundaries
}"""
        patch = """    // =========================================================================
    // Patch Hooks / Boundaries

    someMethod() {
        return 1;
    }

    anotherMethod() {
        return 2;
    }
"""
        # Notice the blank line between methods has 8 spaces.
        composed = patch_js(base, patch)

        # Split into lines to verify
        lines = composed.split('\n')
        for line in lines:
            if line.isspace():
                self.fail(f"Found whitespace-only line: {repr(line)}")

        self.assertIn("someMethod", composed)
        self.assertIn("anotherMethod", composed)

if __name__ == '__main__':
    unittest.main()
