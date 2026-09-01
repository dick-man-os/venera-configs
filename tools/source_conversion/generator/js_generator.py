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


import re


def _is_absolute_attribute_grammar(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    grammar_expr = value.strip()
    return grammar_expr.startswith("@abs:") or "@abs:" in grammar_expr


def _contains_absolute_attribute_grammar(value: Any) -> bool:
    if _is_absolute_attribute_grammar(value):
        return True
    if isinstance(value, dict):
        return any(_contains_absolute_attribute_grammar(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_attribute_grammar(item) for item in value)
    return False


def parse_field_extractor(
    field_name: str,
    grammar_expr: str,
    var_name: str = "el",
    request_url_expr: Optional[str] = None,
    resolver_expr: Optional[str] = None,
) -> str:
    grammar_expr = grammar_expr.strip()
    if not grammar_expr:
        return '""'
    if grammar_expr.startswith("@"):
        attr = grammar_expr[1:]
        if attr.startswith("abs:"):
            literal_attr = attr[len("abs:"):]
            if not literal_attr or not request_url_expr or not resolver_expr:
                raise ValueError(f"Invalid absolute attribute grammar for {field_name}: {grammar_expr}")
            literal_lookup = f"({var_name}.attributes['{literal_attr}'] || '')"
            return f"{resolver_expr}({literal_lookup}, {request_url_expr})"
        return f"({var_name}.attributes['{attr}'] || '')"
    elif "@" in grammar_expr:
        child_sel, attr = grammar_expr.split("@", 1)
        if attr.startswith("abs:"):
            literal_attr = attr[len("abs:"):]
            if not literal_attr or not request_url_expr or not resolver_expr:
                raise ValueError(f"Invalid absolute attribute grammar for {field_name}: {grammar_expr}")
            child_lookup = f"{var_name}.querySelector('{child_sel}')"
            literal_lookup = f"({child_lookup} ? ({child_lookup}.attributes['{literal_attr}'] || '') : '')"
            return f"{resolver_expr}({literal_lookup}, {request_url_expr})"
        return f"({var_name}.querySelector('{child_sel}') ? ({var_name}.querySelector('{child_sel}').attributes['{attr}'] || '') : '')"
    elif grammar_expr == "text":
        return f"({var_name}.text || '')"
    else:
        return f"({var_name}.querySelector('{grammar_expr}') ? {var_name}.querySelector('{grammar_expr}').text : '')"


def generate_venera_js(ir_data: Dict[str, Any]) -> str:
    """Generates Venera JavaScript base source code from validated IR data."""
    # 1. Extract metadata & provenance
    name = ir_data.get("name", "Webtoons")
    source_id = ir_data.get("id", "en_webtoons")
    languages = ir_data.get("languages") or ["en"]
    route_language = str(languages[0]).lower()

    # Sanitize key for VeneraX runtime (only A-Z, a-z, 0-9, _)
    sanitized_key = re.sub(r'[^A-Za-z0-9_]', '_', source_id)
    sanitized_key = re.sub(r'_+', '_', sanitized_key)

    class_name_raw = "".join(part.capitalize() for part in source_id.split("_"))
    class_name = "".join(c for c in class_name_raw if c.isalnum()) + "Source"
    base_url = ir_data.get("baseUrl", "https://www.webtoons.com")
    mobile_url = ir_data.get("mobileUrl", "https://m.webtoons.com")
    uses_absolute_attributes = _contains_absolute_attribute_grammar(ir_data)
    absolute_url_resolver = f"{class_name}.resolveAbsoluteUrl"

    prov = ir_data.get("provenance", {})
    upstream_project = prov.get("upstreamProject", "keiyoushi")
    upstream_pkg = prov.get("upstreamPackage", "unknown")
    upstream_commit = prov.get("upstreamCommit", "unknown")
    upstream_version = prov.get("upstreamVersion", "1.0.0")
    upstream_license = prov.get("upstreamLicense", "Apache-2.0")
    converter_ver = prov.get("converterVersion", "0.1.0")
    source_version = ir_data.get("version", "1.0.0")

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
    explore_custom_hooks: List[str] = []

    static_catalog = ir_data.get("staticCatalog")
    if static_catalog:
        import json
        static_catalog_json = json.dumps(static_catalog, indent=8, ensure_ascii=False)
        static_catalog_code = f"    // Static Catalog Array\n    staticCatalog = {static_catalog_json.strip()};\n\n"
    else:
        static_catalog_code = ""

    for tab_key, tab_def in explore_dict.items():
        tab_title = tab_key.capitalize()
        tab_url = tab_def.get("url", "")
        tab_selector = tab_def.get("selector", "")
        tab_fields = tab_def.get("fields", {})
        manual_patch = tab_def.get("manualPatchRequired", False)
        use_static = tab_def.get("useStaticCatalog", False)

        fail_closed = enforce_fail_closed(manual_patch, f"explore {tab_key}", True)

        base_url_ref = "this.baseUrl" if mirrors else f"{class_name}.baseUrl"

        js_url_expr = f"`{tab_url}`"
        js_url_expr = js_url_expr.replace("{{baseUrl}}", f"${{{base_url_ref}}}")
        js_url_expr = js_url_expr.replace("{{langCode}}", route_language)
        js_url_expr = js_url_expr.replace("{{page}}", "${page}")
        js_url_expr = js_url_expr.replace("{{day}}", "${day}")

        tab_uses_absolute_attributes = any(
            _is_absolute_attribute_grammar(value) for value in tab_fields.values()
        )
        id_expr = parse_field_extractor(
            "id", tab_fields.get("url", "@href"), "el", "url", absolute_url_resolver
        )
        title_expr = parse_field_extractor(
            "title", tab_fields.get("title", ".title"), "el", "url", absolute_url_resolver
        )
        cover_expr = parse_field_extractor(
            "cover", tab_fields.get("thumbnail", "img@src"), "el", "url", absolute_url_resolver
        )

        pagination = tab_def.get("pagination")
        if pagination and pagination.get("hasNextStrategy") == "compareAttributes":
            next_sel = pagination.get("nextSelector")
            curr_sel = pagination.get("currentSelector")
            attr = pagination.get("attribute")
            pagination_js = f"""                let nextEl = doc.querySelector("{next_sel}");
                let currEl = doc.querySelector("{curr_sel}");
                let hasNext = nextEl && currEl && nextEl.attributes["{attr}"] !== currEl.attributes["{attr}"];
                let outMaxPage = hasNext ? page + 1 : page;
"""
            max_page_expr = "outMaxPage"
        else:
            pagination_js = ""
            max_page_expr = "1"


        day_calc = ""
        if "{{day}}" in tab_url:
            day_calc = '                let days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];\n                let day = days[new Date().getDay()];\n'

        custom_hook_name = f"load{tab_key.capitalize()}Custom"

        if use_static:
            explore_body = f"""                return {{
                    comics: this.staticCatalog.map(item => new Comic({{
                        id: item.url,
                        title: item.title,
                        cover: \"\"
                    }})),
                    hasMore: false
                }};"""
        elif manual_patch:
            explore_body = f"                return await this.{custom_hook_name}(page);"
            explore_custom_hook = f"""
    /**
     * Placeholder hook to be overridden by manual patch layer for Explore {tab_title}.
     */
    {custom_hook_name} = async (page) => {{
        throw new Error("MANUAL PATCH REQUIRED: {custom_hook_name} must be implemented in patch layer.");
    }}"""
            explore_custom_hooks.append(explore_custom_hook)
        elif fail_closed:
            explore_body = f"                {fail_closed}"
        else:
            if tab_uses_absolute_attributes:
                network_request_js = f"""                let url = {js_url_expr};
                let res = await Network.get(url, {class_name}.headers);"""
            else:
                network_request_js = f"""                let res = await Network.get({js_url_expr}, {class_name}.headers);"""
            explore_body = f"""{day_calc}{network_request_js}
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
{pagination_js}                doc.dispose();
                return {{
                    comics: comics,
                    maxPage: {max_page_expr},
                }};"""

        explore_section = f"""        {{
            title: "{tab_title}",
            type: "multiPageComicList",
            load: async (page) => {{
{explore_body}
            }}
        }}"""
        explore_sections.append(explore_section)

    explore_code = ",\n".join(explore_sections)
    explore_hooks_code = "".join(explore_custom_hooks)

    # 5. Extract search
    search_dict = ir_data.get("search", {})
    search_manual = search_dict.get("manualPatchRequired", False)
    search_use_static = search_dict.get("useStaticCatalog", False)
    search_url = search_dict.get("url", "")
    search_selector = search_dict.get("selector", "")
    search_fields = search_dict.get("fields", {})

    search_fail_closed = enforce_fail_closed(search_manual, "search load", False)

    base_url_ref = "this.baseUrl" if mirrors else f"{class_name}.baseUrl"

    search_url_expr = f"`{search_url}`"
    search_url_expr = search_url_expr.replace("{{baseUrl}}", f"${{{base_url_ref}}}")
    search_url_expr = search_url_expr.replace("{{langCode}}", route_language)
    search_url_expr = search_url_expr.replace("{{query}}", "${encodeURIComponent(keyword)}")
    search_url_expr = search_url_expr.replace("{{page}}", "${page}")

    search_id_expr = parse_field_extractor(
        "id", search_fields.get("url", "@href"), "el", "url", absolute_url_resolver
    )
    search_title_expr = parse_field_extractor(
        "title", search_fields.get("title", ".title"), "el", "url", absolute_url_resolver
    )
    search_cover_expr = parse_field_extractor(
        "cover", search_fields.get("thumbnail", "img@src"), "el", "url", absolute_url_resolver
    )

    pagination = search_dict.get("pagination")
    if pagination and pagination.get("hasNextStrategy") == "compareAttributes":
        next_sel = pagination.get("nextSelector")
        curr_sel = pagination.get("currentSelector")
        attr = pagination.get("attribute")
        search_pagination_js = f"""            let nextEl = doc.querySelector("{next_sel}");
            let currEl = doc.querySelector("{curr_sel}");
            let hasNext = nextEl && currEl && nextEl.attributes["{attr}"] !== currEl.attributes["{attr}"];
            let outMaxPage = hasNext ? page + 1 : page;
"""
        search_max_page_expr = "outMaxPage"
    else:
        search_pagination_js = ""
        search_max_page_expr = "100"

    if search_use_static:
        search_body = f"""              const q = (keyword || \"\").toLowerCase();
              return {{
                  comics: this.staticCatalog
                      .filter(item => item.title.toLowerCase().includes(q))
                      .map(item => new Comic({{
                          id: item.url,
                          title: item.title,
                          cover: \"\"
                      }})),
                  hasMore: false
              }};"""
        search_custom_hook = ""
    elif search_manual:
        search_body = "            return await this.loadSearchCustom(keyword, options, page);"
        search_custom_hook = """
    /**
     * Placeholder hook to be overridden by manual patch layer for Search.
     */
    loadSearchCustom = async (keyword, options, page) => {
        throw new Error("MANUAL PATCH REQUIRED: loadSearchCustom must be implemented in patch layer.");
    }"""
    elif search_fail_closed:
        search_body = f"            {search_fail_closed}"
        search_custom_hook = ""
    else:
        search_custom_hook = ""
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
{search_pagination_js}            doc.dispose();
            return {{
                comics: comics,
                maxPage: {search_max_page_expr},
            }};"""

    # 6. Extract details
    details_dict = ir_data.get("details", {})
    details_manual = details_dict.get("manualPatchRequired", False)
    details_fields = details_dict.get("fields", {})

    details_fail_closed = enforce_fail_closed(details_manual, "comic loadInfo", True)

    title_sel = details_fields.get("title", "h1.subj, h3.subj")
    author_sel = details_fields.get("author", ".author")
    desc_sel = details_fields.get("description", "#_asideDetail p.summary")
    thumb_sel = details_fields.get("thumbnail", ".detail_header .thmb img@src")

    thumb_extractor = parse_field_extractor(
        "cover", thumb_sel, "doc", "url", absolute_url_resolver
    )

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
{"" if details_manual else "            doc.dispose();"}

            let chapters = await this.loadChapters(id);

            {"let comicDetails = " if details_manual else "return "}new ComicDetails({{
                title: title,
                subtitle: author,
                subTitle: author,
                cover: cover,
                description: description,
                tags: {{}},
                chapters: chapters,
            }});{f'''

            comicDetails = this.parseDetailsCustom(comicDetails, doc);
            doc.dispose();
            return comicDetails;''' if details_manual else ""}"""

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
    pages_image_field = pages_fields.get("imageUrl", "@data-url")
    pages_img_attr = pages_image_field.lstrip("@")
    pages_uses_absolute_attribute = _is_absolute_attribute_grammar(pages_image_field)
    pages_image_extractor = (
        parse_field_extractor(
            "imageUrl", pages_image_field, "el", "url", absolute_url_resolver
        )
        if pages_uses_absolute_attribute
        else None
    )
    pages_manual = pages_dict.get("manualPatchRequired", False)
    pages_image_load_patch_required = pages_dict.get("imageLoadPatchRequired", False)

    pages_manual_only = pages_manual and not pages_dict.get("selector") and not pages_dict.get("url")

    if pages_image_load_patch_required:
        image_load_body = f"""        onImageLoad: (url, comicId, epId) => {{
            if (this.onImageLoadCustom) {{
                return this.onImageLoadCustom(url, comicId, epId);
            }}
            return {{
                url: url,
                headers: {{
                    ...{class_name}.headers,
                    "Referer": `${{{base_url_ref}}}/`,
                }},
            }};
        }},"""
        image_load_hook = """
    /**
     * Placeholder hook to be overridden by manual patch layer for Image Load.
     */
    onImageLoadCustom = (url, comicId, epId) => {
        throw new Error("MANUAL PATCH REQUIRED: onImageLoadCustom must be implemented in patch layer.");
    }"""
    else:
        image_load_body = f"""        onImageLoad: (url, comicId, epId) => ({{
            url: url,
            headers: {{
                ...{class_name}.headers,
                "Referer": `${{{base_url_ref}}}/`,
            }},
        }}),"""
        image_load_hook = ""

    # pages has a patch boundary: parsePagesCustom
    pages_fail_closed = enforce_fail_closed(pages_manual, "comic loadEp", True)

    if pages_manual_only:
        pages_body = f"            return await this.loadEpCustom(comicId, epId);"
        pages_custom_hook = """
    /**
     * Placeholder hook to be overridden by manual patch layer for Pages.
     */
    loadEpCustom = async (comicId, epId) => {
        throw new Error("MANUAL PATCH REQUIRED: loadEpCustom must be implemented in patch layer.");
    }"""
    elif pages_fail_closed:
        pages_body = f"            {pages_fail_closed}"
        pages_custom_hook = ""
    else:
        pages_custom_hook = ""
        if pages_uses_absolute_attribute:
            pages_images_js = f"            let images = imgElements.map(el => {pages_image_extractor}).filter(Boolean);"
        else:
            pages_images_js = f'''            let images = imgElements.map(el => el.attributes["{pages_img_attr}"]).filter(Boolean);'''
        pages_body = f"""            let url = epId.startsWith("http") ? epId : `${{{base_url_ref}}}${{epId}}`;
            let res = await Network.get(url, {class_name}.headers);
            if (res.status !== 200) {{
                throw new Error(`Failed to load episode, status: ${{res.status}}`);
            }}
            let doc = new HtmlDocument(res.body);
            let imgElements = doc.querySelectorAll("{pages_selector}");
{pages_images_js}
            doc.dispose();

            // Hook for custom page transformations (e.g. MotionToon / AuthorNotes)
            images = this.parsePagesCustom(images, res.body);

            return {{
                images: images,
            }};"""

    chapters_is_json = chapters_dict.get("isJson", False)
    if not chapters_is_json and chapters_dict.get("selector"):
        chap_sel = chapters_dict.get("selector")
        chap_url_field = chapters_dict.get("fields", {}).get("url", "@href")
        chap_title_field = chapters_dict.get("fields", {}).get("name", "text")
        chap_reverse = chapters_dict.get("reverse", False)

        url_extractor = parse_field_extractor(
            "url", chap_url_field, "el", "url", absolute_url_resolver
        )
        title_extractor = parse_field_extractor(
            "name", chap_title_field, "el", "url", absolute_url_resolver
        )

        reverse_js = "        chaptersList.reverse();\n" if chap_reverse else ""

        chapters_body = f"""    loadChapters = async (comicUrl) => {{
        let url = comicUrl.startsWith("http") ? comicUrl : `${{{base_url_ref}}}${{comicUrl}}`;
        let res = await Network.get(url, {class_name}.headers);
        if (res.status !== 200) {{
            throw new Error(`Failed to load chapters, status: ${{res.status}}`);
        }}
        let doc = new HtmlDocument(res.body);
        let elements = doc.querySelectorAll("{chap_sel}");

        let chaptersList = elements.map(el => ({{
            id: {url_extractor},
            title: {title_extractor},
        }}));
{reverse_js}
        let chaptersObj = {{}};
        for (let ch of chaptersList) {{
            if (ch.id) {{
                chaptersObj[ch.id] = ch.title || "";
            }}
        }}
        doc.dispose();

        // Hook for custom chapter parsing
        return this.parseChaptersCustom(chaptersObj, res.body);
    }}"""
        chapters_fail_closed = ""
        parse_chapters_custom = f"""    /**
     * Placeholder hook for custom chapter transformations.
     */
    parseChaptersCustom = (chaptersObj, htmlBody) => {{
{"        throw new Error('MANUAL PATCH REQUIRED: parseChaptersCustom must be implemented in patch layer.');" if chapters_manual else "        return chaptersObj;"}
    }}"""
    else:
        if chapters_fail_closed:
            chapters_body = f"""    loadChapters = async (comicUrl) => {{
{chapters_fail_closed}
    }}"""
            parse_chapters_custom = ""
        else:
            chapters_body = f"""    /**
     * [MANUAL PATCH HOOK] Load and parse chapters
     * Upstream Webtoons uses mobile JSON API:{' ' + chapters_url if chapters_url else ''}
     * Manual patch is required for episode title parsing, season numbering, and offsets.
     */
    loadChapters = async (comicUrl) => {{
        return this.parseChaptersCustom(comicUrl);
    }}"""
            parse_chapters_custom = f"""    /**
     * Placeholder hook to be overridden by manual patch layer.
     */
    parseChaptersCustom = async (comicUrl) => {{
        throw new Error("MANUAL PATCH REQUIRED: parseChaptersCustom must be implemented in patch layer.");
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

    absolute_url_helper = ""
    if uses_absolute_attributes:
        absolute_url_helper = r'''

    static resolveAbsoluteUrl = (rawValue, requestUrl) => {
        if (rawValue === null || rawValue === undefined || rawValue === "") {
            return "";
        }

        let raw = String(rawValue);
        if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(raw)) {
            return raw;
        }

        let baseMatch = String(requestUrl || "").match(/^([A-Za-z][A-Za-z0-9+.-]*:)\/\/([^/?#]+)([^?#]*)(\?[^#]*)?(?:#.*)?$/);
        if (!baseMatch) {
            return raw;
        }

        let origin = baseMatch[1] + "//" + baseMatch[2];
        let basePath = baseMatch[3] || "/";
        let baseQuery = baseMatch[4] || "";

        if (raw.startsWith("//")) {
            return baseMatch[1] + raw;
        }
        if (raw.startsWith("#")) {
            return origin + basePath + baseQuery + raw;
        }
        if (raw.startsWith("?")) {
            return origin + basePath + raw;
        }

        let suffixAt = raw.search(/[?#]/);
        let suffix = suffixAt === -1 ? "" : raw.slice(suffixAt);
        let rawPath = suffixAt === -1 ? raw : raw.slice(0, suffixAt);
        let path = rawPath.startsWith("/")
            ? rawPath
            : basePath.slice(0, basePath.lastIndexOf("/") + 1) + rawPath;
        let trailingSlash = path.endsWith("/") || path.endsWith("/.") || path.endsWith("/..");
        let segments = [];
        for (let segment of path.split("/")) {
            if (!segment || segment === ".") {
                continue;
            }
            if (segment === "..") {
                segments.pop();
            } else {
                segments.push(segment);
            }
        }

        let normalizedPath = "/" + segments.join("/");
        if (trailingSlash && normalizedPath !== "/") {
            normalizedPath += "/";
        }
        return origin + normalizedPath + suffix;
    }'''


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
    key = "{sanitized_key}"
    version = "{source_version}"
    minAppVersion = "1.6.0"{base_url_getter}
    static mobileUrl = "{mobile_url}"

    static headers = {{
{headers_code}
    }}{settings_code}{cookies_init}{absolute_url_helper}
{static_catalog_code}
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

{image_load_body}

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
{f'''
    /**
     * Placeholder hook to be overridden by manual patch layer for Details.
     */
    parseDetailsCustom = (comicDetails, htmlDoc) => {{
        throw new Error('MANUAL PATCH REQUIRED: parseDetailsCustom must be implemented in patch layer.');
    }}
''' if details_manual else ""}
{explore_hooks_code}{search_custom_hook}{parse_chapters_custom}{pages_custom_hook}{image_load_hook}

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
