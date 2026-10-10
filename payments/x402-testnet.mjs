/**
 * OK-only Base Sepolia payment gate. Simulated by default.
 *
 * Adapted from arigatoexpress/agent-opportunity-exchange src/x402-testnet.ts
 * (blob e3f8e38c3f0f339967ec4eae51e8e273185c3b2c, commit 8ef5daf6) and the
 * client cap in scripts/x402-testnet-fetch.ts (blob c024c0b4). The original
 * file attached @x402/hono middleware to artifact routes. This port keeps the
 * testnet gate and spends no funds. A release requires a replayed receipt
 * whose verdict is OK. The author relicenses this ported rail under the
 * Apache License 2.0. No SDK import, no private key, no fetch.
 */

import {
  BASE_SEPOLIA_NETWORK,
  MAINNET_NETWORKS,
  amountProblem,
  formatUsd,
  getReadyX402TestnetConfig,
  getX402PaymentStatus,
  privateKeyPresent,
  usdToMicros,
} from './x402-config.mjs';
import {replayReceipt} from './receipt.mjs';

export class ReleaseLedger {
  constructor() {
    this.used = new Set();
  }

  consume(receiptHash) {
    if (typeof receiptHash !== 'string' || !receiptHash || this.used.has(receiptHash)) return false;
    this.used.add(receiptHash);
    return true;
  }
}

const processLedger = new ReleaseLedger();

export function createX402TestnetGate(env = {}) {
  const status = getX402PaymentStatus(env);
  const config = getReadyX402TestnetConfig(env);
  const gate = {status, gateActive: config !== null, liveSettlementAllowed: false};
  if (config) gate.config = config;
  return gate;
}

export function decideRelease(spec = {}, options = {}) {
  const env = spec.env || {};
  const ledger = options.ledger || processLedger;
  const modeText = spec.mode === undefined ? 'simulated' : String(spec.mode);
  const network = spec.network === undefined ? BASE_SEPOLIA_NETWORK : String(spec.network).trim();
  const result = {
    decision: 'DENY',
    reason: 'verdict_not_ok',
    verdict: null,
    mode: 'simulated',
    network,
    amount: typeof spec.amount === 'string' ? spec.amount : null,
    appliedMaxUsd: null,
    liveSettlementAllowed: false,
    settled: false,
    simulated: false,
  };
  if (privateKeyPresent(env)) return deny(result, 'private_key_refused');
  const errors = [];
  const mode = paymentMode(modeText, errors);
  result.mode = mode;
  result.simulated = mode === 'simulated';
  if (errors.length) return deny(result, 'unsupported_mode');
  const envNetwork = envMainnet(env);
  if (MAINNET_NETWORKS.has(network) || envNetwork) {
    result.network = MAINNET_NETWORKS.has(network) ? network : envNetwork;
    return deny(result, 'mainnet_network_blocked');
  }
  if (network !== BASE_SEPOLIA_NETWORK) return deny(result, 'unsupported_network');
  if (mode === 'x402_testnet') {
    const statusEnv = {...env, AOX_PAYMENT_MODE: env.AOX_PAYMENT_MODE ?? env.AOE_PAYMENT_MODE ?? 'x402_testnet'};
    if (statusEnv.AOX_X402_NETWORK === undefined && statusEnv.AOE_X402_NETWORK === undefined) {
      statusEnv.AOX_X402_NETWORK = BASE_SEPOLIA_NETWORK;
    }
    const status = getX402PaymentStatus(statusEnv);
    if (!status.ready) {
      if (status.errors.includes('facilitator_not_allowlisted')) return deny(result, 'facilitator_not_allowlisted');
      return deny(result, 'config_not_ready');
    }
  }
  const parsed = readVerdict(spec.verdict);
  if (parsed.receipt) {
    result.receiptHash = parsed.receipt.hash;
    result.taskId = parsed.receipt.task_id;
  }
  if (parsed.error || parsed.verdict !== 'OK') {
    result.verdict = parsed.verdict;
    return deny(result, parsed.error || 'verdict_not_ok');
  }
  result.verdict = parsed.verdict;
  let cap;
  try {
    cap = usdToMicros(spec.maxUsd === undefined ? '1.00' : spec.maxUsd);
  } catch {
    return deny(result, 'malformed_cap');
  }
  result.appliedMaxUsd = formatUsd(cap);
  const amountError = amountProblem(spec.amount);
  if (amountError) return deny(result, amountError);
  if (BigInt(spec.amount) > cap) return deny(result, 'spend_cap');
  if (!ledger.consume(parsed.receipt.hash)) return deny(result, 'replay');
  result.decision = 'RELEASE';
  result.reason = 'ok';
  result.settled = false;
  if (options.settler && mode === 'x402_testnet') {
    const payload = {
      network,
      amount: spec.amount,
      verdict: parsed.verdict,
      receiptHash: parsed.receipt.hash,
      taskId: parsed.receipt.task_id,
    };
    if (options.settler(payload) === true) result.settled = true;
  }
  return result;
}

function readVerdict(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {verdict: null, receipt: null, error: 'receipt_required'};
  }
  try {
    const receipt = replayReceipt(value);
    return {verdict: receipt.verdict, receipt, error: null};
  } catch {
    return {verdict: null, receipt: null, error: 'receipt_rejected'};
  }
}

function paymentMode(value, errors) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === 'simulated') return 'simulated';
  if (normalized === 'x402_testnet' || normalized === 'testnet') return 'x402_testnet';
  errors.push(`unsupported_payment_mode:${normalized}`);
  return 'simulated';
}

function envMainnet(env) {
  for (const key of ['AOX_X402_NETWORK', 'AOE_X402_NETWORK', 'AOX_TESTNET_NETWORK', 'AOE_TESTNET_NETWORK']) {
    if (Object.prototype.hasOwnProperty.call(env, key) && MAINNET_NETWORKS.has(String(env[key]).trim())) {
      return String(env[key]).trim();
    }
  }
  return null;
}

function deny(result, reason) {
  result.decision = 'DENY';
  result.reason = reason;
  result.settled = false;
  return result;
}
