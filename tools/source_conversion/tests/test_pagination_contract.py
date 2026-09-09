"""Execute generated sources against the page-number contract used by VeneraX."""
import json
from pathlib import Path
import unittest

from tools.source_conversion.tests import test_chinese_families as family_tests
from tools.source_conversion.tests.test_chinese_families import node
from tools.source_conversion.tests import test_dongman_regression as dongman_tests
from tools.source_conversion.tests.test_dongman_regression import chapters, row

FIXTURE = Path(__file__).with_name('fixtures') / 'dongman_chapters_three_pages.json'


class ExplorePaginationTests(unittest.TestCase):
    runtime = family_tests.FamilyContractTests.runtime

    def test_globalcomix_exact_totals_and_host_navigation(self):
        # Zero, single, exact-size, partial-final and multiple full pages.
        for total in (0, 1, 23, 24, 25, 48, 49, 73):
            for tab in (0, 1):
                with self.subTest(total=total, tab=tab):
                    self.runtime('globalcomix', r'''
                        const total=TOTAL, size=24, tab=TAB;
                        const count=Math.max(1, Math.ceil(total/size));
                        const all=Array.from({length:total},(_,i)=>({id:i+1,name:'Title '+i,slug:'title-'+i}));
                        const outputs=[];
                        for (let repeat=0;repeat<2;repeat++) {
                            let page=1, last=1; const seen=[];
                            do {
                                jsonReply({payload:{results:all.slice((page-1)*size,page*size),
                                    pagination:{page,per_page:size,total_results:total,total_pages:total ? count : 0}}});
                                const result=await s.explore[tab].load(page);
                                // parser.dart supplies only maxPage to the page-number UI.
                                last=result.maxPage;
                                eq(last,count); eq(result.hasMore,page<count);
                                ok(total===0 || result.comics.length>0);
                                seen.push(...result.comics.map(x=>x.id));
                                if(repeat===0) outputs.push(result); else eq(result,outputs[page-1]);
                                page++;
                            } while(page<=last);
                            eq(page,count+1); eq(seen.length,total); eq(new Set(seen).size,total);
                        }
                        eq(calls.length,2*count);
                    '''.replace('TOTAL', str(total)).replace('TAB', str(tab)))

    def test_namicomi_independent_locale_totals_and_host_navigation(self):
        for locale, totals in [('zh-Hans',(0,1,3,19,20,21,40,41,63)), ('zh-Hant',(0,1,20,23,40,41,63))]:
            for total in totals:
                for tab in (0, 1):
                    with self.subTest(locale=locale,total=total,tab=tab):
                        self.runtime('namicomi', r'''
                            const total=TOTAL,size=20,tab=TAB,count=Math.max(1,Math.ceil(total/size));
                            const all=Array.from({length:total},(_,i)=>({id:'m'+i,attributes:{title:{en:'Title '+i}},relationships:[]}));
                            const outputs=[];
                            for(let repeat=0;repeat<2;repeat++) {
                                let page=1,last=1; const seen=[];
                                do {
                                    const offset=(page-1)*size;
                                    jsonReply({data:all.slice(offset,offset+size),meta:{limit:size,offset,total}});
                                    const result=await s.explore[tab].load(page);
                                    last=result.maxPage;
                                    eq(last,count);eq(result.hasMore,page<count);
                                    ok(total===0 || result.comics.length>0);
                                    seen.push(...result.comics.map(x=>x.id));
                                    if(repeat===0) outputs.push(result);else eq(result,outputs[page-1]);
                                    page++;
                                }while(page<=last);
                                eq(page,count+1);eq(seen.length,total);eq(new Set(seen).size,total);
                            }
                            eq(calls.length,2*count);
                            ok(calls.every(c=>c.url.includes('availableTranslatedLanguages%5B%5D='+s.externalLocale())));
                        '''.replace('TOTAL',str(total)).replace('TAB',str(tab)),locale)

    def test_namicomi_unexpected_limit_cannot_silently_skip_results(self):
        self.runtime('namicomi', r'''
            jsonReply({data:[],meta:{limit:10,offset:0,total:23}});
            await rejects(()=>s.explore[0].load(1),'page size');
        ''')

    def test_globalcomix_invalid_total_fails_closed(self):
        self.runtime('globalcomix', r'''
            for(const total of [-1,1.5,9007199254740992]) {
                jsonReply({payload:{results:[],pagination:{page:1,total_pages:total}}});
                await rejects(()=>s.explore[0].load(1),'pagination');
            }
        ''')

    def test_dongman_calendars_are_complete_single_pages(self):
        selectors=['div#dailyList .daily_section li a, div.daily_lst.comp li a'] + [
            'div#dailyList > div._list_'+day+' li > a' for day in
            ('SUNDAY','MONDAY','TUESDAY','WEDNESDAY','THURSDAY','FRIDAY','SATURDAY')]
        for count in (0,1,10,20,21,40,41):
            items=[node(attrs={'href':'/title/'+str(i)},select={'p.subj':[node('Title '+str(i))]}) for i in range(count)]
            doc=node(select={selector:items for selector in selectors})
            for tab in (0,1):
                with self.subTest(count=count,tab=tab):
                    self.runtime('dongmanmanhua', f'''
                        const results=[];
                        for(let repeat=0;repeat<2;repeat++) {{
                            htmlReply({json.dumps(doc)});
                            const result=await s.explore[{tab}].load(1);
                            eq(result.comics.length,{count});eq(result.maxPage,1);eq(result.hasMore,false);
                            results.push(result);
                        }}
                        eq(results[0],results[1]);eq(calls.length,2);
                        // The UI disables next; an out-of-contract request is also bounded.
                        eq(await s.explore[{tab}].load(2),{{comics:[],hasMore:false,maxPage:1}});
                        eq(calls.length,2);
                    ''')


class DongmanFullTraversalTests(unittest.TestCase):
    runtime = dongman_tests.DongmanRuntimeTests.runtime

    def test_three_pages_every_accessible_chapter_once_in_upstream_order(self):
        fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))
        replies='\n'.join('htmlReply('+json.dumps(page['dom'])+');' for page in fixture['pages'])
        expected=json.dumps(fixture['expectedIds'])
        paths=json.dumps([page['path'] for page in fixture['pages']])
        self.runtime(f'''
            const results=[];
            for(let repeat=0;repeat<2;repeat++) {{
                {replies}
                results.push(await s.loadChapters('/series/list?title_no=42'));
            }}
            eq(results[0],results[1]);
            eq(Object.keys(results[0]),{expected}.map(id=>s.baseUrl+'/reader/'+id));
            eq(Object.values(results[0]),{expected}.map(id=>'Chapter '+id));
            eq(Object.keys(results[0]).length,28);
            eq(calls.slice(0,3).map(c=>c.url),{paths}.map(path=>s.baseUrl+path));
            eq(calls.length,6);eq(disposed,6);
        ''')

    def test_repeated_rows_with_distinct_next_urls_stop_without_partial_result(self):
        first=chapters([row('One','/reader/1')],'?title_no=42&page=2')
        repeated=chapters([row('One','/reader/1')],'?title_no=42&page=3')
        self.runtime(f'''
            htmlReply({json.dumps(first)});htmlReply({json.dumps(repeated)});
            await rejects(()=>s.loadChapters('/series/list?title_no=42'),'Non-progressing');
            eq(calls.length,2);eq(disposed,2);
        ''')


if __name__ == '__main__':
    unittest.main()
