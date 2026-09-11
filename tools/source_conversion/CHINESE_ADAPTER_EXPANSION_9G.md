# 9G Chinese source adapter expansion and batch import

## Scope and baselines

9G is limited to `zh-Hans` and `zh-Hant`. English source expansion remains
frozen. The writable baseline is `venera-configs` commit
`c47d08fd91f3f396a64493e0e0ef06250b9a6ee3`; the read-only VeneraX host is
`126a462debbe5b05a8c8d6e3dcb1b67fff1ebcdf`. The canonical extraction input is
the disposable, clean checkout of `keiyoushi/extensions-source` at
`5a0261c718cd6d5ecf14963d837f29024c792398`. The persistent upstream checkout
remained read-only at `5e06c412c0264b18120fd963fdd6efb529f3fa29`.

The source-conversion baseline independently discovered and passed 648 tests.
The authoritative R2 audit classified 93 candidates as 9 published, 18
adapter-blocked, 61 unknown, 2 anti-bot blocked, 1 dead upstream, 1 eligible
but unpublished, and 1 authentication blocked. R2 did not use the final
`PARKED_ADAPTER` / `PARKED_ARCHITECTURE` names; 9G resolves every old unknown
to one of those explicit states or to another allowed terminal class.

## Family ranking

| Family | Candidates | Live base URLs | Risk | Expected safe yield | Decision |
| --- | ---: | ---: | --- | ---: | --- |
| MCCMS | 3 | 3 | Low | 1 | Implemented |
| GalleryAdults | 5 | 5 | Medium-high | Unresolved | Deferred: raw `zh` and NSFW identity/content semantics |
| Goda | 2 | 1 | Medium | 1 | Deferred: one member returns 403 |
| HentaiHand | 2 | 2 | Medium | Unresolved | Deferred: identity and NSFW review |
| SinMH | 2 | 1 | Medium | 1 | Deferred: one member returns 403 |
| MMLook | 2 | 0 | High | 0 | Deferred: TLS failure |
| MadaraLegacy | 1 | 0 | Medium-high | 0 | Deferred: 403 |
| Manga18 | 1 | 1 | Medium | 1 | Deferred at the bounded batch boundary |

MCCMS was selected over the numerically larger GalleryAdults cluster because
all three sites were live, all three candidates inherit the same reviewed
upstream superclass, the source identities were byte-exact and stable at the
canonical pin, and the implementation required neither login nor anti-bot
bypass. GalleryAdults has materially higher identity and content-warning risk.

## Bounded MCCMS implementation

The implementation adds a closed `mccms-v1` family contract. It is activated
only for the three exact source IDs and exact upstream file hashes recorded in
`extractor/source_adapters/chinese_contracts.json`; it is not a generic raw
`zh` inference. The extractor normalizes shared catalog, detail, chapter and
reader semantics while retaining three evidence-backed variants:

- Manhuawu: desktop HTML listings/details, paired-link pagination and lazy
  `data-original` reader images.
- Miaoqu: mobile details, next-link pagination and the upstream XOR/Base64
  reader payload.
- SixMH: desktop HTML, newest-first provider chapters normalized to OLD to NEW,
  and the upstream AES-CBC/PKCS7 reader payload.

The schema change is one enum member, `mccms-v1`. The generator loads one
human-readable MCCMS runtime template and selects behavior from declarative IR
fields. The materializer accepts reviewed `zh-Hans` only when the entire closed
candidate contract matches. There is no arbitrary Kotlin execution, no network
dependency during canonical generation, no identity migration, and no Host
change. Existing family runtimes and existing generated artifacts are outside
the changed semantic path.

## Reclassification and publication

All three MCCMS candidates convert and pass deterministic identity validation:

