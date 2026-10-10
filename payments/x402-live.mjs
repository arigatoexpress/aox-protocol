/**
 * Opt-in Base Sepolia settlement.
 *
 * The simulated gate in x402-testnet.mjs stays the default. This module is
 * used only when the demo is started with --live-testnet, or by a test that
 * injects a facilitator. It registers eip155:84532 and no other network.
 * The payer key is never written to the result or to a ledger file.
 */

import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {dirname} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {Hono} from 'hono';
import {paymentMiddleware, x402ResourceServer} from '@x402/hono';
import {HTTPFacilitatorClient} from '@x402/core/server';
import {ExactEvmScheme as ExactEvmSchemeServer} from '@x402/evm/exact/server';
import {x402Client} from '@x402/core/client';
import {ExactEvmScheme as ExactEvmSchemeClient} from '@x402/evm/exact/client';
import {wrapFetchWithPayment} from '@x402/fetch';
import {privateKeyToAccount} from 'viem/accounts';
import {
  BASE_SEPOLIA_NETWORK,
  amountProblem,
  facilitatorAllowed,
  usdToMicros,
} from './x402-config.mjs';
import {replayReceipt} from './receipt.mjs';

const LEDGER_FILE = fileURLToPath(new URL('../.aox-release-ledger.json', import.meta.url));

export function redact(text, secret) {
  let out = String(text);
  const raw = String(secret || '').trim();
  if (!raw) return out;
  const prefixed = raw.startsWith('0x') || raw.startsWith('0X') ? raw : `0x${raw}`;
  const bare = prefixed.slice(2);
  if (prefixed) out = out.split(prefixed).join('[redacted]');
  if (bare) out = out.split(bare).join('[redacted]');
  return out;
}

export function receiptPaymentPolicy(receipt, capMicros) {
  return (_version, requirements) => requirements.filter((requirement) => {
    if (requirement.network !== BASE_SEPOLIA_NETWORK) return false;
    const extra = requirement.extra || {};
    if (extra.receiptHash !== receipt.hash || extra.taskId !== receipt.task_id) return false;
    try {
      const amount = BigInt(requirement.amount);
      if (amount < 1n || amount > capMicros) return false;
    } catch {
      return false;
    }
    return true;
  });
}

export class FileReleaseLedger {
  constructor(filePath) {
    this.filePath = filePath;
    this.used = new Set();
    try {
      const data = JSON.parse(readFileSync(filePath, 'utf8') || '[]');
      if (!Array.isArray(data) || data.some((item) => typeof item !== 'string')) {
        throw new Error('release ledger must be a list of hashes');
      }
      for (const item of data) this.used.add(item);
    } catch (error) {
      if (error && error.code !== 'ENOENT') throw error;
    }
  }

  consume(receiptHash) {
    if (typeof receiptHash !== 'string' || !receiptHash || this.used.has(receiptHash)) return false;
    this.used.add(receiptHash);
    mkdirSync(dirname(this.filePath), {recursive: true});
    writeFileSync(this.filePath, JSON.stringify([...this.used].sort()));
    return true;
  }
}

export async function createReleaseApp({facilitatorClient, payTo, amount, receipt}) {
  const server = new x402ResourceServer(facilitatorClient);
  server.register(BASE_SEPOLIA_NETWORK, new ExactEvmSchemeServer());
  const routes = {
    'GET /release': {
      accepts: {
        scheme: 'exact',
        payTo,
        price: minorToPrice(amount),
        network: BASE_SEPOLIA_NETWORK,
        extra: {receiptHash: receipt.hash, taskId: receipt.task_id},
      },
      description: 'Synthetic AOX verdict release',
      mimeType: 'application/json',
    },
  };
  const app = new Hono();
  app.use(paymentMiddleware(routes, server, undefined, undefined, false));
  app.get('/release', (c) => c.json({released: true}));
  await server.initialize();
  return {app, server};
}

export async function settleOnce(options = {}) {
  const secret = String(options.payerKey || '');
  const previousError = console.error;
  const previousWarn = console.warn;
  console.error = (...args) => previousError(redact(args.map(String).join(' '), secret));
  console.warn = (...args) => previousWarn(redact(args.map(String).join(' '), secret));
  try {
    return await settleBody(options);
  } catch (error) {
    return {
      ok: false,
      settled: false,
      reason: 'live_failed',
      message: redact(errorText(error), secret),
    };
  } finally {
    console.error = previousError;
    console.warn = previousWarn;
  }
}

