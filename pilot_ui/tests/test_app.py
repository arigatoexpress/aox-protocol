import copy
import unittest

from pilot_ui.app import run_fixture, inspect_receipt


def sample(**changes):
    return dict(text='Straße <script>alert(1)</script>', budget=20,
                offers=[{'provider': 'fixture-b', 'price': 10},
                        {'provider': 'fixture-a', 'price': 10}], scenario='pass', **changes)


class ReceiptTests(unittest.TestCase):
    def test_pass_unicode_tie_break_and_round_trip(self):
        receipt = run_fixture(sample())
        view = inspect_receipt(receipt)
        self.assertEqual(view['request']['quote']['provider'], 'fixture-a')
        self.assertEqual(view['request']['output']['text'], sample()['text'].upper())
        self.assertTrue(view['request']['verification']['known_answer_pass'])
        self.assertEqual(view['checkpoint']['event_count'], 8)
        self.assertTrue(view['synthetic_only'])

    def test_rejection_and_no_match(self):
        data = sample()
        data['scenario'] = 'reject'
        failed = inspect_receipt(run_fixture(data))
        self.assertEqual(failed['request']['status'], 'failed')
        self.assertFalse(failed['request']['verification']['schema_valid'])
        data['budget'] = 0
        unmatched = inspect_receipt(run_fixture(data))
        self.assertEqual(unmatched['request']['status'], 'unmatched')
        self.assertEqual(len(unmatched['unmet_demand']), 1)

    def test_tampered_and_truncated_receipts_rejected(self):
        receipt = run_fixture(sample())
        for change in ('hash', 'prefix', 'provenance', 'checkpoint'):
            bad = copy.deepcopy(receipt)
            if change == 'hash': bad['ledger'][-1]['hash'] = '0' * 64
            if change == 'prefix': bad['ledger'].pop()
            if change == 'provenance': bad['provenance'] = 'real'
            if change == 'checkpoint': bad['checkpoint']['event_count'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                inspect_receipt(bad)

    def test_invalid_requests_fail_closed(self):
        cases = [('budget', True), ('text', 'x' * 4097), ('scenario', 'execute'),
                 ('offers', [{'provider': 'requester', 'price': 1}]),
                 ('offers', [{'provider': 'x', 'price': -1}]), ('offers', []),
                 ('offers', [{'provider': 'x', 'price': 1}] * 2), ('extra', 'field')]
        for key, value in cases:
            data = sample()
            data[key] = value
            with self.subTest(key=key, value=str(value)[:50]), self.assertRaises(ValueError):
                run_fixture(data)

    def test_import_does_not_trust_summary(self):
        receipt = run_fixture(sample())
        receipt['state'] = {'status': 'passed'}
        with self.assertRaises(ValueError): inspect_receipt(receipt)


class HttpTests(unittest.TestCase):
    def setUp(self):
        import threading
        from pilot_ui.app import make_server
        self.server = make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, data=None, headers=None):
        import http.client
        import json
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        body = json.dumps(data) if data is not None else None
        conn.request(method, path, body, headers or {'Content-Type': 'application/json'})
        response = conn.getresponse()
        status, raw = response.status, response.read()
        conn.close()
        return status, raw

    def test_run_replay_history_and_static_routes(self):
        import json
        status, raw = self.request('POST', '/api/run', sample())
        self.assertEqual(status, 200)
        receipt = json.loads(raw)['receipt']
        self.assertEqual(self.request('POST', '/api/replay', receipt)[0], 200)
        status, raw = self.request('GET', '/api/history')
        self.assertEqual(len(json.loads(raw)), 2)
        for path in ('/', '/app.js', '/style.css', '/api/contracts', '/csv', '/csv.css', '/csv-ui.mjs', '/csv-core.mjs', '/csv-reference.mjs', '/csv-worker.mjs'):
            self.assertEqual(self.request('GET', path)[0], 200)
        self.assertEqual(self.request('GET', '/../../simulator.py')[0], 404)

    def test_foreign_origin_invalid_import_and_limits(self):
        self.assertEqual(self.request('POST', '/api/run', sample(), {'Origin': 'https://example.com', 'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={'Host': 'example.com'})[0], 403)
        self.assertEqual(self.request('POST', '/api/run', sample(), {'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('POST', '/api/replay', {'provenance': 'real'})[0], 400)
        self.assertEqual(self.request('POST', '/api/run', {'text': 'x' * 262145})[0], 400)
        self.assertEqual(self.server.history, [])

    def test_history_is_bounded(self):
        for _ in range(52):
            self.assertEqual(self.request('POST', '/api/run', sample())[0], 200)
        self.assertEqual(len(self.server.history), 50)


class DraftTests(unittest.TestCase):
    def test_draft_cites_replayed_evidence_without_payload(self):
        from pilot_ui.draft_devlog import draft
        receipt = run_fixture(sample())
        text = draft(receipt)
        self.assertIn('SYNTHETIC DEMO', text)
        self.assertIn(receipt['checkpoint']['final_hash'], text)
        self.assertIn('8 events', text)
        self.assertNotIn(sample()['text'], text)
        self.assertIn('not authorship', text)

    def test_tampered_receipt_cannot_generate_draft(self):
        from pilot_ui.draft_devlog import draft
        receipt = run_fixture(sample())
        receipt['ledger'][-1]['hash'] = '0' * 64
        with self.assertRaises(ValueError): draft(receipt)


def imported_terminal_receipt(output=False, ending='fail', late_offer=False):
    from simulator import CONTRACT, Simulator
    sim = Simulator()
    sim.record('seed', balances={'requester': 100, 'early': 0, 'late': 0})
    sim.record('offer', provider='early', price=10, contract=CONTRACT)
    sim.record('post', request='imported-task', requester='requester', contract=CONTRACT,
               payload={'text': 'hello'}, budget=20, deadline=100)
    sim.record('quote', request='imported-task', now=0)
    sim.record('accept', request='imported-task', now=1)
    sim.record('deliver', request='imported-task', output=output, now=2)
    sim.record(ending, request='imported-task', now=100 if ending == 'expire' else 3)
    if late_offer:
        sim.record('offer', provider='late', price=1, contract=CONTRACT)
    events = sim.events
    return {'format': 'aox-pilot-receipt@1', 'provenance': 'synthetic', 'ledger': events,
            'checkpoint': {'event_count': len(events), 'final_hash': events[-1]['hash']}}


class ReviewRegressionTests(unittest.TestCase):
    def test_candidates_are_from_quote_time(self):
        view = inspect_receipt(imported_terminal_receipt(late_offer=True))
        self.assertEqual([o['provider'] for o in view['offers']], ['early'])
        self.assertEqual(view['request']['quote']['provider'], 'early')

    def test_falsy_deliveries_survive_import_without_inferred_verdict(self):
        for output in (False, 0, None, ''):
            for ending in ('fail', 'expire'):
                with self.subTest(output=output, ending=ending):
                    view = inspect_receipt(imported_terminal_receipt(output, ending))
                    self.assertIn('output', view['request'])
                    self.assertEqual(view['request']['output'], output)
                    self.assertNotIn('verification', view['request'])

    def test_partial_http_body_times_out_and_server_recovers(self):
        import http.client
        import socket
        import threading
        from pilot_ui.app import Handler, make_server
        # A local handler subclass keeps the short test timeout isolated.
        class FastHandler(Handler):
            timeout = 0.15
        server = make_server(0)
        server.RequestHandlerClass = FastHandler
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with socket.create_connection(server.server_address, timeout=2) as slow:
                request = (f'POST /api/run HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n'
                           'Content-Type: application/json\r\nContent-Length: 10\r\n\r\n{')
                slow.sendall(request.encode())
                response = slow.recv(4096)
                self.assertIn(b'408', response)
            conn = http.client.HTTPConnection(*server.server_address, timeout=2)
            conn.request('GET', '/api/history')
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'[]')
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
