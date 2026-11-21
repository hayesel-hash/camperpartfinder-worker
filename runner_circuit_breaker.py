"""Conservative GitHub Actions runner-allocation circuit breaker.

Missing runner_id or steps is UNKNOWN, not proof of pre-provisioning.
No retries are permitted until jobs demonstrate actual runner execution.
"""
from datetime import datetime


def _executed_step(job):
    """Require a completed, timestamped step rather than a merely allocated runner."""
    for step in job.get('steps') or []:
        if not isinstance(step, dict):
            continue
        if step.get('status') != 'completed' or not step.get('started_at') or not step.get('completed_at'):
            continue
        try:
            start = datetime.fromisoformat(step['started_at'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(step['completed_at'].replace('Z', '+00:00'))
            if end >= start:
                return True
        except (TypeError, ValueError, AttributeError):
            continue
    return False


def classify_jobs(jobs):
    if not jobs:
        return 'unknown_no_jobs'
    if any(j.get('status') != 'completed' for j in jobs):
        return 'active'
    if all(j.get('conclusion') == 'success' for j in jobs):
        return 'successful_run'
    if any('runner_id' not in j or j.get('steps') is None for j in jobs):
        return 'unknown_incomplete_metadata'
    if all(j.get('runner_id') == 0 and j.get('steps') == [] and
           j.get('conclusion') == 'failure' and
           _within_seconds(j) for j in jobs):
        return 'pre_provisioning_failure'
    if any(j.get('conclusion') == 'failure' and
           (not isinstance(j.get('runner_id'), int) or j['runner_id'] <= 0 or not _executed_step(j)) for j in jobs):
        return 'unknown_no_execution_evidence'
    if any(isinstance(j.get('runner_id'), int) and j['runner_id'] > 0 and _executed_step(j) for j in jobs):
        return 'runner_executed'
    return 'unknown_no_execution_evidence'


def _within_seconds(job, limit=30):
    try:
        start = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
        return 0 <= (end - start).total_seconds() <= limit
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def retry_eligible(jobs):
    """Conservative prerequisite only; incident reservation must still be atomic."""
    return classify_jobs(jobs) == 'runner_executed' and any(
        j.get('conclusion') == 'failure' for j in jobs
    )
