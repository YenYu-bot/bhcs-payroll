"""Fail closed: launched sandbox flag alone is not proof of active renderer protection."""
import json, os, pathlib, re, socket
from playwright.sync_api import sync_playwright
assert os.geteuid() != 0, 'root forbidden'
assert [name for _, name in socket.if_nameindex()] == ['lo'], 'non-loopback interface present'
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, chromium_sandbox=True)
    # Headless Shell has no chrome://sandbox WebUI. Verify its own renderer via CDP and /proc instead.
    page = b.new_page(); page.set_content('<p>isolated sandbox probe</p>')
    session = b.new_browser_cdp_session()
    infos = session.send('SystemInfo.getProcessInfo')['processInfo']
    print(json.dumps({'processInfo': infos}), flush=True)
    renderer_pids = [int(i['id']) for i in infos if i['type'] == 'renderer']
    renderers = []
    for pid in renderer_pids:
        d = pathlib.Path('/proc') / str(pid)
        try:
            cmd = (d/'cmdline').read_bytes().split(b'\0')
            print(json.dumps({'pid': pid, 'uid': d.stat().st_uid, 'cmd': [c.decode(errors='replace') for c in cmd]}), flush=True)
            if b'--type=renderer' not in cmd: continue
            st = dict(line.split(':', 1) for line in (d/'status').read_text().splitlines())
            item = {'pid': int(d.name), 'seccomp': st['Seccomp'].strip(), 'nnp': st['NoNewPrivs'].strip(), 'nspid': st['NSpid'].strip(), 'noSandbox': b'--no-sandbox' in cmd}
            renderers.append(item)
        except (OSError, KeyError) as e: print(json.dumps({'pid': pid, 'error': str(e)}), flush=True)
    print(json.dumps({'uid': os.getuid(), 'browser': b.version, 'renderers': renderers}), flush=True)
    assert renderers and all(x['seccomp']=='2' and x['nnp']=='1' and len(x['nspid'].split()) >= 2 and not x['noSandbox'] for x in renderers), 'renderer protection missing'
    b.close()
print('SANDBOX_GATE_PASS')
