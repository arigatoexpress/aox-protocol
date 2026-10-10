import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ReleaseLedger, createX402TestnetGate, decideRelease} from './x402-testnet.mjs';
import {getX402PaymentStatus} from './x402-config.mjs';

const vectors = JSON.parse(readFileSync(new URL('./vectors.json', import.meta.url), 'utf8'));

function view(status) {
  const rails = Object.fromEntries(status.rails.map((rail) => [rail.railId, rail]));
  return {
    mode: status.mode,
    activeRail: status.activeRail,
    ready: status.ready,
    liveSettlementAllowed: status.liveSettlementAllowed,
    serverPrivateKeyRequired: status.serverPrivateKeyRequired,
    networkId: status.network.id,
    networkMainnet: status.network.mainnet,
    payToRedacted: status.payTo.redacted,
    errors: status.errors,
    baseSepoliaLive: rails['base-sepolia-official-x402'].liveSettlementAllowed,
    solanaStatus: rails['solana-pay-sh-svm-candidate'].status,
  };
}

function assertExpect(actual, expect) {
  if (expect.errors) assert.deepEqual(actual.errors, expect.errors);
  for (const item of expect.errorsContain || []) assert.ok(actual.errors.includes(item), item);
  for (const [key, value] of Object.entries(expect)) {
    if (key === 'errors' || key === 'errorsContain') continue;
    assert.deepEqual(actual[key], value, key);
  }
}

test('status vectors block mainnet and refuse keys', () => {
  for (const vector of vectors.status) {
    const status = getX402PaymentStatus(vector.env);
    assertExpect(view(status), vector.expect);
    if (vector.absent) assert.equal(JSON.stringify(status).includes(vector.absent), false, vector.name);
  }
});

test('release vectors cap spend and withhold UNKNOWN', () => {
  for (const vector of vectors.release) {
    const decision = decideRelease(vector.input, {ledger: new ReleaseLedger()});
    assertExpect(decision, vector.expect);
    assert.equal(decision.liveSettlementAllowed, false, vector.name);
    if (vector.absent) assert.equal(JSON.stringify(decision).includes(vector.absent), false, vector.name);
  }
});

test('configured gate still refuses live settlement', () => {
  const idle = createX402TestnetGate({});
  assert.equal(idle.gateActive, false);
  assert.equal(idle.liveSettlementAllowed, false);
  const ready = createX402TestnetGate({
    AOX_PAYMENT_MODE: 'x402_testnet',
    AOX_X402_NETWORK: 'eip155:84532',
    AOX_X402_PAY_TO: '0x1111111111111111111111111111111111111111',
  });
  assert.equal(ready.gateActive, true);
  assert.equal(ready.liveSettlementAllowed, false);
  assert.equal(ready.status.serverPrivateKeyRequired, false);
});

test('one receipt is released once and the payload carries its hash', () => {
  const ready = vectors.release.find((vector) => vector.name === 'testnet ready still does not settle');
  const ledger = new ReleaseLedger();
  const calls = [];
  const first = decideRelease(ready.input, {
    ledger,
    settler(payload) {
      calls.push(payload);
      return true;
    },
  });
  assert.equal(first.decision, 'RELEASE');
  assert.equal(first.settled, true);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].receiptHash, ready.input.verdict.hash);
  assert.equal(calls[0].taskId, ready.input.verdict.task_id);
  assert.equal(calls[0].verdict, 'OK');
  const second = decideRelease(ready.input, {
    ledger,
    settler(payload) {
      calls.push(payload);
      return true;
    },
  });
  assert.equal(second.decision, 'DENY');
  assert.equal(second.reason, 'replay');
  assert.equal(second.settled, false);
  assert.equal(calls.length, 1);
});

test('rail source does not call fetch or read process.env', () => {
  const source = [
    readFileSync(new URL('./x402-testnet.mjs', import.meta.url), 'utf8'),
    readFileSync(new URL('./x402-config.mjs', import.meta.url), 'utf8'),
  ].join('\n');
  assert.equal(source.includes('fetch('), false);
  assert.equal(source.includes('process.env'), false);
  assert.equal(source.includes('http.request'), false);
});
