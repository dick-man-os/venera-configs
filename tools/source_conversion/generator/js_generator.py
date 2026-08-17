#!/usr/bin/env python3
"""
js_generator.py - Deterministic IR-to-Venera JavaScript Generator (Base Source)

Generates a standard Venera-compatible ComicSource subclass from Intermediate
Representation (IR) JSON definitions using only the Python standard library.
"""

import argparse
import json
import os
import sys
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional

# Import existing IR validator for contract validation
validator_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "validator"))
if validator_dir not in sys.path:
    sys.path.insert(0, validator_dir)

try:
    from validate_ir import validate_ir_data
except ImportError as e:
    raise ImportError(f"Failed to import validate_ir_data from {validator_dir}: {e}")


def parse_field_extractor(field_name: str, grammar_expr: str, var_name: str = "el") -> str:
    grammar_expr = grammar_expr.strip()
    if not grammar_expr:
        return '""'
    if grammar_expr.startswith("@"):
        attr = grammar_expr[1:]
        return f"({var_name}.attributes['{attr}'] || '')"
    elif "@" in grammar_expr:
        child_sel, attr = grammar_expr.split("@", 1)
        return f"({var_name}.querySelector('{child_sel}') ? ({var_name}.querySelector('{child_sel}').attributes['{attr}'] || '') : '')"
    else:
        return f"({var_name}.querySelector('{grammar_expr}') ? {var_name}.querySelector('{grammar_expr}').text : '')"


