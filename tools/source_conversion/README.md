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

## Existing pipeline

Pinned static inventory candidate `(project, sourceId)` and module locator
→ canonical E0–E6 eligibility/family report → explicit reviewed local identity
plan → canonical extraction dispatch → validated IR → generated base JS
→ source patch where supported → final root JS → registry validation and
canonical index derivation → reviewed materializer transaction.

Inventory, registry, adapters, generator, patcher, and materializer remain the
single existing pipeline. The batch report is a read-only view over it. It does
not assign local identities or turn an eligibility observation into a write.

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
  --extensions-root "<exact-census-checkout>" \
  --project keiyoushi/extensions-source \
  --expected-commit 5a0261c718cd6d5ecf14963d837f29024c792398
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
  --extensions-root "<exact-census-checkout>" \
  --project keiyoushi/extensions-source \
  --expected-commit 5a0261c718cd6d5ecf14963d837f29024c792398 \
  --write

python tools/source_conversion/inventory/generate_static_inventory.py \
  --extensions-root "<exact-census-checkout>" \
  --project keiyoushi/extensions-source \
  --expected-commit 5a0261c718cd6d5ecf14963d837f29024c792398 \
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

## 9A language-agnostic batch planning

The existing planner accepts `--batch`, repeatable `--locale`, `--eligibility`,
and `--source-id`. Any selection option enables the batch view. Output stays on
stdout; there is no production write or automatic identity-plan creation.
`schemaVersion: "1.1"` retains the original complete E0–E6 report and adds a
`batch` extension (`schemaVersion: "1.0"`). Legacy calls without these options
retain the original report format. `schema/batch_report.schema.json` describes
the extension, and its standard-library validator checks schema and semantic
counts, identity uniqueness/order, actions, and the empty publication delta.

The `batch.candidates` view contains candidate identity, raw language, normalized
locale, family, actual dispatch adapter, E0–E6 eligibility, state, action,
reason codes, warnings, imported artifact/provider/runtime identities, catalog
name, current local and upstream versions, proposed upstream version, patch
state/path, shared-key group, and auth/JS-heavy review evidence. The proposed
local version remains null until explicitly supplied in a materializer plan.
Unimported artifact IDs, runtime keys, providers, and filenames also remain null:
they are local reviewed identities, not inferred from display names or locales.

Locales use the existing registry/inventory grammar: language, optional script,
and optional region. Casing and underscores normalize deterministically.
`canonicalLocale` evidence takes precedence; otherwise raw upstream language is
normalized without changing inventory bytes. Bare `zh` stays `zh`. `all` and
`other` remain unresolved. `zh-TW`, `zh-HK`, and `zh-MO` match a `zh-Hant` filter;
`zh-CN` and `zh-SG` match `zh-Hans`, with the regional label retained in output.
No name, URL, or module language is used to guess a Chinese script. Explicit
script filters also include corresponding tags with a region suffix.

All unresolved locales are retained in `batch.unresolvedLocales` even when a
locale filter excludes them. All unresolved modules remain visible because
their source languages and identities are unknown. `--include-unresolved-locales`
also includes generic `zh` and unresolved-language rows in the selected view.
This is an evidence boundary, not a claim that the static inventory captures
every source in evaluated-only modules.

The 9B read-only entry point (no 9B import is performed by 9A):

```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
python -B tools/source_conversion/planner/eligibility_planner.py `
  --extensions-root ../extensions-source `
  --batch --locale zh-Hant --locale zh-Hans
```

Add `--include-unresolved-locales` to include undecided source languages in the
selected candidate rows; use `--locale en` or another concrete locale for the
same contract. `--eligibility E1 --eligibility E2` filters existing eligibility
routes; it does not assert that extraction or runtime validation has passed.
`--repo-root` selects the local artifact evidence root and defaults to the
registry file's directory. Reports contain no timestamps or absolute paths.
Identical input produces identical UTF-8 JSON bytes, sorted selection options,
candidates, warning/reason arrays, group membership, and summary counts.

### Classification and failure isolation

