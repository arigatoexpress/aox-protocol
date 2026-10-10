"""Small, fast version of the synthetic matcher experiment. Not demand evidence."""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('matcher_run', os.path.join(ROOT, 'experiments', '2026-10-07-matcher', 'run.py'))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run.REQUESTS_PER_RUN = 30
        cls.first = run.experiment(seeds=[1, 2])
        cls.second = run.experiment(seeds=[1, 2])

    def test_deterministic(self):
        self.assertEqual(self.first, self.second)

    def test_invariants_and_labels(self):
        r = self.first
        self.assertTrue(r['synthetic_only'])
        self.assertFalse(r['real_demand_evidence'])
        self.assertTrue(all(r['invariants'].values()))
        for policy in ('reputation', 'lowest_price'):
            self.assertEqual(r['aggregate'][policy]['traces_posted'], 60)

    def test_at_least_three_distinct_requesters_and_common_request_stream(self):
        reqs = {j['requester'] for j in run.request_stream(1)}
        self.assertGreaterEqual(len({run.OPERATORS[x] for x in reqs}), 3)
        self.assertEqual(list(run.request_stream(1)), list(run.request_stream(1)))

    def test_lowest_price_always_picks_cheapest_eligible(self):
        # prov-bargain is the cheapest offer on both contracts and every budget (6..12) covers it.
        for row in self.first['per_run']['lowest_price']:
            self.assertEqual(set(row['provider_share']), {'prov-bargain'})


if __name__ == '__main__':
    unittest.main()
