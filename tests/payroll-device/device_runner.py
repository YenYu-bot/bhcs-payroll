#!/usr/bin/env python3
"""Synthetic, local-only backup/migration acceptance on real sandboxed Chromium.
No Firebase SDK/emulator, no production sign-in. Run inside the existing no-uplink
network namespace after sandbox_gate.py, under supervise.py. Does not edit app.
"""
import argparse, copy, hashlib, json, os, sys, time, traceback
from pathlib import Path
from urllib.parse import urlsplit

APP_SHA = '1689c2a585a54849be4fa09f607e482d5184dfbb70398ffc3ac50f77ede21586'
PW = 'synthetic-migration-only-password'
# Independent implementation of documented backup envelope, not candidate encStr.
ENCRYPT = """async ([obj,pw])=>{const e=new TextEncoder(),b=a=>btoa(String.fromCharCode(...a));
 const salt=crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
 const k0=await crypto.subtle.importKey('raw',e.encode(pw),'PBKDF2',false,['deriveKey']);
 const k=await crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:250000,hash:'SHA-256'},k0,{name:'AES-GCM',length:256},false,['encrypt']);
 return {bhcsEnc:1,salt:b(salt),iv:b(iv),ct:b(new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},k,e.encode(JSON.stringify(obj)))))};}"""
FIXED_DATE = """(()=>{const Real=Date;class Fixed extends Real {constructor(...a){super(...(a.length?a:['2026-11-12T08:00:00.000Z']));}static now(){return Real.parse('2026-11-12T08:00:00.000Z');}}window.Date=Fixed;})();"""

def need(ok, msg):
    if not ok: raise AssertionError(msg)
def wait(p,expression,timeout=45000):
    deadline=time.monotonic()+timeout/1000
    while time.monotonic()<deadline:
        if p.evaluate('()=>Boolean('+expression+')'):return
        p.wait_for_timeout(50)
    raise AssertionError('Timed out waiting for '+expression)

def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def payload(obj, name='synthetic.json'):
    return {'name':name,'mimeType':'application/json','buffer':(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False)).encode()}
def root(p): return p.evaluate('__bsdk.read()')
def state_on_disk(p):
    r=root(p); need(r is not None,'root absent')
    return json.loads(r['values']['bhcs_payroll_device_test_v3'])
def page(env,ctx):
    p=ctx.new_page();p.goto(env.srv.base+"/app/",wait_until="domcontentloaded")
    wait(p,"typeof cloud!=='undefined' && typeof load==='function'")
    wait(p,'localDB.db!==null || localDB.failed!==null')
    need(p.evaluate('localDB.failed===null'),'storage open failed')
    return p

def context(env,name,**kwargs):
    # No WebSocket interception: exercise native CSP. OS netns has no uplink.
    c=env.b.new_context(service_workers='block',accept_downloads=True,timezone_id='UTC',locale='zh-TW',**kwargs)
    env.contexts.append(c)
    def route(r):
        u=urlsplit(r.request.url);ok=u.scheme=='http' and u.hostname=='127.0.0.1' and u.port==env.srv.port
        env.log({'kind':'route','ctx':name,'decision':'ALLOW' if ok else 'BLOCK','origin':u.scheme+'://'+u.netloc,'path':u.path})
        r.continue_() if ok else r.abort('blockedbyclient')
    c.route('**/*',route)
    c.add_init_script(script='window.__BSDK_NO_FB_GUARD=true;'+env.h.HOOKS)
    c.add_init_script(script=FIXED_DATE)
    c.dialogs=[];c.policy=lambda d:True;c.errors=[]
    def wire(pg):
        def dlg(d):
            c.dialogs.append({'type':d.type,'message':d.message[:160]})
            d.accept() if c.policy(d) else d.dismiss()
        pg.on('dialog',dlg);pg.on('pageerror',lambda e:c.errors.append(str(e)[:300]));pg.set_default_timeout(45000)
    c.on('page',wire)
    return c