- `ELIGIBLE`: existing evidence permits a reviewed identity plan and CHECK.
  It is not runtime acceptance or permission to publish.
- `ALREADY_IMPORTED`: the exact registry join exists; action is `skip`.
- `UPDATE_AVAILABLE`: a numeric upstream version is newer; action is review
  only. Upstream refresh remains unsupported by the materializer.
- `UNSUPPORTED_ADAPTER`: explicit unsupported core evidence or a theme with no
  matching dedicated family adapter. No missing adapter is implemented here.
- `PATCH_REQUIRED`: explicit patch/manual extraction evidence; no patch is
  generated or overwritten.
- `UNRESOLVED_METADATA`: locale or extraction evidence remains insufficient.
- `BLOCKED`: explicit retired/needs-rescue registry state or backward upstream
  version. No live dead/unreachable status is inferred.
- `ERROR`: a source unit or local artifact could not be read/checked. Other
  candidate classifications are retained; module errors affect only that module,
  and theme errors affect only its explicit members.

Malformed inventory/registry data, duplicate candidate identities, and ambiguous
registry ownership still fail the whole input validation before reporting or
publication. They are not silently deduplicated. Lexical credentials and
WebView/QuickJS matches are orthogonal review flags; confirmed auth requirements
are exposed only when local IR supplies evidence. Live anti-bot state, login
state, cookies, and site reachability remain unknown without runtime evidence.
NSFW/MIXED/SAFE metadata is retained for every locale; absence remains unknown.

`existingArtifacts` also includes manual sources with no upstream join.
`sharedRuntimeKeyGroups` exposes the complete explicit registry groups, including
CopyManga standard/multi-account. Distinct artifact IDs are retained. Shared
keys are never join keys, and unmodeled collisions remain publication errors.
Patch-backed and manually customized existing sources remain protected. A changed
generator or adapter does not automatically regenerate them; UPDATE always
requires an explicit plan/version and a fresh CHECK.

### Batch CHECK and publication boundary

Select candidates → review explicit local identity plan → materializer CHECK
→ review exact target hashes and index/registry deltas → WRITE with the CHECK
digest. Existing multi-artifact identity plans are reused; mixed CREATE/UPDATE,
patch-backed UPDATE, upstream refresh, renames, and deletions remain unsupported.
The planner's publication manifest and deltas are empty because no local
publication identities or outputs have been prepared there. The materializer's
CHECK computes the exact concrete publication manifest and deltas.

The materializer prepares every artifact in OS Temp and reports all per-artifact
preparation failures before aborting the batch. Successful siblings are never
partially published. Re-running the same valid plan produces the same prepared
bytes. Registry/index validation and two-pass determinism are global batch gates.
The existing transaction owns promotion, stale checks, and rollback; individual
file promotion is atomic, while detected transaction failures restore prior
bytes. Process termination/power loss is not a globally atomic filesystem commit.

Planning scans module/theme source text once and loads inventory/registry once.
Materializer candidate resolution uses a single identity map, and each transaction
captures shared state rather than hashing the repository for every candidate.
CHECK still intentionally runs two extraction/generation passes and validates the
complete proposed registry/index overlay twice.

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
P2C v0.1 supports **generated / NO-PATCH CREATE** plus a deliberately narrow
**generated / NO-PATCH UPDATE v0.1**. UPDATE is implementation-only
regeneration of an existing artifact; it is not an upstream refresh. The
existing upstream `project`, `module`, `sourceId`, and `commit` must match the
reviewed plan and current registry exactly.
Candidate readiness is not stored as a `"COMPATIBLE"` inventory sentinel. The
materializer calls the canonical eligibility planner over the validated
inventory and live registry. CREATE accepts planner routes `E1`, `E2`, and
`E3`; UPDATE additionally accepts `E0` for the exact existing artifact. Routes
`E4`, `E5`, and `E6` are rejected. An explicit planner patch state of `required`
is rejected before extraction; otherwise the extracted IR must still prove that
no manual patch is required before final JS can be proposed.

The following are **unsupported**:
- patch-backed UPDATE and sources requiring manual patches
  (`manualPatchRequired: true` or `PATCH_REQUIRED`)
