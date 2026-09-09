"""MangaDex page-number navigation and independent artifact ownership."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.source_conversion.tests import test_chinese_families as family
from tools.source_conversion.materializer import materialize as mat

ROOT = Path(__file__).resolve().parents[3]


class MangaDexRegressionTests(unittest.TestCase):
    runtime = family.FamilyContractTests.runtime

    def test_exact_totals_first_middle_final_and_no_empty_successor(self):
        for locale in ('zh-Hant', 'zh-Hans'):
            for kind, size in [('popular', 20), ('search', 20), ('latest', 100)]:
                for total in (0, 1, size-1, size, size+1, 2*size, 3*size+4):
                    with self.subTest(locale=locale, kind=kind, total=total):
                        self.runtime('mangadex', r'''
                            const total=TOTAL,size=SIZE,kind=KIND,last=Math.max(1,Math.ceil(total/size));
                            const id=i=>'00000000-0000-0000-0000-'+String(i+1).padStart(12,'0');
                            const rows=Array.from({length:total},(_,i)=>({id:id(i),attributes:{title:{en:'Title '+i}}}));
                            const results=[];
                            for(let repeat=0;repeat<2;repeat++) {
                                let page=1,maxPage=1;const seen=[];
                                do {
                                    const offset=(page-1)*size,data=rows.slice(offset,offset+size);
                                    if(kind==='latest') {
                                        jsonReply({data:data.map(m=>({relationships:[{type:'manga',id:m.id}]})),limit:size,offset,total});
                                        if(data.length) jsonReply({data});
                                    } else jsonReply({data,limit:size,offset,total});
                                    const result=kind==='search' ? await s.search.load('title',{},page) : await s.explore[kind==='latest'?1:0].load(page);
                                    maxPage=result.maxPage;
                                    eq(maxPage,last);eq(result.hasMore,page<last);
                                    eq(result.comics.length,data.length);
                                    ok(total===0 || result.comics.length>0);
                                    seen.push(...result.comics.map(m=>m.id));
                                    if(repeat===0) results.push(result);else eq(result,results[page-1]);
                                    page++;
                                }while(page<=maxPage);
                                eq(page,last+1);eq(seen.length,total);eq(new Set(seen).size,total);
                            }
                            eq(calls.length,2*last*(kind==='latest' && total ? 2:1));
                        '''.replace('TOTAL',str(total)).replace('SIZE',str(size)).replace('KIND',json.dumps(kind)),locale)

    def test_locales_have_independent_authoritative_terminal_pages(self):
        for locale,total in [('zh-Hant',704),('zh-Hans',638)]:
            self.runtime('mangadex',r'''
                const total=TOTAL,last=Math.ceil(total/20),offset=(last-1)*20;
                const data=Array.from({length:total-offset},(_,i)=>({id:'00000000-0000-0000-0000-'+String(i+1).padStart(12,'0'),attributes:{title:{en:'Title'}}}));
                jsonReply({data,limit:20,offset,total});
                const result=await s.explore[0].load(last);
                eq(result.maxPage,last);eq(result.hasMore,false);eq(result.comics.length,total-offset);
                ok(calls[0].url.includes('availableTranslatedLanguage%5B%5D='+s.dexLocale()));
            '''.replace('TOTAL',str(total)),locale)

    def test_empty_response_terminates_without_a_successor(self):
        for locale in ('zh-Hant','zh-Hans'):
            self.runtime('mangadex',r'''
                for(const tab of [0,1]) for(const page of [1,4]) {
                    jsonReply(null,204);
                    eq(await s.explore[tab].load(page),{comics:[],hasMore:false,maxPage:Math.max(1,page-1)});
                }
            ''',locale)

    def test_unexpected_page_size_cannot_skip_results(self):
        self.runtime('mangadex',r'''
            for(const tab of [0,1]) {
                jsonReply({data:[],offset:0,limit:10,total:100});
                await rejects(()=>s.explore[tab].load(1),'page size');
            }
        ''')

    def test_invalid_authoritative_pagination_fails_closed(self):
        self.runtime('mangadex',r'''
            for(const total of [-1,1.5,9007199254740992]) {
                jsonReply({data:[],offset:0,limit:20,total});
                await rejects(()=>s.explore[0].load(1),'pagination');
            }
            jsonReply({data:[],offset:1,limit:20,total:21});
            await rejects(()=>s.explore[0].load(1),'pagination');
        ''')

    def test_create_preserves_legacy_rows_files_and_source_identity(self):
        registry=json.loads((ROOT/'sources_registry.json').read_bytes())
        legacy=next(a for a in registry['artifacts'] if a['artifactId']=='manga_dex')
        legacy_js=(ROOT/'manga_dex.js').read_bytes()
        old_index=next(a for a in json.loads((ROOT/'index.json').read_bytes()) if a['fileName']=='manga_dex.js')
        candidates=[family.candidate('mangadex',locale) for locale in ('zh-Hant','zh-Hans')]
        plan={'schemaVersion':'1','upstream':{'project':'keiyoushi/extensions-source','commit':family.families.PIN},
              'generatedTimestamp':family.STAMP,'artifacts':[
                  {'sourceId':c['sourceId'],'artifactId':'mangadex_'+c['upstreamLang'].lower().replace('-','_'),
                   'providerId':'mangadex','localVersion':'1.0.0'} for c in candidates]}
        def extract(item,candidate,timestamp,root):
            return {**family.families.make_ir(candidate,timestamp),'artifactId':item['artifactId'],'version':item['localVersion']}
        with tempfile.TemporaryDirectory() as directory:
            repo=Path(directory)/'repo';repo.mkdir()
            prepared=Path(directory)/'prepared';prepared.mkdir()
            baseline={'schemaVersion':'1.0','artifacts':[legacy]}
            (repo/'sources_registry.json').write_text(json.dumps(baseline),encoding='utf-8')
            (repo/'manga_dex.js').write_bytes(legacy_js)
            with patch.object(mat,'_extract_to_temp',side_effect=extract):
                result=mat._execute_pass(plan,{c['sourceId']:c for c in candidates},Path(directory),repo,prepared)
            rows=result['proposed_registry']['artifacts']
            self.assertEqual(rows[0],legacy)
            self.assertEqual(result['proposed_index'][0],old_index)
            self.assertEqual((repo/'manga_dex.js').read_bytes(),legacy_js)
            self.assertEqual((prepared/'manga_dex.js').read_bytes(),legacy_js)
            self.assertEqual(json.loads((repo/'sources_registry.json').read_bytes()),baseline)
            self.assertEqual(len({a['runtimeKey'] for a in rows}),3)
            self.assertEqual(len({a['fileName'] for a in result['proposed_index']}),3)
            self.assertNotIn('manga_dex.js',{a['relativePath'] for a in result['targets']})
            for candidate,row in zip(candidates,rows[1:]):
                self.assertEqual(row['runtimeKey'],'keiyoushi_'+candidate['sourceId'])
                self.assertEqual(row['upstream']['sourceId'],candidate['sourceId'])
                self.assertEqual(row['locales'],[candidate['upstreamLang']])
                artifact=row['artifactId']
                ir=json.loads((prepared/'sources_ir'/f'{artifact}.json').read_bytes())
                self.assertEqual(ir['id'],row['runtimeKey'])
                self.assertEqual(ir['provenance']['upstreamCommit'],family.families.PIN)
                self.assertEqual(ir['version'],'1.0.0')

    def test_existing_other_family_output_is_unchanged(self):
        for path in sorted((ROOT/'sources_ir').glob('*.json')):
            ir=json.loads(path.read_bytes())
            if ir.get('familyContract') and ir['familyContract']!='mangadex-v1':
                with self.subTest(artifact=path.stem):
                    self.assertEqual(mat._generate_base_js(ir),(ROOT/'sources_generated'/f'{path.stem}.base.js').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
