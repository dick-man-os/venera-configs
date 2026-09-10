# 9F-R2 Chinese runtime sampling and rescue closure

Evidence date: 2026-09-10. Source baseline: `68345f320b255b466c1e4fcda790f9b3311b7cb9`.
Host baseline: `126a462debbe5b05a8c8d6e3dcb1b67fff1ebcdf`.

Eight existing Chinese source artifacts receive bounded runtime repairs. No
English artifact, shared generator/adapter, registry identity, account flow,
persistent data, host source, or pinned inventory is changed. No new import
passed every eligibility and live-availability condition in this batch.

## Inventory and identity closure

The catalog and registry contain 52 artifacts. Of these, 32 are Chinese provider
artifacts: nine have explicit script locales in registry/IR; 23 manual artifacts
have Chinese provider/runtime evidence but no separately registered Hant/Hans
identity. A null locale is left unknown, rather than inferred from a filename or
a translated title. `baihehui.js` is a 53rd source root artifact, absent from the
registry/index; its login implementation does not prove an anonymous contract.
It remains UNKNOWN and unpublished.

The canonical inventory contains 2,212 candidates, including 93 Chinese
candidates: 74 `zh`, nine `zh-Hant`, nine `zh-Hans`, and one `zh-TW`. The inventory
is pinned to `5a0261c718cd6d5ecf14963d837f29024c792398`, as established by the
conversion pipeline. An independent temporary exact-pin checkout reproduced its
inventory check. The persistent read-only upstream checkout remained untouched
at `5e06c412c0264b18120fd963fdd6efb529f3fa29`.

[Machine inventory](audit/chinese_runtime_audit_9fr2.json) records artifact ID,
runtime key, provider/site, display name, locale evidence, upstream
project/module/source ID, family, adapter, current version, publication,
identity risk, authentication, content warning, classification, and runtime
evidence for every current artifact and canonical Chinese candidate. Unresolved
upstream IDs or artifact assignments remain null. PUBLISHED denotes catalog
membership, not a claim that a provider currently works.

| Canonical candidate classification | Count |
|---|---:|
| PUBLISHED | 9 |
| BLOCKED_ADAPTER | 18 |
| UNKNOWN | 61 |
| BLOCKED_AUTH | 1 |
| BLOCKED_ANTIBOT | 2 |
| DEAD_UPSTREAM (reviewed comic endpoints) | 1 |
| ELIGIBLE_NOT_PUBLISHED | 1 |

Four remaining E2 candidates passed deterministic extraction but not the complete
live gate. YellowNote Hans (`170542391855030753`) and Hant
(`4899554363948814001`) returned challenges. iQiyi Hans
(`2198877009406729694`) comic routes redirected to the general site without a
usable comic catalog; this is not a claim that the entire iQiyi service is dead.
GlobalComix Hant (`3451257781273481191`, API language `zh`) returned empty Explore,
Latest and Search results. Its Hans sibling's nonempty `cn` catalog is not a
reason to reassign the Hant identity. NoyAcg remains BLOCKED_AUTH. Unsupported or
unresolved candidates were not forced through another adapter.

| Provider | Hant owner | Hans owner | Coexistence and update ownership |
|---|---|---|---|
| MangaDex | `mangadex_zh_hant` | `mangadex_zh_hans` | Both and legacy `manga_dex` keep three distinct keys, filenames and installations. Legacy remains preserve-only. |
| NamiComi | `namicomi_zh_hant` | `namicomi_zh_hans` | Distinct keys and filenames; both coexist. |
| Webtoons | `webtoons_zh_hant` | No separate Webtoons Hans artifact asserted | Existing English artifact is unchanged; distinct keys. Dongman is its own Chinese provider/module contract. |
| GlobalComix | Unpublished candidate | `globalcomix_zh_hans` | No sibling replacement or reassignment. |
| Baozi | User-selectable site language | User-selectable site language | One existing artifact/key; settings do not create two installed identities. |
| Copy | No registered script split | No registered script split | `copy_manga` and `copy_manga_multi_accounts` share runtime key `copy_manga`; they occupy one runtime slot and can replace one another. They cannot be promised independent simultaneous installations. |

