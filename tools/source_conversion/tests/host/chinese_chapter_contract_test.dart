import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:venera/foundation/chapter_duplicates.dart';
import 'package:venera/foundation/comic_source/comic_source.dart';
import 'package:venera/foundation/comic_source/source_library.dart';

// Run from VeneraX; the source producer repository owns these captured outputs.
void main() {
  final root =
      Platform.environment['SOURCE_CONVERSION_ROOT'] ??
      '${Directory.current.parent.path}/venera-configs';
  final fixtures =
      jsonDecode(
            File(
              '$root/tools/source_conversion/tests/fixtures/chinese_chapters_live_20260909.json',
            ).readAsStringSync(),
          )
          as List;
  for (final fixture in fixtures) {
    test(
      '${fixture['artifact']} chronological navigation and display reversal',
      () {
        final chapters = ComicChapters.fromJson(fixture['chapters']);
        final ids = chapters.ids.toList();
        int? navigate(int from, int step) => nextVisibleChapter(
          from: from,
          step: step,
          maxChapter: chapters.length,
          isHidden: (_) => false,
          groupOf: (_) => 0,
        );
        expect(chapters.length, fixture['authoritativeAccessible']);
        expect(chapters.titles.first, fixture['oldestTitle']);
        expect(chapters.titles.last, fixture['latestTitle']);
        expect(navigate(1, -1), isNull);
        expect(navigate(chapters.length, 1), isNull);
        for (var chapter = 1; chapter <= chapters.length; chapter++) {
          final next = navigate(chapter, 1);
          final previous = navigate(chapter, -1);
          expect(next, chapter == chapters.length ? null : chapter + 1);
          expect(previous, chapter == 1 ? null : chapter - 1);
          if (next != null) expect(ids[next - 1], ids[chapter]);
          if (previous != null) expect(ids[previous - 1], ids[chapter - 2]);
        }
        // The detail UI reverses slots, preserving the original reader index.
        final visible = List.generate(chapters.length, (i) => i);
        final displayed = visible.reversed.toList();
        expect(ids[displayed.first], ids.last);
        expect(navigate(displayed.first + 1, 1), isNull);
      },
    );
  }

  final catalog =
      (jsonDecode(File('$root/index.json').readAsStringSync()) as List)
          .where(
            (row) => const {
              'manga_dex.js',
              'mangadex_zh_hant.js',
              'mangadex_zh_hans.js',
              'namicomi_zh_hant.js',
              'namicomi_zh_hans.js',
            }.contains(row['fileName']),
          )
          .map(
            (row) => CatalogSourceArtifact(
              libraryId: 'chinese-contract',
              runtimeKey: row['key'],
              fileName: row['fileName'],
              version: row['version'],
              downloadUrl: 'https://example.test/${row['fileName']}',
            ),
          )
          .toList();
  test('legacy and locale artifacts retain distinct runtime slots', () {
    expect(catalog.length, 5);
    expect(catalog.map((a) => a.runtimeKey).toSet().length, 5);
  });
  for (final artifact in catalog) {
    test('${artifact.fileName} restart and update never select siblings', () {
      final installed = provenanceForCatalogInstall(
        libraryId: artifact.libraryId,
        artifactFileName: artifact.fileName,
      );
      final restored = SourceProvenance.fromJson(
        jsonDecode(jsonEncode(installed.toJson())) as Map<String, dynamic>,
      );
      final selected = resolveCatalogArtifact(
        libraryId: restored.originId!,
        runtimeKey: artifact.runtimeKey,
        artifacts: catalog,
        libraryReachable: true,
        artifactFileName: restored.artifactFileName,
      );
      expect(selected.artifact, same(artifact));
      expect(
        validateCatalogUpdateTarget(
          installedRuntimeKey: artifact.runtimeKey,
          provenance: restored,
          target: selected.artifact,
        ),
        isNull,
      );
      for (final sibling in catalog.where((a) => a != artifact)) {
        expect(
          validateCatalogUpdateTarget(
            installedRuntimeKey: artifact.runtimeKey,
            provenance: restored,
            target: sibling,
          ),
          isNotNull,
        );
      }
      final missing = resolveCatalogArtifact(
        libraryId: restored.originId!,
        runtimeKey: artifact.runtimeKey,
        artifacts: catalog.where((a) => a != artifact),
        libraryReachable: true,
        artifactFileName: restored.artifactFileName,
      );
      expect(missing.status, CatalogArtifactResolutionStatus.missing);
    });
  }
}
