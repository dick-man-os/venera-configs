"""Bounded 9I family contracts; no live network or cross-family runtime changes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest

from tools.source_conversion.tests import test_chinese_families as shared
from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.validator.validate_ir import validate_ir_data

node = shared.node
IDENTITIES = {"guazimanhua": "9103931521355991619", "terrahistoricus": "4585134706567717130", "bh3": "5943234929466346733"}


def guazi_card(i):
    return node(select={"a.cover-wrap": [node(attrs={"href": "/comic.php?id=" + str(i)})],
                        "h3 a": [node("作品" + str(i))], "img.cover": [node(attrs={"src": "//img.test/cover.jpg"})]})


def guazi_page(ids, last, next_page=None):
    links = [node(str(last), {"href": "/category.php?sort=hits&keyword=%E6%88%91&page=" + str(last)})]
    if next_page is not None:
        links.append(node(">", {"href": "/category.php?keyword=%E6%88%91&sort=hits&page=" + str(next_page)}))
    return node(select={"article.card": [guazi_card(i) for i in ids], "nav.pager a": links})


class ChinesePracticalClosureTests(unittest.TestCase):
    runtime = shared.FamilyContractTests.runtime

    def run_family(self, family, code):
        self.runtime(family, code, source_id=IDENTITIES[family])

    def test_exact_three_metadata_schema_and_deterministic_generation(self):
        for family, source_id in IDENTITIES.items():
            with self.subTest(family=family):
                c = next(c for c in shared.CANDIDATES if c["sourceId"] == source_id)
                ir = shared.families.make_ir(c, shared.STAMP)
                self.assertEqual(validate_ir_data(ir), [])
                self.assertEqual(ir["familyContract"], family + "-v1")
                self.assertEqual(ir["languages"], ["zh-Hans"])
                self.assertEqual(ir["id"], "keiyoushi_" + source_id)
                self.assertFalse(ir["requiresAuth"])
                self.assertFalse(ir["requiresWebView"])
                self.assertEqual(ir["contentWarning"], "SAFE")
                self.assertNotIn("Origin", ir["headers"])
                self.assertEqual(set(ir["headers"]), {"User-Agent"} if family == "guazimanhua" else {"Referer"})
                self.assertEqual(generate_venera_js(ir), generate_venera_js(copy.deepcopy(ir)))
                self.assertEqual(ir["schemaVersion"], "0.2")

    def test_exact_input_hashes_and_rejected_identity_or_contract_mutation(self):
        root = Path(os.environ["SOURCE_CONVERSION_TEST_EXTENSIONS_ROOT"])
        for family, source_id in IDENTITIES.items():
            entry = shared.families.MANIFEST["families"]["zh." + family]
            self.assertEqual(len(entry["files"]), 3)
            for name, expected in entry["files"].items():
                self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), expected)
            c = entry["candidates"][0]
            self.assertIsNone(shared.families.candidate_contract({**c, "sourceId": source_id + "0"}, shared.families.PIN))
            self.assertIsNone(shared.families.candidate_contract(c, "0" * 40))
            ir = shared.families.make_ir(c, shared.STAMP)
            ir["search"]["url"] += "/changed"
            with self.assertRaises(ValueError):
                generate_venera_js(ir)

    def test_guazi_underfull_first_real_second_terminal_and_canonical_dedupe(self):
        first = guazi_page([*range(1, 36), 1], 75, 2)
        second = guazi_page(range(36, 72), 75, 3)
        last = guazi_page(range(100, 120), 75)
        self.run_family("guazimanhua", f'''
            htmlReply({json.dumps(first)}); const a=await s.search.load(" 我 ",{{}},1);
            htmlReply({json.dumps(second)}); const b=await s.search.load("我",{{}},2);
            htmlReply({json.dumps(last)}); const c=await s.search.load("我",{{}},75);
            eq([a.comics.length,b.comics.length,c.comics.length],[35,36,20]);
            eq([a.hasMore,b.hasMore,c.hasMore],[true,true,false]);
            eq([a.maxPage,b.maxPage,c.maxPage],[75,75,75]);
            ok(!b.comics.some(x=>a.comics.some(y=>x.id===y.id)));
            eq(calls.length,3); ok(calls[1].url.endsWith("keyword=%E6%88%91&sort=hits&page=2"));
            eq(calls[0].headers,s.headers); ok(!("Referer" in s.headers));
        ''')

    def test_guazi_invalid_next_never_repeats_or_changes_query(self):
        for href in ["/category.php?keyword=%E6%88%91&sort=hits&page=1",
                     "/category.php?keyword=wrong&sort=hits&page=2",
                     "https://other.test/category.php?keyword=%E6%88%91&page=2",
                     "/category.php?keyword=%E6%88%91&page=2&page=3"]:
            body = node(select={"article.card": [guazi_card(1)], "nav.pager a": [node(">", {"href": href})]})
            self.run_family("guazimanhua", f'htmlReply({json.dumps(body)}); await rejects(()=>s.search.load("我",{{}},1),"Guazimanhua");')

    def test_guazi_empty_terminal_is_allowed_but_empty_nonterminal_is_error(self):
        end = guazi_page([], 2)
        more = guazi_page([], 2, 2)
        self.run_family("guazimanhua", f'''
            htmlReply({json.dumps(end)}); eq(await s.search.load("我",{{}},2),{{comics:[],hasMore:false,maxPage:2}});
            htmlReply({json.dumps(more)}); await rejects(()=>s.search.load("我",{{}},1),"Empty nonterminal");
            await rejects(()=>s.search.load("我",{{}},0),"Invalid page");
        ''')

    def test_guazi_complete_fixture_owned_605_chapters_and_navigation(self):
        self.run_family("guazimanhua", r'''
            const row=i=>({text:"话"+i,attributes:{href:"/chapter.php?id="+i}});
            htmlReply({select:{[s.config.chapters.selector]:[row(605),...Array.from({length:605},(_,i)=>row(605-i))]}});
            const ids=Object.keys(await s.loadChapters("/comic.php?id=1"));
            eq(ids.length,605); eq(ids[0],s.baseUrl+"/chapter.php?id=1"); eq(ids[604],s.baseUrl+"/chapter.php?id=605");
            eq(ids[605]??null,null); eq(ids[-1]??null,null);
            ok(ids[301].endsWith("id=302")); ok(ids[303].endsWith("id=304"));
        ''')

    def test_guazi_detail_and_direct_images_preserve_order_headers_and_white_pages(self):
        detail = node(select={"div.mobile-comic-title": [node("作品")], "img.mobile-comic-cover": [node(attrs={"src": "/cover.jpg"})],
                              "p.mobile-comic-desc": [node("介绍")], "p.mobile-comic-tags": [node("热血")],
                              "div.cinema-strip > div": [node(select={"span": [node("作者")], "b": [node("作者名")]})]})
        images = node(select={"section.reader-images img": [node(attrs={"src": " //img.test/first.jpg "}), node(attrs={"src": "//img.test/first.jpg"}), node(attrs={"src": "/white.jpg"}), node(attrs={"src": "/last.jpg"})]})
        self.run_family("guazimanhua", f'''
            htmlReply({json.dumps(detail)}); const info=await s.info("/comic.php?id=1");
            eq(info.title,"作品"); eq(info.subtitle,"作者名");
            htmlReply({json.dumps(images)}); const pages=(await s.comic.loadEp("/comic.php?id=1","/chapter.php?id=2")).images;
            eq(pages,["https://img.test/first.jpg",s.baseUrl+"/white.jpg",s.baseUrl+"/last.jpg"]);
            eq(s.comic.onImageLoad(pages[2]),{{url:pages[2],headers:s.headers}});
        ''')

    def test_guazi_missing_or_invalid_images_fail_clearly(self):
        for src in [None, "javascript:bad", "https://img.test/a\nb.jpg", "https://img.test/%ZZ"]:
            rows = [] if src is None else [node(attrs={"src": src})]
            body = node(select={"section.reader-images img": rows})
            self.run_family("guazimanhua", f'htmlReply({json.dumps(body)}); await rejects(()=>s.images("/comic.php?id=1","/chapter.php?id=2"),"Error");')

    def test_terra_search_includes_second_topic_and_stops_without_network(self):
        self.run_family("terrahistoricus", r'''
            jsonReply({code:0,data:[{cid:"1",title:"第一目录",cover:"https://img.test/1"}]});
            jsonReply({code:0,data:[{cid:"2",title:"终末地",cover:"https://img.test/2"},{cid:"2",title:"终末地",cover:"https://img.test/2"}]});
            const result=await s.search.load("终末",{},1); eq(result.comics.length,1);
            eq(result.comics[0].id,s.baseUrl+"/api/comic/2"); eq(result.maxPage,1); eq(result.hasMore,false);
            eq(await s.search.load("终末",{},2),{comics:[],hasMore:false,maxPage:1}); eq(calls.length,2);
            ok(calls[0].url.endsWith("topicKey=terra-historicus")); ok(calls[1].url.endsWith("topicKey=talos-ii-historicus"));
        ''')

    def test_terra_topic_explore_and_latest_shapes(self):
        self.run_family("terrahistoricus", r'''
            jsonReply({code:0,data:[{cid:"01",title:"主题一",cover:"https://img.test/1"}]});
            const first=await s.explore[0].load(1); eq(first.hasMore,true); eq(first.maxPage,2);
            jsonReply({code:0,data:[{comicCid:"02",title:"主题二",coverUrl:"https://img.test/2"}]});
            const last=await s.explore[1].load(2); eq(last.hasMore,false); eq(last.maxPage,2);
            ok(calls[1].url.includes("/api/recentUpdate?")); eq(last.comics[0].id,s.baseUrl+"/api/comic/02");
            eq(await s.explore[0].load(3),{comics:[],hasMore:false,maxPage:2}); eq(calls.length,2);
        ''')

    def test_terra_string_chapters_special_entries_and_navigation(self):
        self.run_family("terrahistoricus", r'''
            const data={cid:"1421",title:"作品",cover:"https://img.test/cover",authors:["甲","乙"],keywords:["剧情"],subtitle:"副标题",introduction:"介绍",type:1,
                episodes:[{cid:"300",type:1,shortTitle:"03",title:"新"},{cid:"0210",type:2,title:"番外"},{cid:"0210",type:2,title:"重复"},{cid:"001",type:4,title:"预告"}]};
            jsonReply({code:0,data}); const info=await s.info("/api/comic/1421"); eq(info.subtitle,"甲、乙");
            jsonReply({code:0,data}); const chapters=await s.loadChapters("/api/comic/1421"), ids=Object.keys(chapters);
            eq(ids.map(id=>id.split("/").pop()),["001","0210","300"]);
            eq(Object.values(chapters),["公告 预告","番外 番外","03 新"]);
            eq(ids[-1]??null,null); eq(ids[3]??null,null); ok(ids[0].endsWith("001")); ok(ids[2].endsWith("300"));
        ''')

    def test_terra_stable_page_keys_and_async_signed_resolution_are_separate(self):
        self.run_family("terrahistoricus", r'''
            s.init(); const comic=s.baseUrl+"/api/comic/1421", ep=comic+"/episode/0210";
            jsonReply({code:0,data:{pageInfos:[{}, {}, {}]}});
            const images=(await s.comic.loadEp(comic,ep)).images, snapshot=JSON.stringify(images);
            eq(images,[ep+"/page?pageNum=1",ep+"/page?pageNum=2",ep+"/page?pageNum=3"]);
            jsonReply({code:0,data:{url:"https://cdn.test/first.jpg?token=one"}});
            jsonReply({code:0,data:{url:"https://cdn.test/last.jpg?token=two"}});
            const preloaded=await Promise.all([s.comic.onImageLoad(images[0],comic,ep),s.comic.onImageLoad(images[2],comic,ep)]);
            eq(preloaded[0].url,"https://cdn.test/first.jpg?token=one"); eq(preloaded[1].url,"https://cdn.test/last.jpg?token=two");
            jsonReply({code:0,data:{url:"https://cdn.test/first.jpg?token=fresh"}});
            eq((await s.comic.onImageLoad(images[0],comic,ep)).url,"https://cdn.test/first.jpg?token=fresh");
            eq(JSON.stringify(images),snapshot); eq(preloaded[0].headers,{Referer:s.baseUrl+"/"}); eq(calls.length,4);
        ''')

    def test_terra_failed_resolver_never_mutates_key_or_retries(self):
        self.run_family("terrahistoricus", r'''
            s.init(); const comic=s.baseUrl+"/api/comic/1", ep=comic+"/episode/0210", key=ep+"/page?pageNum=1";
            jsonReply({code:1,data:{url:"https://cdn.test/no.jpg"}});
            await rejects(()=>s.comic.onImageLoad(key,comic,ep),"API error"); eq(calls.length,1);
            jsonReply({code:0,data:{url:"https://cdn.test/a.jpg"}},403);
            await rejects(()=>s.comic.onImageLoad(key,comic,ep),"HTTP 403"); eq(calls.length,2);
            await rejects(()=>s.comic.onImageLoad(key,comic,comic+"/episode/2"),"ownership");
            await rejects(()=>s.comic.onImageLoad(key.replace("pageNum=1","pageNum=0"),comic,ep),"page key"); eq(calls.length,2);
            jsonReply({code:0,data:{url:"javascript:bad"}}); await rejects(()=>s.comic.onImageLoad(key,comic,ep),"signed image URL");
        ''')

    def test_terra_empty_malformed_and_numeric_identity_rejected(self):
        self.run_family("terrahistoricus", r'''
            jsonReply({code:0,data:{pageInfos:[]}}); await rejects(()=>s.images("/api/comic/1","/api/comic/1/episode/0210"),"no readable images");
            jsonReply({code:0,data:{cid:1421}}); await rejects(()=>s.info("/api/comic/1421"),"string identity");
            jsonReply({code:0,data:{}}); await rejects(()=>s.explore[0].load(1),"Malformed list");
            await rejects(()=>s.images("/api/comic/1","/api/comic/2/episode/3"),"ownership");
        ''')

    def test_bh3_dom_identity_complete_local_search_and_no_fake_second_page(self):
        book = lambda i, title: node(attrs={"href": "javascript:enterBookApp(" + str(i) + ")"}, select={"div.container": [node(attrs={"id": str(i)})], "div.container-title": [node(title)], "img": [node(attrs={"src": "//img.test/cover.jpg"})]})
        body = node(select={"a[href*=book]": [book(1, "崩坏 学园"), book(2, "逆熵"), book(2, "逆熵")]})
        self.run_family("bh3", f'''
            s.init(); eq(s.explore.length,1); eq(s.explore[0].title,"漫画目录");
            htmlReply({json.dumps(body)}); const result=await s.search.load(" 逆熵 ",{{}},1);
            eq(result.comics.length,1); eq(result.comics[0].id,s.baseUrl+"/book/2");
            eq(result.maxPage,1); eq(result.hasMore,false); eq(calls[0].url,s.baseUrl+"/book");
            eq(await s.search.load("逆熵",{{}},2),{{comics:[],hasMore:false,maxPage:1}}); eq(calls.length,1);
        ''')

    def test_bh3_full_json_67_chapters_dedupe_old_to_new(self):
        self.run_family("bh3", r'''
            const ch=i=>({bookid:"1012",chapterid:String(i),title:"话"+i});
            jsonReply([ch(67),...Array.from({length:67},(_,i)=>ch(67-i))]);
            const chapters=await s.loadChapters("/book/1012"), ids=Object.keys(chapters);
            eq(ids.length,67); eq(ids[0],s.baseUrl+"/book/1012/1"); eq(ids[66],s.baseUrl+"/book/1012/67");
            eq(calls.length,1); eq(calls[0].url,s.baseUrl+"/book/1012/get_chapter");
            eq(ids[-1]??null,null); eq(ids[67]??null,null); ok(ids[32].endsWith("/33")); ok(ids[34].endsWith("/35"));
        ''')

    def test_bh3_chapter_shape_ownership_and_string_ids_rejected(self):
        for payload, message in [({"chapters": []}, "Malformed list"), ([{"bookid": "2", "chapterid": "3", "title": "错"}], "ownership"),
                                 ([{"bookid": "1", "chapterid": 3, "title": "错"}], "string identity"), ([], "Missing BH3")]:
            self.run_family("bh3", f'jsonReply({json.dumps(payload)}); await rejects(()=>s.loadChapters("/book/1"),"{message}");')

    def test_bh3_details_reader_original_attr_and_order(self):
        detail = node(select={"div.title": [node("作品")], "img.cover": [node(attrs={"src": "/cover.jpg"})], "div.detail_info1": [node("介绍")]})
        reader = node(select={"img.lazy.comic_img": [node(attrs={"data-original": " //img.test/first.jpg ", "src": "placeholder.gif"}),
                                                    node(attrs={"data-original": "/middle.jpg"}), node(attrs={"data-original": "/last.jpg"}), node(attrs={"data-original": "/last.jpg"})]})
        self.run_family("bh3", f'''
            htmlReply({json.dumps(detail)}); eq((await s.info("/book/1")).description,"介绍");
            htmlReply({json.dumps(reader)}); const pages=(await s.comic.loadEp("/book/1","/book/1/2")).images;
            eq(pages,["https://img.test/first.jpg",s.baseUrl+"/middle.jpg",s.baseUrl+"/last.jpg"]);
            eq(s.comic.onImageLoad(pages[2]),{{url:pages[2],headers:{{Referer:s.baseUrl+"/"}}}});
        ''')

    def test_bh3_invalid_reader_or_foreign_book_never_returns_placeholder(self):
        for attrs in [{"src": "placeholder.gif"}, {"data-original": "javascript:bad"}, {"data-original": "https://img.test/a\nb.jpg"}]:
            body = node(select={"img.lazy.comic_img": [node(attrs=attrs)]})
            self.run_family("bh3", f'htmlReply({json.dumps(body)}); await rejects(()=>s.images("/book/1","/book/1/2"),"Error");')
        self.run_family("bh3", 'await rejects(()=>s.images("/book/1","/book/2/3"),"ownership");')
