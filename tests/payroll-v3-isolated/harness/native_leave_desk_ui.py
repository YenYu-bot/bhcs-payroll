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
        decision=[True]
        async def dialog(d):
            if d.type!='confirm': errors.append('unexpected '+d.type)
            if decision[0] and d.type=='confirm':await d.accept()
            else:await d.dismiss()
        page.on('dialog',lambda d:asyncio.create_task(dialog(d)))
        await page.goto(origin+'/');await page.evaluate('async()=>{await storageReady}')
        fixture=await page.evaluate("""()=>{
          const make=(id,payType='monthly')=>({id,name:'合成-'+id,payType,base:36000,rate:205,hire:'2026-01-01',leave:'',labor:0,health:0,perfect:0,otFixed:0,fixedItems:[],sched:Object.fromEntries(Array.from({length:7},(_,i)=>['d'+i,{type:i===0?'off':i===6?'rest':'work',start:'09:00',end:payType==='hourly'?'12:00':'17:00'}])),hourBasis:'punch',brkMin:payType==='hourly'?0:90,brkAfter:6,leaveSystem:'cal',yearEnd:'pay'});
          const m=blankRec(),h=blankRec(),locked=blankRec();
          m.days=[{date:'2026-10-08',wk:'四',status:'pending',kind:'work',hours:null,punches:0,wh:0}];
          h.days=[{date:'2026-10-08',wk:'四',status:'work',kind:'work',hours:3,punches:2,wh:180}];
          const fixture={version:3,settings:DEF_SETTINGS(),employees:[make('salary'),make('hourly','hourly'),make('locked')],months:{'2026-10':{salary:m,hourly:h,locked}},log:[]};
          const old=state;try{state=fixture;const snapshot=computeLive(fixture.employees[2],'2026-10',locked);Object.assign(locked,{confirmed:true,snapshot:{...snapshot,net:7777,marker:'unchanged'}});}finally{state=old;}
          return fixture;
        }""")
        await page.locator('#storageSetup input[type=file]').set_input_files({'name':'synthetic-leave-desk.json','mimeType':'application/json','buffer':json.dumps(fixture).encode()})
        await page.wait_for_function('localDB.ready && !sec.locked && !persistence.loadBlocked')
        async def open_desk(id='salary'):
            await page.locator('#pYear').fill('2026');await page.locator('#pYear').press('Tab');await page.select_option('#pMonth','10')
            await page.locator('[data-v="leaveDesk"]').click();await page.select_option('#ldEmployee',id)
        async def enter(date,kind):
            await page.locator('#ldDate').fill(date);await page.select_option('#ldType',kind)
        await open_desk()
        await enter('2026-10-08','annual')
        assert '6 小時 30 分鐘' in await page.locator('#ldPreview').inner_text()
        before=await page.evaluate('JSON.stringify(state)')
        decision[0]=False;await page.locator('#ldSave').click()
        assert before==await page.evaluate('JSON.stringify(state)');checks.append('cancel-no-write')
        decision[0]=True;await page.locator('#ldSave').click()
        await page.get_by_text('已儲存。請假已列入本月出勤。',exact=True).wait_for()
        assert await page.evaluate("state.months['2026-10'].salary.days[0].hours") == 6.5
        assert await page.locator('#ldSave').is_disabled();checks.append('full-pending-replacement-and-duplicate-block')
        await enter('2026-10-12','personal')
        await page.locator('#ldPartial').check();await page.locator('#ldHours').fill('20')
        await page.locator('#ldSave').click();await page.get_by_text('已儲存。請假已列入本月出勤。',exact=True).wait_for()
        assert '20 分鐘' in await page.locator('#ldList').inner_text();checks.append('partial-20-minute-visible')
        await page.locator('[data-v="att"]').click()
        await page.locator('#attFile').set_input_files({'name':'synthetic.csv','mimeType':'text/csv','buffer':'姓名,日期,假別,時數\n合成-salary,2026-10-08,事假,1\n'.encode()})
        try:
            await page.get_by_text('已有請假登記，未覆蓋：合成-salary。請到出勤日曆核對後手動補登出勤。',exact=True).wait_for(timeout=8000)
        except Exception:
            print(json.dumps(await page.evaluate("""()=>({message:$('parseMsg').textContent,ym:curYM(),days:state.months['2026-10'].salary.days})"""),ensure_ascii=False),flush=True)
            print(json.dumps({'pageErrors':errors},ensure_ascii=False),flush=True)
            raise
        assert await page.evaluate("state.months['2026-10'].salary.days[0].status")=='annual';checks.append('import-cannot-overwrite')
        if await page.locator('#absModal').evaluate("e=>e.classList.contains('on')"):await page.locator('#absModal button[onclick="closeAbs()"]').first.click()
        await page.reload();await page.wait_for_function('localDB.ready && !sec.locked')
        await open_desk()
        assert '20 分鐘' in await page.locator('#ldList').inner_text();checks.append('native-idb-reload')
        await page.locator('#ldCalendar').click()
        row=page.locator('#detModal tr').filter(has_text='10-08')
        assert await row.locator('select').first.is_disabled()
        await row.get_by_role('button',name='移除請假').click()
        await page.wait_for_function('persistence.pending===0 && !persistence.error')
        assert await page.evaluate("state.months['2026-10'].salary.days[0].status")=='pending'
        await page.locator('#detModal button[onclick="closeDet()"]').first.click()
        assert '2026-10-08' not in await page.locator('#ldList').inner_text();checks.append('remove-restores-pending')
        await page.select_option('#ldEmployee','hourly')
        await enter('2026-10-08','sick');assert await page.locator('#ldSave').is_disabled()
        await enter('2026-10-12','sick');assert await page.locator('#ldPartial').is_disabled()
        assert '3 小時' in await page.locator('#ldPreview').inner_text();checks.append('hourly-partial-and-punch-guard')
        await page.select_option('#ldEmployee','locked')
        await enter('2026-10-08','sick') if not await page.locator('#ldType').is_disabled() else await page.locator('#ldDate').fill('2026-10-08')
        assert await page.locator('#ldSave').is_disabled()
        assert await page.evaluate("state.months['2026-10'].locked.snapshot")==fixture['months']['2026-10']['locked']['snapshot']
        checks.append('confirmed-snapshot-protected')
        assert not errors and not downloads and not requests,(errors,downloads,requests)
        await page.screenshot(path=str(out/'leave-desk.png'),full_page=True)
        (out/'leave-desk.json').write_text(json.dumps({'candidate':EXPECTED,'checks':checks,'errors':errors,'external_requests':requests,'renderer_gate':renderers},ensure_ascii=False))
        await browser.close()
    server.shutdown();assert hashlib.sha256(html.read_bytes()).hexdigest()==EXPECTED
    print(json.dumps({'passed':len(checks),'candidate':EXPECTED}))
asyncio.run(main())
