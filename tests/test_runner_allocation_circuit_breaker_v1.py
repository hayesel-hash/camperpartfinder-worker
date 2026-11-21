import unittest
from engineering.runner_allocation_circuit_breaker_v1 import assess_jobs

BASE = dict(id=1, runner_id=0, steps=[], started_at="2026-11-20T10:00:00Z", completed_at="2026-11-20T10:00:04Z", conclusion="failure")

class Tests(unittest.TestCase):
    def test_preprovision(self):
        self.assertEqual(assess_jobs([BASE, dict(BASE, id=2)]).classification, "PRE_PROVISIONING_FAILURE")
    def test_missing_steps_fail_closed(self):
        x = dict(BASE); x.pop("steps")
        self.assertFalse(assess_jobs([x]).retry_allowed)
    def test_missing_runner_fail_closed(self):
        x = dict(BASE); x.pop("runner_id")
        self.assertFalse(assess_jobs([x]).retry_allowed)
    def test_real_runner(self):
        self.assertTrue(assess_jobs([dict(BASE, runner_id=42, steps=[{"name": "checkout"}])]).retry_allowed)
    def test_long_no_runner_not_decisive(self):
        self.assertFalse(assess_jobs([dict(BASE, completed_at="2026-11-20T10:03:00Z")]).retry_allowed)
    def test_empty_fail_closed(self):
        self.assertFalse(assess_jobs([]).retry_allowed)
    def test_idempotent(self):
        self.assertEqual(assess_jobs([BASE]), assess_jobs([BASE]))

if __name__ == "__main__":
    unittest.main()
