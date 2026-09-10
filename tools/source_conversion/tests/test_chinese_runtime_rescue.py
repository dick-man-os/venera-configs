"""Behavioral R2 regressions for the shipped Chinese patches (no network)."""
import json
from pathlib import Path
import unittest
import quickjs

from tools.source_conversion.generator.js_generator import generate_venera_js
from tools.source_conversion.patcher.js_patcher import patch_js
from tools.source_conversion.tests.test_chinese_families import HARNESS, node

ROOT=Path(__file__).resolve().parents[3]

class ChineseRuntimeRescueTests(unittest.TestCase):
    def run_source(self, artifact, code):
        source=(ROOT/(artifact+'.js')).read_text(encoding='utf-8')
        import re
        classname=re.search(r'class\s+(\w+)\s+extends ComicSource',source)[1]
        ctx=quickjs.Context()
        ctx.eval(HARNESS+source+'\nconst s=new '+classname+'''();
            let complete=false,failure=null;
            (async()=>{
        '''+code+'''\n eq(replies.length,0);
            })().then(()=>complete=true).catch(e=>failure=String(e)+"\\n"+e.stack);
        ''')
        for _ in range(10000):
            if not ctx.execute_pending_job(): break
        else: self.fail('Unbounded pending jobs')
        self.assertIsNone(ctx.eval('failure'))
        self.assertTrue(ctx.eval('complete'))

    def webtoons(self, code): self.run_source('webtoons_zh_hant',code)

    def test_webtoons_complete_cursor_pages_dedup_before_numbering_and_navigation(self):
        self.webtoons(r'''
            const ep=i=>({episodeTitle:'第'+i+'話',viewerLink:'/viewer?title_no=1&episode_no='+i});
            jsonReply({result:{episodeList:Array.from({length:200},(_,i)=>ep(i+1)),nextCursor:200}});
            jsonReply({result:{episodeList:[ep(200),...Array.from({length:200},(_,i)=>ep(i+201))],nextCursor:400}});
            jsonReply({result:{episodeList:Array.from({length:203},(_,i)=>ep(i+401)),nextCursor:0}});
            const chapters=await s.loadChapters('/list?title_no=1');
            eq(chapters.size,603);eq(calls.length,3);
            ok(calls[0].url.endsWith('episodes?pageSize=200'));
            ok(calls[1].url.endsWith('&cursor=200'));ok(calls[2].url.endsWith('&cursor=400'));
            const ids=[...chapters.keys()];eq(ids[0],ep(1).viewerLink);eq(ids[602],ep(603).viewerLink);
            eq(chapters.get(ep(201).viewerLink),'第201話 (ch. 201)');
            const neighbor=(i,d)=>ids[i+d]??null;
            eq(neighbor(0,-1),null);eq(neighbor(602,1),null);
            eq(neighbor(300,1),ep(302).viewerLink);eq(neighbor(300,-1),ep(300).viewerLink);
            // Reversing displayed slots retains the original reader indices.
            const display=ids.map((id,index)=>({id,index})).reverse();
            eq(neighbor(display[0].index,1),null);eq(neighbor(display[602].index,-1),null);
        ''')

    def test_webtoons_canvas_locale_cursor_and_special_identity(self):
        self.webtoons(r'''
            const rows=[{episodeTitle:'Season 1 Ep. 1',viewerLink:'/one'},
                {episodeTitle:'Bonus',viewerLink:'/bonus',hasBgm:true},
                {episodeTitle:'Season 2 Ep. 1',viewerLink:'/two'}];
            jsonReply({result:{episodeList:rows,nextCursor:0}});
            const result=await s.loadChapters('/zh-hant/canvas/name/list?title_no=3');
            eq([...result.keys()],['/one','/bonus','/two']);
            ok(result.get('/bonus').includes('♫'));
            ok(calls[0].url.includes('/canvas/3/episodes?pageSize=200&readingLanguageCode=zh-hant'));
        ''')

    def test_webtoons_repeated_cursor_rejected(self):
        self.webtoons(r'''
            jsonReply({result:{episodeList:[{viewerLink:'/1'}],nextCursor:1}});
            jsonReply({result:{episodeList:[{viewerLink:'/2'}],nextCursor:1}});
            await rejects(()=>s.loadChapters('/list?title_no=1'),'Non-progressing Webtoons cursor');
        ''')

    def test_webtoons_repeated_page_rejected_even_if_cursor_moves(self):
        self.webtoons(r'''
            jsonReply({result:{episodeList:[{viewerLink:'/1'}],nextCursor:1}});
            jsonReply({result:{episodeList:[{viewerLink:'/1'}],nextCursor:2}});
            await rejects(()=>s.loadChapters('/list?title_no=1'),'Non-progressing Webtoons chapter page');
        ''')

    def test_webtoons_missing_later_page_never_returns_partial_success(self):
        for status in (204,403,500):
            with self.subTest(status=status):
                self.webtoons('''
                    jsonReply({result:{episodeList:[{viewerLink:'/1'}],nextCursor:1}});
                    jsonReply({},STATUS);
                    await rejects(()=>s.loadChapters('/list?title_no=1'),'status: STATUS');
                '''.replace('STATUS',str(status)))

    def test_webtoons_invalid_payload_or_missing_cursor_rejected(self):
        for payload in ({}, {'success':False,'result':{'episodeList':[],'nextCursor':0}},
                        {'result':{'episodeList':[]}}, {'result':{'episodeList':[],'nextCursor':-1}},
                        {'result':{'episodeList':[],'nextCursor':'2'}},
                        {'result':{'episodeList':[{}],'nextCursor':0}}):
            self.webtoons('jsonReply('+json.dumps(payload)+');await rejects(()=>s.loadChapters("/list?title_no=1"),"Webtoons");')

    def test_webtoons_empty_first_terminal_and_empty_later_page(self):
        self.webtoons(r'''
            jsonReply({result:{episodeList:[],nextCursor:0}});eq((await s.loadChapters('/list?title_no=1')).size,0);
            jsonReply({result:{episodeList:[{viewerLink:'/1'}],nextCursor:1}});
            jsonReply({result:{episodeList:[],nextCursor:0}});
            await rejects(()=>s.loadChapters('/list?title_no=1'),'Non-progressing');
        ''')

    def test_webtoons_missing_title_id_never_requests(self):
        self.webtoons("await rejects(()=>s.loadChapters('/bad'),'title_no');eq(calls.length,0);")

    def test_webtoons_search_combines_real_result_types_and_terminal_counts(self):
        card=lambda ident: node(attrs={'href':ident},select={'.title':[node('Title')],'img':[node(attrs={'src':'https://img.test/1.jpg'})]})
        first=node(select={'.series_count .number':[node('136')],'.webtoon_list li a':[card('/1'),card('/1')]})
        second=node(select={'.series_count .number':[node('278')],'.webtoon_list li a':[card('/2')]})
        self.webtoons(f'''
            htmlReply({json.dumps(first)});htmlReply({json.dumps(second)});
            const first=await s.search.load('愛 & Love',[],1);
            eq(first.comics.map(c=>c.id),['/1','/2']);eq(first.maxPage,10);
            ok(calls[0].url.includes('/search/originals?keyword='+encodeURIComponent('愛 & Love')));
            ok(calls[1].url.includes('/search/canvas?keyword='+encodeURIComponent('愛 & Love')));
            htmlReply({json.dumps(first)});htmlReply({json.dumps(second)});
            const last=await s.search.load('愛 & Love',[],10);
            eq(last.comics.map(c=>c.id),['/2']);eq(last.maxPage,10);eq(disposed,4);
        ''')

    def test_webtoons_search_locale_queries_and_empty_results(self):
        for query in ('愛','爱','Love','Romanized & Title'):
            self.webtoons(f'''
                htmlReply({{}});htmlReply({{}});
                eq(await s.search.load({json.dumps(query)},[],1),{{comics:[],maxPage:1}});
                ok(calls.every(c=>c.url.includes('/zh-hant/search/')));eq(disposed,2);
            ''')

    def test_webtoons_search_fails_closed_without_advertised_count(self):
        bad=node(select={'.webtoon_list li a':[node(attrs={'href':'/1'})]})
        self.webtoons(f'''htmlReply({json.dumps(bad)});
            await rejects(()=>s.search.load('x',[],1),'Missing Webtoons search count');eq(disposed,1);
            await rejects(()=>s.search.load('x',[],0),'Invalid search page');''')

    def test_webtoons_reader_page_order_headers_and_denial(self):
        doc=node(select={'div#_imageList > img':[node(attrs={'data-url':f'https://img.test/{i}.jpg'}) for i in (1,2,3)]})
        self.webtoons(f'''
            htmlReply({json.dumps(doc)});
            const result=await s.comic.loadEp('/list?title_no=1','/viewer?title_no=1&episode_no=1');
            eq(result.images,['https://img.test/1.jpg','https://img.test/2.jpg','https://img.test/3.jpg']);
            const config=await s.comic.onImageLoad(result.images[0]);ok(config.headers.Referer.includes('webtoons.com'));
            htmlReply({{}},403);await rejects(()=>s.comic.loadEp('/list','/viewer'),'403');
        ''')

    def test_comicabc_dom_order_dedup_and_special_chapter_ids(self):
        rows=[node('One',{'onclick':"cview('42-1.html',14,0);return false;"}),
              node('Special',{'onclick':"cview('42-1.html',14,0);return false;",'ch':'1.5'}),
              node('Three',{'onclick':"cview('42-3.html',14,0);return false;"})]
        doc=node(select={'#chapters a, .comic_chapters a':rows+[rows[0]]})
        self.run_source('comicabc',f'''
            htmlReply({json.dumps(doc)});
            const c=await s.loadChapters('/html/42.html');
            eq(Object.keys(c),['https://www.8comic.com/view/42.html?ch=1','https://www.8comic.com/view/42.html?ch=1.5','https://www.8comic.com/view/42.html?ch=3']);
            eq(disposed,1);
        ''')

    def test_manhuashe_complete_large_dom_order_dedup(self):
        self.run_source('manhuashe',r'''
            s.loadSetting=()=>null;
            const row=i=>({attributes:{href:'/chapter_'+i+'.html'},text:'第'+i+'話'});
            const rows=Array.from({length:1003},(_,i)=>row(i+1));rows.push(row(1));
            htmlReply({select:{'#chapter-list > div.chapter-item > a':rows}});
            const c=await s.loadChapters('/comic');eq(Object.keys(c).length,1003);
            eq(Object.keys(c)[0],'/chapter_1.html');eq(Object.keys(c)[1002],'/chapter_1003.html');eq(disposed,1);
        ''')

    def test_html_sources_empty_and_http_failure(self):
        for artifact in ('comicabc','manhuashe'):
            self.run_source(artifact,r'''
                s.loadSetting=()=>null;
                htmlReply({});eq(await s.loadChapters('/comic'),{});
                htmlReply({},500);await rejects(()=>s.loadChapters('/comic'),'500');eq(disposed,1);
            ''')

    def test_mycomic_embedded_chapters_keep_map_order_and_original_ids(self):
        self.run_source('mycomic',r'''
            HtmlDocument=class extends Node { dispose() {} };
            htmlReply('chapters: [{"id":2,"title":"Third"},{"id":99,"title":"Special"},{"id":7,"title":"First"},{"id":2,"title":"Third"}]');
            const c=(await s.comic.loadInfo('1')).chapters;
            ok(c instanceof Map);eq([...c],[['7','First'],['99','Special'],['2','Third']]);
            eq(c.size,3);eq(calls[0].url,'https://mycomic.com/cn/comics/1');
        ''')

    def test_mycomic_fallback_links_keep_chronology_and_deduplicate(self):
        rows=[node('Third',{'href':'/cn/chapters/2'}),node('First',{'href':'/cn/chapters/7'}),node('Third',{'href':'/cn/chapters/2'})]
        doc=node(select={"a[href*='/cn/chapters/']":rows})
        self.run_source('mycomic',f'''
            HtmlDocument=class extends Node {{ constructor() {{ super({json.dumps(doc)}); }} }};
            htmlReply('chapters: [invalid]');
            eq([...(await s.comic.loadInfo('1')).chapters],[['7','First'],['2','Third']]);
        ''')

    def test_mycomic_empty_list_and_denied_detail(self):
        self.run_source('mycomic',r'''
            HtmlDocument=class extends Node {};
            htmlReply('chapters: []');eq((await s.comic.loadInfo('1')).chapters.size,0);
            htmlReply('',500);await rejects(()=>s.comic.loadInfo('1'),'HTTP 500');
        ''')

    def manhuagui_detail(self, grouped=True, modern=True):
        # Upload IDs deliberately disagree with story order; one duplicate spans panels.
        def row(ident,title):
            return node(select={'a':[node(attrs={'href':'/comic/1/'+ident+'.html'},select={'span':[node(title)]})]})
        book=node(select={'.book-title':[node(select={'h1':[node('Title')],'h2':[node('Subtitle')]})],
                          '.hcover':[node(select={'img':[node(attrs={'src':'//img.test/cover'})]})],
                          '#intro-all':[node()],'.detail-list span':[node() for _ in range(9)]})
        panels=[node(select={'li':[row('2','Third'),row('99','Second')]}),node(select={'li':[row('7','First'),row('2','Third')]})]
        if grouped:
            panels=[node(select={'li':[row('2','Third'),row('99','Second'),row('7','First'),row('2','Third')]}),node(select={'li':[row('1','Bonus')]})]
        doc=node(select={'.book-cont':[book],'.chapter-list':panels,
                         '.chapter h4 span':[node('Story'),node('Special')] if grouped else []})
        return f's.getHtml=async()=>new HtmlDocument({json.dumps(doc)});s.isAppVersionAfter=()=>{str(modern).lower()};'

    def test_manhuagui_preserves_groups_while_reversing_provider_order(self):
        self.run_source('manhuagui',self.manhuagui_detail()+r'''
            const c=(await s.comic.loadInfo('1')).chapters;
            eq([...c.keys()],['Story','Special']);
            eq([...c.get('Story')],[['7','First'],['99','Second'],['2','Third']]);
            eq([...c.get('Special')],[['1','Bonus']]);
        ''')

    def test_manhuagui_ungrouped_panels_merge_before_reversing(self):
        self.run_source('manhuagui',self.manhuagui_detail(grouped=False)+r'''
            const c=(await s.comic.loadInfo('1')).chapters;
            eq([...c.get('连载')],[['7','First'],['99','Second'],['2','Third']]);
        ''')

    def test_manhuagui_legacy_flatten_keeps_group_order_without_id_sort(self):
        self.run_source('manhuagui',self.manhuagui_detail(modern=False)+r'''
            const c=(await s.comic.loadInfo('1')).chapters;
            eq([...c],[['7','First'],['99','Second'],['2','Third'],['1','Bonus']]);
        ''')

    def copy_search_setup(self):
        return r'''
            s.loadSetting=k=>k==='base_url'?'api.test':null;
            s.author_path_word_dict={'Known Author':'known-author'};
            Object.defineProperty(s,'headers',{get:()=>({})});
        '''

    def test_copy_forks_search_totals_and_terminal_pages_match_30_row_requests(self):
        for artifact in ('copy_manga','copy_manga_multi_accounts'):
            for total in (0,30,31,60,421):
                self.run_source(artifact,self.copy_search_setup()+f'''
                    jsonReply({{results:{{total:{total},list:[]}}}});
                    const c=await s.search.load('愛 & Love',[],2);
                    eq(c.maxPage,{max(1,(total+29)//30)});
                    ok(calls[0].url.includes('limit=30&offset=30'));
                    ok(calls[0].url.includes(encodeURIComponent('愛 & Love')));
                ''')

    def test_hot_manga_search_last_page_is_not_truncated_by_21_row_divisor(self):
        for total in (0,20,21,420,421):
            self.run_source('hot_manga',self.copy_search_setup()+f'''
                jsonReply({{results:{{total:{total},list:[]}}}});
                const c=await s.search.load('爱',[],22);
                eq(c.maxPage,{max(1,(total+19)//20)});
                ok(calls[0].url.includes('limit=20&offset=420'));
            ''')

    def test_copy_family_author_search_uses_30_rows_and_preserves_http_errors(self):
        for artifact in ('copy_manga','copy_manga_multi_accounts','hot_manga'):
            self.run_source(artifact,self.copy_search_setup()+r'''
                jsonReply({results:{total:60,list:[]}});
                const c=await s.search.load('作者:Known Author',[],2);
                eq(c.maxPage,2);ok(calls[0].url.includes('limit=30&offset=30'));
                ok(calls[0].url.includes('author=known-author'));
                jsonReply({},403);await rejects(()=>s.search.load('愛',[],1),'403');
            ''')

    def test_every_published_chinese_converted_artifact_is_reproducible(self):
        registry=json.loads((ROOT/'sources_registry.json').read_bytes())
        for a in registry['artifacts']:
            if not any(l.startswith('zh') for l in a.get('locales',[])): continue
            if a['implementation']['producer']=='manual': continue
            with self.subTest(artifact=a['artifactId']):
                ident=a['artifactId'];ir=json.loads((ROOT/'sources_ir'/f'{ident}.json').read_bytes())
                base=generate_venera_js(ir)
                self.assertEqual(base,(ROOT/'sources_generated'/f'{ident}.base.js').read_text(encoding='utf-8'))
                patch=ROOT/'sources_patches'/f'{ident}.patch.js'
                final=patch_js(base,patch.read_text(encoding='utf-8')) if patch.exists() else base
                self.assertEqual(final,(ROOT/f'{ident}.js').read_text(encoding='utf-8'))

if __name__=='__main__': unittest.main()
