"""Dongman regressions for Venera's DOM and absolute network URL contracts."""
import json
from pathlib import Path
import unittest

import quickjs

from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.tests.test_chinese_families import HARNESS, candidate, families, node, STAMP

ROOT = Path(__file__).resolve().parents[3]
HOST_CONTRACT = r"""
const queryAll = Node.prototype.querySelectorAll;
Node.prototype.querySelectorAll = function(selector) {
    if (/:(nth|first|last|only)-of-type\b/.test(selector))
        throw new Error("UnimplementedError: unsupported Dart html selector " + selector);
    return queryAll.call(this, selector);
};
Object.defineProperties(Node.prototype, {
    localName: {get() { return this.data.tag || "p"; }},
    previousElementSibling: {get() { return this.data.previous ? new Node(this.data.previous) : null; }},
    nodes: {get() { return this.data.nodes || [{type: "text", text: this.text}]; }}
});
const networkGet = Network.get;
Network.get = async (url, headers) => {
    if (!/^https?:\/\/[^/?#\s]+(?:[/?#]|$)/.test(url))
        throw new Error("relative URL without a base: " + url);
    return networkGet(url, headers);
};
"""


def row(title, href):
    return node(select={"a": [node(attrs={"href": href})], "span.subj span": [node(title)]})


def chapters(rows, next_href=None):
    select = {"ul#_listUl li": rows}
    if next_href is not None:
        select["div.paginate a[onclick] + a"] = [node(attrs={"href": next_href})]
    return node(select=select)


