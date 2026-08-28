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

`schema/upstream_inventory.schema.json` defines the generated inventory record.
`inventory/upstream_inventory.json` is the canonical checked-in snapshot of what
exists in the exact pinned upstream checkout. It is upstream evidence only, not
runtime, import, conversion, registry, or generated-JavaScript ownership. Root
`upstreams` entries pin each unique upstream `project` to one immutable
`commit`; every resolved candidate and unresolved module must refer to a
declared project snapshot.

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
- `extraction`: `unclassified`, `generic`, `adapter`, `manual`, or `unsupported`
- optional `patchRequired`: omitted when unknown, otherwise an evidence-backed
  boolean classification

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

### Deterministic static inventory generation

`inventory/generate_static_inventory.py` discovers `src/**/build.gradle.kts`
modules in stable repository-relative order and reuses the existing Gradle
parser. Repository-relative module segments are lowercased to the accepted B1
locator grammar, with collisions rejected rather than merged. A source block
becomes a candidate only when its raw name, raw language,
and authoritative explicit or parser-derived source ID are all static. Dynamic
or missing required metadata produces a module record with one of three bounded
reason codes: `unresolved-required-metadata`, `no-source-blocks`, or
`static-parse-error`. Optional base URL, content warning, theme, version, and
extension-library metadata are emitted only when statically resolved. No locale
is inferred, so raw `upstreamLang: "all"` remains `"all"` and does not produce a
`canonicalLocale`.

The CLI reads `git rev-parse --verify HEAD` with a process-local
`safe.directory` override, without changing Git config or repository state, and
can enforce an exact expected commit. It does not run Gradle or Kotlin and
refuses to write output inside the supplied upstream checkout. Omitting
`--output` writes JSON to stdout; file output always requires an explicit path:

```bash
python tools/source_conversion/inventory/generate_static_inventory.py \
  --extensions-root ../extensions-source \
  --project keiyoushi/extensions-source \
  --expected-commit 5e06c412c0264b18120fd963fdd6efb529f3fa29
```

Serialization is UTF-8 JSON with controlled field insertion order, two-space
indentation, `ensure_ascii=False`, and exactly one LF at EOF. Candidates sort by
`(project, sourceId, module, name, upstreamLang)` and unresolved modules sort by
`(project, module, reason.code)`. There are no timestamps, absolute paths,
filesystem metadata, runtime keys, registry-owned artifact IDs, or candidate
commit copies. B2 records `metadataResolution: static` and
`extraction: unclassified`, omitting `patchRequired`, because discovery does
not evaluate conversion or patch compatibility. `unsupported` and explicit
patch booleans are reserved for candidates with classification evidence.

The parser also performs bounded declarative source expansion. Its complete
evaluation surface is deliberately small: quoted strings, integer/long
literals, direct immutable `val` aliases, complete literal `listOf` and
`mapOf` collections, direct `forEach` over those collections, two-item map
destructuring, literal-only string interpolation/concatenation, and source
metadata assignments selected by `binding == literal`, `binding != literal`,
or `when (binding)` literal branches. The implicit `it` loop binding and an
explicit single binding are supported. A direct `deeplink` sibling is ignored
as inert metadata while the source template is expanded; other loop-body
statements, nested iteration, shadowing, mutable bindings, incomplete
collections, duplicate map keys, or unsupported expressions invalidate the
whole affected template rather than producing a partial result.

Expansion is capped at `MAX_STATIC_EXPANSION = 512` source instances per
module, comfortably above the pinned maximum of 108, and literal/alias
resolution is capped at 16 levels. Limit overflow, binding cycles, ambiguous
bindings, unresolved predicates, or duplicate final `(project, sourceId)`
identities fail closed. Auto IDs continue to use the existing authoritative
final `(name, lang, versionId)` algorithm; a deterministically nonmatching
conditional explicit-ID branch permits normal auto-ID generation, while an
ambiguous branch never does.

Everything outside that grammar remains evaluated-only: arbitrary function
calls and helpers, providers, project/system/environment properties,
filesystem or network access, time/randomness, mutable collections, collection
transforms such as `filter`, `map`, or `flatMap`, plugin callbacks, external
build-state conditions, unknown property access, and unknown expressions. The
static parser never executes these constructs, and this inventory command does
not implement or invoke an evaluated Gradle fallback.