def setup(p,obj):
    # Observe completion of the real UI file input handler, preserving its implementation.
    p.evaluate("()=>{const o=window.initializeFromBackup;window.initializeFromBackup=async function(...a){window.__migSetup={done:false};try{const v=await o.apply(this,a);window.__migSetup={done:true,result:v};return v;}catch(e){window.__migSetup={done:true,error:String(e)};throw e;}};}")
    p.set_input_files('input[onchange="initializeFromBackup(this)"]',payload(obj))
    wait(p,'window.__migSetup && __migSetup.done',timeout=60000)
    return p.evaluate('__migSetup')

def import_file(p,obj):
    p.evaluate("()=>{window.__migImport={done:false};const orig=window.dataOp;window.dataOp=function(...a){const promise=orig.apply(this,a);return promise.then(v=>{window.__migImport={done:true,result:v};return v;},e=>{window.__migImport={done:true,error:String(e)};throw e;});};}")
    p.set_input_files('input[onchange="importData(this)"]',payload(obj))
    wait(p,'window.__migImport.done',timeout=60000)
    env_result=p.evaluate('__migImport')
    wait(p,'persistence.operations===0 && persistence.pending===0')
    return env_result

def init_legacy(env):
    c=context(env,'M01-v2');p=page(env,c)
    old={'version':2,'settings':{'absUnit':30,'fixtureMarker':'V2-SYNTHETIC'},'employees':[{'id':'OLD1','name':'虛構遷移甲','base':36000,'payType':'monthly','hire':'2024-01-01','annual':9,'voidSick':True,'hourly':210,'daily':1200,'fixedItems':[{'name':'虛構津貼','amount':321,'type':'add'}]}],
      'monthly':{'OLD1':{'att':{'sick':1.5,'personal':0.25,'restHours':10.5,'annualUsed':0.5},'lateEvents':[{'date':'2026-10-02','minutes':11}],'otherBonus':123,'otherDeduct':45,'overrides':{'休息日出勤加班費':999,'虛構保留欄位':17}}}}
    # Start from known renderable synthetic employee fields, then override documented v2 inputs.
    old['employees'][0]={**copy.deepcopy(env.fixture['employees'][0]),**old['employees'][0]}
    need(setup(p,old).get('result') is True,'v2 setup failed')
    d=state_on_disk(p);e=d['employees'][0];r=d['months']['2026-10']['OLD1']
    need(d['version']==3 and d['settings']['fixtureMarker']=='V2-SYNTHETIC','version/settings lost')
    need(e['name']=='虛構遷移甲' and e['base']==36000 and e['fixedItems']==old['employees'][0]['fixedItems'],'employee data lost')
    need(all(k not in e for k in ['annual','voidSick','hourly','daily']),'obsolete v2 fields remain')
    need(e['leaveSystem']=='anniv' and e['priorUsed']==0 and e['priorAsOf']=='','documented migration defaults wrong')
    need(r['att']['sick']==12 and r['att']['personal']==2,'day/hour migration wrong')
    need(r['otEvents']==[{'date':'','type':'rest','hours':8},{'date':'','type':'rest','hours':2.5}],'rest chunks wrong')
    need(r['annualEvents']==[{'date':'2026-10-01','hours':4}],'annual event wrong')
    need(r['lateEvents']==old['monthly']['OLD1']['lateEvents'] and r['otherBonus']==123 and r['otherDeduct']==45,'month values lost')
    need(r['overrides']=={'加班費':999,'虛構保留欄位':17},'override mapping wrong')
    need(r['confirmed'] is False and r['snapshot'] is None,'invented confirmation')
    return {'rootDigest':digest(root(p)),'month':'2026-10','note':'Explicit documented v2 conversion; not legal correctness of migration defaults.'}