def generate_venera_js(ir_data: Dict[str, Any]) -> str:
    """Generates Venera JavaScript base source code from validated IR data."""
    # 1. Extract metadata & provenance
    name = ir_data.get("name", "Webtoons")
    source_id = ir_data.get("id", "en_webtoons")
    class_name = "".join(part.capitalize() for part in source_id.split("_")) + "Source"
    base_url = ir_data.get("baseUrl", "https://www.webtoons.com")
    mobile_url = ir_data.get("mobileUrl", "https://m.webtoons.com")

    prov = ir_data.get("provenance", {})
    upstream_project = prov.get("upstreamProject", "keiyoushi")
    upstream_pkg = prov.get("upstreamPackage", "unknown")
    upstream_commit = prov.get("upstreamCommit", "unknown")
    upstream_version = prov.get("upstreamVersion", "1.0.0")
    upstream_license = prov.get("upstreamLicense", "Apache-2.0")
    converter_ver = prov.get("converterVersion", "0.1.0")

    # Mirror Support (v0.2)
    mirrors = ir_data.get("mirrors", [])
    settings_code = ""
    # Maintain formatting: if no mirrors, use static baseUrl without extra newlines.
    if mirrors:
        options_list = []
        for m in mirrors:
            url = m["url"]
            label = m.get("label")
            if not label:
                label = urlparse(url).netloc
            options_list.append(f'                {{ value: "{url}", text: "{label}" }}')

        options_str = ",\n".join(options_list)
        default_url = mirrors[0]["url"]

        base_url_getter = f"""
    get baseUrl() {{
        let m = this.loadSetting('baseUrlSelection');
        return m ? m : "{default_url}";
    }}
"""
        settings_code = f"""
    settings = {{
        baseUrlSelection: {{
            title: "Preferred Mirror",
            type: "select",
            options: [
{options_str}
            ],
            default: "{default_url}"
        }}
    }}
"""
    else:
        base_url_getter = f'\n\n    static baseUrl = "{base_url}"'
        settings_code = ""

    # 2. Extract cookies
    cookies_list = ir_data.get("cookies", [])
    cookie_instantiations: List[str] = []
    for c in cookies_list:
        cookie_instantiations.append(
            f'            new Cookie({{ name: "{c["name"]}", value: "{c["value"]}", domain: "{c["domain"]}" }}),'
        )
    cookies_code = "\n".join(cookie_instantiations)

    # 3. Extract headers
    headers_dict = ir_data.get("headers", {})
    headers_entries: List[str] = []
    for k, v in headers_dict.items():
        headers_entries.append(f'        "{k}": "{v}",')
    headers_code = "\n".join(headers_entries)

    # Fail closed macro
    def enforce_fail_closed(manual_required: bool, method_name: str, has_patch_boundary: bool) -> str:
        if manual_required and not has_patch_boundary:
            return f'        throw new Error("MANUAL PATCH REQUIRED: {method_name} must be implemented in patch layer.");'
        return ""

    # 4. Extract explore tabs
    explore_dict = ir_data.get("explore", {})
    explore_sections: List[str] = []

    for tab_key, tab_def in explore_dict.items():
        tab_title = tab_key.capitalize()
        tab_url = tab_def.get("url", "")
        tab_selector = tab_def.get("selector", "")
        tab_fields = tab_def.get("fields", {})
        manual_patch = tab_def.get("manualPatchRequired", False)

        fail_closed = enforce_fail_closed(manual_patch, f"explore {tab_key}", False)

        base_url_ref = "this.baseUrl" if mirrors else f"{class_name}.baseUrl"

        js_url_expr = f"`{tab_url}`"
        js_url_expr = js_url_expr.replace("{{baseUrl}}", f"${{{base_url_ref}}}")
        js_url_expr = js_url_expr.replace("{{langCode}}", "en")
        js_url_expr = js_url_expr.replace("{{day}}", "${day}")

        id_expr = parse_field_extractor("id", tab_fields.get("url", "@href"), "el")
        title_expr = parse_field_extractor("title", tab_fields.get("title", ".title"), "el")
        cover_expr = parse_field_extractor("cover", tab_fields.get("thumbnail", "img@src"), "el")

        day_calc = ""
        if "{{day}}" in tab_url:
            day_calc = '                let days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];\n                let day = days[new Date().getDay()];\n'

        if fail_closed:
            explore_section = f"""        {{
            title: "{tab_title}",
            type: "multiPageComicList",
            load: async (page) => {{
{fail_closed}
            }}
        }}"""
        else:
            explore_section = f"""        {{
            title: "{tab_title}",
            type: "multiPageComicList",
            load: async (page) => {{
{day_calc}                let res = await Network.get({js_url_expr}, {class_name}.headers);
                if (res.status !== 200) {{
                    throw new Error(`Failed to load {tab_title.lower()} comics, status: ${{res.status}}`);
                }}
                let doc = new HtmlDocument(res.body);
                let elements = doc.querySelectorAll("{tab_selector}");
                let comics = elements.map(el => new Comic({{
                    id: {id_expr},
                    title: {title_expr},
                    cover: {cover_expr},
                }}));
                doc.dispose();
                return {{
                    comics: comics,
                    maxPage: 1,
                }};
            }}
        }}"""
        explore_sections.append(explore_section)

    explore_code = ",\n".join(explore_sections)

    # 5. Extract search
    search_dict = ir_data.get("search", {})
    search_manual = search_dict.get("manualPatchRequired", False)
    search_url = search_dict.get("url", "")
    search_selector = search_dict.get("selector", "")
    search_fields = search_dict.get("fields", {})

    search_fail_closed = enforce_fail_closed(search_manual, "search load", False)

    base_url_ref = "this.baseUrl" if mirrors else f"{class_name}.baseUrl"

    search_url_expr = f"`{search_url}`"
    search_url_expr = search_url_expr.replace("{{baseUrl}}", f"${{{base_url_ref}}}")
    search_url_expr = search_url_expr.replace("{{langCode}}", "en")
    search_url_expr = search_url_expr.replace("{{query}}", "${encodeURIComponent(keyword)}")
    search_url_expr = search_url_expr.replace("{{page}}", "${page}")

    search_id_expr = parse_field_extractor("id", search_fields.get("url", "@href"), "el")
    search_title_expr = parse_field_extractor("title", search_fields.get("title", ".title"), "el")
    search_cover_expr = parse_field_extractor("cover", search_fields.get("thumbnail", "img@src"), "el")

    if search_fail_closed:
        search_body = f"            {search_fail_closed}"
    else:
        search_body = f"""            let url = {search_url_expr};
            let res = await Network.get(url, {class_name}.headers);
            if (res.status !== 200) {{
                throw new Error(`Failed to load search results, status: ${{res.status}}`);
            }}
            let doc = new HtmlDocument(res.body);
            let elements = doc.querySelectorAll("{search_selector}");
            let comics = elements.map(el => new Comic({{
                id: {search_id_expr},
                title: {search_title_expr},
                cover: {search_cover_expr},
            }}));
            doc.dispose();
            return {{
                comics: comics,
                maxPage: 100,
            }};"""

    # 6. Extract details
    details_dict = ir_data.get("details", {})
    details_manual = details_dict.get("manualPatchRequired", False)
    details_fields = details_dict.get("fields", {})

    details_fail_closed = enforce_fail_closed(details_manual, "comic loadInfo", False)

    title_sel = details_fields.get("title", "h1.subj, h3.subj")
    author_sel = details_fields.get("author", ".author:nth-of-type(1)")
    desc_sel = details_fields.get("description", "#_asideDetail p.summary")
    thumb_sel = details_fields.get("thumbnail", ".detail_header .thmb img@src")

    thumb_extractor = parse_field_extractor("cover", thumb_sel, "doc")

    if details_fail_closed:
        details_body = f"            {details_fail_closed}"
    else:
        details_body = f"""            let url = id.startsWith("http") ? id : `${{{base_url_ref}}}${{id}}`;
            let res = await Network.get(url, {class_name}.headers);
            if (res.status !== 200) {{
                throw new Error(`Failed to load comic details, status: ${{res.status}}`);
            }}
            let doc = new HtmlDocument(res.body);
            let titleEl = doc.querySelector("{title_sel}");
            let authorEl = doc.querySelector("{author_sel}") || doc.querySelector(".author_area");
            let descEl = doc.querySelector("{desc_sel}");

            let title = titleEl ? titleEl.text : "";
            let author = authorEl ? authorEl.text : "";
            let description = descEl ? descEl.text : "";
            let cover = {thumb_extractor};
            doc.dispose();

            let chapters = await this.loadChapters(id);

            return new ComicDetails({{
                title: title,
                subtitle: author,
                subTitle: author,
                cover: cover,
                description: description,
                tags: {{}},
                chapters: chapters,
            }});"""

    # 7. Extract chapters & pages
    chapters_dict = ir_data.get("chapters", {})
    chapters_url = chapters_dict.get("url", "")
    chapters_list_path = chapters_dict.get("listPath", "result.episodeList")
    chapters_manual = chapters_dict.get("manualPatchRequired", False)

    # chapters has a patch boundary: parseChaptersCustom
    chapters_fail_closed = enforce_fail_closed(chapters_manual, "loadChapters", True)

    pages_dict = ir_data.get("pages", {})
    pages_selector = pages_dict.get("selector", "div#_imageList > img")
    pages_fields = pages_dict.get("fields", {})
    pages_img_attr = pages_fields.get("imageUrl", "@data-url").lstrip("@")
    pages_manual = pages_dict.get("manualPatchRequired", False)

    # pages has a patch boundary: parsePagesCustom
    pages_fail_closed = enforce_fail_closed(pages_manual, "comic loadEp", True)

    if pages_fail_closed:
        pages_body = f"            {pages_fail_closed}"
    else:
        pages_body = f"""            let url = epId.startsWith("http") ? epId : `${{{base_url_ref}}}${{epId}}`;
            let res = await Network.get(url, {class_name}.headers);
            if (res.status !== 200) {{
                throw new Error(`Failed to load episode, status: ${{res.status}}`);
            }}
            let doc = new HtmlDocument(res.body);
            let imgElements = doc.querySelectorAll("{pages_selector}");
            let images = imgElements.map(el => el.attributes["{pages_img_attr}"]).filter(Boolean);
            doc.dispose();

            // Hook for custom page transformations (e.g. MotionToon / AuthorNotes)
            images = this.parsePagesCustom(images, res.body);

            return {{
                images: images,
            }};"""

    if chapters_fail_closed:
        chapters_body = f"""    loadChapters = async (comicUrl) => {{
{chapters_fail_closed}
    }}"""
    else:
        chapters_body = f"""    /**
     * [MANUAL PATCH HOOK] Load and parse chapters
     * Upstream Webtoons uses mobile JSON API: {chapters_url}
     * Manual patch is required for episode title parsing, season numbering, and offsets.
     */
    loadChapters = async (comicUrl) => {{
        return this.parseChaptersCustom(comicUrl);
    }}"""

    cookies_init = ""
    if cookies_list:
        if mirrors:
            cookies_init = f"""
    init() {{
        Network.setCookies(this.baseUrl, [
{cookies_code}
        ]);
    }}"""
        else:
            cookies_init = f"""

    init() {{
        Network.setCookies({class_name}.baseUrl, [
{cookies_code}
        ]);
    }}"""


    # 8. Assemble full JavaScript source
    js_code = f"""/**
 * @file {source_id}.base.js
 * Generated automatically by Venera Source Converter v{converter_ver}
 *
 * Upstream Project: {upstream_project}
 * Upstream Package: {upstream_pkg}
 * Upstream Commit:  {upstream_commit}
 * Upstream Version: {upstream_version}
 * Upstream License: {upstream_license}
 */

/** @type {{import('./_venera_.js')}} */

class {class_name} extends ComicSource {{
    name = "{name}"
    key = "{source_id}"
    version = "1.0.0"
    minAppVersion = "1.6.0"{base_url_getter}
    static mobileUrl = "{mobile_url}"

    static headers = {{
{headers_code}
    }}{settings_code}{cookies_init}

    // Explore / Discovery Sections
    explore = [
{explore_code}
    ]

    // Search
    search = {{
        load: async (keyword, options, page) => {{
{search_body}
        }}
    }}

    // Comic Details and Reader Loading
    comic = {{
        loadInfo: async (id) => {{
{details_body}
        }},

        loadEp: async (comicId, epId) => {{
{pages_body}
        }},

        onImageLoad: (url, comicId, epId) => ({{
            url: url,
            headers: {{
                ...{class_name}.headers,
                "Referer": `${{{base_url_ref}}}/`,
            }},
        }}),

        onThumbnailLoad: (url) => ({{
            url: url,
            headers: {{
                ...{class_name}.headers,
                "Referer": `${{{base_url_ref}}}/`,
            }},
        }}),
    }}

    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

{chapters_body}

    /**
     * Placeholder hook to be overridden by manual patch layer.
     */
    parseChaptersCustom = async (comicUrl) => {{
        throw new Error("MANUAL PATCH REQUIRED: parseChaptersCustom must be implemented in patch layer.");
    }}

    /**
     * Placeholder hook for special page variants (e.g. MotionToon).
     */
    parsePagesCustom = (images, htmlBody) => {{
        return images;
    }}
}}
"""
    return js_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Venera ComicSource base JavaScript file from IR JSON."
    )
    parser.add_argument(
        "--input",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "sources_ir", "webtoons.json")
        ),
        help="Path to input IR JSON file.",
    )
    parser.add_argument(
        "--output",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "sources_generated", "webtoons.base.js")
        ),
        help="Path to write the generated base JavaScript file.",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip IR schema validation (for testing/debugging).",
    )

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    output_path = os.path.abspath(args.output)

    print(f"[*] Reading IR definition from: {input_path}")
    print(f"[*] Target output JS: {output_path}")

    if not os.path.exists(input_path):
        print(f"[!] Error: Input IR file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            ir_data = json.load(f)
    except Exception as e:
        print(f"[!] Error reading IR JSON: {e}", file=sys.stderr)
        return 1

    # 1. Validate IR contract using existing validate_ir
    if not args.skip_validation:
        validation_errors = validate_ir_data(ir_data)
        if validation_errors:
            print(f"[!] IR validation failed ({len(validation_errors)} errors):", file=sys.stderr)
            for err in validation_errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    # 2. Generate Venera JavaScript code
    try:
        js_code = generate_venera_js(ir_data)
    except Exception as e:
        print(f"[!] Code generation failed: {e}", file=sys.stderr)
        return 1

    # 3. Write output file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(js_code)

    print(f"[+] Successfully generated Venera Base JS: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
