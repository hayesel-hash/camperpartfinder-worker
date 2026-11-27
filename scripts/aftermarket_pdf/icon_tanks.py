"""Two-pass reader for ICON Technologies RV parts catalogue tank pages:
"<ICON no.> Replaces <RV brand> <number>[, <number>]" lines under a tank heading
("WT3545 Fresh Water Tank", "Center End Drain H3554", ...) and its size/capacity line.

Pass A: page text lines in reading order. Pass B: word boxes only (column by x, row by
baseline), rebuilt without the PDF's block/line structure. Both must give the same rows.

Only rows that name a brand are staged; a number printed with no brand ("15924 Replaces
2047644") or a misspelt brand is returned with a hold reason, never guessed.

usage: python3 -I icon_tanks.py <split.pdf> <first_full_page> <out.json>
"""
import hashlib, json, re, sys

ROW = re.compile(r"^(\d{5})\s+Replaces\s+(.*\S)\s*$")
HEAD = re.compile(r"(Fresh Water Tank|Drain\b)")
DIMS = re.compile(r"US Gallon")
SECTIONS = ("FRESH WATER TANKS", "HOLDING TANKS")
# brands exactly as ICON prints them -> manufacturer name used in the database
BRANDS = {
    "Jayco Entegra": "Jayco", "Braxton Creek": "Braxton Creek", "Elkhart Plastics": "Elkhart Plastics",
    "Forest River": "Forest River", "Triple E": "Triple E", "Ameri-Kart": "Ameri-Kart",
    "StarCraft": "Starcraft", "Coachmen": "Coachmen", "Jayco": "Jayco",
}
MISSPELT = {"Forerst River"}
OEMNUM = re.compile(r"^#?([A-Za-z0-9][A-Za-z0-9-]*[A-Za-z0-9]|[0-9]+)$")


def split_rest(rest):
    """-> (printed_brand, brand, [numbers], hold_reason)"""
    for b in sorted(list(BRANDS) + list(MISSPELT), key=len, reverse=True):
        if rest == b or rest.startswith(b + " "):
            nums = [n.strip() for n in rest[len(b):].split(",")]
            if any(not OEMNUM.match(n) for n in nums):
                return b, None, nums, "number not in a recognised form"
            nums = [OEMNUM.match(n).group(1) for n in nums]
            if b in MISSPELT:
                return b, None, nums, "brand misspelt on the page (%s); not corrected" % b
            return b, BRANDS[b], nums, None
    first = rest.split()[0]
    if re.match(r"^#?\d", first):
        return None, None, [n.strip() for n in rest.split(",")], "no brand named on the page"
    return None, None, [rest], "brand not recognised: " + rest


def rows_from_lines(lines):
    """lines: list of text lines in reading order for one column/page -> rows"""
    out, head, dims, section = [], None, None, None
    for l in lines:
        l = " ".join(l.split())
        if not l:
            continue
        if l in SECTIONS:
            section = l
            continue
        m = ROW.match(l)
        if m:
            out.append({"icon": m.group(1), "rest": m.group(2), "heading": head, "dims": dims, "line": l})
            continue
        if DIMS.search(l):
            dims = l
            continue
        if HEAD.search(l) and not re.match(r"^\d{5}\s", l):
            head, dims = l, None
    return out, section


def pass_a(lines):
    rows, _ = rows_from_lines(lines)
    return rows


def pass_b(words, width):
    """words: (x0, y0, x1, y1, word, ...) boxes. Columns split at mid-page; the side label
    strips on either page edge (x0 > 0.9 * width, or x1 < 0.065 * width: the rotated
    "HOLDING TANKS" label) are ignored. Rows are words sharing a baseline (±2 pt)."""
    cols = {0: [], 1: []}
    for w in words:
        x0, x1, y1, t = w[0], w[2], w[3], w[4]
        if x0 > 0.9 * width or x1 < 0.065 * width:
            continue
        cols[0 if x0 < width / 2 else 1].append((y1, x0, t))
    out = []
    for c in (0, 1):
        ws = sorted(cols[c])
        lines, cur, cy = [], [], None
        for y, x, t in ws:
            if cy is not None and abs(y - cy) > 2:
                lines.append(" ".join(t for _, t in sorted(cur)))
                cur = []
            if not cur:
                cy = y
            cur.append((x, t))
        if cur:
            lines.append(" ".join(t for _, t in sorted(cur)))
        out += rows_from_lines(lines)[0]
    return out


def section_of(lines):
    for l in lines:
        if " ".join(l.split()) in SECTIONS:
            return " ".join(l.split())
    return None


def read(pages, first_full_page=1):
    """pages: list of (lines, words, width). Returns (assertions, diffs)."""
    res, diffs = [], []
    for i, (lines, words, width) in enumerate(pages):
        a = pass_a(lines)
        b = pass_b(words, width)
        key = lambda r: (r["icon"], r["rest"], r["heading"])
        ka, kb = sorted(map(key, a)), sorted(map(key, b))
        if ka != kb:
            diffs.append({"page": i + 1, "only_a": [x for x in ka if x not in kb], "only_b": [x for x in kb if x not in ka]})
        if not a:
            continue
        full = first_full_page + i
        nums = [" ".join(l.split()) for l in lines if re.match(r"^\s*\d{1,3}\s*$", l)]
        printed = str(full - 3) if str(full - 3) in nums else None
        sec = section_of(lines)
        for r in a:
            pb, brand, oems, hold = split_rest(r["rest"])
            for n in oems:
                h = hold
                if not h and r["heading"] and n.upper() in r["heading"].upper().split():
                    h = "OEM number printed is the same as ICON's tank model code in the heading; possible misprint"
                res.append({"page": i + 1, "full_page": full, "printed_page": printed, "section": sec,
                            "icon": r["icon"], "printed_brand": pb, "brand": brand, "oem_number": n,
                            "heading": r["heading"], "dims": r["dims"], "line": r["line"], "hold": h})
    return res, diffs


def load(pdf):
    import pymupdf
    d = pymupdf.open(pdf)
    return [(p.get_text().splitlines(), p.get_text("words"), p.rect.width) for p in d]


def main(pdf, first, outp):
    raw = open(pdf, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    rows, diffs = read(load(pdf), int(first))
    json.dump({"sha256": sha, "agree": not diffs, "diffs": diffs, "rows": rows}, open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "agree": not diffs, "rows": len(rows),
                      "held": sum(1 for r in rows if r["hold"]), "pages": sorted({r["page"] for r in rows}),
                      "diffs": diffs[:3]}, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
