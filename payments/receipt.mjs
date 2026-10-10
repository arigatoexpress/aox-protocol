/**
 * Replay an aox-verdict-receipt@1 object.
 *
 * The digest matches verdict.py: SHA-256 over canonical JSON with sorted keys
 * and no extra whitespace. A matching hash is internally consistent. It does
 * not authenticate an author.
 */

import {createHash} from 'node:crypto';

export const FORMAT = 'aox-verdict-receipt@1';
const FIELDS = ['format', 'provenance', 'contract', 'task_id', 'verdict', 'evidence', 'reasons', 'hash'];
const EVIDENCE = new Set(['present', 'missing', 'malformed', 'timed_out']);
const VERDICTS = new Set(['OK', 'FAILED', 'UNKNOWN']);

export function replayReceipt(receipt) {
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) {
    throw new Error('unsupported verdict receipt');
  }
  const keys = Object.keys(receipt);
  if (keys.length !== FIELDS.length || FIELDS.some((key) => !Object.prototype.hasOwnProperty.call(receipt, key))) {
    throw new Error('unsupported verdict receipt');
  }
  if (receipt.format !== FORMAT || receipt.provenance !== 'synthetic') {
    throw new Error('only synthetic verdict receipts are supported');
  }
  identifier(receipt.task_id, 'task_id');
  identifier(receipt.contract, 'contract');
  if (!EVIDENCE.has(receipt.evidence)) throw new Error('unknown evidence kind');
  const reasons = receipt.reasons;
  if (!Array.isArray(reasons) || reasons.length > 32 || reasons.some((item) => typeof item !== 'string' || item.length > 240)) {
    throw new Error('reasons are not a short list of strings');
  }
  if (!VERDICTS.has(receipt.verdict)) throw new Error('receipt verdict is not a three-state Verdict');
  if (receipt.evidence === 'present') {
    if (receipt.verdict === 'UNKNOWN') throw new Error('present evidence cannot be UNKNOWN');
    if (receipt.verdict === 'OK' && reasons.length) throw new Error('OK cannot carry reasons');
  } else if (receipt.verdict !== 'UNKNOWN' || reasons.length) {
    throw new Error('missing evidence must be UNKNOWN');
  }
  const body = {};
  for (const key of FIELDS) {
    if (key !== 'hash') body[key] = receipt[key];
  }
  if (typeof receipt.hash !== 'string' || receipt.hash !== digest(body)) {
    throw new Error('verdict receipt hash mismatch');
  }
  return receipt;
}

function identifier(value, label) {
  if (typeof value !== 'string' || !value || value.length > 128) {
    throw new Error(`${label} must be a short string`);
  }
}

function digest(body) {
  return createHash('sha256').update(JSON.stringify(sortValue(body))).digest('hex');
}

function sortValue(value) {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === 'object') {
    const sorted = {};
    for (const key of Object.keys(value).sort()) sorted[key] = sortValue(value[key]);
    return sorted;
  }
  return value;
}
