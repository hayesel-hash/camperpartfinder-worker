"""Advent Air "Coleman to Advent Compatibility Chart" (CCADVCOL-001, 08/12/2011).

Table: Coleman KIT# | Description | Advent Compatibility | Reason, two pages, with the
heading statement "AC135, AC150, ACM135 & ACM150 compatibility achieved with use of Advent
adaptor kit ACCOLKIT." and NOTE 1 / NOTE 2 under the table.

The chart says which Coleman ceiling assemblies (control kits) an Advent upper unit can be
used with through the ACCOLKIT adaptor.  It names no Coleman part that the Advent unit
replaces, so rows are compatibility (relation `fits_model`), never interchangeability.

Pass A: pymupdf plain text (one cell per line, Reason lines follow the compatibility cell).
Pass B: poppler `pdftotext -layout` lines (columns by regex).  Rows must agree.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pymupdf

KIT = re.compile(r"^\d{4}(?:-|[A-C])\d{3,4}$")
COMPAT = ("Yes, with ACCOLKIT", "Unknown", "No")


def pass_a(path: str) -> list[dict]:
    rows = []
    for pno, page in enumerate(pymupdf.open(path), 1):
        lines = [l.strip() for l in page.get_text().splitlines() if l.strip()]
        i = 0
        while i < len(lines):
            if KIT.match(lines[i]) and i + 2 < len(lines) and lines[i + 2] in COMPAT:
                row = {"page": pno, "kit": lines[i], "description": lines[i + 1], "compat": lines[i + 2], "reason": ""}
                j = i + 3
                reason = []
                while j < len(lines) and not KIT.match(lines[j]) and not lines[j].startswith(("NOTE", "Coleman")):
                    reason.append(lines[j])
                    j += 1
                row["reason"] = " ".join(reason)
                rows.append(row)
                i = j
            else:
                i += 1
    return rows


def pass_b(path: str) -> list[dict]:
    rows, pno = [], 0
    with pymupdf.open(path) as d:
        n = d.page_count
    for pno in range(1, n + 1):
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(pno), "-l", str(pno), path, "-"],
                             capture_output=True, text=True, check=True).stdout
        for line in txt.splitlines():
            m = re.match(r"^(\d{4}(?:-|[A-C])\d{3,4})\s{2,}(.+?)\s{2,}(Yes, with ACCOLKIT|Unknown|No)(?:\s{2,}(.+))?$", line.strip())
            if m:
                rows.append({"page": pno, "kit": m.group(1), "description": m.group(2), "compat": m.group(3),
                             "reason": m.group(4) or ""})
            elif rows and rows[-1]["page"] == pno and re.match(r"^\s{40,}\S", line) and not line.strip().startswith(("NOTE", "Coleman")):
                rows[-1]["reason"] = (rows[-1]["reason"] + " " + line.strip()).strip()
    return rows


def _ws(rows: list[dict]) -> list[dict]:
    return [{k: re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v for k, v in r.items()} for r in rows]


def read(path: str) -> dict:
    a, b = _ws(pass_a(path)), _ws(pass_b(path))
    if a != b:
        diffs = [(x, y) for x, y in zip(a, b) if x != y]
        raise SystemExit(f"passes disagree: {len(a)} vs {len(b)}; {diffs[:3]}")
    text = " ".join(p.get_text() for p in pymupdf.open(path))
    heading = re.search(r"AC135, AC150, ACM135 & ACM150 compatibility achieved with use of Advent adaptor kit ACCOLKIT\.", text)
    notes = [re.sub(r"\s+", " ", m) for m in re.findall(r"NOTE \d:.*?(?=NOTE \d:|$)", re.sub(r"\s+", " ", text))]
    return {"heading": heading.group(0) if heading else None, "notes": [n.strip() for n in notes], "rows": a}


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1]), indent=1))
