"""Complete chronological lists, access boundaries, and stable installation IDs."""
import json
from pathlib import Path
import unittest

import quickjs

from tools.source_conversion.tests import test_chinese_families as family

ROOT = Path(__file__).resolve().parents[3]


class ChineseChapterContractTests(unittest.TestCase):
    runtime = family.FamilyContractTests.runtime

    def test_mangadex_three_full_pages_both_locales_decimal_special_volume_and_dedup(self):
        for locale in ('zh-Hant', 'zh-Hans'):
            self.runtime('mangadex', r'''
                const id=i=>'00000000-0000-0000-0000-'+String(i+1).padStart(12,'0');
                const chronological=Array.from({length:1003},(_,i)=>({id:id(i),attributes:{
                    volume:i<500?'1':'2',chapter:i===0?null:i===100?'99.5':String(i),
                    title:i===0?'Prologue':'',translatedLanguage:s.dexLocale(),pages:3}}));
                chronological[1001].attributes.isUnavailable=true;
                chronological[1002].attributes.externalUrl='https://external.test';
                chronological[1002].attributes.pages=0;
                const rows=chronological.slice().reverse(); rows.splice(500,0,rows[499]);
                const expected=Array.from({length:1001},(_,i)=>'/chapter/'+id(i));
                let previous;
                for(let repeat=0;repeat<2;repeat++) {
                    for(let offset=0;offset<rows.length;offset+=500)
                        jsonReply({data:rows.slice(offset,offset+500),offset,limit:500,total:rows.length});
                    const result=await s.loadChapters('/manga/'+id(0));
                    eq(Object.keys(result),expected);
                    eq(result[expected[0]],'Vol.1 - Prologue');
                    eq(result[expected[100]],'Vol.1 Ch.99.5');
                    eq(result[expected[500]],'Vol.2 Ch.500');
                    if(previous) eq(result,previous); previous=result;
                }
                eq(calls.length,6);
                for(let i=0;i<6;i++) {
                    ok(calls[i].url.includes('offset='+(i%3)*500));
                    ok(calls[i].url.includes('translatedLanguage%5B%5D='+s.dexLocale()));
                }
            ''', locale)

    def test_namicomi_three_full_pages_and_three_access_batches(self):
        for locale in ('zh-Hant', 'zh-Hans'):
            self.runtime('namicomi', r'''
                const chronological=Array.from({length:403},(_,i)=>({id:'c'+i,attributes:{
                    volume:'1',chapter:i===0?null:i===100?'99.5':String(i),name:i===0?'Special':'',
                    translatedLanguage:s.externalLocale()}}));
                const rows=chronological.slice().reverse();rows.splice(200,0,rows[199]);
                for(let offset=0;offset<rows.length;offset+=200)
                    jsonReply({data:rows.slice(offset,offset+200),meta:{offset,limit:200,total:rows.length}});
                const upstreamIds=chronological.slice().reverse().map(c=>c.id);
                for(let offset=0;offset<upstreamIds.length;offset+=200)
                    jsonReply({data:{attributes:{map:Object.fromEntries(upstreamIds.slice(offset,offset+200).map(id=>[id,id!=='c200']))}}});
                const result=await s.loadChapters('title');
                eq(Object.keys(result),Array.from({length:403},(_,i)=>'c'+i).filter(id=>id!=='c200'));
                eq(result.c0,'Vol.1 - Special');eq(result.c100,'Vol.1 Ch.99.5');
                eq(calls.length,6);eq(calls.slice(3).map(c=>c.data.entities.length),[200,200,3]);
                for(let i=0;i<3;i++) {
                    ok(calls[i].url.includes('offset='+i*200));
                    ok(calls[i].url.includes('translatedLanguages%5B%5D='+s.externalLocale()));
                }
            ''', locale)

    def test_same_title_locale_counts_are_independent_of_global_total(self):
        for name, locales in [('mangadex',[('zh-Hant',6),('zh-Hans',2)]),('namicomi',[('zh-Hant',3),('zh-Hans',1)])]:
            for locale, count in locales:
                self.runtime(name, r'''
                    const count=COUNT, size=SIZE;
                    const id=i=>'00000000-0000-0000-0000-'+String(i+1).padStart(12,'0');
                    const data=Array.from({length:count},(_,i)=>({id:id(i),attributes:{chapter:String(count-i),pages:2}}));
                    jsonReply(FAMILY==='namicomi'?{data,meta:{limit:size,offset:0,total:count}}:{data,limit:size,offset:0,total:count});
                    if(FAMILY==='namicomi')jsonReply({data:{attributes:{map:Object.fromEntries(data.map(c=>[c.id,true]))}}});
                    eq(Object.keys(await s.loadChapters(id(0))).length,count);
                    eq(calls.length,FAMILY==='namicomi'?2:1);
                '''.replace('COUNT',str(count)).replace('SIZE','200' if name=='namicomi' else '500').replace('FAMILY',json.dumps(name)),locale)

    def test_missing_or_repeated_later_page_never_returns_partial_success(self):
        for name,size in [('mangadex',500),('namicomi',200)]:
            for terminal in ['204','empty','repeated']:
                self.runtime(name,r'''
                    const id='00000000-0000-0000-0000-000000000001',size=SIZE;
                    const data=[{id,attributes:{chapter:'1',pages:1}}];
                    const page=(data,offset)=>FAMILY==='namicomi'?{data,meta:{limit:size,offset,total:size+1}}:{data,limit:size,offset,total:size+1};
                    jsonReply(page(data,0));
                    if(TERMINAL==='204')jsonReply(null,204);
                    else jsonReply(page(TERMINAL==='empty'?[]:data,size));
                    await rejects(()=>s.loadChapters(id),TERMINAL==='204'?'Incomplete':'Non-progressing');
                    eq(calls.length,2);
                '''.replace('SIZE',str(size)).replace('FAMILY',json.dumps(name)).replace('TERMINAL',json.dumps(terminal)))

    def test_page_errors_and_wrong_offset_fail_without_partial_result(self):
        for name,size in [('mangadex',500),('namicomi',200)]:
            self.runtime(name,r'''
                const id='00000000-0000-0000-0000-000000000001',size=SIZE;
                for(const status of [429,500]){
                    const data=[{id,attributes:{chapter:'1'}}];
                    jsonReply(FAMILY==='namicomi'?{data,meta:{limit:size,offset:0,total:size+1}}:{data,limit:size,offset:0,total:size+1});
                    jsonReply({},status);await rejects(()=>s.loadChapters(id),'HTTP '+status);
                }
                jsonReply(FAMILY==='namicomi'?{data:[],meta:{limit:size,offset:1,total:1}}:{data:[],limit:size,offset:1,total:1});
                await rejects(()=>s.loadChapters(id),'pagination');
            '''.replace('SIZE',str(size)).replace('FAMILY',json.dumps(name)))

    def test_globalcomix_complete_all_releases_keeps_ascending_order_and_access(self):
        self.runtime('globalcomix',r'''
            // all=true's response already carries chronological release order.
            const rows=Array.from({length:501},(_,i)=>({key:'c'+i,chapter:String(i),premium_only:i===250?1:0}));
            rows.splice(250,0,rows[249]);
            jsonReply({payload:{results:rows,pagination:{page:1,per_page:9999,total_pages:1,total_results:rows.length}}});
            const result=await s.loadChapters('12/title');
            eq(Object.keys(result),Array.from({length:501},(_,i)=>'c'+i).filter(id=>id!=='c250'));
            eq(calls.length,1);ok(calls[0].url.includes('all=true'));ok(calls[0].url.includes('lang_id=cn'));
            jsonReply({payload:{results:rows,pagination:{page:1,total_pages:2}}});
            await rejects(()=>s.loadChapters('12/title'),'Incomplete all-releases');
        ''')

    def test_shipped_identity_names_and_no_patch_survive_regeneration(self):
        registry=json.loads((ROOT/'sources_registry.json').read_bytes())['artifacts']
        catalog=json.loads((ROOT/'index.json').read_bytes())
        runtime_keys=set()
        for name,sid in [('manga_dex',None),('mangadex_zh_hant','1493666528525752601'),
                         ('mangadex_zh_hans','5148895169070562838'),('namicomi_zh_hant','7859611418350123856'),
                         ('namicomi_zh_hans','1163192659786040070')]:
            row=next(r for r in registry if r['artifactId']==name)
            entry=next(r for r in catalog if r['fileName']==name+'.js')
            key='keiyoushi_'+sid if sid else 'manga_dex'
            self.assertEqual(row['runtimeKey'],key)
            self.assertEqual(entry['key'],key)
            self.assertNotIn(key,runtime_keys);runtime_keys.add(key)
            if sid:
                ir=json.loads((ROOT/'sources_ir'/f'{name}.json').read_bytes())
                self.assertEqual(ir['id'],key)
                self.assertEqual(row['upstream']['sourceId'],sid)
                self.assertEqual(ir['provenance']['upstreamSourceId'],sid)
                self.assertEqual(ir['provenance']['upstreamCommit'],family.families.PIN)
                label=('MangaDex' if name.startswith('mangadex') else 'NamiComi')+('（繁體中文）' if name.endswith('hant') else '（简体中文）')
                self.assertEqual(ir['name'],label);self.assertEqual(entry['name'],label)
                self.assertEqual((ROOT/f'{name}.js').read_bytes(),(ROOT/'sources_generated'/f'{name}.base.js').read_bytes())
                self.assertFalse((ROOT/'sources_patches'/f'{name}.patch.js').exists())
            else:
                self.assertEqual(row['implementation']['producer'],'manual')
                self.assertNotIn('upstream',row)


