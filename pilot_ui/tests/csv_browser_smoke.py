"""Local browser acceptance. Uses already installed Playwright/Chromium; no installs.
Starts a temporary loopback server and shuts it down; uses only synthetic test files.
"""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[2]
out=Path(os.environ.get('AOX_EVIDENCE_DIR','/tmp/aox-csv-evidence'))
out.mkdir(parents=True,exist_ok=True)
server=subprocess.Popen([sys.executable,'-S','-m','pilot_ui.app','--port','0'],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
    url=server.stdout.readline().split()[2]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        requests=[];errors=[]
        page.on('request',lambda r: requests.append((r.method,r.url)))
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.goto(url+'/csv')
        page.get_by_role('button',name='Normalize & verify').click()
        page.get_by_role('status').filter(has_text='verification passed').wait_for()
        assert 'BOLT_A' in page.locator('#csv-rows').inner_text()
        with page.expect_download() as download:
            page.get_by_role('button',name='Download normalized CSV').click()
        download.value.save_as(out/'normalized.csv')
        assert (out/'normalized.csv').read_text()=='item_id,quantity\nBOLT_A,7\nNUT_B,2\n'
        with page.expect_download() as download:
            page.get_by_role('button',name='Download receipt',exact=True).click()
        receipt_path=out/'csv-receipt.json';download.value.save_as(receipt_path)
        receipt=json.loads(receipt_path.read_text())
        page.screenshot(path=str(out/'csv-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(out/'csv-mobile.png'),full_page=True)
        page.locator('#csv-import').set_input_files(str(receipt_path))
        page.get_by_role('status').filter(has_text='internally consistent').wait_for()
        bad=json.loads(json.dumps(receipt));bad['output']['rows'][0]['quantity']=123
        page.locator('#csv-import').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':json.dumps(bad).encode()})
        page.get_by_role('status').filter(has_text='disagrees').wait_for()
        assert page.locator('#csv-result').is_hidden()
        for content in [b'item_id,quantity\r\n" part_a ","007"\r\n', b'item_id,quantity\rA,1\r', b'item_id,quantity\n=1+1,2\n', b'item_id,quantity\n"A\nB",1\n', b'\xff', b'x'*32769, b'\xef\xbb\xbfitem_id,quantity\nA,1\n']:
            page.locator('#csv-file').set_input_files({'name':'local.csv','mimeType':'text/csv','buffer':content})
            if content==b'\xff' or len(content)>32768:
                page.get_by_role('status').filter(has_text='Unable to read CSV').wait_for()
            else:
                page.get_by_role('status').filter(has_text='Local file loaded').wait_for()
                page.get_by_role('button',name='Normalize & verify').click()
                if b'part_a' in content:
                    page.get_by_role('status').filter(has_text='verification passed').wait_for()
                    assert 'PART_A' in page.locator('#csv-rows').inner_text()
                    with page.expect_download() as dl:
                        page.get_by_role('button',name='Download receipt',exact=True).click()
                    saved=json.loads(Path(dl.value.path()).read_text())
                    assert saved['input']['csv_text'].encode()==content
                    assert saved['input_sha256']==hashlib.sha256(content).hexdigest()
                else:
                    page.locator('#csv-status.error').wait_for()
                    assert page.locator('#csv-result').is_hidden()
        page.locator('#csv-import').set_input_files({'name':'deep.json','mimeType':'application/json','buffer': ('{"x":'*20000+'0'+'}'*20000).encode()})
        page.locator('#csv-status.error').wait_for()
        assert page.locator('#csv-result').is_hidden()
        # Cancel in the same browser turn, before a worker message can be delivered.
        page.get_by_role('button',name='Load synthetic sample').click()
        page.evaluate("document.getElementById('csv-run').click(); document.getElementById('csv-cancel').click()")
        assert 'Cancelled' in page.locator('#csv-status').inner_text()
        assert page.locator('#csv-result').is_hidden()
        # Repeated runs supersede the prior worker and retain only the latest input.
        page.evaluate("""() => {
            document.getElementById('csv-run').click();
            const input=document.getElementById('csv-input');
            input.value='item_id,quantity\\nLATEST,42\\n';
            input.dispatchEvent(new Event('input'));
            document.getElementById('csv-run').click();
        }""")
        page.get_by_role('status').filter(has_text='verification passed').wait_for()
        assert page.locator('#csv-rows').inner_text()=='LATEST\t42'
        page.locator('#csv-input').fill('item_id,quantity\nCHANGED,1\n')
        assert page.locator('#csv-result').is_hidden()
        page.get_by_role('button',name='Clear data').click()
        assert page.locator('#csv-input').input_value()==''
        assert page.evaluate('localStorage.length === 0 && sessionStorage.length === 0')
        assert not errors,errors
        assert all(method=='GET' and location.startswith(url+'/') for method,location in requests),requests
        assert all(location.split('/')[-1] in {'csv','style.css','csv.css','csv-ui.mjs','csv-worker.mjs','csv-core.mjs','csv-reference.mjs'} for _,location in requests),requests
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.tagName')!='BODY'
        browser.close()
    print('PASS: local sample/file/receipt flows, CSV/receipt downloads, quoting/CRLF, malformed UTF-8/BOM/size/formula/newline rejection, tamper rejection, cancellation/repeated runs, stale-output invalidation, desktop/mobile/focus, zero data requests/storage/browser errors.')
finally:
    server.terminate();server.communicate(timeout=5)