- upstream refresh, upstream commit migration, or upstream source migration
- renames, migrations, or deletions
- UPDATE major/minor changes or skipped patch versions
- mass discover-and-write (transactions must be explicitly planned)
- automatic version calculation or bumping

### Identity and Metadata
- **`artifactId`**: The local generated filename stem (e.g., `test_source`). Distinct from the opaque runtime ID.
- **`providerId`**: The explicit local provider ownership string.
- **`localVersion`**: The explicit local version (e.g., `1.0.0`), separate from the `upstreamVersion` provided by the original extension.
- **`sourceId`**: The inventory-resolved upstream source identity used to locate the candidate.
- **`moduleAssert`**: An optional exact assertion over the inventory module locator. Inventory modules remain dot-separated; the materializer translates that locator to a source-tree path and delegates all source-family selection to `extract.py::dispatch_extraction`.

- **`expectedCurrentLocalVersion`**: The explicit current local version (required for UPDATE).
- **`newLocalVersion`**: The explicit next patch version (required for UPDATE). UPDATE requires the same major and minor components and exactly `current.patch + 1`.
- **`operation`**: Optional top-level field `create` (default) or `update`.

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
- **Upstream Provenance**: Reuses the planner checkout attestation to verify the supplied root is the Git top-level, its actual `HEAD` equals the inventory/plan pin, and its tracked and untracked state is clean before extraction.
- **Canonical Eligibility**: Reuses `eligibility_planner.build_plan`; the materializer does not reinterpret structured `compatibility` fields or duplicate E0-E6 derivation rules.
- **Stale-State Guard**: Preflight fingerprints cover the registry, index, root final JS files, generated base JS files, and converted IR files consumed by proposal preparation. The complete fingerprint is repeated immediately before publication. CREATE also repeats all new-target absence checks. Any drift aborts before a transaction target is published.
- **Collision Rejection**: Artifacts and files already existing in the repository abort the transaction.
- **Two-Pass Determinism**: Executes extraction and generation twice in separate temporary directories, asserting byte-identical results and identical SHAs.
- **Transaction Digest**: Normalized hash over the reviewed inputs (schemaVersion, upstream project/commit, generatedTimestamp, artifact inputs) and the resulting target file SHAs. For UPDATE, it additionally binds stable repository-relative paths and exact current SHA-256 values for every updated root JS, generated base JS, and IR file, plus global `index.json` and `sources_registry.json`. The low-level legacy digest remains stable, but public CHECK/WRITE now uses digest version 2 with complete review-state binding.
- **Complete Proposal Validation**: Each pass builds a temporary overlay containing existing and proposed final JS/IR plus the complete proposed registry. The canonical registry validator checks schema, runtime identity, IR linkage, and index relationships before publication.
- **Canonical Index Bytes**: Proposed `index.json` bytes are produced by `validate_registry.py`'s canonical `write_index` implementation, including its ordering, formatting, UTF-8 encoding, and trailing newline.

### Promotion and Rollback (Per-Target Same-Filesystem Atomicity)
For every target file, an exclusive random temporary sibling is created on the
same filesystem and recorded before copying begins. A partial or failed copy is
therefore transaction-owned and removable. CREATE artifact files use an atomic
hard-link create that cannot overwrite a concurrently appearing destination.
UPDATE artifact files use sequential same-filesystem `os.replace` operations;
`index.json` is replaced only after all UPDATE artifact files have been
published. UPDATE reads and validates `sources_registry.json`, binds its exact
bytes into the reviewed digest and stale-state guard, but does not include it in
the output target manifest or rewrite it.

