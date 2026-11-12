#!/usr/bin/env python3
"""Self-tests of supervise.py (harness self-test; no SDK). Exit 0 only if every expectation holds.
Covers exit-code propagation, timeout, detached descendants (setsid escape), owned residual listener, and that FOREIGN
same-UID processes (not started by the supervised run) are never signalled."""
import json, os, shlex, signal, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); SUP = os.path.join(HERE, 'supervise.py'); PY = sys.executable
def alive(pid):
    try:
        st = open(f'/proc/{pid}/stat').read().rsplit(')', 1)[1].split()[0]; return st != 'Z'
    except OSError: return False
def detach(code, pidfile):
    """child command: spawn a detached (new session) grandchild running `code`, record its pid, then exit/linger."""
    return [PY, '-c', f"import subprocess,sys;p=subprocess.Popen([sys.executable,'-c',{code!r}],start_new_session=True);open({pidfile!r},'w').write(str(p.pid))"]
LISTEN = "import socket,time;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',{port}));s.listen();time.sleep(600)"

def run_sup(d, t, cmd):
    r = subprocess.run([PY, SUP, '--out', d, '--timeout', str(t), '--', *cmd], capture_output=True, text=True, timeout=120)
    return r.returncode, json.load(open(os.path.join(d, 'supervisor.json')))

def main():
    root = tempfile.mkdtemp(prefix='suptest-'); results = []; ok = True
    def record(name, good, rc, rep, extra=None):
        nonlocal ok; ok &= bool(good)
        results.append({'case': name, 'pass': bool(good), 'supervisorExit': rc, **(extra or {}),
                        'report': {k: rep.get(k) for k in ('childExitCode', 'timedOut', 'seconds', 'subreaper', 'ownedLeftovers', 'ownedListeners', 'foreignListeners',
                                                            'cleanupKilledOwned', 'timeoutSigkillOwned', 'ownedAfterCleanup', 'portsOpenAfterCleanup', 'portsBusyBeforeStart', 'final', 'reason', 'finalExit')}})
    d = os.path.join(root, 'exit0'); rc, rep = run_sup(d, 30, [PY, '-c', 'print(1)']); record('clean-exit-0', rc == 0 and rep['final'] == 'PASS', rc, rep)
    d = os.path.join(root, 'exit3'); rc, rep = run_sup(d, 30, [PY, '-c', 'import sys;sys.exit(3)']); record('child-exit-3-propagated', rc == 3 and rep['childExitCode'] == 3, rc, rep)
    d = os.path.join(root, 'timeout'); rc, rep = run_sup(d, 3, [PY, '-c', 'import time;time.sleep(60)']); record('hard-timeout-124', rc == 124 and rep['timedOut'], rc, rep)
    pf = os.path.join(root, 'det.pid'); d = os.path.join(root, 'timeout-detached')
    rc, rep = run_sup(d, 3, ['bash', '-c', shlex.join(detach('import time;time.sleep(600)', pf)) + '; sleep 60'])
    gp = int(open(pf).read()); record('timeout-kills-detached-descendant', rc == 124 and not alive(gp) and rep['ownedAfterCleanup'] == [], rc, rep, {'detachedPid': gp, 'detachedAliveAfter': alive(gp)})
    pf = os.path.join(root, 'leak.pid'); d = os.path.join(root, 'leak')
    rc, rep = run_sup(d, 30, detach(LISTEN.format(port=14400), pf) + []); time.sleep(0.2)
    gp = int(open(pf).read())
    record('owned-detached-listener-after-exit-0', rc == 1 and rep['childExitCode'] == 0 and rep['ownedListeners'].get('hub') == [gp] and not alive(gp)
           and rep['portsOpenAfterCleanup']['hub'] is False, rc, rep, {'leakPid': gp, 'aliveAfter': alive(gp)})
    foreign = subprocess.Popen([PY, '-c', 'import time;time.sleep(600)'], start_new_session=True); time.sleep(0.3)
    d = os.path.join(root, 'foreign-proc'); rc, rep = run_sup(d, 30, [PY, '-c', 'print(1)'])
    record('foreign-same-uid-process-untouched', rc == 0 and alive(foreign.pid) and foreign.pid not in [x['pid'] for x in rep['ownedLeftovers']], rc, rep,
           {'foreignPid': foreign.pid, 'foreignAliveAfter': alive(foreign.pid)})
    fl = subprocess.Popen([PY, '-c', LISTEN.format(port=14500)], start_new_session=True); time.sleep(0.5)
    d = os.path.join(root, 'foreign-port'); rc, rep = run_sup(d, 30, [PY, '-c', 'print(1)'])
    record('foreign-listener-on-suite-port-fails-but-untouched', rc == 1 and alive(fl.pid) and 'logging' in rep['portsBusyBeforeStart'], rc, rep,
           {'foreignListenerPid': fl.pid, 'foreignAliveAfter': alive(fl.pid)})
    for x in (foreign, fl): x.kill(); x.wait()
    for r in results: print(json.dumps(r, ensure_ascii=False))
    print('SUPERVISOR_SELFTEST', 'PASS' if ok else 'FAIL'); return 0 if ok else 1
if __name__ == '__main__':
    sys.exit(main())
