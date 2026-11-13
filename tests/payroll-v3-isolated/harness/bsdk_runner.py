#!/usr/bin/env python3
"""BSDK runner v2: REAL sandboxed Chromium + OFFICIAL Firebase JS SDK 10.12.2 (browser ESM from the locked npm package,
served locally) + LOCAL Auth/Firestore emulators (project demo-bhcs-payroll-isolated). Synthetic data only.

Case families
  G*    production-init guard and browser egress controls (no SDK needed)
  H*    harness self-tests (no SDK; stubbed cloud run where stated) - they validate the tooling, NOT the candidate's SDK path
  BSDK* integration cases - require the official SDK + emulators; BLOCKED by preflight when those are missing

Exit codes: 0 all selected PASS | 1 any FAIL / exception | 2 empty selection / bad args | 3 preflight BLOCKED for selected
            SDK cases (other selected cases still run and are reported) | 124 hard total timeout (in-process watchdog).
Run under supervise.py for the outer timeout, residual-port and leftover-process checks.
Usage: bsdk_runner.py --candidate-root DIR --output NEW_DIR [--case PREFIX ...] [--no-sdk-only] [--timeout-seconds N]
"""
import argparse, base64, hashlib, json, os, re, signal, socket, subprocess, sys, threading, time, traceback, urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import netpolicy

HERE = os.path.dirname(os.path.abspath(__file__))
APP_SHA = '388620bb25f64db6245bf187d4bbe64c6e78a22920f4509e9577cf65e0ceb837'
RULES_SHA = '61e211620915fb4e413871e07bf3d1aa6d1462698cadda41f2bcec3df3b62987'
LOCK_SHA = 'e792ee4171a006155b5b8f7d8597c238e7a650f481f231e73718a99a8c59d246'
FIXTURE_SHA = '237fde167ea8e6803a1a43aea84af275a59a24d9abdc6d65a9958afa105ae0cd'
PROJECT = netpolicy.PROJECT
AUTH, FST = ('127.0.0.1', 19099), ('127.0.0.1', 18080)
PORTS = {'auth': 19099, 'firestore': 18080, 'hub': 14400, 'logging': 14500}
SDK_VER, TOOLS_VER, FIRESTORE_EMU = '10.12.2', '13.35.1', '1.19.8'
GSTATIC = f'https://www.gstatic.com/firebasejs/{SDK_VER}/'
SDK_FILES = ['firebase-app.js', 'firebase-auth.js', 'firebase-firestore.js']
USERS = {'a': 'synthetic-a@example.test', 'b': 'synthetic-b@example.test'}
SYN_LOGIN_PW = 'synthetic-only-password'      # emulator-only synthetic login
PAY_PW = 'synthetic-bsdk-payroll-password'     # synthetic payroll encryption password
HOOKS = open(os.path.join(HERE, 'page_hooks.js')).read()
DEADLINE_MS = 30000
# NEVER DEPLOY: BSDK06 negative-control mutant removes the deadline race from cloudRequest.
MUT06_FROM = ("try{return await Promise.race([Promise.resolve().then(async()=>{await checkCloudTicket(ticket);await checkCloudTicket(ticket);"
              "const result=await run(ticket);await checkCloudTicket(ticket);return result;}),deadline]);}")
MUT06_TO = ("try{deadline.catch(()=>{});/*NEVER DEPLOY: BSDK06 mutant, no deadline race*/return await Promise.resolve().then(async()=>{await checkCloudTicket(ticket);"
            "await checkCloudTicket(ticket);const result=await run(ticket);await checkCloudTicket(ticket);return result;});}")

def sha(b): return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()
def canon(o): return sha(json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(',', ':')))
def now(): return datetime.now(timezone.utc).isoformat(timespec='milliseconds')
class Fail(AssertionError): pass
class Blocked(AssertionError): pass
def need(c, point, detail=''):
    if not c: raise Fail(f'{point}: {detail}' if detail else point)

# ----------------------------------------------------------------------------- preflight & provenance
def lock_entry(lock, name):
    e = lock.get('packages', {}).get(f'node_modules/{name}', {})
    return {k: e.get(k) for k in ('version', 'resolved', 'integrity')}

def emulator_expected_checksum(nm):
    """firebase-tools ships the expected md5 of each downloadable emulator; read it, never trust the jar alone."""
    p = os.path.join(nm, 'firebase-tools', 'lib', 'emulator', 'downloadableEmulators.js')
    try: src = open(p).read()
    except OSError: return None
    m = re.search(r'firestore:\s*\{[^}]*?version:\s*"([^"]+)"[^}]*?expectedChecksum:\s*"([0-9a-f]{32})"', src, re.S)
    return {'version': m.group(1), 'md5': m.group(2)} if m else None

def preflight(root):
    """Checks only; never installs or downloads. Returns (ok, report)."""
    it = os.path.join(root, 'tests', 'isolated-integration'); nm = os.path.join(it, 'node_modules')
    r = {'missing': [], 'hashes': {}}
    def h(rel, exp):
        p = os.path.join(root, rel)
        if not os.path.exists(p): r['missing'].append(rel); return
        a = sha(open(p, 'rb').read()); r['hashes'][rel] = a
        if exp and a != exp: r['missing'].append(f'{rel} sha mismatch {a}')
    h('index.html', APP_SHA); h('tests/isolated-integration/firestore.rules', RULES_SHA)
    h('tests/isolated-integration/package-lock.json', LOCK_SHA); h('tests/idb-browser/fixture_A.json', FIXTURE_SHA)
    try:
        lock = json.load(open(os.path.join(it, 'package-lock.json')))
        r['lockedSources'] = {n: lock_entry(lock, n) for n in ('firebase', 'firebase-tools', '@firebase/rules-unit-testing')}
    except Exception as e: r['lockedSources'] = {'error': str(e)}
    def ver(pkg):
        try: return json.load(open(os.path.join(nm, pkg, 'package.json')))['version']
        except Exception: return None
    r['installed'] = {'firebase': ver('firebase'), 'firebase-tools': ver('firebase-tools')}
    if r['installed']['firebase'] != SDK_VER: r['missing'].append(f'node_modules/firebase {SDK_VER} (found {r["installed"]["firebase"]})')
    if r['installed']['firebase-tools'] != TOOLS_VER: r['missing'].append(f'node_modules/firebase-tools {TOOLS_VER} (found {r["installed"]["firebase-tools"]})')
    r['sdkBrowserFiles'] = {}
    for f in SDK_FILES:
        p = os.path.join(nm, 'firebase', f)
        if os.path.exists(p): r['sdkBrowserFiles'][f] = sha(open(p, 'rb').read())
        else: r['missing'].append(f'node_modules/firebase/{f} (official browser ESM build)')
    exp = emulator_expected_checksum(nm); r['emulatorExpected'] = exp
    jar = os.path.join(it, 'emulator-cache', f'cloud-firestore-emulator-v{FIRESTORE_EMU}.jar')
    if os.path.exists(jar):
        b = open(jar, 'rb').read(); r['firestoreEmulatorJar'] = {'sha256': sha(b), 'md5': hashlib.md5(b).hexdigest()}
        if not exp or exp['version'] != FIRESTORE_EMU or exp['md5'] != r['firestoreEmulatorJar']['md5']:
            r['missing'].append('emulator jar md5 does not match firebase-tools expectedChecksum')
    else:
        r['firestoreEmulatorJar'] = None
        r['missing'].append(f'emulator-cache/cloud-firestore-emulator-v{FIRESTORE_EMU}.jar (pre-provision with provision.sh; runner never downloads)')
    prov = os.path.join(it, 'deps-provenance.json')
    r['provenanceFile'] = sha(open(prov, 'rb').read()) if os.path.exists(prov) else None
    try:
        v = subprocess.run(['java', '-version'], capture_output=True, text=True, timeout=20, env=dict(os.environ, JAVA_TOOL_OPTIONS=''))
        r['java'] = next((l for l in v.stderr.splitlines() if 'version' in l), v.stderr.strip()[:120])
    except Exception as e: r['missing'].append('java'); r['java'] = str(e)
    r['node'] = subprocess.run(['node', '-v'], capture_output=True, text=True).stdout.strip()
    busy = [n for n, p in PORTS.items() if port_open('127.0.0.1', p)]
    if busy: r['missing'].append(f'emulator ports already in use: {busy}')
    r['euid'] = os.geteuid()
    if r['euid'] == 0: r['missing'].append('running as root: refused (sandbox must stay on)')
    return (not r['missing']), r

def port_open(host, port):
    s = socket.socket(); s.settimeout(0.3)
    try: s.connect((host, port)); return True
    except Exception: return False
    finally: s.close()

