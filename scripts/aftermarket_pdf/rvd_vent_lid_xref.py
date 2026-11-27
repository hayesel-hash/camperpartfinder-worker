"""RV Designer "Vent Lid Cross Reference" (one landscape page, 2020).

Table: RVD | Hinge Type | Description | CAMCO | HENGS | VENTLINE (blank cells allowed).
Pass A: poppler `pdftotext -layout` (regex: RVD number, hinge, description, then 1-3 numbers;
the VENTLINE number is recognised by its x position in pass B and by being the third number
in pass A).  Pass B: pymupdf word boxes cut by the header x positions.  Rows must agree.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pymupdf

BRANDS = ("CAMCO", "HENGS", "VENTLINE")


def pass_a(path: str) -> list[dict]:
    txt = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout
    rows = []
    for line in txt.splitlines():
        m = re.match(r"^\s*(V\d{3})\s+(#\d)\s+(.+?)\s{2,}(\d{5})\s+(\S+)(?:\s+(\S+))?\s*$", line)
        if m:
            rows.append({"rvd": m.group(1), "hinge": m.group(2), "description": m.group(3).strip(),
                         "CAMCO": m.group(4), "HENGS": m.group(5), "VENTLINE": m.group(6) or ""})
    return rows


def pass_b(path: str) -> list[dict]:
    page = pymupdf.open(path)[0]
    words = page.get_text("words")
    rvd_head = next(w for w in words if w[4] == "RVD")
    head = {w[4]: (w[0], w[2]) for w in words
            if w[4] in ("RVD", "Hinge", "Description") + BRANDS and abs(w[3] - rvd_head[3]) < 2}
    # column cuts: midway between header boxes
    cuts = {"rvd": (0, head["Hinge"][0] - 5), "hinge": (head["Hinge"][0] - 5, 180),
            "description": (180, head["CAMCO"][0] - 5), "CAMCO": (head["CAMCO"][0] - 5, head["HENGS"][0] - 5),
            "HENGS": (head["HENGS"][0] - 5, head["VENTLINE"][0] - 5), "VENTLINE": (head["VENTLINE"][0] - 5, 800)}
    lines: dict[int, list] = {}
    for w in words:
        lines.setdefault(round(w[3]), []).append(w)
    rows = []
    for y in sorted(lines):
        ln = sorted(lines[y], key=lambda w: w[0])
        if not re.match(r"^V\d{3}$", ln[0][4]):
            continue
        row = {k: " ".join(w[4] for w in ln if a <= (w[0] + w[2]) / 2 < b) for k, (a, b) in cuts.items()}
        rows.append(row)
    return rows


def read(path: str) -> dict:
    a, b = pass_a(path), pass_b(path)
    if a != b:
        raise SystemExit(f"passes disagree: {a} vs {b}")
    return {"rows": a}


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1]), indent=1))
