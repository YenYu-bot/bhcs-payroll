#!/usr/bin/env python3
"""Synthetic leave UI tests. No function/source replacement, production data or Firebase.
Require non-root, sandboxed Chromium and externally established loopback-only namespace.
Native print-media/PDF pipeline is tested; not an OS print-dialog automation claim.
"""
import argparse, hashlib, json, os, pathlib, socket, threading, traceback, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
EXPECTED='562ba4bbee112235eb8b014b66108236bb98115bfb09ddf20f8a73c26b0c9388'
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
 const e={id:'synthetic-review',name:'病假特休隔離合成人員',payType:'monthly',base:26500,rate:200,
 hire:kind==='partial'?'2026-11-02':'2024-01-01',leave:'',labor:0,health:0,perfect:3000,summer:0,otFixed:0,fixedItems:[],
 pensionWage:0,pensionSelf:0,sched:defaultSched(),hourBasis:'punch',hourRound:0,brkMin:0,brkAfter:0,
 leaveSystem:'cal',yearEnd:'pay',lateePolicy:'deduct',lateGrace:0,lateUnit:0};
 for(let i=0;i<7;i++)e.sched['d'+i]={type:'work',start:'09:00',end:'17:00'};
 const r=blankRec();r.att.sick=8;r.annualEvents=[{date:'2026-11-04',hours:8}];
 return {version:3,settings:DEF_SETTINGS(),employees:[e],months:{'2026-11':{[e.id]:r}},log:[]};
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
   for kind in ['normal','override','partial']:
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
     month='11'
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
     def blocked():return page.evaluate("compute(emp('synthetic-review')).settlementBlocked")
     def override(label,value):
      step('override_'+label+'_'+str(value));page.get_by_role('button',name='最後確認 / 修改',exact=True).click()
      modal=page.locator('#ovModal');expect(modal).to_have_class('overlay on')
      field=modal.locator('tr').filter(has=page.get_by_text(label,exact=True)).locator('input');field.fill(str(value));field.press('Tab');save_done()
      modal.locator('button[onclick="closeOv()"]').first.click();expect(modal).not_to_have_class('overlay on')
     if kind=='partial':
      need(blocked(),'partial month erroneously unlocked');approve_all();confirm_click();need(not page.evaluate("mrec('synthetic-review').confirmed"),'partial month confirmed');blocked_outputs();reload_slip();need(blocked(),'partial blocker lost');mark('partial_remains_blocked')
     else:
      need(net()==29009 and money('病假最低工資補足')=='99','paid annual sick floor not 29009');approve_all();confirm_click();need(blocked() and not page.evaluate("mrec('synthetic-review').confirmed"),'batch bypassed floor review');blocked_outputs();mark('paid_annual_pending_floor')
      review('sickFloor','ok');need(not blocked(),'individual floor acknowledgment did not release')
      reload_slip();need(net()==29009 and not blocked(),'floor review not persisted');mark('floor_review_idb_reload')
      if kind=='override':
       for label in ['生理假扣薪','事假扣薪','曠職扣薪','颱風假扣薪','遲到/早退扣薪']:
        override(label,500);approve_all();review('sickFloor','ok');confirm_click();need(blocked() and not page.evaluate("mrec('synthetic-review').confirmed"),'non-sick override bypass '+label);blocked_outputs()
        reload_slip();need(blocked(),'override blocker lost on reload '+label)
        if label=='事假扣薪':
         page.emulate_media(media='print');need(page.locator('.slip').evaluate("e=>Array.from(e.children).every(x=>getComputedStyle(x).display==='none')"),'blocked print leaked fields');page.pdf(path=str(out/'override-blocked.pdf'),print_background=True);page.emulate_media(media='screen')
        override(label,'');need(blocked(),'removing override reused floor acknowledgment');review('sickFloor','ok');need(not blocked(),'clean override failed to release');mark('non_sick_override_blocked_'+label)
       override('勞保費',500);review('sickFloor','ok');need(not blocked() and net()==28509,'insurance wrongly treated as normal-wage reduction');mark('insurance_net_not_floor')
      approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'verified payroll confirmation failed')
      snapshot=page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)");locked_net=net();reload_slip();need(page.evaluate("compute(emp('synthetic-review')).locked"),'snapshot not persisted')
      page.evaluate("async()=>{emp('synthetic-review').base=90000;await save();renderSlips();}");reload_slip();need(page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)")==snapshot and net()==locked_net,'historical snapshot changed');mark('snapshot_immutable')
     need(not errors,'page errors '+repr(errors));need(not dialog_queue,'unconsumed dialogs');page.wait_for_timeout(300);page.screenshot(path=str(out/(kind+'.png')),full_page=True)
     report['cases'].append({'case':kind,'result':'PASS','events':events,'dialogs':dialogs,'downloads':downloads,'steps':steps,'ui_event_batches':ui_batches,'ui_events':page.evaluate('window.__uiEventLog')})
    except Exception:
     report['cases'].append({'case':kind,'result':'FAIL','error':traceback.format_exc(),'page_errors':errors,'events':events,'dialogs':dialogs,'steps':steps,'ui_event_batches':ui_batches,'ui_events':page.evaluate('window.__uiEventLog')})
     try:page.screenshot(path=str(out/(kind+'-failure.png')),full_page=True)
     except Exception:pass
    finally:ctx.close()
   browser.close()
  report['candidate_sha256_after']=hashlib.sha256((pathlib.Path(a.candidate_root)/'index.html').read_bytes()).hexdigest();need(report['candidate_sha256_after']==EXPECTED,'candidate modified')
  need(not report['requests_blocked'],'unexpected network request was blocked');need(len(report['cases'])==3 and all(x['result']=='PASS' for x in report['cases']),'one or more cases failed');report['result']='PASS'
 except Exception:report['result']='FAIL';report['error']=traceback.format_exc()
 finally:
  if server:server.shutdown();server.server_close()
  (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
