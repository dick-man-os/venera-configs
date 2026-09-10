# 9F-R1 Chinese source and chapter contract

Decision: **Option C**. The generated locale artifacts are the primary MangaDex
implementation for Chinese reading. Keep `manga_dex` operational for existing
installations and its English/features compatibility surface. There is no
automatic replacement, source-key alias, catalog redirection, or removal.

The evidence baseline is configs `e7ede67ea0e68d6443934653552a6b1d75b31754`
and host `126a462debbe5b05a8c8d6e3dcb1b67fff1ebcdf`. Imported upstream evidence
remains pinned to `5a0261c718cd6d5ecf14963d837f29024c792398`; the persistent
read-only extensions checkout remains `5e06c412c0264b18120fd963fdd6efb529f3fa29`.

## MangaDex comparison and migration boundary

| Dimension | Legacy `manga_dex` | Generated `mangadex_zh_hant` / `mangadex_zh_hans` |
|---|---|---|
| Producer/API | Manual root JS; MangaDex v5 REST endpoints | One reviewed family emitter; same REST API, exact Keiyoushi source/DTO pin |
| Languages | Chapters hardcoded to `en`; localized display titles do not change chapter language | `zh-hk` / `zh`, respectively; immutable source-instance locale |
| Explore/search | Popular, recent, updated, tag/category browsing and configurable sort/rating/status | Popular and latest, locale-filtered search, explicit page counts |
| Metadata | Localized title, English description, tags, authors/artists, statistics/comments | Locale title/description fallbacks, cover/author relationships and tags; smaller anonymous reading subset |
| Chapters | Ascending chapter request, grouped by volume, original bare UUIDs; first-500 truncation repaired here | All feed pages, accessibility filters, complete list converted to oldest first; `/chapter/UUID` keys |
| Pagination | Now bounded offset traversal, metadata validation and ID deduplication | 500 rows/request, response-limit offsets, bound/progress checks, no partial success on missing/repeated later pages |
| Reader/pages | Original/compressed setting and fixed uploads host retained | Original pages, API at-home host and five-minute refresh |
| Filters | User-selected tags, sort, content rating and publication status | Fixed locale and reviewed default ratings/group policy; optional upstream preferences not imported |
| Authentication | No implemented account feature | Anonymous accessible subset; no account/purchase flow |
| Runtime work | Three detail operations run concurrently; chapters now O(ceil(N/500)) requests | Detail then chapter feed, O(ceil(N/500)); page-server cache; no per-chapter metadata calls |
| Installed compatibility | Same `manga_dex` key, filename, manga IDs, chapter IDs, grouped shape and settings | Same two opaque keys, filenames, upstream source IDs and source provenance |
| Update ownership | Existing manual/direct URL retained; catalog installs remain artifact-aware | Host resolves library + runtime key + exact artifact filename; names are presentation only |
| Upstream maintenance | Independent manual compatibility implementation | One emitter and closed extraction contract for both locales; pin/file attestations retained |

A single selectable-language artifact cannot replace these installations safely
today: it would have to reconcile three keys, English functionality, language
preferences, different comic/chapter ID encodings and grouped/flat histories.
Keeping two small generated artifacts does not duplicate the API implementation.
No sibling may satisfy another artifact's update target.

Future migration must be explicit and optional, with English/filter/image-quality
parity where relevant, verified UUID mappings (`UUID` versus `/manga/UUID` and
`/chapter/UUID`), group/locale-aware chapter identity mapping, and preservation of
favorites/history/provenance. Retain the old installation until that contract is
implemented and tested. Name changes never trigger migration.

## Chapter order and host audit

Classification: **SOURCE_ORDER**, not a host next/previous defect.
`ComicChapters` preserves insertion order; `reader.dart::visibleChapterFrom`
delegates to `nextVisibleChapter` with +1 for next and -1 for previous.
The helper returns null outside 1..length. Continuous reading, neighboring-chapter
loading/preload and separators use that same helper. The detail UI's
`reverseChapterOrder` reverses displayed slots while retaining original reader
indices. It does not reorder the source map.

Keiyoushi returns newest-first chapter lists. The generated MangaDex, NamiComi
and Dongman adapters had carried that order into Venera, causing forward reading
to select an older chapter. Reverse these three producers' complete, deduplicated
lists once. Keep IDs, decimals, special chapters and volume labels intact;
do not sort display labels lexically or reverse each pagination page. NamiComi's
access map is still evaluated before producing the readable list. GlobalComix's
live release response is already ascending and remains byte-for-byte unchanged.

The oldest chapter has no previous, the latest has no next, and a middle chapter
advances toward newer chapters. No wraparound is introduced. Host code is unchanged.

