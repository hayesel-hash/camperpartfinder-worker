"""Two-pass reader for Lippert / Girard component identification charts that have no Quantity or Model column:
"Callout | Part # | Description" (GG500 awning components CCD-0008337), "ITEM | DESCRIPTION | PART NUMBER" (Nova II patio
awning CCD-0006784) and "ITEM | DESCRIPTION | PART NUMBER (WHITE) | PART NUMBER (BLACK)" (GG750 awning CCD-0006108).

The charts are ruled tables. Pass A: pymupdf find_tables(); pass B: pdfplumber extract_tables() (two independent
table finders). A table is used when its header row has a "Description" cell and one or more "Part ..." cells; a colour
label in a part header ("PART NUMBER (WHITE)") is appended to the description ("Main Housing (white)"). "N/A" cells are
skipped; cells holding two numbers ("2025008011/ 2025008012") are reported as `shared_cells`, not loaded (which number
is which is not printed). Only rows on which both passes agree (spaces ignored) are kept.

usage: python3 -I lci_component_chart.py <pdf> <out.json> "<section label>"
"""
import hashlib, json, re, sys
import pymupdf, pdfplumber

NUM = re.compile(r"^\d{6,10}(?:-[A-Z0-9]{1,4})?$")
SHARED = re.compile(r"^\d{6,10}/$")


def read_tables(tables, carry=None):
    """tables: list of row lists (cells as text or None); carry: header row of the previous page's chart, used for a
    continuation table printed without a header (Nova II p 19) when its column count is the same.
    Returns (rows, shared, last_header)."""
    rows, shared = [], []
    for t in tables:
        hdr_i = None
        for k, r in enumerate(t):
            cells = [(c or "").lower() for c in r]
            if any(c.strip() == "description" for c in cells) and any(c.startswith("part") for c in cells):
                hdr_i = k; break
        if hdr_i is None and carry and t and len(t[0]) == len(carry):
            t = [carry] + t; hdr_i = 0
        if hdr_i is None:
            continue
        hdr = [(c or "") for c in t[hdr_i]]
        carry = hdr
        di = [k for k, c in enumerate(hdr) if c.strip().lower() == "description"][0]
        pcols = [(k, (re.search(r"\((\w+)\)", c) or [None, ""])[1].lower()) for k, c in enumerate(hdr)
                 if c.lower().startswith("part")]
        for r in t[hdr_i + 1:]:
            if len(r) != len(hdr):
                continue
            desc = " ".join((r[di] or "").split())
            for k, lab in pcols:
                cell = " ".join((r[k] or "").split())
                if not cell or cell.upper() == "N/A":
                    continue
                if "/" in cell and all(NUM.match(x.strip()) for x in cell.split("/")):
                    shared.append(cell); continue
                if NUM.match(cell) and desc:
                    rows.append((cell, f"{desc} ({lab})" if lab else desc))
    return rows, shared, carry


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, shared, noname = [], [], [], []
    carry_a = carry_b = None
    for i, p in enumerate(d):
        a, sa, carry_a = read_tables([t.extract() for t in p.find_tables().tables], carry_a)
        b, sb, carry_b = read_tables(pl.pages[i].extract_tables(), carry_b)
        key = lambda x: (x[0], "".join(x[1].split()).casefold())
        ka, kb = {key(x) for x in a}, {key(x) for x in b}
        if ka != kb:
            diffs.append({"page": i + 1, "only_a": [x for x in a if key(x) not in kb][:5], "only_b": [x for x in b if key(x) not in ka][:5]})
        shared += [{"page": i + 1, "cell": s} for s in sa]
        for x in a:
            if key(x) in kb:
                (keep if x[1] else noname).append((i + 1, x) if x[1] else {"page": i + 1, "number": x[0]})
    seen, lines, per = {}, [], {}
    other = []
    for pg, (num, t) in keep:
        if num in seen:
            if seen[num] != t:
                other.append({"page": pg, "number": num, "first": seen[num], "here": t})
            continue
        seen[num] = t; per[pg] = per.get(pg, 0) + 1
        lines.append(f"{pg}|{per[pg]}|{num}|{t.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines), "shared_cells": shared,
           "no_name": noname, "other_wordings": other}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(keep), "numbers": len(seen), "diffs": diffs[:3],
                      "shared": shared, "no_name": noname[:5], "other": other[:4]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
