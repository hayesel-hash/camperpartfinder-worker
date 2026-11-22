"""Compare relationship extractors on identical benchmark pages.

  python3 benchmarks/run_relationship_benchmark.py            # table to stdout
  python3 benchmarks/run_relationship_benchmark.py --json     # machine-readable

"current" replays the exact production page path in scripts/rv_master_disk.py:
adaptive_page() -> relationship_rows() -> catalogue_relationship_extractor.
"""
from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

import rv_master_disk as prod  # noqa: E402
from catalogue_relationship_extractor import extract_page as prod_catalogue  # noqa: E402
import relationship_graph_v2 as v2  # noqa: E402
from relationship_cases import CASES as DEV_CASES, build  # noqa: E402
from relationship_holdout_cases import CASES as HOLDOUT_CASES  # noqa: E402
CASES = HOLDOUT_CASES if "--holdout" in sys.argv else DEV_CASES

KIND_MAP = {
    "stated_replacement_unverified": "supersedes",
    "manufacturer_supersession_candidate": "supersedes",
    "distributor_manufacturer_crossref": "oem_xref",
    "fits_model": "fits",
}


def current_edges(page, authority, adapter=None):
    adapter = adapter or ("reimo-catalogue-v2" if authority == "distributor" else "adaptive-table-v3")
    found, _metrics = prod.adaptive_page(page, 1, adapter, None, authority)
    out = []
    for r in prod.relationship_rows(page, 1):
        out.append({"kind": "supersedes", "a": r["original"], "b": r["replacement"],
                    "qualified": bool(r["page_qualifiers_detected"]), "method": r["method"]})
    for r in prod_catalogue(page, 1, found, authority):
        out.append({"kind": KIND_MAP[r["kind"]], "a": r["subject"], "b": r["object"],
                    "qualified": False, "method": r["method"]})
    return out


def v2_edges(page, authority):
    return [{"kind": e["kind"], "a": e["a"], "b": e["b"], "qualified": bool(e["qualifiers"]),
             "method": e["method"]} for e in v2.extract_page(page, 1, authority)]


def matches(pred, gold):
    kind, a, b = gold
    if pred["kind"] != kind or pred["a"] != a:
        return False
    if kind == "fits":
        return b.lower() in pred["b"].lower()
    return pred["b"] == b


def score(extractor):
    per_kind = collections.defaultdict(lambda: collections.Counter())
    per_case = []
    for case in CASES:
        name, authority, cls, _items, gold = case
        doc, page = build(case)
        try:
            preds = extractor(page, authority)
        finally:
            doc.close()
        # De-duplicate identical claims from overlapping methods.
        uniq = {}
        for p in preds:
            key = (p["kind"], p["a"], p["b"])
            uniq[key] = {**p, "qualified": uniq.get(key, p)["qualified"] and p["qualified"]}
        preds = list(uniq.values())
        hit_staged, hit_clean = set(), set()
        for g in gold:
            for p in preds:
                if matches(p, g):
                    hit_staged.add(g)
                    if not p["qualified"]:
                        hit_clean.add(g)
        fps = [p for p in preds if not p["qualified"] and not any(matches(p, g) for g in gold)]
        for g in gold:
            c = per_kind[g[0]]
            c["gold"] += 1
            c["staged_tp"] += g in hit_staged
            c["clean_tp"] += g in hit_clean
        for p in fps:
            per_kind[p["kind"]]["clean_fp"] += 1
        per_kind["_all"]["clean_pred"] += sum(not p["qualified"] for p in preds)
        per_case.append({"case": name, "class": cls, "gold": len(gold), "staged_hits": len(hit_staged),
                         "clean_hits": len(hit_clean), "false_positives": [(p["kind"], p["a"], p["b"]) for p in fps],
                         "qualified_preds": sum(p["qualified"] for p in preds)})
    return per_kind, per_case


def summary(per_kind):
    rows = {}
    tot = collections.Counter()
    for kind, c in per_kind.items():
        if kind == "_all":
            continue
        tot.update(c)
        clean_pred = c["clean_tp"] + c["clean_fp"]
        rows[kind] = {"gold": c["gold"],
                      "staged_recall": round(c["staged_tp"] / c["gold"], 3) if c["gold"] else None,
                      "clean_recall": round(c["clean_tp"] / c["gold"], 3) if c["gold"] else None,
                      "clean_precision": round(c["clean_tp"] / clean_pred, 3) if clean_pred else None,
                      "clean_false_positives": c["clean_fp"]}
    clean_pred = tot["clean_tp"] + tot["clean_fp"]
    rows["ALL"] = {"gold": tot["gold"], "staged_recall": round(tot["staged_tp"] / tot["gold"], 3),
                   "clean_recall": round(tot["clean_tp"] / tot["gold"], 3),
                   "clean_precision": round(tot["clean_tp"] / clean_pred, 3) if clean_pred else None,
                   "clean_false_positives": tot["clean_fp"]}
    return rows


def main():
    result = {}
    for label, fn in (("current_production", current_edges), ("relationship_graph_v2", v2_edges)):
        per_kind, per_case = score(fn)
        result[label] = {"summary": summary(per_kind), "cases": per_case}
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))
        return result
    for label, r in result.items():
        print(f"\n== {label} ==")
        print(f"{'edge type':<12}{'gold':>5}{'staged R':>10}{'clean R':>9}{'clean P':>9}{'FP':>4}")
        for kind, s in r["summary"].items():
            fmt = lambda v: "  -  " if v is None else f"{v:.2f}"
            print(f"{kind:<12}{s['gold']:>5}{fmt(s['staged_recall']):>10}{fmt(s['clean_recall']):>9}{fmt(s['clean_precision']):>9}{s['clean_false_positives']:>4}")
        for c in r["cases"]:
            flag = "" if c["clean_hits"] == c["gold"] and not c["false_positives"] else "  <--"
            print(f"   {c['case']:<38} gold {c['gold']}  staged {c['staged_hits']}  clean {c['clean_hits']}  FP {c['false_positives']}{flag}")
    return result


if __name__ == "__main__":
    main()