Existing source/favorite/history records are not deleted or reassigned. The host
currently stores read positions/marks as indices rather than chapter IDs. After
refreshing a previously descending list, an old positional bookmark/mark can
therefore denote another chapter. Reopen the intended chapter by its title after
this source update; automatic positional-history conversion is not claimed.
This is also a prerequisite for any future cross-artifact migration.

## Completeness, access and live evidence

Anonymous live validation on 2026-09-09 executed the shipped JS with QuickJS and
the host's actual Dart HTML bridge. Expected sets come from the same locale's
API rows plus access decisions, or independently enumerated web-list links.
Counts below are accessible chapter entities, not a manga's global total.

| Source | Representative title / identity | Upstream accessible = returned | Reader pages |
|---|---|---:|---:|
| Dongman zh-Hans | 如出一辙的女儿, `title_no=1954` | 11 = 11 across two chapter-list pages | 176 |
| GlobalComix zh-Hans | 暴走群俠傳, `8304/--25`, API `lang_id=cn` | 7 = 7 | 6 |
| NamiComi zh-Hant | 愛上我前未婚夫的祖父, `73hLs8EN` | 3 = 3 | 44 |
| NamiComi zh-Hant access control | 鬱悶英雄, `CBZPr9jK` | 1 = 1 (three locale rows, two access denials) | 28 |
| NamiComi zh-Hans | 我是赛拉, `5eKytbrB` | 1 = 1 | 20 |
| MangaDex zh-Hant | Kage no Jitsuryokusha ni Naritakute!, `77bee52c-d2d6-44ad-a33a-1734c1fe696a` | 6 = 6 (`zh-hk`) | 32 |
| MangaDex zh-Hans | Same manga UUID | 2 = 2 (`zh`) | 15 |

Dongman's public web list omits paid/app-only episodes. Its latest accessible
entry is the free afterword; 104 in that entry's URL is not an accessible count.
The MangaDex Hant sequence is 75, 81, 82.1, 82.2, 83, 84; Hans is 76.1, 76.2.
NamiComi Hans and Hant differ by API locale, translation availability and title
fallback, not by authentication or reader implementation.

MangaDex/NamiComi retain 500/200-row pagination, respectively; Nami access checks
are independently chunked at 200 IDs. They now reject repeated/non-progressing
later pages and HTTP 204 after an API-advertised successor instead of silently
returning partial chapters. Dongman retains bounded same-origin, cycle-checked
next-link traversal. All filter/deduplication occurs on chapter identity.

GlobalComix requests `all=true`; live metadata reports `per_page=9999` and one
complete response. The existing guard rejects an advertised incomplete
all-releases response rather than accepting a partial list. No GlobalComix
truncation or reversal was observed; no artifact/version change is justified.
Nami requires an explicit true access decision. MangaDex retains
future/empty/unavailable and zero-page external filtering. GlobalComix retains
premium-only chapter and paid/unknown reader-page rejection.

## Verification and Windows handoff

Baseline: 612 source tests pass. Updated full suite: 622 tests pass. New behavioral
fixtures cover 1,003 MangaDex chapter identities over three feed pages, 403 Nami
identities over three pages and three access batches, 1,201 legacy MangaDex
identities, locale counts, cross-page duplicates, decimal/special/volume labels,
empty/error/missing/repeated pages and identity/name safety. Dongman's existing
three-page fixture now expects chronological order. A 501-release GlobalComix
fixture verifies its complete-response/access contract without reversing it.

The sanitized live output fixture and companion Flutter test exercise actual
`ComicChapters`, `nextVisibleChapter`, reversed display indices,
`SourceProvenance` serialization and artifact-aware update resolution against the
unchanged host. Run from VeneraX:

```powershell
flutter test --no-pub ../venera-configs/tools/source_conversion/tests/host/chinese_chapter_contract_test.dart
```

Windows physical retest (handoff, not an assertion that UI testing already ran):

1. Update the existing catalog and installed sources. Confirm MangaDex（繁體中文）,
   MangaDex（简体中文）, NamiComi（繁體中文） and NamiComi（简体中文）.
   Confirm the existing legacy MangaDex installation is still independently present.
2. Refresh details for the titles above. Select the intended chapter by title
   after the order correction. Confirm 6/2 MangaDex locale chapters, 3/1 Nami
   representative chapters, and Dongman's 11 chapters across two list pages.
3. For MangaDex Hant read chapter 84 to the bottom: stop at the end. Previous
   reaches 83. Read 82.1 forward to 82.2 and back toward 81. Chapter 75 has no
   previous. Repeat latest/middle/oldest checks in Nami Hant and Dongman.
4. Toggle newest-first detail display and repeat forward reading. It must still
   move chronologically newer and never auto-advance latest to an older chapter.
5. Restart, refresh/update sources, and confirm each source's key, filename and
   library ownership persist without sibling replacement; existing library and
   history entries remain attached to their original source. Reopen saved titles.

No later roadmap stage, login flow, destructive migration or broad reader
refactor is included.
