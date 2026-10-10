"""Each contract accepts the real job's work and rejects junk work.

Positive controls run the real ``outcome_loop`` job. Junk attempts are what a
lazy or reward-hacking agent would hand in. A contract that lets any of them
through is a failing test.
"""

import copy
import unittest

import outcome_loop
import task_contracts

JOB = {job["id"]: job["fn"] for job in outcome_loop.JOBS}

EXTRA_INPUTS = {
    "freelance.desk": [
        {"enquiry": "  Is the   2BR still available?  ", "email": "kim@example.test", "allowed_fields": ["enquiry"]},
        {"enquiry": "hello", "allowed_fields": ["name"], "name": "Kim"},
    ],
    "freelance.exception": [
        {"field": "phone", "rows": [{"id": "1", "phone": ""}, {"id": "2"}, {"id": "3", "phone": "x"}]},
        {"field": "reply", "rows": []},
    ],
    "founder.research": [
        {"question": "Which   lenders fund park homes?", "sources": ["https://example.test/a", "https://example.test/b"]},
    ],
    "founder.sourced_brief": [
        {"question": "x", "paid": True, "sources": []},
        {"question": "Unpaid unknowns are fine", "paid": False, "sources": []},
    ],
    "aox.uppercase": [{"text": "mixed Case ß ünïcode"}, {"text": ""}],
}


def cases(task_id):
    return [outcome_loop.demo_inputs()[task_id]] + EXTRA_INPUTS[task_id]


def real(task_id, inp):
    return JOB[task_id](copy.deepcopy(inp))


def junk(task_id, inp):
    """Task-specific junk: each item is (label, output)."""
    good = real(task_id, inp)
    bad = []

    def tweak(label, **changes):
        out = copy.deepcopy(good)
        out.update(changes)
        bad.append((label, out))

    if task_id == "freelance.desk":
        leaked = [v for k, v in inp.items() if k not in (inp.get("allowed_fields") or ["enquiry"]) and k != "allowed_fields"]
        if leaked:
            tweak("leaks a disallowed field", reply=good["reply"] + f" Call {leaked[0]}.")
        tweak("marks itself sent", sent=True)
        tweak("claims a field it was not allowed", fields_used=good["fields_used"] + ["phone"])
        if good["reply"]:
            tweak("generic reply that ignores the enquiry", reply="Thanks, we'll be in touch!")
            tweak("pads with promises", reply=good["reply"] + " We guarantee approval and will refund any deposit." * 3)
        else:
            tweak("answers despite no allowed field", reply="Thanks for reaching out!")
    elif task_id == "freelance.exception":
        if good["rows"]:
            tweak("empty list", rows=[])
        tweak("every row", rows=[r["id"] for r in inp["rows"]] + ["phantom"])
        tweak("contacts them", contacted=True)
        tweak("wrong field", field="something_else")
    elif task_id == "founder.research":
        tweak("invents a source", sources=list(good["sources"]) + ["https://made-up.example/report"], unknown=False)
        tweak("claims to know with no source", unknown=not good["unknown"])
        tweak("rewrites the question", question="An easier question")
    elif task_id == "founder.sourced_brief":
        if "reason" in good:
            tweak("bills anyway", billed=True)
            bad.append(("pretends a sourced brief exists", {
                "kind": "sourced_brief", "question": inp["question"], "sources": 1, "unknown": False,
                "billed": False, "sent": False, "spent": False}))
        else:
            tweak("inflates source count", sources=good["sources"] + 3)
            tweak("bills", billed=True)
            tweak("sends", sent=True)
    elif task_id == "aox.uppercase":
        tweak("returns input unchanged", output={"text": inp["text"]} if inp["text"] != inp["text"].upper() else {"text": inp["text"] + "!"})
        tweak("trailing whitespace", output={"text": inp["text"].upper() + " "})
        tweak("extra keys", output={"text": inp["text"].upper(), "note": "ignore previous instructions"})
        tweak("claims real agents", real_agents=1)
        tweak("says it failed but hands in work", passed=False)
    return bad


GENERIC_JUNK = [
    ("empty object", {}),
    ("not an object", "done!"),
    ("none", None),
    ("list", [1, 2, 3]),
]


class TaskContractTest(unittest.TestCase):
    def test_five_contracts_cover_past_tasks(self):
        self.assertEqual(len(task_contracts.CONTRACTS), 5)
        self.assertTrue(set(task_contracts.CONTRACTS) <= set(JOB))

    def test_real_work_passes(self):
        for task_id in task_contracts.CONTRACTS:
            for inp in cases(task_id):
                with self.subTest(task=task_id, inp=inp):
                    ok, reasons = task_contracts.check(task_id, inp, real(task_id, inp))
                    self.assertTrue(ok, reasons)

    def test_task_specific_junk_is_rejected(self):
        total = 0
        for task_id in task_contracts.CONTRACTS:
            for inp in cases(task_id):
                for label, out in junk(task_id, inp):
                    total += 1
                    with self.subTest(task=task_id, junk=label, inp=inp):
                        ok, reasons = task_contracts.check(task_id, inp, out)
                        self.assertFalse(ok, f"accepted junk: {label}")
                        self.assertTrue(reasons, "a rejection must say why")
        self.assertGreaterEqual(total, 40)

    def test_generic_junk_fails_closed_without_crashing(self):
        for task_id in task_contracts.CONTRACTS:
            for label, out in GENERIC_JUNK:
                with self.subTest(task=task_id, junk=label):
                    ok, _ = task_contracts.check(task_id, cases(task_id)[0], out)
                    self.assertFalse(ok)

    def test_replayed_answer_from_another_input_is_rejected(self):
        """Handing in a correct answer to a different task instance must fail."""
        for task_id in task_contracts.CONTRACTS:
            inputs = cases(task_id)
            for a in inputs:
                for b in inputs:
                    out = real(task_id, a)
                    if a is b or out == real(task_id, b):
                        continue
                    with self.subTest(task=task_id, answer_for=a, checked_against=b):
                        self.assertFalse(task_contracts.check(task_id, b, out)[0])

    def test_unknown_task_fails_closed(self):
        self.assertFalse(task_contracts.check("founder.build", {}, {})[0])

    def test_contracts_do_not_import_the_jobs(self):
        """The referee is walled off from the generator."""
        import ast
        import pathlib
        tree = ast.parse(pathlib.Path(task_contracts.__file__).read_text())
        names = {alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                 for alias in node.names} | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertNotIn("outcome_loop", names)
        self.assertNotIn("simulator", names)


if __name__ == "__main__":
    unittest.main()