The Copy exception is already explicitly registered as a shared runtime-key
group. Its settings and reading records are key-specific, not isolated per
filename. It is not silently converted into a locale migration. All other
reviewed Chinese identities retain their existing keys. The updater's artifact
filename/provenance rules remain authoritative; a sibling is not an acceptable
update match merely because provider or display name overlaps. Favorites/history
are never reassigned. Established MangaDex and NamiComi Chinese display names
remain unchanged and unambiguous.

## Runtime method and contract matrix

Public network samples executed the shipped JavaScript with QuickJS and the
unchanged host's Dart HTML bridge. Only anonymous reading/catalog requests ran;
existing NamiComi access-check POSTs and Komiic read-only GraphQL queries were
included. No account login, purchase, mutation, captcha bypass, challenge solving,
or arbitrary downloaded-code evaluation was introduced. Each ordinary probe was
bounded to 28 requests with time/response-size limits.

Captured response hashes and operation outcomes are in the machine inventory;
[deep evidence](audit/chinese_runtime_deep_evidence_9fr2.json) includes search
terminal pages, image-prefix results, larger pagination and before/after data.
Public response bodies stayed in the local evidence capsule. Published evidence
omits account headers and redacts URL signatures/tokens. Image file magic bytes
are not authentication signatures.

Offline replay re-executed 29 public-response sets without network: 25 detail /
chapter extractions passed and four stopped on already captured transport or
challenge errors. The replay preserves actual Map insertion order, verifies
response hashes and routes, and records an ordered chapter hash. JSON object
serialization reorders integer-like keys and is therefore not accepted as
evidence of a source Map's reading order. This distinction exposed MyComic's
reversed list. A chapter replay PASS does not imply image decoding, login,
provider-wide availability, or exhaustive catalog pagination passed.

Every explicit Chinese converted artifact has deterministic runtime/fixture
coverage and regeneration checks. New fixtures execute the repaired source
methods, including final cursor pages, failures, duplicates, special chapter
IDs, Map order, grouping, headers and search page sizes. Manual artifacts also
received public-response replay where access allowed. No blanket assertion of
complete behavior is made for unexecuted account or category paths.

The 32 published artifacts form 28 implementation families. H/S counts below
refer to registered Hant/Hans identities; U means script identity unspecified.
Each source-specific row is its own family, with no claimed shared parser.