def v3_preserve(env):
    c=context(env,'M02-v3');p=page(env,c);fixture=copy.deepcopy(env.fixture)
    need(setup(p,fixture).get('result') is True,'setup fail');d=state_on_disk(p)
    for k in ('employees','months'):need(d[k]==fixture[k],k+' changed')
    before=root(p);p.reload(wait_until='domcontentloaded');wait(p,'localDB.ready');need(root(p)==before,'reload wrote root')
    need(p.evaluate('state.months')==fixture['months'],'reload mutated historical snapshots')
    return {'months':sorted(fixture['months']),'confirmedSnapshotDigest':digest(fixture['months']['2026-09']['E1']['snapshot']),'rootDigest':digest(before)}

def first_rejections(env):
    outcomes=[]
    for typ in ['cancel','bad-password','malformed','unknown-version']:
        c=context(env,'M03-'+typ);p=page(env,c);obj=copy.deepcopy(env.fixture)
        if typ=='cancel':c.policy=lambda d:False
        if typ=='bad-password':
            obj=p.evaluate(ENCRYPT,[obj,PW]);p.fill('#storageSetupPass','incorrect-synthetic-password')
        if typ=='malformed':obj='{this is not JSON'
        if typ=='unknown-version':obj['version']=999
        result=setup(p,obj);need(result.get('result') is False,'invalid setup succeeded '+typ)
        need(root(p) is None,'invalid setup wrote root '+typ);need(not p.evaluate('localDB.ready'),'invalid setup ready '+typ)
        outcomes.append({'kind':typ,'rootAbsent':True,'message':p.locator('#storageSetupMsg').inner_text()})
    return {'variants':outcomes}

def first_race(env):
    c=context(env,'M04-first-race');p=page(env,c);q=page(env,c)
    need(root(p) is None and root(q) is None,'not empty')
    # Gate both app initialization calls before their actual native CAS; then allow both.
    for pg in (p,q):pg.evaluate("()=>{const o=window.initializeStorage;window.__initGate={reached:false};window.__initGate.p=new Promise(r=>window.__initGate.release=r);window.initializeStorage=async function(...a){window.__initGate.reached=true;await window.__initGate.p;return o.apply(this,a);};}")
    a=copy.deepcopy(env.fixture);b=copy.deepcopy(a);a['settings']['fixtureMarker']='FIRST-A';b['settings']['fixtureMarker']='FIRST-B'
    for pg,obj in [(p,a),(q,b)]:
        pg.evaluate("(obj)=>{window.__firstResult={done:false};initializeFromBackup({files:[new File([JSON.stringify(obj)],'synthetic.json',{type:'application/json'})],value:'x'}).then(v=>window.__firstResult={done:true,result:v});}",obj)
        wait(pg,'__initGate.reached')
    for pg in (p,q):pg.evaluate('__initGate.release()')
    for pg in (p,q):wait(pg,'__firstResult.done')
    results=[pg.evaluate('__firstResult.result') for pg in (p,q)];need(results.count(True)==1 and results.count(False)==1,'initializations did not yield exactly one winner')
    rec=root(p);need(rec['revision']==1,'bootstrap increment wrong');d=json.loads(rec['values']['bhcs_payroll_device_test_v3'])
    expected=a if results[0] else b
    need(d['settings']['fixtureMarker']==expected['settings']['fixtureMarker'] and d['months']==expected['months'],'winner data mismatch')
    return {'results':results,'revision':rec['revision'],'rootDigest':digest(rec),'note':'Both initializers gated before native CAS; no claim of transaction-overlap proof.'}

