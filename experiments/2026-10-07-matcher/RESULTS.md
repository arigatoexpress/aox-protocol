# Synthetic matcher experiment: reputation-aware vs lowest-price (AOX v0.2)

**Run:** 2026-10-07, about 09:53 to 09:56 MT, on the shared box (Python 3.13.5, stdlib only).
**Branch:** `aox/v0.2-sim`. Code: `simulator_v02.py`, `accounting_oracle.py`, `experiments/2026-10-07-matcher/run.py`.

> **Read this first.** This experiment tests **software invariants** (conservation, replay,
> determinism, oracle agreement) and a **toy hypothesis** on **invented providers whose hidden
> quality levels were chosen by us**. It is **not evidence of demand**, of real agent quality, or
> of how a real exchange would behave. No real agents, no network, no payments, no spend.
> The provider set was fixed before the run and not tuned afterwards. It also **favors the
> reputation matcher by construction**: the cheapest provider is the worst one. A market where
> price tracks quality would shrink or reverse the gap.

## Hypothesis (toy)

When the cheapest provider is unreliable, the spec v0 section 5 matcher (0.45 rep_norm + 0.25
price_fit + 0.20 latency_fit + 0.10 exploration, rep_norm = Beta p10 lower bound) gets a higher
synthetic pass rate than a lowest-price matcher, and spends more credits doing it.

## Commands

```bash
python3 experiments/2026-10-07-matcher/run.py > run1.json        # PYTHONHASHSEED=1
python3 experiments/2026-10-07-matcher/run.py > run2.json        # PYTHONHASHSEED=999
cmp run1.json run2.json                                          # identical
python3 experiments/2026-10-07-matcher/run.py --check-determinism  # in-process variant (not run in full for this report)
```

Each full run took 3 min 22 s wall time. The full output is committed as `results.json`
(sha256 `dbd9aaf47cdb59193367746c8dab40158002b97310395987f424ec7b05a10b51`, internal
result digest `725c4a6d345ed6839a56154e865cc06279eced76c71e43fd6610554c5da7d83f`).

## Setup

- **Seeds:** 1 to 25. Each seed is one independent market run of **120 requests**, run once per
  matcher: 25 x 120 = **3,000 traces per matcher, 6,000 in total**, 31,321 ledger events.
- **Common random numbers:** both matchers see the same request stream per seed
  (`random.Random(seed)`), and a provider's pass, fail or exception on a given task is a SHA-256
  function of (seed, provider, task id). Differences come only from routing.
- **Requesters (4 agents, 3 operators):** `req-a1`, `req-a2` (op-a), `req-b` (op-b), `req-c` (op-c),
  with 2,000 synthetic credits each.
- **Contracts:** `text.upper@1` and `json.extract@1` (a deterministic known-answer path lookup into a
  random nested JSON document), each about 50% of requests. Budgets are uniform integers 6 to 12.
- **Providers (hidden quality q, never visible to the simulator):**

| provider | operator | text.upper@1 price / latency / q | json.extract@1 price / latency / q |
|---|---|---|---|
| prov-bargain | op-p1 | 2 / 60 / 0.50 | 3 / 60 / 0.40 |
| prov-steady | op-p2 | 5 / 120 / 0.90 | 6 / 120 / 0.92 |
| prov-premium | op-p3 | 8 / 60 / 0.97 | 9 / 60 / 0.98 |
| prov-overpriced | op-p1 | 7 / 240 / 0.60 | n/a |
| prov-house | op-a (same as req-a1/a2) | 4 / 90 / 0.85 | n/a |
| prov-json-new | op-p4 | n/a | 5 / 90 / 0.80 |

- Every provider runs the 5-task qualification suite per contract at t=0 (spec section 5.1). Passing
  all 5 sets the prior to Beta(2,1), otherwise Beta(1,1). There is a 2% chance per task that a
  synthetic exception fires, which refunds and leaves reputation unchanged.
- Failed verification refunds the requester, so "credits released" counts only passes.

## Results (exact)

| metric (3,000 traces each) | reputation-aware | lowest-price |
|---|---|---|
| passed | **2,349** | **1,335** |
| synthetic pass rate (of posted = of accepted) | **0.783** | **0.445** |
| failed verification | 592 | 1,595 |
| provider exceptions (refunded) | 59 | 70 |
| unmatched | 0 | 0 |
| credits released to providers (net spend) | **11,210** | **3,275** |
| credits escrowed gross (incl. later refunds) | 13,641 | 7,512 |
| credits per passed task | **4.772** | **2.453** |
| provider share of accepted tasks | steady 953, house 863, json-new 673, bargain 478, premium 33 | bargain 3,000 |

**Paired per-run differences (reputation minus lowest-price, n = 25 runs, normal-approx 95% CI):**

| metric | mean diff per run | sd | 95% CI | runs where reputation is higher |
|---|---|---|---|---|
| passed (of 120) | +40.56 | 12.78 | [35.55, 45.57] | 25 / 25 |
| pass rate | +0.338 | 0.107 | [0.296, 0.380] | 25 / 25 |
| credits released | +317.4 | 88.79 | [282.6, 352.2] | 25 / 25 |

## Invariants (all PASS, all 50 runs)

- **Independent accounting oracle** (`accounting_oracle.py`, no simulator imports, its own
  known-answer checks and SHA-256 recomputation) re-derived balances from each ledger and matched
  the simulator's balances exactly. Pass and fail counts agreed.
- **Conservation:** sum(balances) + sum(escrow) equals the seeded total after **every** event in every run.
- **Escrow** is empty at the end of every run, and no balance ever went negative.
- **Replay:** re-applying each ledger reproduced the identical state, with all hashes matching.
- **Determinism:** two processes with different `PYTHONHASHSEED` produced byte-identical output.

## What this does and does not show

- In this toy market, the spec's ranking avoided the worst provider and roughly doubled the synthetic
  pass rate (0.445 to 0.783). It paid about 1.95x more per passed task and released 3.4x more credits.
  With refund-on-fail, lowest-price is *cheaper per pass*. What it loses is completed work.
- **Weak exploration (finding about the spec):** the best provider, prov-premium (q 0.97/0.98),
  got only 33 of 3,000 tasks. A 0.10 exploration bonus can't overcome its price_fit penalty, so the
  first adequate provider tends to lock in. The qualification-suite draw at t=0 strongly shapes
  routing (for example, seed 1 never routed text tasks to prov-bargain because it failed
  qualification). Per-seed pass counts ranged widely: 72 to 112 of 120 for reputation-aware vs 43 to 65 for lowest-price.
- The same-operator 0.5 discount applied to prov-house's evidence from op-a requesters (req-a1, req-a2).
  It still won 863 tasks. Its evidence from req-b and req-c counts at full weight, so the discount
  slows its score growth but doesn't block it.
- **Not modelled:** time decay (90-day half-life), late-delivery weight, agent verifiers, spot checks,
  disputes, price negotiation, capacity limits, strategic or adaptive providers, real latency. No
  oracle-optimal routing baseline was computed.
- **Not demand.** Nothing here says any real agent or person wants this exchange.
