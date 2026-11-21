"""Fail-closed classifier for GitHub Actions runner allocation. Does not dispatch retries."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

@dataclass(frozen=True)
class Assessment:
    classification: str
    retry_allowed: bool
    evidence: tuple[str, ...]

def assess_jobs(jobs: Sequence[Mapping[str, Any]], *, max_seconds: int = 30) -> Assessment:
    if not jobs:
        return Assessment("UNKNOWN_INCOMPLETE_EVIDENCE", False, ("No jobs returned",))
    evidence = []
    preprovision = True
    real_execution = False
    for index, job in enumerate(jobs):
        rid, steps = job.get("runner_id"), job.get("steps")
        start, end = job.get("started_at"), job.get("completed_at")
        if rid is None or not isinstance(steps, list) or not start or not end:
            return Assessment("UNKNOWN_INCOMPLETE_EVIDENCE", False, (f"job[{index}] missing runner_id/steps/timestamps",))
        try:
            seconds = (datetime.fromisoformat(end.replace("Z", "+00:00")) -
                       datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
        except (ValueError, TypeError):
            return Assessment("UNKNOWN_INCOMPLETE_EVIDENCE", False, (f"job[{index}] invalid timestamps",))
        if seconds < 0:
            return Assessment("UNKNOWN_INCOMPLETE_EVIDENCE", False, (f"job[{index}] negative duration",))
        evidence.append(f'job[{index}] id={job.get("id")} runner_id={rid} steps={len(steps)} elapsed_s={seconds:g} conclusion={job.get("conclusion")}')
        if not (job.get("conclusion") == "failure" and rid == 0 and len(steps) == 0 and seconds <= max_seconds):
            preprovision = False
        if isinstance(rid, int) and rid > 0 and len(steps) > 0:
            real_execution = True
    if preprovision:
        return Assessment("PRE_PROVISIONING_FAILURE", False, tuple(evidence))
    if real_execution:
        return Assessment("RUNNER_EXECUTED", True, tuple(evidence))
    return Assessment("UNKNOWN_INCOMPLETE_EVIDENCE", False, tuple(evidence))
