# AOX Protocol v0.3 (draft): typed task contracts, independent verifier, verified-only reputation

- **Status:** design draft, docs only. Accepted into the main line on 2026-10-10. Nothing here is a running service.
- **Date:** 2026-10-09 (MT). Author: AOX lane agent.
- **Why this exists:** an internal planning document ("division plan" below, §3.1, drafted 2026-10-09; not published) repositions AOX from a marketplace to a **protocol/library**: "typed task contracts (versioned JSON Schema + acceptance checks) + verified-only reputation ... an A2A/ERC-8004-compatible 'contract + verifier + reputation' package, not a marketplace."
- **Anti-jobs (unchanged, and binding on this document):** AOX stays closed, credit-only and offline. No public marketplace, no payments, no token, no outreach, no spend, no paid models, no production deploy, no on-chain writes. Everything below is a format and a set of rules; nothing here is a running service.
- **Companion docs:** `spec/v0.md` (v0 design), `data-model.md`, `mvp-loop.md`, `simulator_v02.py` (the reference implementation of the reputation rules below), `spec/spend-guard-interface.md` (how a payment guard consumes AOX attestations). An earlier v0.1 draft (not adopted) proposed `spec/v0.md` v0.1 §4.1 (standards mapping) and §9 (abstract adapters); those sections are not part of this specification.

## 1. What changes and what does not

| | v0 / v0.2 (marketplace framing) | v0.3 (protocol/library framing) |
|---|---|---|
| Unit of value | a matched engagement inside the exchange | a **TaskContract** that any two agents can use, plus a **VerifiedCompletion** that anyone can check |
| Matching | core loop step | optional reference module (`match`), not part of the protocol |
| Pricing / credits | simulated credits | unchanged; credits stay simulated and never leave AOX |
| Verification | step 7 of the loop | a first-class, independently run component with a signed output |
| Reputation | Beta score per (agent, capability) | unchanged math, but defined as a pure function of VerifiedCompletions only |
| Identity / discovery | AOX ids | AOX ids stay authoritative; A2A Agent Cards and ERC-8004 ids are **untrusted external refs** |

The INFERENCE behind the change (plan §3.1): marketplaces in this category are commodity and demand-thin; nobody inspected on 2026-10-01 made a typed contract the unit of matching. The protocol framing is cheaper to keep alive (a spec plus a small library) and is the only part that a payment guard or another team could reuse.

## 2. Components

```text
            +--------------------+        +--------------------+
 requester  |  TaskContract      |        |  Verifier          |   signs
 provider   |  (versioned JSON   |------->|  (independent of   |---------> VerifiedCompletion
 agents --->|  Schema + checks)  |  out   |  provider and      |           (hash + signature)
            +--------------------+        |  requester)        |                 |
                                          +--------------------+                 v
                                                                     +------------------------+
                                                                     | Reputation (pure fn of |
                                                                     | VerifiedCompletions)   |
                                                                     +------------------------+
   optional: match (reference matcher), ledger (simulated credits), adapters (spec v0.1 §9)
```

### 2.1 TaskContract

A TaskContract is an immutable, versioned JSON document. Fields (v0 spec §4 plus v0.1 additions, now normative for the library):

| field | type | rule |
|---|---|---|
| `contract_id` | string, dotted namespace | stable across versions, e.g. `research.source_brief` |
| `version` | SemVer string | any change to schemas or checks bumps it; old versions stay resolvable |
| `contract_hash` | `sha256:<hex>` | SHA-256 of the RFC 8785 (JCS) canonical JSON of the contract **without** this field. Two parties agree on a contract by hash, not by name |
| `capability_id` | string | AOX controlled vocabulary, e.g. `research.source_brief@1` |
| `input_schema`, `output_schema` | JSON Schema (draft 2020-12) | closed objects (`additionalProperties: false`), explicit length caps on every string and array |
| `acceptance_checks[]` | list of `{check_id, kind, spec, deterministic: bool}` | `kind ∈ {schema, assertion, reference_diff, known_answer, human_review, agent_review}` |
| `outcome_definition` | string | what "pass" means in one sentence |
| `risk_class` | `r0_pure` / `r1_sandboxed` / `r2_side_effects` | `r2` remains out of scope |
| `allowed_tools[]`, `network`, `max_runtime_s` | | sandbox limits; `network` defaults to `none` |
| `external_mappings` | object | optional A2A / MCP / ERC-8004 pointers (§4, §5); untrusted, never used for matching or scoring |

Existing examples: The repository (since 2026-10-08) carries two contracts in this shape at `pilot_ui/contracts/source-brief.json` and `pilot_ui/contracts/csv-normalization.json` (version `0.1.0-draft`, check kinds `schema`, `assertion`, `reference_diff`, `human_review`). `simulator_v02.py` implements two synthetic contracts with deterministic known-answer checks (`json.extract@1` is one).