def existing_rejections(env):
    outcomes=[]
    for typ in ['cancel','bad-password','malformed','unknown-version']:
        c=context(env,'M05-'+typ);p=page(env,c);need(setup(p,env.fixture).get('result') is True,'setup fail');before=root(p);before_ram=p.evaluate('JSON.stringify(state)');obj=copy.deepcopy(env.fixture)
        if typ=='cancel':c.policy=lambda d:False
        if typ=='bad-password':
            obj=p.evaluate(ENCRYPT,[obj,PW])
            # Inject only the custom password-dialog answer; exercise actual file input, decryption and persistence.
            p.evaluate("()=>{window.__passObserved=false;const o=window.askPass;window.askPass=function(...a){window.__passObserved=true;return Promise.resolve('incorrect-synthetic-password');};}")
        if typ=='malformed':obj='bad json'
        if typ=='unknown-version':obj['version']=999
        result=import_file(p,obj)
        if typ=='cancel':need(result.get('result') is False,'cancel not observed')
        else:need(bool(result.get('error')),'rejection path not observed '+typ)
        if typ=='bad-password':need(p.evaluate('__passObserved'),'password prompt boundary not reached')
        need(root(p)==before,'rejected import changed root '+typ);need(p.evaluate('JSON.stringify(state)')==before_ram,'rejected import changed RAM '+typ)
        outcomes.append({'kind':typ,'result':result,'rootUnchanged':True})
    return {'variants':outcomes,'note':'Wrong-password input injected at askPass boundary; file input/crypto/persistence are real.'}

def legacy_retention(env):
    c=context(env,'M06-legacy');p=page(env,c);legacy='synthetic-legacy-not-authoritative'
    p.evaluate('(s)=>localStorage.setItem(KEY,s)',legacy)
    need(setup(p,env.fixture).get('result') is True,'setup fail');before=root(p)
    need(p.evaluate('localStorage.getItem(KEY)')==legacy,'setup deleted legacy')
    q=c.new_page();q.goto(env.srv.base+'/observer');q.evaluate("()=>localStorage.setItem('bhcs_payroll_device_test_v3','synthetic-new-legacy-write')")
    wait(p,"cloud.conflict===true")
    need(root(p)==before,'legacy writer changed root');p.reload(wait_until='domcontentloaded');wait(p,'localDB.ready')
    need(root(p)==before,'reload migrated newer localStorage');need(p.evaluate('state.settings.fixtureMarker')=='FIXTURE-A','canonical state replaced')
    need(p.evaluate("localStorage.getItem(KEY)")=='synthetic-new-legacy-write','legacy content removed')
    return {'rootUnchanged':True,'legacyRetained':True,'note':'Same-origin legacy localStorage only; no old-version cloud client is run.'}


def narrow_encrypted_roundtrip(env):
    c=context(env,'M07-narrow-encrypted',viewport={'width':390,'height':844});p=page(env,c)
    packet=p.evaluate(ENCRYPT,[env.fixture,PW])
    box=p.locator('#storageSetupPass').bounding_box()
    need(box is not None and box['x']>=0 and box['x']+box['width']<=390,'password field outside viewport')
    p.fill('#storageSetupPass',PW)
    need(setup(p,packet).get('result') is True,'encrypted setup failed')
    need(p.evaluate('sec.locked'),'encrypted startup did not lock')
    p.fill('#lockPass',PW);p.click('#lockUnlock');wait(p,'!sec.locked && persistence.operations===0',timeout=60000)
    need(p.evaluate('state.months')==env.fixture['months'],'encrypted import changed snapshots')
    with p.expect_download() as download_wait:
        p.evaluate('exportData()')
    download=download_wait.value;body=json.loads(Path(download.path()).read_text())
    need(body.get('bhcsEnc')==1,'export not encrypted')
    decoded=json.loads(p.evaluate('(a)=>__bsdk.decrypt(...a)',[body,PW,body['salt']]))
    need(decoded['months']==env.fixture['months'] and decoded['employees']==env.fixture['employees'],'export core mismatch')
    c2=context(env,'M07-import-exported',viewport={'width':390,'height':844});q=page(env,c2)
    q.fill('#storageSetupPass',PW);need(setup(q,body).get('result') is True,'downloaded backup import failed')
    q.fill('#lockPass',PW);q.click('#lockUnlock');wait(q,'!sec.locked && persistence.operations===0',timeout=60000)
    need(q.evaluate('state.months')==env.fixture['months'],'download-import roundtrip changed snapshots')
    r=root(q);need(r['values']['bhcs_payroll_device_test_v3'] is None and r['values']['bhcs_payroll_device_test_v3_enc'] is not None,'cipher/plain placement invalid')
    return {'viewport':{'width':390,'height':844},'passwordField':box,'snapshotDigest':digest(env.fixture['months']),'downloadedBackupEncrypted':True,'note':'Desktop Chromium viewport only, NOT Android or Samsung device verification.'}