- **Promotion Order**: CREATE promotes artifact files, registry, then index. UPDATE promotes IR, generated base JS, and root JS for each artifact, followed only by `index.json`.
- **Rollback Guarantees**: Any failure during copy or promotion triggers a transaction-owned rollback. UPDATE restores every replaced artifact and `index.json` to its exact prior bytes; its registry is never a publication or rollback target. CREATE removes transaction-created outputs. Temporary siblings and empty transaction-created directories are cleaned, and unrelated files are untouched.
- **Atomicity Boundary**: Individual target publication is atomic, and detected failures are rolled back byte-for-byte. The materializer does not claim whole-filesystem global atomicity across all targets.

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
Executes the same verified prepared transaction as CHECK mode. Upon passing the
stale-state revalidation, the prepared temporary transaction is promoted to the
live repository. Both CREATE and UPDATE require the digest printed by a reviewed CHECK via
`--expected-digest`; stale CHECK output cannot authorize a WRITE.

```bash
python tools/source_conversion/materializer/materialize.py \
  --mode write \
  --plan plan.json \
  --repo-root . \
  --extensions-root ../extensions-source \
  --expected-digest <reviewed-check-digest>
```

### 9A transaction review binding

CHECK/WRITE reports use `schemaVersion: "1.1"`, `digestVersion: "2"`. The legacy
normalized transaction hash is wrapped with `reviewState`: sorted repository-
relative paths and exact SHA-256 values for registry, index, root JS, IR,
generated bases, patch files, canonical inventory, and the executing conversion
Python/schema inputs. Missing global inputs are represented explicitly. This
snapshot is captured before input loading and rechecked after preparation and
immediately before promotion. The UPDATE `currentState` subset remains available
for compatibility. Old public CHECK digests must be regenerated.

`targets` is the exact sorted publication manifest with SHA-256 and byte length.
`registryDelta` and `indexDelta` list sorted identity-keyed before/after records.
UPDATE retains the exact registry overlay and emits an empty registry delta;
intentional `catalogName`/`catalogDescription` overrides remain authoritative.
A no-patch UPDATE rejects root JS that differs from its stored generated base.

Generic extraction now uses the selected source declaration's language rather
than its module directory. IR v0.1/v0.2 accept the existing canonical locale
grammar instead of a four-language allowlist. With an authoritative source ID,
a generic runtime ID is `keiyoushi_<sourceId>`, independent of display-name
spelling or Unicode sanitization. Existing root/generated/IR artifacts are not
regenerated. An existing runtime key that differs from newly extracted identity
still fails UPDATE and requires separate reviewed migration. Legacy extraction
without a source declaration retains its old ID behavior. Source-specific
adapters keep their established identities, and generic Kotlin file fallback
selection is now sorted by repository-relative path.

Publication also requires an extracted `upstreamSourceId` matching the selected
candidate, and an exact language match against canonical or normalized raw
inventory evidence. Adapters missing that evidence fail CHECK; no ID or locale
is supplied on their behalf. UPDATE rejects any extracted upstream metadata
change, including version/library/theme changes, even if a local version bump
was requested. Both public report schemas are checked before WRITE.

CHECK stdout is a deterministic JSON document: internal extraction/validator
progress messages containing temporary paths are suppressed. Generator calls
require IR name, ID, languages, and base URL; missing values no longer silently
select English/Webtoons defaults. New CREATE preparation explicitly supplies the source's own
base URL as mobileUrl when absent. The generator retains its legacy mobile URL
fallback solely for historical IR reproduction; existing generated bytes and
production artifacts remain unchanged.


### 9C exact-pin Chinese family contracts

The six reviewed families are bound to upstream `keiyoushi/extensions-source`
commit `5a0261c718cd6d5ecf14963d837f29024c792398`. The closed candidate and file
SHA-256 manifest is `extractor/source_adapters/chinese_contracts.json`; every
listed Kotlin/build input must match before extraction. The planner requires
both that pin and the complete original inventory candidate record. A different
pin, identity, locale, or metadata record supplies no new eligibility evidence.
The inventory remains an unmodified static census; reviewed extraction evidence
is added by the planner. Bare `zh` is never assigned a script.

