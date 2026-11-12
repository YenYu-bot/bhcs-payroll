#!/usr/bin/env python3
"""Independent payroll UI review. Native sandboxed Chromium + native IndexedDB.
No source transformation or application-function replacements. Only synthetic fixture import.
Must execute as non-root inside a loopback-only network namespace; no fallback sandbox flags.
"""
import argparse, hashlib, json, os, pathlib, socket, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

EXPECTED='52086ec4fd1fde1b7e2cde7ed587dbe5c68e42ad1e602427b5426a556349d456'
FIXTURE=r'''kind => {
 const e={id:'synthetic-review',name:'獨立審核合成員工',payType:'monthly',base:36000,rate:200,
 hire:'2026-01-01',leave:'',labor:0,health:0,perfect:0,summer:0,otFixed:0,fixedItems:[],
 pensionWage:0,pensionSelf:0,sched:defaultSched(),hourBasis:'punch',hourRound:0,
 brkMin:0,brkAfter:0,leaveSystem:'cal',yearEnd:'pay',lateePolicy:'deduct',lateGrace:0,lateUnit:0};
 const r=blankRec(),date=kind==='offday'?'2026-11-01':'2026-11-02';
 r.days=[{date,wk:wkOf(date),status:'work',kind:kind==='offday'?'offWork':'work',wh:600,punches:2,in:'09:00',out:'19:00'}];
 if(kind==='sources'||kind==='reject')r.otEvents=[{date:'2026/11/2',type:'weekday',hours:2}];
 if(kind==='hourly'){e.payType='hourly';e.lateePolicy='annualOffset';r.days[0].wh=420;r.days[0].in='10:00';r.days[0].out='17:00';r.lateEvents=[{date,late:60,early:0}];}
 return {version:3,settings:DEF_SETTINGS(),employees:[e],months:{'2026-11':{[e.id]:r}},log:[]};
}'''

def need(value, msg):
 if not value: raise AssertionError(msg)