# ----------------------------------------------------------------------------- emulator
class Emulators:
    def __init__(self, root, outdir):
        self.it = os.path.join(root, 'tests', 'isolated-integration'); self.out = outdir; self.p = None
    def start(self):
        env = dict(os.environ, FIREBASE_EMULATORS_PATH=os.path.join(self.it, 'emulator-cache'),
                   XDG_CONFIG_HOME=os.path.join(self.out, 'isolated-firebase-config'), GOOGLE_APPLICATION_CREDENTIALS='',
                   FIREBASE_TOKEN='', GCLOUD_PROJECT=PROJECT, FIREBASE_CLI_DISABLE_MOTD='1', HOME=os.path.join(self.out, 'isolated-home'),
                   FIREBASE_CLI_EXPERIMENTS='', HTTPS_PROXY='http://127.0.0.1:9', HTTP_PROXY='http://127.0.0.1:9', NO_PROXY='127.0.0.1')
        os.makedirs(env['XDG_CONFIG_HOME']); os.makedirs(env['HOME'])
        self.log = open(os.path.join(self.out, 'emulator.log'), 'w')
        self.p = subprocess.Popen([os.path.join(self.it, 'node_modules', '.bin', 'firebase'), 'emulators:start', '--only', 'auth,firestore',
                                   '--project', PROJECT, '--config', 'firebase.json'],
                                  cwd=self.it, env=env, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        end = time.monotonic() + 120
        while time.monotonic() < end:
            if self.p.poll() is not None: raise Blocked('emulator exited early; see emulator.log')
            if port_open(*AUTH) and port_open(*FST): return
            time.sleep(0.5)
        raise Blocked('emulators not ready within 120 s')
    def admin(self, method, base, path, body=None):
        req = urllib.request.Request(f'http://{base[0]}:{base[1]}{path}', method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer owner', 'Content-Type': 'application/json'})
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(req, timeout=20) as r: t = r.read(); return json.loads(t) if t else None
    def reset(self):
        self.admin('DELETE', FST, f'/emulator/v1/projects/{PROJECT}/databases/(default)/documents')
        self.admin('DELETE', AUTH, f'/emulator/v1/projects/{PROJECT}/accounts')
        for e in USERS.values():
            u = self.admin('POST', AUTH, '/identitytoolkit.googleapis.com/v1/accounts:signUp?key=demo-key', {'email': e, 'password': SYN_LOGIN_PW, 'returnSecureToken': True})
            self.admin('POST', AUTH, '/identitytoolkit.googleapis.com/v1/accounts:update?key=demo-key', {'localId': u['localId'], 'emailVerified': True})
    def dump(self):
        """Admin REST listing of every payroll document (bypasses rules; harness-side evidence only)."""
        d = self.admin('GET', FST, f'/v1/projects/{PROJECT}/databases/(default)/documents/payroll?pageSize=1000') or {}
        return {doc['name'].rsplit('/', 1)[1]: {k: v for k, v in doc.get('fields', {}).items() if k != 'updatedAt'} for doc in d.get('documents', [])}
    def stop(self):
        if self.p and self.p.poll() is None:
            os.killpg(self.p.pid, signal.SIGTERM)
            try: self.p.wait(30)
            except subprocess.TimeoutExpired: os.killpg(self.p.pid, signal.SIGKILL); self.p.wait(10)
        time.sleep(1)
        return {n: port_open('127.0.0.1', p) for n, p in PORTS.items()}

# ----------------------------------------------------------------------------- server & routing
class Server:
    def __init__(self, app_bytes, sdk_dir, fixture_bytes):
        txt = app_bytes.decode('utf-8'); n = txt.count(MUT06_FROM)
        self.mutant_applied = n
        self.app = app_bytes; self.mutant = txt.replace(MUT06_FROM, MUT06_TO).encode() if n == 1 else None
        self.fixture = fixture_bytes; self.sdk = {}
        if sdk_dir:
            for f in SDK_FILES: self.sdk[f] = open(os.path.join(sdk_dir, f), 'rb').read()
        outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                p = self.path.split('?')[0]
                body = {'/app/': outer.app, '/mutant06/': outer.mutant, '/observer': b'<!doctype html><meta charset=utf-8><title>observer</title>',
                        '/fixture_A.json': outer.fixture}.get(p)
                if body is None: self.send_response(404); self.end_headers(); return
                self.send_response(200); self.send_header('content-type', 'application/json' if p.endswith('.json') else 'text/html; charset=utf-8')
                self.send_header('cache-control', 'no-store'); self.end_headers(); self.wfile.write(body)
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), H); self.port = self.httpd.server_address[1]; self.base = f'http://127.0.0.1:{self.port}'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

def guard(env, name, fb_base_guard=True, substitute=True, **ctx_kw):
    """New browser context with exact default-deny routing, async-safe WebSocket interception, blocked service workers.
    Route log records method/origin/path/decision only - never query values, headers or bodies."""
    ctx = env.b.new_context(service_workers='block', locale='zh-TW', **ctx_kw); env.contexts.append(ctx); server, log = env.srv, env.log
    def route(r):
        req = r.request; u = urlsplit(req.url)
        if substitute and req.url.startswith(GSTATIC) and not u.query and u.path.rsplit('/', 1)[-1] in server.sdk:
            f = u.path.rsplit('/', 1)[-1]
            log({'kind': 'route', 'ctx': name, 'decision': 'SUBSTITUTE-LOCAL-SDK', 'method': req.method, 'origin': 'https://www.gstatic.com', 'path': u.path, 'sha256': sha(server.sdk[f])})
            return r.fulfill(status=200, body=server.sdk[f], headers={'content-type': 'text/javascript', 'access-control-allow-origin': '*'})
        ok, why = netpolicy.decide(req.url, server.port)
        log({'kind': 'route', 'ctx': name, 'decision': 'ALLOW' if ok else 'BLOCK', 'why': why, 'method': req.method, 'origin': f'{u.scheme}://{u.netloc.rsplit("@", 1)[-1]}', 'path': u.path})
        r.continue_() if ok else r.abort('blockedbyclient')
    ctx.route('**/*', route)
    # Never call ws.close()/connect_to_server() synchronously in this callback (repaired NET01 pattern): never upstream.
    ctx.route_web_socket(re.compile('.*'), lambda ws: log({'kind': 'route', 'ctx': name, 'decision': 'BLOCK-WEBSOCKET(never upstream)', 'origin': urlsplit(ws.url).netloc}))
    if not fb_base_guard: ctx.add_init_script(script='window.__BSDK_NO_FB_GUARD=true;')
    ctx.add_init_script(script=HOOKS)
    ctx.dialogs = []; ctx.policy = lambda d: True; ctx.errors = []
    def wire(pg):
        def dlg(d):
            ctx.dialogs.append({'type': d.type, 'message': d.message[:160]}); d.accept() if ctx.policy(d) else d.dismiss()
        pg.on('dialog', dlg); pg.on('pageerror', lambda e: ctx.errors.append(str(e)[:300])); pg.set_default_timeout(45000)
    ctx.on('page', wire)
    return ctx

# ----------------------------------------------------------------------------- page helpers
WIRE = """async ([email, pw, app_name, observer]) => {
  const B = 'https://www.gstatic.com/firebasejs/10.12.2/';
  const [a, au, fs] = await Promise.all([import(B + 'firebase-app.js'), import(B + 'firebase-auth.js'), import(B + 'firebase-firestore.js')]);
  const app = a.initializeApp({projectId: 'demo-bhcs-payroll-isolated', apiKey: 'demo-key', authDomain: 'localhost'}, app_name);
  if (app.options.projectId !== 'demo-bhcs-payroll-isolated') throw new Error('wrong project');
  const auth = au.getAuth(app); au.connectAuthEmulator(auth, 'http://127.0.0.1:19099', {disableWarnings: true});
  const db = fs.initializeFirestore(app, {experimentalForceLongPolling: true}); fs.connectFirestoreEmulator(db, '127.0.0.1', 18080);
  const cred = await au.signInWithEmailAndPassword(auth, email, pw);
  const info = {sdkVersion: a.SDK_VERSION, project: app.options.projectId, user: cred.user.email, verified: cred.user.emailVerified};
  if (observer) { window.__obs = {app, au, auth, fs, db}; return info; }
  if (cloud.fs || cloud.app) throw new Error('candidate already loaded an SDK before test wiring');
  cloud.app = app; cloud.au = au; cloud.auth = auth; cloud.fs = fs; cloud.db = db; setCloudUser(cred.user); cloud.ready = true; loadCloudMeta();
  __bsdk.instrumentSdk(); __bsdk.trackRequests(); return info; }"""
