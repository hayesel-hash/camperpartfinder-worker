"""Read-only real-catalogue comparison: production extractors vs relationship_graph_v2.

No database access, no gateway, no publication. Downloads one allowlisted PDF
through the production fetch policy (host allowlist, robots, same-origin
redirects), checks the SHA-256 fingerprint, runs both extractors on the chosen
pages and writes:

  <out>/edges.jsonl   one record per page: production edges, v2 edges
  <out>/summary.json  per-edge-type yield and a disagreement list ranked for
                      human annotation (the ground truth this benchmark needs)

Usage:
  python3 benchmarks/real_page_shadow.py --url URL --sha256 HEX \
      --authority distributor --adapter reimo-catalogue-v2 --sample 40 --out out/
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

import pymupdf  # noqa: E402
import rv_master_disk as prod  # noqa: E402
import relationship_graph_v2 as v2  # noqa: E402
from run_relationship_benchmark import current_edges  # noqa: E402


def choose_pages(spec, sample, total):
    if spec:
        pages = set()
        for part in spec.split(","):
            a, _, b = part.partition("-")
            pages.update(range(int(a), int(b or a) + 1))
        return sorted(p for p in pages if 1 <= p <= total)
    stride = max(1, total // max(1, sample))
    return list(range(1 + stride // 2, total + 1, stride))[:sample]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--authority", choices=("manufacturer", "distributor"), required=True)
    ap.add_argument("--adapter", default="adaptive-table-v3")
    ap.add_argument("--pages", default="")
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--out", default="shadow-out")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rv-shadow-") as tmp:
        dest = Path(tmp) / "catalogue.pdf"
        fingerprint, size = prod.download(a.url, dest)
        # "any" = exploratory run: record the observed fingerprint instead of enforcing one.
        if a.sha256.lower() != "any" and fingerprint != a.sha256.lower():
            raise SystemExit(f"fingerprint mismatch: expected {a.sha256}, got {fingerprint}; refusing to benchmark")
        totals = {"production": collections.Counter(), "v2": collections.Counter()}
        timing = {"production": 0.0, "v2": 0.0}
        disagreements = []
        pages_with = {"production": 0, "v2": 0}
        text_pages = 0
        with pymupdf.open(dest) as doc, (out / "edges.jsonl").open("w") as f:
            pages = choose_pages(a.pages, a.sample, len(doc))
            for p in pages:
                page = doc[p - 1]
                text_pages += len(page.get_text("words")) > 20
                t0 = time.perf_counter()
                cur = current_edges(page, a.authority, a.adapter)
                t1 = time.perf_counter()
                new = v2.extract_page(page, p, a.authority)
                t2 = time.perf_counter()
                timing["production"] += t1 - t0
                timing["v2"] += t2 - t1
                for label, edges, clean_key in (("production", cur, "qualified"), ("v2", new, "qualifiers")):
                    for e in edges:
                        totals[label][e["kind"] + (":qualified" if e[clean_key] else ":clean")] += 1
                    pages_with[label] += bool(edges)
                ck = {(e["kind"], e["a"], e["b"]) for e in cur}
                nk = {(e["kind"], e["a"], e["b"]) for e in new}
                for key in sorted(nk - ck):
                    e = next(x for x in new if (x["kind"], x["a"], x["b"]) == key)
                    disagreements.append({"page": p, "only_in": "v2", "edge": key, "statement": e["statement"],
                                          "qualifiers": e["qualifiers"], "method": e["method"]})
                for key in sorted(ck - nk):
                    disagreements.append({"page": p, "only_in": "production", "edge": key})
                f.write(json.dumps({"page": p, "words": len(page.get_text("words")),
                                    "production": cur, "v2": new}, ensure_ascii=False) + "\n")
    summary = {"url": a.url, "sha256": fingerprint, "bytes": size, "authority": a.authority,
               "pages_examined": len(pages), "pages_with_text_layer": text_pages, "pages": pages,
               "edges": {k: dict(v) for k, v in totals.items()},
               "pages_with_any_edge": pages_with,
               "seconds": {k: round(v, 2) for k, v in timing.items()},
               "disagreements_for_annotation": disagreements[:500],
               "note": "Counts are extractor output, not verified truth. Annotate the disagreement list "
                       "against the PDF pages before using these numbers to justify a full replay."}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print("DISAGREEMENTS (first 25):")
    for d in disagreements[:25]:
        print("  ", json.dumps(d, ensure_ascii=False)[:300])
    print(json.dumps({k: summary[k] for k in ("sha256", "pages_examined", "pages_with_text_layer", "edges", "pages_with_any_edge", "seconds")}, indent=2))


if __name__ == "__main__":
    main()
