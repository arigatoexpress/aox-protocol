import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {generatePrivateKey} from 'viem/accounts';
import {facilitatorAllowed} from './x402-config.mjs';
import {ReleaseLedger} from './x402-testnet.mjs';
import {createReleaseApp, receiptPaymentPolicy, redact, settleOnce} from './x402-live.mjs';

const vectors = JSON.parse(readFileSync(new URL('./vectors.json', import.meta.url), 'utf8'));
const receipt = vectors.release.find((item) => item.name === 'ok simulated').input.verdict;
const PAY_TO = '0x1111111111111111111111111111111111111111';

function mockFacilitator() {
  const calls = [];
  return {
    calls,
    async getSupported() {
      return {
        kinds: [{x402Version: 2, scheme: 'exact', network: 'eip155:84532'}],
        extensions: [],
        signers: {},
      };
    },
    async verify() {
      calls.push('verify');
      return {isValid: true, payer: PAY_TO};
    },
    async settle(_payload, requirements) {
      calls.push(requirements);
      return {
        success: true,
        transaction: `0x${'ab'.repeat(32)}`,
        network: requirements.network,
        payer: PAY_TO,
      };
    },
  };
}

test('unpaid release asks for Base Sepolia bound to the receipt', async () => {
  const facilitator = mockFacilitator();
  const {app, server} = await createReleaseApp({
    facilitatorClient: facilitator,
    payTo: PAY_TO,
    amount: '500000',
    receipt,
  });
  assert.equal(server.hasRegisteredScheme('eip155:84532', 'exact'), true);
  assert.equal(server.hasRegisteredScheme('eip155:8453', 'exact'), false);
  assert.equal(server.hasRegisteredScheme('eip155:*', 'exact'), false);
  const response = await app.request('/release');
  assert.equal(response.status, 402);
  const header = response.headers.get('payment-required');
  const required = JSON.parse(Buffer.from(header, 'base64').toString('utf8'));
  assert.equal(required.accepts.length, 1);
  assert.equal(required.accepts[0].network, 'eip155:84532');
  assert.equal(required.accepts[0].amount, '500000');
  assert.equal(required.accepts[0].extra.receiptHash, receipt.hash);
  assert.equal(required.accepts[0].extra.taskId, receipt.task_id);
});

test('client policy keeps only the matching Base Sepolia receipt', () => {
  const policy = receiptPaymentPolicy(receipt, 1_000_000n);
  const kept = policy(2, [
    {network: 'eip155:8453', amount: '1', extra: {receiptHash: receipt.hash, taskId: receipt.task_id}},
    {network: 'eip155:84532', amount: '0', extra: {receiptHash: receipt.hash, taskId: receipt.task_id}},
    {network: 'eip155:84532', amount: '1', extra: {receiptHash: 'nope', taskId: receipt.task_id}},
    {network: 'eip155:84532', amount: '1', extra: {receiptHash: receipt.hash, taskId: receipt.task_id}},
  ]);
  assert.equal(kept.length, 1);
  assert.equal(kept[0].network, 'eip155:84532');
});

test('injected facilitator settles once and a replay does not settle again', async () => {
  const facilitator = mockFacilitator();
  const ledger = new ReleaseLedger();
  const secret = generatePrivateKey();
  const first = await settleOnce({
    receipt,
    amount: '1',
    payTo: PAY_TO,
    payerKey: secret,
    facilitatorClient: facilitator,
    ledger,
  });
  assert.equal(first.ok, true, JSON.stringify(first));
  assert.equal(first.settled, true);
  assert.equal(JSON.stringify(first).includes(secret), false);
  assert.equal(JSON.stringify(first).includes(secret.slice(2)), false);
  const settlements = facilitator.calls.filter((call) => typeof call === 'object');
  assert.equal(settlements.length, 1);
  assert.equal(settlements[0].extra.receiptHash, receipt.hash);
  assert.equal(settlements[0].extra.taskId, receipt.task_id);
  assert.equal(settlements[0].network, 'eip155:84532');
  const second = await settleOnce({
    receipt,
    amount: '1',
    payTo: PAY_TO,
    payerKey: secret,
    facilitatorClient: facilitator,
    ledger,
  });
  assert.equal(second.reason, 'replay');
  assert.equal(second.settled, false);
  assert.equal(facilitator.calls.filter((call) => typeof call === 'object').length, 1);
});

test('amount and facilitator failures stop before settlement', async () => {
  const secret = '12'.repeat(32);
  const zero = await settleOnce({receipt, amount: '0', payTo: PAY_TO, payerKey: secret, facilitatorUrl: 'https://example.com'});
  assert.equal(zero.reason, 'amount_not_positive');
  const negative = await settleOnce({receipt, amount: '-1', payTo: PAY_TO, payerKey: secret});
  assert.equal(negative.reason, 'amount_not_positive');
  const foreign = await settleOnce({
    receipt,
    amount: '1',
    payTo: PAY_TO,
    payerKey: secret,
    facilitatorUrl: 'https://example.com/facilitator',
    ledger: new ReleaseLedger(),
  });
  assert.equal(foreign.reason, 'facilitator_not_allowlisted');
  assert.equal(JSON.stringify(foreign).includes(secret), false);
});

test('loopback facilitator is allowed only as an explicit test option', () => {
  assert.equal(facilitatorAllowed('http://127.0.0.1:9'), false);
  assert.equal(facilitatorAllowed('http://127.0.0.1:9', {allowLoopback: true}), true);
  assert.equal(facilitatorAllowed('https://example.com/facilitator', {allowLoopback: true}), false);
  assert.equal(facilitatorAllowed('https://x402.org/facilitator/'), true);
});

test('a facilitator error does not echo the payer key', async () => {
  const secret = `0x${'ee'.repeat(32)}`;
  const broken = {
    async getSupported() {
      throw new Error(`leaked ${secret}`);
    },
    async verify() {
      return {isValid: false};
    },
    async settle() {
      return {success: false, transaction: '0x', network: 'eip155:84532'};
    },
  };
  const result = await settleOnce({
    receipt,
    amount: '1',
    payTo: PAY_TO,
    payerKey: secret,
    facilitatorClient: broken,
    ledger: new ReleaseLedger(),
  });
  assert.equal(result.reason, 'live_failed');
  assert.equal(JSON.stringify(result).includes('ee'.repeat(32)), false);
  assert.equal(redact(`see ${secret}`, secret).includes('ee'.repeat(32)), false);
});

test('live module registers only Base Sepolia', () => {
  const source = readFileSync(new URL('./x402-live.mjs', import.meta.url), 'utf8');
  assert.equal(/eip155:\*/.test(source), false);
  assert.equal(source.includes('registerExactEvmScheme'), false);
  assert.equal(/eip155:8453(?!\d)/.test(source), false);
  assert.equal(source.includes('register(BASE_SEPOLIA_NETWORK'), true);
});