| Family / artifacts | Count H/S/U | Parser, pagination and chapter order | Reader / access and sampled outcome |
|---|---|---|---|
| MangaDex locales | 2: 1/1/0 | REST; response-limit offsets; dedup/access filtering; complete feed reversed once to OLD→NEW | At-home API, ordered pages and image headers; both PASS |
| NamiComi locales | 2: 1/1/0 | REST; 200-row pages and independent 200-ID access batches; dedup; OLD→NEW | Explicit access result, reader JSON; both PASS |
| Webtoons Hant | 1: 1/0/0 | HTML catalogs; separate originals/canvas search pages; mobile episode cursor API; dedup before numbering; already ascending API | HTML image order and source Referer; PASS after rescue |
| Dongman Hans | 1: 0/1/0 | HTML; same-origin next-link traversal, cycle/termination guards; merged list OLD→NEW | Public web episodes, image DOM order and Referer; PASS |
| GlobalComix Hans | 1: 0/1/0 | API `all=true`; reject incomplete advertised release response; dedup; already ascending | Premium/page-access checks, ordered URLs and headers; PASS |
| Comicabc Hant | 1: 1/0/0 | Complete chapter DOM, explicit chapter identities, dedup; preserve ascending site order | Existing data-only reader decoder and headers; PASS after rescue |
| Manhuashe Hans | 1: 0/1/0 | Complete chapter DOM, dedup map; preserve ascending site order, including notices | Existing reader extraction and headers; PASS after rescue |
| Copy API manual forks: Copy, multi-account Copy, Hot Manga | 3: 0/0/3 | Offset search; Copy 30 rows, Hot 20 / author 30; grouped chapters in 100-row offsets until reported total; preserve provider order | Existing API page arrays/reordering; anonymous subset PASS; account paths not exercised |
| Baozi | 1: 0/0/1 | HTML/API; complete main/other chapter containers; source-specific fallback direction, positional chapter IDs retained | 287 chapters; 257/163 pages; locale selectable, no login in sample |
| CCC | 1: 0/0/1 | API counts; complete chapter endpoint; metadata includes paid markers; publication/anthology sequence retained | 23 metadata entries; 20/19 logical image handles; host AES image processing remains partial |
| Goda | 1: 0/0/1 | Source-specific catalog path inspected; live parser/order not established | BLOCKED_ANTIBOT |
| Happy | 1: 0/0/1 | Source-specific catalog path inspected; no live chapter contract established | DNS failure; no verified replacement domain; search POST not executed |
| Hcomic | 1: 0/0/1 | API catalog, single-volume chapter identity carrying provider/page count | One volume, 27 pages; mixed-language provider, no new locale assignment |
| Ikmmh | 1: 0/0/1 | HTML catalog/detail; 195 deduplicated chronological chapter links | Both readers empty; downloaded obfuscated program requires a proven bounded decoder; parked |
| Jcomic | 1: 0/0/1 | HTML catalog/detail, existing episode/page extraction | One volume, 156 pages; source image configuration PASS |
| JM | 1: 0/0/1 | Domain discovery/crypto initialization not reproduced by harness | PARTIAL_HOST_RUNTIME_VALIDATION; no source-failure assertion or bypass |
| Komiic | 1: 0/0/1 | Read-only GraphQL, offset catalog, complete chapter query and volume/chapter grouping | One chapter, 18 page IDs; image transport not fully established by harness |
| Manhuagui | 1: 0/0/1 | HTML groups and all hidden list panels; dedup then reverse each complete provider group; never sort upload IDs | 108 chapters; order replay PASS after rescue; reader compression helper requires host sampling |
| Manhuaren | 1: 0/0/1 | HTML grouped chapters; preserve chronological sequence within provider groups | 1,023 entries, 13/1 pages; special notice remains in its own group |
| Manwaba | 1: 0/0/1 | API asks chapter total then requests that count; complete 30-row observed response; provider order | 60/1 pages; no claim about a larger upstream server cap |
| Mh1234 | 1: 0/0/1 | Empty catalog and incompatible search response; completeness/order unverified | Windows Defender blocked captured response as unsafe; not reopened or bypassed |
| Mh18 | 1: 0/0/1 | Source-specific catalog inspected; live chapter contract unverified | BLOCKED_ANTIBOT |
| Mxs | 1: 0/0/1 | HTML complete chapter list; source map preserves site order | 11 chapters, 316/263 pages |
| MyComic | 1: 0/0/1 | HTML embedded chapter array / fallback links; dedup then reverse final Map; no new ID encoding | 16 chapters, 61/28 pages and image-prefix PASS; order repaired |
| Picacg | 1: 0/0/1 | Existing authenticated API contract; credentials not supplied or used | BLOCKED_AUTH |
| Wnacg | 1: 0/0/1 | HTML single-volume metadata, no separate chapter map by design | 22 pages; zero chapter entries is not truncation |
| Ykmh | 1: 0/0/1 | Source-specific catalog inspected; live chapter contract unverified | BLOCKED_ANTIBOT |
| Zaimanhua | 1: 0/0/1 | API grouped chapters; reverse each provider group, IDs retained | 74 entries, 26/11 pages |

Grouped special material and anthology entries do not establish one global
publication-date sequence. Group identities and source group order remain
intact; no lexical chapter-title sort or global date sort was introduced.
Catalog totals and completeness are claimed only under the same provider,
locale, accessibility and sampled response conditions. All-sources operation
outcomes, partial statuses and exact request routes are retained in the JSON.

## Deep controls, completeness and rescue evidence

