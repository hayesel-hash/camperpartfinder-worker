"""Two-pass reader for the MORryde "RUBBER PIN BOX FIT CHART" (MORryde Aftermarket Product Catalogue 2021 v7b, printed
p16) and the "LIPPERT RHINO | MORryde PART #" box on printed p15.

The fit chart is a ruled table: "Cross Reference Guide" MFG | MODEL# (the stock pin box) | four MORryde part-number
columns, one per trailer GVWR band ("Order according to GVWR of the trailer, not the GVW of the pin box.*") | MORryde
Pin Box Rating. Below it MORryde asks for the "Part Number of the stock pin box" to order a replacement pin box system,
and p15 says the Rubber Pin Box is "designed to directly replace the Lippert Rhino Pin Box". So each (stock pin box,
MORryde part) pair is a MORryde statement that its rubber pin box replaces that pin box, for trailers in that GVWR band.

Pass A: pymupdf find_tables(); pass B: pdfplumber extract_tables() (two independent table finders). Only cells both
passes read identically are used.

What is staged and what is held (never guessed):
- "N/A" cells: no MORryde part for that band, skipped.
- MODEL# cells holding a comma list of plain numbers ("7920, 7921", "300,314,316") are split; every model gets the row's
  MORryde parts. A list whose items are not all numbers ("1621, SHD-TA": one model or two?) is held.
- MODEL# cells with no digit (Rhino, Med, Long, Medium, Short) are named sizes / product names, not numbered parts:
  held. "45 degree" is held the same way.
- Brands whose alias in the DB was set for a different product line are held by the caller (see STAGING_HOLDS).

usage: python3 -I morryde_pin_box_chart.py <pdf> <out.json>
"""
import hashlib
import json
import re
import sys

import pdfplumber
import pymupdf

MOR = re.compile(r"^(?:RPB7\d|SEITZL)[A-Z0-9-]{3,30}$")
BANDS_HDR = re.compile(r"^(11,500 or less|11,501 - 14,000|14,001 - 18,000|18,001 & over)$")
PLAIN_NUM = re.compile(r"^[0-9][0-9A-Z-]*$")


def norm(c):
    return " ".join((c or "").split())


def split_models(cell):
    """Return (models, hold_reason)."""
    cell = norm(cell)
    if not re.search(r"\d", cell):
        return [], f"stock pin box named by size / product name, no part number: {cell}"
    if "," in cell:
        items = [x.strip() for x in cell.split(",") if x.strip()]
        if all(PLAIN_NUM.match(x) for x in items):
            return items, None
        return [], f"model cell is a list that is not all part numbers (one model or several?): {cell}"
    if " " in cell:
        return [], f"model cell is not a part number: {cell}"
    return [cell], None


def chart_rows(table):
    """table: rows of cell text. Returns list of dicts (one per printed data row) or [] if this is not the chart."""
    hdr_i = None
    for k, r in enumerate(table):
        cells = [norm(c) for c in r]
        if cells[:2] == ["MFG", "MODEL#"] and sum(bool(BANDS_HDR.match(c)) for c in cells) == 4:
            hdr_i = k
            break
    if hdr_i is None:
        return []
    hdr = [norm(c) for c in table[hdr_i]]
    band_cols = [(k, c) for k, c in enumerate(hdr) if BANDS_HDR.match(c)]
    rating_col = len(hdr) - 1
    out = []
    for r in table[hdr_i + 1:]:
        cells = [norm(c) for c in r]
        if len(cells) != len(hdr) or not cells[0]:
            continue
        out.append({"mfg": cells[0], "model_cell": cells[1],
                    "parts": {band: cells[k] for k, band in band_cols},
                    "rating": cells[rating_col]})
    return out


def pairs(rows, page, printed_page):
    staged, held, unread = [], [], []
    for r in rows:
        models, why = split_models(r["model_cell"])
        for band, num in r["parts"].items():
            if not num or num.upper() == "N/A":
                continue
            if not MOR.match(num.replace(" ", "")):
                unread.append({"page": page, "cell": num, "row": r})
                continue
            base = {"page": page, "printed_page": printed_page, "mfg": r["mfg"], "model_cell": r["model_cell"],
                    "morryde_number": num.replace(" ", ""), "gvwr_band": band, "rating": r["rating"]}
            if why:
                held.append({**base, "hold_reason": why})
                continue
            for m in models:
                staged.append({**base, "oem_number": m})
    return staged, held, unread


def rhino_box(page_text):
    """Printed p15 box: 'LIPPERT RHINO | MORryde PART #' with GVWR lines. Returns rows (all held: no number)."""
    out = []
    for m in re.finditer(r"(\d[\d,]*-[\d,]+ GVWR|[\d,]+ \+ GVWR)\s*\n\s*(RPB77-RHINO-0\d)", page_text):
        out.append({"gvwr": m.group(1), "morryde_number": m.group(2)})
    return out


def main(pdf, outp):
    raw = open(pdf, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    pl = pdfplumber.open(pdf)
    result = {"sha256": sha, "pages": d.page_count, "staged": [], "held": [], "unread": [], "diffs": [], "rhino": []}
    for i, p in enumerate(d):
        a_tables = [t.extract() for t in p.find_tables().tables]
        a = [row for t in a_tables for row in chart_rows(t)]
        if not a:
            rh = rhino_box(p.get_text())
            if rh and "directly replace the Lippert Rhino Pin Box" in " ".join(p.get_text().split()):
                result["rhino"] += [{**x, "page": i + 1} for x in rh]
            continue
        b = [row for t in pl.pages[i].extract_tables() for row in chart_rows(t)]
        key = lambda r: json.dumps(r, sort_keys=True)
        ka, kb = {key(r) for r in a}, {key(r) for r in b}
        agreed = [r for r in a if key(r) in kb]
        result["diffs"] += [{"page": i + 1, "only_a": json.loads(x)} for x in ka - kb]
        result["diffs"] += [{"page": i + 1, "only_b": json.loads(x)} for x in kb - ka]
        m = re.search(r"\n(\d{1,3})\n", "\n" + p.get_text())
        printed = None
        for line in p.get_text().splitlines()[::-1]:
            if re.fullmatch(r"\d{1,3}", line.strip()):
                printed = line.strip()
                break
        s, h, u = pairs(agreed, i + 1, printed)
        result["staged"] += s
        result["held"] += h
        result["unread"] += u
        result["rows_a"], result["rows_b"], result["rows_agreed"] = len(a), len(b), len(agreed)
    json.dump(result, open(outp, "w"), indent=1)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
