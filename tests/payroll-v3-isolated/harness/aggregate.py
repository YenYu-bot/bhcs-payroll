#!/usr/bin/env python3
"""Aggregate run_all.sh results into summary.json and the final exit code. Every check is independent:
the empty-selection run must exit exactly 2; the full run's real supervisor exit decides PASS(0)/BLOCKED(3)/FAIL(other);
self-tests must exit 0; index.html hash must equal the expected value before AND after."""
import json, os, sys
O, EXP = sys.argv[1], sys.argv[2]
def rd(n, default=None):
    try: return open(os.path.join(O, n)).read().strip()
    except OSError: return default
def code(n):
    v = rd(n); return int(v) if v is not None and v.lstrip('-').isdigit() else None
checks = []
def add(name, status, **kw): checks.append({'check': name, 'status': status, **kw})
for n in ('before', 'after'):
    h = rd(f'index-sha-{n}.txt'); add(f'index-sha-{n}', 'PASS' if h == EXP else 'FAIL', value=h, expected=EXP)
for n in ('netpolicy-selftest', 'supervisor-selftest', 'provision-paths', 'sandbox-check'):
    c = code(n + '.exit'); add(n, 'PASS' if c == 0 else 'FAIL', exit=c)
sb = rd('sandbox-check.txt', '')
add('sandbox-renderer-seccomp', 'PASS' if any('--type=renderer' in l and 'Seccomp= 2' in l and 'no-sandbox-flag= False' in l for l in sb.splitlines()) else 'FAIL')
c = code('sup-empty.exit'); add('empty-selection-exit-2', 'PASS' if c == 2 else 'FAIL', exit=c)
c = code('sup-full.exit'); st = {0: 'PASS', 3: 'BLOCKED'}.get(c, 'FAIL')
sup = {}
try: sup = json.load(open(os.path.join(O, 'sup-full', 'supervisor.json')))
except Exception: st = 'FAIL'
add('full-suite', st, supervisorExit=c, childExitCode=sup.get('childExitCode'), supervisorFinal=sup.get('final'), reason=sup.get('reason'))
cases = {}
try:
    for l in open(os.path.join(O, 'out-full', 'results.jsonl')):
        r = json.loads(l)
        if r.get('kind') == 'case': cases[r['id']] = r['status']
        if r.get('kind') == 'suite': add('runner-suite-record', {'PASS': 'PASS', 'BLOCKED': 'BLOCKED'}.get(r['status'], 'FAIL'), runnerExit=r.get('exitCode'))
except OSError: add('runner-results', 'FAIL', error='out-full/results.jsonl missing')
if st == 'BLOCKED' and not any(v == 'BLOCKED' for v in cases.values()): add('blocked-consistency', 'FAIL', error='exit 3 without BLOCKED cases')
if any(v == 'FAIL' for v in cases.values()) and st != 'FAIL': add('fail-consistency', 'FAIL', error='FAIL case but suite not FAIL')
statuses = [x['status'] for x in checks]
final = 1 if 'FAIL' in statuses else (3 if 'BLOCKED' in statuses else 0)
summary = {'final': {0: 'PASS', 1: 'FAIL', 3: 'BLOCKED'}[final], 'exit': final, 'checks': checks, 'cases': cases}
json.dump(summary, open(os.path.join(O, 'summary.json'), 'w'), indent=1, ensure_ascii=False)
for x in checks: print(f"{x['status']:8} {x['check']}")
print('RUN_ALL', summary['final']); sys.exit(final)