| Source / title | Accessible input and final output | Reader evidence |
|---|---|---|
| MangaDex Hant, Kage no Jitsuryokusha ni Naritakute!, `77bee52c-d2d6-44ad-a33a-1734c1fe696a` | 6; 75, 81, 82.1, 82.2, 83, 84 | Old/new 32/29 pages |
| MangaDex Hans, same UUID | 2; 76.1, 76.2 | 15/14 pages |
| NamiComi Hant, 愛上我前未婚夫的祖父, `73hLs8EN` | 3 | 44/20 pages |
| NamiComi Hans, 我是赛拉, `5eKytbrB` | 1 | 20 pages |
| Dongman, 如出一辙的女儿, `title_no=1954` | 11 across two chapter-list pages | 176/65 pages |
| GlobalComix Hans, 暴走群俠傳, `8304/--25` | 7, complete all-releases response | 6/11 pages |
| Webtoons Hant, 第44節生存課, `title_no=8230` | 36; before 36→1, after 1→36 | 73/155 pages |
| Webtoons Hant, 超人時代, `title_no=2877` | 241 = 200 + 41; cursor 0→200→0 | Old/middle/new 36/58/120 pages; middle content image in each returned JPEG/200 |
| Comicabc, 狂賭之淵, `10818` | 135 entities including specials; original reverse corrected | 83/33 pages |
| Manhuashe, 一人之下, `13871` | 800 entities including notices; original reverse corrected | 18/1 pages |
| MyComic, A PRESTO破碎的记忆, `1` | 16; actual Map 16→1 corrected to 1→16 | 61/28 pages for fixed endpoint IDs |
| Manhuagui, 罗宾V4, `32602` | 108 group-qualified entries; upload-ID sort corrected to provider chapter sequence | Chapter replay only; reader host helper incomplete |

The R1 control counts remained consistent under the sampled locale/access
conditions. Webtoons' later Explore ranking selected 煙癮 (`title_no=10945`, two
chapters, 90/94 pages), a different title; this is UPSTREAM_CHANGED ranking,
not SOURCE_REGRESSION. Dated counts are observations and are not permanent
test assertions. New deterministic chapter fixtures use synthetic 603/1,003-row
data and explicit terminal/error cases.

Webtoons now follows the physical `nextCursor` contract in 200-row pages, requires
progress, rejects repeated/malformed/missing later responses, deduplicates before
numbering, and accepts only explicit terminal cursor zero. Its bounded loop
throws on exhaustion rather than silently returning an arbitrary partial count.
A two-row API probe independently demonstrated cursor 2 then 4. The 241-chapter
sample proved the production 200-row boundary and final 41-row page.

Webtoons' combined search route was a preview that ignored page numbers. The
repair queries the provider's originals and canvas endpoints, merges duplicate
comic IDs and derives each endpoint's last page from its advertised 30-slot
count. It excludes exhausted result types. `愛` returned 57 first-page results,
ten pages and eight final-page results; `爱` returned five results; `Love`
returned 30. English/romanized queries are not prohibited by locale identity.

Copy search originally divided totals by 21 despite requesting 30 rows; Hot
Manga requested 20 rows for keywords and 30 for authors. The resulting Hot
Manga last page could be omitted. Existing source methods now use their actual
request size. Both Copy variants returned 1,500 results / 50 pages for `愛` and
`爱`, and 403 / 14 pages for `Love` (13 final rows). Hot Manga returned 1,494 /
75 pages for `愛` and `爱` (14 final rows), and 403 / 21 pages for `Love` (three
final rows). These are provider-reported search totals, not claims that all
provider content beyond an upstream search cap is searchable. Category and
authenticated favorites pagination were not changed or certified by this repair.

Locked, absent and accessible chapters remain distinct. CCC retains paid
metadata markers and logical image handles. Established R1 NamiComi explicit
access filtering, MangaDex unavailable/external-page policy and GlobalComix paid
page rejection are preserved. Dongman's public web list excludes app-only/paid
episodes. No locked images are invented and no purchase/login path was invoked.

## Versions and publication risk

| Artifact | Before | After | Runtime change |
|---|---|---|---|
| `webtoons_zh_hant` | 1.0.0 | 1.0.1 | Complete cursor chapters, chronological order, real search pagination |
| `comicabc` | 1.0.3 | 1.0.4 | Preserve ascending DOM order |
| `manhuashe` | 1.0.1 | 1.0.2 | Preserve ascending DOM order |
| `mycomic` | 1.1.0 | 1.1.1 | Reverse deduplicated chapter Map |
| `manhuagui` | 1.2.1 | 1.2.2 | Provider order within groups instead of numeric upload-ID sort |
| `copy_manga` | 1.4.1 | 1.4.2 | Correct 30-row search count |
| `copy_manga_multi_accounts` | 1.4.1 | 1.4.2 | Correct 30-row search count |
| `hot_manga` | 1.0.0 | 1.0.1 | Correct keyword/author search counts |