OBS_READ = """async () => { const o = window.__obs, d = id => o.fs.doc(o.db, 'payroll', id);
  const m = await o.fs.getDocFromServer(d('meta')); if (!m.exists()) return {meta: null, parts: {}};
  const meta = m.data(), parts = {}; for (const id of meta.parts) { const s = await o.fs.getDocFromServer(d(id)); parts[id] = s.exists() ? s.data() : null; }
  return {meta: {...meta, updatedAt: null}, parts}; }"""
OBS_DOC_EXISTS = "async (id) => (await __obs.fs.getDocFromServer(__obs.fs.doc(__obs.db, 'payroll', id))).exists()"
DECRYPT_ALL = "async ([parts, pw, salt]) => { const o = {}; for (const [k, v] of Object.entries(parts)) o[k] = v ? await __bsdk.decrypt(v, pw, salt) : null; return o; }"
SNAP = """() => ({state: JSON.stringify(state), cw: storeGet(CLOUD_WRITE), rev: cloud.rev, uncertain: cloud.uncertain, conflict: cloud.conflict,
  status: cloud.status, user: cloud.user ? cloud.user.email : null, epoch: dataEpoch, busy: cloud.busy, sdk: {...__bsdk.sdk},
  banner: getComputedStyle($('cloudBanner')).display !== 'none' ? $('cloudBannerTxt').textContent : ''})"""
LOCAL_PARTS = "() => JSON.stringify(cloudParts(JSON.parse(JSON.stringify(state))))"

def app_page(ctx, base, path='/app/'):
    p = ctx.new_page(); p.goto(base + path, wait_until='domcontentloaded')
    p.wait_for_function("typeof localDB!=='undefined' && (localDB.ready || localDB.failed!==null || getComputedStyle($('storageSetup')).display!=='none')"); return p
def first_setup(p, fixture_path):
    p.set_input_files('input[onchange="initializeFromBackup(this)"]', fixture_path); p.wait_for_function('localDB.ready', timeout=60000)
def idle(p, t=60000): p.wait_for_function('persistence.pending===0 && persistence.operations===0 && !sec.locking && !cloud.busy', timeout=t)
def enable_pw(p):
    p.click('#secBtn'); p.fill('#secNew', PAY_PW); p.fill('#secNew2', PAY_PW); p.click('#secSet'); idle(p); p.evaluate('closeSec()')
def unlock(p):
    p.wait_for_selector('#lockOverlay.on'); p.fill('#lockPass', PAY_PW); p.click('#lockUnlock'); idle(p); need(not p.evaluate('sec.locked'), 'FP-UNLOCK')
def canonical(p): return p.evaluate('__bsdk.canonical()')
def settled(p, n_before, t=40000):
    """Wait for an explicit end of the transaction(s) started after n_before - never a bare sleep."""
    p.wait_for_function('(n)=>__bsdk.settled.transactions>n && __bsdk.settled.callbacks>=__bsdk.sdk.txAttempts', arg=n_before, timeout=t)

class Env: pass

def prepared(env, name, encrypted=True, sign_in=True, user='a', path='/app/'):
    """first-setup UI import of the synthetic fixture, payroll password, test wiring to the emulators."""
    c = guard(env, name, accept_downloads=True); p = app_page(c, env.srv.base, path); first_setup(p, env.fixture_path)
    root = p.evaluate('__bsdk.read()'); need(json.loads(root['values']['bhcs_payroll_cloudwrite'])['kind'] == 'initial-verification', 'FP-PRE-MARKER')
    if encrypted: enable_pw(p)
    info = p.evaluate(WIRE, [USERS[user], SYN_LOGIN_PW, 'candidate', False]) if sign_in else None
    return c, p, info

def observer(env, user='b'):
    c = guard(env, 'observer-' + user); o = c.new_page(); o.goto(env.srv.base + '/observer')
    return c, o, o.evaluate(WIRE, [USERS[user], SYN_LOGIN_PW, 'observer', True])

def seeder(env, marker):
    """Second real SDK client (separate candidate page, user b) that publishes a valid encrypted snapshot via the app."""
    c, p, _ = prepared(env, 'seeder', True, True, 'b'); p.evaluate('cloud.suppress=true')
    p.evaluate("(m)=>{state.settings.fixtureMarker=m;return save();}", marker); idle(p)
    p.evaluate('openCloud()'); p.click('#cloudPushBtn'); idle(p); need(p.evaluate('cloud.rev') >= 1, 'FP-SEED-UPLOAD')
    return c, p

def seeder_publish(p, marker):
    rev = p.evaluate('cloud.rev'); p.evaluate("(m)=>{state.settings.fixtureMarker=m;return save();}", marker); idle(p)
    p.click('#cloudPushBtn'); idle(p); need(p.evaluate('cloud.rev') == rev + 1, 'FP-SEED-PUBLISH', str(p.evaluate('cloud.status')))

def synced(env, name, path='/app/'):
    env.emu.reset(); c, p, _ = prepared(env, name, path=path); p.evaluate('cloud.suppress=true')
    p.evaluate('openCloud()'); p.click('#cloudPushBtn'); idle(p)
    need(p.evaluate('cloud.rev') == 1 and p.evaluate('storeGet(CLOUD_WRITE)') is None, 'FP-PRE-SYNC', str(p.evaluate('cloud.status')))
    p.evaluate('closeCloud()'); return c, p

def remote(env, o=None):
    d = env.emu.dump(); r = {'adminDumpDigest': canon(d), 'docs': sorted(d)}
    if o: x = o.evaluate(OBS_READ); r.update(observerDigest=canon(x), rev=(x['meta'] or {}).get('rev'))
    return r

# ----------------------------------------------------------------------------- cases
CASES = []
def case(cid, title, needs_sdk=True, kind='integration'):
    def d(fn): CASES.append(dict(id=cid, title=title, needs_sdk=needs_sdk, kind=kind, fn=fn)); return fn
    return d

@case('G1', 'candidate cannot initialize production Firebase (FB_BASE -> missing local path)', False, 'guard')
def g1(env):
    c = guard(env, 'G1'); p = app_page(c, env.srv.base); first_setup(p, env.fixture_path); n0 = len(env.records)
    p.evaluate("cloudSignIn()"); p.wait_for_function("/載入|失敗|Failed|fetch|import/.test(cloud.status)", timeout=20000)
    st = p.evaluate("({app:cloud.app,fs:!!cloud.fs,status:cloud.status,fbBase:FB_BASE})")
    routes = [r for r in env.records[n0:] if r.get('kind') == 'route']
    need(st['app'] is None and not st['fs'], 'FP-G1-INIT', repr(st))
    need(not [r for r in routes if r['decision'] != 'BLOCK' and r.get('why') != 'local-server'], 'FP-G1-EGRESS')
    return {'candidate': st, 'routesDuringSignIn': routes}

@case('G1b', 'FB_BASE guard removed: route default-deny blocks gstatic, candidate still cannot initialize', False, 'guard')
def g1b(env):
    c = guard(env, 'G1b', fb_base_guard=False, substitute=False); p = app_page(c, env.srv.base); first_setup(p, env.fixture_path); n0 = len(env.records)
    p.evaluate("cloudSignIn()"); p.wait_for_function("/載入|失敗|Failed|fetch|import/.test(cloud.status)", timeout=20000)
    st = p.evaluate("({app:cloud.app,fs:!!cloud.fs,status:cloud.status,fbBase:FB_BASE})")
    routes = [r for r in env.records[n0:] if r.get('kind') == 'route']
    need(st['fbBase'].startswith(GSTATIC), 'FP-G1B-GUARD-NOT-REMOVED', st['fbBase'])
    need(any(r['decision'] == 'BLOCK' and r['origin'] == 'https://www.gstatic.com' for r in routes), 'FP-G1B-GSTATIC')
    need(st['app'] is None and not st['fs'], 'FP-G1B-INIT', repr(st))
    return {'candidate': st, 'routesDuringSignIn': routes}

