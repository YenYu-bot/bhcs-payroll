"""Exact egress allowlist for the BSDK browser runs. Default deny.
Parses scheme / host / port / raw path / query parameters; never substring-matches the whole URL."""
import re
from urllib.parse import urlsplit, parse_qs

PROJECT = 'demo-bhcs-payroll-isolated'
FS_DB = f'projects/{PROJECT}/databases/(default)'
AUTH_PORT, FST_PORT = 19099, 18080
LOCAL_PATHS = {'/app/', '/observer', '/fixture_A.json', '/mutant06/'}
FORBIDDEN_PREFIX = '/__candidate_fbLoad_forbidden__/'
AUTH_PATH = re.compile(r'^/(identitytoolkit\.googleapis\.com/v1/accounts:(signInWithPassword|lookup|signUp|update|delete)'
                       r'|securetoken\.googleapis\.com/v1/token)$')
FS_REST = re.compile(r'^/v1/projects/' + re.escape(PROJECT) + r'/databases/\(default\)/documents(:[A-Za-z]+|/[A-Za-z0-9_\-]+(/[A-Za-z0-9_\-]+)*)?$')
FS_CHANNEL = re.compile(r'^/google\.firestore\.v1\.Firestore/(Listen|Write)/channel$')
PARAM_NAME = re.compile(r'^[A-Za-z$][A-Za-z0-9_\-$]*$')
def _params_clean(q, need_db):
    """Every parameter name is plain; 'database' (if required) occurs once and equals FS_DB exactly; no other value may
    mention a project path (blocks decoy / smuggled project ids)."""
    if need_db and q.get('database') != [FS_DB]: return False, 'database-param'
    for k, vs in q.items():
        if not PARAM_NAME.match(k): return False, 'param-name'
        for v in vs:
            if 'projects' in v and not (k == 'database' and v == FS_DB): return False, 'param-mentions-project'
    return True, ''

def decide(url, server_port):
    """Return (allowed: bool, reason: str)."""
    try: u = urlsplit(url); port = u.port
    except ValueError: return False, 'unparseable'
    if u.username is not None or u.password is not None or '@' in u.netloc: return False, 'userinfo'
    if u.fragment: return False, 'fragment'
    if u.scheme != 'http' or u.hostname != '127.0.0.1' or u.netloc not in (f'127.0.0.1:{port}',): return False, 'host/scheme'
    p, low = u.path, u.path.lower()
    if '%' in p or '//' in p or '\\' in p or re.search(r'(^|/)\.\.?(/|$)', p): return False, 'path-encoding/traversal'
    try: q = parse_qs(u.query, keep_blank_values=True, strict_parsing=bool(u.query))
    except ValueError: return False, 'query-malformed'
    if port == server_port:
        if u.query: return False, 'local-query'
        if p in LOCAL_PATHS or (p.startswith(FORBIDDEN_PREFIX) and p.count('/') == 2): return True, 'local-server'
        return False, 'local-unknown-path'
    if port == AUTH_PORT:
        if not AUTH_PATH.match(p): return False, 'auth-path'
        if set(q) != {'key'} or q['key'] != ['demo-key']: return False, 'auth-key'
        return True, 'auth-emulator'
    if port == FST_PORT:
        if FS_REST.match(p):
            ok, why = _params_clean(q, False)
            return (True, 'firestore-emulator-rest') if ok else (False, 'firestore-rest-' + why)
        if FS_CHANNEL.match(p):
            ok, why = _params_clean(q, True)
            return (True, 'firestore-emulator-channel') if ok else (False, 'firestore-channel-' + why)
        return False, 'firestore-path'
    return False, 'default-deny'

