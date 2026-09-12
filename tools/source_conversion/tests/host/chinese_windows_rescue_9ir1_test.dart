import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:venera/foundation/app.dart';
import 'package:venera/foundation/js_engine.dart';

// Source-owned test: run in a disposable checkout of the unchanged Host.
// SOURCE_CONVERSION_ROOT points to the source repository under test.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final root = Platform.environment['SOURCE_CONVERSION_ROOT'] ??
      '${Directory.current.parent.path}/venera-configs';
  final fixtures = jsonDecode(File(
    '$root/tools/source_conversion/tests/fixtures/chinese_windows_rescue_9ir1.json',
  ).readAsStringSync())['html'] as Map;

  setUpAll(() async {
    final temp = Directory.systemTemp.createTempSync('venerax_9ir1_contract_');
    App.dataPath = temp.path;
    App.cachePath = temp.path;
    // Do not initialize the real app profile or cookie store.
    JsEngine.cacheJsInit(File('assets/init.js').readAsBytesSync());
    await JsEngine().init();
    for (final name in ['manhuawu', 'hanman18']) {
      final source = File('$root/$name.js').readAsStringSync();
      final className = RegExp(r'class (\w+) extends ComicSource')
          .firstMatch(source)!.group(1)!;
      JsEngine().runCode(
        '(()=>{$source;globalThis.$name=new $className();})();',
      );
    }
  });
  tearDownAll(() => JsEngine().dispose());

  Future<Map> replay(String fixture, String expression) async {
    final value = await JsEngine().runCode('''
      Network.get=async(url,headers)=>({status:200,body:${jsonEncode(fixtures[fixture])}});
      (async()=>{try{return JSON.stringify({ok:true,data:await ($expression)});}
      catch(e){return JSON.stringify({ok:false,error:String(e)});}})()
    ''');
    return jsonDecode(value as String) as Map;
  }

  test('Captured search HTML supplies maxPage to the Host numbered search', () async {
    final first = await replay('douluo1', 'manhuawu.search.load("斗罗大陆",{},1)');
    expect(first['ok'], true);
    expect(first['data']['comics'].length, 8); // This captured fixture owns 8 IDs.
    expect(first['data']['maxPage'], 1);
    expect(first['data']['hasMore'], false);
    final beyond = await replay('douluo2', 'manhuawu.search.load("斗罗大陆",{},2)');
    expect(beyond['data']['comics'], isEmpty);
    expect(beyond['data']['maxPage'], 1);
    final real1 = await replay('fight1', 'manhuawu.search.load("斗",{},1)');
    final real2 = await replay('fight2', 'manhuawu.search.load("斗",{},2)');
    expect(real1['data']['maxPage'], 20); // Captured last-page target.
    expect(real2['data']['maxPage'], 20);
    expect(real1['data']['hasMore'], true);
    expect(real2['data']['hasMore'], true);
    final ids1 = (real1['data']['comics'] as List).map((c) => c['id']).toSet();
    final ids2 = (real2['data']['comics'] as List).map((c) => c['id']).toSet();
    expect(ids2.difference(ids1), isNotEmpty);
  });

  test('Empty successful pages reproduce the exact Dart reader exception; source rejects them', () async {
    // reader.maxPage derives from image count; scaffold clamps page to 1..maxPage.
    // This is the historical source result, not an exception simulated in JS.
    final oldSuccess = jsonDecode('{"images":[]}');
    final maxPage = (oldSuccess['images'].length / 1).ceil();
    expect(() => 1.clamp(1, maxPage), throwsA(isA<ArgumentError>().having(
      (error) => error.toString(), 'message', 'Invalid argument(s): 1',
    )));
    final latest = await replay('reader115',
      'hanman18.comic.loadEp("/manhwa/youqingwanshui","/manhwa/youqingwanshui/115")');
    expect(latest['ok'], false);
    expect(latest['error'], contains('upstream chapter has no readable images'));
  });

  test('Actual Host Base64 bridge preserves valid first, middle and last page manifests', () async {
    for (final entry in {'114': 105, '58': 14, '1': 59}.entries) {
      final result = await replay('reader${entry.key}',
        'hanman18.comic.loadEp("/manhwa/youqingwanshui","/manhwa/youqingwanshui/${entry.key}")');
      expect(result['ok'], true);
      final images = result['data']['images'] as List;
      expect(images.length, entry.value); // Counts owned by captured manifests.
      expect(images.toSet().length, images.length);
      expect(images.every((url) => Uri.parse(url).isAbsolute), true);
      expect(1.clamp(1, images.length), 1);
      for (final index in [0, images.length ~/ 2, images.length - 1]) {
        final config = jsonDecode(JsEngine().runCode(
          'JSON.stringify(hanman18.comic.onImageLoad(${jsonEncode(images[index])}))',
        ) as String);
        expect(config, {'url': images[index], 'headers': {'Referer': 'https://hanman18.com/'}});
      }
    }
  });
}