@case('G2', 'browser egress negative controls incl. query/host/userinfo spoofing (netpolicy.NEGATIVE) and WebSocket', False, 'guard')
def g2(env):
    c = guard(env, 'G2', substitute=False); p = c.new_page(); p.goto(env.srv.base + '/observer'); n0 = len(env.records)
    # 'local-forbidden-nested' is resolved by the browser to the allowed /app/ page before routing (not egress); raw form covered by H1.
    urls = {k: u.replace(str(netpolicy.SP), str(env.srv.port)) for k, u in netpolicy.NEGATIVE.items() if k != 'local-forbidden-nested'}
    res = p.evaluate("""async(U)=>{const R={};for(const [k,u] of Object.entries(U)){try{await fetch(u,{mode:'no-cors'});R[k]='reached';}catch(e){R[k]='blocked';}}
      R.__ws=await new Promise(a=>{const w=new WebSocket('wss://firestore.googleapis.com/x');w.onopen=()=>a('page-side open, no upstream');w.onerror=()=>a('error');setTimeout(()=>a('no event'),2500);});
      return R;}""", urls)
    routes = [r for r in env.records[n0:] if r.get('kind') == 'route']
    need(all(res[k] == 'blocked' for k in urls), 'FP-G2-EGRESS', repr({k: v for k, v in res.items() if v != 'blocked'}))
    need(not [r for r in routes if r['decision'] == 'ALLOW' and r['why'] != 'local-server'], 'FP-G2-ALLOWED', 'a non-local request was ALLOWed')
    need(any(r['decision'].startswith('BLOCK-WEBSOCKET') for r in routes), 'FP-G2-WS')
    need(p.evaluate('6*7') == 42, 'FP-G2-PAGE-HUNG')
    return {'attempts': res, 'routes': routes, 'note': 'browser-normalized URLs (e.g. ../) reach the router already resolved; raw forms are covered by H1'}

@case('H1', 'netpolicy exact parser unit self-test (positives allowed, every spoof/negative denied)', False, 'harness-self-test')
def h1(env):
    ok, rows = netpolicy.self_test(); need(ok, 'FP-H1', json.dumps([r for r in rows if (r['kind'] == 'positive') != r['allowed']]))
    return {'rows': rows}

def bsdk06_body(env, p, req_call, label):
    """Shared BSDK06/H3 logic. req_call starts the foreground request in the page and stores its outcome in window.__fg."""
    r0 = canonical(p); rev0 = p.evaluate('cloud.rev'); p.evaluate("__bsdk.trackRequests()")
    p.evaluate("()=>{__bsdk.gate('postRunCheck'); __bsdk.holdTarget = r => !r.write;}")
    t0 = time.monotonic(); p.evaluate("window.__fg=null"); p.evaluate("() => { " + req_call + "; }")   # fire-and-forget: never await the foreground here
    p.wait_for_function('__bsdk.gates.postRunCheck.reached', timeout=DEADLINE_MS - 2000)
    g = p.evaluate("({...__bsdk.gates.postRunCheck, p: undefined})"); req = p.evaluate("(id)=>__bsdk.reqs.find(r=>r.id===id)", g['req'])
    need(g['callIndex'] == 3, 'FP-06-WRONG-CHECK', f'held ensureStorageCurrent call #{g["callIndex"]} (expected #3: after 2 pre-run checks + run resolved)')
    need(g['msSinceRequestStart'] < DEADLINE_MS, 'FP-06-HOLD-OUTSIDE-DEADLINE', str(g['msSinceRequestStart']))
    try: p.wait_for_function('window.__fg!==null', timeout=DEADLINE_MS + 15000)
    except Exception: pass
    fg = p.evaluate('window.__fg'); held_still = not p.evaluate('__bsdk.gates.postRunCheck.released')
    need(fg is not None and held_still, 'FP-06-FOREGROUND-NOT-ENDED', 'foreground still pending while the post-run check is held past the deadline')
    req = p.evaluate("(id)=>__bsdk.reqs.find(r=>r.id===id)", g['req'])
    need(req['outcome'] == 'rejected' and req['code'] == 'cloud-read-timeout', 'FP-06-OUTCOME', repr(req))
    need(req['end'] - req['start'] >= DEADLINE_MS - 2, 'FP-06-EARLY', str(req['end'] - req['start']))
    p.evaluate("__bsdk.release('postRunCheck')"); p.wait_for_function('__bsdk.gates.postRunCheck.settled', timeout=10000); idle(p)
    need(canonical(p) == r0 and p.evaluate('cloud.rev') == rev0, 'FP-06-LATE-APPLIED')
    return {'gate': g, 'request': req, 'foreground': fg, 'pythonForegroundSeconds': round(time.monotonic() - t0, 3), 'localCanonicalDigest': sha(r0),
            'events': [e for e in p.evaluate('__bsdk.events') if e['what'].startswith(('req:', 'post-run'))]}

H3_CALL = "cloudRequest(dataEpoch, async () => 'stub-read-NOT-SDK', false, true).then(v=>{window.__fg={v,t:performance.now()};},e=>{window.__fg={err:String(e.message),code:e.code||null,t:performance.now()};})"
@case('H3', 'BSDK06 gate placement self-test with a STUB run (no SDK): hold lands on post-run check inside the real 30 s deadline', False, 'harness-self-test')
def h3(env):
    c = guard(env, 'H3'); p = app_page(c, env.srv.base); first_setup(p, env.fixture_path)
    return bsdk06_body(env, p, H3_CALL, 'H3')

def negative_control(expected_point, fn):
    def run(env):
        try: out = fn(env)
        except Fail as e:
            point = str(e).split(':', 1)[0]
            need(point == expected_point, 'FP-NEG-WRONG-POINT', f'mutant failed at {point}, expected {expected_point}')
            return {'negativeControl': {'mutant': 'NEVER DEPLOY: cloudRequest without deadline race', 'expectedFailPoint': expected_point,
                                        'observedFailPoint': point, 'detail': str(e), 'detected': True}}
        raise Fail('FP-NEG-MUTANT-SURVIVED: mutant passed every assertion: ' + json.dumps(out)[:300])
    return run

def h3m(env):
    need(env.srv.mutant is not None, 'FP-NEG-MUTATION-NOT-APPLIED', f'pattern count {env.srv.mutant_applied}')
    c = guard(env, 'H3-MUTANT'); p = app_page(c, env.srv.base, '/mutant06/'); first_setup(p, env.fixture_path)
    return bsdk06_body(env, p, H3_CALL, 'H3-MUTANT')
case('H3-MUTANT', 'negative control for H3: NEVER-DEPLOY mutant must be detected at FP-06-FOREGROUND-NOT-ENDED', False, 'harness-negative-control')(
    negative_control('FP-06-FOREGROUND-NOT-ENDED', h3m))

def h4(mode):
    @case('H4-' + mode, f'CLOUD_WRITE intent persistence fault self-test ({mode}) on real native IndexedDB, direct beginCloudWrite (no SDK)', False, 'harness-self-test')
    def f(env):
        c = guard(env, 'H4-' + mode); p = app_page(c, env.srv.base); first_setup(p, env.fixture_path); enable_pw(p)
        r0 = canonical(p); rev0 = p.evaluate('__bsdk.read()')['revision']
        if mode == 'intent-cas':
            q = c.new_page(); q.goto(env.srv.base + '/observer'); peer_rev = q.evaluate('__bsdk.peerBump()')
        else: p.evaluate('(m)=>__bsdk.cloudWriteFault(m)', mode); peer_rev = None
        err = p.evaluate("beginCloudWrite(7).then(()=>null,e=>String(e.message))")
        need(err and '未送出雲端交易' in err, 'FP-H4-NO-REJECTION', repr(err))
        fault = p.evaluate('__bsdk.fault||null')
        if mode != 'intent-cas': need(fault['hits'] == 1, 'FP-H4-FAULT-NOT-REACHED')
        if mode == 'abort-after-success': need(fault['requestSucceeded'] and fault['aborted'], 'FP-H4-ABORT')
        r1 = canonical(p); need(r1 == r0, 'FP-H4-CANONICAL-CHANGED')
        return {'rejection': err, 'fault': fault, 'peerRevision': peer_rev, 'revisionBefore': rev0, 'revisionAfter': p.evaluate('__bsdk.read()')['revision'],
                'localCanonicalDigest': sha(r1), 'note': 'synthetic quota, NOT real exhaustion' if mode == 'quota' else ''}
for _m in ('abort-after-success', 'quota', 'intent-cas'): h4(_m)

