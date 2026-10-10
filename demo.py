"""One-command synthetic demo for the lab referee and the simulated payment gate.

Run ``python3 demo.py``. Tasks are synthetic. The payment step records a
simulated Base Sepolia decision. It reads no key and submits nothing.
``python3 demo.py --live-testnet`` attempts one Base Sepolia settlement when
``TESTNET_PAYER_KEY``, ``TESTNET_PAYTO_ADDRESS``, and
``TESTNET_FACILITATOR_URL`` are set. The key is not printed and is not placed
on the command line.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import task_contracts
import x402_testnet
from simulator import CONTRACT, Simulator
from verdict import Verdict, build_receipt, replay_receipt, verdict_for

ROOT = Path(__file__).resolve().parent
TASK = "aox.uppercase"
TEXT = "synthetic"
REQUIRED_LIVE = ("TESTNET_PAYER_KEY", "TESTNET_PAYTO_ADDRESS", "TESTNET_FACILITATOR_URL")


def uppercase_output(text, passed=True):
    return {
        "kind": "exchange",
        "passed": passed,
        "output": {"text": text},
        "real_agents": 0,
        "sent": False,
        "spent": False,
    }


def post_fixture():
    sim = Simulator()
    sim.record("seed", balances={"fixture-requester": 100, "fixture-provider": 0})
    sim.record("offer", provider="fixture-provider", price=10, contract=CONTRACT)
    sim.record(
        "post",
        request="demo-1",
        requester="fixture-requester",
        contract=CONTRACT,
        payload={"text": TEXT},
        budget=20,
        deadline=100,
    )
    return sim.state["requests"]["demo-1"]["contract"]


def referee(output):
    return task_contracts.check(TASK, {"text": TEXT}, output)


def payment_line(label, evidence, ledger):
    receipt = build_receipt(TASK, evidence, CONTRACT)
    replay_receipt(receipt)
    decision = x402_testnet.decide_release({
        "verdict": receipt,
        "amount": "500000",
        "network": x402_testnet.BASE_SEPOLIA_NETWORK,
        "mode": "simulated",
        "maxUsd": "1.00",
    }, ledger=ledger)
    return (
        f"{label}: verdict {receipt['verdict']} decision {decision['decision']} "
        f"reason {decision['reason']} settled {decision['settled']}"
    )


def demo_lines():
    ledger = x402_testnet.ReleaseLedger()
    posted = post_fixture()
    good = referee(uppercase_output(TEXT.upper()))
    junk = referee(uppercase_output("nope"))
    ok_receipt = build_receipt(TASK, good, posted)
    replayed = replay_receipt(ok_receipt)
    ok = verdict_for(good)
    decision = x402_testnet.decide_release({
        "verdict": replayed,
        "amount": "500000",
        "network": x402_testnet.BASE_SEPOLIA_NETWORK,
        "mode": "simulated",
        "maxUsd": "1.00",
    }, ledger=ledger)
    status = x402_testnet.payment_status({})
    return [
        "AOX synthetic demo",
        "Tasks are synthetic. Payment mode is simulated on the Base Sepolia rail.",
        "The gate records a decision. It submits nothing and reads no key.",
        f"1. Posted contract {posted} for referee task {TASK}.",
        f"2. Referee on the uppercased output returned ok={good[0]}. Junk output returned ok={junk[0]}.",
        f"3. Verdict {ok.value}. is_success={ok.is_success}. Only {Verdict.OK.value} counts as success.",
        f"4. Receipt {replayed['format']} field verdict={replayed['verdict']} replayed hash={replayed['hash']}.",
        (
            "5. Simulated release on the OK receipt: "
            f"decision {decision['decision']} settled {decision['settled']} "
            f"liveSettlementAllowed {json.dumps(decision['liveSettlementAllowed'])} "
            f"mode {status['mode']} network {status['network']['id']}."
        ),
        "6. " + payment_line("FAILED junk", junk, ledger),
        "   " + payment_line("UNKNOWN missing", None, ledger),
        "   " + payment_line("UNKNOWN timed out", {"timed_out": True}, ledger),
    ]


def redact(text, secret):
    raw = "" if secret is None else str(secret).strip()
    if not raw:
        return str(text)
    prefixed = raw if raw[:2].lower() == "0x" else "0x" + raw
    bare = prefixed[2:]
    redacted = str(text).replace(prefixed, "[redacted]")
    if bare:
        redacted = redacted.replace(bare, "[redacted]")
    return redacted


def current_ok_receipt():
    posted = post_fixture()
    good = referee(uppercase_output(TEXT.upper()))
    return build_receipt(TASK, good, posted)


def live_release(env, settler=None, ledger=None):
    """Policy check for one live release. The payer key stays out of the policy env."""
    missing = [name for name in REQUIRED_LIVE if not str(env.get(name, "")).strip()]
    if missing:
        return {"decision": "DENY", "reason": "missing_live_env", "missing": missing, "settled": False}
    key = str(env["TESTNET_PAYER_KEY"])
    receipt = current_ok_receipt()
    policy_env = {
        "AOX_PAYMENT_MODE": "x402_testnet",
        "AOX_X402_NETWORK": x402_testnet.BASE_SEPOLIA_NETWORK,
        "AOX_X402_PAY_TO": str(env["TESTNET_PAYTO_ADDRESS"]).strip(),
        "AOX_X402_FACILITATOR_URL": str(env["TESTNET_FACILITATOR_URL"]).strip(),
    }
    def node_settler(payload):
        return _node_settle(payload, key, env, receipt)

    chosen = node_settler if settler is None else settler
    if ledger is None:
        ledger = x402_testnet.ReleaseLedger(str(ROOT / ".aox-release-ledger.json"))
    return x402_testnet.decide_release({
        "verdict": receipt,
        "amount": "500000",
        "network": x402_testnet.BASE_SEPOLIA_NETWORK,
        "mode": "x402_testnet",
        "maxUsd": "1.00",
        "env": policy_env,
    }, settler=chosen, ledger=ledger)


def _node_settle(payload, key, env, receipt):
    if payload.get("receiptHash") != receipt["hash"] or payload.get("taskId") != receipt["task_id"]:
        return False
    body = {
        "receipt": receipt,
        "amount": payload["amount"],
        "payTo": str(env["TESTNET_PAYTO_ADDRESS"]).strip(),
        "facilitatorUrl": str(env["TESTNET_FACILITATOR_URL"]).strip(),
        "maxUsd": "1.00",
        "ledgerConsumed": True,
    }
    child_env = {name: value for name, value in env.items() if type(value) is str}
    child_env["TESTNET_PAYER_KEY"] = key
    proc = subprocess.run(
        ["node", str(ROOT / "payments" / "x402-live.mjs")],
        input=json.dumps(body),
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        env=child_env,
        check=False,
    )
    stdout = redact(proc.stdout, key)
    stderr = redact(proc.stderr, key)
    if stderr.strip():
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        print(stdout, file=sys.stderr)
        return False
    if not result.get("ok"):
        print(redact(str(result.get("message") or result.get("reason") or ""), key), file=sys.stderr)
        return False
    return True


def run_live_testnet(env=None, settler=None, ledger=None):
    source = os.environ if env is None else env
    missing = [name for name in REQUIRED_LIVE if not str(source.get(name, "")).strip()]
    if missing:
        print("live testnet needs " + ", ".join(missing), file=sys.stderr)
        return 2
    decision = live_release(source, settler=settler, ledger=ledger)
    print(redact(
        f"live: decision {decision['decision']} reason {decision['reason']} settled {decision['settled']}",
        source.get("TESTNET_PAYER_KEY", ""),
    ))
    if decision["decision"] == "RELEASE" and decision["settled"]:
        return 0
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="demo.py")
    parser.add_argument("--live-testnet", action="store_true")
    args = parser.parse_args(argv)
    print("\n".join(demo_lines()))
    if not args.live_testnet:
        return 0
    return run_live_testnet()


if __name__ == "__main__":
    sys.exit(main())
