# AOX demo

One command, from the repository root:

```sh
python3 demo.py
```

The run is synthetic. Say that, and say testnet, whenever this is shown.
The payment step uses the Base Sepolia rail in **simulated** mode. The recorded
decision has `settled` false and `liveSettlementAllowed` false. No key is read
and no transaction is submitted. Two runs print the same text.

The referee is an independent code path from the fixture poster. One operator
runs both today. Separate operators are future work. The receipt is replayable
and internally consistent. It is an unkeyed SHA-256. It does not authenticate
an author.

## What the command does

1. Posts contract `text.upper@1` on the synthetic fixture ledger.
2. Runs the `aox.uppercase` referee. The referee recomputes the answer from the
   input. A junk answer fails.
3. Maps the referee pair to a three-state verdict. `(True, [])` is OK.
   `(False, reasons)` is FAILED. Missing, malformed, and timed-out evidence is
   UNKNOWN. Only OK counts as success.
4. Writes an `aox-verdict-receipt@1` receipt with a `verdict` field and replays
   it by recomputing the hash.
5. Asks the payment gate to record a simulated release for that OK receipt.
   The amount is `500000` minor units of the rail's test asset (USDC on Base
   Sepolia), under the default `1.00` cap.
6. Repeats the gate for a FAILED junk answer, missing evidence, and a timed-out
   check. Each decision is DENY with reason `verdict_not_ok`.

## Limits

- Default payment mode is `simulated`. `AOX_PAYMENT_MODE=x402_testnet` plus a
  pay-to address marks the config ready and still does not settle.
- Network ids other than `eip155:84532` are denied. Base mainnet `eip155:8453`,
  Solana mainnet, and Stellar pubnet are denied by name.
- A requested cap above `5.00` clamps to `5.00`. Amounts above the cap are denied.
  An amount of `0` or below is denied.
- A release requires a full `aox-verdict-receipt@1` object whose hash replays
  and whose verdict is OK. A bare `OK` string is denied.
- The same receipt hash is released once. A second release is a replay. The
  simulated lines use an in-memory ledger. `--live-testnet` records the hash
  in `.aox-release-ledger.json` before it asks the facilitator to settle.
- A private-key name, or any value that is 64 hex digits with or without an
  `0x` prefix, in the supplied policy env is a DENY. The process environment
  is not consulted by the policy. The value is not copied into the decision.
- The facilitator URL must be `https://x402.org/facilitator`. Any other URL is
  refused, including other `https` hosts.
- The Solana rail stays `planned_simulated_only`.

## Optional live Base Sepolia settlement

The default command stays simulated. To attempt one live settlement of the
demo's OK receipt:

```sh
npm ci
export TESTNET_PAYTO_ADDRESS=0xYourPayToAddress
export TESTNET_FACILITATOR_URL=https://x402.org/facilitator
export TESTNET_PAYER_KEY=0xYourTestnetKey
python3 demo.py --live-testnet
```

The payer key is read from the environment. It is not printed and it is not
passed on the command line. The command prints the synthetic demo first, then
one live result. Missing variables are named and their values are not printed.

The payer address needs test USDC on Base Sepolia. Open
<https://faucet.circle.com/>, choose Base Sepolia, paste the payer address,
and request test USDC. Circle's public faucet can send up to 20 USDC per
address on that network about every two hours. No Circle account is required.
The facilitator submits the transfer. This demo does not create a wallet and
does not ask for a separate gas transaction.

Mainnet network ids stay denied. A second `--live-testnet` run of the same
receipt is refused.

Attribution for the verdict enum and the payment rail is in `verdict.py` and
`payments/ATTRIBUTION.md`.

![AOX wordmark](assets/aox-wordmark.svg)