class LegacyMangaDexChapterTests(unittest.TestCase):
    def runtime(self, code):
        ctx=quickjs.Context()
        ctx.eval(family.HARNESS+(ROOT/'manga_dex.js').read_text(encoding='utf-8')+r'''
            const s=new MangaDex();
            const fetch=async url=>{const r=respond('GET',url);return {ok:r.status===200,json:async()=>JSON.parse(r.body)};};
            let complete=false,failure=null;
            (async()=>{
        '''+code+r'''
            eq(replies.length,0);})().then(()=>{complete=true;}).catch(e=>{failure=String(e)+'\n'+e.stack;});
        ''')
        jobs=0
        while ctx.execute_pending_job():
            jobs+=1;self.assertLess(jobs,10000)
        self.assertIsNone(ctx.eval('failure'));self.assertTrue(ctx.eval('complete'))

    def test_over_500_chapters_keep_legacy_english_grouped_ids(self):
        self.runtime(r'''
            const rows=Array.from({length:1201},(_,i)=>({id:'c'+i,attributes:{volume:i<600?'1':'2',chapter:String(i)}}));
            rows.splice(500,0,rows[499]);
            for(let offset=0;offset<rows.length;offset+=500)
                jsonReply({data:rows.slice(offset,offset+500),offset,limit:500,total:rows.length});
            const result=await s.comic.getChapters('manga');
            eq([...result.keys()],['Volume 1','Volume 2']);
            eq([...result.values()].flatMap(g=>[...g.keys()]),Array.from({length:1201},(_,i)=>'c'+i));
            eq(calls.length,3);eq(s.key,'manga_dex');
            for(let i=0;i<3;i++){ok(calls[i].url.includes('offset='+i*500));ok(calls[i].url.includes('translatedLanguage[]=en'));}
        ''')

    def test_empty_single_page_decimal_special_and_no_extra_request(self):
        self.runtime(r'''
            jsonReply({data:[],limit:500,offset:0,total:0});eq([...await s.comic.getChapters('manga')],[]);
            jsonReply({data:[{id:'a',attributes:{chapter:'99.5',volume:'1'}},{id:'b',attributes:{chapter:null,title:'Special'}}],limit:500,offset:0,total:2});
            const result=await s.comic.getChapters('manga');
            eq([...result.get('Volume 1')],[['a','99.5']]);
            eq([...result.get('No Volume')],[['b','Oneshot: Special']]);eq(calls.length,2);
        ''')

    def test_legacy_bad_page_or_repeated_page_is_not_partial_success(self):
        self.runtime(r'''
            const data=[{id:'a',attributes:{chapter:'1'}}];
            jsonReply({data,limit:500,offset:0,total:501});jsonReply({data,limit:500,offset:500,total:501});
            await rejects(()=>s.comic.getChapters('m'),'Non-progressing');
            jsonReply({data,limit:500,offset:0,total:501});jsonReply({},500);
            await rejects(()=>s.comic.getChapters('m'),'Network');
            jsonReply({data,limit:0,offset:0,total:1});await rejects(()=>s.comic.getChapters('m'),'pagination');
        ''')


if __name__=='__main__':
    unittest.main()
