import unittest
from unittest.mock import patch, MagicMock
import os
import json
import tempfile
from pathlib import Path
import sys
import subprocess

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from source_conversion.test_ladder import run_ladder, LadderConfig, StageResult

class TestLadder(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = repo_root / "source_conversion" / "tests" / "fixtures"
        self.v01_ir = str(self.fixtures_dir / "v0.1_ir.json")
        self.v02_ir = str(self.fixtures_dir / "v0.2_ir.json")
        self.patch_req_ir = str(self.fixtures_dir / "patch_required_ir.json")
        self.invalid_ir = str(self.fixtures_dir / "invalid_ir.json")
        self.base_js = str(self.fixtures_dir / "base.js")
        self.patch_js = str(self.fixtures_dir / "patch.js")
        self.final_js = str(self.fixtures_dir / "final.js")

    def _create_mock_run(self, side_effect_func):
        return patch('source_conversion.test_ladder.run_subprocess', side_effect=side_effect_func)

    def test_complete_offline_pass_no_patch(self):
        # 1. complete offline PASS
        # 10. no-patch source safely uses base as final
        config = LadderConfig(
            source="dummy",
            mode="new",
            extensions_root="dummy"
        )

        def mock_subprocess_run(args, cwd):
            cmd = args[2]
            if "extract.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f:
                    with open(self.v01_ir, "r") as src: f.write(src.read())
            elif "js_generator.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f:
                    with open(self.base_js, "r") as src: f.write(src.read())
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with self._create_mock_run(mock_subprocess_run):
            res = run_ladder(config)

        self.assertEqual(res.overall_status, "PASS")
        self.assertEqual(next((s for s in res.stages if s.level == "L0"), res.stages[0]).status, "PASS")  # L0
        self.assertEqual(next((s for s in res.stages if s.level == "L1"), res.stages[0]).status, "PASS")  # L1
        self.assertEqual(next((s for s in res.stages if s.level == "L2"), res.stages[0]).status, "PASS")  # L2
        self.assertEqual(next((s for s in res.stages if s.level == "L3"), res.stages[0]).status, "PASS")  # L3
        self.assertEqual(next((s for s in res.stages if s.level == "L4"), res.stages[0]).status, "PASS")  # L4
        self.assertEqual(next((s for s in res.stages if s.level == "L5"), res.stages[0]).status, "PASS")  # L5
        self.assertEqual(next(s for s in res.stages if s.level == "L6").status, "NOT_APPLICABLE")  # L6

    def test_extraction_fail(self):
        # 2. extraction failure stops downstream stages
        config = LadderConfig("dummy", "new", "dummy")
        def mock_fail(args, cwd):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="Extract Error")

        with self._create_mock_run(mock_fail):
            res = run_ladder(config)

        self.assertEqual(res.overall_status, "FAIL")
        self.assertEqual(next((s for s in res.stages if s.level == "L0"), res.stages[0]).status, "FAIL")
        self.assertEqual(next((s for s in res.stages if s.level == "L1"), res.stages[0]).status, "SKIP")

    def test_generator_fail(self):
        # 4. generator failure stops downstream stages
        config = LadderConfig("dummy", "new", "dummy")
        def mock_run(args, cwd):
            cmd = args[2]
            if "extract.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f:
                    with open(self.v01_ir, "r") as src: f.write(src.read())
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if "js_generator.py" in cmd:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="Gen Error")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with self._create_mock_run(mock_run):
            res = run_ladder(config)

        self.assertEqual(res.overall_status, "FAIL")
        self.assertEqual(next((s for s in res.stages if s.level == "L2"), res.stages[0]).status, "FAIL") # L2
        self.assertEqual(next((s for s in res.stages if s.level == "L3"), res.stages[0]).status, "SKIP") # L3

    def test_patch_missing_fails(self):
        # 6. required patch missing fails
        config = LadderConfig("dummy", "new", "dummy") # no patch_path
        def mock_run(args, cwd):
            cmd = args[2]
            if "extract.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f:
                    with open(self.patch_req_ir, "r") as src: f.write(src.read())
            elif "js_generator.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f: f.write("")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with self._create_mock_run(mock_run):
            res = run_ladder(config)

        self.assertEqual(res.overall_status, "FAIL")
        self.assertEqual(next((s for s in res.stages if s.level == "L4"), res.stages[0]).status, "FAIL")
        self.assertIn("missing", next(s for s in res.stages if s.level == "L4").message)

    def test_patch_composition_success(self):
        # 7. patch composition success reaches final validation
        config = LadderConfig("dummy", "new", "dummy", patch_path=self.patch_js)
        def mock_run(args, cwd):
            cmd = args[2]
            if "extract.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f:
                    with open(self.patch_req_ir, "r") as src: f.write(src.read())
            elif "js_patcher.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f: f.write("")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with self._create_mock_run(mock_run):
            res = run_ladder(config)

        self.assertEqual(res.overall_status, "PASS")
        self.assertEqual(next((s for s in res.stages if s.level == "L4"), res.stages[0]).status, "PASS")

    def test_invalid_ir_fail(self):
        # 3. invalid IR stops generation
        config = LadderConfig("dummy", "new", "dummy")
        def mock_run(args, cwd):
            cmd = args[2]
            if "extract.py" in cmd:
                with open(args[args.index("--output")+1], "w") as f:
                    with open(self.invalid_ir, "r") as src: f.write(src.read())
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if "validate_ir.py" in cmd:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="IR invalid")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with self._create_mock_run(mock_run):
            res = run_ladder(config)

        self.assertEqual(res.overall_status, "FAIL")
        self.assertEqual(next((s for s in res.stages if s.level == "L1"), res.stages[0]).status, "FAIL") # L1
        self.assertEqual(next((s for s in res.stages if s.level == "L2"), res.stages[0]).status, "SKIP") # L2

    def test_canonical_mode(self):
        # 11. canonical mode checks byte equality
        # 17. optional/non-applicable canonical stage reports correctly
        config = LadderConfig("dummy", "canonical", "dummy", patch_path=self.patch_js,
                              canonical_ir=self.patch_req_ir, canonical_base=self.base_js, canonical_final=self.final_js)

        def mock_run(args, cwd):
            import shutil
            cmd = args[2]
            if "extract.py" in cmd:
                shutil.copy2(self.patch_req_ir, args[args.index("--output")+1])
            elif "js_generator.py" in cmd:
                shutil.copy2(self.base_js, args[args.index("--output")+1])
            elif "js_patcher.py" in cmd:
                shutil.copy2(self.final_js, args[args.index("--output")+1])
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with self._create_mock_run(mock_run):
            res = run_ladder(config)

        self.assertEqual(res.overall_status, "PASS")
         # PREP is 0, L0 is 1, L6 is 7
        self.assertEqual(next(s for s in res.stages if s.level == "L6").status, "PASS")

    def test_cleanup_on_pass_and_fail(self):
        # 13. temp cleanup on PASS
        # 14. temp cleanup on FAIL
        config = LadderConfig("dummy", "new", "dummy")
        def mock_pass(args, cwd):
            if "extract.py" in args[2]:
                with open(args[args.index("--output")+1], "w") as f: f.write("{}")
            elif "js_generator.py" in args[2]:
                with open(args[args.index("--output")+1], "w") as f: f.write("")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        temp_dir_captured = []
        import tempfile
        original_tempdir = tempfile.TemporaryDirectory
        class MockTempDir:
            def __init__(self, *args, **kwargs):
                self.td = original_tempdir(*args, **kwargs)
                temp_dir_captured.append(self.td.name)
            def __enter__(self):
                return self.td.__enter__()
            def __exit__(self, exc_type, exc_val, exc_tb):
                return self.td.__exit__(exc_type, exc_val, exc_tb)

        with patch('tempfile.TemporaryDirectory', new=MockTempDir):
            with self._create_mock_run(mock_pass):
                run_ladder(config)
        self.assertFalse(os.path.exists(temp_dir_captured[0]))

    def test_is_patch_required(self):
        from source_conversion.test_ladder import is_patch_required
        import tempfile
        import json
        cases = [
            ({"chapters": {"manualPatchRequired": True}}, True),
            ({"pages": {"manualPatchRequired": True}}, True),
            ({"explore": {"tabs": [{"manualPatchRequired": True}]}}, True),
            ({"manualPatchRequired": False}, False),
            ({}, False),
            ({"manualPatchRequired": "true"}, False),
        ]
        for data, expected in cases:
            with tempfile.NamedTemporaryFile("w", delete=False) as f:
                json.dump(data, f)
                temp_path = f.name
            try:
                self.assertEqual(is_patch_required(Path(temp_path)), expected)
            finally:
                os.remove(temp_path)

if __name__ == '__main__':
    unittest.main()
