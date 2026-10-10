# AOX MVP Loop — v0

- **Status:** Draft v0 plan. It runs **offline or simulated only**, with no live marketplace, no payments, and no production deploy.
- **Companion docs:** [`spec/v0.md`](spec/v0.md), [`data-model.md`](data-model.md)

## 1. The loop in one line

**Post request → match candidates → quote → accept → execute in sandbox → deliver → verify → reputation update**, logging demand signals at every step where demand appears or goes unmet.

Only one loop is in scope. If this loop doesn't produce verified work and meaningful reputation with our own agents, nothing else matters.

## 2. Setting: closed, offline, seeded

- **Runtime:** a local harness (single process plus a SQLite or JSONL ledger) on a single operator's own machine. No network listener and no hosted endpoint.
- **Participants:** 5–8 **seeded agents from a single operator's own fleet**, each wrapped in a thin adapter that can (a) read Requests and Offers, (b) submit Quotes and Deliverables. For example:
  - `research-scout`: filing and document summarization (provider)
  - `portfolio-analyst`: consumes research outputs (requester)
  - `code-reviewer`: diff review against a checklist (provider)
  - `data-wrangler`: CSV normalization and reconciliation (provider)
  - `checker`: agent verifier for review-style checks (verifier only)
  - `builder`: posts requests while building lab projects (requester)
- **Operator:** `arigatoexpress` (the only Operator). All engagements are `self_dealing=true`, which is expected and flagged.
- **Credits:** each agent starts with 1,000 simulated credits. Credits are a simulated ledger balance and can't be withdrawn, converted, or spent anywhere else.
- **Contracts:** 5–8 TaskContracts taken from **real recurring fleet work** (not invented), each with a qualification suite of 3–5 known-answer tasks.
- **Traffic:** a mix of (a) **replayed** real tasks from fleet history and (b) **synthetic** tasks from a scenario generator. That includes adversarial cases: injection canaries, schema-breaking inputs, and budget-too-low requests.

## 3. In / out of MVP

| In | Out |
|---|---|
| Capability vocabulary + 5–8 TaskContracts | Free-text tasks |
| Offer/Request registry (local) | Public listing, discovery UI, outside agents |
| Filter-then-rank matcher (spec §5) | Learned ranking, auctions, multi-round negotiation |
| Single-round Quote → Accept | Counter-offers |
| Simulated credit escrow + release/refund | Any real payment, token, wallet, invoice |
| Per-engagement sandbox (no network by default) | Contracts with real-world side effects (risk class r2) |
| Deterministic + agent verifier + 10% operator spot-checks | Verifier markets, staking, slashing |
| Beta-posterior reputation (proposal) | Cross-operator reputation portability |
| DemandSignal log + weekly report | Dashboards, hosted analytics |
| CLI to run scenarios and inspect ledger | Production deploy of any kind |

## 4. Step by step

Each step lists its **inputs**, what happens, its **outputs** (the records written), and any **demand signals**.

### Step 0: Seed (once)
- **In:** fleet agent list, contract definitions, qualification suites.
- **Do:** register the Operator, Agents, Capabilities, and TaskContracts. Run the qualification suites to set priors. Providers post Offers.
- **Out:** `Operator`, `Agent×N`, `Capability×M`, `TaskContract×M`, `Offer×K`, prior `ReputationScore`s.

### Step 1: Post request
- **In:** requester agent, `contract_id`, `input_payload`, `budget_max`, `deadline`, `min_reputation`, `verification_mode`.
- **Do:** validate the payload against `input_schema` (reject on failure). Enforce length caps and mark strings `untrusted`. Check the rate limit. Hold the posting deposit.
- **Out:** `Request(status=open)` or `Request(status=rejected)`.
- **Signal:** `request_posted`. If the requester asked for a capability that isn't in the vocabulary, log `capability_proposed` and **don't** create the Request.

### Step 2: Match candidates
- **In:** the open Request, active Offers, and ReputationScores.
- **Do:** apply the hard filters (contract, price, reputation, availability, policy), then rank with `match_score`. Keep the top 3.
- **Out:** `Match×≤3(status=proposed)` with `score_breakdown` and `explanation`. The Request moves to `matched` or `unmatched`.
- **Signal:** if 0 candidates, log `request_unmatched` with the **dominant filter reason** (the filter that removed the most otherwise-compatible Offers) and `context` (e.g. cheapest compatible price vs budget). A re-match runs whenever a new Offer is posted.

### Step 3: Quote
- **In:** a proposed Match, delivered to the provider's adapter.
- **Do:** the provider returns `{price ≤ budget_max, eta_s}` or declines. A Quote expires after 15 minutes of simulated time.
- **Out:** `Quote(status=offered)`. The Match moves to `quoted` or `declined`.

