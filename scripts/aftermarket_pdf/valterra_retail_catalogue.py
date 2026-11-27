"""Two-pass reader for the Valterra RV Retail Parts Catalogue (Acrobat Distiller "Valterra Retail Catalog", 39 pages):
product tables headed "Part No. | Ctn.Qty. | Ctn.Wt. | Retail Price". Each row is printed on one baseline:
part number (left column), description, carton quantity, carton weight, retail price. Lines below a row at the
description indent ("Black w/gate seals, nuts, bolts") are part of the row; the paragraphs and headings between rows
(left of the description indent) are not.

Pass A: pymupdf word boxes; pass B: pdfplumber word boxes (two text extractors), same row rule in both: a baseline
whose first word sits in the "Part No." column (x from the page's header) and matches the part-number shape, with
three numeric cells ("-" allowed) right of the "Ctn.Qty." column; description = the words between, plus the wrapped
lines directly below that start at the description indent and hold no cells. pdfplumber glues words around commas
("Dry,8-2"), so the passes are compared with spaces removed and pass A's text is kept.

Rows on which both passes give the same number and description are kept. Rows whose description is "Same as Above,
..." are reported (the description is not self-contained) and not loaded. Prices, carton quantities and weights are
dropped.

usage: python3 -I valterra_retail_catalogue.py <pdf> <out.json>
"""
import hashlib
import json
import re
import sys

import pdfplumber
import pymupdf

PN = re.compile(r"^(?=.*\d)[A-Z]{1,3}\d{1,5}(?:-[A-Z0-9]{1,6})*[A-Z0-9]*$")
CELL = re.compile(r"^(?:\d+(?:\.\d+)?(?:/\d+)?|-)$")
TITLE = "Valterra RV Retail Parts Catalogue"


def clean(s):
    return " ".join(s.replace(" ", " ").split())


def rows_from_words(words, part_x, qty_x):
    """words: (x0, x1, top, bottom, text). A row = a baseline whose first word sits in the Part No. column and matches
    the part-number shape, with exactly three numeric cells right of the Ctn.Qty. column. Description = the words
    between, plus the lines directly below that start at the description indent and hold no cells (wrapped
    descriptions such as "3\u201d SAN TEE REDUCING - 3\u201d bayonet / x 1-1/2\u201d hub")."""
    lines = {}
    for w in words:
        lines.setdefault(round(w[3]), []).append(w)
    keys = sorted(lines)
    rows = []
    k = 0
    while k < len(keys):
        ws = sorted(lines[keys[k]], key=lambda w: w[0])
        first = ws[0]
        desc = [w for w in ws[1:] if w[1] < qty_x - 4]
        tail = [w[4] for w in ws[1:] if w[0] >= qty_x - 4]
        if abs(first[0] - part_x) > 12 or not PN.match(first[4]) or not desc or len(tail) != 3 \
                or not all(CELL.match(t) for t in tail):
            k += 1
            continue
        dx = desc[0][0]
        h = first[3] - first[2]
        text = [w[4] for w in desc]
        prev_bottom = first[3]
        j = k + 1
        while j < len(keys):
            nx = sorted(lines[keys[j]], key=lambda w: w[0])
            if abs(nx[0][0] - dx) > 4 or any(w[1] >= qty_x - 4 for w in nx) or nx[0][3] - prev_bottom > 1.6 * h:
                break
            text += [w[4] for w in nx]
            prev_bottom = nx[0][3]
            j += 1
        rows.append((first[4], clean(" ".join(text))))
        k = j
    return rows


def header_x(words):
    part = qty = None
    for w in words:
        if w[4].startswith("Ctn.Qty") and qty is None:
            qty = w[0]
        if w[4] == "Part" and part is None:
            part = w[0]
    return part, qty


def pass_a(page):
    """pymupdf words."""
    words = [(w[0], w[2], w[1], w[3], w[4]) for w in page.get_text("words")]
    part, qty = header_x(words)
    return rows_from_words(words, part, qty) if part is not None and qty is not None else []


def pass_b(page):
    """pdfplumber words (it glues words around commas: compared with spaces removed)."""
    words = [(w["x0"], w["x1"], w["top"], w["bottom"], w["text"]) for w in page.extract_words()]
    part, qty = header_x(words)
    return rows_from_words(words, part, qty) if part is not None and qty is not None else []


def key(row):
    return (row[0], row[1].replace(" ", ""))


def main(pdf, outp):
    raw = open(pdf, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    pl = pdfplumber.open(pdf)
    keep, diffs, same_as_above, dup_conflicts = [], [], [], []
    seen = {}
    for i, p in enumerate(d):
        a = pass_a(p)
        b = pass_b(pl.pages[i])
        sa, sb = {key(x) for x in a}, {key(x) for x in b}
        diffs += [{"page": i + 1, "only_a": x} for x in a if key(x) not in sb]
        diffs += [{"page": i + 1, "only_b": x} for x in b if key(x) not in sa]
        for num, desc in a:
            if key((num, desc)) not in sb:
                continue
            if desc.lower().startswith("same as above"):
                same_as_above.append({"page": i + 1, "number": num, "desc": desc})
                continue
            if num in seen and seen[num] != desc:
                dup_conflicts.append({"page": i + 1, "number": num, "desc": desc, "first": seen[num]})
                continue
            if num in seen:
                continue
            seen[num] = desc
            keep.append((i + 1, num, desc))
    lines = [f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0" for n, (pg, num, desc) in enumerate(keep, 1)]
    out = {"doc": sha, "pages": d.page_count, "agree": bool(keep), "diffs": diffs, "rows_total": len(keep),
           "same_as_above": same_as_above, "dup_conflicts": dup_conflicts,
           "sections": {"0": TITLE}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "diffs": len(diffs), "same_as_above": len(same_as_above),
                      "dup_conflicts": len(dup_conflicts)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