The three converted repairs use source-specific patches, synchronized IR/base/root
versions, and deterministic generator + patcher output. The five manual-source
repairs edit their canonical root producer directly. The canonical registry
writer updates only eight index version values; entry order, native CJK text,
format and unrelated metadata remain intact. Copy multi-account's existing CRLF
serialization is preserved. No reusable emitter or adapter bytes change, so this
candidate does not require the broad-generator or cross-repository review stop.
The existing multi-account blob itself is CRLF, so whitespace validation uses
command-local `core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol`
for both working and staged diffs. This accepts its existing line terminators
while retaining trailing-space and blank-line checks, without repository/global
configuration changes or whole-file newline churn.

The post-commit publication check initially classified the changed generated
bases and patch files as catalog sources because its filter accepted JavaScript
in every directory. Both publication scripts now select root JavaScript artifacts
only. A temporary-repository regression proves that one changed root source is
version-checked and listed while its changed generated base and patch are ignored.
This validator-only repair changes no source runtime or version.

As documented in R1, the host stores some reading positions/marks by index.
Correcting a previously reversed/reordered source list can make an old index
refer to a different chapter. Refresh and reopen the intended chapter by title;
automatic positional-history migration is not claimed. Keys, chapter IDs,
favorites ownership and stored data are not rewritten.

## Validation and bounded Windows handoff

`R2_BASELINE_TEST_COUNT = 622`, all passed at the trusted source baseline.
The affected R1/family/registry/materializer set passed 281 tests before the
additional manual rescues. The final rescue module passes 25 behavioral tests.
The final discovered suite also includes the publication-script regression and
passes **648 tests, zero failures, zero errors**:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B -m unittest discover -s tools/source_conversion/tests
```

The unchanged host's existing R1 Flutter chapter/provenance anchor also passed
all 12 tests with `--no-pub`. It exercises real `ComicChapters`, neighbor edges,
reversed display indices and artifact-aware update ownership. Source fixtures
verify newest has no next, oldest has no previous and middle moves toward newer
chapters. Source ordering is corrected before UI display reversal. The host is
unchanged; no separate host implementation or migration was necessary.

Self-review checks the full source/patch diff, all eight version deltas, precise
index serialization, deterministic converted roots, JavaScript syntax, registry
consistency, `git diff --check`, unchanged English/control artifacts, and the
exact staged path/blob manifest. Local branch, tracking branch and remote must
equal the trusted baseline before commit; normal push must not overwrite a
remote race. Post-push hashes and clean status are recorded in the local
checkpoint capsule because a commit cannot contain its own final hash.

Windows physical UI sampling remains a handoff, not a completed runtime claim.
Keep it bounded:

1. Refresh the catalog and update only the eight affected installed artifacts.
   Verify versions above. Use the already installed Copy variant; do not install
   both variants into the same key slot to test coexistence.
2. Webtoons: refresh 超人時代, select the intended chapter by title, check oldest,
   middle and newest navigation, and load the final search page for `愛`.
   Toggle chapter-list display direction and confirm forward reading still
   advances to newer chapters. Counts may legitimately change upstream.
3. Check one existing title each in Comicabc, Manhuashe, MyComic and Manhuagui.
   Confirm chronological movement within the existing group; do not globally
   reorder special groups. Manhuagui also needs one physical reader image check
   because the external harness lacks its host compression helper.
4. Run the retained MangaDex Hant/Hans, NamiComi Hant/Hans and Dongman controls
   listed above. Confirm locale-specific display names and legacy MangaDex's
   separate installation survive refresh/restart without sibling replacement.
5. For remaining host-only harness gaps, one anonymous representative in
   CCC/Komiic/JM is sufficient if those sources are installed. Stop on login or
   challenge requirements. No request to manually test every Chinese source is
   made. Reopen saved chapter titles after order corrections and verify original
   source ownership remains attached to library/history records.

Blocked providers and unresolved candidates remain explicitly parked in this
report; they are not presented as rescued or fully validated.