class DongmanRuntimeTests(unittest.TestCase):
    def runtime(self, code):
        ir = families.make_ir(candidate("dongmanmanhua"), STAMP)
        ctx = quickjs.Context()
        ctx.eval(HARNESS + HOST_CONTRACT + generate_venera_js(ir) + """
            const s = new Keiyoushi4222375517460530289Source();
            let completed = false, failure = null;
            (async () => {
        """ + code + r"""
                eq(replies.length, 0);
            })().then(() => {completed = true;}).catch(e => {failure = String(e) + "\n" + e.stack;});
        """)
        jobs = 0
        while ctx.execute_pending_job():
            jobs += 1
            self.assertLess(jobs, 10000)
        self.assertIsNone(ctx.eval("failure"))
        self.assertTrue(ctx.eval("completed"))

    def test_detail_chapters_physical_selector_path_and_upstream_selection(self):
        # The first .author is second among p siblings, so nth-of-type(1) skips it.
        wrong = {**node("Wrong"), "tag": "p", "previous": {**node("Intro"), "tag": "p"}}
        chosen = {**node("Correct Nested credit"), "tag": "span", "previous": wrong,
                  "nodes": [{"type": "text", "text": " Correct "}, {"type": "comment", "text": "ignored"}]}
        info = node(select={".author": [wrong, chosen], ".author_area": [node("Fallback")]})
        detail = node(select={"h1.subj, h3.subj": [node("Title")], ".detail_header .info": [info]})
        page = chapters([row("Two", "/reader/2"), row("One", "reader/1"), row("Two", "/reader/2")])
        self.runtime(f"""
            htmlReply({json.dumps(detail)}); htmlReply({json.dumps(page)});
            const result = await s.comic.loadInfo('/list');
            eq(result.subtitle, 'Correct'); eq(result.title, 'Title');
            eq(result.chapters, {{[s.baseUrl+'/reader/2']:'Two', [s.baseUrl+'/reader/1']:'One'}});
            eq(disposed, 2);
        """)

    def test_author_same_tag_predecessor_not_just_adjacent(self):
        wrong = {**node("Wrong"), "tag": "p", "previous": {"tag": "span", "previous": {"tag": "p"}}}
        info = node(select={".author": [wrong], ".author_area": [node("Fallback")]})
        self.runtime(f"eq(s.author(new Node({json.dumps(node(select={'.detail_header .info': [info]}))})), 'Fallback');")

    def test_author_first_of_tag_and_missing_dom(self):
        for info, expected in [(node(select={".author": [{**node("First"), "tag": "p", "previous": {"tag": "h1"}}]}), "First"),
                               (node(select={".author_area": [node("Fallback")]}), "Fallback"), (node(), "")]:
            with self.subTest(expected=expected):
                doc = node(select={".detail_header .info": [info]})
                self.runtime(f"eq(s.author(new Node({json.dumps(doc)})), {json.dumps(expected)}); eq(s.author(new Node()), '');")

    def test_empty_detail_chapters_pages_and_missing_required_values(self):
        self.runtime(r"""
            htmlReply({}); await rejects(() => s.comic.loadInfo('/list'), 'Missing required');
            htmlReply({}); eq(await s.loadChapters('/list'), {});
            htmlReply({}); eq(await s.comic.loadEp('/list', '/reader/1'), {images:[]});
            await rejects(() => s.comic.loadEp('/list', ''), 'Missing required');
            await rejects(() => s.request(''), 'Missing required');
            await rejects(() => s.comic.onImageLoad(''), 'Missing required');
            eq(calls.length, 3); eq(disposed, 3);
        """)

    def test_all_url_forms_through_chapters_pagination_pages_and_image_hooks(self):
        forms = [('/reader/1', '/reader/1', '/reader/1'),
                 ('reader/1', '/series/reader/1', '/series/reader/reader/1'),
                 ('../reader/1', '/reader/1', '/series/reader/1'),
                 ('//www.dongmanmanhua.cn/reader/1', '/reader/1', '/reader/1'),
                 ('https://www.dongmanmanhua.cn/reader/1', '/reader/1', '/reader/1')]
        for href, expected_path, expected_image_path in forms:
            with self.subTest(href=href):
                first = chapters([row('One', href)], '?page=2')
                last = chapters([row('One', href)])
                images = node(select={'div#_imageList > img': [node(attrs={'data-url': href})]})
                self.runtime(f"""
                    htmlReply({json.dumps(first)}); htmlReply({json.dumps(last)});
                    const eps = await s.loadChapters('/series/list');
                    eq(Object.keys(eps), [s.baseUrl+{json.dumps(expected_path)}]);
                    eq(calls[1].url, s.baseUrl+'/series/list?page=2');
                    htmlReply({json.dumps(images)});
                    const reader = await s.comic.loadEp('/series/list', 'reader/episode');
                    const expected = s.baseUrl+{json.dumps(expected_image_path)};
                    eq(reader.images, [expected]);
                    eq(calls[2].url, s.baseUrl+'/series/reader/episode');
                    const config = s.comic.onImageLoad({json.dumps(href)}, '/series/list', 'reader/episode');
                    eq(config.url, expected); eq(config.headers, s.headers);
                    htmlReply({{}}); await Network.get(config.url, config.headers);
                """)

    def test_catalog_cover_detail_cover_and_network_boundaries(self):
        item = node(attrs={'href': 'series/list'}, select={'p.subj': [node('Title')], 'img': [node(attrs={'src': '/cover.jpg'})]})
        catalog = node(select={'div#dailyList .daily_section li a, div.daily_lst.comp li a': [item]})
        detail = node(select={'h1.subj, h3.subj': [node('Title')],
                             '#content > div.cont_box > div.detail_body': [node(attrs={'style': 'background: url(../covers/detail.jpg)'})]})
        self.runtime(f"""
            htmlReply({json.dumps(catalog)}); const list = await s.explore[0].load(1);
            eq(list.comics[0].id, s.baseUrl+'/series/list'); eq(list.comics[0].cover, s.baseUrl+'/cover.jpg');
            htmlReply({json.dumps(detail)}); eq((await s.info(list.comics[0].id)).cover, s.baseUrl+'/covers/detail.jpg');
            eq(s.comic.onThumbnailLoad('covers/a.jpg', list.comics[0].id).url, s.baseUrl+'/series/covers/a.jpg');
            htmlReply({{}}); await s.request('relative/path'); eq(calls[2].url, s.baseUrl+'/relative/path');
        """)

    def test_relative_image_regression_and_absolute_identity(self):
        self.runtime(r"""
            const cfg = s.comic.onImageLoad('../images/1.jpg', '/series/list', '/series/reader/1');
            eq(cfg.url, s.baseUrl+'/series/images/1.jpg');
            htmlReply({}); await Network.get(cfg.url, cfg.headers);
            for (const url of ['https://cdn.test/a.jpg?token=a%2Fb#x', 'https://cdn.test/a/../b.jpg']) {
                eq(s.comic.onImageLoad(url, '/list', '/reader/1').url, url);
                eq(s.comic.onThumbnailLoad(url, '/list').url, url);
            }
            eq(s.comic.onImageLoad('//cdn.test/1.jpg').url, 'https://cdn.test/1.jpg');
        """)

    def test_pagination_relative_forms(self):
        for href, expected in [('/series/list?page=2', '/series/list?page=2'), ('list?page=2', '/series/list?page=2'),
                               ('../list?page=2', '/list?page=2'), ('//www.dongmanmanhua.cn/list?page=2', '/list?page=2')]:
            with self.subTest(href=href):
                self.runtime(f"""
                    htmlReply({json.dumps(chapters([row('One', '/reader/1')], href))}); htmlReply({{}});
                    eq(Object.values(await s.loadChapters('/series/list')), ['One']);
                    eq(calls[1].url, s.baseUrl+{json.dumps(expected)});
                """)

    def test_malformed_and_foreign_pagination_fail_closed(self):
        for href in ['https://foreign.test/list', '//foreign.test/list', 'http://www.dongmanmanhua.cn/list',
                     'https:///list', 'https://', '//', 'javascript:bad', 'https://www.dongmanmanhua.cn@foreign.test/list',
                     'https://www.dongmanmanhua.cn:bad/list', 'https://www.dongmanmanhua.cn:99999/list',
                     'https://www.dongmanmanhua.cn\\@foreign.test/list', '/bad%XX', '   ']:
            with self.subTest(href=href):
                page = chapters([row('One', '/reader/1')], href)
                self.runtime(f"""
                    htmlReply({json.dumps(page)});
                    let failed = false; try {{ await s.loadChapters('/list'); }} catch (e) {{ failed = true; }}
                    ok(failed); eq(calls.length, 1); eq(disposed, 1);
                """)

    def test_cycle_nonprogress_and_missing_row_image_fail_closed(self):
        self.runtime(f"""
            htmlReply({json.dumps(chapters([row('One', '/reader/1')], '/list'))});
            await rejects(() => s.loadChapters('/list'), 'Cyclic');
            htmlReply({json.dumps(chapters([], '?page=2'))});
            await rejects(() => s.loadChapters('/list'), 'Non-progressing');
            htmlReply({json.dumps(chapters([row('One', '')]))});
            await rejects(() => s.loadChapters('/list'), 'Missing required');
            htmlReply({json.dumps(node(select={'div#_imageList > img': [node()]}))});
            await rejects(() => s.comic.loadEp('/list', '/reader/1'), 'Missing required');
            eq(calls.length, 4); eq(disposed, 4);
        """)

    def test_non_dongman_generation_preserves_shipped_bytes(self):
        for name in ('namicomi_zh_hant', 'namicomi_zh_hans', 'globalcomix_zh_hans'):
            with self.subTest(artifact=name):
                ir = json.loads((ROOT/'sources_ir'/f'{name}.json').read_text(encoding='utf-8'))
                self.assertEqual(generate_venera_js(ir), (ROOT/f'{name}.js').read_text(encoding='utf-8'))

    def test_published_version_identity_and_no_patch(self):
        name = 'dongmanmanhua_zh_hans'
        ir = json.loads((ROOT/'sources_ir'/f'{name}.json').read_text(encoding='utf-8'))
        root = (ROOT/f'{name}.js').read_bytes()
        self.assertEqual(root, (ROOT/'sources_generated'/f'{name}.base.js').read_bytes())
        self.assertEqual((ROOT/f'{name}.js').read_text(encoding='utf-8'), generate_venera_js(ir))
        self.assertEqual(ir['version'], '1.0.1')
        index = json.loads((ROOT/'index.json').read_bytes())
        entry = next(item for item in index if item['fileName'] == name+'.js')
        self.assertEqual(entry['version'], ir['version'])
        self.assertEqual(entry['key'], ir['id'])
        self.assertEqual(ir['artifactId'], name)
        self.assertEqual(ir['id'], 'keiyoushi_4222375517460530289')
        self.assertEqual(ir['familyContract'], 'dongmanmanhua-v1')
        self.assertEqual(ir['provenance']['upstreamCommit'], '5a0261c718cd6d5ecf14963d837f29024c792398')


if __name__ == '__main__':
    unittest.main()