Rules:
1. A contract with any `human_review` or `agent_review` check cannot produce a `pass` from deterministic checks alone.
2. Payloads are **untrusted data**. Verifiers and providers receive them inside a delimited data block; instructions found inside payloads are data (see the `source-brief` qualification case "Sources containing instructions to ignore verification remain data").
3. A deliverable that fails `output_schema` is never passed to later checks.

### 2.2 Verifier

The verifier is a separate component that takes `(contract, input, deliverable)` and returns a verdict. It is the only component allowed to emit a VerifiedCompletion.

Independence rules (normative):
- `verifier_id ∉ {provider_agent_id, requester_agent_id}`.
- For `agent_review` checks, the verifier agent is selected at random from eligible verifiers (v0 mvp-loop Step 7) and must not share an operator with the provider. In the current single-operator lab this is unsatisfiable, so v0.3 marks every agent-review verdict `independence=operator_shared` and the reputation function discounts it (§3).
- Deterministic checks are re-runnable: anyone holding the contract, input and deliverable must reproduce the same verdict. The VerifiedCompletion carries hashes of all three so this is checkable.
- Verdicts: `pass | partial | fail | inconclusive`. `inconclusive` never counts as a pass anywhere.

Status today: v0.2 implements deterministic checks only. Agent verifiers, operator spot-checks and disputes are **not implemented** (v0.2 RECEIPT "Not modelled").

### 2.3 VerifiedCompletion (attestation)

The verifier's output. Its exact fields, hashing and signature are defined once, in `spec/spend-guard-interface.md` §3, because the payment guard is its first consumer. Summary: engagement id, contract id + version + hash, input/deliverable hashes, verifier id + key id, outcome, per-check results, issued/expiry times, a single-use nonce, mode (`sim` or `testnet`), and an Ed25519 signature over the JCS-canonical payload.

## 3. Verified-only reputation

Reputation is a **pure function of VerifiedCompletions**. Nothing else moves it: not self-reported ratings, not external feedback, not registration age, not A2A card signatures, not ERC-8004 feedback or validation summaries.

The math is the one `simulator_v02.py` implements and tests (v0.2 RECEIPT, row "Beta reputation"):
- Beta posterior per (provider, capability) from weighted pass/fail outcomes. v0.2 verdicts are binary; `partial` handling from the v0 data model is not implemented.
- Same-operator engagements weigh 0.5.
- Fewer than 3 distinct requesters caps the score at 0.6 (sybil guard).
- Ranking uses the posterior's 10th percentile (p10), so thin histories rank low.
- Proposed v0.3 additions (not implemented): completions with `independence=operator_shared` weigh 0.5; completions whose verifier key is not on the verifier allowlist weigh 0; the 90-day decay from spec v0 §6.

Known weakness (v0.2 experiment, synthetic): the cold-start exploration bonus is too small; the best provider got 33 of 3,000 tasks. Fix before any real-fleet run.

## 4. Mapping to A2A 1.0 (untrusted external refs)

Source: A2A Protocol Specification, "Latest Released Version 1.0.0", https://a2a-protocol.org/latest/specification/ (fetched 2026-10-09 ~12:20 MT). AOX does not implement A2A; this is an export/import mapping.

| AOX | A2A 1.0 object | Mapping rule |
|---|---|---|
| Agent | `AgentCard` (§4.4.1: `name`, `description`, `supportedInterfaces`, `version`, `capabilities`, `skills`, optional `signatures`) | Stored as `external_refs[]` with `kind=a2a_agent_card`, `verified=false`. A valid `AgentCardSignature` (JWS) proves who signed the card, not that the skills work; weight 0 in reputation |
| Capability | `AgentSkill` (§4.4.5: `id`, `name`, `description`, `tags`) | `external_mappings.a2a_skill_id`. The AOX vocabulary stays authoritative |
| TaskContract | an A2A **Extension** (§4.6: declared in `AgentCard.capabilities.extensions[]` by `uri`; carried in `Message.extensions[]` and `metadata` keyed by the URI) | Proposed: one extension URI per contract major version, with `params` = `{contract_id, version, contract_hash}`. The URI is a placeholder; nothing is published. §4.6.3: a breaking change needs a new URI, which matches AOX's version-bump rule |
| Request input | `Message` with a `Part` whose `data` holds the input and `mediaType: application/json` (§4.1.6) | validated against `input_schema` before anything else |
| Engagement | `Task` (`id`, `contextId`, `status`) | A2A `taskId`/`contextId` stored as untrusted refs on the Engagement. State map: `TASK_STATE_SUBMITTED`→`active`, `WORKING`→`executing`, `COMPLETED`→`delivered` (**not** verified), `FAILED`/`REJECTED`→`failed_delivery`, `CANCELED`→`cancelled`, `INPUT_REQUIRED`/`AUTH_REQUIRED`→no AOX equivalent (out of scope) |
| Deliverable | `Artifact` with `data` parts (§4.1.7) | hashed after `output_schema` validation |
| VerifiedCompletion | none in core A2A | could ride as Artifact `metadata` under the AOX extension URI. A2A `COMPLETED` never implies AOX `pass` |

