# AOX × Agent Spend Guard: VerifiedCompletion interface (design only)

- **Status:** design draft, docs only. Accepted into the main line on 2026-10-10. Nothing here is implemented, deployed or connected. No payment of any kind is made or enabled by this document.
- **Date:** 2026-10-09 (MT).
- **Scope:** **testnet only.** Mainnet is out of scope. Any mainnet chain id, unknown network or missing mode fails closed.
- **Source of the requirement:** an internal planning document ("division plan" below, 2026-10-09; not published). §3.2 describes the guard as "a policy contract plus an off-chain guard that blocks over-limit, unknown-counterparty or prompt-injected payments, with receipts"; §7 (30-day roadmap) lists its policy as "per-tx and daily caps, counterparty allowlist, x402 quote checks, prompt-injection heuristics, human-approval threshold, signed receipts. Testnet only"; §4 adds "an MCP 'payment guard' tool that any agent calls before paying (x402/USDG)"; §6 and §7 name `aegis` as the core. The lane brief asks AOX to "expose AOX acceptance checks so the guard can require 'verified completion' before any (testnet) payment release".
- **What this document does not assume:** anything about `aegis` internals, the guard's code, the x402 wire format, USDG contracts or Robinhood Chain. The guard spec does not exist yet (plan §7 item 2 is still open). This is the AOX side of a contract between the two.

## 1. The rule in one line

**The guard releases a testnet payment for agent work only if it holds a valid, unexpired, unused, correctly bound AOX VerifiedCompletion with `outcome = pass` from an allowlisted verifier. Anything else is DENY.**

AOX never moves money, never sees a wallet, address, asset or chain id, and never calls the guard. The guard reads an attestation and decides. That keeps the AOX anti-jobs intact (simulated credits only; spec v0.1 §9.1 "No value escape") and keeps custody and payment logic entirely on the guard side.

## 2. Flow

```text
 requester agent           AOX (offline lab)                  verifier               spend guard (testnet)
      |  1. open engagement     |                                 |                         |
      |  + guard_binding ------>|  stores binding as opaque hash  |                         |
      |                         |---- 2. deliverable ------------>|                         |
      |                         |<--- 3. VerifiedCompletion ------|  (signed)               |
      |  4. payment intent + attestation ------------------------------------------------->|
      |                         |                                 |      5. checks §5       |
      |<--------------------------------------------------- 6. ALLOW or DENY + guard receipt|
```

`guard_binding` is how the payment and the work are tied together without AOX learning payment details. The guard (or the requester through the guard) computes `guard_binding = sha256(JCS(payment_intent_core))`, where `payment_intent_core` is whatever the guard considers the payment's identity (e.g. its own intent id, payee, amount, asset, chain). AOX stores the 64-hex string opaquely and copies it into the attestation. At release time the guard recomputes it from the intent in front of it and requires equality. A swapped payee or amount breaks the binding.

## 3. VerifiedCompletion v0.1 (fields)

All fields are required unless marked optional. Times are RFC 3339 UTC with `Z`.

