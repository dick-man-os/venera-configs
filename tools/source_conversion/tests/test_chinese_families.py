"""Offline payload/runtime regressions for exact-pin Chinese family contracts."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import jsonschema
import quickjs

ROOT = Path(__file__).resolve().parents[3]
EXTRACTOR = ROOT / "tools/source_conversion/extractor"
sys.path.insert(0, str(EXTRACTOR))
from source_adapters import chinese_families as families
from extract import dispatch_extraction
from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.validator.validate_ir import validate_ir_data
from tools.source_conversion.extractor.common.dispatch_rules import adapter_for_candidate
from tools.source_conversion.planner.eligibility_planner import build_plan

STAMP = "2026-09-07T00:00:00Z"
CANDIDATES = [c for m in sorted(families.ENABLED) for c in families.MANIFEST["families"][m]["candidates"]]
SCHEMA = json.loads((ROOT / "tools/source_conversion/schema/ir_v0_2.schema.json").read_bytes())
HARNESS = r"""
class ComicSource {}
class Comic { constructor(data) { Object.assign(this, data); } }
class ComicDetails { constructor(data) { Object.assign(this, data); } }
let disposed = 0, calls = [], replies = [];
let decodeReplies = [], decryptReplies = [], convertCalls = [];
function asciiBytes(value) {
    const result = new Uint8Array(value.length);
    for (let i=0;i<value.length;i++) result[i] = value.charCodeAt(i);
    return result;
}
const Convert = {
    decodeBase64: value => {
        convertCalls.push({kind:"base64",value});
        if (!decodeReplies.length) throw new Error("Unexpected base64 decode");
        return decodeReplies.shift();
    },
    decodeUtf8: value => {
        const bytes = new Uint8Array(value), chars = [];
        for (const byte of bytes) chars.push(String.fromCharCode(byte));
        return chars.join("");
    },
    encodeUtf8: value => asciiBytes(value).buffer,
    decryptAesCbc: (data,key,iv) => {
        convertCalls.push({kind:"aes",data:Array.from(new Uint8Array(data)),key:Array.from(new Uint8Array(key)),iv:Array.from(new Uint8Array(iv))});
        if (!decryptReplies.length) throw new Error("Unexpected AES decrypt");
        return decryptReplies.shift();
    }
};
class Node {
    constructor(data = {}) { this.data = data; this.text = data.text || ""; this.attributes = data.attributes || {}; }
    querySelectorAll(selector) { return (this.data.select?.[selector] || []).map(x => new Node(x)); }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
class HtmlDocument extends Node { dispose() { disposed++; } }
const Network = {
    get: async (url, headers) => respond("GET", url, undefined, headers),
    post: async (url, headers, data) => respond("POST", url, JSON.parse(data), headers)
};
function respond(method, url, data, headers) {
    calls.push({method, url, data, headers});
    if (!replies.length) throw new Error("Unexpected network call: " + url);
    return replies.shift();
}
function jsonReply(body, status = 200) { replies.push({status, body: JSON.stringify(body)}); }
function htmlReply(body, status = 200) { replies.push({status, body}); }
function eq(actual, expected) {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(JSON.stringify({actual, expected}));
}
function ok(value) { if (!value) throw new Error("Assertion failed"); }
async function rejects(fn, text) {
    try { await fn(); } catch (e) { if (String(e).includes(text)) return; throw e; }
    throw new Error("Expected rejection: " + text);
}
"""


def candidate(family, locale="zh-Hans"):
    return next(c for c in CANDIDATES if families.family_name(c["module"]) == family and families.reviewed_locale(c) == locale)


def node(text="", attrs=None, select=None):
    return {"text": text, "attributes": attrs or {}, "select": select or {}}


class FamilyContractTests(unittest.TestCase):
    def runtime(self, family, code, locale="zh-Hans", source_id=None):
        selected = (next(c for c in CANDIDATES if c["sourceId"] == source_id)
                    if source_id else candidate(family, locale))
        ir = families.make_ir(selected, STAMP)
        ctx = quickjs.Context()
        source = generate_venera_js(ir)
        classname = "Keiyoushi" + ir["provenance"]["upstreamSourceId"] + "Source"
        ctx.eval(HARNESS + source + "\nlet completed = false, failure = null; const s = new " + classname + "();\n" +
                 "(async () => {" + code + "\n eq(replies.length, 0); })().then(() => {completed = true;}).catch(e => {failure = String(e.stack || e);});")
        jobs = 0
        while ctx.execute_pending_job():
            jobs += 1
            self.assertLess(jobs, 10000)
        self.assertIsNone(ctx.eval("failure"))
        self.assertTrue(ctx.eval("completed"))

    def test_exact_identity_locale_dispatch_ir_schema_and_generator(self):
        keys = set()
        for c in CANDIDATES:
            with self.subTest(source=c["sourceId"]):
                ir = families.make_ir(c, STAMP)
                self.assertEqual(validate_ir_data(ir), [])
                jsonschema.validate(ir, SCHEMA)
                self.assertEqual(ir["languages"], [families.reviewed_locale(c)])
                self.assertEqual(ir["provenance"]["upstreamSourceId"], c["sourceId"])
                self.assertEqual(adapter_for_candidate(c), families.family_name(c["module"]))
                self.assertNotIn(ir["id"], keys)
                keys.add(ir["id"])
                js = generate_venera_js(ir)
                self.assertEqual(js, generate_venera_js(copy.deepcopy(ir)))
                self.assertNotIn("eval(", js)
                self.assertNotIn("MANUAL PATCH", js)
                self.assertIn('key = "' + ir["id"] + '"', js)

    def test_unknown_and_bare_zh_instances_keep_generic_route(self):
        for c in CANDIDATES:
            changed = {**c, "sourceId": "1", "upstreamLang": "zh"}
            self.assertEqual(adapter_for_candidate(changed), "generic-html")
            self.assertIsNone(families.candidate_contract(changed, families.PIN))

    def test_wrong_pin_never_supplies_eligibility_evidence(self):
        for c in CANDIDATES:
            self.assertIsNone(families.candidate_contract(c, "f" * 40))

    def test_mutated_inventory_candidate_never_supplies_evidence(self):
        for key, value in (("baseUrl", "https://wrong.test"), ("name", "Wrong"), ("version", "1.4.999")):
            self.assertIsNone(families.candidate_contract({**CANDIDATES[0], key: value}, families.PIN))

    def test_partial_or_modified_ir_contract_rejected(self):
        original = families.make_ir(CANDIDATES[0], STAMP)
        for key, value in (("chapters", {}), ("provenance", None), ("provenance", []), ("provenance", "invalid"),
                           ("requiresAuth", True), ("familyContract", "unknown"),
                           ("languages", ["zh"]), ("id", "shared_key")):
            with self.subTest(key=key):
                ir = {**original, key: value}
                self.assertTrue(validate_ir_data(ir))
                with self.assertRaises(ValueError):
                    generate_venera_js(ir)

    def test_materializer_local_identity_and_version_remain_separate(self):
        ir = families.make_ir(CANDIDATES[0], STAMP)
        ir.update(artifactId="reviewed_fixture", version="1.0.0")
        self.assertEqual(validate_ir_data(ir), [])

    def test_extractor_attests_files_and_rejects_source_drift(self):
        c = CANDIDATES[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.kt"
            path.write_bytes(b"sanitized static upstream contract")
            entry = {"files": {"source.kt": hashlib.sha256(path.read_bytes()).hexdigest()}, "candidates": [c]}
            with mock.patch.dict(families.MANIFEST["families"], {c["module"]: entry}), \
                 mock.patch.object(families.subprocess, "check_output", return_value=families.PIN):
                ir = dispatch_extraction(tmp, c["module"].replace(".", "/"), timestamp=STAMP, source_id=c["sourceId"])
                self.assertEqual(ir["provenance"]["upstreamSourceId"], c["sourceId"])
                path.write_bytes(b"changed")
                with self.assertRaisesRegex(ValueError, "source drift"):
                    families.extract(tmp, c["module"], STAMP, source_id=c["sourceId"])

    def test_extractor_rejects_wrong_pin_and_locale(self):
        c = CANDIDATES[0]
        with mock.patch.object(families.subprocess, "check_output", return_value="f" * 40):
            with self.assertRaisesRegex(ValueError, "exact reviewed"):
                families.extract(".", c["module"], STAMP, source_id=c["sourceId"])
        with mock.patch.dict(families.MANIFEST["families"], {c["module"]: {"files": {}, "candidates": [c]}}), \
             mock.patch.object(families.subprocess, "check_output", return_value=families.PIN):
            with self.assertRaisesRegex(ValueError, "locale"):
                families.extract(".", c["module"], STAMP, "zh", c["sourceId"])
            with self.assertRaisesRegex(ValueError, "source ID"):
                families.extract(".", c["module"], STAMP, source_id="1")

    def test_all_primary_candidates_receive_e2_without_inventory_mutation(self):
        # Registry schema is reused, with no production ownership inferred.
        registry = json.loads((ROOT / "sources_registry.json").read_bytes())
        registry["artifacts"] = [{"artifactId": "unrelated", "runtimeKey": "unrelated", "providerId": "unrelated", "implementation": {"producer": "manual"}}]
        inventory = {"schemaVersion": "1.0", "upstreams": [{"project": "keiyoushi/extensions-source", "commit": families.PIN}],
                     "candidates": sorted(CANDIDATES, key=lambda c: (c["project"], c["sourceId"])), "unresolvedModules": []}
        original = copy.deepcopy(inventory)
        plan = build_plan(inventory, registry)
        self.assertTrue(all(c["eligibility"] == "E2" and c["patchState"] == "not-required" for c in plan["candidates"]))
        self.assertEqual(inventory, original)

    def test_url_normalization_and_invalid_scheme(self):
        self.runtime("iqiyi", r"""
            eq(s.absolute("../a.jpg", "https://img.test/path/reader/1"), "https://img.test/path/a.jpg");
            eq(s.absolute("//cdn.test/1"), "https://cdn.test/1");
            eq(s.absolute("?page=2", "https://x.test/list?p=1"), "https://x.test/list?page=2");
            await rejects(() => s.absolute("javascript:bad"), "scheme");
        """)

    def test_http_errors_and_invalid_page(self):
        for family in ("globalcomix", "namicomi", "dongmanmanhua", "iqiyi", "mccms"):
            with self.subTest(family=family):
                self.runtime(family, r"""
                    jsonReply({}, 403); await rejects(() => s.search.load("x", {}, 1), "HTTP 403");
                    jsonReply({}, 402); await rejects(() => s.search.load("x", {}, 1), "Payment");
                    await rejects(() => s.search.load("x", {}, 0), "Invalid page");
                """)

    def test_mccms_raw_zh_is_exactly_reviewed_as_simplified(self):
        candidates = [c for c in CANDIDATES if families.family_name(c["module"]) == "mccms"]
        self.assertEqual(len(candidates), 3)
        for c in candidates:
            with self.subTest(module=c["module"]):
                self.assertEqual(c["upstreamLang"], "zh")
                self.assertEqual(families.reviewed_locale(c), "zh-Hans")
                ir = families.make_ir(c, STAMP)
                self.assertEqual(ir["languages"], ["zh-Hans"])
                self.assertEqual(ir["familyContract"], "mccms-v1")
                self.assertEqual(set(ir["headers"]), {"User-Agent"})

    def test_mccms_default_catalog_search_pagination_and_dedup(self):
        item = node(select={
            ".comic__title > a": [node("Fixture", {"href": "/index.php/comic/fixture"})],
            "img": [node(attrs={"data-original": "//img.test/cover.jpg"})],
        })
        more = node(select={
            ".common-comic-item": [item, item],
            "#Pagination a, .NewPages a": [node(attrs={"href": "/page/1"}), node(attrs={"href": "/page/2"})],
        })
        final = node(select={
            ".common-comic-item": [item],
            "#Pagination a, .NewPages a": [node(attrs={"href": "/page/2"}), node(attrs={"href": "/page/2"})],
        })
        self.runtime("mccms", f"""
            htmlReply({json.dumps(more)}); const popular=await s.explore[0].load(1);
            eq(popular.comics.length,1); eq(popular.comics[0].id,"/comic/fixture");
            eq(popular.comics[0].cover,"https://img.test/cover.jpg"); eq(popular.hasMore,true);
            htmlReply({json.dumps(final)}); const search=await s.search.load("斗罗 大陆",{{}},2);
            eq(search.hasMore,false); ok(calls[1].url.endsWith("/search/%E6%96%97%E7%BD%97%20%E5%A4%A7%E9%99%86/2"));
            eq(await s.search.load("   ",{{}},1),{{comics:[],hasMore:false}}); eq(disposed,2);
        """, source_id="3279300917142951720")

    def test_mccms_details_and_old_to_new_chapter_contract(self):
        details_root = node(select={
            ".comic-title": [node("Fixture")], "img": [node(attrs={"src": "/cover.jpg"})],
            ".name": [node("Author")], ".intro-total": [node("Summary")],
            ".comic-status a": [node("冒险"), node("剧情")],
        })
        details = node(select={".de-info__box": [details_root]})
        def chapter(title, href):
            return node(select={"a": [node(title, {"href": href})]})
        chapters = node(select={".chapter__list-box > li": [
            chapter("Old", "/index.php/chapter/1"), chapter("Old duplicate", "/index.php/chapter/1"),
            chapter("New", "/index.php/chapter/2"),
        ]})
        self.runtime("mccms", f"""
            htmlReply({json.dumps(details)}); const info=await s.info("/comic/fixture");
            eq(info.title,"Fixture"); eq(info.subtitle,"Author"); eq(info.description,"Summary");
            eq(info.cover,s.baseUrl+"/cover.jpg"); eq(info.tags,{{Genre:["冒险","剧情"]}});
            htmlReply({json.dumps(chapters)}); const eps=await s.loadChapters("/comic/fixture");
            eq(Object.keys(eps),["/chapter/1","/chapter/2"]); eq(Object.values(eps),["Old","New"]);
        """, source_id="3279300917142951720")

        six_chapters = node(select={"ul#mh-chapter-list-ol-0 li.chapter__item": [
            chapter("New", "/comic/2.html"), chapter("Old", "/comic/1.html"),
        ]})
        self.runtime("mccms", f"""
            htmlReply({json.dumps(six_chapters)}); const eps=await s.loadChapters("/comic/fixture");
            eq(Object.keys(eps),["/comic/1.html","/comic/2.html"]); eq(Object.values(eps),["Old","New"]);
        """, source_id="5183325399429659419")

        miaoqu_chapters = node(select={"ul.list > li": [
            chapter("Old", "/263176/63234.html"), chapter("New", "/263176/63235.html"),
        ]})
        self.runtime("mccms", f"""
            htmlReply({json.dumps(miaoqu_chapters)}); const eps=await s.loadChapters("/fixture");
            eq(Object.values(eps),["Old","New"]); eq(calls[0].url,"https://m.miaoqumh.org/fixture");
        """, source_id="116946528518438525")

    def test_mccms_reader_variants_order_dedup_decoding_and_headers(self):
        default_reader = node(select={"img[data-original]": [
            node(attrs={"data-original": "//img.test/1.jpg"}),
            node(attrs={"data-original": "//img.test/1.jpg"}),
            node(attrs={"data-original": "/2.jpg"}),
        ]})
        self.runtime("mccms", f"""
            htmlReply({json.dumps(default_reader)}); const images=await s.images("/comic/a","/chapter/1");
            eq(images,["https://img.test/1.jpg",s.baseUrl+"/2.jpg"]); eq(calls[0].headers,s.headers);
            ok(!("Referer" in calls[0].headers)); eq(disposed,1);
        """, source_id="3279300917142951720")

        self.runtime("mccms", r"""
            const stage="fixture-base64", key="8-mbJpU7", encrypted=asciiBytes(stage);
            for(let i=0;i<encrypted.length;i++) encrypted[i]^=key.charCodeAt(i&7);
            decodeReplies.push(encrypted.buffer,asciiBytes('[{"url":"//img.test/1.jpg"},{"url":"//img.test/1.jpg"},{"url":"/2.jpg"}]').buffer);
            htmlReply("var DATA='fixture'",500);
            eq(await s.images("/263176","/263176/63234.html"),["https://img.test/1.jpg",s.config.mobileUrl+"/2.jpg"]);
            eq(calls[0].url,s.config.mobileUrl+"/263176/63234.html"); eq(convertCalls.length,2);
            htmlReply("missing",500); await rejects(()=>s.images("x","/1/63234.html"),"Missing Miaoqu");
        """, source_id="116946528518438525")

        self.runtime("mccms", r"""
            const raw=new Uint8Array(32); for(let i=16;i<32;i++) raw[i]=i;
            const json=asciiBytes('{"images":["//img.test/1.jpg","/2.jpg"]}'), padding=16-(json.length%16);
            const padded=new Uint8Array(json.length+padding); padded.set(json); padded.fill(padding,json.length);
            decodeReplies.push(raw.buffer); decryptReplies.push(padded.buffer); htmlReply("params = 'fixture'");
            eq(await s.images("/263176","/263176/63234.html"),["https://img.test/1.jpg",s.baseUrl+"/2.jpg"]);
            eq(convertCalls[1].kind,"aes"); eq(String.fromCharCode(...convertCalls[1].key),"9S8$vJnU2ANeSRoF");
            eq(convertCalls[1].iv,new Array(16).fill(0)); eq(convertCalls[1].data,[16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31]);
        """, source_id="5183325399429659419")

    def test_globalcomix_catalog_first_next_final_locale_and_dedup(self):
        for locale, query in (("zh-Hans", "cn"), ("zh-Hant", "zh")):
            with self.subTest(locale=locale):
                self.runtime("globalcomix", r"""
                    const m = {id: 12, name: "Title One", slug: "title-one", image_url: "//cdn.test/cover.jpg", artist: {name: "Author"}};
                    jsonReply({payload:{results:[m,m],pagination:{page:1,total_pages:2}}});
                    const first = await s.explore[0].load(1);
                    eq(first.comics.length, 1); eq(first.hasMore, true); eq(first.comics[0].id, "12/title-one");
                    jsonReply({payload:{results:[],pagination:{page:2,total_pages:2}}});
                    const last = await s.search.load("漢 & 字", {}, 2);
                    eq(last, {comics:[],hasMore:false,maxPage:2});
                    ok(calls[0].url.includes("lang_id%5B%5D=LANG"));
                    ok(calls[1].url.includes("lang_id%5B%5D=LANG"));
                    ok(calls[1].url.includes("p=2")); ok(calls[1].url.includes("sort=relevance"));
                    ok(calls[0].headers["x-gc-client"].startsWith("gck_"));
                """.replace("LANG", query), locale)

    def test_globalcomix_details_and_identity_check(self):
        self.runtime("globalcomix", r"""
            const m = {id:12,name:"Title One",slug:"title-one",description:"Description",artist:{roman_name:"Author"}};
            jsonReply({payload:{results:m}});
            eq((await s.info("12/title-one")).description, "Description");
            eq(calls[0].url, "https://api.globalcomix.com/v1/read/title-one");
            jsonReply({payload:{results:{...m,id:13}}});
            await rejects(() => s.info("12/title-one"), "identity mismatch");
        """)

    def test_globalcomix_authoritative_slug_survives_translated_title(self):
        for locale in ("zh-Hans", "zh-Hant"):
            with self.subTest(locale=locale):
                self.runtime("globalcomix", r"""
                    const m = {id:31985,name:"侯門少爺寵上天",slug:"the-marquis-s-cherished-one"};
                    jsonReply({payload:{results:[m],pagination:{page:1,total_pages:1}}});
                    const list = await s.explore[0].load(1);
                    eq(list.comics[0].id, "31985/the-marquis-s-cherished-one");
                    jsonReply({payload:{results:m}});
                    eq((await s.info(list.comics[0].id)).title, m.name);
                    eq(calls[1].url, "https://api.globalcomix.com/v1/read/the-marquis-s-cherished-one");
                    jsonReply({payload:{results:[{id:31985,name:m.name}],pagination:{page:1,total_pages:1}}});
                    await rejects(() => s.explore[0].load(1), "Missing required value");
                """, locale)

    def test_globalcomix_chapters_preserve_order_and_hide_paid(self):
        self.runtime("globalcomix", r"""
            jsonReply({payload:{results:[
                {key:"b",chapter:"2",title:"Two",premium_only:0},
                {key:"paid",chapter:"3",title:"Paid",premium_only:1},
                {key:"a",chapter:"1",title:"One",premium_only:0},
                {key:"a",chapter:"1",title:"One",premium_only:0}]}});
            eq(await s.loadChapters("12/title"), {b:"Ch.2 - Two",a:"Ch.1 - One"});
            ok(calls[0].url.includes("lang_id=cn")); ok(calls[0].url.includes("all=true"));
        """)

    def test_globalcomix_pages_order_and_paid_rejection(self):
        self.runtime("globalcomix", r"""
            jsonReply({payload:{results:{key:"c",premium_only:0,page_objects:[
                {is_page_paid:false,desktop_image_url:"https://img.test/2"},
                {is_page_paid:false,desktop_image_url:"//img.test/1"}]}}});
            eq(await s.images("12/title","c"), ["https://img.test/2","https://img.test/1"]);
            jsonReply({payload:{results:{key:"c",premium_only:1,page_objects:[]}}});
            await rejects(() => s.images("12/title","c"), "Paid chapter");
            jsonReply({payload:{results:{key:"c",page_objects:[{is_page_paid:true,desktop_image_url:"https://img.test/paid"}]}}});
            await rejects(() => s.images("12/title","c"), "page access");
        """)

    def test_globalcomix_empty_and_incomplete_response(self):
        self.runtime("globalcomix", r"""
            jsonReply({payload:{results:[]}}); eq(await s.loadChapters("1/a"), {});
            jsonReply({payload:{results:{key:"c",page_objects:[]}}}); eq(await s.images("1/a","c"), []);
            jsonReply({}); await rejects(() => s.explore[0].load(1), "payload");
            jsonReply({payload:{results:[],pagination:{page:1,total_pages:2}}});
            await rejects(() => s.loadChapters("1/a"), "Incomplete");
        """)

    def test_namicomi_locale_title_relationships_and_catalog_pagination(self):
        for locale in ("zh-Hans", "zh-Hant"):
            self.runtime("namicomi", r"""
                const m={id:"m",attributes:{title:{"zh-hans":"简","zh-hant":"繁"},description:{en:"fallback"}},
                    relationships:[{type:"cover_art",attributes:{fileName:"cover.jpg"}},{type:"organization",attributes:{name:"Author"}}]};
                jsonReply({result:"ok",data:[m,m],meta:{offset:0,limit:20,total:21}});
                const a=await s.explore[0].load(1);
                eq(a.comics.length,1); eq(a.hasMore,true); eq(a.comics[0].title,s.locale === "zh-Hans" ? "简" : "繁");
                eq(a.comics[0].description,"fallback"); eq(a.comics[0].subtitle,"Author");
                ok(a.comics[0].cover.endsWith("/m/cover.jpg"));
                jsonReply({result:"ok",data:[],meta:{offset:20,limit:20,total:21}});
                eq(await s.search.load("中文",{},2),{comics:[],hasMore:false,maxPage:2});
                ok(calls.every(c=>c.url.includes("availableTranslatedLanguages%5B%5D="+s.locale.toLowerCase())));
                ok(calls[1].url.includes("offset=20"));
            """, locale)

    def test_namicomi_details_and_fallback(self):
        self.runtime("namicomi", r"""
            jsonReply({result:"ok",data:{id:"m",attributes:{title:{en:"Fallback"},description:{en:"Description"}},relationships:[]}});
            eq((await s.info("m")).title,"Fallback");
            ok(calls[0].url.includes("/title/m?includes"));
        """)

    def test_namicomi_chapters_two_pages_order_access_and_dedup(self):
        for locale in ("zh-Hans", "zh-Hant"):
            self.runtime("namicomi", r"""
                const a={id:"a",attributes:{volume:"1",chapter:"2",name:"Two"}};
                const b={id:"b",attributes:{chapter:"1",name:"One"}};
                jsonReply({result:"ok",data:[a],meta:{offset:0,limit:200,total:201}});
                jsonReply({result:"ok",data:[a,b],meta:{offset:200,limit:200,total:201}});
                jsonReply({result:"ok",data:{attributes:{map:{a:true,b:false}}}});
                eq(await s.loadChapters("m"),{a:"Vol.1 Ch.2 - Two"});
                ok(calls[1].url.includes("offset=200"));
                for(const call of calls.slice(0,2)) ok(call.url.includes("translatedLanguages%5B%5D="+s.locale.toLowerCase()));
                eq(calls[2].data,{entities:[{entityId:"a",entityType:"chapter"},{entityId:"b",entityType:"chapter"}]});
                eq(calls[2].method,"POST");
            """, locale)

    def test_namicomi_access_batches_of_200(self):
        self.runtime("namicomi", r"""
            const ids=Array.from({length:201},(_,i)=>"c"+i);
            jsonReply({result:"ok",data:{attributes:{map:Object.fromEntries(ids.slice(0,200).map(id=>[id,true]))}}});
            jsonReply({result:"ok",data:{attributes:{map:{c200:false}}}});
            const access=await s.access(ids);
            eq(calls[0].data.entities.length,200); eq(calls[1].data.entities.length,1); eq(access.c200,false);
        """)

    def test_namicomi_missing_access_never_means_free(self):
        self.runtime("namicomi", r"""
            jsonReply({result:"ok",data:{attributes:{map:{}}}});
            await rejects(()=>s.images("m","a"),"Unknown chapter access");
            jsonReply({result:"ok",data:{attributes:{map:{a:false}}}});
            await rejects(()=>s.images("m","a"),"access denied");
            eq(calls.length,2);
        """)

    def test_namicomi_pages_order_quality_url_and_empty(self):
        self.runtime("namicomi", r"""
            jsonReply({result:"ok",data:{attributes:{map:{a:true}}}});
            jsonReply({result:"ok",data:{baseUrl:"https://cdn.test",hash:"hash",source:[{filename:"2.jpg"},{filename:"1.jpg"}],low:[{filename:"low.jpg"}]}});
            eq(await s.images("m","a"),["https://cdn.test/chapter/a/hash/source/2.jpg","https://cdn.test/chapter/a/hash/source/1.jpg"]);
            jsonReply({result:"ok",data:{attributes:{map:{a:true}}}});
            jsonReply({result:"ok",data:null}); eq(await s.images("m","a"),[]);
        """)

    def test_namicomi_204_empty_and_no_gating_for_empty_chapters(self):
        self.runtime("namicomi", r"""
            jsonReply(null,204); eq(await s.explore[1].load(1),{comics:[],hasMore:false,maxPage:1});
            jsonReply(null,204); eq(await s.loadChapters("m"),{});
            eq(calls.length,2);
        """)

    def test_namicomi_rejects_nonprogressing_pagination(self):
        self.runtime("namicomi", r"""
            jsonReply({result:"ok",data:[],meta:{limit:0,offset:0,total:20}});
            await rejects(()=>s.loadChapters("m"),"pagination");
            jsonReply({result:"ok",data:[],meta:{limit:200,offset:0,total:201}});
            await rejects(()=>s.loadChapters("m"),"Non-progressing");
        """)

    def test_dongman_catalog_and_search_pagination(self):
        item=node(attrs={"href":"/title"},select={"p.subj":[node("Title")],"img":[node(attrs={"src":"//img.test/cover"})]})
        popular=node(select={"div#dailyList .daily_section li a, div.daily_lst.comp li a":[item,item]})
        search=node(select={"#content > div.card_wrap.search ul:not(#filterLayer) li a":[item],
                            "div.more_area, div.paginate a[onclick] + a":[node()]})
        self.runtime("dongmanmanhua", f"""
            htmlReply({json.dumps(popular)}); const a=await s.explore[0].load(1);
            eq(a.comics.length,1); eq(a.hasMore,false);
            htmlReply({json.dumps(search)}); eq((await s.search.load("a & b",{{}},1)).hasMore,true);
            htmlReply({{}}); eq((await s.search.load("a & b",{{}},2)).hasMore,false);
            ok(calls[1].url.includes("keyword=a%20%26%20b")); ok(calls[2].url.includes("page=2"));
            eq(disposed,3);
        """)

    def test_dongman_details_and_background_cover(self):
        doc=node(select={"h1.subj, h3.subj":[node("Title")],"#_asideDetail p.summary":[node("Summary")],
                         "#content > div.cont_box > div.detail_body":[node(attrs={"style":"background-image: url('//img.test/cover.jpg')"})]})
        self.runtime("dongmanmanhua", f"""
            htmlReply({json.dumps(doc)}); const a=await s.info("/title"); eq(a.title,"Title");
            eq(a.description,"Summary"); eq(a.cover,"https://img.test/cover.jpg"); eq(disposed,1);
        """)

    def test_dongman_chapter_following_order_dedup_and_termination(self):
        def row(name, href): return node(select={"a":[node(attrs={"href":href})],"span.subj span":[node(name)]})
        first=node(select={"ul#_listUl li":[row("Two","/read/2")],"div.paginate a[onclick] + a":[node(attrs={"href":"?page=2"})]})
        last=node(select={"ul#_listUl li":[row("Two","/read/2"),row("One","/read/1")]})
        self.runtime("dongmanmanhua", f"""
            htmlReply({json.dumps(first)}); htmlReply({json.dumps(last)});
            eq(Object.values(await s.loadChapters("/title")),["One","Two"]);
            eq(calls[1].url,s.baseUrl+"/title?page=2"); eq(disposed,2);
        """)

    def test_dongman_chapter_cycle_fails_without_partial_results(self):
        doc=node(select={"ul#_listUl li":[node(select={"a":[node(attrs={"href":"/read/1"})],"span.subj span":[node("One")]})],
                         "div.paginate a[onclick] + a":[node(attrs={"href":"/title"})]})
        self.runtime("dongmanmanhua", f"""
            htmlReply({json.dumps(doc)}); await rejects(()=>s.loadChapters("/title"),"Cyclic");
            eq(disposed,1);
        """)

    def test_dongman_pages_order_empty_and_document_disposal(self):
        doc=node(select={"div#_imageList > img":[node(attrs={"data-url":"//img.test/2"}),node(attrs={"data-url":"/1"})]})
        self.runtime("dongmanmanhua", f"""
            htmlReply({json.dumps(doc)}); eq(await s.images("/title","/read/1"),["https://img.test/2",s.baseUrl+"/1"]);
            htmlReply({{}}); eq(await s.images("/title","/read/1"),[]); eq(disposed,2);
        """)

    def test_iqiyi_catalog_and_search_next_page_without_jsoup_pseudoselector(self):
        item=node(select={"a.cartoon-item-tit":[node("Title",{"href":"/manhua/detail_12.html"})],
                          "img":[node(attrs={"src":"//img.test/cover"})]})
        doc=node(select={"ul.cartoon-hot-ul > li.cartoon-hot-list":[item],"div.mod-page > a.a1":[node("下一页")]})
        self.runtime("iqiyi", f"""
            htmlReply({json.dumps(doc)}); const r=await s.explore[0].load(1); eq(r.comics.length,1); eq(r.hasMore,true);
            htmlReply({{}}); eq(await s.search.load("漢 & 字",{{}},2),{{comics:[],hasMore:false}});
            ok(calls[1].url.includes("search-keyword=%E6%BC%A2%20%26%20%E5%AD%97_2"));
        """)

    def test_iqiyi_details(self):
        doc=node(select={"div.detail-tit > h1":[node("Title")],"p.detail-docu":[node("Summary")],
                         "p.author > span.author-name":[node("Author")],"div.detail-cover > img":[node(attrs={"src":"//img.test/cover"})]})
        self.runtime("iqiyi", f"""
            htmlReply({json.dumps(doc)}); const a=await s.info("/manhua/detail_12.html");
            eq(a.title,"Title"); eq(a.description,"Summary"); eq(a.subtitle,"Author"); eq(disposed,1);
        """)

    def test_iqiyi_json_chapter_identity_titles_reverse_and_empty(self):
        self.runtime("iqiyi", r"""
            jsonReply({data:{episodes:[
                {comicId:"12",episodeId:"1",episodeTitle:"One",episodeOrder:1},
                {comicId:"12",episodeId:"2",episodeTitle:"Two",episodeOrder:2}]}});
            const chapters=await s.loadChapters(s.baseUrl+"/detail_12.html");
            eq(Object.values(chapters),["2 Two","1 One"]);
            eq(Object.keys(chapters)[0],s.baseUrl+"/reader/12_2.html");
            eq(calls[0].url,s.baseUrl+"/catalog/12/");
            jsonReply({data:null}); eq(await s.loadChapters(s.baseUrl+"/detail_12.html"),{});
        """)

    def test_iqiyi_paid_page_rejection_image_fallback_and_order(self):
        paid=node(select={"div.main > p.pay-title":[node("Paid")]})
        free=node(select={"ul.main-container > li.main-item > img":[node(attrs={"data-original":"//img.test/2","src":"bad"}),node(attrs={"src":"1.jpg"})]})
        self.runtime("iqiyi", f"""
            htmlReply({json.dumps(paid)}); await rejects(()=>s.images("12",s.baseUrl+"/reader/1.html"),"付费");
            htmlReply({json.dumps(free)}); eq(await s.images("12",s.baseUrl+"/reader/1.html"),["https://img.test/2",s.baseUrl+"/reader/1.jpg"]);
            htmlReply({{}}); eq(await s.images("12",s.baseUrl+"/reader/1.html"),[]); eq(disposed,3);
        """)


    def test_yellownote_catalog_locales_warning_pagination_and_empty(self):
        link=node(attrs={"href":"/album.html","title":"Fixture"},select={"div.img":[node(attrs={"style":"background-image:url('//img.test/cover')"})]})
        item=node(select={"a":[link],"div.tags > div":[node("3P + 1V")]})
        doc=node(select={"div.list.photo-list > div.item.photo, div.list.amateur-list > div.item.amateur":[item,item],
                         "div.pager:first-of-type > a.pager-next":[node()]})
        for locale in ("zh-Hans","zh-Hant"):
            self.runtime("yellownote",f"""
                eq(s.config.contentWarning,"NSFW");
                htmlReply({json.dumps(doc)}); const r=await s.search.load("字 & x",{{}},1);
                eq(r.comics.length,1); eq(r.comics[0].title,"Fixture(3P + 1V)"); eq(r.comics[0].tags,["NSFW"]); eq(r.hasMore,true);
                ok(calls[0].url.startsWith(s.baseUrl)); ok(calls[0].url.includes("%E5%AD%97%20%26%20x"));
                htmlReply({{}}); eq(await s.explore[1].load(2),{{comics:[],hasMore:false}});
            """,locale)

    def test_yellownote_details_without_unsupported_has_selector(self):
        def field(icon,value): return node(select={".icon > "+icon:[node()],"div.text":[node(value)]})
        card=node(select={"div.item":[field("i.fa-address-card","Fixture"),field("i.fa-image","3P"),field("i.fa-file","001"),field("i.fa-circle-user","Author")]})
        doc=node(select={"div.info-card.photo-detail":[card]})
        self.runtime("yellownote",f"""
            htmlReply({json.dumps(doc)}); const r=await s.info("/album.html");
            eq(r.title,"Fixture 001(3P)"); eq(r.subtitle,"Author"); eq(r.tags,{{Content:["NSFW"]}});
            htmlReply({{}}); await rejects(()=>s.info("/bad.html"),"info card"); eq(disposed,2);
        """)

    def test_yellownote_synthetic_chapters_order_and_bound(self):
        doc=node(select={"div.info-card.photo-detail":[node()],"div.pager:first-of-type a.pager-num":[node("1"),node("3")]})
        bad=node(select={"div.info-card.photo-detail":[node()],"div.pager:first-of-type a.pager-num":[node("10001")]})
        self.runtime("yellownote",f"""
            htmlReply({json.dumps(doc)}); const chapters=await s.loadChapters("/album.html");
            eq(Object.values(chapters),["Page 3","Page 2","Page 1"]);
            eq(Object.keys(chapters)[0],s.baseUrl+"/album/3.html");
            htmlReply({json.dumps(bad)}); await rejects(()=>s.loadChapters("/album.html"),"bound");
        """)

    def test_yellownote_page_quality_rewrite_order_missing_style_and_empty(self):
        def picture(url): return node(select={"div.img":[node(attrs={"style":"background-image: url('"+url+"')"})]})
        doc=node(select={"div.list.photo-items > div.item.photo-image, div.list.amateur-items > div.item.amateur-image":[picture("//img.test/2_600x0.webp"),node(),picture("https://img.test/1.jpg")]})
        self.runtime("yellownote",f"""
            htmlReply({json.dumps(doc)}); eq(await s.images("/album.html","/album/1.html"),["https://img.test/2.jpg","https://img.test/1.jpg"]);
            htmlReply({{}}); eq(await s.images("/album.html","/album/1.html"),[]); eq(disposed,2);
        """)

    def test_mangadex_locale_relationships_search_and_pagination(self):
        for locale in ("zh-Hans","zh-Hant"):
            self.runtime("mangadex",r"""
                const id="11111111-1111-1111-1111-111111111111";
                const m={id,attributes:{title:{en:"Fallback"},altTitles:[{zh:"简","zh-hk":"繁"}],description:{en:"Description"}},
                    relationships:[{type:"cover_art",attributes:{fileName:"cover.jpg"}}]};
                jsonReply({data:[m,m],offset:0,limit:20,total:21});
                const r=await s.explore[0].load(1); eq(r.comics.length,1); eq(r.hasMore,true);
                eq(r.comics[0].title,s.locale === "zh-Hant" ? "繁" : "简");
                ok(r.comics[0].cover.endsWith("/cover.jpg"));
                jsonReply({data:[],offset:20,limit:20,total:21}); eq(await s.search.load("x",{},2),{comics:[],hasMore:false,maxPage:2});
                ok(calls.every(c=>c.url.includes("availableTranslatedLanguage%5B%5D="+s.dexLocale())));
                ok(calls.every(c=>c.url.includes("contentRating%5B%5D=safe")&&c.url.includes("contentRating%5B%5D=suggestive")));
            """,locale)

    def test_mangadex_latest_relationship_join_order_and_empty(self):
        self.runtime("mangadex",r"""
            const a="11111111-1111-1111-1111-111111111111",b="22222222-2222-2222-2222-222222222222";
            jsonReply({data:[{relationships:[{type:"manga",id:b},{type:"manga",id:a},{type:"manga",id:b}]}],offset:0,limit:100,total:100});
            jsonReply({data:[{id:a,attributes:{title:{en:"A"}}},{id:b,attributes:{title:{en:"B"}}}]});
            const r=await s.explore[1].load(1); eq(r.comics.map(c=>c.title),["B","A"]); eq(r.hasMore,false);
            ok(calls[0].url.includes("translatedLanguage%5B%5D=zh"));
            ok(calls[0].url.includes("includeFuturePublishAt=0")); ok(calls[0].url.includes("excludedGroups"));
            jsonReply({data:[],offset:100,limit:100,total:100}); eq(await s.explore[1].load(2),{comics:[],hasMore:false,maxPage:1});
            eq(calls.length,3);
        """)

    def test_mangadex_details(self):
        self.runtime("mangadex",r"""
            const id="11111111-1111-1111-1111-111111111111";
            jsonReply({data:{id,attributes:{title:{en:"Title"},description:{zh:"Description"}},
                relationships:[{type:"author",attributes:{name:"Author"}}]}});
            const r=await s.info("/manga/"+id); eq(r.title,"Title"); eq(r.description,"Description"); eq(r.subtitle,"Author");
            ok(calls[0].url.includes("includes%5B%5D=author"));
        """)

    def test_mangadex_paginated_chapters_preserve_access_locale_and_order(self):
        for locale in ("zh-Hans","zh-Hant"):
            self.runtime("mangadex",r"""
                const id="11111111-1111-1111-1111-111111111111", a="22222222-2222-2222-2222-222222222222",b="33333333-3333-3333-3333-333333333333";
                const ca={id:a,attributes:{chapter:"2",title:"Two",pages:2,isUnavailable:false}};
                const cb={id:b,attributes:{chapter:"1",title:"One",pages:0,externalUrl:"https://external.test"}};
                jsonReply({data:[ca],offset:0,limit:500,total:501});
                jsonReply({data:[ca,cb],offset:500,limit:500,total:501});
                const r=await s.loadChapters("/manga/"+id); eq(Object.values(r),["Ch.2 - Two"]);
                ok(calls.every(c=>c.url.includes("translatedLanguage%5B%5D="+s.dexLocale())));
                ok(calls.every(c=>c.url.includes("includeUnavailable=0")&&c.url.includes("includeEmptyPages=0")&&c.url.includes("includeFuturePublishAt=0")));
                ok(calls[1].url.includes("offset=500"));
            """,locale)

    def test_mangadex_page_server_quality_order_expiry_refresh(self):
        self.runtime("mangadex",r"""
            const id="11111111-1111-1111-1111-111111111111",ep="/chapter/"+id;
            jsonReply({baseUrl:"https://cdn1.test",chapter:{hash:"h",data:["2.jpg","1.jpg"],dataSaver:["low.jpg"]}});
            const images=await s.images("/manga/"+id,ep);
            eq(images,["https://cdn1.test/data/h/2.jpg","https://cdn1.test/data/h/1.jpg"]);
            s.init(); eq((await s.comic.onImageLoad(images[0],"/manga/"+id,ep)).url,images[0]);
            eq(calls.length,1);
            s.pageServers.get(id).time-=300001;
            jsonReply({baseUrl:"https://cdn2.test",chapter:{hash:"h",data:["2.jpg","1.jpg"]}});
            eq((await s.comic.onImageLoad(images[1],"/manga/"+id,ep)).url,"https://cdn2.test/data/h/1.jpg");
            eq(calls.length,2);
        """)

    def test_mangadex_empty_errors_and_no_legacy_runtime_key(self):
        ir=families.make_ir(candidate("mangadex"),STAMP)
        self.assertNotEqual(ir["id"],"manga_dex")
        self.runtime("mangadex",r"""
            const id="11111111-1111-1111-1111-111111111111";
            jsonReply(null,204); eq(await s.loadChapters("/manga/"+id),{});
            jsonReply({baseUrl:"https://cdn.test",chapter:{hash:"h",data:[]}});
            eq(await s.images("/manga/"+id,"/chapter/"+id),[]);
            await rejects(()=>s.info("123"),"UUID");
            jsonReply({data:[],offset:0,limit:0,total:9}); await rejects(()=>s.explore[0].load(1),"pagination");
        """)

    def test_namicomi_response_discriminator_is_not_guessed(self):
        self.runtime("namicomi",r"""
            jsonReply({result:"a-source-defined-value",data:[],meta:{offset:0,limit:20,total:0}});
            eq(await s.explore[0].load(1),{comics:[],hasMore:false,maxPage:1});
        """)

    def test_old_pin_batch_does_not_promote_shared_family(self):
        from tools.source_conversion.planner.batch_reporting import add_batch_report
        c=copy.deepcopy(candidate("globalcomix"))
        c2=copy.deepcopy(candidate("globalcomix","zh-Hant"))
        registry={"schemaVersion":"1.0","artifacts":[{"artifactId":"unrelated","runtimeKey":"unrelated","providerId":"unrelated","implementation":{"producer":"manual"}}]}
        inventory={"schemaVersion":"1.0","upstreams":[{"project":c["project"],"commit":"f"*40}],
                   "candidates":[c,c2],"unresolvedModules":[]}
        plan=add_batch_report(build_plan(inventory,registry),inventory,registry)
        self.assertTrue(all(row["state"]=="UNRESOLVED_METADATA" and row["adapter"]=="generic-html" for row in plan["batch"]["candidates"]))

    def test_9g_matrix_closes_all_r2_candidates_without_unknown(self):
        r2 = json.loads((ROOT / "tools/source_conversion/audit/chinese_runtime_audit_9fr2.json").read_bytes())
        matrix = json.loads((ROOT / "tools/source_conversion/audit/chinese_candidate_matrix_9g.json").read_bytes())
        expected = {row["upstream"]["sourceId"] for row in r2["chineseCandidates"]}
        actual = {row["sourceId"] for row in matrix["candidates"]}
        self.assertEqual(matrix["summary"]["total"], 93)
        self.assertEqual(actual, expected)
        self.assertEqual(matrix["summary"]["unexplainedUnknown"], 0)
        self.assertFalse(any(row["classification"] == "UNKNOWN" for row in matrix["candidates"]))
        by_id = {row["sourceId"]: row for row in matrix["candidates"]}
        self.assertEqual(by_id["3279300917142951720"]["classification"], "PUBLISHED_PASS")
        self.assertEqual(by_id["116946528518438525"]["classification"], "CONVERTED_LIVE_BLOCKED")
        self.assertEqual(by_id["5183325399429659419"]["classification"], "CONVERTED_LIVE_BLOCKED")



if __name__ == "__main__":
    unittest.main()
