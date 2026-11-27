"""Progressive Dynamics "RV Converter Crossover List" (one page, two side-by-side tables).

Each table: Progressive Dynamics Part Number | Replaces, with section rows (Deck Mount,
Wall Mount - 30 Amp Service, Wall Mount - 50 Amp Service, Replacement Sections) and the PD
number in a merged cell spanning several "Replaces" rows.  A row may carry
"(w/PD9105V charge wizard added)"; a PD cell may carry "(*20 AMP PLUG)" and "*This unit does
not have Power Factor Correction".  Page footnote: "*Not all units are a direct
replacement. Modifications may be required.*"

Pass B (structure): the ruled lines.  A horizontal rule across the PD column closes a PD
group; rules across the Replaces column close a Replaces cell.  Words go to cells by centre.
Pass A (check): pymupdf text blocks.  The multiset of Replaces cell texts and of PD cell
texts must equal pass B's, so no cell is lost or merged; group membership was checked
against the page image.
"""
from __future__ import annotations

import collections
import json
import re
import sys

import pymupdf

SIDES = [  # (pd x0, pd x1, replaces x1)
    (27, 119, 291),
    (303, 395, 567),
]
SECTIONS = ("Deck Mount", "Wall Mount - 30 Amp Service", "Wall Mount - 50 Amp Service", "Replacement Sections")
FOOTNOTE = "*Not all units are a direct replacement. Modifications may be required.*"
WIZARD = "(w/PD9105V charge wizard added)"


def _rules(page) -> list[tuple[float, float, float]]:
    out = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.6:
                out.append((min(it[1].x, it[2].x), max(it[1].x, it[2].x), it[1].y))
            elif it[0] == "re" and it[1].height < 1.2:
                out.append((it[1].x0, it[1].x1, it[1].y0))
    return out


def _bands(rules, x0, x1) -> list[float]:
    ys = sorted({round(y, 1) for a, b, y in rules if a <= x0 + 2 and b >= x1 - 2 and b - a < 300})
    return ys


def _text(words, x0, x1, y0, y1) -> str:
    ws = [w for w in words if x0 <= (w[0] + w[2]) / 2 < x1 and y0 <= (w[1] + w[3]) / 2 < y1]
    lines = collections.OrderedDict()
    for w in sorted(ws, key=lambda w: (round(w[3]), w[0])):
        lines.setdefault(round(w[3]), []).append(w[4])
    return "\n".join(" ".join(v) for v in lines.values())


def pass_b(page) -> list[dict]:
    rules, words = _rules(page), page.get_text("words")
    groups = []
    for px0, px1, rx1 in SIDES:
        g_ys = _bands(rules, px0, px1)
        r_ys = _bands(rules, px1, rx1)
        section = None
        for gy0, gy1 in zip(g_ys, g_ys[1:]):
            pd = _text(words, px0, px1, gy0, gy1)
            cells = [t for ry0, ry1 in zip(r_ys, r_ys[1:]) if ry0 >= gy0 - 0.5 and ry1 <= gy1 + 0.5
                     for t in [_text(words, px1, rx1, ry0, ry1)] if t]
            whole = _text(words, px0, rx1, gy0, gy1)
            if whole in SECTIONS:
                section = whole
                continue
            if pd.startswith("Progressive Dynamics"):
                continue
            groups.append({"side": "left" if px0 < 200 else "right", "section": section, "pd_cell": pd,
                           "replaces": cells, "y": round(gy0, 1)})
    return groups


def pass_a_lines(page, y0: float, y1: float) -> tuple[collections.Counter, collections.Counter]:
    """Text-layer lines (pymupdf dict spans, joined per line and column) inside the table."""
    pd, rep = collections.Counter(), collections.Counter()
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for px0, px1, rx1 in SIDES:
                for col, (a, z) in (("pd", (px0, px1)), ("rep", (px1, rx1))):
                    spans = [s for s in ln["spans"] if a <= (s["bbox"][0] + s["bbox"][2]) / 2 < z
                             and y0 < (s["bbox"][1] + s["bbox"][3]) / 2 < y1 and s["text"].strip()]
                    if spans:
                        t = re.sub(r"\s+", " ", " ".join(s["text"] for s in spans)).strip()
                        (pd if col == "pd" else rep)[t] += 1
    return pd, rep


def parse_group(g: dict) -> dict:
    lines = g["pd_cell"].split("\n")
    number = lines[0].strip()
    notes = " ".join(l.strip() for l in lines[1:])
    out = []
    for cell in g["replaces"]:
        c = " ".join(cell.split("\n"))
        wizard = WIZARD in c
        c = c.replace(WIZARD, "").strip()
        m = re.match(r"^(Parallax|Iota|WFCO|Powermax)\s+(\S+)$", c)
        out.append({"cell": cell, "brand": m.group(1) if m else None, "number": m.group(2) if m else None,
                    "requires_pd9105v_charge_wizard": wizard})
    return {**g, "pd_number": number, "pd_notes": notes, "rows": out}


def read(path: str) -> dict:
    page = pymupdf.open(path)[0]
    groups = pass_b(page)
    ys = [g["y"] for g in groups]
    pd_a, rep_a = pass_a_lines(page, 111.0, 700.0)
    for h in ("Progressive Dynamics", "Part Number", "Replaces") + SECTIONS:
        pd_a.pop(h, None); rep_a.pop(h, None)
    norm = lambda t: re.sub(r"\s+", " ", t).strip()
    pd_b = collections.Counter(norm(l) for g in groups for l in g["pd_cell"].split("\n") if l.strip())
    rep_b = collections.Counter(norm(l) for g in groups for c in g["replaces"] for l in c.split("\n"))
    for k in list(pd_a):
        if k == "*" or k.startswith(("*Not all", "Please contact")):
            del pd_a[k]
    for k in list(rep_a):
        if k.startswith(("*Not all", "Not all units", "Please contact", "replacement. Mod", "department with")):
            del rep_a[k]
    if pd_a != pd_b or rep_a != rep_b:
        raise SystemExit(f"passes disagree: pd {pd_a - pd_b} / {pd_b - pd_a}; replaces {rep_a - rep_b} / {rep_b - rep_a}")
    if FOOTNOTE not in page.get_text().replace("\n", " "):
        raise SystemExit("footnote not found")
    return {"footnote": FOOTNOTE, "groups": [parse_group(g) for g in groups]}


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1]), indent=1))
