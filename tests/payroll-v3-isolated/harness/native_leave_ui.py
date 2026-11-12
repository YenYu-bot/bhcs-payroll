#!/usr/bin/env python3
"""Synthetic leave UI tests. No function/source replacement, production data or Firebase.
Require non-root, sandboxed Chromium and externally established loopback-only namespace.
Native print-media/PDF pipeline is tested; not an OS print-dialog automation claim.
"""
import argparse, hashlib, json, os, pathlib, socket, threading, traceback, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
EXPECTED='ff5399e07c7e023de6db13c3983acec5d991d82de54e25782109851a7ea64782'
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
 const e={id:'synthetic-review',name:'特休隔離合成人員',payType:'monthly',base:36000,rate:200,
 hire:'2024-01-01',leave:'2026-01-30',labor:0,health:0,perfect:0,summer:0,otFixed:0,fixedItems:[],
 pensionWage:0,pensionSelf:0,sched:defaultSched(),hourBasis:'punch',hourRound:0,
 brkMin:0,brkAfter:0,leaveSystem:'cal',yearEnd:'defer',lateePolicy:'deduct',lateGrace:0,lateUnit:0};
 for(let i=1;i<=5;i++){e.sched['d'+i].start='09:00';e.sched['d'+i].end='17:00';}
 const old=blankRec(),r=blankRec();let months={'2025-12':{[e.id]:old},'2026-01':{[e.id]:r}};
 if(kind==='sources'){
  Object.assign(e,{hire:'2026-01-01',leave:'',leaveSystem:'anniv',yearEnd:'pay'});
  r.annualEvents=[{date:'2026-03-02',hours:2}];r.days=[{date:'2026-03-02',wk:wkOf('2026-03-02'),status:'annual',hours:2}];
  r.absChoice={'2026-03-02':{type:'annual',hours:4}};months={'2026-03':{[e.id]:r}};
 }
 if(kind==='negative'){
  Object.assign(e,{hire:'2025-01-01',leave:'',leaveSystem:'cal',yearEnd:'pay'});
  r.annualEvents=[{date:'2026-12-01',hours:64}];months={'2026-12':{[e.id]:r}};
 }
 if(kind==='december'){
  Object.assign(e,{hire:'2025-01-01',leave:'2026-12-31'});months={'2026-12':{[e.id]:r}};
 }
 return {version:3,settings:DEF_SETTINGS(),employees:[e],months,log:[]};
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
   for kind in ['basis','sources','negative','december']:
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
     month={'basis':'1','sources':'3','negative':'12','december':'12'}[kind]
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
     if kind=='basis':
      need(page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'missing basis must block')
      expect(page.locator('.slip-foot .lbl')).to_contain_text('不可付款')
      need(money('特休未休工資')=='12000','draft current-year amount only, missing carry not guessed')
      approve_all();confirm_click();need(not page.evaluate("mrec('synthetic-review').confirmed"),'approveAll bypassed missing basis');mark('missing_basis_confirmation_blocked')
      for fn in ['exportExcel()','exportWord()','printPayroll()']:
       page.locator('button[onclick="'+fn+'"]').click();page.wait_for_timeout(100)
      need(not downloads,'blocked outputs produced download');need(page.evaluate('window.__printEvents.length')==0,'blocked system print reached print');mark('blocked_export_and_system_print')
      page.emulate_media(media='print')
      need(page.locator('.slip').evaluate("e=>getComputedStyle(e,'::before').content").find('不可付款')>=0,'print CSS missing blocker notice')
      need(page.locator('.slip').evaluate("e=>Array.from(e.children).every(x=>getComputedStyle(x).display==='none')"),'print CSS leaked payroll children')
      page.pdf(path=str(out/'blocked-payroll.pdf'),print_background=True)
      page.emulate_media(media='screen');mark('native_print_media_pdf_block_notice')
      dialog_queue.extend([('prompt','0')]);page.get_by_role('button',name='核對／更正原年度基準',exact=True).click();need(not dialog_queue,'zero prompt not shown');need(page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'zero accepted');mark('zero_basis_rejected')
      dialog_queue.extend([('prompt','1000'),('prompt','合成原年度薪資單：正常日薪1000，已核對遞延7日'),('confirm','yes')]);page.get_by_role('button',name='核對／更正原年度基準',exact=True).click();save_done();need(not dialog_queue,'basis dialogs incomplete')
      need(money('特休未休工資')=='19000','7*1000+10*1200 expected19000');need(not page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'verified basis still blocked');mark('native_basis_dialog_19000')
      reload_slip();need(money('特休未休工資')=='19000','basis lost after native IDB reload');need(page.evaluate("Object.values(emp('synthetic-review').leaveWageBases)[0].dayWage")==1000,'stored basis missing');mark('basis_survives_native_idb')
      approve_all();need(page.evaluate("compute(emp('synthetic-review')).pendingReviews")==0,'reviews not cleared')
      dialog_queue.extend([('prompt','1000'),('prompt','同額重新核對合成來源'),('confirm','yes')]);page.get_by_role('button',name='核對／更正原年度基準',exact=True).click();save_done()
      need(page.evaluate("compute(emp('synthetic-review')).reviews.find(x=>x.key==='annualPay').st")=='pending','same amount basis revision did not invalidate review');mark('basis_revision_invalidates')
      approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'basis confirmation failed')
      snapshot=page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)")
      # Deliberate synthetic source mutation tests the locked snapshot path, not normal editing UI.
      page.evaluate("async()=>{emp('synthetic-review').base=90000;await save();renderSlips();}")
      need(money('特休未休工資')=='19000','confirmed snapshot recalculated');reload_slip();need(page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)")==snapshot,'snapshot changed across IDB reload');mark('confirmed_snapshot_immutable')
     elif kind=='sources':
      key='annualSources:2026-03-02';need(page.evaluate("compute(emp('synthetic-review')).annualLeft")==-1,'split whole shift not advanced')
      need(page.evaluate("JSON.parse(compute(emp('synthetic-review')).reviews.find(x=>x.key==='"+key+"').sig).records.map(x=>x[0]).sort().join(',')")=='absence,calendar,manual','three sources not distinguished')
      approve_all();confirm_click();need(not page.evaluate("mrec('synthetic-review').confirmed"),'approveAll bypassed source ack');review(key,'ok');mark('individual_ack_required')
      step('manual_edit_open');page.locator('.step[data-v="att"]').click();page.locator('button[onclick="openDet(\'synthetic-review\',\'annual\')"]').click();mark('manual_edit_open')
      step('manual_edit_fill');field=page.locator('#detWrap input[onchange="editDet(0,\'hours\',this.value)"]');field.fill('3');mark('manual_edit_fill')
      step('manual_edit_natural_tab');field.press('Tab');save_done();mark('manual_edit_natural_tab');need(page.evaluate("window.__uiEventLog.filter(x=>x.step==='manual_edit_natural_tab'&&x.type==='change'&&x.target?.change===\"editDet(0,'hours',this.value)\").length")==1,'manual natural commit must emit exactly one change');need(not errors,'error during natural manual change '+repr(errors))
      step('manual_edit_close');page.locator('#detModal button[onclick="closeDet()"]').first.click();save_done();mark('manual_edit_close')
      step('calendar_edit_open');page.locator('button[onclick="openDet(\'synthetic-review\',\'day\')"]').click();mark('calendar_edit_open')
      step('calendar_edit_fill');field=page.locator('#detWrap input[onchange="editDet(0,\'hours\',this.value)"]');field.fill('1');mark('calendar_edit_fill')
      step('calendar_edit_natural_mouse_blur');page.locator('#detTitle').click();save_done();mark('calendar_edit_natural_mouse_blur');need(page.evaluate("window.__uiEventLog.filter(x=>x.step==='calendar_edit_natural_mouse_blur'&&x.type==='change'&&x.target?.change===\"editDet(0,'hours',this.value)\").length")==1,'calendar natural commit must emit exactly one change');need(not errors,'error during natural calendar change '+repr(errors))
      step('calendar_edit_close');page.locator('#detModal button[onclick="closeDet()"]').first.click();save_done();mark('calendar_edit_close');select_slip()
      need(page.evaluate("compute(emp('synthetic-review')).annualLeft")==-1,'same aggregate leave unexpectedly changed')
      need(page.evaluate("compute(emp('synthetic-review')).reviews.find(x=>x.key==='"+key+"').st")=='pending','source changes with unchanged total not invalidated');mark('actual_dom_edit_invalidates_ack')
      review(key,'ok');approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'reviewed source did not confirm');reload_slip();need(page.evaluate("compute(emp('synthetic-review')).locked"),'source confirmation not stored');mark('source_ack_confirmed_native_idb')
     elif kind=='negative':
      approve_all();review('annualSources:2026-12-01','ok');review('annualNeg','carry');need(page.evaluate("compute(emp('synthetic-review')).reviews.find(x=>x.key==='annualNeg').st")=='carry','carry failed')
      review('annualNeg','waive');need(page.evaluate("compute(emp('synthetic-review')).reviews.find(x=>x.key==='annualNeg').st")=='waive','waive failed');confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'negative decision confirmation failed');reload_slip();need(page.evaluate("compute(emp('synthetic-review')).locked"),'negative snapshot lost');mark('native_carry_waive_no_referenceerror')
     else:
      need(money('特休未休工資')=='8400','Dec31 own7*1200 must settle, not defer and lose');need(not page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'no historic carry should not require basis');approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'Dec31 confirmation failed');mark('dec31_defer_termination')
     need(not errors,'page errors '+repr(errors));need(not dialog_queue,'unconsumed dialogs');page.wait_for_timeout(300);page.screenshot(path=str(out/(kind+'.png')),full_page=True)
     report['cases'].append({'case':kind,'result':'PASS','events':events,'dialogs':dialogs,'downloads':downloads,'steps':steps,'ui_event_batches':ui_batches,'ui_events':page.evaluate('window.__uiEventLog')})
    except Exception:
     report['cases'].append({'case':kind,'result':'FAIL','error':traceback.format_exc(),'page_errors':errors,'events':events,'dialogs':dialogs,'steps':steps,'ui_event_batches':ui_batches,'ui_events':page.evaluate('window.__uiEventLog')})
     try:page.screenshot(path=str(out/(kind+'-failure.png')),full_page=True)
     except Exception:pass
    finally:ctx.close()
   browser.close()
  report['candidate_sha256_after']=hashlib.sha256((pathlib.Path(a.candidate_root)/'index.html').read_bytes()).hexdigest();need(report['candidate_sha256_after']==EXPECTED,'candidate modified')
  need(not report['requests_blocked'],'unexpected network request was blocked');need(len(report['cases'])==4 and all(x['result']=='PASS' for x in report['cases']),'one or more cases failed');report['result']='PASS'
 except Exception:report['result']='FAIL';report['error']=traceback.format_exc()
 finally:
  if server:server.shutdown();server.server_close()
  (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