def renderer_gate(browser):
 probe=browser.new_page();probe.set_content('<p>renderer sandbox check</p>')
 infos=browser.new_browser_cdp_session().send('SystemInfo.getProcessInfo')['processInfo'];found=[]
 for p in infos:
  if p['type']!='renderer':continue
  root=pathlib.Path('/proc')/str(p['id'])
  try:
   cmd=(root/'cmdline').read_bytes().replace(b'\0',b' ').split()
   if b'--type=renderer' not in cmd:continue
   status=dict(x.split(':',1) for x in (root/'status').read_text().splitlines())
   found.append({'pid':p['id'],'seccomp':status['Seccomp'].strip(),'nnp':status['NoNewPrivs'].strip(),'nspid':status['NSpid'].split(),'noSandbox':b'--no-sandbox' in cmd})
  except OSError:continue
 need(found and all(x['seccomp']=='2' and x['nnp']=='1' and len(x['nspid'])>=2 and not x['noSandbox'] for x in found),'renderer sandbox protection not proven')
 probe.close();return found

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate-root',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=False)
 report={'candidate_sha256':None,'cases':[],'requests_blocked':[],'scope':'synthetic calculation UI and local IDB only, no Firebase integration'}
 server=None
 try:
  need(os.geteuid()!=0,'root forbidden');need([n for _,n in socket.if_nameindex()]==['lo'],'loopback-only namespace required')
  payload=(pathlib.Path(a.candidate_root)/'index.html').read_bytes();report['candidate_sha256']=hashlib.sha256(payload).hexdigest()
  need(report['candidate_sha256']==EXPECTED,'candidate hash mismatch')
  class Handler(BaseHTTPRequestHandler):
   def do_GET(self):
    if self.path=='/favicon.ico':self.send_response(204);self.end_headers();return
    if self.path not in ('/','/index.html'):self.send_error(404);return
    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
   def log_message(self,*args):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
  origin='http://127.0.0.1:'+str(server.server_port)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,chromium_sandbox=True)
   report['browser']=browser.version;report['renderer_gate']=renderer_gate(browser)
   for kind in ['monthly','sources','reject','hourly','offday']:
    ctx=browser.new_context(service_workers='block',timezone_id='Asia/Taipei',viewport={'width':1440,'height':1100})
    errors=[]
    def route(r):
     u=urlsplit(r.request.url)
     if u.scheme=='http' and u.netloc==urlsplit(origin).netloc and u.path in ('/','/index.html','/favicon.ico'):r.continue_()
     else:report['requests_blocked'].append(r.request.url);r.abort()
    ctx.route('**/*',route)
    # Prevent production Firebase module imports even if initialization accidentally runs.
    ctx.add_init_script("window.FB_BASE=location.origin+'/__firebase_forbidden__/';")
    page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
    try:
     page.goto(origin,wait_until='load');page.evaluate('async()=>{await storageReady;}')
     fixture=page.evaluate(FIXTURE,kind)
     (out/(kind+'-fixture.json')).write_text(json.dumps(fixture,ensure_ascii=False),encoding='utf-8')
     page.locator('#storageSetup input[type=file]').set_input_files({'name':'synthetic.json','mimeType':'application/json','buffer':json.dumps(fixture).encode()})
     expect(page.locator('#storageSetup')).to_be_hidden()
     page.locator('#pYear').fill('2026');page.locator('#pYear').dispatch_event('change');page.select_option('#pMonth','11');page.locator('.step[data-v="slip"]').click()
     def money(label):return page.locator('input[data-lb="'+label+'"]').input_value().replace(',','')
     def save_done():page.evaluate('async()=>{await saveChain;}')
     def review(key,decision):page.locator('button[onclick="setReview(\'synthetic-review\',\''+key+'\',\''+decision+'\')"]').click();save_done()
     confirm=page.locator('button[onclick="toggleConfirm(\'synthetic-review\')"]')
     if kind=='monthly':
      need(money('加班費')=='400','monthly 10h expected OT400')
      review('ot','ok');confirm.click();save_done()
      need(page.evaluate("mrec('synthetic-review').confirmed"),'UI confirmation did not lock')
      # Synthetic fixture mutation deliberately bypasses editing UI to test locked compute path.
      page.evaluate("async()=>{mrec('synthetic-review').days[0].wh=720;await save();renderSlips();}")
      need(money('加班費')=='400','confirmed snapshot recalculated after source mutation')
      page.reload();page.evaluate('async()=>{await storageReady;}');page.locator('#pYear').fill('2026');page.locator('#pYear').dispatch_event('change');page.select_option('#pMonth','11');page.locator('.step[data-v="slip"]').click()
      need(money('加班費')=='400','snapshot did not survive native IndexedDB reload')
     elif kind=='sources':
      need(money('加班費')=='900','mixed date formats manual2+auto2 expected900')
      page.get_by_role('button',name='全部通過',exact=True).click();save_done()
      need(page.evaluate("compute(emp('synthetic-review')).reviews.find(x=>x.key==='otSources').st")=='pending','approveAll bypassed source acknowledgement')
      confirm.click();save_done();need(not page.evaluate("mrec('synthetic-review').confirmed"),'pending source permitted confirmation')
      review('otSources','ok');confirm.click();save_done();need(page.evaluate("mrec('synthetic-review').confirmed"),'acknowledged source did not permit confirmation')
     elif kind=='reject':
      review('ot','no');need(money('加班費')=='400','reject auto must retain manual400')
      need(page.evaluate("compute(emp('synthetic-review')).reviews.find(x=>x.key==='otSources').st")=='pending','reject auto incorrectly bypassed source ack')
      review('otSources','ok');confirm.click();save_done();need(page.evaluate("mrec('synthetic-review').snapshot.earnings.find(x=>x[0]==='加班費')[1]")==400,'confirmed rejected-auto amount wrong')
     elif kind=='hourly':
      need(money('工時工資')=='1400','hourly actual7h expected1400')
      need(page.evaluate("usageItems(emp('synthetic-review'),Date.UTC(2026,11,1)).filter(x=>x.kind==='late').length")==0,'hourly consumed annual leave')
      need(page.locator('button[onclick*="lateOffset"]').count()==0,'hourly annual-offset review displayed')
      need(page.evaluate("compute(emp('synthetic-review')).deducts.find(x=>x[0]==='遲到/早退扣薪')[1]")==0,'hourly punch lateness deducted twice')
     elif kind=='offday':need(money('加班費')=='1,800'.replace(',',''),'offday10h expected1800')
     need(not errors,'page errors: '+repr(errors));page.screenshot(path=str(out/(kind+'.png')),full_page=True)
     report['cases'].append({'case':kind,'result':'PASS'})
    except Exception:
     report['cases'].append({'case':kind,'result':'FAIL','error':traceback.format_exc()})
     try:page.screenshot(path=str(out/(kind+'-failure.png')),full_page=True)
     except Exception:pass
    finally:ctx.close()
   browser.close()
  report['candidate_sha256_after']=hashlib.sha256((pathlib.Path(a.candidate_root)/'index.html').read_bytes()).hexdigest()
  need(report['candidate_sha256_after']==EXPECTED,'candidate changed during tests')
  need(not report['requests_blocked'],'unexpected network attempt was blocked')
  need(len(report['cases'])==5 and all(x['result']=='PASS' for x in report['cases']),'one or more UI checks failed')
  report['result']='PASS'
 except Exception:
  report['result']='FAIL';report['error']=traceback.format_exc()
 finally:
  if server:server.shutdown();server.server_close()
  (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