`familyContract` is an optional IR 0.2 enum selecting a fixed family emitter.
The IR records operation endpoints, language parameters, field/selector mappings,
pagination, ordering and access rules. The semantic validator compares the whole
contract and provenance to its reviewed candidate, allowing only local artifact
ID/version fields from an explicit publication plan. There is no user-defined
expression interpreter or downloaded-code execution. Other IR uses the existing
generator unchanged. Shared helpers are limited to HTTP/JSON/HTML lifecycle,
query and URL normalization, required-value checks and stable deduplication.
Templates are checked-in JSON so materializer review-state fingerprints include
them alongside Python and schema inputs.

| Family | Core reading contract | Explicit source IDs |
|---|---|---|
| all.globalcomix | API lists/search, numeric ID plus API-provided slug, all releases, premium exclusion, original ordered pages | zh-Hant: `3451257781273481191`, zh-Hans: `7151191693036508367` |
| all.namicomi | Locale/relationship DTOs, offset pagination, all chapter pages, 200-ID access checks, source-quality pages | zh-Hans: `1163192659786040070`, zh-Hant: `7859611418350123856` |
| zh.dongmanmanhua | HTML catalog/search/detail, daily calendar, bounded next-link chapter traversal, data-url images | zh-Hans: `4222375517460530289` |
| zh.iqiyi | HTML catalog/search/detail, JSON catalog with reversed episode order, HTML image fallback and paid rejection | zh-Hans: `2198877009406729694` |
| all.yellownote | Locale domains, explicit NSFW metadata, HTML catalog/detail, descending synthetic chapters, original image rewrite | zh-Hans: `170542391855030753`, zh-Hant: `4899554363948814001` |
| all.mangadex | Chinese locale DTOs, relationship join, paginated feed, unavailable/external filtering, original pages and expiring host refresh | zh-Hant: `1493666528525752601`, zh-Hans: `5148895169070562838` |

Relevant upstream implementations are the six modules' source class/factory and
DTO files, recorded individually with hashes in the manifest. GlobalComix uses
`GlobalComix.kt` and `dto/*`; NamiComi uses `NamiComi.kt` and its DTO/access models;
Dongman uses `DongmanManhua.kt`; iQiyi uses `Iqiyi.kt` and its catalog models;
YellowNote uses `YellowNote.kt`; MangaDex uses `MangaDex.kt` plus DTO/network
helpers. The manifest is authoritative for exact paths and capitalization.

The emitted sources support the anonymous, accessible core reading subset.
Optional accounts, purchase flows, user preference filters, and source-specific
bookmark functionality are outside this contract. NamiComi requires an explicit
positive access decision; unknown access never means free. GlobalComix rejects
paid/unknown page access. iQiyi preserves its paid-page rejection. Lexical auth
and WebView warnings remain visible in batch reports; reviewed basic-reading
auth is false only for these exact candidates. Network failures and changed
upstream responses fail explicitly and remain runtime acceptance work for 9D.
MangaDex identities are distinct from legacy `manga_dex`; no ownership migration
is implied. YellowNote retains NSFW labeling and needs that publication review.

`tests/test_chinese_families.py` uses sanitized static DTO-shaped JSON and DOM
fixtures derived from upstream fields/selectors. Generated JS executes offline
in QuickJS against mocked requests. The DOM harness supplies selector results;
it does not replace physical host HTML-selector/network acceptance. Tests cover
locale identity, dispatch and drift rejection, schema/semantic IR validation,
first/next/final pagination, stable chapter/page order, deduplication, access
rejection, URL/quality transformations, empty/error responses and old-pin
non-promotion. Existing materializer, registry, index and generator regressions
must continue to pass. No production artifacts are created by these tests.

#### Deferred contract work at the same exact pin

