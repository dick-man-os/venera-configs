"""Emit only the closed reviewed family contracts; legacy generation is unchanged."""
import json
from pathlib import Path
import sys

EXTRACTOR = Path(__file__).resolve().parents[1] / "extractor"
if str(EXTRACTOR) not in sys.path:
    sys.path.insert(0, str(EXTRACTOR))
from source_adapters.chinese_families import validate_contract


def generate(ir):
    problems = validate_contract(ir)
    if problems:
        raise ValueError("; ".join(problems))
    cfg = json.dumps(ir, ensure_ascii=False, separators=(",", ":"))
    family = ir["familyContract"].removesuffix("-v1")
    templates = json.loads(Path(__file__).with_name("chinese_runtime.json").read_text(encoding="utf-8"))
    body, common = templates[family], templates["common"]
    name = "Keiyoushi" + ir["provenance"]["upstreamSourceId"] + "Source"
    # Substitution inserts JSON data and checked-in code, never upstream code.
    return (common.replace("__CLASS__", name).replace("__CONFIG__", cfg)
            .replace("__NAME__", json.dumps(ir["name"], ensure_ascii=False))
            .replace("__KEY__", json.dumps(ir["id"]))
            .replace("__VERSION__", json.dumps(ir.get("version", "1.0.0")))
            .replace("__FAMILY_BODY__", body)).rstrip() + "\n"
