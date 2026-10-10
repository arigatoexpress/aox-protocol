"""Simulated Base Sepolia gate: OK only, mainnet blocked, spend capped."""

import json
import os
import tempfile
import unittest
from pathlib import Path

import x402_testnet
from verdict import Verdict, build_receipt

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "payments" / "vectors.json").read_text())
PAY_TO = "0x1111111111111111111111111111111111111111"


def view(status):
    rails = {rail["railId"]: rail for rail in status["rails"]}
    return {
        "mode": status["mode"],
        "activeRail": status["activeRail"],
        "ready": status["ready"],
        "liveSettlementAllowed": status["liveSettlementAllowed"],
        "serverPrivateKeyRequired": status["serverPrivateKeyRequired"],
        "networkId": status["network"]["id"],
        "networkMainnet": status["network"]["mainnet"],
        "payToRedacted": status["payTo"].get("redacted"),
        "errors": status["errors"],
        "baseSepoliaLive": rails["base-sepolia-official-x402"]["liveSettlementAllowed"],
        "solanaStatus": rails["solana-pay-sh-svm-candidate"]["status"],
    }


class X402Tests(unittest.TestCase):
    def assert_expect(self, actual, expect):
        if "errors" in expect:
            self.assertEqual(actual["errors"], expect["errors"])
        for item in expect.get("errorsContain", []):
            self.assertIn(item, actual["errors"])
        for key, value in expect.items():
            if key in ("errors", "errorsContain"):
                continue
            self.assertEqual(actual[key], value, key)

    def test_status_vectors(self):
        for vector in VECTORS["status"]:
            status = x402_testnet.payment_status(vector["env"])
            with self.subTest(vector["name"]):
                self.assert_expect(view(status), vector["expect"])
                self.assertFalse(view(status)["baseSepoliaLive"])
                self.assertEqual(view(status)["solanaStatus"], "planned_simulated_only")
                if "absent" in vector:
                    self.assertNotIn(vector["absent"], json.dumps(status))

    def test_release_vectors(self):
        for vector in VECTORS["release"]:
            decision = x402_testnet.decide_release(vector["input"], ledger=x402_testnet.ReleaseLedger())
            with self.subTest(vector["name"]):
                self.assert_expect(decision, vector["expect"])
                self.assertIs(decision["liveSettlementAllowed"], False)
                if "absent" in vector:
                    self.assertNotIn(vector["absent"], json.dumps(decision))

    def test_process_environment_cannot_authorize_or_leak(self):
        sentinel = "not-a-key"
        previous = os.environ.get("EVM_PRIVATE_KEY")
        os.environ["EVM_PRIVATE_KEY"] = sentinel
        try:
            receipt = build_receipt("process-env", (True, []), "text.upper@1")
            decision = x402_testnet.decide_release(
                {"verdict": receipt, "amount": "1"},
                ledger=x402_testnet.ReleaseLedger(),
            )
        finally:
            if previous is None:
                os.environ.pop("EVM_PRIVATE_KEY", None)
            else:
                os.environ["EVM_PRIVATE_KEY"] = previous
        self.assertEqual(decision["decision"], "RELEASE")
        self.assertNotIn(sentinel, json.dumps(decision))
        self.assertEqual(os.environ.get("EVM_PRIVATE_KEY"), previous)

    def test_unknown_receipt_blocks_and_ok_receipt_simulates(self):
        ok = build_receipt("aox.uppercase", (True, []), "text.upper@1")
        unknown = build_receipt("aox.uppercase", None, "text.upper@1")
        failed = build_receipt("aox.uppercase", (False, ["nope"]), "text.upper@1")
        released = x402_testnet.decide_release(
            {"verdict": ok, "amount": "500000"},
            ledger=x402_testnet.ReleaseLedger(),
        )
        self.assertEqual(released["decision"], "RELEASE")
        self.assertIs(released["settled"], False)
        self.assertEqual(released["verdict"], "OK")
        self.assertTrue(Verdict(released["verdict"]).is_success)
        for receipt in (unknown, failed):
            decision = x402_testnet.decide_release(
                {"verdict": receipt, "amount": "500000"},
                ledger=x402_testnet.ReleaseLedger(),
            )
            self.assertEqual(decision["decision"], "DENY")
            self.assertEqual(decision["reason"], "verdict_not_ok")
            self.assertFalse(Verdict(decision["verdict"]).is_success)

    def test_tampered_receipt_is_denied(self):
        receipt = build_receipt("aox.uppercase", (True, []), "text.upper@1")
        receipt["verdict"] = "OK"
        receipt["hash"] = "0" * 64
        decision = x402_testnet.decide_release(
            {"verdict": receipt, "amount": "1"},
            ledger=x402_testnet.ReleaseLedger(),
        )
        self.assertEqual(decision["reason"], "receipt_rejected")
        bare = x402_testnet.decide_release(
            {"verdict": Verdict.OK, "amount": "1"},
            ledger=x402_testnet.ReleaseLedger(),
        )
        self.assertEqual(bare["reason"], "receipt_required")
        self.assertEqual(decision["decision"], "DENY")

    def test_injected_settler_runs_only_for_ready_ok_testnet(self):
        calls = []

        def settler(payload):
            calls.append(payload)
            return True

        ready = {
            "AOX_PAYMENT_MODE": "x402_testnet",
            "AOX_X402_NETWORK": "eip155:84532",
            "AOX_X402_PAY_TO": PAY_TO,
        }
        receipt = build_receipt("settler-ok", (True, []), "text.upper@1")
        blocked = [
            {"verdict": "FAILED", "amount": "1", "mode": "x402_testnet", "env": ready},
            {"verdict": "UNKNOWN", "amount": "1", "mode": "x402_testnet", "env": ready},
            {"verdict": "OK", "amount": "1", "network": "eip155:8453", "mode": "x402_testnet", "env": ready},
            {"verdict": receipt, "amount": "1000001", "maxUsd": "1.00", "mode": "x402_testnet", "env": ready},
            {"verdict": receipt, "amount": "1", "mode": "x402_testnet", "env": {"EVM_PRIVATE_KEY": "not-a-key", **ready}},
            {"verdict": Verdict.OK, "amount": "1", "mode": "x402_testnet", "env": ready},
        ]
        for spec in blocked:
            decision = x402_testnet.decide_release(spec, settler=settler, ledger=x402_testnet.ReleaseLedger())
            self.assertEqual(decision["decision"], "DENY", spec)
            self.assertIs(decision["settled"], False)
        simulated = x402_testnet.decide_release(
            {"verdict": receipt, "amount": "1", "mode": "simulated"},
            settler=settler,
            ledger=x402_testnet.ReleaseLedger(),
        )
        self.assertEqual(simulated["decision"], "RELEASE")
        self.assertIs(simulated["settled"], False)
        self.assertEqual(calls, [])
        ledger = x402_testnet.ReleaseLedger()
        released = x402_testnet.decide_release(
            {"verdict": receipt, "amount": "1", "mode": "x402_testnet", "env": ready},
            settler=settler,
            ledger=ledger,
        )
        self.assertEqual(released["decision"], "RELEASE")
        self.assertIs(released["settled"], True)
        self.assertIs(released["liveSettlementAllowed"], False)
        self.assertEqual(calls, [{
            "network": "eip155:84532",
            "amount": "1",
            "verdict": "OK",
            "receiptHash": receipt["hash"],
            "taskId": receipt["task_id"],
        }])
        self.assertNotIn("not-a-key", json.dumps(calls))
        replayed = x402_testnet.decide_release(
            {"verdict": receipt, "amount": "1", "mode": "x402_testnet", "env": ready},
            settler=settler,
            ledger=ledger,
        )
        self.assertEqual(replayed["reason"], "replay")
        self.assertIs(replayed["settled"], False)
        self.assertEqual(len(calls), 1)

    def test_gate_source_has_no_network_client(self):
        text = (ROOT / "x402_testnet.py").read_text()
        for needle in ("import urllib", "import requests", "import socket", "import subprocess", "import http.client"):
            self.assertNotIn(needle, text)
        self.assertEqual(x402_testnet.simulated_pay_to({}), x402_testnet.DEFAULT_SIMULATED_PAY_TO)
        gate = x402_testnet.create_gate({
            "AOX_PAYMENT_MODE": "x402_testnet",
            "AOX_X402_PAY_TO": PAY_TO,
        })
        self.assertIs(gate["gateActive"], True)
        self.assertIs(gate["liveSettlementAllowed"], False)
        self.assertIs(x402_testnet.create_gate({})["gateActive"], False)

    def test_spend_cap_rejects_non_positive_caps(self):
        for bad in ("0", "-1", "abc", "1e2", ""):
            with self.assertRaises(ValueError):
                x402_testnet.usd_to_micros(bad)
        self.assertTrue(x402_testnet.within_cap("1000000", "1.00"))
        self.assertFalse(x402_testnet.within_cap("1000001", "1.00"))
        self.assertFalse(x402_testnet.within_cap("0", "1.00"))
        self.assertFalse(x402_testnet.within_cap("-1", "1.00"))
        self.assertEqual(x402_testnet.usd_to_micros("100"), 5_000_000)

    def test_file_ledger_rejects_a_second_process(self):
        receipt = build_receipt("file-ledger", (True, []), "text.upper@1")
        spec = {"verdict": receipt, "amount": "1"}
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ledger.json")
            first = x402_testnet.decide_release(spec, ledger=x402_testnet.ReleaseLedger(path))
            second = x402_testnet.decide_release(spec, ledger=x402_testnet.ReleaseLedger(path))
            stored = Path(path).read_text()
        self.assertEqual(first["decision"], "RELEASE")
        self.assertEqual(second["reason"], "replay")
        self.assertIn(receipt["hash"], stored)
        self.assertNotIn("PRIVATE", stored)


if __name__ == "__main__":
    unittest.main()
