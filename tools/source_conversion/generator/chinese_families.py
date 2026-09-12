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
    if family == "mccms":
        mccms = json.loads(Path(__file__).with_name("chinese_mccms_runtime.json").read_text(encoding="utf-8"))
        body = "\n".join(mccms["mccms"]) + "\n"
        catalog_result = "{comics:this.unique(rows),hasMore:this.hasNext(doc,request)}"
        if ir["provenance"]["upstreamSourceId"] == "3279300917142951720":
            body += "\n".join(mccms["manhuawu"]) + "\n"
            catalog_result = "this.catalogResult(kind,rows,doc,request,page)"
        body = body.replace("__MCCMS_CATALOG_RESULT__", catalog_result)
    elif family == "manga18":
        manga18 = json.loads(Path(__file__).with_name("chinese_manga18_runtime.json").read_text(encoding="utf-8"))
        body = "\n".join(manga18["manga18"]) + "\n"
    elif family in {"guazimanhua", "terrahistoricus", "bh3"}:
        template = json.loads(Path(__file__).with_name("chinese_" + family + "_runtime.json").read_text(encoding="utf-8"))
        body = "\n".join(template[family]) + "\n"
    else:
        body = templates[family]
    common = templates["common"]
    hooks = {
        "__REQUEST_URL__": "",
        "__THUMBNAIL_LOAD__": "url => ({url, headers: this.headers})",
        "__IMAGE_LOAD__": "url => ({url, headers: this.headers})",
    }
    if family == "dongmanmanhua":
        hooks.update({
            "__REQUEST_URL__": "        url = this.networkUrl(url);\n",
            "__THUMBNAIL_LOAD__": '(url, comicId) => this.imageConfig(url, this.networkUrl(comicId || "/"))',
            "__IMAGE_LOAD__": '(url, comicId, epId) => this.imageConfig(url, epId ? this.readerBase(comicId, epId) : this.networkUrl(comicId || "/"))',
        })
    for token, value in hooks.items():
        common = common.replace(token, value)
    name = "Keiyoushi" + ir["provenance"]["upstreamSourceId"] + "Source"
    # Substitution inserts JSON data and checked-in code, never upstream code.
    return (common.replace("__CLASS__", name).replace("__CONFIG__", cfg)
            .replace("__NAME__", json.dumps(ir["name"], ensure_ascii=False))
            .replace("__KEY__", json.dumps(ir["id"]))
            .replace("__VERSION__", json.dumps(ir.get("version", "1.0.0")))
            .replace("__FAMILY_BODY__", body)).rstrip() + "\n"