| Family | Selected count | Missing bounded capability | Follow-up |
|---|---:|---|---|
| Kuaikan | 1 | Core operations execute downloaded `window.__NUXT__` data scripts; define and test a data-only serialization decoder before use | Additional reviewed medium-risk family wave |
| Toomics | 2 | Escaped AJAX HTML, free/read chapter classes, and age-verification WebView/session boundary | 9F reviewed age/session contract |
| Mangadotnet | 1 | React Router `.data` flat reference graph, indexed keys and route payloads need bounded reference/depth/cycle validation | Dedicated RSC-data contract review |
| Tencent Comics | 1 | Downloaded nonce expression, retry and noise removal before Base64 JSON; preserve `canRead` rejection without general JS execution | 9F bounded nonce decoder |
| NoyAcg | 1 | Login/session generation, cookie host mapping, one-retry authentication and memo-sized page data | 9F host/session design review |
| Pixiv | 1 | Artwork/series/user identity, ranking-detail joins, stateful/adaptive paging and series ordering; optional login lookup needs a separate boundary | Dedicated typed API/iterator contract review |
| Creativecomic | 1 | Optional token or anonymous default, SHA-512 key/IV derivation, staged AES-CBC page key and binary image decryption | 9F image transport/decryption review |

Pixiv and Creativecomic are not classified as universally requiring login for
basic reading: the inspected source has optional login paths, and Creativecomic
has an explicit anonymous token fallback. None of these deferrals authorizes a
generic WebView/JavaScript evaluator, login architecture, ownership migration,
or age/payment gate bypass. The 74 bare-zh candidates remain locale-unresolved.

#### 9D canonical census checkpoint and pre-write boundary

The canonical publication inventory now binds to
`5a0261c718cd6d5ecf14963d837f29024c792398`: 1,396 modules, 2,212 candidates,
no unresolved modules, 984,378 bytes, SHA-256
`6dbfb04abad9736e94aafb3456a77232a61ef7caebd606746bd077b297573c90`.
The persistent read-only `extensions-source` checkout remains at
`5e06c412c0264b18120fd963fdd6efb529f3fa29`; existing source-level provenance
remains its historical extraction checkpoint. Supply an isolated clean Git tree
at the census pin for canonical inventory CHECK and materializer CHECK.

The full regression's live-checkout scanner accepts the explicit environment
variable `SOURCE_CONVERSION_TEST_EXTENSIONS_ROOT` for that isolated tree. It
still checks actual HEAD, cleanliness and exact output bytes; it never fetches
or changes the persistent checkout. For example, set the variable to the
verified OS Temp upstream root before `python -B -m unittest discover -s
tools/source_conversion/tests`.

The bounded 9D GlobalComix repair uses the API's explicit `slug` for detail
identity. Deriving a slug from a translated Chinese display name produced `-`
and returned the wrong comic in a live lookup. Missing slugs fail closed.

Live probes on 2026-09-07 found no titles in GlobalComix's `zh` catalog, and
iQiyi's legacy comic list/search routes redirected to its general homepage
from the test connection. Neither observation proves a usable Chinese read;
exclude these two primary instances from this pilot. Do not remap their
locales or substitute alternates. Every included instance requires its own
bounded list/detail/chapter/page/image preflight.

Regenerate inventory and eligibility, then run the exact candidate materializer
CHECK and review its identities, patch/access warnings, target manifest and
digest. The first Chinese multi-source CREATE still requires a fresh independent
pre-write review. Pin reconciliation and CHECK do not authorize production WRITE.

For census reproduction, set `PYTHONDONTWRITEBYTECODE=1`, use `python -B` for
every invocation, and use only OS Temp for an exact clean upstream tree and all
inventory/report files. Generate inventory with
`generate_static_inventory.py --extensions-root <temp-upstream> --project
keiyoushi/extensions-source --expected-commit <full-reviewed-sha> --output
<temp-inventory>`, then run `eligibility_planner.py --inventory <temp-inventory>
--registry sources_registry.json --extensions-root <temp-upstream> --batch
--locale zh-Hant --locale zh-Hans --repo-root .`. Capture stdout as UTF-8 bytes in
OS Temp. Repeat both generations, compare exact bytes, and run the canonical
inventory and batch validators plus their schemas. The guarded canonical
`--write` lifecycle is used only for reviewed inventory
checkpoint reconciliation; candidate source outputs remain temporary until the
independent production-write review.

### 9F-R1 chapter contract and MangaDex architecture

See [the consolidation audit and Windows handoff](CHINESE_CHAPTER_CONTRACT.md) for the canonical locale architecture, complete chronological chapter contract, live access-specific counts, and identity/restart verification.
