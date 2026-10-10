/**
 * Base Sepolia x402 configuration.
 *
 * Ported from arigatoexpress/agent-opportunity-exchange src/x402-config.ts
 * (blob afbf62a9438f497b777a7f797c6e620064cbe369, commit 8ef5daf6).
 * The source repo is public and archived. No LICENSE file was present on
 * 2026-10-10. AOX_ names are accepted beside the original AOE_ names.
 * The author relicenses this ported rail under the Apache License 2.0.
 * This file does not read the process environment and does not open a connection.
 */

export const BASE_SEPOLIA_NETWORK = 'eip155:84532';
export const SOLANA_DEVNET_NETWORK = 'solana-devnet';
export const DEFAULT_FACILITATOR_URL = 'https://x402.org/facilitator';
export const ALLOWED_FACILITATORS = new Set([DEFAULT_FACILITATOR_URL]);
export const MAINNET_NETWORKS = new Set([
  'eip155:8453',
  'solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp',
  'stellar:pubnet',
]);
const HARD_CAP_MICROS = 5_000_000;

const MODE_KEYS = ['AOX_PAYMENT_MODE', 'AOE_PAYMENT_MODE'];
const NETWORK_KEYS = ['AOX_X402_NETWORK', 'AOE_X402_NETWORK', 'AOX_TESTNET_NETWORK', 'AOE_TESTNET_NETWORK'];
const FACILITATOR_KEYS = ['AOX_X402_FACILITATOR_URL', 'AOE_X402_FACILITATOR_URL', 'X402_FACILITATOR_URL'];
const PAY_TO_KEYS = ['AOX_X402_PAY_TO', 'AOE_X402_PAY_TO', 'EVM_PAY_TO'];
const PRIVATE_KEY_KEYS = [
  'AOX_BUYER_EVM_PRIVATE_KEY',
  'AOE_BUYER_EVM_PRIVATE_KEY',
  'AOX_PRIVATE_KEY',
  'EVM_PRIVATE_KEY',
  'PRIVATE_KEY',
];

export function getX402PaymentStatus(env = {}) {
  const errors = [];
  const warnings = [];
  if (privateKeyPresent(env)) errors.push('private_key_refused');
  const mode = paymentMode(pick(env, MODE_KEYS, 'simulated'), errors);
  const network = pick(env, NETWORK_KEYS, BASE_SEPOLIA_NETWORK).trim();
  const facilitatorUrl = pick(env, FACILITATOR_KEYS, DEFAULT_FACILITATOR_URL).trim().replace(/\/+$/, '');
  const payTo = pick(env, PAY_TO_KEYS, '').trim();

  if (network !== BASE_SEPOLIA_NETWORK) errors.push(`unsupported_network:${network || 'empty'}`);
  if (MAINNET_NETWORKS.has(network)) errors.push(`mainnet_network_blocked:${network}`);
  const facilitatorError = facilitatorProblem(facilitatorUrl);
  if (facilitatorError) errors.push(facilitatorError);
  if (mode === 'x402_testnet' && !payTo) errors.push('missing_AOX_X402_PAY_TO');
  if (payTo && !isAddress(payTo)) errors.push('invalid_AOX_X402_PAY_TO');
  if (mode === 'simulated' && payTo) warnings.push('pay-to is configured and ignored while payment mode is simulated');

  const ready = mode === 'x402_testnet' && errors.length === 0;
  const payToStatus = {configured: Boolean(payTo)};
  if (payTo && isAddress(payTo)) {
    payToStatus.address = payTo;
    payToStatus.redacted = `${payTo.slice(0, 6)}...${payTo.slice(-4)}`;
  }
  return {
    protocol: 'x402',
    mode,
    activeRail: mode === 'simulated' ? 'simulated_header' : ready ? 'official_x402_testnet' : 'x402_testnet_config_required',
    ready,
    liveSettlementAllowed: false,
    serverPrivateKeyRequired: false,
    network: {id: BASE_SEPOLIA_NETWORK, label: 'Base Sepolia', testnet: true, mainnet: false},
    facilitator: {url: facilitatorUrl.includes('@') ? '' : facilitatorUrl, defaultTestnet: facilitatorUrl === DEFAULT_FACILITATOR_URL},
    payTo: payToStatus,
    rails: rails(),
    acceptedAsset: 'USDC',
    errors,
    warnings,
  };
}