| field | type | meaning / rule |
|---|---|---|
| `type` | const `"aox.verified_completion"` | |
| `schema_version` | const `"0.1"` | the guard rejects unknown versions |
| `attestation_id` | UUIDv4 | unique per attestation |
| `mode` | `"sim"` or `"testnet"` | the guard accepts only `"testnet"`; `"sim"` attestations are for tests. No other value is valid |
| `engagement_id` | string | AOX engagement id; must equal the id named in the payment intent |
| `request_id` | string | AOX request id |
| `contract` | `{contract_id, version, contract_hash}` | `contract_hash` = `sha256:` + hex of JCS(contract without its hash field) (protocol.md §2.1) |
| `input_hash` | `sha256:<hex>` | of JCS(input payload) |
| `deliverable_hash` | `sha256:<hex>` | of JCS(deliverable) |
| `provider_agent_id`, `requester_agent_id` | string | AOX ids (not wallets) |
| `verifier` | `{verifier_id, key_id, kind}` | `kind ∈ {deterministic, agent, operator}`; `verifier_id` must differ from both agent ids |
| `independence` | `"independent"` or `"operator_shared"` | see protocol.md §2.2 |
| `outcome` | `pass` / `partial` / `fail` / `inconclusive` | |
| `checks` | list of `{check_id, kind, result}` | `result ∈ {pass, fail, skipped}`; must cover every check in the contract version |
| `guard_binding` | 64-hex string | opaque, copied from the engagement (§2) |
| `issued_at` | timestamp | |
| `expires_at` | timestamp | proposed max lifetime 24 h after `issued_at` |
| `nonce` | 32-hex (128-bit random) | single-use |
| `prev_attestation_id` | UUID, optional | set when a resubmission replaces an earlier `fail` |
| `signature` | `{alg: "Ed25519", key_id, sig}` | `sig` = base64url Ed25519 signature over the bytes of JCS(attestation **without** `signature` and `attestation_hash`) |
| `attestation_hash` | `sha256:<hex>` | of the same canonical bytes; what the guard logs in its receipt |