def device_security(env):
    c=context(env,'D01-security')
    observer=c.new_page();observer.goto(env.srv.base+'/observer')
    observer.evaluate("""async()=>{localStorage.setItem('bhcs_payroll_v3','SYNTHETIC-PRODUCTION-SENTINEL');await new Promise((res,rej)=>{let r=indexedDB.open('bhcs-payroll-safe-storage',1);r.onupgradeneeded=()=>r.result.createObjectStore('state');r.onerror=()=>rej(r.error);r.onsuccess=()=>{let db=r.result,t=db.transaction('state','readwrite');t.objectStore('state').put({syntheticSentinel:'DO-NOT-TOUCH'},'root');t.oncomplete=()=>{db.close();res()};t.onabort=()=>rej(t.error)}})}""")
    p=page(env,c)
    cfg=p.evaluate('JSON.stringify(FB_CONFIG)');need(cfg=='{}','production config not empty')
    msg=p.evaluate("async()=>{try{await fbLoad();return 'UNEXPECTED'}catch(e){return e.message}}")
    need('雲端功能已停用' in msg,'cloud loader did not reject')
    route_start=len(env.records)
    result=p.evaluate("""async()=>{window.__viol=[];document.addEventListener('securitypolicyviolation',e=>__viol.push({directive:e.effectiveDirective,uri:e.blockedURI}));let fetchBlocked=false;try{await fetch('https://example.invalid/device-test')}catch(e){fetchBlocked=true;}let wsBlocked=await new Promise(res=>{try{let w=new WebSocket('wss://example.invalid/device-test');w.onerror=()=>res(true);w.onopen=()=>{w.close();res(false)};setTimeout(()=>res(false),1000)}catch(e){res(true)}});const el=document.createElement('script');el.src='https://example.invalid/device-test.js';document.head.append(el);await new Promise(r=>setTimeout(r,250));return {fetchBlocked,wsBlocked,violations:__viol};}""")
    remote=[r for r in env.records[route_start:] if r.get('kind')=='route' and 'example.invalid' in r.get('origin','')]
    need(not remote,'external probe escaped CSP and reached routing guard')
    need(result['fetchBlocked'],'fetch unexpectedly succeeded')
    need(result['wsBlocked'],'websocket did not reject')
    need(any(x['directive']=='connect-src' and x['uri'].startswith('wss://example.invalid') for x in result['violations']),'WebSocket-specific CSP violation absent')
    dirs={x['directive'] for x in result['violations']}
    need('connect-src' in dirs and any(x.startswith('script-src') for x in dirs),'CSP not enforced')
    need(setup(p,env.fixture).get('result') is True,'setup failed')
    databases=p.evaluate('indexedDB.databases()');need({d['name'] for d in databases}=={'bhcs-payroll-device-test-storage','bhcs-payroll-safe-storage'},'unexpected DB namespace')
    need(p.evaluate('storageKeys().every(k=>k.startsWith("bhcs_payroll_device_test_"))'),'unexpected keys')
    need(p.evaluate('JSON.stringify(localStorage)')=='{"bhcs_payroll_v3":"SYNTHETIC-PRODUCTION-SENTINEL"}','original localStorage changed')
    sentinel=p.evaluate("""async()=>await new Promise((res,rej)=>{let r=indexedDB.open('bhcs-payroll-safe-storage',1);r.onsuccess=()=>{let db=r.result,t=db.transaction('state','readonly'),g=t.objectStore('state').get('root');g.onsuccess=()=>{res(g.result);db.close()};g.onerror=()=>rej(g.error)}})""")
    need(sentinel=={'syntheticSentinel':'DO-NOT-TOUCH'},'original DB changed')
    return {'cloudRejected':msg,'csp':result,'databases':databases,'storageNamespace':'isolated'}