@case('H5', 'snapshot-CAS gate self-test (no SDK): armed after a settled initial save; only the targeted caller is held; peer tab write + release -> CAS rejection, no deadlock', False, 'harness-self-test')
def h5(env):
    c = guard(env, 'H5'); p = app_page(c, env.srv.base); first_setup(p, env.fixture_path); enable_pw(p)
    p.evaluate("()=>{state.settings.h5='initial';return save();}"); idle(p, 20000)          # initial save settles first
    p.evaluate("()=>__bsdk.armSnapshotCas('h5Target')")
    p.evaluate("()=>{state.settings.h5='untargeted';return save();}"); idle(p, 20000)       # untargeted caller must pass through
    calls = p.evaluate('__bsdk.snapCalls'); need(calls and not any(x['held'] for x in calls) and not p.evaluate('__bsdk.gates.snapCas.reached'), 'FP-H5-UNTARGETED-HELD')
    r0 = canonical(p)
    p.evaluate("""()=>{window.__h5=null; window.h5Target=function h5Target(){return persistSnapshot(JSON.stringify(state),sec.key,sec.salt,dataEpoch);};
                   h5Target().then(()=>{window.__h5={ok:true};},e=>{window.__h5={err:String(e.message)};});}""")
    p.wait_for_function('__bsdk.gates.snapCas.reached', timeout=10000); g = p.evaluate("({stack:__bsdk.gates.snapCas.stack})")
    need(any(f.endswith('h5Target') for f in g['stack']), 'FP-H5-WRONG-CALLER', json.dumps(g))
    q = c.new_page(); q.goto(env.srv.base + '/observer'); peer = q.evaluate('__bsdk.peerBump()')
    p.evaluate("__bsdk.release('snapCas')"); p.wait_for_function('window.__h5!==null', timeout=15000); res = p.evaluate('window.__h5')
    need('err' in res, 'FP-H5-NO-CAS-REJECTION', json.dumps(res)); need(canonical(p) == r0, 'FP-H5-CANONICAL-CHANGED')
    return {'untargetedCalls': calls, 'gateStack': g['stack'], 'peerRevision': peer, 'result': res}

# ---- SDK integration cases --------------------------------------------------------------------------------------
@case('BSDK01', 'first connect is read-only; no automatic upload (empty remote and different remote)')
def bsdk01(env):
    out = {}
    for variant in ('remote-empty', 'remote-different'):
        env.emu.reset(); sc = None
        if variant == 'remote-different': sc, _ = seeder(env, 'REMOTE-OTHER')
        before = env.emu.dump(); c, p, info = prepared(env, 'BSDK01-' + variant)
        l0 = canonical(p); r1 = p.evaluate('cloudPush(true)'); r2 = p.evaluate('cloudConnect(true)'); idle(p)
        p.evaluate('cloudWatch()'); p.wait_for_function('__bsdk.sdk.onSnapshot>=1', timeout=10000)
        n_rt = p.evaluate('__bsdk.sdk.runTransaction')
        sched = p.evaluate("(()=>{const t0=cloud.timer;schedulePush();return {changed:cloud.timer!==t0};})()")
        p.wait_for_timeout(3000)   # schedulePush debounce is 2 s; this window only verifies nothing is ever started
        s = p.evaluate(SNAP); l1 = canonical(p); after = env.emu.dump()
        need(r1 is False and r2 is False, 'FP-01-RETURN', f'{r1}/{r2}')
        need(s['sdk']['runTransaction'] == 0 and n_rt == 0, 'FP-01-SDK-WRITE'); need(s['sdk']['getDocFromServer'] >= 1, 'FP-01-NO-SERVER-READ')
        need(after == before, 'FP-01-REMOTE-CHANGED'); need(json.loads(s['cw'])['kind'] == 'initial-verification', 'FP-01-MARKER-CLEARED')
        need('不會自動上傳' in s['banner'], 'FP-01-NO-WARNING'); need(not sched['changed'], 'FP-01-SCHEDULED')
        out[variant] = {'info': info, 'sdk': s['sdk'], 'remote': {'before': canon(before), 'after': canon(after)},
                        'local': {'before': sha(l0), 'after': sha(l1)}, 'banner': s['banner']}
        c.close()
        if sc: sc.close()
    return out

@case('BSDK02', 'explicit download: cancel confirm, cancel password, wrong password, missing shard, meta change (before tx / after tx meta read), success with full + recovery consistency, RAM edit during download')
def bsdk02(env):
    res = {}; env.emu.reset(); sc, sp = seeder(env, 'REMOTE-B2'); co, o, _ = observer(env)
    def fresh(tag):
        c, p, _ = prepared(env, 'BSDK02-' + tag); p.evaluate('cloud.suppress=true')
        return c, p, canonical(p), p.evaluate('JSON.stringify(state)'), env.emu.dump()
    def unchanged(p, l0, s0, d0, fp): need(canonical(p) == l0 and p.evaluate('JSON.stringify(state)') == s0 and env.emu.dump() == d0, fp)
    def start_pull(p): p.evaluate('openCloud()'); p.click('#cloudPullBtn')
    def give_pw(p, pw=PAY_PW): p.wait_for_selector('#askModal.on'); p.fill('#askPass', pw); p.click('#askOk')
    c, p, l0, s0, d0 = fresh('cancel-confirm'); c.policy = lambda d: False
    start_pull(p); idle(p); unchanged(p, l0, s0, d0, 'FP-02-CANCEL-CONFIRM'); res['cancelConfirm'] = {'dialogs': c.dialogs, 'status': p.evaluate('cloud.status')}; c.close()
    c, p, l0, s0, d0 = fresh('cancel-password')
    start_pull(p); p.wait_for_selector('#askModal.on'); n0 = p.evaluate('__bsdk.sdk.runTransaction'); p.click('#askCancel'); idle(p)
    unchanged(p, l0, s0, d0, 'FP-02-CANCEL-PASSWORD'); need(p.evaluate('__bsdk.sdk.runTransaction') == n0, 'FP-02-CANCEL-PASSWORD-SDK')
    res['cancelPassword'] = {'status': p.evaluate('cloud.status')}; c.close()
    c, p, l0, s0, d0 = fresh('wrong-password'); start_pull(p); prompts = 0
    for _ in range(3):
        try: p.wait_for_selector('#askModal.on', timeout=5000)
        except Exception: break
        p.fill('#askPass', 'synthetic-wrong'); p.click('#askOk'); prompts += 1; p.wait_for_timeout(300)
    if p.locator('#askModal.on').count(): p.click('#askCancel')
    idle(p); unchanged(p, l0, s0, d0, 'FP-02-WRONG-PASSWORD'); res['wrongPassword'] = {'prompts': prompts, 'status': p.evaluate('cloud.status')}; c.close()
    for where in ('before-tx', 'after-tx-meta-read'):
        c, p, l0, s0, d0 = fresh('meta-change-' + where); gate = 'entryHold' if where == 'before-tx' else 'metaHold'
        p.evaluate('(g)=>__bsdk.gate(g)', gate); start_pull(p); give_pw(p)
        p.wait_for_function('(g)=>__bsdk.gates[g].reached', arg=gate, timeout=30000); n_tx = p.evaluate('__bsdk.settled.transactions')
        seeder_publish(sp, 'REMOTE-B2-NEWER-' + where); d_mid = env.emu.dump()
        p.evaluate('(g)=>__bsdk.release(g)', gate); settled(p, n_tx); idle(p)
        need(canonical(p) == l0 and p.evaluate('JSON.stringify(state)') == s0, 'FP-02-META-CHANGE-' + where.upper(), 'local replaced although meta changed during read')
        need(env.emu.dump() == d_mid, 'FP-02-META-CHANGE-REMOTE')
        res['metaChange-' + where] = {'status': p.evaluate('cloud.status'), 'txAttempts': p.evaluate('__bsdk.sdk.txAttempts'),
                                      'events': [e for e in p.evaluate('__bsdk.events') if e['what'].startswith(('tx', 'runTransaction', 'callback'))]}
        c.close()
    c, p, l0, s0, d0 = fresh('missing-shard'); meta = o.evaluate(OBS_READ)['meta']; victim = [x for x in meta['parts'] if x != 'core'][0]
    o.evaluate("(id)=>__obs.fs.deleteDoc(__obs.fs.doc(__obs.db,'payroll',id))", victim); d_mid = env.emu.dump()
    start_pull(p); give_pw(p); idle(p); unchanged(p, l0, s0, d_mid, 'FP-02-MISSING-SHARD')
    res['missingShard'] = {'deleted': victim, 'status': p.evaluate('cloud.status')}; c.close()
    seeder_publish(sp, 'REMOTE-B2-FULL')   # restores every listed shard (full republish by the seeder)
    c, p, l0, s0, d0 = fresh('success'); old_salt = p.evaluate('b64(sec.salt)')
    start_pull(p); give_pw(p); idle(p)
    s = p.evaluate(SNAP); rem = o.evaluate(OBS_READ); salt = rem['meta']['salt']
    plain = p.evaluate(DECRYPT_ALL, [rem['parts'], PAY_PW, salt]); local = json.loads(p.evaluate(LOCAL_PARTS))
    need(json.loads(s['state'])['settings']['fixtureMarker'] == 'REMOTE-B2-FULL', 'FP-02-NOT-REMOTE')
    need(plain == local and set(rem['meta']['parts']) == set(local), 'FP-02-PARTIAL', 'local parts != decrypted remote parts')
    need(s['rev'] == rem['meta']['rev'] and s['cw'] is None, 'FP-02-BASELINE')
    rec_pkt = json.loads(p.evaluate('storeGet(RECOVERYKEY)') or 'null'); rec_plain = None
    for sl in (old_salt, salt):
        try: rec_plain = p.evaluate('([k,pw,s])=>__bsdk.decrypt(k,pw,s)', [rec_pkt, PAY_PW, sl]); break
        except Exception: pass
    need(rec_plain is not None and json.loads(rec_plain) == json.loads(s0), 'FP-02-RECOVERY', 'recovery copy missing or != pre-download local state')
    res['success'] = {'rev': s['rev'], 'remoteDigest': canon(rem), 'localDigest': sha(canonical(p)), 'parts': sorted(local), 'recovery': 'equals pre-download state'}
    c.close()
    c, p, l0, s0, d0 = fresh('ram-edit'); p.evaluate("__bsdk.gate('metaHold')"); start_pull(p); give_pw(p)
    p.wait_for_function('__bsdk.gates.metaHold.reached', timeout=30000); n_tx = p.evaluate('__bsdk.settled.transactions')
    p.evaluate("state.settings.bsdkRamEdit='edited-during-download'"); p.evaluate("__bsdk.release('metaHold')"); settled(p, n_tx); idle(p)
    need(p.evaluate("state.settings.bsdkRamEdit") == 'edited-during-download' and json.loads(p.evaluate('JSON.stringify(state)'))['settings'].get('fixtureMarker') != 'REMOTE-B2-FULL',
         'FP-02-RAM-EDIT', 'RAM edit swallowed or local replaced')
    res['ramEdit'] = {'status': p.evaluate('cloud.status')}; c.close(); co.close(); sc.close()
    return res

