"""Dometic "Replacement Chart" for RV refrigerators (catalogue page 1-19.0, 2014).

Layout: one page, four sections "REPLACING A[N] <BRAND> WITH A DOMETIC", each row
    Model # | Height | Width | Depth | Dometic Replacement Options | Height | Width | Depth
with continuation rows (blank model cell) that add a further Dometic option for the model
above.  Footnotes: "*RM3962 approximately 3 inches higher ..." and "**RM2652 = DM2652 ...".

Two independent passes:
  pass A  poppler `pdftotext -layout` lines (regex over the laid-out text)
  pass B  pymupdf word boxes, grouped by baseline and cut into the eight columns by x
Only rows on which both passes agree are returned.

Output rows are model-for-model statements: Dometic (the publisher) names its refrigerator
model as a replacement option for the other maker's model.  Dimensions travel with every
row because the cabinets differ (cut-out check).  Nothing here infers a match: the options
cell is split on commas; a bare number after a prefixed one ("RM2351, 2354") takes the
prefix and keeps `printed_as`; an original-model cell with a shorthand second model
("1200LR/LAIM") and an option row with no model printed are reported as held.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

import pymupdf

SECTION_RE = re.compile(r"^REPLACING AN? (.+?) WITH A DOMETIC$")
DIM = r"\d{1,2}(?: \d{1,2}/\d{1,2})?"
# pass A row: model cell, three dims, options cell, three dims
ROW_A = re.compile(
    rf"^(?P<model>\S.*?)\s+(?P<h>{DIM})\s+(?P<w>{DIM})\s+(?P<d>{DIM})\s+(?P<opt>.*?)\s+(?P<h2>{DIM})\s+(?P<w2>{DIM})\s+(?P<d2>{DIM})\s*$"
)
CONT_A = re.compile(rf"^\s+(?P<opt>\S.*?)\s+(?P<h2>{DIM})\s+(?P<w2>{DIM})\s+(?P<d2>{DIM})\s*$")
BRANDS = {"NORCOLD": "Norcold", "INSTAMATIC": "Instamatic", "SIBIR": "Sibir", "GE": "GE"}

# pass B column cuts (PDF points, page width 603)
COLS = [("model", 0, 110), ("h", 110, 155), ("w", 155, 200), ("d", 200, 262),
        ("opt", 262, 420), ("h2", 420, 462), ("w2", 462, 510), ("d2", 510, 603)]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\t", " ")).strip()


def pass_a(path: str) -> list[dict]:
    out = subprocess.run(["pdftotext", "-layout", path, "-"], check=True, capture_output=True, text=True).stdout
    rows, brand = [], None
    for raw in out.splitlines():
        line = raw.replace("\t", " ")
        s = _norm(line)
        m = SECTION_RE.match(s)
        if m:
            brand = BRANDS[m.group(1)]
            continue
        if brand is None or not s or s.startswith(("Model #", "*", "RM3662", "DD ")):
            continue
        m = ROW_A.match(s)
        if m and not line.startswith(" "):
            rows.append({"brand": brand, **{k: _norm(v) for k, v in m.groupdict().items()}})
            continue
        m = CONT_A.match(line)
        if m:
            rows.append({"brand": brand, "model": "", "h": "", "w": "", "d": "", **{k: _norm(v) for k, v in m.groupdict().items()}})
            continue
        # a line with model + dims but no options cell (N841/N841.3 first line)
        m = re.match(rf"^(?P<model>\S+)\s+(?P<h>{DIM})\s+(?P<w>{DIM})\s+(?P<d>{DIM})\s+(?P<h2>{DIM})\s+(?P<w2>{DIM})\s+(?P<d2>{DIM})$", s)
        if m:
            rows.append({"brand": brand, "opt": "", **{k: _norm(v) for k, v in m.groupdict().items()}})
            continue
        raise ValueError(f"pass A: unread line {s!r}")
    return rows


def pass_b(path: str) -> list[dict]:
    page = pymupdf.open(path)[0]
    words = sorted(page.get_text("words"), key=lambda w: (round(w[3]), w[0]))
    lines: list[list] = []
    for w in words:
        if lines and abs(lines[-1][0][3] - w[3]) < 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    rows, brand = [], None
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        text = " ".join(w[4] for w in ln)
        m = SECTION_RE.match(text)
        if m:
            brand = BRANDS[m.group(1)]
            continue
        if brand is None or text.startswith(("Model #", "*", "RM3662", "DD ")):
            continue
        cells = {k: [] for k, _, _ in COLS}
        for w in ln:
            cx = (w[0] + w[2]) / 2
            for k, x0, x1 in COLS:
                if x0 <= cx < x1:
                    cells[k].append(w[4])
                    break
        # long model lists ("462, 463, 662, 663, 641") run past the model column: a model
        # cell ending in a comma continues into the next cell
        while cells["model"] and cells["model"][-1].endswith(",") and cells["h"]:
            cells["model"].append(cells["h"].pop(0))
        row = {k: " ".join(v) for k, v in cells.items()}
        if not any(row.values()):
            continue
        rows.append({"brand": brand, **row})
    return rows


def split_models(cell: str) -> tuple[list[str], str | None]:
    """Original-model cell -> models.  'N260/N260.3' -> both (each printed in full)."""
    out = []
    for tok in [t.strip() for t in cell.split(",") if t.strip()]:
        if "/" in tok:
            a, b = tok.split("/", 1)
            if re.match(r"^[A-Z]+", b) and b[:1] == a[:1]:
                out += [a, b]
            else:
                return [], f"shorthand second model in {tok!r} not expanded"
        else:
            out.append(tok)
    return out, None


def split_options(cell: str, printed_in_full: set[str]) -> list[dict]:
    """Options cell -> Dometic models.  A bare number takes the prefix of the number before
    it only when that full model is printed somewhere on the page (e.g. "RM2351, 2354" ->
    RM2354, printed in full in the N300 row); otherwise the option is returned held."""
    opts, prefix = [], ""
    cell = cell.replace(",**", "**,")  # "2862,** RM3962*": the marks belong to 2862
    for tok in [t.strip() for t in cell.split(",") if t.strip()]:
        marks = "".join(ch for ch in tok if ch == "*")
        num = tok.replace("*", "").strip()
        printed = tok
        m = re.match(r"^([A-Z]+)\d", num)
        if m:
            prefix = m.group(1)
            full = num
        else:
            full = prefix + num
            if full not in printed_in_full:
                opts.append({"number": None, "printed_as": printed, "marks": marks,
                             "hold": f"bare {num!r}: {full} is not printed in full on the page"})
                continue
        opts.append({"number": full, "printed_as": printed, "marks": marks})
    return opts


FOOT_1 = "*RM3962 approximately 3 inches higher than 2852, 2862."
FOOT_2 = ("**RM2652 = DM2652, RM2662 = DM2662, RM2663 = DM2663, RM2852 = DM2852, RM2862 = DM2862, "
          "RM3662 = DM3662, RM3663 = DISCONTINUED, RM3862 = DM3862, RM3863 = DISCONTINUED, NDR1062 = NDM1062")


def read(path: str) -> dict:
    a, b = pass_a(path), pass_b(path)
    printed_in_full = set(re.findall(r"\b[A-Z]{2,3}\d{3,4}\b", pymupdf.open(path)[0].get_text()))
    if a != b:
        diffs = [(x, y) for x, y in zip(a, b) if x != y]
        raise SystemExit(f"passes disagree: {len(a)} vs {len(b)} rows; first diffs {diffs[:3]}")
    pairs, held, current = [], [], None
    for r in a:
        if r["model"]:
            current = r
        orig = current
        models, why = split_models(orig["model"])
        dims_o = {"height": orig["h"], "width": orig["w"], "depth": orig["d"]}
        dims_r = {"height": r["h2"], "width": r["w2"], "depth": r["d2"]}
        if why:
            held.append({"brand": orig["brand"], "model_cell": orig["model"], "options": r["opt"], "reason": why})
            continue
        if not r["opt"]:
            held.append({"brand": orig["brand"], "model_cell": orig["model"], "options": "", "reason":
                         f"replacement row with dimensions {dims_r} but no Dometic model printed"})
            continue
        for o in split_options(r["opt"], printed_in_full):
            if o["number"] is None:
                held.append({"brand": orig["brand"], "model_cell": orig["model"], "options": r["opt"], "reason": o["hold"]})
                continue
            for mdl in models:
                notes = []
                if "**" in o["marks"]:
                    notes.append(FOOT_2)
                elif "*" in o["marks"]:
                    notes.append(FOOT_1)
                pairs.append({
                    "oem_brand": orig["brand"], "oem_model": mdl, "dometic_model": o["number"],
                    "printed_as": o["printed_as"], "original_dimensions_in": dims_o,
                    "replacement_dimensions_in": dims_r, "footnotes": notes,
                    "row_text": f"REPLACING A{'N' if orig['brand'][0] in 'AEIOU' else ''} {orig['brand'].upper()} WITH A DOMETIC: "
                                f"{orig['model']} ({orig['h']} x {orig['w']} x {orig['d']}) -> {r['opt']} "
                                f"({r['h2']} x {r['w2']} x {r['d2']})",
                })
    return {"rows_read": len(a), "pairs": pairs, "held": held}


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1]), indent=1))