| Module | Source ID | Locale | Conversion | Identity | Live contract | Publication |
| --- | --- | --- | --- | --- | --- | --- |
| `zh.manhuawu` | `3279300917142951720` | `zh-Hans` | Pass | Pass | Pass | `manhuawu` 1.0.0 |
| `zh.miaoqu` | `116946528518438525` | `zh-Hans` | Pass | Pass | Blocked | Not published |
| `zh.sixmh` | `5183325399429659419` | `zh-Hans` | Pass | Pass | Blocked | Not published |

Manhuawu passed base/explore, search, detail, complete chapter and reader
checks. Search `/search/斗罗大陆/1` returned 17 items. `斗破苍穹` exposed 670
deduplicated chapters in canonical OLD to NEW order, from `01` through
`第519回 帝戰終局`; the sampled reader returned 36 ordered absolute image URLs.

Miaoqu passed base/explore/detail, produced 222 deduplicated chapters and 52
ordered reader images after XOR/Base64 decoding. Every reviewed search route
returned HTTP 404, so it is `CONVERTED_LIVE_BLOCKED` and remains unpublished.

SixMH passed base/explore/detail, produced 222 deduplicated chapters and 52
ordered reader images after AES-CBC decoding. A provider-native search returned
an empty catalog, so it is `CONVERTED_LIVE_BLOCKED` and remains unpublished.

The resulting 93-row matrix contains 13 converted candidates, 13 identity
passes, 10 live passes and 10 published candidates. Its final classes are 10
`PUBLISHED_PASS`, 3 `CONVERTED_LIVE_BLOCKED`, 29 `PARKED_ADAPTER`, 47
`PARKED_ARCHITECTURE`, 2 `BLOCKED_ANTIBOT`, 1 `BLOCKED_AUTH`, and 1
`DEAD_UPSTREAM`. There are no unexplained unknowns. The canonical table is
`audit/chinese_candidate_matrix_9g.json`.

## Contract and regression evidence

The deterministic tests cover catalog and search pagination/termination,
details, chapter deduplication, OLD to NEW normalization, first/middle/last
chapter navigation, HTML/XOR/AES reader variants, absolute ordered image URLs,
the bounded header contract, exact locale identity, matrix closure, registry,
index, planner and materializer behavior. Existing R2 anchors remain covered,
including MangaDex, NamiComi, Dongman, GlobalComix, Webtoons, Comicabc,
Manhuashe, MyComic, Manhuagui, Copy Manga standard/multi-account and Hot Manga.

The final source-conversion discovery passed 653 tests with zero failures and
zero errors. A read-only VeneraX Host anchor rerun passed all 22 tests currently
discovered in `chapter_duplicates_test.dart` and
`comic_source_artifact_update_test.dart`; Host HEAD and worktree remained
unchanged. Canonical materialization was deterministic and registry/index
goldens passed. No English artifact, English version, JJK, Black Clover or
English MangaCatalog state changed.

## Bounded Windows runtime handoff

The published MCCMS sample is `漫画屋` (`zh-Hans`). Search for `斗罗大陆` and
confirm that results are returned without a repeated-page loop. Open `斗破苍穹`
and confirm a large list of 670 chapters, with `01` at the old end and
`第519回 帝戰終局` at the new end. From the newest chapter, Next must be absent;
from a middle chapter, Next goes newer and Previous goes older; from the oldest
chapter, Previous must be absent. Open reader chapter `01` and sample the first,
middle and last pages. After restarting VeneraX, confirm that the installed
source is still owned by runtime key `keiyoushi_3279300917142951720` and is not
offered as a second identity.

R2 controls need only be sampled for Comicabc chapter order, Manhuagui chapter
order, and one Copy Manga search final page. Miaoqu and SixMH are deliberately
excluded from physical acceptance because their required live search gate did
not pass.

The next bounded milestone should be **9H — NEXT CHINESE ADAPTER FAMILY**,
starting with the remaining low-risk singleton/live clusters while keeping
auth, anti-bot, and ambiguous raw-`zh`/NSFW candidates parked.
