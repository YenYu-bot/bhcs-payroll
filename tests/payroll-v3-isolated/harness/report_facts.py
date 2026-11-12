#!/usr/bin/env python3
"""Derive every number quoted in the report directly from the raw evidence (no hand-copied values).
Usage: report_facts.py <run_all-output-dir>  ->  prints facts.json"""
import json, os, sys
O = sys.argv[1]; F = {}
recs = [json.loads(l) for l in open(os.path.join(O, 'out-full', 'results.jsonl'))]
for r in recs:
    if r.get('kind') == 'run': F['hashes'] = {k: r[k] for k in ('appSha256Start', 'runnerSha256', 'hooksSha256', 'netpolicySha256', 'mutant06Sha256', 'mutant06PatternCount')}
    if r.get('kind') == 'browser': F['browser'] = r['version']
    if r.get('kind') == 'shutdown': F['appSha256End'] = r['appSha256End']
    if r.get('kind') == 'suite': F['suite'] = r
    if r.get('kind') == 'preflight': F['preflightMissing'] = r['missing']; F['lockedSources'] = r['lockedSources']
cases = [r for r in recs if r.get('kind') == 'case']
F['cases'] = [{k: r.get(k) for k in ('id', 'caseKind', 'status', 'startedAt', 'endedAt', 'seconds', 'failPoint', 'cleanup')} for r in cases]
h3 = next(r for r in cases if r['id'] == 'H3')
F['H3'] = {'holdMsAfterRequestStart': h3['gate']['msSinceRequestStart'], 'heldCallIndex': h3['gate']['callIndex'],
           'deadlineRejectMsAfterRequestStart': round(h3['request']['end'] - h3['request']['start'], 1), 'code': h3['request']['code'], 'caseSeconds': h3['seconds']}
m = next(r for r in cases if r['id'] == 'H3-MUTANT'); F['H3-MUTANT'] = m['negativeControl']
g2 = next(r for r in cases if r['id'] == 'G2'); F['G2'] = {'browserNegatives': len([k for k in g2['attempts'] if k != '__ws']), 'allBlocked': all(v == 'blocked' for k, v in g2['attempts'].items() if k != '__ws')}
h1 = next(r for r in cases if r['id'] == 'H1'); F['H1'] = {'positives': sum(x['kind'] == 'positive' for x in h1['rows']), 'negatives': sum(x['kind'] == 'negative' for x in h1['rows'])}
F['supervisor'] = {k: json.load(open(os.path.join(O, 'sup-full', 'supervisor.json'))).get(k) for k in
                   ('supervisorPid', 'childPid', 'subreaper', 'childExitCode', 'timedOut', 'seconds', 'reapedBeforeCheck', 'ownedLeftovers', 'ownedListeners', 'foreignListeners', 'cleanupKilledOwned', 'ownedAfterCleanup', 'portsOpenAfterCleanup', 'final', 'finalExit')}
F['summary'] = json.load(open(os.path.join(O, 'summary.json')))
print(json.dumps(F, ensure_ascii=False, indent=1))