Design choices (proposals, open to the guard's needs): SHA-256 + RFC 8785 JCS so any language can recompute hashes byte-for-byte; Ed25519 because it is deterministic and has no parameter choices. If the guard prefers EIP-712 / keccak256 so a policy contract can verify on-chain, a second encoding can be added under `schema_version "0.2"`; this document does not pick a chain format. ERC-8004 export (protocol.md §5) would use keccak256 of the same canonical bytes as `responseHash`.

Example (synthetic, unsigned values are placeholders):

```json
{
  "type": "aox.verified_completion",
  "schema_version": "0.1",
  "attestation_id": "3b0f6c9e-2d1a-4c55-9a0e-6f7d2b1c8e44",
  "mode": "testnet",
  "engagement_id": "eng-000123",
  "request_id": "req-000456",
  "contract": {"contract_id": "json.extract", "version": "1.0.0", "contract_hash": "sha256:<64 hex>"},
  "input_hash": "sha256:<64 hex>",
  "deliverable_hash": "sha256:<64 hex>",
  "provider_agent_id": "agent-provider-a",
  "requester_agent_id": "agent-requester-b",
  "verifier": {"verifier_id": "verifier-det-1", "key_id": "aox-ver-2026-10", "kind": "deterministic"},
  "independence": "independent",
  "outcome": "pass",
  "checks": [{"check_id": "schema", "kind": "schema", "result": "pass"},
             {"check_id": "known_answer", "kind": "known_answer", "result": "pass"}],
  "guard_binding": "<64 hex>",
  "issued_at": "2026-10-09T18:30:00Z",
  "expires_at": "2026-10-10T18:30:00Z",
  "nonce": "<32 hex>",
  "signature": {"alg": "Ed25519", "key_id": "aox-ver-2026-10", "sig": "<base64url>"},
  "attestation_hash": "sha256:<64 hex>"
}
```

## 4. Interface

```text
// AOX side (read-only from the guard's point of view; offline file or local call in v0.3)
aox.get_verified_completion(engagement_id) -> VerifiedCompletion | NOT_FOUND

// Guard side (the guard's MCP tool would expose something like this; names are proposals)
guard.require_verified_completion(payment_intent, attestation) -> {decision: ALLOW | DENY, reason_code, attestation_hash}
guard.consume_attestation(attestation_id, nonce)              -> OK | ALREADY_CONSUMED   // atomic, called only on ALLOW, before release
```

`payment_intent` must carry at least `aox_engagement_id`, the fields the guard hashes into `guard_binding`, and the testnet chain id. The guard's own caps, allowlists, x402 quote checks, injection heuristics and human-approval threshold run **in addition** to this check, never instead of it.

## 5. Guard checks (all must pass; any failure is DENY)

| # | check | reason_code on failure |
|---|---|---|
| 1 | Parses; `type` and `schema_version` known; every required field present | `MALFORMED` / `UNKNOWN_VERSION` |
| 2 | `mode == "testnet"` and the intent's chain id is on the guard's **testnet** allowlist. Mainnet ids, unknown ids, empty values: deny | `MODE_FORBIDDEN` |
| 3 | `signature.key_id` is on the guard's pinned verifier-key allowlist, and the Ed25519 signature verifies over the recomputed canonical bytes | `UNTRUSTED_VERIFIER` / `BAD_SIGNATURE` |
| 4 | Recomputed `attestation_hash` matches | `HASH_MISMATCH` |
| 5 | `verifier.verifier_id ∉ {provider_agent_id, requester_agent_id}` | `VERIFIER_NOT_INDEPENDENT` |
| 6 | `outcome == "pass"`. `partial`, `fail`, `inconclusive`: deny (partial release is out of scope for v0.1; it goes to human approval) | `NOT_PASSED` |
| 7 | `contract.contract_id@version` is on the guard's contract allowlist and `contract_hash` equals the pinned hash for that version | `CONTRACT_NOT_ALLOWED` |
| 8 | `checks[]` covers every check of that contract version, all `pass` | `CHECKS_INCOMPLETE` |
| 9 | `engagement_id` equals the intent's `aox_engagement_id`, and `guard_binding` equals the guard's recomputed hash of the intent | `BINDING_MISMATCH` |
| 10 | `issued_at ≤ now + 60 s` and `now < expires_at`, lifetime ≤ 24 h | `EXPIRED` / `NOT_YET_VALID` |
| 11 | `attestation_id` and `nonce` never consumed before; consume atomically before release | `REPLAY` |
| 12 | Any error, timeout, missing attestation, or AOX unreachable | `UNAVAILABLE` (deny, never "allow and log") |

Replay protection comes from three layers: the single-use `nonce` + `attestation_id` store (check 11), the short expiry (check 10), and the binding to one engagement and one payment intent (check 9). Re-using an attestation for a second payment fails 11; using it for a different payee or amount fails 9.

## 6. Guard receipt fields (what AOX expects to see logged)

So that AOX's ledger and the guard's receipt can be reconciled offline: `decision`, `reason_code`, `attestation_hash`, `engagement_id`, `contract_id@version`, `verifier.key_id`, `checked_at`, and the guard's own payment-intent id. The guard signs its receipt with its own key (plan §7: "signed receipts"). AOX does not ingest guard receipts into reputation.

## 7. Tests to write (design only, against fakes, no chain)

1. Golden vector: a fixed attestation, test key and expected `attestation_hash` + signature; two independent implementations agree byte-for-byte.
2. Each row of §5 has a negative test that produces exactly its `reason_code`.
3. Mode: `mainnet`, `prod`, `""`, `null`, unknown chain id all DENY.
4. Replay: second use of the same attestation is DENY even with a different intent; concurrent double-consume yields one OK and one `ALREADY_CONSUMED`.
5. Tampering any single field (including whitespace-insensitive reorderings that change values) breaks the signature or hash.
6. AOX unreachable or attestation missing: DENY.
7. A valid `sim` attestation is DENY in a testnet guard.

## 8. Open items and owner decisions

- **Verifier signing key:** where it lives and who holds it. No key exists. Creating one is an owner decision; it must not live in the repo.
- **Guard spec:** plan §7 item 2 is not written yet; field names in §4 may change to match it.
- **Partial outcomes:** whether a `partial` should ever release a pro-rated testnet amount. Default here: no.
- **On-chain verification:** whether the policy contract should verify attestations itself (needs an EIP-712 encoding) or trust the off-chain guard. Not decided; no on-chain work is in scope for AOX.
- **Legal posture (plan §8):** the guard must pay from the client's own wallet; neither AOX nor the guard custodies or forwards others' funds. This interface carries no funds and no addresses.