SP = 41234
POSITIVE = [
    f'http://127.0.0.1:{SP}/app/',
    f'http://127.0.0.1:{SP}/__candidate_fbLoad_forbidden__/firebase-app.js',
    'http://127.0.0.1:19099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=demo-key',
    'http://127.0.0.1:19099/securetoken.googleapis.com/v1/token?key=demo-key',
    f'http://127.0.0.1:18080/v1/projects/{PROJECT}/databases/(default)/documents/payroll/meta',
    f'http://127.0.0.1:18080/v1/projects/{PROJECT}/databases/(default)/documents:commit',
    'http://127.0.0.1:18080/google.firestore.v1.Firestore/Listen/channel?database=projects%2Fdemo-bhcs-payroll-isolated%2Fdatabases%2F(default)&VER=8&RID=1&CVER=22&X-HTTP-Session-Id=gsessionid&zx=a&t=1',
    'http://127.0.0.1:18080/google.firestore.v1.Firestore/Write/channel?database=projects%2Fdemo-bhcs-payroll-isolated%2Fdatabases%2F(default)&gsessionid=abc&SID=x&RID=rpc&AID=3&CI=0&TYPE=xmlhttp&zx=b&t=1',
]
NEGATIVE = {
    'query-spoof-project': 'http://127.0.0.1:18080/v1/projects/bhcs-payroll/databases/(default)/documents/payroll/meta?x=projects/demo-bhcs-payroll-isolated/',
    'query-spoof-in-rest': f'http://127.0.0.1:18080/v1/projects/{PROJECT}/databases/(default)/documents/payroll/meta?database=projects/bhcs-payroll/databases/(default)',
    'channel-prod-db-with-demo-decoy': 'http://127.0.0.1:18080/google.firestore.v1.Firestore/Listen/channel?database=projects%2Fbhcs-payroll%2Fdatabases%2F(default)&x=projects%2Fdemo-bhcs-payroll-isolated%2Fdatabases%2F(default)',
    'channel-duplicate-database': 'http://127.0.0.1:18080/google.firestore.v1.Firestore/Write/channel?database=projects%2Fdemo-bhcs-payroll-isolated%2Fdatabases%2F(default)&database=projects%2Fbhcs-payroll%2Fdatabases%2F(default)',
    'channel-decoy-in-headers-param': 'http://127.0.0.1:18080/google.firestore.v1.Firestore/Write/channel?database=projects%2Fdemo-bhcs-payroll-isolated%2Fdatabases%2F(default)&%24httpHeaders=x-goog-request-params%3Adatabase%3Dprojects%252Fbhcs-payroll',
    'channel-project-suffix': 'http://127.0.0.1:18080/google.firestore.v1.Firestore/Listen/channel?database=projects%2Fdemo-bhcs-payroll-isolated-evil%2Fdatabases%2F(default)',
    'rest-project-suffix': 'http://127.0.0.1:18080/v1/projects/demo-bhcs-payroll-isolated-evil/databases/(default)/documents/payroll/meta',
    'rest-traversal': f'http://127.0.0.1:18080/v1/projects/{PROJECT}/databases/(default)/documents/../../../bhcs-payroll/databases/(default)/documents/x',
    'rest-encoded-slash': 'http://127.0.0.1:18080/v1/projects/demo-bhcs-payroll-isolated%2F..%2Fbhcs-payroll/databases/(default)/documents/x',
    'auth-duplicate-key': 'http://127.0.0.1:19099/identitytoolkit.googleapis.com/v1/accounts:lookup?key=prodkey&key=demo-key',
    'auth-key-in-other-param': 'http://127.0.0.1:19099/identitytoolkit.googleapis.com/v1/accounts:lookup?foo=key=demo-key',
    'auth-key-suffix': 'http://127.0.0.1:19099/identitytoolkit.googleapis.com/v1/accounts:lookup?key=demo-key-evil',
    'auth-key-in-fragment': 'http://127.0.0.1:19099/identitytoolkit.googleapis.com/v1/accounts:lookup?k=1#key=demo-key',
    'auth-key-in-path-only': 'http://127.0.0.1:19099/identitytoolkit.googleapis.com/v1/accounts:lookup/key=demo-key',
    'auth-unknown-endpoint': 'http://127.0.0.1:19099/emulator/v1/projects/demo-bhcs-payroll-isolated/accounts?key=demo-key',
    'host-suffix': 'http://127.0.0.1.evil.test:18080/v1/projects/demo-bhcs-payroll-isolated/databases/(default)/documents/x',
    'host-localhost': 'http://localhost:18080/v1/projects/demo-bhcs-payroll-isolated/databases/(default)/documents/x',
    'host-ipv6': 'http://[::1]:18080/v1/projects/demo-bhcs-payroll-isolated/databases/(default)/documents/x',
    'userinfo': 'http://demo@127.0.0.1:18080/v1/projects/demo-bhcs-payroll-isolated/databases/(default)/documents/x',
    'https-scheme': 'https://127.0.0.1:18080/v1/projects/demo-bhcs-payroll-isolated/databases/(default)/documents/x',
    'wrong-port': 'http://127.0.0.1:18081/v1/projects/demo-bhcs-payroll-isolated/databases/(default)/documents/x',
    'emulator-admin-delete': 'http://127.0.0.1:18080/emulator/v1/projects/demo-bhcs-payroll-isolated/databases/(default)/documents',
    'prod-firestore': 'https://firestore.googleapis.com/v1/projects/bhcs-payroll/databases/(default)/documents/payroll/meta?x=demo-bhcs-payroll-isolated',
    'prod-identitytoolkit-demo-key': 'https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=demo-key',
    'gstatic': 'https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js',
    'local-unknown-path': f'http://127.0.0.1:{SP}/secret',
    'local-forbidden-nested': f'http://127.0.0.1:{SP}/__candidate_fbLoad_forbidden__/x/../../app/',
}

def self_test():
    rows, ok = [], True
    for u in POSITIVE:
        a, why = decide(u, SP); rows.append({'kind': 'positive', 'url': u, 'allowed': a, 'reason': why}); ok &= a
    for k, u in NEGATIVE.items():
        a, why = decide(u, SP); rows.append({'kind': 'negative', 'name': k, 'url': u, 'allowed': a, 'reason': why}); ok &= not a
    return ok, rows

if __name__ == '__main__':
    import json, sys
    ok, rows = self_test()
    for r in rows: print(json.dumps(r, ensure_ascii=False))
    print('NETPOLICY_SELFTEST', 'PASS' if ok else 'FAIL'); sys.exit(0 if ok else 1)
