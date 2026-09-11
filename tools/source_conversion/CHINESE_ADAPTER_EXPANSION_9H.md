# 9H next Chinese adapter family

## Scope and baselines

9H remains limited to Chinese sources; English expansion is frozen. The writable
baseline is `venera-configs` commit
`a7ea993f4cdfd2d2f77e3868760a5122616d3255`. The read-only VeneraX Host is
`126a462debbe5b05a8c8d6e3dcb1b67fff1ebcdf`. The persistent upstream checkout
remained clean and read-only at
`5e06c412c0264b18120fd963fdd6efb529f3fa29`; extraction used a disposable
checkout of the canonical inventory pin
`5a0261c718cd6d5ecf14963d837f29024c792398`.

The untouched source-conversion baseline independently discovered and passed
653 tests. The 9G matrix was used as the authoritative 93-candidate input; it
was not rebuilt from scratch.

## Remaining-family ranking and selection

The canonical 9H matrix contains all 70 remaining or selected family rows and,
for every row, records language counts, live/dead evidence, authentication and
anti-bot boundaries, identity clarity, upstream pattern, parser/override/reader
complexity, expected yield, generic blast radius and the decision reason.

| Rank | Family | Candidates | 9G live bases | Auth / anti-bot | Risk | Expected yield | Decision |
| ---: | --- | ---: | ---: | --- | --- | ---: | --- |
| 1 | Manga18 | 1 | 1 | None | Low after review | 1 | Implemented and published |
| 2 | GalleryAdults | 5 | 5 | None identified | Medium-high | Unresolved | Deferred: raw `zh`, identity and NSFW semantics |
| 3 | Goda | 2 | 1 | None identified | Medium | 1 | Deferred: one 403 plus existing GoDa/18漫画 identity roles |
| 4 | HentaiHand | 2 | 2 | None identified | Medium | Unresolved | Deferred: identity and NSFW review |
| 5 | SinMH | 2 | 1 | None identified | Medium | 1 | Deferred: one 403 and unresolved script identity |
| 6 | MMLook | 2 | 0 | None identified | High | 0 | Deferred: TLS failure |
| 7 | MadaraLegacy | 1 | 0 | None identified | Medium-high | 0 | Deferred: 403 |

Manga18 was selected because its single HANMAN18 member is live, anonymous,
free of anti-bot bypass requirements, backed by one deterministic shared
upstream superclass, and has a unique source ID. Its HTML and Base64 reader
contract fits a small closed adapter and produces one real `zh-Hant`
publication. No second family met the same low-risk boundary after reranking.

## Bounded Manga18 implementation

The extractor recognizes only exact module `zh.hanman18`, source ID
`5092568988625041973`, and the exact upstream file hashes recorded in
`extractor/source_adapters/chinese_contracts.json`. It emits closed
`manga18-v1` IR with explicit HTML selectors, newest-first upstream chapter
order, Base64 `slides_p_path` decoding, directory-placeholder rejection and a
Referer header.

The schema change adds only the `manga18-v1` enum member. The generator selects
one isolated, human-readable Manga18 runtime template; generic generator
semantics are unchanged. The runtime parses catalog/search/detail metadata,
deduplicates chapters before reversing them to canonical OLD to NEW order, and
decodes, trims, absolutizes and stably deduplicates reader URLs. HANMAN18's
upstream tag-filter override is retained as a bounded family fact rather than a
global parser change. The canonical materializer created IR, generated base,
root JS, registry and index targets without a patch file.

This path has no existing consumers. Every prior source, generated artifact
and version remains byte-untouched; the only schema surface is a closed enum.

## Identity, live contract and publication

| Module | Source ID | Artifact | Runtime key | Locale | Conversion | Identity | Live | Publication |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `zh.hanman18` | `5092568988625041973` | `hanman18` | `keiyoushi_5092568988625041973` | `zh-Hant` | Pass | Pass | Pass | 1.0.0 |

No artifact, provider or runtime-key collision was found. In particular, the
existing manual `goda` and `mh18` identities are unrelated and unchanged.
Locale resolution is supported by upstream `zh` metadata plus live Traditional
Chinese provider behavior, not glyph appearance alone. The content warning is
NSFW from upstream module metadata.

Bounded live evidence on 2026-09-12:

- Catalog pages 1 and 2 each returned 20 distinct entries; page 62 returned 14
  entries and no next page.
- Traditional Chinese search `秘密教學` returned one exact-title result on page
  1 and stopped with no result/no next page on page 2.
- Detail `秘密教學` returned core metadata and 320 deduplicated chapters.
- Provider-newest-first chapters were normalized to OLD to NEW.
- Reader sample `/manhwa/mimijiaohua/164` returned 29 ordered unique absolute
  image URLs; first, middle and last image requests all returned JPEG content.
- The reader trims payload values, preserves order, rejects decoded directory
  placeholders, deduplicates URLs and sends `Referer: https://hanman18.com/`.

The new root and generated JS SHA-256 is
`8f8df45bf46748f553d15e7032962cb7f8a436045933cc91cd8742cd3bf581cd`;
the IR SHA-256 is
`af48fd3dec334efc95c27ac3b7808d67c7ebb0bad300b7e1d0ca75e23324a293`.
Materialization transaction
`6638496a874dc3982836b3bd53d0ea09b9221461894284ebb258645d092bf632`
reported validation and determinism PASS.

## Candidate closure and regression evidence

HANMAN18 moves from 9G `PARKED_ADAPTER` to 9H `PUBLISHED_PASS`; its matrix row
records both milestone states, conversion, identity, live evidence,
publication, and no remaining blocker. No other candidate was reclassified.
The final matrix totals are 11 `PUBLISHED_PASS`, 3
`CONVERTED_LIVE_BLOCKED`, 28 `PARKED_ADAPTER`, 47
`PARKED_ARCHITECTURE`, 2 `BLOCKED_ANTIBOT`, 1 `BLOCKED_AUTH`, and 1
`DEAD_UPSTREAM`, with zero `UNKNOWN`. The canonical successor is
`audit/chinese_candidate_matrix_9h.json`.

Targeted suites passed 55 family tests, 28 planner tests and 23 registry tests.
The complete suite independently discovered and passed 657 tests with zero
failures and zero errors. The unchanged VeneraX Host anchors passed all 22
tests in `chapter_duplicates_test.dart` and
`comic_source_artifact_update_test.dart`. Existing MCCMS, R2 Chinese,
MangaDex, NamiComi, Dongman and GlobalComix regressions remain green. No
English source, English version, JJK, Black Clover or English MangaCatalog
state changed.

## Bounded Windows runtime handoff

Use source `HANMAN18` (`zh-Hant`, NSFW). Search `秘密教學`, open the exact title,
and expect 320 chapters in OLD to NEW order. At the newest chapter, Next must be
absent; at a middle chapter, Next must go newer and Previous older; at the
oldest chapter, Previous must be absent. Open the reader for the chapter whose
provider path is `/manhwa/mimijiaohua/164` and sample its first, middle and last
images. Restart VeneraX and confirm the installed source remains owned by
runtime key `keiyoushi_5092568988625041973` without a second identity. Use
`漫画屋` and MangaDex `zh-Hant` as the small unchanged controls.

The next bounded milestone is **9I — NEXT CHINESE ADAPTER FAMILY**. It should
reassess SinMH and other single-yield adapter candidates, while keeping auth,
anti-bot, raw-`zh` identity ambiguity and architecture-heavy families parked.
