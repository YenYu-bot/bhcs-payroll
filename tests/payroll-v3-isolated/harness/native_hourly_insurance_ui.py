#!/usr/bin/env python3
"""Synthetic hourly/insurance UI tests. No function/source replacement, production data or Firebase.
Require non-root, sandboxed Chromium and externally established loopback-only namespace.
Native print-media/PDF pipeline is tested; not an OS print-dialog automation claim.
"""
import argparse, hashlib, json, os, pathlib, socket, threading, traceback, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
EXPECTED='388620bb25f64db6245bf187d4bbe64c6e78a22920f4509e9577cf65e0ceb837'
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

FIXTURE=r'''kind => {
 const e={id:'synthetic-review',name:'工時保費隔離合成人員',payType:'hourly',base:0,rate:200,
 hire:'2026-02-16',leave:'',labor:0,health:0,perfect:0,summer:0,otFixed:0,fixedItems:[],
 pensionWage:0,pensionSelf:0,sched:defaultSched(),hourBasis:'punch',hourRound:30,
 brkMin:0,brkAfter:4,leaveSystem:'cal',yearEnd:'pay',lateePolicy:'deduct',lateGrace:0,lateUnit:0};
 for(let i=0;i<7;i++)e.sched['d'+i]={type:'work',start:'09:00',end:'18:00'};
 if(kind==='minutes')for(let i=0;i<7;i++)e.sched['d'+i].end='09:59';
 const r=blankRec();r.days=[{date:'2026-02-16',wk:'一',in:'09:00',out:'09:59',wh:59,punches:2,status:'work',kind:'work'}];
 if(kind!=='minutes'){e.hourBasis='sched';e.brkMin=60;r.days[0].out='18:00';r.days[0].wh=540;}
 if(kind==='standard'){e.laborGrade=30300;e.labor=758;}
 if(kind==='unknown'||kind==='joint'){e.laborGrade='custom';e.labor=600;}
 return {version:3,settings:DEF_SETTINGS(),employees:[e],months:{'2026-02':{[e.id]:r}},log:[]};
}'''

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate-root',required=True);ap.add_argument('--output',required=True);a=ap.parse_args()
 out=pathlib.Path(a.output);out.mkdir(parents=True,exist_ok=False)
 report={'expected_sha256':EXPECTED,'cases':[],'requests_blocked':[],'scope':'synthetic native DOM, IndexedDB, dialogs and print media only; no Firebase'}
 server=None
 try:
  need(os.geteuid()!=0,'root forbidden');need([n for _,n in socket.if_nameindex()]==['lo'],'loopback-only namespace required')
  payload=(pathlib.Path(a.candidate_root)/'index.html').read_bytes();report['candidate_sha256']=hashlib.sha256(payload).hexdigest();need(report['candidate_sha256']==EXPECTED,'candidate hash mismatch')
  class Handler(BaseHTTPRequestHandler):
   def do_GET(self):
    if self.path=='/favicon.ico':self.send_response(204);self.end_headers();return
    if self.path not in ('/','/index.html'):self.send_error(404);return
    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)
   def log_message(self,*args):pass
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();origin='http://127.0.0.1:'+str(server.server_port)
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True,chromium_sandbox=True)
   report['browser']=browser.version;report['renderer_gate']=renderer_gate(browser)
   for kind in ['minutes','schedule','standard','unknown','joint']:
    ctx=browser.new_context(service_workers='block',timezone_id='Asia/Taipei',viewport={'width':1440,'height':1100})
    errors=[];downloads=[];dialog_queue=[];dialogs=[];phase=['setup'];events=[];steps=[];ui_batches=[];step_name=['setup'];started=time.monotonic()
    def route(r):
     u=urlsplit(r.request.url)
     if u.scheme=='http' and u.netloc==urlsplit(origin).netloc and u.path in ('/','/index.html','/favicon.ico'):r.continue_()
     else:report['requests_blocked'].append(r.request.url);r.abort()
    ctx.route('**/*',route);ctx.add_init_script("""window.FB_BASE=location.origin+'/__firebase_forbidden__/';window.__printEvents=[];addEventListener('beforeprint',()=>window.__printEvents.push('before'));addEventListener('afterprint',()=>window.__printEvents.push('after'));
     window.__testStep='setup';window.__uiEventLog=[];
     const desc=e=>e?{tag:e.tagName,id:e.id||'',change:e.getAttribute?.('onchange')||'',value:e.value??null,connected:e.isConnected}:null;
     for(const type of ['input','change','blur','focusout'])document.addEventListener(type,e=>{if(window.__uiEventLog.length<1000)window.__uiEventLog.push({type,step:window.__testStep,ms:performance.now(),trusted:e.isTrusted,target:desc(e.target),active:desc(document.activeElement)});},true);
     addEventListener('error',e=>window.__uiEventLog.push({type:'window-error',step:window.__testStep,ms:performance.now(),message:e.message,stack:e.error?.stack||'',file:e.filename,line:e.lineno,column:e.colno,active:desc(document.activeElement)}));
    """)
    page=ctx.new_page();page.on('pageerror',lambda e:errors.append({'message':str(e),'stack':getattr(e,'stack',None),'step':step_name[0],'elapsed_ms':round((time.monotonic()-started)*1000,3)}));page.on('download',lambda d:downloads.append(d.suggested_filename))
    def dialog(d):
     dialogs.append({'type':d.type,'message':d.message})
     if dialog_queue:
      expected,answer=dialog_queue.pop(0)
      if d.type!=expected:errors.append('unexpected dialog type '+d.type+' vs '+expected);d.dismiss();return
      if answer is None:d.dismiss()
      else:d.accept(answer if d.type=='prompt' else None)
     elif phase[0]=='setup' and d.type=='confirm':d.accept()
     else:errors.append('unexpected dialog '+d.type+': '+d.message);d.dismiss()
    page.on('dialog',dialog)
    try:
     page.goto(origin,wait_until='load');page.evaluate('async()=>{await storageReady;}')
     fixture=page.evaluate(FIXTURE,kind);(out/(kind+'-fixture.json')).write_text(json.dumps(fixture,ensure_ascii=False),encoding='utf-8')
     page.locator('#storageSetup input[type=file]').set_input_files({'name':'synthetic.json','mimeType':'application/json','buffer':json.dumps(fixture).encode()});expect(page.locator('#storageSetup')).to_be_hidden()
     month='2'
     def select_slip():
      page.locator('#pYear').fill('2026');page.locator('#pYear').press('Tab');page.select_option('#pMonth',month);page.locator('.step[data-v="slip"]').click()
     def save_done():
      steps.append({'step':step_name[0],'event':'save_wait_begin','elapsed_ms':round((time.monotonic()-started)*1000,3)})
      page.evaluate('async()=>{await saveChain;}')
      steps.append({'step':step_name[0],'event':'save_wait_complete','elapsed_ms':round((time.monotonic()-started)*1000,3),'state':page.evaluate("({error:persistence.error?.message||null,confirmed:mrec('synthetic-review').confirmed,annualEvents:mrec('synthetic-review').annualEvents,days:mrec('synthetic-review').days.map(x=>({date:x.date,hours:x.hours}))})")})
     def review(key,decision):page.locator('button[onclick="setReview(\'synthetic-review\',\''+key+'\',\''+decision+'\')"]').click();save_done()
     def approve_all():
      b=page.get_by_role('button',name='全部通過',exact=True)
      if b.count():b.click();save_done()
     def confirm_click():page.locator('button[onclick="toggleConfirm(\'synthetic-review\')"]').click();save_done()
     def money(label):return page.locator('input[data-lb="'+label+'"]').input_value().replace(',','')
     def reload_slip():
      ui_batches.append({'until_step':step_name[0],'reason':'before_native_reload','events':page.evaluate('window.__uiEventLog')})
      page.reload();page.evaluate('async()=>{await storageReady;}');select_slip()
     def step(label):
      step_name[0]=label;page.evaluate('(s)=>{window.__testStep=s}',label);steps.append({'step':label,'event':'begin','elapsed_ms':round((time.monotonic()-started)*1000,3)})
     def mark(label):
      events.append(label);steps.append({'step':label,'event':'complete','elapsed_ms':round((time.monotonic()-started)*1000,3),'page_error_count':len(errors)})
     select_slip();phase[0]='test';save_done()
     def net():return page.evaluate("compute(emp('synthetic-review')).net")
     def blocked_outputs():
      expect(page.locator('.slip-foot .lbl')).to_contain_text('不可付款')
      before=len(downloads);prints=page.evaluate('window.__printEvents.length')
      for fn in ['exportExcel()','exportWord()','printPayroll()']:
       page.locator('button[onclick="'+fn+'"]').click();page.wait_for_timeout(100)
      need(len(downloads)==before and page.evaluate('window.__printEvents.length')==prints,'blocked output side effect')
     def pending(key):return page.evaluate("(key)=>compute(emp('synthetic-review')).reviews.find(x=>x.key===key)?.st",key)
     def blocked():return page.evaluate("compute(emp('synthetic-review')).settlementBlocked")
     def override_bill(value):
      step('native_bill_override_'+str(value));field=page.locator('input[data-lb="勞保費"]');field.fill(str(value));field.press('Tab');save_done()
     expected_work='197' if kind=='minutes' else '1600'
     need(money('工時工資')==expected_work,'wrong actual minute/net schedule wage')
     need(page.evaluate("compute(emp('synthetic-review')).ot.pay")==0,'unexpected schedule overtime')
     need(pending('workMinutes')=='pending','work review missing')
     approve_all();confirm_click();need(not page.evaluate("mrec('synthetic-review').confirmed"),'batch bypassed work review');blocked_outputs();mark('batch_and_formal_outputs_blocked')
     if kind in ['minutes','schedule']:
      review('workMinutes','ok');need(not blocked(),'individual work acknowledgment not released')
      reload_slip();need(pending('workMinutes')=='ok' and money('工時工資')==expected_work,'work amount/review lost on IDB reload')
      if kind=='minutes':need(abs(page.evaluate("dayAgg(emp('synthetic-review'),mrec('synthetic-review')).regH")-59/60)<1e-8,'59m hours truncated')
      else:need(page.evaluate("compute(emp('synthetic-review')).hoursInfo.regH")==8,'9h minus60m not8h')
      mark('minutes_or_schedule_review_persists')
     elif kind=='standard':
      need(money('勞保費')=='378','30300 15d must348+30=378, not379')
      need(page.locator('.rv-tbl').inner_text().find('348')>=0 and page.locator('.rv-tbl').inner_text().find('378')>=0,'component review detail missing')
      review('workMinutes','ok');need(blocked() and pending('laborPrecision')=='pending','work review bypassed insurance review');blocked_outputs()
      review('laborPrecision','ok');need(blocked() and pending('pensionPrecision')=='pending','labor acknowledgment bypassed pension gate');blocked_outputs()
      # This grade also supplies the pension wage. Resolve the NEW independent gate through native dialogs.
      dialog_queue.extend([('prompt','15'),('prompt','909'),('prompt','0'),('prompt','合成勞退提繳明細'),('confirm','yes')])
      page.get_by_role('button',name='核對／更正勞退帳單',exact=True).click();save_done();need(not dialog_queue,'pension dialogs not consumed')
      need(blocked(),'statement skipped individual review');review('pensionPrecision','ok');need(not blocked(),'standard known grade not released');reload_slip();need(money('勞保費')=='378' and pending('laborPrecision')=='ok','precision review lost on IDB reload');mark('standard_378_individual_review')
     elif kind=='unknown':
      review('workMinutes','ok');review('laborPrecision','ok');need(blocked(),'unknown amount acknowledgment guessed bill');blocked_outputs();mark('unknown_bill_not_guessed')
      override_bill(378);need(pending('laborPrecision')=='pending' and blocked(),'bill change did not invalidate precision review');blocked_outputs()
      review('laborPrecision','ok');need(not blocked() and money('勞保費')=='378','bill override not accepted');reload_slip();need(not blocked() and money('勞保費')=='378','bill override lost in IDB');mark('native_bill_override_persistence')
      override_bill('');review('laborPrecision','ok');need(blocked(),'cleared unknown bill allowed');blocked_outputs()
      override_bill(378);review('laborPrecision','ok');need(not blocked(),'restored valid bill still blocked');mark('cleared_unknown_bill_never_final')
     else:
      override_bill(378);review('laborPrecision','ok');need(blocked() and pending('workMinutes')=='pending','insurance review bypassed work gate');blocked_outputs()
      page.emulate_media(media='print');need(page.locator('.slip').evaluate("e=>Array.from(e.children).every(x=>getComputedStyle(x).display==='none')"),'blocked print leaked payroll fields');page.pdf(path=str(out/'joint-blocked.pdf'),print_background=True);page.emulate_media(media='screen')
      review('workMinutes','ok');need(not blocked(),'joint review did not release');reload_slip();need(not blocked(),'joint acknowledgment lost in IDB');mark('both_independent_gates_and_print_media')
     approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'fully reviewed payroll not confirmed')
     snapshot=page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)");reload_slip();need(page.evaluate("compute(emp('synthetic-review')).locked"),'snapshot not persisted')
     page.evaluate("async()=>{emp('synthetic-review').rate=333;emp('synthetic-review').brkMin=15;emp('synthetic-review').labor=999;await save();renderSlips();}");reload_slip()
     need(page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)")==snapshot and money('工時工資')==expected_work,'confirmed snapshot changed after current settings changed');mark('historical_snapshot_immutable')
     need(not errors,'page errors '+repr(errors));need(not dialog_queue,'unconsumed dialogs');page.wait_for_timeout(300);page.screenshot(path=str(out/(kind+'.png')),full_page=True)
     report['cases'].append({'case':kind,'result':'PASS','events':events,'dialogs':dialogs,'downloads':downloads,'steps':steps,'ui_event_batches':ui_batches,'ui_events':page.evaluate('window.__uiEventLog')})
    except Exception:
     report['cases'].append({'case':kind,'result':'FAIL','error':traceback.format_exc(),'page_errors':errors,'events':events,'dialogs':dialogs,'steps':steps,'ui_event_batches':ui_batches,'ui_events':page.evaluate('window.__uiEventLog')})
     try:page.screenshot(path=str(out/(kind+'-failure.png')),full_page=True)
     except Exception:pass
    finally:ctx.close()
   browser.close()
  report['candidate_sha256_after']=hashlib.sha256((pathlib.Path(a.candidate_root)/'index.html').read_bytes()).hexdigest();need(report['candidate_sha256_after']==EXPECTED,'candidate modified')
  need(not report['requests_blocked'],'unexpected network request was blocked');need(len(report['cases'])==5 and all(x['result']=='PASS' for x in report['cases']),'one or more cases failed');report['result']='PASS'
 except Exception:report['result']='FAIL';report['error']=traceback.format_exc()
 finally:
  if server:server.shutdown();server.server_close()
  (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
