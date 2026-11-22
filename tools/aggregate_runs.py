"""Aggregate real worker outcomes from GitHub Actions logs (Process catalogue queue step only)."""
import collections
import glob
import json
import re
import sys

STEP = "Process catalogue queue"
stats = collections.Counter()
errors = collections.Counter()
catalogues = collections.Counter()
extracted_by_cat = collections.Counter()
idle_jobs = 0
jobs_seen = 0
job_secs = []

for path in sorted(glob.glob(sys.argv[1] + "/run_*.log")):
    per_job = collections.defaultdict(list)
    times = collections.defaultdict(list)
    for line in open(path, encoding="utf-8", errors="replace"):
        parts = line.rstrip("\n").split("\t", 2)
        if len(parts) < 3:
            continue
        job, step, rest = parts
        m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", rest)
        if m:
            times[job].append(m.group(1))
        brace = rest.find("{")
        if brace < 0:
            continue
        try:
            ev = json.loads(rest[brace:])
        except ValueError:
            continue
        per_job[job].append(ev)
    for job, evs in per_job.items():
        jobs_seen += 1
        work = [e for e in evs if "catalogue" in e or "repository" in e or "verified_catalogue" in e]
        if not work:
            idle_jobs += 1
        for e in evs:
            if "catalogue" in e:
                stats[f"{e['mode']}:{e['outcome']}"] += 1
                catalogues[e["catalogue"]] += 1
                extracted_by_cat[e["catalogue"]] += e.get("extracted") or 0
                stats["rows_extracted"] += e.get("extracted") or 0
                stats["saved_total"] += e.get("saved") if isinstance(e.get("saved"), int) else 0
                if e.get("error"):
                    errors[e["error"]] += 1
            elif "repository" in e:
                stats["repository:" + e["status"]] += 1
                stats["links_found"] += e.get("links") or 0
                if e.get("error"):
                    errors["repo: " + e["error"][:80]] += 1
            elif "event" in e and not (e["event"]=="claim_gateway_transient" and e.get("action")=="claim_batch"):
                stats["event:" + e["event"]] += 1

print("runs:", len(glob.glob(sys.argv[1] + "/run_*.log")), "job-instances:", jobs_seen, "idle job-instances:", idle_jobs)
for k, v in sorted(stats.items()):
    print(f"  {k}: {v}")
print("errors:")
for k, v in errors.most_common(20):
    print(f"  {v:5d}  {k}")
print("catalogues touched:", len(catalogues))
for c, n in catalogues.most_common(15):
    print(f"  {n:4d} batches  {extracted_by_cat[c]:6d} rows  {c}")
