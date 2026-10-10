# Synthetic offline fixture loop

This is preparatory implementation, **not an agent pilot**. There are zero real agents,
no measured demand and no completion claim for M0, M1, M2, M3 or M4 in `mvp-loop.md`.
The design documents remain proposals. The simulator implements only the subset below.

Python 3.11+ and its standard library are sufficient; nothing is installed or contacted:

```sh
python3 -m unittest discover -s tests -v
python3 simulator.py
```

The CLI prints a synthetic receipt, final state and replayable JSON event ledger to stdout.
The receipt compares the exact same uppercase fixture through one direct call and one
exchange execution: equal output, one fixture call each, seven exchange events. This is
an operation-count comparison, not a measured model latency/cost benchmark or evidence
that matching adds value.

## Implemented subset

- One closed contract, `text.upper@1`: exactly one input `text` string, at most 4,096 characters.
  Output may expand under Unicode uppercase conversion; its bound is the computed known-answer
  length for that input, and verification requires exact equality to that answer.
- Explicit fixture balances and offers; nonnegative integer accounting units only.
- Request validation, deterministic lowest-price matching (provider ID breaks ties), quote,
  expiry and acceptance, simulated escrow, injected trusted fixture execution, output checking,
  release on known-answer pass or refund on failure, one boolean outcome per settlement.
- No-match state and explanation; unknown contracts/schema fields rejected.
- Monotonic explicit simulated time. Quotes expire after 900 simulated seconds or at the
  request deadline, whichever comes first. These are proposed experimental parameters.
- Atomic event application, hash chain and deterministic replay with transition validation.

Balances 100/0, price 10 and budget 20 are invented **test inputs**, never real prices or
scarcity evidence. The outcome list is accounting for fixture verification, not the proposed
Beta reputation model. Match and quote are recorded together; verification and settlement
are recorded together. Duplicate acceptance/settlement fails without changing state.

## Important implementation limits

`execute(request, fixture, now=...)` accepts only caller-supplied **trusted pure Python fixtures**.
It copies the payload; strings are never evaluated or interpreted as commands. It is not a
security sandbox and cannot constrain arbitrary Python, model tools, filesystem access or
network access inside a callable. The built-in CLI uses only the fixed uppercase function.
Do not connect agent adapters or untrusted execution until separate isolation is implemented
and verified. Tests use injected fixtures, never hostile processes or live providers.

Fixture exceptions record a generic failure event and refund escrow, without recording
exception text. Delivery and settlement both require explicit simulated time before the
request deadline. At or after the deadline, an explicit `expire` event closes unfinished
requests and refunds escrow exactly once, including when output arrived but was not settled.
There is no automatic timeout worker: the caller advances the clock and records expiry.
Expiry/fixture exceptions do not infer a provider quality verdict. Expired quotes cannot be
accepted and move no funds. A failed delivered output refunds immediately, without the
design's resubmission/partial/dispute paths or posting deposits.

Hash chaining detects edits against existing hashes and replay rejects invalid transitions.
It does **not** authenticate an author, prevent a malicious full valid rewrite, or detect a
truncated valid prefix without an externally retained final hash/count. Everything is in
memory unless the caller saves the printed output. Public `state` and `events` reads return
detached snapshots so consumer edits cannot rewrite the live ledger. Private Python attributes
remain accessible to trusted in-process code; this is not an authorization boundary. Events
require strict JSON values and string object keys, with a nesting limit of 32. No claim of
durable multi-process ledger security is made.

Not implemented: real recurring contracts or agent identities, fleet adapters, OS isolation,
network allowlists, capacity, deposits, schema-version negotiation, scoring, human/agent
verification, real demand reports, or payments. Full pilot acceptance remains in the design
documents and requires actual authorized evidence. Direct execution may remain the better
choice; this fixture offers no proof otherwise.

## Verification

Tests cover release/refund and credit conservation at each ledger prefix, replay equality,
hash tampering and semantic tampering, reordered/duplicate events, duplicate settlement,
quote/request expiry, insufficient balance, deterministic matching, self-match rejection,
unknown/invalid schemas, fixture failure/refund, deadline expiry/refund and instruction strings handled only as data.
Hosted CI runs tests and the synthetic demo with read-only repository permissions.

The reliability suite additionally checks 256 deterministic synthetic traces across eight
pass/failure/expiry modes against an independent accounting oracle, plus interleaved requests
sharing a balance. It covers public snapshot mutation, strict JSON boundaries and malformed
replay input. This is a software regression corpus, not the full simulated week milestone:
it has no fleet tasks, adapters, model verification, operator spot checks or demand evidence.
