#!/usr/bin/env python3
"""Synthetic leave UI tests. No function/source replacement, production data or Firebase.
Require non-root, sandboxed Chromium and externally established loopback-only namespace.
Native print-media/PDF pipeline is tested; not an OS print-dialog automation claim.
"""
import argparse, hashlib, json, os, pathlib, socket, threading, traceback, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
EXPECTED='dd0c88ea87a0837fb21da38e903b4aa68783fab9d01b9c87a15b12c7a6b6d58c'
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
 const e={id:'synthetic-review',name:'請假隔離合成人員',payType:'monthly',base:30000,rate:200,
 hire:'2024-01-01',leave:'',labor:0,health:0,perfect:3000,summer:0,otFixed:0,fixedItems:[],
 pensionWage:0,pensionSelf:0,sched:defaultSched(),hourBasis:'punch',hourRound:0,
 brkMin:0,brkAfter:0,leaveSystem:'cal',yearEnd:'pay',lateePolicy:'deduct',lateGrace:0,lateUnit:0};
 for(let i=0;i<7;i++)e.sched['d'+i]={type:'work',start:'09:00',end:'17:00'};
 const r=blankRec();let months={'2026-11':{[e.id]:r}};
 if(kind==='q10'||kind==='floor')r.att.sick=8;
 if(kind==='floor')e.base=26500;
 if(kind==='protected')r.days=[{date:'2026-11-02',wk:'一',status:'protectedSick',hours:8},{date:'2026-11-03',wk:'二',status:'carePersonal',hours:8}];
 if(kind.startsWith('menstrual')){
  Object.assign(e,{payType:'hourly',rate:200,ptRatio:.5,perfect:0});
  for(let i=0;i<7;i++)e.sched['d'+i].end='13:00';
  for(const m of ['08','09','10']){const prior=blankRec();prior.days=[{date:'2026-'+m+'-03',wk:wkOf('2026-'+m+'-03'),status:'menstrual',hours:4}];months['2026-'+m]={[e.id]:prior};}
  months['2026-08'][e.id].att.sick=120;
  if(kind==='menstrual')r.days=[{date:'2026-11-03',wk:'二',status:'menstrual',hours:4}];else r.att.menstrual=4;
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
   for kind in ['q10','protected','floor','menstrual','menstrual_missing']:
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
     if kind=='q10':
      need(net()==32352,'Q10 net32352');need(money('病假扣薪')=='548','actual attendance day wage');mark('official_q10_32352')
      step('q10_native_sick_edit');page.locator('.step[data-v="att"]').click()
      field=page.locator("input[oninput=\"setAtt('synthetic-review','sick',this.value)\"]");field.fill('4');field.press('Tab');save_done();select_slip()
      need(net()==32675,'half day sick net32675');need(money('全勤獎金')=='2950','half day attendance2950');reload_slip();need(net()==32675,'changed leave lost on IDB reload');mark('native_sick_edit_idb')
      approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'q10 confirm failed');snapshot=page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)")
      page.evaluate("async()=>{emp('synthetic-review').base=90000;await save();renderSlips();}");reload_slip();need(page.evaluate("JSON.stringify(mrec('synthetic-review').snapshot)")==snapshot and net()==32675,'confirmed snapshot changed');mark('confirmed_snapshot_immutable')
     elif kind=='protected':
      need(net()==31350 and money('全勤獎金')=='3000','protected categories failed');mark('protected_calendar_sources')
      step('protected_native_extra');page.locator('.step[data-v="att"]').click()
      field=page.locator("input[oninput=\"setAtt('synthetic-review','protectedSick',this.value)\"]");field.fill('4');field.press('Tab');save_done();select_slip()
      need(net()==31075 and money('全勤獎金')=='3000','protected field altered attendance');reload_slip();need(net()==31075,'protected field lost on IDB reload');mark('protected_native_field_persistence')
      approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'protected confirm failed');reload_slip();need(page.evaluate("compute(emp('synthetic-review')).locked"),'protected snapshot not stored')
     elif kind=='floor':
      need(net()==29009 and money('病假最低工資補足')=='99','Q5 floor initial');approve_all();confirm_click();need(not page.evaluate("mrec('synthetic-review').confirmed"),'batch bypassed individual floor ack');blocked_outputs();mark('floor_pending_blocks_all_outputs')
      page.emulate_media(media='print');print_reason=page.locator('.slip').evaluate("e=>getComputedStyle(e,'::before').content");need('病假最低工資' in print_reason and '原年度特休' not in print_reason,'wrong floor print reason');need(page.locator('#toast').evaluate("e=>getComputedStyle(e).display")=='none','toast leaked into print');need(page.locator('.slip').evaluate("e=>Array.from(e.children).every(x=>getComputedStyle(x).display==='none')"),'floor print leaked payroll fields');page.pdf(path=str(out/'floor-blocked.pdf'),print_background=True);page.emulate_media(media='screen')
      review('sickFloor','ok');need(not page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'individual ack did not unblock');mark('individual_floor_ack')
      step('actual_perfect_override');field=page.locator('input[data-lb="全勤獎金"]');field.fill('3000');field.press('Tab');save_done()
      need(net()==29009 and money('病假最低工資補足')=='1','override must recompute floor1');need(page.evaluate("compute(emp('synthetic-review')).reviews.find(x=>x.key==='sickFloor').st")=='pending','override did not invalidate floor ack');blocked_outputs();need(page.evaluate("compute(emp('synthetic-review')).perfectNote").find('不再另扣')>=0,'override note still misleading');need(page.locator('.rv-tbl').inner_text().find('已覆寫，不另扣薪')>=0,'review label misleading');mark('native_override_recalculates_and_invalidates')
      reload_slip();need(net()==29009 and money('病假最低工資補足')=='1','override lost on IDB reload');review('sickFloor','ok');approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'reviewed floor failed confirmation');reload_slip();need(page.evaluate("compute(emp('synthetic-review')).locked"),'floor snapshot lost');mark('floor_confirmation_native_idb')
     elif kind=='menstrual':
      need(net()==0,'fourth full4h calendar day must be unpaid at exhausted cap');need(page.evaluate("leaveText(compute(emp('synthetic-review')))").find('15 日（120 小時）')>=0,'wrong parttime cap text');need(not page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'dated full shifts incorrectly blocked');approve_all();confirm_click();need(page.evaluate("mrec('synthetic-review').confirmed"),'dated menstrual confirm failed');reload_slip();need(net()==0 and page.evaluate("compute(emp('synthetic-review')).locked"),'menstrual snapshot not stored');mark('parttime_fourth_actual_day')
     else:
      need(page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'undated menstrual guessed');approve_all();confirm_click();need(not page.evaluate("mrec('synthetic-review').confirmed"),'undated menstrual confirmed');blocked_outputs();reload_slip();need(page.evaluate("compute(emp('synthetic-review')).settlementBlocked"),'missing date blocker lost on reload');mark('undated_menstrual_never_guessed')
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