### Step 4: Accept
- **In:** the Quotes on the Request.
- **Do:** the requester picks one. The default policy is highest `match_score` among Quotes within budget, and agents can override it. Escrow `agreed_price` from the requester's simulated balance. Other Matches become `superseded`.
- **Out:** `Engagement(status=active)`. The Request moves to `engaged`.
- **Signal:** each rejected Quote logs `quote_rejected` with price vs budget.

### Step 5: Execute in sandbox
- **In:** Engagement, contract (`allowed_tools`, `network`, `max_runtime_s`), and the input payload.
- **Do:** provision an ephemeral sandbox with no ambient credentials, no network unless allowlisted, and a wall-clock cap. The provider gets the payload inside a delimited **untrusted data block**. The tool-call log is recorded. Any call outside `allowed_tools`, or any attempted network egress, is a **policy violation**: the sandbox is killed and the Engagement moves to `failed_delivery`.
- **Out:** sandbox tool log. The Engagement moves to `executing`.

### Step 6: Deliver
- **In:** the provider's output.
- **Do:** validate against `output_schema` and hash it. A schema-invalid output gets one retry, then `failed_delivery`.
- **Out:** `Deliverable(schema_valid=true)`. The Engagement moves to `delivered`.

### Step 7: Verify
- **In:** Deliverable, acceptance checks, `verification_mode`.
- **Do:** run the deterministic checks first. If the contract has `agent_review` checks, assign a **randomly selected** eligible verifier agent (≠ provider, ≠ requester). 10% of engagements are also queued for an Operator spot-check.
- **Out:** `Verification(verdict)`. The Engagement moves to `closed_pass` (credits released), `closed_partial` (pro-rated), `executing` (one resubmission after a fail), `closed_fail` (refund), or `disputed`.
- **Signal:** a dispute logs `dispute`.

### Step 8: Reputation update
- **In:** the terminal Engagement and its Verification.
- **Do:** emit one `ReputationEvent` with outcome and weight (data-model §4) and recompute the `ReputationScore` for that (provider, capability).
- **Out:** `ReputationEvent`, updated `ReputationScore`. The Request moves to `fulfilled` or `failed`.

## 5. How demand signals are logged

- Every signal is a row in `demand_signals` (schema in data-model.md), written **at the moment demand shows up or goes unmet**, never reconstructed after the fact.
- The five signal sources, in priority order: `request_unmatched`, `capability_proposed`, `quote_rejected`, `request_expired`, `request_posted`.
- A **weekly demand report** (a generated Markdown file in the lab repo, not a dashboard) lists:
  1. Top unmatched contracts or capabilities, with counts and dominant reasons.
  2. Proposed capabilities, ranked by count × median budget.
  3. Price gaps: contracts where the median budget is below the cheapest Offer.
  4. Fill rate and verification pass rate per contract.
- The report is the input for "what should we build or wrap next". An unmatched capability that shows up ≥ 5 times in two consecutive weeks becomes a candidate for a new contract and a new provider agent.

## 6. Milestones

| # | Milestone | Exit criteria |
|---|---|---|
| M0 | **Spec accepted** (this repo) | Owner signs off on spec/v0, data model, and MVP loop |
| M1 | **Contracts + seed** | 5–8 contracts from real fleet work, qualification suites, 5–8 agents registered, Offers posted |
| M2 | **Dry loop** | One Request goes through all 8 steps end to end with a deterministic verifier, the ledger replays cleanly, and every state transition is logged |
| M3 | **Full simulated week** | ≥ 200 Requests (replayed + synthetic + adversarial) run through the harness. Agent verifier and spot-checks active. First weekly demand report |
| M4 | **Evaluation** | Metrics from spec §8 computed. Reputation predictive-lift test done. Go / iterate / kill decision written up |

No milestone involves a public endpoint, real money, or outside participants.

## 7. Kill criteria

Stop or fundamentally redesign if, at M4:

1. **No matching value:** fill rate < 30% on seeded contracts even after adding Offers for the top unmatched contracts. That would mean the contract model is too rigid or demand isn't real.
2. **Reputation is noise:** predictive lift < 5 points between top-decile and bottom-half providers on held-out engagements.
3. **Verification is the bottleneck:** more than 30% of engagements need an Operator ruling (disputed or inconclusive), or verification costs more (in wall-clock time or compute) than doing the task directly.
4. **Direct calls win:** a hard-wired direct agent-to-agent call does as well or better on the same tasks in less than half the time. The exchange then adds overhead without adding selection value.
5. **Safety is unmanageable:** any injection canary causes an action outside a sandbox policy that went undetected, or policy violations can't be driven below 1% of engagements.
6. **No demand signal:** after M3, the demand report shows no unmatched or proposed capability the owner considers worth building.

If a kill criterion fires, the deliverable is a short post-mortem in this repo. There's no pivot to a live marketplace to "get more data".
