"""9I-R1 regressions: numbered search termination and nonempty reader success."""
import base64
import json
import unittest

from tools.source_conversion.tests import test_chinese_families as family_tests

node = family_tests.node
MANHUAWU = "3279300917142951720"
HANMAN18 = "5092568988625041973"


def card(identity, title="Fixture"):
    return node(select={".comic__title > a": [node(title, {"href": identity})]})


def catalog(cards, last, next_page=None):
    links = [] if last is None else [node(attrs={"href": last}), node(attrs={"href": next_page or last})]
    return node(select={
        ".common-comic-item": cards,
        "#Pagination a, .NewPages a": links,
        "#Pagination a.end": links[:1],
    })


class ChineseWindowsRescueTests(unittest.TestCase):
    runtime = family_tests.FamilyContractTests.runtime

    def test_manhuawu_captured_single_page_exposes_host_max_page(self):
        # The live page uses the query root for end/next, with no /1 suffix.
        body = catalog([card("/index.php/comic/a")], "/index.php/search/斗罗大陆")
        empty = catalog([], "/index.php/search/斗罗大陆")
        self.runtime("mccms", f'''
            htmlReply({json.dumps(body)});
            const first=await s.search.load("斗罗大陆",{{}},1);
            eq(first.maxPage,1); eq(first.hasMore,false); eq(first.comics.length,1);
            eq(calls.length,1); // No next-page prefetch.
            htmlReply({json.dumps(empty)});
            const beyond=await s.search.load("斗罗大陆",{{}},2);
            eq(beyond.maxPage,1); eq(beyond.comics,[]);
        ''', source_id=MANHUAWU)

    def test_manhuawu_real_second_and_terminal_page_are_not_repeated_or_hidden(self):
        # Owns a two-page dataset; end == next on P1 must still allow P2.
        first = catalog([card("/comic/a")], "/index.php/search/斗/2", "/index.php/search/斗/2")
        last = catalog([card("/comic/b")], "/index.php/search/斗/2")
        self.runtime("mccms", f'''
            htmlReply({json.dumps(first)}); const a=await s.search.load("斗",{{}},1);
            htmlReply({json.dumps(last)}); const b=await s.search.load("斗",{{}},2);
            eq(a.maxPage,2); eq(a.hasMore,true); eq(b.maxPage,2); eq(b.hasMore,false);
            eq(a.comics.map(c=>c.id),["/comic/a"]); eq(b.comics.map(c=>c.id),["/comic/b"]);
            eq(calls.map(c=>c.url),[s.baseUrl+"/search/%E6%96%97/1",s.baseUrl+"/search/%E6%96%97/2"]);
        ''', source_id=MANHUAWU)

    def test_manhuawu_missing_or_unrelated_last_link_does_not_invent_terminal_page(self):
        for href in [None, "/index.php/search/another/2", "https://other.test/search/斗/2",
                     "/index.php/search/斗/0", "/index.php/search/斗/2?bad=1",
                     "/index.php/search/斗/9007199254740992"]:
            with self.subTest(href=href):
                body = catalog([card("/comic/a")], href)
                self.runtime("mccms", f'''
                    htmlReply({json.dumps(body)}); const result=await s.search.load("斗",{{}},1);
                    ok(!("maxPage" in result));
                ''', source_id=MANHUAWU)

    def test_manhuawu_only_identical_canonical_comics_are_deduplicated(self):
        body = catalog([card("/index.php/comic/tower", "神之塔"),
                        card("/comic/tower", "Other spelling"),
                        card("/comic/tower-other", "神之塔")], "/search/神之塔")
        self.runtime("mccms", f'''
            htmlReply({json.dumps(body)}); const result=await s.search.load("神之塔",{{}},1);
            eq(result.comics.map(c=>c.id),["/comic/tower","/comic/tower-other"]);
            eq(result.comics.map(c=>c.title),["神之塔","神之塔"]);
        ''', source_id=MANHUAWU)

    def test_manhuawu_fixture_owned_670_chapters_and_reader_are_preserved(self):
        self.runtime("mccms", r'''
            const chapter=i=>({select:{a:[{text:"Chapter "+i,attributes:{href:"/index.php/chapter/"+i}}]}});
            htmlReply({select:{".chapter__list-box > li":[...Array.from({length:670},(_,i)=>chapter(i+1)),chapter(670)]}});
            const chapters=await s.loadChapters("/comic/fixture");
            eq(Object.keys(chapters).length,670); eq(Object.keys(chapters)[0],"/chapter/1");
            eq(Object.keys(chapters)[669],"/chapter/670");
            htmlReply({select:{"img[data-original]":[
                {attributes:{"data-original":"//img.test/first.jpg"}},
                {attributes:{"data-original":"//img.test/last.jpg"}}]}});
            eq((await s.comic.loadEp("/comic/fixture","/chapter/670")).images,
               ["https://img.test/first.jpg","https://img.test/last.jpg"]);
            eq(s.comic.onImageLoad("https://img.test/last.jpg").headers,s.headers);
        ''', source_id=MANHUAWU)

    def test_hanman18_empty_manifest_rejects_before_zero_page_reader_boundary(self):
        self.runtime("manga18", r'''
            htmlReply('var slides_p_path = [];');
            await rejects(()=>s.comic.loadEp("/manhwa/youqingwanshui","/manhwa/youqingwanshui/115"),
                "HANMAN18: upstream chapter has no readable images");
            decodeReplies.push(asciiBytes("https://img.test/chapter/").buffer);
            htmlReply('var slides_p_path = ["YQ=="];');
            await rejects(()=>s.comic.loadEp("/manhwa/a","/manhwa/a/1"),"no readable images");
            htmlReply('missing');
            await rejects(()=>s.comic.loadEp("/manhwa/a","/manhwa/a/1"),"Missing Manga18 reader data");
        ''', locale="zh-Hant", source_id=HANMAN18)

    def test_hanman18_valid_manifest_preserves_first_middle_last_and_white_artwork(self):
        values = ["https://img.test/chapter/", "//img.test/first.jpg", "//img.test/first.jpg",
                  " /chapter/middle.jpg\r\n", "https://img.test/white-artwork.jpg", "https://img.test/last.jpg"]
        encoded = [base64.b64encode(v.encode()).decode() for v in values]
        body = "var slides_p_path = " + json.dumps(encoded) + ";"
        self.runtime("manga18", f'''
            const decoded={json.dumps(dict(zip(encoded, values)))};
            Convert.decodeBase64=value=>asciiBytes(decoded[value]).buffer;
            htmlReply({json.dumps(body)});
            const pages=(await s.comic.loadEp("/manhwa/a","/manhwa/a/1")).images;
            eq(pages,["https://img.test/first.jpg",s.baseUrl+"/chapter/middle.jpg",
                      "https://img.test/white-artwork.jpg","https://img.test/last.jpg"]);
            eq(calls[0].headers,{{Referer:"https://hanman18.com/"}});
            eq(s.comic.onImageLoad(pages[3]),{{url:pages[3],headers:{{Referer:"https://hanman18.com/"}}}});
        ''', locale="zh-Hant", source_id=HANMAN18)

    def test_hanman18_fixture_owned_320_rows_317_identities_and_latest_retention(self):
        self.runtime("manga18", r'''
            const row=i=>({select:{a:[{text:"Chapter "+i,attributes:{href:"/manhwa/a/"+({215:219,214:218,213:217}[i]||i)}},
                {text:"",attributes:{href:"/download/not-a-chapter"}}]}});
            htmlReply({select:{"div.chapter_box .item":Array.from({length:320},(_,i)=>row(320-i))}});
            const chapters=await s.loadChapters("/manhwa/a"), ids=Object.keys(chapters);
            eq(ids.length,317); eq(ids[0],"/manhwa/a/1"); eq(ids[316],"/manhwa/a/320");
            eq(chapters["/manhwa/a/219"],"Chapter 219");
            ok(!ids.includes("/download/not-a-chapter"));
            for(let i=1;i<ids.length;i++) ok(Number(ids[i].split("/").pop())>Number(ids[i-1].split("/").pop()));
        ''', locale="zh-Hant", source_id=HANMAN18)
