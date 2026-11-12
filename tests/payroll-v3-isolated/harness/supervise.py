#!/usr/bin/env python3
"""Rerunnable supervisor for the BSDK suite.

Ownership model (no UID-wide cleanup):
- the supervisor marks itself a Linux child SUBREAPER (prctl PR_SET_CHILD_SUBREAPER), so every process started by this
  run - including ones that detach into their own session/process group (Playwright starts Chromium detached) - stays
  a descendant of the supervisor and is re-parented to it if its parent dies;
- "owned" = current descendants of the supervisor's PID. Only owned processes are ever signalled;
- processes of the same UID that were not started by this run are never signalled, even if they hold a suite port.
Failure rules: hard timeout -> 124; owned leftover process or owned listener after the child exits -> 1 (then killed);
suite port held by a FOREIGN process (before or after) -> 1, NOT killed. Otherwise the child's real exit code.
Usage: supervise.py --out DIR --timeout SECONDS -- CMD ...
"""
import argparse, ctypes, glob, json, os, signal, socket, subprocess, sys, time

PORTS = {'auth': 19099, 'firestore': 18080, 'hub': 14400, 'logging': 14500}
PR_SET_CHILD_SUBREAPER = 36

def ts(): return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def port_open(p):
    s = socket.socket(); s.settimeout(0.3)
    try: s.connect(('127.0.0.1', p)); return True
    except OSError: return False
    finally: s.close()

def proc_table():
    t = {}
    for d in glob.glob('/proc/[0-9]*'):
        try:
            st = open(d + '/stat').read(); rest = st.rsplit(')', 1)[1].split()
            cmd = open(d + '/cmdline', 'rb').read().replace(b'\0', b' ').decode(errors='replace').strip()
            t[int(d[6:])] = {'ppid': int(rest[1]), 'state': rest[0], 'pgid': int(rest[2]), 'sid': int(rest[3]), 'uid': os.stat(d).st_uid, 'cmd': cmd[:160]}
        except (OSError, IndexError, ValueError): pass
    return t

def descendants(root):
    t = proc_table(); kids = {}
    for pid, i in t.items(): kids.setdefault(i['ppid'], []).append(pid)
    out, stack = [], list(kids.get(root, []))
    while stack:
        p = stack.pop(); out.append(p); stack.extend(kids.get(p, []))
    return [{'pid': p, **t[p]} for p in sorted(out) if p in t]

def listeners(port):
    inodes = set()
    for f in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            for line in open(f).read().splitlines()[1:]:
                c = line.split()
                if c[3] == '0A' and int(c[1].rsplit(':', 1)[1], 16) == port: inodes.add(c[9])
        except OSError: pass
    pids = set()
    for fd in glob.glob('/proc/[0-9]*/fd/*'):
        try:
            if os.readlink(fd)[8:-1] in inodes: pids.add(int(fd.split('/')[2]))
        except OSError: pass
    return sorted(pids)

def reap():
    n = 0
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0: return n
            n += 1
        except ChildProcessError: return n

def kill_owned(sig):
    me = os.getpid(); hit = []
    for x in descendants(me):
        try: os.kill(x['pid'], sig); hit.append(x['pid'])
        except ProcessLookupError: pass
    return hit

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--timeout', type=float, required=True)
    ap.add_argument('--grace', type=float, default=3.0); ap.add_argument('cmd', nargs=argparse.REMAINDER)
    a = ap.parse_args(); cmd = a.cmd[1:] if a.cmd[:1] == ['--'] else a.cmd
    if not cmd: print('no command'); return 2
    os.makedirs(a.out, exist_ok=True)
    libc = ctypes.CDLL(None, use_errno=True)
    sub = libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0
    rep = {'cmd': cmd, 'timeoutSeconds': a.timeout, 'startedAt': ts(), 'uid': os.getuid(), 'supervisorPid': os.getpid(),
           'subreaper': sub, 'ownershipModel': 'descendants of supervisorPid (subreaper); never UID-wide'}
    def finish(**kw):
        rep.update(kw); rep['endedAt'] = ts()
        json.dump(rep, open(os.path.join(a.out, 'supervisor.json'), 'w'), indent=1, ensure_ascii=False)
        print(json.dumps({k: rep.get(k) for k in ('childExitCode', 'timedOut', 'seconds', 'ownedLeftovers', 'ownedListeners', 'foreignListeners', 'final', 'reason', 'finalExit')}))
        return rep['finalExit']
    if not sub: return finish(final='FAIL', reason='cannot become subreaper; refusing to run without process-tree ownership', finalExit=1)
    busy = {n: listeners(p) or ['unknown-owner'] for n, p in PORTS.items() if port_open(p)}
    rep['portsBusyBeforeStart'] = busy
    if busy: return finish(final='FAIL', reason='suite ports busy before start (foreign process; not touched)', finalExit=1)
    t0 = time.monotonic(); timed_out = False
    with open(os.path.join(a.out, 'child.stdout'), 'w') as o, open(os.path.join(a.out, 'child.stderr'), 'w') as e:
        p = subprocess.Popen(cmd, stdout=o, stderr=e, start_new_session=True); rep['childPid'] = p.pid
        try: code = p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try: os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            rep['timeoutSigtermOwned'] = kill_owned(signal.SIGTERM)
            try: p.wait(timeout=a.grace)
            except subprocess.TimeoutExpired: pass
            time.sleep(0.2); rep['timeoutSigkillOwned'] = kill_owned(signal.SIGKILL); code = p.wait()
    rep.update(childExitCode=code, timedOut=timed_out, seconds=round(time.monotonic() - t0, 3))
    time.sleep(0.5); rep['reapedBeforeCheck'] = reap()
    owned = [x for x in descendants(os.getpid()) if x['state'] != 'Z']
    owned_pids = {x['pid'] for x in owned}
    owned_l, foreign_l = {}, {}
    for n, pt in PORTS.items():
        if not port_open(pt): continue
        ls = listeners(pt); mine = [q for q in ls if q in owned_pids]
        if mine: owned_l[n] = mine
        if [q for q in ls if q not in owned_pids] or not ls: foreign_l[n] = [q for q in ls if q not in owned_pids] or ['unknown-owner']
    rep.update(ownedLeftovers=owned, ownedListeners=owned_l, foreignListeners=foreign_l)
    rep['cleanupKilledOwned'] = kill_owned(signal.SIGKILL) if owned else []
    time.sleep(0.5); rep['reapedAfterCleanup'] = reap()
    rep['ownedAfterCleanup'] = descendants(os.getpid())
    rep['portsOpenAfterCleanup'] = {n: port_open(pt) for n, pt in PORTS.items()}
    if timed_out: return finish(final='FAIL', reason='hard total timeout', finalExit=124)
    if owned: return finish(final='FAIL', reason='owned leftover process/listener after child exit (killed)', finalExit=1)
    if foreign_l: return finish(final='FAIL', reason='suite port held by a foreign process (not touched)', finalExit=1)
    return finish(final='PASS' if code == 0 else 'NONZERO', reason='child exit code', finalExit=code)

if __name__ == '__main__':
    sys.exit(main())
