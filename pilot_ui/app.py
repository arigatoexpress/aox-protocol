"""Loopback-only, single-operator fixture inspector. Python standard library only."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from simulator import CONTRACT, Simulator, identifier, natural, replay, require, uppercase_fixture

ROOT = Path(__file__).parent
MAX_BODY = 262144
MAX_HISTORY = 50


def inspect_receipt(receipt):
    require(type(receipt) is dict and set(receipt) ==
            {'format', 'provenance', 'ledger', 'checkpoint'}, 'unsupported receipt envelope')
    require(receipt['format'] == 'aox-pilot-receipt@1' and receipt['provenance'] == 'synthetic',
            'only synthetic fixture receipts are supported')
    events = receipt['ledger']
    require(type(events) is list and 1 <= len(events) <= 100, 'expected 1–100 ledger events')
    require(all(type(event) is dict for event in events), 'events must be objects')
    checkpoint = receipt['checkpoint']
    require(type(checkpoint) is dict and set(checkpoint) == {'event_count', 'final_hash'}
            and type(checkpoint['event_count']) is int
            and checkpoint['event_count'] == len(events)
            and checkpoint['final_hash'] == events[-1].get('hash'), 'checkpoint mismatch')
    sim = replay(events)
    state = sim.state
    require(len(state['requests']) == 1, 'inspector requires one task per receipt')
    request = next(iter(state['requests'].values()))
    require(request['status'] in ('passed', 'failed', 'unmatched', 'expired'),
            'receipt must have a terminal task state')
    # Matching evidence must use offers available at the quote event, not later additions.
    quote_index = next((i for i, event in enumerate(events)
                        if event['kind'] == 'quote'), None)
    match_offers = replay(events[:quote_index + 1]).state['offers'] if quote_index is not None else []
    return {'synthetic_only': True, 'request': request, 'offers': match_offers,
            'checkpoint': checkpoint, 'events': events,
            'fixture_outcomes': state['reputation'],
            'unmet_demand': ([{'provenance': 'synthetic', 'reason': request['match_reason'],
                              'contract': request['contract']}] if request['status'] == 'unmatched' else [])}


def run_fixture(data):
    require(type(data) is dict and set(data) == {'text', 'budget', 'offers', 'scenario'},
            'expected text, budget, offers and scenario')
    require(type(data['text']) is str and len(data['text']) <= 4096, 'text limit is 4096 characters')
    require(natural(data['budget']) and data['budget'] <= 100, 'budget must be an integer from 0 to 100')
    require(data['scenario'] in ('pass', 'reject'), 'unknown fixture scenario')
    offers = data['offers']
    require(type(offers) is list and 1 <= len(offers) <= 8, 'provide 1–8 synthetic offers')
    providers = set()
    for offer in offers:
        require(type(offer) is dict and set(offer) == {'provider', 'price'}, 'invalid offer schema')
        provider = offer['provider']
        require(identifier(provider) and provider != 'requester' and provider not in providers,
                'providers must be distinct and different from requester')
        require(natural(offer['price']) and offer['price'] <= 100, 'offer price must be 0–100')
        providers.add(provider)
    sim = Simulator()
    sim.record('seed', balances={'requester': 100, **{p: 0 for p in sorted(providers)}})
    for offer in offers:
        sim.record('offer', **offer, contract=CONTRACT)
    sim.record('post', request='local-task', requester='requester', contract=CONTRACT,
               payload={'text': data['text']}, budget=data['budget'], deadline=100)
    sim.record('quote', request='local-task', now=0)
    if sim.state['requests']['local-task']['status'] == 'quoted':
        sim.record('accept', request='local-task', now=1)
        # Fixed trusted fixtures only. No callable is selected from payload data.
        fixture = uppercase_fixture if data['scenario'] == 'pass' else lambda payload: {'invalid': True}
        sim.execute('local-task', fixture, now=2)
        sim.record('settle', request='local-task', now=3)
    events = sim.events
    receipt = {'format': 'aox-pilot-receipt@1', 'provenance': 'synthetic', 'ledger': events,
               'checkpoint': {'event_count': len(events), 'final_hash': events[-1]['hash']}}
    inspect_receipt(receipt)
    return receipt


class Handler(BaseHTTPRequestHandler):
    timeout = 5  # Accepted-socket timeout; server.timeout does not bound request reads.

    def log_message(self, *args):
        pass  # Payloads and task text must not enter server logs.

    def respond(self, value, status=200, content_type='application/json; charset=utf-8'):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', ("connect-src 'none'; worker-src 'self'; form-action 'none'; " if self.path.startswith('/csv') else '') + "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def local_request(self):
        # Reject foreign Host/Origin values. There is no CORS or public binding.
        expected = f'127.0.0.1:{self.server.server_port}'
        return self.headers.get('Host') == expected and self.headers.get('Origin', f'http://{expected}') == f'http://{expected}'

    def do_GET(self):
        if not self.local_request():
            return self.respond({'error': 'loopback origin required'}, 403)
        static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                  '/style.css': ('style.css', 'text/css'), '/csv': ('csv.html', 'text/html'),
                  '/csv.css': ('csv.css', 'text/css')}
        for module in ('csv-ui', 'csv-core', 'csv-reference', 'csv-worker'):
            static[f'/{module}.mjs'] = (f'{module}.mjs', 'text/javascript')
        if self.path in static:
            name, mime = static[self.path]
            return self.respond((ROOT / 'static' / name).read_bytes(), content_type=mime + '; charset=utf-8')
        if self.path == '/api/history':
            return self.respond(self.server.history)
        if self.path == '/api/contracts':
            return self.respond([json.loads(p.read_text()) for p in sorted((ROOT / 'contracts').glob('*.json'))])
        return self.respond({'error': 'not found'}, 404)

    def do_POST(self):
        if not self.local_request():
            return self.respond({'error': 'loopback origin required'}, 403)
        if self.path not in ('/api/run', '/api/replay'):
            return self.respond({'error': 'not found'}, 404)
        try:
            require(self.headers.get('Content-Type') == 'application/json', 'JSON content type required')
            length = int(self.headers.get('Content-Length', '0'))
            require(0 < length <= MAX_BODY, 'request must be 1–262144 bytes')
            data = json.loads(self.rfile.read(length))
            receipt = run_fixture(data) if self.path == '/api/run' else data
            view = inspect_receipt(receipt)
            item = {'receipt': receipt, 'view': view, 'origin': 'local fixture' if self.path == '/api/run' else 'imported synthetic ledger'}
            self.server.history.insert(0, item)
            del self.server.history[MAX_HISTORY:]
            return self.respond(item)
        except TimeoutError:
            self.close_connection = True
            return self.respond({'error': 'request read timed out'}, 408)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError):
            return self.respond({'error': 'Invalid task or receipt. Check schema, bounds, provenance and ledger checkpoint.'}, 400)


class LocalServer(HTTPServer):
    allow_reuse_address = True


def make_server(port=8765):
    server = LocalServer(('127.0.0.1', port), Handler)
    server.history = []
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with make_server(args.port) as server:
        print(f'Synthetic inspector: http://127.0.0.1:{server.server_port} (history is memory-only)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