Ownership remains separated: the inventory persists pinned upstream evidence
and compatibility observations; the registry owns artifact/runtime/provider
identities and shared-runtime-key groups; login state, cookies, selected
mirrors, and live site health remain runtime-only. Manual overrides are deferred
until a concrete non-derivable exception requires one.

### Canonical inventory lifecycle

Ad-hoc generation remains available through stdout or an explicit `--output`.
The fixed canonical path can only be managed through mutually exclusive
`--write` and `--check` modes. Both modes require the exact canonical project
and full pin, prove that `--extensions-root` is the Git top-level at that HEAD,
and accept any configured fetch-remote name whose normalized GitHub HTTPS or SSH
URL identifies `keiyoushi/extensions-source`. They do not fetch or alter Git
configuration.

Both modes generate twice in memory and fail closed on semantic or byte-order
nondeterminism. Generated data is checked with the existing inventory validator,
joined to registry upstream metadata only by `(project, sourceId)`, and gated by
the existing whole-repository registry validator. `--check` requires the
snapshot to exist, never repairs it, and distinguishes semantic inventory drift
from byte-only serialization drift. `--write` treats an absent snapshot as a
bootstrap, prints an ephemeral deterministic review summary, writes a
same-directory temporary file only after every guard passes, and atomically
replaces the canonical path. No summary or hash sidecar is persisted.

```bash
python tools/source_conversion/inventory/generate_static_inventory.py \
  --extensions-root ../extensions-source \
  --project keiyoushi/extensions-source \
  --expected-commit 5e06c412c0264b18120fd963fdd6efb529f3fa29 \
  --write

python tools/source_conversion/inventory/generate_static_inventory.py \
  --extensions-root ../extensions-source \
  --project keiyoushi/extensions-source \
  --expected-commit 5e06c412c0264b18120fd963fdd6efb529f3fa29 \
  --check
```

The exact-path `.gitattributes` rule keeps the canonical JSON LF-normalized in
both the Git index and Windows working tree without normalizing unrelated files.

## Deterministic eligibility planner

`planner/eligibility_planner.py` is a read-only planning boundary over the
canonical inventory, the registry, and a clean checkout at the inventory pin.
It validates those inputs, scans Kotlin/Gradle text for bounded capability
signals without executing extension code, and writes one deterministic JSON
report to stdout. It has no report-file mode and does not update the inventory,
registry, index, IR, generated sources, or patches.

```bash
python tools/source_conversion/planner/eligibility_planner.py \
  --extensions-root ../extensions-source
```

The normalized report has three levels. A family owns references to explicit
member modules; a module summarizes its candidate routes; and each candidate
owns exactly one canonical `(project, sourceId)` identity and its module
locator. Families are derived only from explicit upstream `theme` metadata and
multi-candidate module identity. No name, hostname, URL, or language similarity
creates a family.

Candidate eligibility uses these fail-closed routes:

- `E0`: exactly one existing registry upstream-identity join
- `E1`: explicit inventory `generic` extraction evidence
- `E2`: explicit inventory `adapter` extraction evidence
- `E3`: an explicit theme or multi-candidate-module relationship
- `E4`: explicit inventory `manual` extraction evidence
- `E5`: explicit evidence that required core extraction is `unsupported`
- `E6`: unknown or insufficient static evidence

Registry upstream identities that resolve to zero or multiple inventory
candidates, and candidate identities joined to multiple registry artifacts,
fail closed. Runtime keys, artifact IDs, filenames, import state, and generated
paths are never created. Existing artifact IDs appear only as the evidence for
an exact E0 registry join.

Patch state is orthogonal: an explicit `patchRequired: false` is
`not-required`, `true` is `required`, and omission remains `unknown`. Likewise,
`contentWarning` is reported as metadata but never changes E0-E6. Raw upstream
language is preserved; in particular, raw `zh` is not normalized to `zh-Hans`
or `zh-Hant`.

Credentials/token, WebView/QuickJS, crypto/decoder, request-signing, image-
interceptor, user-configuration, and static-local-catalog matches are lexical
evidence flags only. A flag alone never implies `E5`; absent explicit required-
core evidence, the route remains `E6` or the independently justified family
route. Current-pin counts live only in integration tests and report summaries,
not planner rules.

