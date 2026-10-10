"""Three-state verdicts: only OK is success, and the receipt says which one."""

import copy
import unittest

import task_contracts
from verdict import (
    FORMAT,
    TimedOutEvidence,
    Verdict,
    build_receipt,
    replay_receipt,
    verdict_for,
)


def pair(ok, reasons):
    return (ok, reasons)


class VerdictTests(unittest.TestCase):
    def test_only_ok_is_success(self):
        self.assertIs(verdict_for(pair(True, [])), Verdict.OK)
        self.assertTrue(Verdict.OK.is_success)
        self.assertTrue(Verdict.OK.counts_as_healthy)
        self.assertIs(verdict_for(pair(False, ["output mismatch"])), Verdict.FAILED)
        self.assertFalse(Verdict.FAILED.is_success)
        self.assertFalse(Verdict.FAILED.counts_as_healthy)
        for evidence in (None, TimedOutEvidence(), {"timed_out": True}, pair(1, []), pair(True, ["x"]), "OK", True):
            verdict = verdict_for(evidence)
            self.assertIs(verdict, Verdict.UNKNOWN, evidence)
            self.assertFalse(verdict.is_success)
            self.assertFalse(verdict.counts_as_healthy)

    def test_truthy_unknown_is_still_not_success(self):
        # str-enum values are truthy. Callers have to use is_success.
        self.assertTrue(Verdict.UNKNOWN)
        self.assertFalse(Verdict.UNKNOWN.is_success)

    def test_uppercase_referee_maps_onto_the_receipt(self):
        inp = {"text": "synthetic"}
        good = {
            "kind": "exchange",
            "passed": True,
            "output": {"text": "SYNTHETIC"},
            "real_agents": 0,
            "sent": False,
            "spent": False,
        }
        ok, reasons = task_contracts.check("aox.uppercase", inp, good)
        receipt = build_receipt("aox.uppercase", (ok, reasons), "text.upper@1")
        self.assertEqual(receipt["format"], FORMAT)
        self.assertEqual(receipt["verdict"], "OK")
        self.assertEqual(replay_receipt(receipt)["hash"], receipt["hash"])
        junk = copy.deepcopy(good)
        junk["output"] = {"text": "nope"}
        failed = build_receipt("aox.uppercase", task_contracts.check("aox.uppercase", inp, junk), "text.upper@1")
        self.assertEqual(failed["verdict"], "FAILED")
        self.assertFalse(Verdict(failed["verdict"]).is_success)

    def test_missing_malformed_and_timeout_are_unknown(self):
        for evidence, kind in (
            (None, "missing"),
            (TimedOutEvidence(), "timed_out"),
            ({"timed_out": True}, "timed_out"),
            ((True, ["should not pass"]), "malformed"),
            ((1, []), "malformed"),
            ("done", "malformed"),
        ):
            receipt = build_receipt("aox.uppercase", evidence, "text.upper@1")
            self.assertEqual(receipt["verdict"], "UNKNOWN")
            self.assertEqual(receipt["evidence"], kind)
            self.assertFalse(Verdict(replay_receipt(receipt)["verdict"]).is_success)

    def test_tampered_verdict_fails_replay(self):
        receipt = build_receipt("aox.uppercase", (True, []), "text.upper@1")
        receipt["verdict"] = "FAILED"
        with self.assertRaises(ValueError):
            replay_receipt(receipt)

    def test_consistent_rewrite_replays_without_becoming_authenticated(self):
        rewritten = build_receipt("aox.uppercase", (False, ["replaced"]), "text.upper@1")
        self.assertEqual(replay_receipt(rewritten)["verdict"], "FAILED")


if __name__ == "__main__":
    unittest.main()
