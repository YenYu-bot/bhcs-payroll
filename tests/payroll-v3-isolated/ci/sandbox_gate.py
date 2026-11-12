"""Fail closed: launched sandbox flag alone is not proof of active renderer protection."""
import json, os, pathlib, re, socket
from playwright.sync_api import sync_playwright
assert os.geteuid() != 0, 'root forbidden'
assert [name for _, name in socket.if_nameindex()] == ['lo'], 'non-loopback interface present'
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, chromium_sandbox=True)
    page = b.new_page(); page.goto('chrome://sandbox')
    report = page.locator('body').inner_text()
    print(report, flush=True)
    assert re.search(r'Namespace sandbox\s+Yes', report), 'namespace sandbox not verified'
    assert re.search(r'Seccomp-BPF sandbox\s+Yes', report), 'seccomp sandbox not verified'
    session = b.new_browser_cdp_session()
    infos = session.send('SystemInfo.getProcessInfo')['processInfo']
    renderer_pids = [int(i['id']) for i in infos if i['type'] == 'renderer']
    renderers = []
    for pid in renderer_pids:
        d = pathlib.Path('/proc') / str(pid)
        try:
            cmd = (d/'cmdline').read_bytes().split(b'\0')
            if b'--type=renderer' not in cmd or d.stat().st_uid != os.getuid(): continue
            st = dict(line.split(':', 1) for line in (d/'status').read_text().splitlines())
            item = {'pid': int(d.name), 'seccomp': st['Seccomp'].strip(), 'nnp': st['NoNewPrivs'].strip(), 'nspid': st['NSpid'].strip(), 'noSandbox': b'--no-sandbox' in cmd}
            renderers.append(item)
        except (OSError, KeyError): pass
    print(json.dumps({'uid': os.getuid(), 'browser': b.version, 'renderers': renderers}), flush=True)
    assert renderers and all(x['seccomp']=='2' and x['nnp']=='1' and not x['noSandbox'] for x in renderers), 'renderer protection missing'
    b.close()
print('SANDBOX_GATE_PASS')