@case('BSDK03', 'explicit overwrite: cancel; success compared with the ACTUAL uploaded snapshot (post-upload log + auto-upload controlled); stale shard created then verified deleted; newer version after meta read -> conflict')
def bsdk03(env):
    res = {}; c, p = synced(env, 'BSDK03'); co, o, _ = observer(env)
    c.policy = lambda d: False; d0 = env.emu.dump(); l0 = canonical(p); n = p.evaluate('({...__bsdk.sdk})')
    p.evaluate('openCloud()'); p.click('#cloudPushBtn'); idle(p)
    need(p.evaluate('({...__bsdk.sdk})') == n and env.emu.dump() == d0 and canonical(p) == l0, 'FP-03-CANCEL'); res['cancel'] = {'sdk': n}
    c.policy = lambda d: True
    def overwrite(tag):
        n_rt = p.evaluate('__bsdk.sdk.runTransaction'); k = len(p.evaluate('__bsdk.staged')); log_before = p.evaluate('(state.log||[]).length')
        before = o.evaluate(OBS_READ)['meta']; p.click('#cloudPushBtn'); idle(p)
        settled(p, p.evaluate('__bsdk.settled.transactions') - 1, 5000)
        p.wait_for_timeout(2600)   # longer than schedulePush's 2 s debounce: proves cloud.suppress held (count checked below)
        need(p.evaluate('__bsdk.sdk.runTransaction') == n_rt + 1, 'FP-03-AUTO-UPLOAD', 'more than one SDK write after explicit overwrite')
        st = [x for x in p.evaluate('__bsdk.staged')[k:]][-1]; rem = o.evaluate(OBS_READ)
        need(rem['meta']['rev'] == before['rev'] + 1 == st['sets']['meta']['rev'], 'FP-03-REV')
        salt = st['sets']['meta']['salt']; staged_plain = p.evaluate(DECRYPT_ALL, [{i: v for i, v in st['sets'].items() if i != 'meta'}, PAY_PW, salt])
        remote_plain = p.evaluate(DECRYPT_ALL, [rem['parts'], PAY_PW, rem['meta']['salt']])
        need(all(remote_plain[i] == staged_plain[i] for i in staged_plain), 'FP-03-REMOTE-NOT-STAGED', 'remote shard != the snapshot actually staged')
        need(rem['meta']['parts'] == st['sets']['meta']['parts'], 'FP-03-PARTS')
        local = json.loads(p.evaluate(LOCAL_PARTS)); core_l, core_r = json.loads(local['core']), json.loads(remote_plain['core'])
        extra = core_l['log'][len(core_r['log']):]
        need({k: v for k, v in core_l.items() if k != 'log'} == {k: v for k, v in core_r.items() if k != 'log'} and core_l['log'][:len(core_r['log'])] == core_r['log'], 'FP-03-CORE')
        need(len(extra) == 1 and '覆蓋雲端' in json.dumps(extra, ensure_ascii=False), 'FP-03-POST-LOG', 'unexpected post-upload local difference: ' + json.dumps(extra, ensure_ascii=False)[:200])
        need(all(local[i] == remote_plain[i] for i in local if i != 'core'), 'FP-03-MONTHS')
        need(p.evaluate('storeGet(CLOUD_WRITE)') is None, 'FP-03-MARKER')
        return {'rev': rem['meta']['rev'], 'staged': {'sets': sorted(st['sets']), 'deletes': st['deletes']}, 'remoteDigest': canon(rem),
                'postUploadLocalLog': extra, 'logLengthBefore': log_before}, st, rem
    p.evaluate('openCloud()'); res['success'], _, _ = overwrite('ok')
    p.evaluate("()=>{state.months['2099-01']={};return save();}"); idle(p); r_add, _, rem = overwrite('add-stale')
    need('m_2099-01' in rem['parts'] and o.evaluate(OBS_DOC_EXISTS, 'm_2099-01'), 'FP-03-STALE-NOT-CREATED')
    p.evaluate("()=>{delete state.months['2099-01'];return save();}"); idle(p); r_del, st, rem = overwrite('delete-stale')
    need('m_2099-01' in st['deletes'] and 'm_2099-01' not in rem['meta']['parts'] and not o.evaluate(OBS_DOC_EXISTS, 'm_2099-01'), 'FP-03-STALE-NOT-DELETED')
    res['staleShard'] = {'created': r_add, 'deleted': r_del}
    sc, sp = None, None
    sc, sp = seeder_on_existing(env)
    p.evaluate("__bsdk.gate('entryHold')"); p.click('#cloudPushBtn'); p.wait_for_function('__bsdk.gates.entryHold.reached', timeout=30000)
    n_tx = p.evaluate('__bsdk.settled.transactions'); seeder_publish(sp, 'OBSERVER-NEWER'); mid = o.evaluate(OBS_READ)
    p.evaluate("__bsdk.release('entryHold')"); settled(p, n_tx); idle(p); after = o.evaluate(OBS_READ); s = p.evaluate(SNAP)
    need(canon(after) == canon(mid), 'FP-03-NEWER-OVERWRITTEN'); need('已同步' not in s['status'], 'FP-03-FALSE-SUCCESS')
    res['conflict'] = {'status': s['status'], 'conflictFlag': s['conflict'], 'remoteRev': after['meta']['rev']}
    c.close(); co.close(); sc.close(); return res

def seeder_on_existing(env):
    """Seeder page (user b) that downloads the current remote first, so its next publish is a valid newer version."""
    c, p, _ = prepared(env, 'seeder-existing', True, True, 'b'); p.evaluate('cloud.suppress=true')
    p.evaluate('openCloud()'); p.click('#cloudPullBtn'); p.wait_for_selector('#askModal.on'); p.fill('#askPass', PAY_PW); p.click('#askOk'); idle(p)
    need(p.evaluate('cloud.rev') >= 1 and p.evaluate('storeGet(CLOUD_WRITE)') is None, 'FP-SEEDER-PULL'); return c, p

