"""The one-command demo stays deterministic and synthetic."""

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

import demo
import x402_testnet

ROOT = Path(__file__).resolve().parents[1]
BANNED = re.compile(r"\b(token|buyback|yield|investment|staking)\b", re.IGNORECASE)
SCAN = (
    "demo.py",
    "DEMO.md",
    "verdict.py",
    "x402_testnet.py",
    "assets/aox-wordmark.svg",
    "payments/ATTRIBUTION.md",
    "payments/x402-config.mjs",
    "payments/x402-testnet.mjs",
    "payments/x402-testnet.test.mjs",
    "payments/receipt.mjs",
    "payments/x402-live.mjs",
    "payments/x402-live.test.mjs",
)


class DemoTests(unittest.TestCase):
    def test_demo_output_is_stable_and_blocks_unknown(self):
        first = subprocess.check_output([sys.executable, str(ROOT / "demo.py")], text=True)
        second = subprocess.check_output([sys.executable, str(ROOT / "demo.py")], text=True)
        self.assertEqual(first, second)
        self.assertIn("synthetic", first.lower())
        self.assertIn("Base Sepolia", first)
        self.assertIn("eip155:84532", first)
        self.assertIn("Verdict OK", first)
        self.assertIn("UNKNOWN missing: verdict UNKNOWN decision DENY", first)
        self.assertIn("FAILED junk: verdict FAILED decision DENY", first)
        self.assertIn("settled False", first)
        self.assertIn("liveSettlementAllowed false", first)
        self.assertIsNone(BANNED.search(first))

    def test_new_demo_files_omit_banned_language(self):
        for name in SCAN:
            text = (ROOT / name).read_text()
            self.assertIsNone(BANNED.search(text), name)

    def test_default_demo_ignores_live_env(self):
        key = "ab" * 32
        env = os.environ.copy()
        env["TESTNET_PAYER_KEY"] = key
        env["TESTNET_PAYTO_ADDRESS"] = "0x1111111111111111111111111111111111111111"
        env["TESTNET_FACILITATOR_URL"] = "https://x402.org/facilitator"
        first = subprocess.check_output([sys.executable, str(ROOT / "demo.py")], text=True, env=env)
        second = subprocess.check_output([sys.executable, str(ROOT / "demo.py")], text=True)
        self.assertEqual(first, second)
        self.assertNotIn(key, first)

    def test_live_flag_names_missing_env_and_hides_the_key(self):
        key = "cd" * 32
        env = os.environ.copy()
        for name in demo.REQUIRED_LIVE:
            env.pop(name, None)
        env["TESTNET_PAYER_KEY"] = key
        proc = subprocess.run(
            [sys.executable, str(ROOT / "demo.py"), "--live-testnet"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("TESTNET_PAYTO_ADDRESS", proc.stderr)
        self.assertIn("TESTNET_FACILITATOR_URL", proc.stderr)
        self.assertIn("AOX synthetic demo", proc.stdout)
        self.assertNotIn(key, proc.stdout)
        self.assertNotIn(key, proc.stderr)
        self.assertFalse((ROOT / ".aox-release-ledger.json").exists())

    def test_live_release_binds_receipt_and_rejects_replay(self):
        key = "ef" * 32
        env = {
            "TESTNET_PAYER_KEY": key,
            "TESTNET_PAYTO_ADDRESS": "0x2222222222222222222222222222222222222222",
            "TESTNET_FACILITATOR_URL": "https://x402.org/facilitator",
        }
        calls = []
        ledger = x402_testnet.ReleaseLedger()

        def settler(payload):
            calls.append(payload)
            return True

        first = demo.live_release(env, settler=settler, ledger=ledger)
        second = demo.live_release(env, settler=settler, ledger=ledger)
        self.assertEqual(first["decision"], "RELEASE")
        self.assertIs(first["settled"], True)
        self.assertEqual(calls[0]["receiptHash"], first["receiptHash"])
        self.assertEqual(calls[0]["taskId"], first["taskId"])
        self.assertEqual(second["reason"], "replay")
        self.assertEqual(len(calls), 1)
        self.assertNotIn(key, json.dumps(first))
        self.assertNotIn(key, json.dumps(calls))
        blocked = demo.live_release(
            {**env, "TESTNET_FACILITATOR_URL": "https://example.com/facilitator"},
            settler=settler,
            ledger=x402_testnet.ReleaseLedger(),
        )
        self.assertEqual(blocked["reason"], "facilitator_not_allowlisted")
        self.assertEqual(len(calls), 1)

    def test_ported_code_is_relicensed(self):
        attribution = " ".join((ROOT / "payments" / "ATTRIBUTION.md").read_text().split())
        header = " ".join((ROOT / "verdict.py").read_text().split())
        sentence = "The author relicenses the vendored Verdict enum and the ported x402 rail under the Apache License 2.0."
        self.assertIn(sentence, attribution)
        self.assertIn(sentence, header)

    def test_wordmark_is_svg(self):
        svg = (ROOT / "assets" / "aox-wordmark.svg").read_text()
        self.assertIn("<svg", svg)
        self.assertIn("AOX", svg)


if __name__ == "__main__":
    unittest.main()
