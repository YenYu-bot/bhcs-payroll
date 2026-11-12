import os, glob
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(chromium_sandbox=True,headless=True); pg=b.new_page(); pg.set_content('<p>x</p>')
    print('uid',os.geteuid(),'browser',b.version)
    for d in glob.glob('/proc/[0-9]*'):
        try:
            cmd=open(d+'/cmdline','rb').read().replace(b'\0',b' ').decode(errors='replace')
            if 'chrom' not in cmd.split(' ')[0] and 'headless_shell' not in cmd.split(' ')[0]: continue
            st=dict(l.split(':\t',1) for l in open(d+'/status').read().splitlines() if ':\t' in l)
            typ=[a for a in cmd.split() if a.startswith('--type=')]
            print(d[6:], (typ or ['--type=browser'])[0], 'Seccomp=',st.get('Seccomp','?').strip(), 'NSpid=',st.get('NSpid','?').strip(), 'no-sandbox-flag=', '--no-sandbox' in cmd, os.path.basename(cmd.split(' ')[0]))
        except Exception: pass
    b.close()