@case('BSDK04', 'committed but acknowledgement withheld: real >= 30 s deadline, late ack, reload variant, explicit download recovery')
def bsdk04(env):
    c, p = synced(env, 'BSDK04'); co, o, _ = observer(env); p.evaluate('cloud.suppress=false')
    p.evaluate("__bsdk.gate('ackHold')"); n0 = p.evaluate('__bsdk.sdk.runTransaction')
    t0 = time.monotonic(); p.evaluate("()=>{state.settings.bsdkEdit='rev2-edit';save();}")   # the app's own debounced upload
    p.wait_for_function('__bsdk.gates.ackHold.reached', timeout=30000); t_commit = time.monotonic()
    rem = o.evaluate(OBS_READ); need(rem['meta']['rev'] == 2, 'FP-04-NOT-COMMITTED')
    marker = p.evaluate('__bsdk.read()')['values']['bhcs_payroll_cloudwrite']; need(marker and json.loads(marker).get('id'), 'FP-04-NO-INTENT')
    p.wait_for_function("__bsdk.reqs.some(r=>r.write&&r.outcome==='rejected')", timeout=DEADLINE_MS + 15000); t_dead = time.monotonic()
    wreq = p.evaluate("__bsdk.reqs.filter(r=>r.write).pop()")
    need(wreq['code'] == 'cloud-write-unknown', 'FP-04-CODE', repr(wreq))
    need(wreq['end'] - wreq['start'] >= DEADLINE_MS - 2, 'FP-04-DEADLINE-LOWER-BOUND', f"{wreq['end'] - wreq['start']:.1f} ms < {DEADLINE_MS} ms")
    s = p.evaluate(SNAP); need(s['rev'] == 1 and s['uncertain'] and s['cw'] == marker, 'FP-04-STATE-AT-DEADLINE')
    p.evaluate("()=>{state.settings.bsdkEdit2='after-deadline';save();}"); idle(p); p.wait_for_timeout(2600)
    need(p.evaluate('__bsdk.sdk.runTransaction') == n0 + 1, 'FP-04-AUTO-RETRY')
    p.evaluate("__bsdk.release('ackHold')"); p.wait_for_function('__bsdk.gates.ackHold.settled', timeout=10000); idle(p)
    s2 = p.evaluate(SNAP); need(s2['rev'] == 1 and s2['cw'] == marker, 'FP-04-LATE-ACK-APPLIED')
    p.evaluate('persistence.safeReload=true'); p.reload(); unlock(p); p.evaluate(WIRE, [USERS['a'], SYN_LOGIN_PW, 'candidate-reload', False])
    n1 = p.evaluate('__bsdk.sdk.runTransaction'); p.evaluate('cloudConnect(false)'); idle(p); p.wait_for_timeout(2600)
    need(p.evaluate('storeGet(CLOUD_WRITE)') == marker and p.evaluate('__bsdk.sdk.runTransaction') == n1, 'FP-04-RELOAD')
    p.evaluate('openCloud()'); p.click('#cloudPullBtn'); idle(p); s3 = p.evaluate(SNAP)
    need(s3['cw'] is None and s3['rev'] == 2 and json.loads(s3['state'])['settings'].get('bsdkEdit') == 'rev2-edit', 'FP-04-RECOVERY')
    out = {'deadline': {'pageMs': round(wreq['end'] - wreq['start'], 1), 'lowerBoundMs': DEADLINE_MS},
           'pythonMonotonic': {'commitHeldAfterS': round(t_commit - t0, 3), 'rejectObservedAfterCommitS': round(t_dead - t_commit, 3)},
           'remoteRevWhileHeld': 2, 'afterLateAck': {'rev': s2['rev'], 'marker': 'unchanged'}, 'reloadVariant': 'realm destroyed; marker kept, no resend (NOT evidence of late-callback execution)',
           'recovery': {'rev': s3['rev'], 'status': s3['status']}, 'remoteDigest': canon(o.evaluate(OBS_READ))}
    c.close(); co.close(); return out

def late_cb(variant):
    @case('BSDK05-' + variant, f'late transaction callback held after the real tx.get(meta) - {variant}; waits for explicit callback/transaction end')
    def f(env):
        c, p = synced(env, 'BSDK05-' + variant); p.evaluate('cloud.suppress=false'); before = env.emu.dump(); l0 = canonical(p)
        p.evaluate("__bsdk.gate('metaHold')"); p.evaluate("()=>{state.settings.bsdkLate='x';save();}")
        p.wait_for_function('__bsdk.gates.metaHold.reached', timeout=30000); n_tx = p.evaluate('__bsdk.settled.transactions')
        e0 = p.evaluate('dataEpoch'); u0 = p.evaluate('cloud.user&&cloud.user.email'); ev = {}
        if variant == 'deadline':
            p.wait_for_function("__bsdk.reqs.some(r=>r.write&&r.outcome==='rejected')", timeout=DEADLINE_MS + 15000)
        elif variant == 'logout':
            # candidate's own logout path (confirm accepted). Not awaited: its dataOp queues behind the held upload.
            p.evaluate("()=>{window.__so=null;cloudSignOut().then(v=>{window.__so={v};},e=>{window.__so={err:String(e.message)};});}")
            p.wait_for_function('cloud.user===null', timeout=15000)
            need(p.evaluate('cloud.user') is None, 'FP-05-LOGOUT-USER'); need(p.evaluate('dataEpoch') > e0, 'FP-05-LOGOUT-EPOCH')
        elif variant == 'switch':
            p.evaluate("cloud.au.signOut(cloud.auth)")
            p.evaluate("([e,pw])=>cloud.au.signInWithEmailAndPassword(cloud.auth,e,pw).then(r=>setCloudUser(r.user))", [USERS['b'], SYN_LOGIN_PW])
            need(p.evaluate('cloud.user.email') == USERS['b'], 'FP-05-SWITCH-USER'); need(p.evaluate('dataEpoch') > e0, 'FP-05-SWITCH-EPOCH')
        elif variant == 'peer-marker':
            q = c.new_page(); q.goto(env.srv.base + '/observer')
            q.evaluate("(m)=>__bsdk.peerBump(m)", json.dumps({'id': 'PEER-OP', 'base': 1, 'started': '2026-01-01T00:00:00.000Z'}))
        p.evaluate("__bsdk.release('metaHold')"); settled(p, n_tx); idle(p)
        if variant == 'logout': p.wait_for_function('window.__so!==null', timeout=20000); ev = {'cloudSignOutResult': p.evaluate('window.__so')}
        after = env.emu.dump(); s = p.evaluate(SNAP); cw = p.evaluate('__bsdk.read()')['values']['bhcs_payroll_cloudwrite']
        need(after == before, 'FP-05-STAGED-WRITES-REACHED-SERVER')
        need('已同步' not in s['status'], 'FP-05-FALSE-SUCCESS')
        if variant == 'peer-marker': need(json.loads(cw)['id'] == 'PEER-OP', 'FP-05-PEER-MARKER-REPLACED')
        cb = [e for e in p.evaluate('__bsdk.events') if e['what'] in ('txCallback:settled', 'runTransaction:sdk-rejected', 'runTransaction:sdk-resolved')]
        out = {'variant': variant, 'epoch': {'before': e0, 'after': s['epoch']}, 'user': {'before': u0, 'after': s['user']}, **ev,
               'remote': {'before': canon(before), 'after': canon(after)}, 'local': {'before': sha(l0), 'after': sha(canonical(p))},
               'transactionEnd': cb, 'status': s['status']}
        c.close(); return out
for _v in ('deadline', 'logout', 'switch', 'peer-marker'): late_cb(_v)

BSDK06_CALL = "cloudConnect(false).then(v=>{window.__fg={v,t:performance.now()};},e=>{window.__fg={err:String(e.message),code:e.code||null,t:performance.now()};})"
@case('BSDK06', 'post-SDK-read canonical check (request-id tracked, inside the real 30 s deadline) held past the deadline: foreground ends, result never applied')
def bsdk06(env):
    c, p = synced(env, 'BSDK06'); out = bsdk06_body(env, p, BSDK06_CALL, 'BSDK06'); out['remoteDigest'] = canon(env.emu.dump()); c.close(); return out
def bsdk06m(env):
    need(env.srv.mutant is not None, 'FP-NEG-MUTATION-NOT-APPLIED')
    c, p = synced(env, 'BSDK06-MUTANT', path='/mutant06/'); out = bsdk06_body(env, p, BSDK06_CALL, 'BSDK06-MUTANT'); c.close(); return out
case('BSDK06-MUTANT', 'negative control for BSDK06 (NEVER DEPLOY mutant without deadline race) must fail at FP-06-FOREGROUND-NOT-ENDED', True, 'negative-control')(
    negative_control('FP-06-FOREGROUND-NOT-ENDED', bsdk06m))