The accepted eight-member MangaCatalog set may appear under `proposals` only
when all named candidates still resolve uniquely in the explicit theme and
remain `E3`. It is labeled `review-only`, is selected by the bounded proposal
rule rather than `contentWarning`, and does not create imports or artifacts.

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
## Canonical Materializer (P2C v0.1)

The `materialize.py` script transforms a reviewed local identity plan, canonical inventory, and a pinned upstream checkout into a deterministic repository transaction.

### Scope and Limitations
P2C v0.1 supports **generated / NO-PATCH CREATE only**.
The following are **unsupported**:
- updates, renames, migrations, or deletions
- sources requiring manual patches (`manualPatchRequired: true` or `PATCH_REQUIRED`)
- mass discover-and-write (transactions must be explicitly planned)
- automatic version bumping

### Identity and Metadata
- **`artifactId`**: The local generated filename stem (e.g., `test_source`). Distinct from the opaque runtime ID.
- **`providerId`**: The explicit local provider ownership string.
- **`localVersion`**: The explicit local version (e.g., `1.0.0`), separate from the `upstreamVersion` provided by the original extension.
- **`sourceId`**: The inventory-resolved upstream source identity used to locate the candidate.

### Explicit Plan Contract
The materializer requires a strict, explicit local plan in JSON format.
- `generatedTimestamp` must be a strict explicit UTC ISO-8601 string (e.g., `YYYY-MM-DDTHH:MM:SSZ`).
- Unknown fields at the top level, `upstream`, or artifact items are rejected.
- Naive timestamps, malformed values, and non-UTC offsets are rejected.

**Synthetic Plan Example:**
```json
{
  "schemaVersion": "1",
  "upstream": {
    "project": "keiyoushi/extensions-source",
    "commit": "5e06c412c0264b18120fd963fdd6efb529f3fa29"
  },
  "generatedTimestamp": "2023-10-15T12:00:00Z",
  "artifacts": [
    {
      "sourceId": "123456789",
      "artifactId": "test_artifact",
      "providerId": "my_provider",
      "localVersion": "1.0.0"
    }
  ]
}
```

### Safety Guards
- **Upstream Provenance**: Reads actual extensions checkout using `git rev-parse HEAD` and `git status --porcelain` to ensure the exact expected commit and a clean working tree.
- **Stale-State Guard**: The preflight registry and index fingerprints are captured and re-verified immediately before promotion. Any drift aborts the transaction.
- **Collision Rejection**: Artifacts and files already existing in the repository abort the transaction.
- **Two-Pass Determinism**: Executes extraction and generation twice in separate temporary directories, asserting byte-identical results and identical SHAs.
- **Transaction Digest**: Normalized hash over the reviewed inputs (schemaVersion, upstream project/commit, generatedTimestamp, artifact inputs) and the resulting target file SHAs.

### Promotion and Rollback (Same-Filesystem Atomic)
For every target file, a temporary sibling (`.tmp`) is prepared on the same filesystem directory as its destination.
Only after complete preparation are they atomically promoted using `os.replace`.
- **Promotion Order**: New artifact files are promoted first, followed by shared registry and index files last.
- **Rollback Guarantees**: Any failure during copy or promotion triggers a transaction-owned rollback. Shared files are restored, created temporary siblings and final paths are unlinked, and empty transaction-created directories are cleaned. Unrelated files are untouched. No partial files are ever exposed.

### Modes

#### CHECK Mode
Executes the real transaction preparation path (extraction, validation, determinism pass, digest calculation) but performs **ZERO live repository writes**.

```bash
python tools/source_conversion/materializer/materialize.py \
  --mode check \
  --plan plan.json \
  --repo-root . \
  --extensions-root ../extensions-source
```

#### WRITE Mode
Executes the same verified prepared transaction as CHECK mode. Upon passing the stale-state revalidation, the prepared temporary transaction is atomically promoted to the live repository.

```bash
python tools/source_conversion/materializer/materialize.py \
  --mode write \
  --plan plan.json \
  --repo-root . \
  --extensions-root ../extensions-source
```