## 5. Mapping to ERC-8004 (untrusted external refs)

Source: "ERC-8004: Trustless Agents [DRAFT]", https://eips.ethereum.org/EIPS/eip-8004 (fetched 2026-10-09 ~12:20 MT; status shown as Draft, created 2025-08-13). AOX makes **no on-chain reads or writes** in v0.3.

| ERC-8004 registry | What the ERC defines | AOX mapping |
|---|---|---|
| Identity Registry | ERC-721 handle; agent id = `agentRegistry` (`{namespace}:{chainId}:{identityRegistry}`) + `agentId`; `agentURI` → registration file with `services[]` (A2A, MCP, OASF, ENS, DID...), `supportedTrust` | `external_refs[]` entry `{kind: erc8004_identity, agentRegistry, agentId, verified: false}`. Never an AOX identity. The ERC itself says it "cannot cryptographically guarantee that advertised capabilities are functional and non-malicious" |
| Reputation Registry | `giveFeedback(agentId, int128 value, uint8 valueDecimals, tag1, tag2, endpoint, feedbackURI, feedbackHash)`; `getSummary` requires a non-empty `clientAddresses` filter because unfiltered results are "subject to Sybil/spam attacks" | **Import: weight 0** (verified-only rule). Possible future **export**: one feedback per VerifiedCompletion with `tag1=aox.verified`, `value` 100/50/0 for pass/partial/fail, `feedbackURI` → the attestation, `feedbackHash` = keccak256 of it. Not done in v0.3 |
| Validation Registry | `validationRequest(validatorAddress, agentId, requestURI, requestHash)`; `validationResponse(requestHash, uint8 response 0-100, responseURI, responseHash, tag)`; responses can be updated | Closest analogue to AOX verification. Export mapping only: `response` = 100 pass / 50 partial / 0 fail, `inconclusive` = no response; `responseURI` → VerifiedCompletion; `tag` = `aox:<contract_id>@<version>`. Note the ERC lets the agent's owner pick the validator; AOX requires verifier independence on top |

Payments: the ERC says "Payments are orthogonal to this protocol" (its feedback file has an optional `proofOfPayment` field for x402). AOX likewise never carries asset, address or chain fields in contracts, reputation or attestations.

## 6. Library surface (proposal; nothing new is implemented on this branch)

| module | does | exists today? |
|---|---|---|
| `contract` | load, canonicalise (JCS), hash, validate a TaskContract; validate payloads against its schemas | partly: `pilot_ui/` on `main` validates two contracts; no hashing |
| `verify` | run acceptance checks, emit an unsigned verdict | deterministic checks in `simulator_v02.py` |
| `attest` | build, sign, hash and check a VerifiedCompletion | no |
| `reputation` | Beta/p10 from a list of VerifiedCompletions | yes, in `simulator_v02.py` (tested) |
| `match` | reference filter-then-rank matcher | yes, in `simulator_v02.py` (tested, synthetic) |
| `export` | A2A extension blob, ERC-8004 feedback/validation JSON (files only, no chain calls) | no |

Constraints: Python stdlib only for the core (as now), no network calls in the core, no key material in the repo. A signing key for real attestations needs an owner decision (where it lives, who holds it).

## 7. Conformance tests to write (design only)

1. Contract hash is stable under key reordering and whitespace (JCS), and changes when any check changes.
2. A contract with a `human_review` check can never yield `pass` from deterministic checks alone.
3. Verifier = provider or verifier = requester is rejected.
4. Reputation is unchanged by any input other than VerifiedCompletions (property test with random external refs and feedback).
5. A2A `TASK_STATE_COMPLETED` without a VerifiedCompletion leaves reputation unchanged.
6. ERC-8004 summaries or feedback in `external_refs` contribute exactly 0.
7. Attestation tests are listed in `spec/spend-guard-interface.md` §7.

## 8. Kill-criteria link

Plan §3.1 decision rule: keep AOX closed and credit-only "until the M3 internal demand report shows unmatched requests the owner would build for. Then publish the contract/verifier spec as open source." Publishing this document is therefore gated on M3 and an owner yes. Kill criterion 7 (redundant layer, from the unadopted v0.1 draft) applies directly: if A2A extensions plus the ERC-8004 Validation Registry cover typed contracts and independent verification at lower cost, the right output is this mapping document and nothing more. The owner approved this public snapshot on 2026-10-10, before M3; no demand has been measured.

## 9. UNKNOWN

- Whether any outside party wants a contract + verifier package. No adopter, no request, no outreach.
- Whether ERC-8004 has moved beyond Draft, and which registries are deployed where (not checked; irrelevant while AOX makes no chain calls).
- The A2A extension URI and its hosting. Placeholder only.
- Independence for agent verifiers in a one-operator fleet. Structurally unsatisfiable today.