def bsdk07(mode):
    @case('BSDK07-' + mode, f'CLOUD_WRITE intent persistence failure ({mode}): zero SDK writes; canonical == pre-intent baseline (IV/revision changes by legitimate persistSnapshot allowed)')
    def f(env):
        c, p = synced(env, 'BSDK07-' + mode); n0 = p.evaluate('__bsdk.sdk.runTransaction')
        # 1) initial save first and let it settle completely - nothing is armed yet, so it can never wait on a gate
        p.evaluate("()=>{state.settings.bsdk07='edit';return save();}"); idle(p)
        need(p.evaluate('__bsdk.sdk.runTransaction') == n0, 'FP-07-PRE-UPLOAD', 'auto-upload not suppressed')
        before = env.emu.dump(); q = None
        if mode in ('snapshot-cas', 'intent-cas'): q = c.new_page(); q.goto(env.srv.base + '/observer')
        # 2) arm only now
        if mode == 'snapshot-cas': p.evaluate("()=>__bsdk.armSnapshotCas('cloudPushLocked')"); p.evaluate('__bsdk.armIntent(null)')
        elif mode == 'intent-cas': p.evaluate("__bsdk.gate('intentCas')"); p.evaluate("__bsdk.armIntent('intentCas')")
        else: p.evaluate('__bsdk.armIntent(null)'); p.evaluate('(m)=>__bsdk.cloudWriteFault(m)', mode)
        # 3) start overwrite, 4) wait gate, peer tab writes, release
        p.evaluate('openCloud()'); p.click('#cloudPushBtn'); peer = None; gate = None
        if q:
            g = 'snapCas' if mode == 'snapshot-cas' else 'intentCas'
            p.wait_for_function('(g)=>__bsdk.gates[g].reached', arg=g, timeout=30000)
            gate = p.evaluate("(g)=>({reached:__bsdk.gates[g].reached, stack:__bsdk.gates[g].stack||null})", g)
            if mode == 'snapshot-cas':
                need(gate['stack'] and any(f.endswith('cloudPushLocked') for f in gate['stack']), 'FP-07-WRONG-GATE-CALLER', json.dumps(gate))
                need(p.evaluate('__bsdk.sdk.runTransaction') == n0 and p.evaluate('__bsdk.intentBaseline===undefined'), 'FP-07-GATE-ORDER', 'gate reached after intent/SDK')
            peer = q.evaluate('__bsdk.peerBump()'); p.evaluate('(g)=>__bsdk.release(g)', g)
        idle(p); p.wait_for_timeout(2600)
        need(p.evaluate('__bsdk.sdk.runTransaction') == n0, 'FP-07-SDK-WRITE-STARTED'); need(env.emu.dump() == before, 'FP-07-REMOTE-CHANGED')
        fault = p.evaluate('__bsdk.fault||null')
        if mode in ('abort-after-success', 'quota'): need(fault['hits'] == 1, 'FP-07-FAULT-NOT-REACHED')
        if mode == 'abort-after-success': need(fault['requestSucceeded'] and fault['aborted'], 'FP-07-ABORT-NOT-OBSERVED')
        base = p.evaluate('__bsdk.snapBaseline') if mode == 'snapshot-cas' else p.evaluate('__bsdk.intentBaseline')
        need(base is not None, 'FP-07-NO-BASELINE', 'expected gate/intent never reached')
        now_c = canonical(p); need(now_c == base, 'FP-07-CANONICAL-CHANGED')
        s = p.evaluate(SNAP); need('已同步' not in s['status'], 'FP-07-FALSE-SUCCESS')
        out = {'fault': fault, 'gate': gate, 'snapCalls': p.evaluate('__bsdk.snapCalls||null'), 'peerRevision': peer, 'status': s['status'],
               'baselineDigest': sha(base), 'canonicalDigest': sha(now_c), 'remote': canon(before), 'note': 'synthetic quota, NOT real exhaustion' if mode == 'quota' else ''}
        c.close(); return out
for _m in ('abort-after-success', 'quota', 'snapshot-cas', 'intent-cas'): bsdk07(_m)

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--candidate-root', required=True); ap.add_argument('--output', required=True)
    ap.add_argument('--case', action='append', default=[]); ap.add_argument('--no-sdk-only', action='store_true'); ap.add_argument('--timeout-seconds', type=int, default=2400)
    a = ap.parse_args()
    if os.geteuid() == 0: print('refusing root'); return 3
    os.makedirs(a.output, exist_ok=False)
    recs = []; f = open(os.path.join(a.output, 'results.jsonl'), 'x', buffering=1); lk = threading.Lock()
    def log(r):
        with lk: recs.append(r); f.write(json.dumps(r, ensure_ascii=False) + '\n')
    def watchdog(): log({'kind': 'suite', 'status': 'FAIL', 'reason': 'hard-total-timeout', 'at': now()}); f.flush(); os._exit(124)
    wd = threading.Timer(a.timeout_seconds, watchdog); wd.daemon = True; wd.start()
    root = os.path.abspath(a.candidate_root); app = open(os.path.join(root, 'index.html'), 'rb').read()
    ok, pre = preflight(root); log({'kind': 'preflight', 'ok': ok, 'at': now(), **pre})
    picked = [x for x in CASES if (not a.case or any(x['id'].startswith(s) for s in a.case)) and (not a.no_sdk_only or not x['needs_sdk'])]
    if not picked: log({'kind': 'suite', 'status': 'FAIL', 'reason': 'empty selection'}); print('no cases selected'); f.close(); os._exit(2)
    sdk_cases = [x for x in picked if x['needs_sdk']]
    if sdk_cases and not ok:
        for x in sdk_cases: log({'kind': 'case', 'id': x['id'], 'title': x['title'], 'caseKind': x['kind'], 'status': 'BLOCKED', 'reason': 'preflight', 'missing': pre['missing'], 'at': now()})
        picked = [x for x in picked if not x['needs_sdk']]
    env = Env(); env.records = recs; env.log = log; env.contexts = []; env.fixture_path = os.path.join(root, 'tests', 'idb-browser', 'fixture_A.json')
    sdk_dir = os.path.join(root, 'tests', 'isolated-integration', 'node_modules', 'firebase') if ok else None
    env.srv = Server(app, sdk_dir, open(env.fixture_path, 'rb').read())
    log({'kind': 'run', 'at': now(), 'appSha256Start': sha(app), 'hooksSha256': sha(HOOKS), 'runnerSha256': sha(open(__file__, 'rb').read()),
         'netpolicySha256': sha(open(netpolicy.__file__, 'rb').read()), 'mutant06PatternCount': env.srv.mutant_applied,
         'mutant06Sha256': sha(env.srv.mutant) if env.srv.mutant else None, 'project': PROJECT, 'ports': PORTS})
    bad = 0; emu = None; shutdown = None
    from playwright.sync_api import sync_playwright
    try:
        if any(x['needs_sdk'] for x in picked): emu = env.emu = Emulators(root, a.output); emu.start(); emu.reset()
        with sync_playwright() as pw:
            env.b = pw.chromium.launch(headless=True, chromium_sandbox=True, args=['--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1'])
            log({'kind': 'browser', 'version': env.b.version, 'chromiumSandbox': True})
            for x in picked:
                t0 = time.monotonic(); rec = {'kind': 'case', 'id': x['id'], 'title': x['title'], 'caseKind': x['kind'], 'startedAt': now()}
                env.contexts = []
                try: out = x['fn'](env); rec.update(out or {}); rec['status'] = 'PASS'
                except Blocked as e: rec.update(status='BLOCKED', error=str(e))
                except Fail as e: rec.update(status='FAIL', failPoint=str(e).split(':', 1)[0], error=str(e)[:800])
                except Exception as e: rec.update(status='FAIL', failPoint='EXCEPTION', error=str(e)[:800], trace=traceback.format_exc()[-1500:])
                closed, errs = 0, []
                for ctx in env.contexts:
                    try: ctx.close(); closed += 1
                    except Exception as e: errs.append(str(e)[:120])
                rec['cleanup'] = {'contextsCreated': len(env.contexts), 'contextsClosedByRunner': closed, 'errors': errs}
                if emu:
                    try: rec['remoteAdminDumpDigestAtEnd'] = canon(emu.dump())
                    except Exception as e: rec['remoteAdminDumpDigestAtEnd'] = 'unavailable: ' + str(e)[:80]
                rec['endedAt'] = now(); rec['seconds'] = round(time.monotonic() - t0, 2); log(rec); bad += rec['status'] != 'PASS'
                print(f"{rec['status']}\t{x['id']}\t{rec['seconds']}s\t{str(rec.get('error', ''))[:200]}", flush=True)
            env.b.close()
    finally:
        if emu: shutdown = emu.stop()
        log({'kind': 'shutdown', 'at': now(), 'emulatorPortsStillOpen': shutdown, 'appSha256End': sha(open(os.path.join(root, 'index.html'), 'rb').read())})
    blocked = sum(1 for r in recs if r.get('kind') == 'case' and r['status'] == 'BLOCKED')
    if shutdown and any(shutdown.values()): bad += 1
    code = 1 if bad else (3 if blocked else 0)
    log({'kind': 'suite', 'status': 'PASS' if code == 0 else ('FAIL' if bad else 'BLOCKED'), 'failures': bad, 'blocked': blocked, 'exitCode': code, 'at': now()})
    f.close(); os._exit(code)

if __name__ == '__main__':
    main()
