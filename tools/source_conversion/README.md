# Source Conversion Tooling

## Purpose
This tooling pipeline provides an automated and maintainable conversion bridge:
```
Keiyoushi / Mihon Kotlin Extension Source
                  ↓
Intermediate Representation (IR JSON)
                  ↓
Venera-Compatible JavaScript Source
```

## Milestone 1 Foundation
This directory currently contains the **foundational specifications and validator** created in Milestone 1:
- `schema/ir_v0_1.schema.json`: JSON Schema specification for IR v0.1.
- `validator/validate_ir.py`: Deterministic validator for IR definitions (Python standard library only).
- `tests/fixtures/`: Valid and invalid structural test fixtures.

### Future Milestones
Subsequent milestones will introduce:
- `extractor/`: Deterministic parser mapping Keiyoushi Kotlin extensions to IR JSON.
- `generator/`: Code generator emitting Venera `class extends ComicSource` JavaScript using native `HtmlDocument` and `Network` APIs.
- `patcher/`: Merge tool applying manual JS patches for complex or procedural logic.
- `Webtoons Pilot`: The first end-to-end verified source conversion.

## Repository Roles
- **`extensions-source`**: Strictly READ-ONLY reference and upstream input.
- **`venera-configs`**: Primary development repository for converter tooling, IR definitions, manual patches, and generated source files (`.js`).
- **`VeneraX`**: Flutter application runtime consumer.

## Planned First Bulk-Conversion Policy
When the converter pipeline is stabilized beyond the Webtoons pilot, future bulk conversion will follow this tiered policy:

### Included in First Bulk Wave
- **Simplified Chinese (`zh-Hans`)**
- **Traditional Chinese (`zh-Hant`)**
- **English SAFE (`en`, `contentWarning: SAFE`)**

### Schema Supported Only (Deferred from First Wave)
- **Korean (`ko`)** (targeted separately via native Strategy A architecture)

### Excluded from First Bulk Wave
- **English MIXED (`en`, `contentWarning: MIXED`)**
- **English NSFW (`en`, `contentWarning: NSFW`)**
- Other languages

## Extraction Field Grammar (IR v0.1)
The `fields` mapping in IR v0.1 definitions unambiguously distinguishes between element text extraction and attribute extraction:
- **Text Extraction:** Plain CSS selector string without `@` suffix.
  - Example: `".title"` -> extracts `element.querySelector(".title").text`.
  - Example: `"h1.subj, h3.subj"` -> extracts matched element's text.
- **Attribute Extraction:** Prefixed by `@` or suffixed with `@<attribute_name>`.
  - Example: `"@href"` -> extracts current element's `href` attribute.
  - Example: `"img@src"` -> extracts child `img` element's `src` attribute.
  - Example: `"@data-url"` -> extracts current element's `data-url` attribute.
- **JSON Field Mapping:** Direct key lookup or dot-separated path in JSON payloads.
  - Example: `"url": "viewerLink"` -> extracts `item["viewerLink"]`.

## Usage

### 1. Extract Webtoons IR
```bash
python tools/source_conversion/extractor/webtoons_extractor.py --extensions-root ../extensions-source --output sources_ir/webtoons.json
```

### 2. Validate an IR File
```bash
python tools/source_conversion/validator/validate_ir.py sources_ir/webtoons.json
```

### 3. Generate Venera Base JavaScript
```bash
python tools/source_conversion/generator/js_generator.py --input sources_ir/webtoons.json --output sources_generated/webtoons.base.js
```

### 4. Compose Final Venera JavaScript Source
```bash
python tools/source_conversion/patcher/js_patcher.py --base sources_generated/webtoons.base.js --patch sources_patches/webtoons.patch.js --output webtoons.js
```
