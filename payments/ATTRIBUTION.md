# Payment-rail attribution

The Base Sepolia gate in this directory is a port of the public archived
repository `arigatoexpress/agent-opportunity-exchange` at commit
`8ef5daf676eea2934b4aa22657e94f6ab9429cd1` (2026-10-10 read).

| Source | Blob | What was kept |
|---|---|---|
| `src/x402-config.ts` | `afbf62a9438f497b777a7f797c6e620064cbe369` | Simulated default, Base Sepolia `eip155:84532` only, mainnet id block, facilitator check, pay-to check |
| `src/x402-testnet.ts` | `e3f8e38c3f0f339967ec4eae51e8e273185c3b2c` | Gate stays inactive until testnet config is ready. `liveSettlementAllowed` stays false on the policy object |
| `scripts/x402-testnet-fetch.ts` | `c024c0b4f4a02864916c19c01432c0a29edd9087` | Client spend cap: default 1.00, hard ceiling 5.00, integer minor units |

No LICENSE file was in that repository on 2026-10-10. The port names the
source, the commit, and the blobs. `AOX_` env names are accepted beside the
original `AOE_` names.

The author relicenses the vendored Verdict enum and the ported x402 rail under the Apache License 2.0.

The policy modules (`x402_testnet.py`, `payments/x402-config.mjs`, `payments/x402-testnet.mjs`) do not import an SDK and do not settle. `payments/x402-live.mjs` is an opt-in Base Sepolia path. It imports `@x402/hono`, `@x402/core`, `@x402/evm`, and `@x402/fetch`, registers only `eip155:84532`, and runs when `python3 demo.py --live-testnet` is passed. The artifact catalog and the original buyer script were not copied. The Solana rail remains `planned_simulated_only`.
