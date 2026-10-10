import unittest

import outcome_loop


class OutcomeLoopTest(unittest.TestCase):
    def test_demo_passes_every_job_and_stops(self):
        receipt = outcome_loop.run(outcome_loop.demo_inputs())
        self.assertEqual(receipt["passed"], receipt["jobs"])
        self.assertFalse(receipt["live_marketplace"])
        self.assertFalse(receipt["payments"])
        by_id = {item["id"]: item for item in receipt["results"]}
        desk = by_id["freelance.desk"]["output"]
        self.assertFalse(desk["sent"])
        self.assertEqual(desk["fields_used"], ["enquiry"])
        self.assertNotIn("555-0100", desk["reply"])
        gate = by_id["freelance.outreach"]["output"]
        self.assertEqual(gate["outreach"], "blocked_name_later")
        self.assertEqual(gate["prices"]["1"]["setup"], 495)
        self.assertFalse(gate["prices"]["3"]["offered"])
        self.assertTrue(by_id["founder.research"]["output"]["unknown"])
        self.assertFalse(by_id["founder.build"]["output"]["merged"])
        self.assertEqual(by_id["freelance.exception"]["output"]["rows"], ["17"])
        self.assertFalse(by_id["freelance.exception"]["output"]["contacted"])
        self.assertTrue(by_id["aox.uppercase"]["output"]["passed"])
        self.assertEqual(by_id["aox.uppercase"]["output"]["real_agents"], 0)
        brief = by_id["founder.sourced_brief"]["output"]
        self.assertEqual(brief["sources"], 1)
        self.assertFalse(brief["billed"])

    def test_paid_brief_with_no_source_is_not_billed(self):
        output = outcome_loop.sourced_brief({"question": "Anything", "paid": True, "sources": []})
        self.assertFalse(output["billed"])
        self.assertEqual(output["reason"], "no_source")
        self.assertNotIn("question", output)

    def test_name_present_still_does_not_send(self):
        inputs = outcome_loop.demo_inputs()
        inputs["freelance.outreach"] = {"sender_name": "Ada"}
        output = outcome_loop.outreach_gate(inputs["freelance.outreach"])
        self.assertEqual(output["outreach"], "blocked_until_explicit_send_yes")
        self.assertFalse(output["sent"])

    def test_forbidden_flag_rejects_only_that_job(self):
        inputs = outcome_loop.demo_inputs()

        def bad(_payload):
            return {"sent": True}

        original = outcome_loop.JOBS
        outcome_loop.JOBS = ({"id": "freelance.desk", "fn": bad, "human": "no"},) + tuple(
            job for job in original if job["id"] != "freelance.desk"
        )
        try:
            receipt = outcome_loop.run(inputs)
        finally:
            outcome_loop.JOBS = original
        by_id = {item["id"]: item for item in receipt["results"]}
        self.assertEqual(by_id["freelance.desk"]["status"], "REJECTED")
        self.assertIn("sent", by_id["freelance.desk"]["violation"])
        self.assertEqual(by_id["founder.build"]["status"], "PASS")
        self.assertEqual(receipt["passed"], receipt["jobs"] - 1)


if __name__ == "__main__":
    unittest.main()
