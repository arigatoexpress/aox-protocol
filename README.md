# AOX: Agent Opportunity Exchange

**Payment follows proof, not claims.** AOX is an open, offline lab prototype of a protocol for
work handed from one AI agent to another. Every task is posted under a typed contract. An
independent checker decides whether the delivered output passed. Reputation moves only on
verified outcomes, and every step lands in a replayable receipt.

> **Status: lab prototype.** Everything here runs offline on synthetic tasks with simulated
> credits. There are zero real agents, no users, no measured demand and no live marketplace.
> Credits are integer accounting units that never convert into money or any other asset.
> The spend-guard interface is a testnet-only design document. The default demo and the
> fixture harness move no funds. `python3 demo.py --live-testnet` can settle one Base
> Sepolia payment when that flag and its configuration are both present.

## Why

AI agents are starting to hand work to other agents. Today the usual check is the provider
saying "done." AOX explores the opposite default: a task is only complete when a checker that
shares no code with the provider says the output passed, and only those verified outcomes are
allowed to build reputation or, in a later testnet experiment, release payment. Unverifiable
results are reported as UNKNOWN, never as success.

## What AOX is

| Piece | What it does | Where |
|---|---|---|
| **Typed task contracts** | Each task type is a versioned contract (`text.upper@1`, `json.extract@1`, …) with a closed input/output schema and acceptance checks. Unknown contracts and unknown fields are rejected. | [`spec/protocol.md`](spec/protocol.md) §2.1, [`simulator.py`](simulator.py), [`simulator_v02.py`](simulator_v02.py) |
| **Independent verifier** | A referee recomputes what a correct answer must look like from the task input alone. It never imports the provider's code, never raises, and fails closed on malformed or hostile output. | [`task_contracts.py`](task_contracts.py), [`TASK_CONTRACTS.md`](TASK_CONTRACTS.md), [`spec/protocol.md`](spec/protocol.md) §2.2 |
| **Verified-only reputation** | Reputation is a pure function of verified completions: a Beta(α, β) score per agent × capability, ranked on its 10th-percentile lower bound, discounted for same-operator work and capped until an agent has several distinct requesters. Self-reported or imported ratings count for nothing. | [`spec/protocol.md`](spec/protocol.md) §3, [`data-model.md`](data-model.md) |
| **Simulated credits** | Escrow, release on pass, refund on failure, all in nonnegative integer units. An independent accounting oracle re-derives every balance from the ledger. | [`simulator_v02.py`](simulator_v02.py), [`accounting_oracle.py`](accounting_oracle.py) |
| **Replayable receipts** | Every event is appended to a SHA-256 hash chain that can be replayed and checked. Edit a balance and replay fails. | [`OFFLINE.md`](OFFLINE.md) |
| **Spend-guard interface (testnet only, design)** | Defines a signed `VerifiedCompletion` record that an external agent spend guard could require before releasing a *testnet* payment. Mainnet, unknown networks and missing modes are denied by design. | [`spec/spend-guard-interface.md`](spec/spend-guard-interface.md) |

AOX ids stay authoritative. Identifiers from outside standards (A2A Agent Cards, ERC-8004
registries) are mapped as **untrusted external references** and never feed matching or scoring.

## Quickstart

Needs Python 3.11+ (standard library only). Node.js 20+ is needed only for the CSV tests.
Nothing is installed and nothing touches the network.

```sh
git clone https://github.com/arigatoexpress/aox-protocol.git
cd aox-protocol

# Unit tests: simulator, v0.2 simulator, reliability, task contracts, outcome loop
python3 -m unittest discover -s tests -v

# v0.1 offline fixture loop: one task, seven events, replayable JSON ledger on stdout
python3 simulator.py

# v0.2 simulator: agent profiles, scored and explained matches, Beta reputation
python3 simulator_v02.py

# Gated outcome loop: drafts and blocks; never sends, spends, deploys or merges
python3 outcome_loop.py

# Synthetic matcher experiment (about 3-4 minutes): reputation-aware vs lowest-price
python3 experiments/2026-10-07-matcher/run.py > /tmp/aox-matcher.json

# Local pilot UI and receipt inspector (loopback only, memory-only history)
python3 -m pilot_ui.app

# Pilot UI tests and CSV verifier tests
python3 -m unittest discover -s pilot_ui/tests -v
node --test pilot_ui/tests/csv/*.test.mjs
```

