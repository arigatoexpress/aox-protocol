"""Independent accounting oracle for v0.2 ledgers.

Deliberately imports nothing from simulator.py or simulator_v02.py: it re-derives balances,
escrow and pass/fail outcomes from the raw event list with its own known-answer checks,
and asserts credit conservation after every event.
"""

import hashlib
import json


class OracleError(AssertionError):
    pass


def _check(cond, msg):
    if not cond:
        raise OracleError(msg)


def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _event_hash(e):
    body = {'sequence': e['sequence'], 'previous': e['previous'], 'kind': e['kind'], 'data': e['data']}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _expected(contract, payload):
    if contract == 'text.upper@1':
        return {'text': payload['text'].upper()}
    if contract == 'json.extract@1':
        node = payload['document']
        for step in payload['path']:
            node = node[step]
        return {'value': node}
    raise OracleError('unknown contract ' + repr(contract))


def audit(events):
    """Return derived totals; raise OracleError on any accounting inconsistency."""
    _check(type(events) is list and events and events[0]['kind'] == 'seed', 'ledger must start with seed')
    balances = dict(events[0]['data']['balances'])
    total = sum(balances.values())
    posts, escrow, outputs = {}, {}, {}
    out = {'passes': 0, 'fails_verified': 0, 'refunds': 0, 'paid_to_providers': 0,
           'escrowed_gross': 0, 'accepted': 0, 'events': len(events)}
    for i, e in enumerate(events):
        _check(e['sequence'] == i, 'sequence gap at %d' % i)
        _check(e['previous'] == (events[i - 1]['hash'] if i else '0' * 64), 'broken hash link at %d' % i)
        _check(e['hash'] == _event_hash(e), 'hash mismatch at %d' % i)
        k, d = e['kind'], e['data']
        if k == 'seed':
            _check(i == 0, 'second seed')
        elif k == 'post':
            posts[d['request']] = d
        elif k == 'accept':
            rq = d['request']
            req = posts[rq]['requester']
            _check(rq not in escrow, 'double accept ' + rq)
            _check(0 <= d['price'] <= posts[rq]['budget'], 'price outside budget ' + rq)
            balances[req] -= d['price']
            _check(balances[req] >= 0, 'negative balance ' + req)
            provider = d['offer']  # resolved to a provider via offers below
            escrow[rq] = (d['price'], provider)
            out['accepted'] += 1
            out['escrowed_gross'] += d['price']
        elif k == 'offer':
            outputs.setdefault('__offers__', {})[d['offer']] = d['provider']
        elif k == 'deliver':
            outputs[d['request']] = d['output']
        elif k == 'settle':
            rq = d['request']
            _check(rq in escrow, 'settle without escrow ' + rq)
            price, offer = escrow.pop(rq)
            provider = outputs['__offers__'][offer]
            ok = _canon(outputs[rq]) == _canon(_expected(posts[rq]['contract'], posts[rq]['payload']))
            balances[provider if ok else posts[rq]['requester']] += price
            if ok:
                out['passes'] += 1
                out['paid_to_providers'] += price
            else:
                out['fails_verified'] += 1
                out['refunds'] += 1
        elif k in ('fail', 'expire'):
            rq = d['request']
            if rq in escrow:
                price, _ = escrow.pop(rq)
                balances[posts[rq]['requester']] += price
                out['refunds'] += 1
        _check(sum(balances.values()) + sum(p for p, _ in escrow.values()) == total,
               'conservation violated at event %d' % i)
        _check(all(v >= 0 for v in balances.values()), 'negative balance at event %d' % i)
    out.update({'balances': balances, 'escrow': {k: v[0] for k, v in escrow.items()}, 'total': total})
    return out
