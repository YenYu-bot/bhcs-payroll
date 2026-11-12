#!/usr/bin/env python3
"""Fail-closed Firefox/WebKit sandbox feasibility, then synthetic migration cases.

The pre-app probe uses only a literal blank page. It neither loads candidate bytes
into a browser nor creates the app HTTP server until sandbox evidence passes.
No security-setting changes or guessed sandbox-enabling flags are attempted.
Run under the existing supervisor inside a fresh loopback-only network namespace.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time
import traceback

PINNED_PLAYWRIGHT = '1.56.0'
APP_SHA = '3437f75e85fc64c088ea24a7f5e5e2f7d4824d43f7ddcd299e25356b37784e67'
DISABLED_ENV = (
 'MOZ_DISABLE_CONTENT_SANDBOX', 'MOZ_DISABLE_GMP_SANDBOX',
 'MOZ_DISABLE_RDD_SANDBOX', 'MOZ_DISABLE_GPU_SANDBOX',
 'MOZ_DISABLE_SOCKET_PROCESS_SANDBOX', 'MOZ_DISABLE_NPAPI_SANDBOX',
 'WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS', 'JSC_useSandbox',
)
DISABLED_ARGS = (
 '--no-sandbox', '--disable-sandbox', '--disable-seccomp-filter-sandbox',
 '--disable-setuid-sandbox', '--no-zygote-sandbox',
)

class Blocked(Exception): pass

def check_environment(env, uid):
    reasons=[]
    if uid == 0: reasons.append('root user is prohibited')
    # Reject presence rather than attempting to interpret undocumented values.
    reasons += ['sandbox-related environment override: '+k for k in DISABLED_ENV if k in env]
    return reasons

def split_cmdline(raw: bytes):
    """Chromium-like process titles can also occur here; support NUL argv and a
    rewritten single process title. Tokenize, never substring-match sandbox flags."""
    parts=[s.decode('utf-8','replace') for s in raw.split(b'\0') if s]
    if len(parts)==1:
        try:return shlex.split(parts[0])
        except ValueError:return parts[0].split()
    return parts

def parse_status(text):
    return {line.split(':',1)[0]:line.split(':',1)[1].strip() for line in text.splitlines() if ':' in line}

def inspect_proc(pid, proc_root=Path('/proc')):
    p=Path(proc_root)/str(pid)
    s=parse_status((p/'status').read_text())
    error=None
    try:argv=split_cmdline((p/'cmdline').read_bytes())
    except OSError as e:argv=[];error='cmdline unreadable: '+type(e).__name__
    return {'pid':int(pid),'ppid':int(s['PPid']),'name':s.get('Name',''),
            'uid':[int(x) for x in s.get('Uid','').split()],
            'seccomp':s.get('Seccomp'), 'seccompFilters':s.get('Seccomp_filters'), 'noNewPrivs':s.get('NoNewPrivs'),
            'nspid':[int(x) for x in s.get('NSpid','').split()],
            'argv':argv,'inspectionError':error}

def descendant_ids(records, root_pid):
    descendants=set();changed=True
    while changed:
        changed=False
        for r in records:
            if r['pid']!=root_pid and (r['ppid']==root_pid or r['ppid'] in descendants) and r['pid'] not in descendants:
                descendants.add(r['pid']);changed=True
    return descendants

def target_content(record, engine):
    args=record.get('argv',[])
    if engine=='firefox':return '-contentproc' in args
    if engine=='webkit':return any(Path(x).name=='WebKitWebProcess' for x in args[:2])
    return False

def forbidden_arguments(record):
    return [arg for arg in record.get('argv',[]) if arg.split('=',1)[0] in DISABLED_ARGS]

def gate_records(records, root_pid, engine, uid):
    ds=descendant_ids(records,root_pid)
    owned=[r for r in records if r['pid'] in ds]
    content=[r for r in owned if target_content(r,engine)]
    errors=[]
    baseline=next((r for r in records if r['pid']==root_pid),None)
    try:baseline_filters=int(baseline['seccompFilters'])
    except (TypeError,KeyError,ValueError):baseline_filters=None;errors.append('runner Seccomp_filters baseline unavailable')
    baseline_depth=len(baseline.get('nspid',[])) if baseline else 0
    if baseline_depth==0:errors.append('runner NSpid baseline unavailable')
    by_pid={r['pid']:r for r in records}
    for r in owned:
        if r.get('inspectionError'):errors.append(f"pid {r['pid']} inspection incomplete: {r['inspectionError']}")
        bad=forbidden_arguments(r)
        if bad:errors.append(f"pid {r['pid']} has disabled-sandbox argv: {bad}")
    if not content:errors.append('no identifiable content process in this runner descendant tree')
    for r in content:
        if not r['uid'] or any(v!=uid or v==0 for v in r['uid']):errors.append(f"pid {r['pid']} UID is not the non-root runner UID")
        if r['seccomp']!='2':errors.append(f"pid {r['pid']} Seccomp is not 2")
        try:filters=int(r['seccompFilters'])
        except (TypeError,KeyError,ValueError):filters=None
        if filters is None or baseline_filters is None or filters<=baseline_filters:errors.append(f"pid {r['pid']} has no proven additional seccomp filter over runner baseline")
        parent=by_pid.get(r['ppid'])
        try:parent_filters=int(parent['seccompFilters'])
        except (TypeError,KeyError,ValueError):parent_filters=None
        if filters is None or parent_filters is None or filters<=parent_filters:errors.append(f"pid {r['pid']} has no proven additional seccomp filter over its immediate parent")
        if r['noNewPrivs']!='1':errors.append(f"pid {r['pid']} NoNewPrivs is not 1")
        if baseline_depth==0 or len(r['nspid'])<=baseline_depth:errors.append(f"pid {r['pid']} NSpid does not demonstrate additional PID namespace depth over runner")
    return {'status':'PASS' if not errors else 'BLOCKED','errors':errors,'contentProcesses':content,
            'descendants':owned,'runnerBaseline':baseline,'criteria':['non-root same UID','Seccomp_filters above runner and immediate parent','Seccomp=2','NoNewPrivs=1','NSpid depth above runner','no sandbox-disable argv']}

def process_snapshot():
    records=[];unreadable=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:records.append(inspect_proc(p.name))
        except (OSError,ValueError,KeyError) as e:
            unreadable.append({'pid':p.name,'error':type(e).__name__})
            # Retain ancestry when status is unavailable. Unknown descendants fail closed.
            try:
                raw=(p/'stat').read_text();ppid=int(raw[raw.rfind(')')+2:].split()[1])
                records.append({'pid':int(p.name),'ppid':ppid,'name':'unknown','uid':[p.stat().st_uid],
                                'seccomp':None,'seccompFilters':None,'noNewPrivs':None,'nspid':[],
                                'argv':[],'inspectionError':'status unreadable: '+type(e).__name__})
            except (OSError,ValueError,IndexError):pass # Process may already have exited.
    return records,unreadable

def validate_network(interfaces, ip_addresses, ipv4, ipv6):
    errors=[]
    ip_interfaces=sorted(item['ifname'] for item in ip_addresses)
    if interfaces!=['lo']:errors.append('socket network interfaces must be exactly loopback')
    if ip_interfaces!=['lo']:errors.append('ip network interfaces must be exactly loopback')
    if interfaces!=ip_interfaces:errors.append('socket and ip interface evidence disagree')
    if any(r[0]!='lo' for r in ipv4):errors.append('non-loopback IPv4 route present')
    if any(r[-1]!='lo' for r in ipv6):errors.append('non-loopback IPv6 route present')
    return errors

def network_evidence():
    # /sys is a shared mount and may expose the host net namespace after unshare.
    # Both socket ioctl/netlink and ip netlink query this process's current netns.
    interfaces=sorted(name for _,name in socket.if_nameindex())
    ip_addresses=json.loads(subprocess.run(['ip','-j','address'],check=True,
                                          capture_output=True,text=True,timeout=5).stdout)
    routes=Path('/proc/net/route').read_text().splitlines()
    ipv4=[l.split() for l in routes[1:] if l.strip()]
    ipv6=[l.split() for l in Path('/proc/net/ipv6_route').read_text().splitlines() if l.strip()]
    errors=validate_network(interfaces,ip_addresses,ipv4,ipv6)
    return {'interfaces':interfaces,'ipAddresses':ip_addresses,
            'interfaceEvidenceSources':['socket.if_nameindex','ip -j address'],
            'ipv4Routes':ipv4,'ipv6Routes':ipv6,'errors':errors,
            'networkNamespace':os.readlink('/proc/self/ns/net')}

def load_migration(path):
    spec=importlib.util.spec_from_file_location('migration_cases',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--engine',choices=['firefox','webkit'],required=True)
    ap.add_argument('--candidate-root',required=True)
    ap.add_argument('--harness-dir',required=True)
    ap.add_argument('--migration-runner',required=True)
    ap.add_argument('--output',required=True)
    a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    records=[]
    def log(r):
        records.append(r)
        with (out/'results.jsonl').open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    module=load_migration(Path(a.migration_runner).resolve())
    app_path=Path(a.candidate_root)/'index.html';server=None;browser=None;env=None;cases_run=0;bad=0;blocked=None;gate=None
    log({'kind':'run','engine':a.engine,'runnerSha':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'migrationRunnerSha':hashlib.sha256(Path(a.migration_runner).read_bytes()).hexdigest(),
         'scope':'Linux engine feasibility plus synthetic local backup tests; not device/production/cloud acceptance'})
    try:
        problems=check_environment(os.environ,os.geteuid())
        if problems:raise Blocked('; '.join(problems))
        net=network_evidence();log({'kind':'network',**net})
        if net['errors']:raise Blocked('; '.join(net['errors']))
        version=importlib.metadata.version('playwright');log({'kind':'dependency','playwright':version})
        if version!=PINNED_PLAYWRIGHT:raise Blocked('Playwright version differs from pinned 1.56.0')
        app=app_path.read_bytes()
        if hashlib.sha256(app).hexdigest()!=APP_SHA:raise Blocked('candidate SHA mismatch')
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            try:
                # No custom flags, no executable overrides, no sandbox disabling.
                browser=getattr(pw,a.engine).launch(headless=True)
                log({'kind':'browser','engine':a.engine,'version':browser.version,'customLaunchArgs':[]})
                probe=browser.new_context(service_workers='block')
                probe.route('**/*',lambda r:r.abort('blockedbyclient'))
                probe.route_web_socket('**/*',lambda ws:None) # no upstream connection
                p=probe.new_page();p.set_content('<!doctype html><meta charset=utf-8><title>Sandbox probe</title><p>Probe</p>')
                p.evaluate('document.title')
                deadline=time.monotonic()+10
                while True:
                    rs,unreadable=process_snapshot();gate=gate_records(rs,os.getpid(),a.engine,os.geteuid());gate['unreadableProcesses']=unreadable
                    if gate['contentProcesses'] or time.monotonic()>=deadline:break
                    p.wait_for_timeout(100)
                log({'kind':'sandboxGate','phase':'before-app','engine':a.engine,**gate})
                if gate['status']!='PASS':raise Blocked('; '.join(gate['errors']))
                # Second observation, same live content process context.
                p.evaluate('document.body.textContent');rs,unreadable=process_snapshot()
                gate2=gate_records(rs,os.getpid(),a.engine,os.geteuid())
                log({'kind':'sandboxGate','phase':'confirmation','engine':a.engine,**gate2})
                if gate2['status']!='PASS':raise Blocked('; '.join(gate2['errors']))
                probe.close()
                # Candidate-serving HTTP server and application pages exist only below the validated gate.
                sys.path.insert(0,str(Path(a.harness_dir).resolve()));import bsdk_runner as h
                fixture_path=Path(a.candidate_root)/'tests/idb-browser/fixture_A.json';fixture_bytes=fixture_path.read_bytes()
                if hashlib.sha256(fixture_bytes).hexdigest()!=h.FIXTURE_SHA:raise Blocked('fixture SHA mismatch')
                env=h.Env();env.h=h;env.fixture=json.loads(fixture_bytes);env.log=log;env.contexts=[];env.b=browser
                env.srv=server=h.Server(app,None,fixture_bytes)
                for name,fn in module.CASES:
                    env.contexts=[];start=time.monotonic();rec={'kind':'case','id':name,'engine':a.engine}
                    try:rec.update(fn(env));rec['status']='PASS'
                    except Exception as e:rec.update(status='FAIL',error=str(e),trace=traceback.format_exc());bad+=1
                    finally:
                        errors=[]
                        for c in env.contexts:
                            try:c.close()
                            except Exception as e:errors.append(str(e))
                        if errors:rec.update(status='FAIL',cleanupErrors=errors);bad+=1
                    cases_run+=1;rec['seconds']=round(time.monotonic()-start,3);log(rec);print(name,rec['status'],flush=True)
            finally:
                if browser:
                    try:browser.close()
                    except Exception as e:bad+=1;log({'kind':'cleanupError','error':str(e)})
    except Blocked as e:blocked=str(e)
    except Exception as e:
        # If no app execution has started, an engine/guard uncertainty is BLOCKED.
        if cases_run==0:blocked=type(e).__name__+': '+str(e)
        else:bad+=1;log({'kind':'fatal','error':str(e),'trace':traceback.format_exc()})
    finally:
        if server:server.httpd.shutdown();server.httpd.server_close()
    if blocked:
        log({'kind':'blocked','reason':blocked,'applicationCasesExecuted':cases_run})
        completed={r['id'] for r in records if r.get('kind')=='case'}
        for name,_ in module.CASES:
            if name not in completed:log({'kind':'case','id':name,'engine':a.engine,'status':'BLOCKED','reason':blocked})
    final_sha=hashlib.sha256(app_path.read_bytes()).hexdigest() if app_path.exists() else None
    if final_sha!=APP_SHA:bad+=1
    status='BLOCKED' if blocked and not bad else ('FAIL' if bad else 'PASS')
    summary={'kind':'suite','engine':a.engine,'status':status,'casesExecuted':cases_run,
             'pass':sum(r.get('kind')=='case' and r.get('status')=='PASS' for r in records),
             'fail':sum(r.get('kind')=='case' and r.get('status')=='FAIL' for r in records),
             'blocked':sum(r.get('kind')=='case' and r.get('status')=='BLOCKED' for r in records),
             'candidateShaAfter':final_sha,'exitCode':0 if status=='PASS' else 1}
    log(summary);(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));return summary['exitCode']

if __name__=='__main__':sys.exit(main())
