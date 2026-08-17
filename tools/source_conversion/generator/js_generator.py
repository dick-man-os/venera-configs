#!/usr/bin/env python3
"""
js_generator.py - Deterministic IR-to-Venera JavaScript Generator (Base Source)

Generates a standard Venera-compatible ComicSource subclass from Intermediate
Representation (IR) v0.1 JSON definitions using only the Python standard library.
"""

import argparse
import json
import os
import sys
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
    """
    Translates an IR field grammar expression into Venera JavaScript element extraction code.
    Grammar rules:
    - Text: CSS selector (e.g. '.title' -> el.querySelector('.title')?.text ?? '')
    - Attribute on current element: '@href' -> el.attributes['href'] ?? ''
    - Attribute on child element: 'img@src' -> el.querySelector('img')?.attributes['src'] ?? ''
    """
    grammar_expr = grammar_expr.strip()
    if grammar_expr.startswith("@"):
        attr = grammar_expr[1:]
        return f"({var_name}.attributes['{attr}'] || '')"
    elif "@" in grammar_expr:
        child_sel, attr = grammar_expr.split("@", 1)
        return f"({var_name}.querySelector('{child_sel}') ? ({var_name}.querySelector('{child_sel}').attributes['{attr}'] || '') : '')"
    else:
        return f"({var_name}.querySelector('{grammar_expr}') ? {var_name}.querySelector('{grammar_expr}').text : '')"


def generate_venera_js(ir_data: Dict[str, Any]) -> str:
    """Generates Venera JavaScript base source code from validated IR v0.1 data."""
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

    # 4. Extract explore tabs
    explore_dict = ir_data.get("explore", {})
    explore_sections: List[str] = []

    for tab_key, tab_def in explore_dict.items():
        tab_title = tab_key.capitalize()
        tab_url = tab_def.get("url", "")
        tab_selector = tab_def.get("selector", "")
        tab_fields = tab_def.get("fields", {})

        # URL template mapping
        js_url_expr = f"`{tab_url}`"
        js_url_expr = js_url_expr.replace("{{baseUrl}}", f"${{{class_name}.baseUrl}}")
        js_url_expr = js_url_expr.replace("{{langCode}}", "en")
        js_url_expr = js_url_expr.replace("{{day}}", "${day}")

        id_expr = parse_field_extractor("id", tab_fields.get("url", "@href"), "el")
        title_expr = parse_field_extractor("title", tab_fields.get("title", ".title"), "el")
        cover_expr = parse_field_extractor("cover", tab_fields.get("thumbnail", "img@src"), "el")

        day_calc = ""
        if "{{day}}" in tab_url:
            day_calc = '                let days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];\n                let day = days[new Date().getDay()];\n'

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
    search_url = search_dict.get("url", "")
    search_selector = search_dict.get("selector", "")
    search_fields = search_dict.get("fields", {})

    search_url_expr = f"`{search_url}`"
    search_url_expr = search_url_expr.replace("{{baseUrl}}", f"${{{class_name}.baseUrl}}")
    search_url_expr = search_url_expr.replace("{{langCode}}", "en")
    search_url_expr = search_url_expr.replace("{{query}}", "${encodeURIComponent(keyword)}")
    search_url_expr = search_url_expr.replace("{{page}}", "${page}")

    search_id_expr = parse_field_extractor("id", search_fields.get("url", "@href"), "el")
    search_title_expr = parse_field_extractor("title", search_fields.get("title", ".title"), "el")
    search_cover_expr = parse_field_extractor("cover", search_fields.get("thumbnail", "img@src"), "el")

    # 6. Extract details
    details_dict = ir_data.get("details", {})
    details_fields = details_dict.get("fields", {})

    title_sel = details_fields.get("title", "h1.subj, h3.subj")
    author_sel = details_fields.get("author", ".author:nth-of-type(1)")
    desc_sel = details_fields.get("description", "#_asideDetail p.summary")
    thumb_sel = details_fields.get("thumbnail", ".detail_header .thmb img@src")

    thumb_extractor = parse_field_extractor("cover", thumb_sel, "doc")

    # 7. Extract chapters & pages
    chapters_dict = ir_data.get("chapters", {})
    chapters_url = chapters_dict.get("url", "")
    chapters_list_path = chapters_dict.get("listPath", "result.episodeList")
    chapters_manual = chapters_dict.get("manualPatchRequired", False)

    pages_dict = ir_data.get("pages", {})
    pages_selector = pages_dict.get("selector", "div#_imageList > img")
    pages_fields = pages_dict.get("fields", {})
    pages_img_attr = pages_fields.get("imageUrl", "@data-url").lstrip("@")
    pages_manual = pages_dict.get("manualPatchRequired", False)

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
    minAppVersion = "1.6.0"

    static baseUrl = "{base_url}"
    static mobileUrl = "{mobile_url}"

    static headers = {{
{headers_code}
    }}

    init() {{
        Network.setCookies({class_name}.baseUrl, [
{cookies_code}
        ]);
    }}

    // Explore / Discovery Sections
    explore = [
{explore_code}
    ]

    // Search
    search = {{
        load: async (keyword, options, page) => {{
            let url = {search_url_expr};
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
            }};
        }}
    }}

    // Comic Details and Reader Loading
    comic = {{
        loadInfo: async (id) => {{
            let url = id.startsWith("http") ? id : `${{{class_name}.baseUrl}}${{id}}`;
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
                chapters: chapters,
            }});
        }},

        loadEp: async (comicId, epId) => {{
            let url = epId.startsWith("http") ? epId : `${{{class_name}.baseUrl}}${{epId}}`;
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
            }};
        }},

        onImageLoad: (url, comicId, epId) => ({{
            url: url,
            headers: {{
                ...{class_name}.headers,
                "Referer": `${{{class_name}.baseUrl}}/`,
            }},
        }}),

        onThumbnailLoad: (url) => ({{
            url: url,
            headers: {{
                ...{class_name}.headers,
                "Referer": `${{{class_name}.baseUrl}}/`,
            }},
        }}),
    }}

    // =========================================================================
    // Patch Hooks / Boundaries
    // =========================================================================

    /**
     * [MANUAL PATCH HOOK] Load and parse chapters
     * Upstream Webtoons uses mobile JSON API: {chapters_url}
     * Manual patch is required for episode title parsing, season numbering, and offsets.
     */
    loadChapters = async (comicUrl) => {{
        return this.parseChaptersCustom(comicUrl);
    }}

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
        description="Generate a Venera ComicSource base JavaScript file from IR v0.1 JSON."
    )
    parser.add_argument(
        "--input",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "sources_ir", "webtoons.json")
        ),
        help="Path to input IR v0.1 JSON file.",
    )
    parser.add_argument(
        "--output",
        default=os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "sources_generated", "webtoons.base.js")
        ),
        help="Path to write the generated base JavaScript file.",
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