def supplied_fixture(env):
    c=context(env,'D05-supplied-backup');p=page(env,c)
    packet=json.loads((Path(env.device_root)/'synthetic-encrypted.json').read_text())
    pw='DeviceTest-Only-2026'
    p.fill('#storageSetupPass',pw);need(setup(p,packet).get('result') is True,'supplied encrypted fixture import failed')
    p.fill('#lockPass',pw);p.click('#lockUnlock');wait(p,'!sec.locked && persistence.operations===0',timeout=60000)
    for k in ['settings','employees','months']:need(p.evaluate('state['+json.dumps(k)+']')==env.fixture[k],'supplied fixture differs '+k)
    return {'suppliedBackup':'synthetic-encrypted.json','contentMatchesPlainFixture':True}

CASES=[('D01-security',device_security),('D02-first-rejections',first_rejections),('D03-existing-rejections',existing_rejections),('D04-encrypted-roundtrip-390px',narrow_encrypted_roundtrip),('D05-supplied-backup',supplied_fixture)]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--candidate-root',required=True);ap.add_argument('--harness-dir',required=True);ap.add_argument('--output',required=True);ap.add_argument('--case',action='append',default=[]);a=ap.parse_args()
    sys.path.insert(0,str(Path(a.harness_dir).resolve()));import bsdk_runner as h
    h.HOOKS=h.HOOKS.replace('bhcs-payroll-safe-storage','bhcs-payroll-device-test-storage').replace('bhcs_payroll_','bhcs_payroll_device_test_')
    if os.geteuid()==0:raise SystemExit('Refusing root browser launch')
    selected=[(n,f) for n,f in CASES if not a.case or any(n.startswith(s) for s in a.case)]
    if not selected:raise SystemExit(2)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False);records=[]
    def log(r):
        records.append(r)
        with (out/'results.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    app_path=Path(a.candidate_root)/'index.html';app=app_path.read_bytes();need(hashlib.sha256(app).hexdigest()==APP_SHA,'candidate SHA mismatch')
    fixture_path=Path(a.candidate_root)/'synthetic-v3.json';fixture=json.loads(fixture_path.read_text())
    env=h.Env();env.h=h;env.device_root=a.candidate_root;env.records=records;env.fixture=fixture;env.log=log;env.contexts=[];env.srv=h.Server(app,None,fixture_path.read_bytes());bad=0
    log({'kind':'run','appSha':APP_SHA,'runnerSha':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'DERIVATIVE device copy only; no SDK/emulator; not actual Windows/Android device'})
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            env.b=pw.chromium.launch(headless=True,chromium_sandbox=True,args=['--no-proxy-server','--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1'])
            log({'kind':'browser','version':env.b.version,'chromiumSandbox':True})
            for name,fn in selected:
                env.contexts=[];start=time.monotonic();r={'kind':'case','id':name}
                try:r.update(fn(env));r['status']='PASS'
                except Exception as e:r.update(status='FAIL',error=str(e),trace=traceback.format_exc());bad+=1
                finally:
                    errs=[]
                    for c in env.contexts:
                        try:c.close()
                        except Exception as e:errs.append(str(e))
                    if errs:r['cleanupErrors']=errs;bad+=1;r['status']='FAIL'
                r['seconds']=round(time.monotonic()-start,3);log(r);print(name,r['status'],flush=True)
            env.b.close()
    finally:env.srv.httpd.shutdown();env.srv.httpd.server_close()
    need(hashlib.sha256(app_path.read_bytes()).hexdigest()==APP_SHA,'candidate changed')
    summary={'kind':'suite','status':'PASS' if bad==0 else 'FAIL','cases':len(selected),'failed':bad,'exitCode':0 if bad==0 else 1};log(summary);(out/'summary.json').write_text(json.dumps(summary,indent=2));return summary['exitCode']
if __name__=='__main__':sys.exit(main())
