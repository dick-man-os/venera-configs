import os
import sys
import json
import subprocess
import difflib
import tempfile

def test_regression():
    workspace = r"c:\Projects\VeneraX-Dev\venera-configs"
    extractor_path = os.path.join(workspace, "tools", "source_conversion", "extractor", "extract.py")
    generator_path = os.path.join(workspace, "tools", "source_conversion", "generator", "js_generator.py")
    patcher_path = os.path.join(workspace, "tools", "source_conversion", "patcher", "js_patcher.py")

    canonical_ir_path = os.path.join(workspace, "sources_ir", "webtoons.json")
    canonical_js_path = os.path.join(workspace, "sources_generated", "webtoons.base.js")
    canonical_patch_path = os.path.join(workspace, "sources_patches", "webtoons.patch.js")
    canonical_final_path = os.path.join(workspace, "webtoons.js")

    webtoons_src = "all/webtoons"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_ir_path = os.path.join(temp_dir, "temp_webtoons.json")
        temp_js_path = os.path.join(temp_dir, "temp_webtoons.base.js")
        temp_final_path = os.path.join(temp_dir, "temp_webtoons.js")

        print("[*] Reading canonical IR timestamp...")
        with open(canonical_ir_path, "r", encoding="utf-8") as f:
            canon_ir_bytes = f.read()
            canon_ir = json.loads(canon_ir_bytes)

        canon_timestamp = canon_ir.get("provenance", {}).get("generatedTimestamp")

        print(f"[*] Running extractor on Webtoons with timestamp: {canon_timestamp}")
        extract_args = [sys.executable, "-B", extractor_path, "--source", webtoons_src, "--output", temp_ir_path]
        if canon_timestamp:
            extract_args.extend(["--timestamp", canon_timestamp])

        res = subprocess.run(extract_args, capture_output=True, text=True)
        if res.returncode != 0:
            print("Extractor failed:")
            print(res.stderr)
            return False

        print("[*] Comparing IRs...")
        with open(temp_ir_path, "r", encoding="utf-8") as f:
            temp_ir_bytes = f.read()
            temp_ir = json.loads(temp_ir_bytes)

        ir_structural_equality = canon_ir == temp_ir
        ir_byte_identical = canon_ir_bytes == temp_ir_bytes

        print(f"IR STRUCTURAL EQUALITY: {ir_structural_equality}")
        print(f"IR BYTE IDENTICAL: {ir_byte_identical}")

        if not ir_structural_equality:
            print("IR structurally differs!")
            return False

        print("[*] Running JS generator on Canonical Webtoons IR...")
        res = subprocess.run([sys.executable, "-B", generator_path, "--input", canonical_ir_path, "--output", temp_js_path], capture_output=True, text=True)
        if res.returncode != 0:
            print("Generator failed:")
            print(res.stderr)
            return False

        print("[*] Comparing Base JS...")
        with open(canonical_js_path, "r", encoding="utf-8") as f:
            canon_js_bytes = f.read()
        with open(temp_js_path, "r", encoding="utf-8") as f:
            temp_js_bytes = f.read()

        base_js_byte_identical = canon_js_bytes == temp_js_bytes
        print(f"BASE JS BYTE IDENTICAL: {base_js_byte_identical}")

        if not base_js_byte_identical:
            print("Base JS differs!")
            diff = difflib.unified_diff(canon_js_bytes.splitlines(), temp_js_bytes.splitlines(), fromfile='canonical', tofile='generated')
            print('\n'.join(diff))
            return False

        print("[*] Running patcher on Temporary Webtoons Base...")
        res = subprocess.run([sys.executable, "-B", patcher_path, "--base", temp_js_path, "--patch", canonical_patch_path, "--output", temp_final_path], capture_output=True, text=True)
        if res.returncode != 0:
            print("Patcher failed:")
            print(res.stderr)
            return False

        print("[*] Comparing Final JS...")
        with open(canonical_final_path, "r", encoding="utf-8") as f:
            canon_final_bytes = f.read()
        with open(temp_final_path, "r", encoding="utf-8") as f:
            temp_final_bytes = f.read()

        final_js_byte_identical = canon_final_bytes == temp_final_bytes
        print(f"FINAL WEBTOONS JS BYTE IDENTICAL: {final_js_byte_identical}")

        if not final_js_byte_identical:
            print("Final JS differs!")
            diff = difflib.unified_diff(canon_final_bytes.splitlines(), temp_final_bytes.splitlines(), fromfile='canonical', tofile='generated')
            print('\n'.join(diff))
            return False

    return True

if __name__ == "__main__":
    if test_regression():
        sys.exit(0)
    else:
        sys.exit(1)