The same checks run in CI on every push and pull request
([`.github/workflows/test.yml`](.github/workflows/test.yml)), including a byte-for-byte
determinism check that runs `simulator.py` twice and compares the output.

## Demo

![AOX wordmark](assets/aox-wordmark.svg)

```sh
python3 demo.py
```

The demo is synthetic and deterministic. It posts `text.upper@1`, runs the independent
referee, writes an `aox-verdict-receipt@1` receipt, and records a simulated Base Sepolia
decision. That decision has `settled` false. The steps are in [`DEMO.md`](DEMO.md).

An optional live settlement on Base Sepolia (`eip155:84532`) stays off unless you pass
`--live-testnet` and set `TESTNET_PAYER_KEY`, `TESTNET_PAYTO_ADDRESS`, and
`TESTNET_FACILITATOR_URL`. The facilitator URL has to be the allow-listed testnet
facilitator `https://x402.org/facilitator`. That path needs `npm ci` and the network.
The default command does not. Mainnet network ids stay denied, and the spend cap stays
in force. A receipt is released once.

## Honest limitations

- **Synthetic only.** All tasks, providers, prices and balances are invented test inputs.
  Results say nothing about real agents or real demand.
- **The matcher experiment favors reputation by construction.** In 6,000 synthetic tasks the
  reputation-aware matcher passed 78% vs 45% for lowest-price, but the cheapest invented
  provider was also the worst one. A market where price tracks quality could shrink or reverse
  the gap. See [`experiments/2026-10-07-matcher/RESULTS.md`](experiments/2026-10-07-matcher/RESULTS.md).
- **One operator.** The verifier's *code* is independent of the provider's code, but a single
  operator runs everything. Independent verifier operators are future work.
- **Receipts are replayable, not tamper-proof.** The ledger is an unkeyed SHA-256 chain: it
  catches edits that are not followed by a full rewrite, but someone who rewrites the whole
  chain can still pass replay. Signing is designed but not implemented.
- **Not an OS sandbox.** The fixture harness treats task payloads as data and never executes
  them, but it is not a security boundary.
- **Not modelled yet:** time decay, late delivery, agent verifiers, spot checks, disputes,
  capacity, adaptive providers.
- **Design docs are proposals.** Weights, thresholds and field names in the spec are open to
  change.

## Documents

| Doc | What it covers |
|---|---|
| [`spec/protocol.md`](spec/protocol.md) | v0.3 protocol: task contracts, verifier, verified completions, verified-only reputation, A2A and ERC-8004 mappings, conformance tests |
| [`spec/spend-guard-interface.md`](spec/spend-guard-interface.md) | Testnet-only `VerifiedCompletion` interface for an external spend guard: fields, hashing, guard checks, deny cases |
| [`spec/v0.md`](spec/v0.md) | Original v0 design: problem, actors, matching, trust and safety, non-goals, metrics |
| [`data-model.md`](data-model.md) | Entities, fields, state machines, example records, reputation formula |
| [`mvp-loop.md`](mvp-loop.md) | The end-to-end offline loop, milestones and kill criteria |
| [`OFFLINE.md`](OFFLINE.md) | What the v0.1 fixture simulator implements and its limits |
| [`TASK_CONTRACTS.md`](TASK_CONTRACTS.md) | The independent referee and the junk outputs it must reject |
| [`OUTCOMES.md`](OUTCOMES.md) | The gated outcome loop |
| [`DEMO.md`](DEMO.md) | One-command synthetic demo and the optional Base Sepolia flag |

## Out of scope

- No live marketplace or public listing. Nothing here accepts outside agents or people.
- No payment processing on the default path. `python3 demo.py` records a simulated decision. `python3 demo.py --live-testnet` can submit one Base Sepolia settlement when its configuration is set. Mainnet stays denied.
- No production deployment or hosted endpoint.
- No autonomous outreach. Agents in the loop never message people or outside agents.

## License

Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
