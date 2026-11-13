"""Synthetic only. Run inside approved loopback-only, non-root sandbox CI.
Requires Playwright/Chromium from official pinned CI dependencies. Never use --no-sandbox.
This script was syntax-checked locally, NOT executed in the local environment.
"""
import argparse, asyncio, hashlib, http.server, json, os, pathlib, threading, subprocess
from playwright.async_api import async_playwright
from urllib.parse import urlsplit
EXPECTED='388620bb25f64db6245bf187d4bbe64c6e78a22920f4509e9577cf65e0ceb837'
SOURCES=['01-01','02-04','02-05','02-06','02-07','02-08','02-28','04-04','04-05','05-01','06-09','09-15','09-28','10-10','10-25','12-25']
TARGETS={'02-06':'02-09','02-07':'02-10','02-28':'03-01','04-04':'04-06','05-01':'05-03','10-10':'10-11','12-25':'12-27'}
async def main():
    a=argparse.ArgumentParser();a.add_argument('--html',required=True);a.add_argument('--out',required=True);a.add_argument('--chromium');args=a.parse_args()
    html=pathlib.Path(args.html).resolve();out=pathlib.Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    assert hashlib.sha256(html.read_bytes()).hexdigest()==EXPECTED
    assert os.getuid()!=0, 'must run as non-root'
    # sysfs can remain mounted from the host; query this process network namespace.
    links=json.loads(subprocess.check_output(['ip','-j','link'],text=True))
    routes=json.loads(subprocess.check_output(['ip','-j','route'],text=True))
    assert {x['ifname'] for x in links}=={'lo'}, 'requires loopback-only network namespace'
    assert routes==[], 'routes forbidden'
    assert len(pathlib.Path('/proc/net/route').read_text().strip().splitlines())==1, 'routes forbidden'
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path=='/':
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(html.read_bytes())
            elif self.path=='/favicon.ico':self.send_response(204);self.end_headers()
            else:self.send_response(404);self.end_headers()
        def log_message(self,*_):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();origin=f'http://127.0.0.1:{server.server_port}'
    errors=[];requests=[];downloads=[];checks=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,chromium_sandbox=True,**({'executable_path':args.chromium} if args.chromium else {}))
        probe=await browser.new_page();await probe.set_content('<p>sandbox proof</p>');session=await browser.new_browser_cdp_session();infos=(await session.send('SystemInfo.getProcessInfo'))['processInfo'];renderers=[]
        for info in infos:
            if info['type']!='renderer':continue
            root=pathlib.Path('/proc')/str(info['id'])
            try:
                cmd=(root/'cmdline').read_bytes().replace(b'\0',b' ').split();status=dict(x.split(':',1) for x in (root/'status').read_text().splitlines())
                if b'--type=renderer' not in cmd:continue
                renderers.append({'pid':info['id'],'seccomp':status['Seccomp'].strip(),'nnp':status['NoNewPrivs'].strip(),'nspid':status['NSpid'].split(),'noSandbox':b'--no-sandbox' in cmd})
            except OSError:continue
        assert renderers and all(x['seccomp']=='2' and x['nnp']=='1' and len(x['nspid'])>=2 and not x['noSandbox'] for x in renderers)
        await probe.close()
        context=await browser.new_context(accept_downloads=False,service_workers='block',timezone_id='Asia/Taipei',viewport={'width':1440,'height':1100})
        async def route(r):
            if r.request.url.startswith(origin+'/') and urlsplit(r.request.url).path in ('/','/favicon.ico'):await r.continue_()
            else:requests.append(r.request.url);await r.abort()
        await context.route('**/*',route);await context.add_init_script("window.FB_BASE=location.origin+'/disabled/';window.__printEvents=[];addEventListener('beforeprint',()=>window.__printEvents.push('before'));window.__uiEvents=[];for(const t of ['input','change'])document.addEventListener(t,e=>window.__uiEvents.push({type:t,id:e.target.id,trusted:e.isTrusted}),true);")
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('download',lambda d:downloads.append(d.suggested_filename))
        phase=['setup'];dialogs=[]
        async def dialog(d):
            dialogs.append({'type':d.type,'message':d.message,'phase':phase[0]})
            if phase[0]=='setup' and d.type=='confirm':await d.accept()
            else:errors.append('unexpected dialog '+d.type);await d.dismiss()
        page.on('dialog',lambda d:asyncio.create_task(dialog(d)))
        await page.goto(origin+'/');await page.evaluate('async()=>{await storageReady}')
        fixture=await page.evaluate("""async()=>{
          const fixture={version:3,settings:DEF_SETTINGS(),employees:[],months:{},log:[]};
          const e={id:'synthetic-calendar',name:'合成行事曆',payType:'monthly',base:36000,rate:205,hire:'2026-01-01',leave:'',labor:0,health:0,perfect:0,summer:0,otFixed:0,fixedItems:[],pensionWage:0,pensionSelf:0,sched:Object.fromEntries(Array.from({length:7},(_,i)=>['d'+i,{type:i===0?'off':i===6?'rest':'work',start:'09:00',end:'17:00'}])),hourBasis:'punch',hourRound:0,brkMin:0,brkAfter:0,leaveSystem:'cal',yearEnd:'pay',lateePolicy:'deduct',lateGrace:0,lateUnit:0};
          fixture.employees=[e];const r=blankRec();fixture.months={'2027-03':{[e.id]:r},'2026-12':{[e.id]:Object.assign(blankRec(),{confirmed:true,snapshot:{net:7777,marker:'unchanged'}})}};
          for(let n=1;n<=31;n++){const d='2027-03-'+String(n).padStart(2,'0'),w=new Date(pd(d)).getUTCDay();if(w>0&&w<6)r.days.push({date:d,wk:wkOf(d),status:n===1?'holiday':'work',kind:'work',hours:8,punches:2,wh:480});}
          return fixture;
        }""")
        await page.locator('#storageSetup input[type=file]').set_input_files({'name':'synthetic-calendar.json','mimeType':'application/json','buffer':json.dumps(fixture).encode()});await page.wait_for_function('localDB.ready && !sec.locked && !persistence.loadBlocked');await page.locator('#storageSetup').wait_for(state='hidden');phase[0]='test'
        await page.locator('#pYear').fill('2027');await page.locator('#pYear').press('Tab');await page.select_option('#pMonth','3');await page.locator('[data-v="slip"]').click()
        async def settle():await page.wait_for_function('persistence.pending===0 && !persistence.error')
        async def open_cal():await page.get_by_role('button',name='開啟年度映射／本月核對',exact=True).click()
        await open_cal();before=await page.evaluate('JSON.stringify(state)');await page.locator('#calBasis').fill('取消中的草稿');await page.keyboard.press('Escape');assert await page.evaluate('JSON.stringify(state)')==before;checks.append('cancel-no-state-change')
        await open_cal();await page.locator('#calCoverage').check();await page.locator('#calBasis').fill('合成官方固定日＋合成個人補假協議')
        for i,s in enumerate(SOURCES):
            await page.locator(f'#calMode{i}').select_option('substitute' if s in TARGETS else 'original')
            await page.locator(f'#calTarget{i}').fill('2027-'+TARGETS.get(s,s));await page.locator(f'#calNote{i}').fill('合成核對依據 '+s)
        await page.get_by_role('button',name='儲存年度映射（本月仍須核對）',exact=True).click();await settle()
        assert await page.evaluate("computeLive(emp('synthetic-calendar'),'2027-03',mrec('synthetic-calendar','2027-03')).settlementBlocked")
        checks.append('annual-plan-does-not-bypass-month-review')
        await open_cal();await page.locator('#calReviewer').fill('合成核對人');await page.locator('#calMonthNote').fill('合成三月：核對無特殊適用日及無個別輪班');await page.locator('#calSpecial').check();await page.locator('#calRegular').check();await page.get_by_role('button',name='個別核對本月',exact=True).click();await settle()
        assert not await page.evaluate("computeLive(emp('synthetic-calendar'),'2027-03',mrec('synthetic-calendar','2027-03')).settlementBlocked")
        checks.append('real-dom-plan-and-month-ack')
        await page.reload();await page.wait_for_function('localDB.ready && !sec.locked');await page.locator('#pYear').fill('2027');await page.locator('#pYear').press('Tab');await page.select_option('#pMonth','3');await page.locator('[data-v="slip"]').click()
        assert not await page.evaluate("computeLive(emp('synthetic-calendar'),'2027-03',mrec('synthetic-calendar','2027-03')).settlementBlocked");checks.append('idb-reload-retains-review')
        await open_cal();await page.get_by_role('button',name='撤銷本月核對',exact=True).click();await settle();assert await page.evaluate("computeLive(emp('synthetic-calendar'),'2027-03',mrec('synthetic-calendar','2027-03')).settlementBlocked");checks.append('revoke-blocks-output')
        await open_cal();before=await page.evaluate('JSON.stringify(state)');await page.locator('#calTarget6').fill('2027-02-04');await page.get_by_role('button',name='儲存年度映射（本月仍須核對）',exact=True).click();assert await page.evaluate('JSON.stringify(state)')==before;checks.append('duplicate-target-rejected');await page.keyboard.press('Escape')
        before_downloads=len(downloads);before_prints=await page.evaluate('window.__printEvents.length')
        for fn in ['exportExcel()','exportWord()','printPayroll()']:
            await page.locator('button[onclick="'+fn+'"]').click();await page.wait_for_timeout(100)
        assert len(downloads)==before_downloads and await page.evaluate('window.__printEvents.length')==before_prints
        await page.emulate_media(media='print');assert await page.locator('.slip').evaluate("e=>Array.from(e.children).every(x=>getComputedStyle(x).display==='none')")
        await page.pdf(path=str(out/'calendar-blocked.pdf'),print_background=True);await page.emulate_media(media='screen');checks.append('blocked-excel-word-print-and-pdf-mask')
        snap=await page.evaluate("state.months['2026-12']['synthetic-calendar'].snapshot");assert snap=={'net':7777,'marker':'unchanged'};checks.append('historical-snapshot-unchanged')
        assert not errors and not downloads and not requests
        await page.screenshot(path=str(out/'calendar-final.png'),full_page=True)
        (out/'calendar-ui.json').write_text(json.dumps({'candidate':EXPECTED,'checks':checks,'errors':errors,'downloads':downloads,'external_requests':requests,'historical':snap,'dialogs':dialogs,'renderer_gate':renderers,'ui_events':await page.evaluate('window.__uiEvents')},ensure_ascii=False,indent=2))
        await browser.close()
    server.shutdown();assert hashlib.sha256(html.read_bytes()).hexdigest()==EXPECTED
    print(json.dumps({'passed':len(checks),'candidate':EXPECTED}))
asyncio.run(main())