export function getReadyX402TestnetConfig(env = {}) {
  const status = getX402PaymentStatus(env);
  if (!status.ready || !status.payTo.address) return null;
  return {
    mode: 'x402_testnet',
    network: BASE_SEPOLIA_NETWORK,
    facilitatorUrl: status.facilitator.url,
    payTo: status.payTo.address,
  };
}

export function usdToMicros(value) {
  const text = String(value).trim();
  if (!text || text.startsWith('.') || (text.match(/\./g) || []).length > 1) throw new Error('malformed cap');
  const [whole, frac = ''] = text.split('.');
  if (!/^\d+$/.test(whole) || (text.includes('.') && !/^\d{1,6}$/.test(frac))) throw new Error('malformed cap');
  const micros = BigInt(whole) * 1_000_000n + BigInt((frac + '000000').slice(0, 6) || '0');
  if (micros <= 0n) throw new Error('cap must be positive');
  return micros > BigInt(HARD_CAP_MICROS) ? BigInt(HARD_CAP_MICROS) : micros;
}

export function formatUsd(micros) {
  const whole = micros / 1_000_000n;
  const frac = (micros % 1_000_000n).toString().padStart(6, '0');
  return `${whole}.${frac}`;
}

export function amountProblem(amount) {
  if (typeof amount !== 'string' || !/^-?\d{1,18}$/.test(amount)) return 'malformed_amount';
  if (BigInt(amount) < 1n) return 'amount_not_positive';
  return null;
}

export function isMinorUnits(amount) {
  return amountProblem(amount) === null;
}

const KEY_VALUE = /^(?:0x)?[a-fA-F0-9]{64}$/;

export function privateKeyPresent(env) {
  return Object.entries(env).some(([key, value]) => {
    const text = value === null || value === undefined ? '' : String(value).trim();
    if (!text) return false;
    return PRIVATE_KEY_KEYS.includes(key) || KEY_VALUE.test(text);
  });
}

export function facilitatorProblem(url) {
  if (!String(url).startsWith('https://')) return 'facilitator_url_must_be_https';
  if (!ALLOWED_FACILITATORS.has(url)) return 'facilitator_not_allowlisted';
  return null;
}

export function facilitatorAllowed(url, options = {}) {
  const normalized = String(url || '').trim().replace(/\/+$/, '');
  if (ALLOWED_FACILITATORS.has(normalized)) return true;
  if (options.allowLoopback && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(normalized)) return true;
  return false;
}

export function rails() {
  return [
    {
      railId: 'base-sepolia-official-x402',
      scheme: 'exact',
      network: BASE_SEPOLIA_NETWORK,
      runtime: 'evm',
      status: 'enabled_when_configured',
      asset: 'USDC',
      liveSettlementAllowed: false,
      serverPrivateKeyRequired: false,
      caveats: [
        'Requires AOX_PAYMENT_MODE=x402_testnet, AOX_X402_PAY_TO, and the allow-listed facilitator.',
        'Mainnet remains blocked.',
        'This policy module does not import the x402 SDK. Live settlement is the opt-in demo flag.',
      ],
    },
    {
      railId: 'solana-pay-sh-svm-candidate',
      scheme: 'exact',
      network: SOLANA_DEVNET_NETWORK,
      runtime: 'svm',
      status: 'planned_simulated_only',
      asset: 'USDC',
      liveSettlementAllowed: false,
      serverPrivateKeyRequired: false,
      caveats: ['No Solana wallet or facilitator call is enabled.'],
    },
  ];
}

function paymentMode(value, errors) {
  const normalized = String(value).trim().toLowerCase();
  if (!normalized || normalized === 'simulated') return 'simulated';
  if (normalized === 'x402_testnet' || normalized === 'testnet') return 'x402_testnet';
  errors.push(`unsupported_payment_mode:${normalized}`);
  return 'simulated';
}

function pick(env, keys, fallback) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(env, key) && env[key] !== null && env[key] !== undefined) return String(env[key]);
  }
  return fallback;
}

function isAddress(value) {
  return /^0x[a-fA-F0-9]{40}$/.test(value);
}

export {MAINNET_NETWORKS as mainnetNetworks, PRIVATE_KEY_KEYS};
