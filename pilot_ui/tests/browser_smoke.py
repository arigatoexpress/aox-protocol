"""Optional browser acceptance test; requires locally available Playwright + Chromium.
Start `python3 -m pilot_ui.app` first. No package install or network calls needed.
"""
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pilot_ui.tests.test_app import imported_terminal_receipt

out = Path(os.environ.get('AOX_EVIDENCE_DIR', '/tmp/aox-browser-evidence'))
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(os.environ.get('AOX_DEMO_URL', 'http://127.0.0.1:8765'))
    page.get_by_text('Schema-bound CSV normalization', exact=True).wait_for()
    page.get_by_label('Input text').fill('Straße <script>window.INJECTED = true</script>')
    page.get_by_role('button', name='Run synthetic task').click()
    page.locator('#status').filter(has_text='Known-answer pass').wait_for()
    assert not page.locator('#empty').is_visible()
    assert 'STRASSE' in page.locator('#output').inner_text()
    assert page.evaluate('window.INJECTED') is None
    assert 'fixture-alpha' in page.locator('#candidates').inner_text()
    with page.expect_download() as downloaded:
        page.get_by_role('button', name='Download replayable receipt').click()
    receipt_path = out / 'aox-synthetic-pass.json'
    downloaded.value.save_as(receipt_path)
    original = json.loads(receipt_path.read_text())
    page.locator('#receipt-file').set_input_files(str(receipt_path))
    page.get_by_role('status').filter(has_text='imported synthetic ledger').wait_for()
    page.locator('#task-text').fill('Turn small tasks into inspectable results.')
    page.get_by_role('button', name='Run synthetic task').click()
    page.get_by_role('status').filter(has_text='local fixture').wait_for()
    page.screenshot(path=str(out / 'aox-desktop.png'), full_page=True)
    page.get_by_label('Verification scenario').select_option('reject')
    page.get_by_role('button', name='Run synthetic task').click()
    page.locator('#status').filter(has_text='Verification failed').wait_for()
    assert 'Schema: fail' in page.locator('#verification').inner_text()
    page.get_by_label('Maximum fixture units').fill('0')
    page.get_by_role('button', name='Run synthetic task').click()
    page.locator('#status').filter(has_text='No eligible offer').wait_for()
    assert 'No delivered result' in page.locator('#verification').inner_text()
    tampered = json.loads(json.dumps(original))
    tampered['ledger'][-1]['hash'] = '0' * 64
    bad_path = out / 'tampered-test.json'
    bad_path.write_text(json.dumps(tampered))
    page.locator('#receipt-file').set_input_files(str(bad_path))
    page.get_by_role('status').filter(has_text='Invalid task or receipt').wait_for()
    bad_path.unlink()
    page.get_by_label('Maximum fixture units').fill('20')
    page.get_by_label('Verification scenario').select_option('pass')
    page.get_by_role('button', name='Run synthetic task').click()
    page.locator('#status').filter(has_text='Known-answer pass').wait_for()
    page.set_viewport_size({'width':390, 'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(out / 'aox-mobile.png'), full_page=True)
    page.keyboard.press('Tab')
    assert page.evaluate('document.activeElement.tagName') != 'BODY'
    for value in (False, 0, None, ''):
        for ending in ('fail', 'expire'):
            receipt = imported_terminal_receipt(value, ending, late_offer=True)
            page.locator('#receipt-file').set_input_files({'name': 'review-fixture.json', 'mimeType': 'application/json', 'buffer': json.dumps(receipt).encode()})
            expected = 'Execution failed' if ending == 'fail' else 'Task expired'
            page.locator('#status').filter(has_text=expected).wait_for()
            assert page.locator('#output').inner_text() == json.dumps(value)
            assert 'A result was delivered' in page.locator('#verification').inner_text()
            assert 'late' not in page.locator('#candidates').inner_text()
    assert not errors, errors
    browser.close()
print('PASS: desktop/mobile, fixture success/rejection/no-match, literal script text, export/import, tampered import, keyboard focus, no horizontal overflow, no browser errors; review regressions for falsy delivered output, failure/expiry verdicts and quote-time candidates.')
