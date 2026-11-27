"""SKF heavy-duty catalogue "Competitor & manufacturer interchange" pages.

Three columns per page, each "Mfr no. | Mfr. | Part no." with a dotted leader between the
maker name and the SKF part number ("010-051-00 Dexter ........ 28758").  Part numbers may
carry a marker ("•", "**", "+") whose legend is not on these pages: such rows are returned
with `marker` set and are held by the caller.  Application tables (axle maker / line number
-> seal, bearing cone/cup) are fitment and are not read here.

Pass A: poppler `pdftotext -layout` lines, regex over every "<no> <maker> ....<part>" chunk.
Pass B: pymupdf words; the three columns cut at the "Mfr no." header x positions, words
joined per baseline, then the same split on the dotted leader.  Rows must agree.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pymupdf

ROW = re.compile(r"(?P<no>\S+) (?P<mfr>[A-Za-z][^.]*?) ?\.{3,} ?(?P<part>\d[\d]*)(?P<mark>\*\*|•|\+)?(?=\s|$)")


def _rows_from_text(s: str) -> list[dict]:
    out = []
    for m in ROW.finditer(s):
        out.append({"mfr_no": m.group("no"), "mfr": m.group("mfr").strip(), "skf_part": m.group("part"),
                    "marker": m.group("mark") or ""})
    return out


def pass_a(path: str, page: int) -> list[dict]:
    txt = subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), path, "-"],
                         capture_output=True, text=True, check=True).stdout
    rows = []
    for line in txt.splitlines():
        rows += _rows_from_text(re.sub(r"\s+", " ", line))
    return rows


def pass_b(path: str, page: int) -> list[dict]:
    p = pymupdf.open(path)[page - 1]
    words = p.get_text("words")
    heads = sorted(w[0] for w in words if w[4] == "Mfr" and words[words.index(w) + 1][4] == "no.")
    cuts = heads + [p.rect.width - 20]
    rows = []
    for c0, c1 in zip(cuts, cuts[1:]):
        col = [w for w in words if c0 - 3 <= w[0] < c1 - 3]
        lines: dict[int, list] = {}
        for w in col:
            lines.setdefault(round(w[3]), []).append(w)
        for y in sorted(lines):
            s = " ".join(w[4] for w in sorted(lines[y], key=lambda w: w[0]))
            rows += _rows_from_text(s)
    return rows


def read(path: str, page: int) -> dict:
    a, b = pass_a(path, page), pass_b(path, page)
    ka = sorted((r["mfr_no"], r["mfr"], r["skf_part"], r["marker"]) for r in a)
    kb = sorted((r["mfr_no"], r["mfr"], r["skf_part"], r["marker"]) for r in b)
    return {"page": page, "rows_a": len(a), "rows_b": len(b), "agree": ka == kb,
            "only_a": sorted(set(ka) - set(kb)), "only_b": sorted(set(kb) - set(ka)),
            "rows": [dict(zip(("mfr_no", "mfr", "skf_part", "marker"), k)) for k in sorted(set(ka) & set(kb))]}


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1], int(sys.argv[2])), indent=1))
