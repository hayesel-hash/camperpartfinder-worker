import unittest
from runner_circuit_breaker import classify_jobs, retry_eligible

STEP = dict(name='checkout', status='completed', started_at='2026-11-20T23:00:00Z', completed_at='2026-11-20T23:00:02Z')

class BreakerTests(unittest.TestCase):
    def test_pre_provisioning_never_retry(self):
        j = dict(status='completed', conclusion='failure', runner_id=0, steps=[],
                 started_at='2026-11-20T23:00:00Z', completed_at='2026-11-20T23:00:03Z')
        self.assertEqual(classify_jobs([j,j]), 'pre_provisioning_failure')
        self.assertFalse(retry_eligible([j]))
    def test_missing_fields_fail_closed(self):
        self.assertEqual(classify_jobs([dict(status='completed', conclusion='failure', steps=None)]), 'unknown_incomplete_metadata')
    def test_actual_runner_can_retry(self):
        j = dict(status='completed', conclusion='failure', runner_id=42, steps=[STEP])
        self.assertTrue(retry_eligible([j]))
    def test_active_blocks_retry(self):
        self.assertFalse(retry_eligible([dict(status='in_progress', runner_id=42, steps=[{}])]))
    def test_mixed_failed_jobs_fail_closed(self):
        executed = dict(status='completed', conclusion='failure', runner_id=42, steps=[STEP])
        unallocated = dict(status='completed', conclusion='failure', runner_id=0, steps=[], started_at='2026-11-20T23:00:00Z', completed_at='2026-11-20T23:00:03Z')
        self.assertFalse(retry_eligible([executed, unallocated]))
    def test_successful_run_not_retryable(self):
        self.assertFalse(retry_eligible([dict(status='completed', conclusion='success', runner_id=42, steps=[{}])]))
    def test_queued_step_is_not_execution(self):
        self.assertFalse(retry_eligible([dict(status='completed', conclusion='failure', runner_id=42, steps=[dict(name='checkout', status='queued')])]))
    def test_missing_step_timestamps_fail_closed(self):
        self.assertFalse(retry_eligible([dict(status='completed', conclusion='failure', runner_id=42, steps=[dict(name='checkout', status='completed')])]))
    def test_mixed_executed_and_queued_fail_closed(self):
        a = dict(status='completed', conclusion='failure', runner_id=42, steps=[STEP])
        b = dict(status='completed', conclusion='failure', runner_id=43, steps=[dict(status='queued')])
        self.assertFalse(retry_eligible([a,b]))
    def test_slow_failure_not_pre_provisioning(self):
        j = dict(status='completed', conclusion='failure', runner_id=0, steps=[],
                 started_at='2026-11-20T23:00:00Z', completed_at='2026-11-20T23:02:00Z')
        self.assertFalse(retry_eligible([j]))

if __name__ == '__main__': unittest.main()
