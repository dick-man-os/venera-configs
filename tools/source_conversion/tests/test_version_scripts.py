"""Regression coverage for the catalog publication scripts."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class VersionScriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git") and shutil.which("node"), "git and node are required")
    def test_nested_javascript_is_not_treated_as_a_publishable_source(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "scripts").mkdir()
            (repo / "sources_generated").mkdir()
            (repo / "sources_patches").mkdir()
            for name in ("validate-pr-versions.js", "list-changed-configs.js"):
                shutil.copyfile(ROOT / "scripts" / name, repo / "scripts" / name)

            source = repo / "source.js"
            generated = repo / "sources_generated" / "source.base.js"
            patch = repo / "sources_patches" / "source.patch.js"
            source.write_text('class Source {\n  version = "1.0.0";\n}\n', encoding="utf-8")
            generated.write_text('class Generated { version = "1.0.0"; }\n', encoding="utf-8")
            patch.write_text('const patchVersion = "1.0.0";\n', encoding="utf-8")
            (repo / "index.json").write_text(
                json.dumps([{"name": "Source", "fileName": "source.js", "key": "source", "version": "1.0.0"}]),
                encoding="utf-8",
            )
            self.run_git(repo, "init")
            self.run_git(repo, "config", "user.name", "Version Test")
            self.run_git(repo, "config", "user.email", "version-test@example.invalid")
            self.run_git(repo, "add", ".")
            self.run_git(repo, "commit", "-m", "baseline")

            source.write_text('class Source {\n  version = "1.0.1";\n}\n', encoding="utf-8")
            generated.write_text('class Generated { version = "1.0.1"; }\n', encoding="utf-8")
            patch.write_text('const patchVersion = "1.0.1";\n', encoding="utf-8")
            (repo / "index.json").write_text(
                json.dumps([{"name": "Source", "fileName": "source.js", "key": "source", "version": "1.0.1"}]),
                encoding="utf-8",
            )
            self.run_git(repo, "add", ".")
            self.run_git(repo, "commit", "-m", "candidate")

            validation = subprocess.run(
                ["node", "scripts/validate-pr-versions.js", "HEAD^"], cwd=repo,
                text=True, capture_output=True,
            )
            self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)
            self.assertIn("passed for 1 config file", validation.stdout)
            changed = subprocess.run(
                ["node", "scripts/list-changed-configs.js", "HEAD^"], cwd=repo,
                text=True, capture_output=True,
            )
            self.assertEqual(changed.returncode, 0, changed.stdout + changed.stderr)
            self.assertEqual(changed.stdout.splitlines(), ["source.js"])

    @staticmethod
    def run_git(repo, *args):
        subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=repo,
                       text=True, capture_output=True, check=True)


if __name__ == "__main__":
    unittest.main()
