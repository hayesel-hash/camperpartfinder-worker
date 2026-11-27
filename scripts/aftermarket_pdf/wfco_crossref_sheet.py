"""WFCO "Converter and Electrical Cross-Reference Guide" (2025 sheet, PDF page 2).

Page 2 holds ~19 small two-column tables, one per competitor, in four page columns:
a brand heading, then a header row "WFCO | <BRAND>" and rows "<WFCO number> | <competitor
numbers, comma separated>".  A competitor cell may wrap onto the next line (no WFCO number on
the continuation line).  Page 1 says the charts are to "replace other manufacturers'
products with ... WFCO products".

Two independent text engines read the same geometry:
  pass A  pdfplumber (pdfminer) words
  pass B  pymupdf words
Each table: header row = the word "WFCO" followed on its baseline by the brand header; the
table spans from that WFCO x to the next page column's WFCO x and down to the next header in
the same page column.  Rows must agree between passes.

Returned per row: WFCO number, brand, the competitor numbers (comma split), and a hold reason
for shapes that would need guessing: a "/" model pair or shorthand ("WF-5220/5320",
"PD9140/45A"), a number broken over a line ending in "-", or a continuation line that has text
in the WFCO column.
"""
from __future__ import annotations

import json
import re
import sys

import pdfplumber
import pymupdf

PAGE = 2


def _words_pymupdf(path):
    p = pymupdf.open(path)[PAGE - 1]
    return [(w[0], w[1], w[2], w[3], w[4]) for w in p.get_text("words")], p.rect.width


def _words_plumber(path):
    with pdfplumber.open(path) as pdf:
        p = pdf.pages[PAGE - 1]
        ws = p.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
        return [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in ws], float(p.width)


def _tables(words, width):
    heads = []
    for h in words:
        if h[4] != "WFCO":
            continue
        brand = [w for w in words if abs(w[3] - h[3]) < 1.5 and h[2] + 20 < w[0] < h[2] + 120 and w[4] != "WFCO"]
        if brand:
            heads.append({"x": h[0], "y": h[3], "brand_x": min(w[0] for w in brand),
                          "brand": " ".join(w[4] for w in sorted(brand, key=lambda w: w[0]))})
    heads.sort(key=lambda h: (round(h["x"] / 20), h["y"]))
    col_x = sorted({round(h["x"] / 20) for h in heads})
    xs = sorted({min(h["x"] for h in heads if round(h["x"] / 20) == c) for c in col_x})
    out = []
    for h in heads:
        right = min([x for x in xs if x > h["x"] + 30] + [width])
        below = [g["y"] for g in heads if abs(g["x"] - h["x"]) < 15 and g["y"] > h["y"]]
        bottom = min(below) - 25 if below else 730
        lines: dict[int, list] = {}
        for w in words:
            if h["x"] - 3 <= w[0] < right - 3 and h["y"] + 2 < w[3] < bottom:
                lines.setdefault(round(w[3]), []).append(w)
        rows = []
        for y in sorted(lines):
            ln = sorted(lines[y], key=lambda w: w[0])
            wf = " ".join(w[4] for w in ln if w[0] < h["brand_x"] - 3)
            comp = " ".join(w[4] for w in ln if w[0] >= h["brand_x"] - 3)
            if wf.startswith(("WF-", "T-", "EM-")):
                rows.append({"wfco": wf, "cell": comp, "cont": []})
            elif rows:
                rows[-1]["cont"].append({"wfco_col": wf, "text": comp})
        out.append({"brand": h["brand"], "rows": rows})
    return out


def _split(cell: str) -> list[str]:
    out = []
    for n in [n.strip() for n in cell.split(",") if n.strip()]:
        toks = n.split()
        # a wrapped list can lose its comma at the line end ("PD9180A PD9270"): split only
        # when every token is a complete PD-style number (spaced model names stay whole)
        if len(toks) > 1 and all(re.match(r"^PD\d{3,}[A-Z]*$", t) for t in toks):
            out += toks
        else:
            out.append(n)
    return out


def _finish(t):
    """Rows -> numbers.  Numbers on the first line of a cell are kept; a continuation line is
    only used when it sits wholly in the competitor column and the line above does not end in a
    broken number ("-").  Otherwise the continuation is reported as held text."""
    res = []
    for r in t["rows"]:
        row_hold = f"WFCO number is a model pair / shorthand: {r['wfco']}" if "/" in r["wfco"] else None
        cell, held_text = r["cell"], []
        for c in r["cont"]:
            if c["wfco_col"] or cell.rstrip().endswith("-") or held_text:
                held_text.append((c["wfco_col"] + " | " + c["text"]).strip(" |"))
            else:
                cell = (cell + " " + c["text"]).strip()
        nums = []
        for n in _split(cell):
            hold = row_hold
            if "/" in n:
                hold = hold or f"competitor number shorthand: {n}"
            if n.endswith("-"):
                hold = hold or f"number broken over a line: {n}"
            nums.append({"number": n, "hold": hold})
        res.append({"brand": t["brand"], "wfco": r["wfco"], "cell": cell, "numbers": nums,
                    "held_continuation": held_text})
    return res


def read(path: str) -> dict:
    a = [_finish(t) for t in _tables(*_words_plumber(path))]
    b = [_finish(t) for t in _tables(*_words_pymupdf(path))]
    if a != b:
        diffs = [(x, y) for ta, tb in zip(a, b) for x, y in zip(ta, tb) if x != y]
        raise SystemExit(f"passes disagree ({len(a)} vs {len(b)} tables): {diffs[:4]}")
    return {"page": PAGE, "tables": len(a), "rows": [r for t in a for r in t]}


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1]), indent=1))
