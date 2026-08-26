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

## Source Registry

`sources_registry.json` is the canonical development-time taxonomy for catalog
artifacts. Its unique `artifactId` is the final JavaScript filename stem;
`runtimeKey` is a separate, opaque installation identity and must remain
compatible with shipped sources. Optional metadata is omitted when it cannot be
backed by reliable evidence.

Validate registry structure, final-JS identities, converted-IR links, and
catalog drift without modifying `index.json`:

```bash
python tools/source_conversion/validator/validate_registry.py
```

Structural or identity violations are emitted as `ERROR`. Stale catalog
name/version/key metadata is emitted as `WARNING`, while explicitly modeled
shared installation slots are emitted as `REPORT`.

Registry `locales` describe the source instance, not every language returned by
the source, query-language support, content origin, or a mandatory search
filter. The accepted bounded grammar is a 2-3 letter lowercase language subtag,
an optional Titlecase four-letter script subtag, and an optional uppercase
two-letter or three-digit region subtag (for example `en`, `ja`, `zh-Hans`,
`zh-Hant`, or `pt-BR`). Omission means unknown. Empty arrays, duplicates,
and non-canonical casing are invalid. The registry grammar does not reserve
`all`: as a primary language subtag it may legitimately mean Allar. This is
distinct from Keiyoushi's operational `all` sentinel. Future upstream
inventory or extraction must not copy that sentinel into `locales` or normalize
it to `en`, `mul`, or a guessed locale; when no reliable source-instance locale
is available, `locales` remains omitted. That ingestion rule is outside the
current registry validator.

`contentWarning` is optional and, when present, is exactly `SAFE`, `MIXED`, or
`NSFW`. Omission means unknown and never defaults to `SAFE`. Stable imported
source locators are `upstream.project`, `upstream.module`, and
`upstream.sourceId`; `upstream.version`, `upstream.extensionLib`, and
`upstream.commit` are reproducibility snapshots. Normal registry validation is
local and does not fetch or execute an upstream checkout.

Runtime capabilities and transient workflow or session state are deliberately
outside this registry. Final JavaScript remains authoritative for runtime
`name`, `key`, and `version`, and taxonomy metadata does not participate in
canonical index derivation.

## Upstream Inventory Contract

`schema/upstream_inventory.schema.json` defines the future generated inventory
record without checking in a production inventory. Root `upstreams` entries pin
each unique upstream `project` to one immutable `commit`; every resolved
candidate and unresolved module must refer to a declared project snapshot.

One resolved candidate is identified only by `(project, sourceId)`. `sourceId`
is an opaque JSON string; `module` is a required current upstream locator and
may change without redefining the candidate. The smallest candidate requires
`project`, `sourceId`, `module`, raw upstream `name`, raw `upstreamLang`, and
`compatibility`. `canonicalLocale`, `baseUrl`, `contentWarning`, `theme`,
`version`, and `extensionLib` are optional evidence or derived values. The
pinned commit is owned once by the root snapshot rather than duplicated across
candidates.

Raw `upstreamLang: "all"` stays raw and does not imply a `canonicalLocale`;
omission means the normalized locale is unresolved. A dynamic module whose
source instances or IDs cannot be established belongs in `unresolvedModules`,
with `project`, current `module`, and a structured `reason.code`. It has no
guessed `sourceId` and does not participate in candidate identity uniqueness.

Compatibility observations are orthogonal:

- `metadataResolution`: `static` or `evaluated`
- `extraction`: `generic`, `adapter`, `manual`, or `unsupported`
- `patchRequired`: boolean

Readiness is derived from those observations; it is not a separately maintained
truth. For example, `extraction: "adapter"` and `patchRequired: true` may
coexist.

Validate an inventory locally, with optional read-only registry join checking:

```bash
python tools/source_conversion/validator/validate_inventory.py inventory.json
python tools/source_conversion/validator/validate_inventory.py inventory.json \
  --registry sources_registry.json
```

The validator uses no network access and performs no Gradle or upstream build.
With `--registry`, it computes and reports zero, one, or multiple matching
artifact IDs from explicit registry `(upstream.project, upstream.sourceId)`
metadata. Candidates do not persist those derived results. `runtimeKey`, names,
and URLs never participate in candidate identity or registry joins, and invalid
or ambiguous registry upstream mappings fail closed.

Ownership remains separated: the inventory persists pinned upstream evidence
and compatibility observations; the registry owns artifact/runtime/provider
identities and shared-runtime-key groups; login state, cookies, selected
mirrors, and live site health remain runtime-only. Manual overrides are deferred
until a concrete non-derivable exception requires one.

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
