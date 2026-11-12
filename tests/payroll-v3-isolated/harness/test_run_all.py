#!/usr/bin/env python3
"""Controlled negative tests of run_all.sh aggregation with a fake runner (BSDK_RUNNER). Real self-tests still run.
Proves: inner exit 3 -> outer 3 (never 0); inner 1 -> 1; inner 0 -> 0; empty selection returning 0 -> 1;
candidate hash mismatch -> 1. The fake runner never touches a browser, SDK or network."""
import json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.join(HERE, 'run_all.sh')
FAKE = r'''import json,os,sys
a=sys.argv; out=a[a.index('--output')+1]; os.makedirs(out)
code=int(os.environ['FAKE_EXIT']); empty='NO_SUCH_CASE' in a
if empty: sys.exit(int(os.environ.get('FAKE_EMPTY_EXIT','2')))
st={0:'PASS',3:'BLOCKED'}.get(code,'FAIL')
with open(os.path.join(out,'results.jsonl'),'w') as f:
    f.write(json.dumps({'kind':'case','id':'FAKE1','status':st})+'\n'); f.write(json.dumps({'kind':'suite','status':st,'exitCode':code})+'\n')
sys.exit(code)
'''
def main():
    root = tempfile.mkdtemp(prefix='runalltest-'); fake = os.path.join(root, 'fake_runner.py'); open(fake, 'w').write(FAKE)
    ign = shutil.ignore_patterns('node_modules', '__pycache__')
    good = os.path.join(root, 'cand-good'); shutil.copytree(sys.argv[1], good, ignore=ign)
    bad = os.path.join(root, 'cand-bad'); shutil.copytree(sys.argv[1], bad, ignore=ign); open(os.path.join(bad, 'index.html'), 'w').write('tampered')
    cases = [('inner-3-reported-3', good, 3, 2, 3), ('inner-1-reported-1', good, 1, 2, 1), ('inner-0-reported-0', good, 0, 2, 0),
             ('empty-selection-wrong-exit-0', good, 0, 0, 1), ('hash-mismatch', bad, 0, 2, 1)]
    ok = True; rows = []
    for name, cand, fx, fe, expect in cases:
        o = os.path.join(root, 'out-' + name)
        r = subprocess.run(['bash', RUN, cand, o], env=dict(os.environ, BSDK_RUNNER=fake, FAKE_EXIT=str(fx), FAKE_EMPTY_EXIT=str(fe)), capture_output=True, text=True, timeout=600)
        s = json.load(open(os.path.join(o, 'summary.json')))
        g = r.returncode == expect and s['exit'] == expect; ok &= g
        rows.append({'case': name, 'pass': g, 'innerExit': fx, 'emptyExit': fe, 'expectedOuter': expect, 'outerExit': r.returncode,
                     'nonPassChecks': [c['check'] for c in s['checks'] if c['status'] != 'PASS']})
    for x in rows: print(json.dumps(x, ensure_ascii=False))
    print('RUN_ALL_SELFTEST', 'PASS' if ok else 'FAIL'); return 0 if ok else 1
if __name__ == '__main__':
    sys.exit(main())