async function settleBody(options) {
  const secret = String(options.payerKey || '');
  if (!options.receipt || typeof options.receipt !== 'object' || Array.isArray(options.receipt)) {
    return {ok: false, settled: false, reason: 'receipt_required'};
  }
  let receipt;
  try {
    receipt = replayReceipt(options.receipt);
  } catch {
    return {ok: false, settled: false, reason: 'receipt_rejected'};
  }
  if (receipt.verdict !== 'OK') return {ok: false, settled: false, reason: 'verdict_not_ok'};
  const amountError = amountProblem(options.amount);
  if (amountError) return {ok: false, settled: false, reason: amountError};
  let cap;
  try {
    cap = usdToMicros(options.maxUsd === undefined ? '1.00' : options.maxUsd);
  } catch {
    return {ok: false, settled: false, reason: 'malformed_cap'};
  }
  if (BigInt(options.amount) > cap) return {ok: false, settled: false, reason: 'spend_cap'};
  if (!/^0x[a-fA-F0-9]{40}$/.test(String(options.payTo || ''))) {
    return {ok: false, settled: false, reason: 'invalid_pay_to'};
  }
  if (!options.facilitatorClient) {
    if (!facilitatorAllowed(options.facilitatorUrl, {allowLoopback: options.allowLoopback === true})) {
      return {ok: false, settled: false, reason: 'facilitator_not_allowlisted'};
    }
  }
  if (!secret.trim()) return {ok: false, settled: false, reason: 'missing_payer_key'};
  if (options.ledgerConsumed !== true) {
    const ledger = options.ledger || new FileReleaseLedger(LEDGER_FILE);
    if (!ledger.consume(receipt.hash)) return {ok: false, settled: false, reason: 'replay'};
  }
  const facilitatorClient = options.facilitatorClient || new HTTPFacilitatorClient({url: String(options.facilitatorUrl).trim().replace(/\/+$/, '')});
  const {app} = await createReleaseApp({
    facilitatorClient,
    payTo: options.payTo,
    amount: options.amount,
    receipt,
  });
  const account = privateKeyToAccount(secret.startsWith('0x') || secret.startsWith('0X') ? secret : `0x${secret}`);
  const client = new x402Client();
  client.register(BASE_SEPOLIA_NETWORK, new ExactEvmSchemeClient(account));
  client.setSpendControls({maxAmountPerPayment: minorToPrice(cap.toString())});
  client.registerPolicy(receiptPaymentPolicy(receipt, cap));
  const paidFetch = wrapFetchWithPayment(async (input, init) => app.request(new Request(input, init)), client);
  const response = await paidFetch('http://127.0.0.1/release');
  if (!response.ok) return {ok: false, settled: false, reason: 'settlement_failed', status: response.status};
  return {ok: true, settled: true, reason: 'ok', status: response.status};
}

function minorToPrice(amount) {
  const value = BigInt(amount);
  const whole = value / 1_000_000n;
  const frac = (value % 1_000_000n).toString().padStart(6, '0').replace(/0+$/, '');
  return frac ? `$${whole}.${frac}` : `$${whole}`;
}

function errorText(error) {
  if (!error) return '';
  const message = error instanceof Error ? error.message : String(error);
  const cause = error instanceof Error && error.cause ? ` ${errorText(error.cause)}` : '';
  return `${message}${cause}`;
}

async function main() {
  const secret = process.env.TESTNET_PAYER_KEY || '';
  const input = JSON.parse(readFileSync(0, 'utf8'));
  const result = await settleOnce({
    receipt: input.receipt,
    amount: input.amount,
    payTo: input.payTo,
    facilitatorUrl: input.facilitatorUrl,
    maxUsd: input.maxUsd,
    payerKey: secret,
    ledgerConsumed: input.ledgerConsumed === true,
  });
  process.stdout.write(`${redact(JSON.stringify(result), secret)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    const secret = process.env.TESTNET_PAYER_KEY || '';
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${redact(message, secret)}\n`);
    process.exitCode = 1;
  });
}
