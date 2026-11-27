"""Two-pass reader for Peterson Manufacturing's "COMPETITIVE INTERCHANGE" pages (pmlights.com catalogue, printed pp 136-140
in the 2025 catalogue excerpt): columns headed "GROTE...... PETERSON", "TRUCK-LITE...PETERSON", "MAXXIMA ... PETERSON",
"OPTRONICS ... PETERSON"; every entry is one line "<competitor no.><dot leader><Peterson no.>".

Pass A: pymupdf text lines (dict layer); pass B: pdfplumber words grouped by column and baseline. A line belongs to the
column whose header starts at or left of it; the column's brand comes from its header word. Rows are compared per page as
multisets of (brand, competitor no., Peterson no.); only rows both passes give are returned.

Held (returned with a reason, never published): Peterson cells naming several parts ("150-09 + 142-49"), competitor cells
with "/" shorthand ("10205R/10208R"), and any data line that does not parse as one number pair.

usage: python3 -I peterson_interchange.py <pdf> <out.json>"""
import collections, hashlib, json, re, sys
import pymupdf, pdfplumber

BRANDS = {"GROTE": "Grote", "TRUCK-LITE": "Truck-Lite", "MAXXIMA": "Maxxima", "OPTRONICS": "Optronics"}
PAIR = re.compile(r"^(\S+?)\s*\.{1,}\s*(\S.*?)\s*$")
TAB = re.compile(r"^(\S+)\s{2,}(\S+)$")
NUM = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*$", re.I)


def norm(s):
    return " ".join(s.replace(" ", " ").replace("\t", " ").split())


def headers(words):
    """words: (x0, top, text). Header words start with a brand name in capitals; returns [(x0, brand)], header bottom."""
    hs = []
    for x0, top, t in words:
        for k, v in BRANDS.items():
            if t.startswith(k) and (len(t) == len(k) or t[len(k)] in ".\t "):
                hs.append((x0, top, v))
    if not hs:
        return [], None
    ytop = min(h[1] for h in hs)
    hs = [h for h in hs if h[1] < ytop + 4]
    return sorted((round(h[0], 1), h[2]) for h in hs), ytop


def parse(line):
    t = norm(line)
    m = PAIR.match(t)
    if not m:
        m2 = TAB.match(t)
        if not m2:
            return None, "unparsed line"
        comp, pet = m2.group(1), m2.group(2)
    else:
        comp, pet = m.group(1), m.group(2).strip()
    comp = comp.rstrip(".")
    if "+" in pet or " " in pet or "," in pet:
        return (comp, pet), "Peterson cell names several parts"
    if "/" in comp:
        return (comp, pet), "competitor number with '/' shorthand"
    if not (NUM.match(comp) and NUM.match(pet)):
        return (comp, pet), "not a number pair"
    return (comp, pet), None


def column_of(x, hs):
    c = [b for hx, b in hs if hx <= x + 2]
    return c[-1] if c else None


def pass_a(page):
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"])
            if t.strip():
                lines.append((l["bbox"][0], l["bbox"][1], l["bbox"][3], t))
    hs, ytop = headers([(x, y, t.strip()) for x, y, _, t in lines])
    out, held = [], []
    if not hs:
        return out, held
    ybot = page.rect.height - 40
    for x, y, y1, t in lines:
        if y <= ytop + 4 or y1 > ybot:
            continue
        pair, why = parse(t)
        brand = column_of(x, hs)
        if why == "unparsed line":
            if re.search(r"\d", t) and not re.fullmatch(r"\s*\d{3}\s*", t):
                held.append((brand, norm(t), why))
            continue
        (held if why else out).append((brand, *pair, why) if why else (brand, *pair))
    return out, held


def pass_b(pl_page):
    ws = pl_page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
    hs, ytop = headers([(w["x0"], w["top"], w["text"]) for w in ws])
    if not hs:
        return [], []
    ybot = pl_page.height - 40
    starts = [hx for hx, _ in hs]
    groups = collections.defaultdict(list)
    for w in ws:
        if w["top"] <= ytop + 4 or w["bottom"] > ybot:
            continue
        ci = max([i for i, hx in enumerate(starts) if hx <= w["x0"] + 2], default=None)
        if ci is None:
            continue
        key = (ci, round(w["bottom"]))
        # merge baselines within 1.5 pt
        for k in list(groups):
            if k[0] == ci and abs(k[1] - w["bottom"]) <= 1.5:
                key = k; break
        groups[key].append(w)
    out, held = [], []
    for (ci, _), g in groups.items():
        t = " ".join(w["text"] for w in sorted(g, key=lambda w: w["x0"]))
        pair, why = parse(t)
        brand = hs[ci][1]
        if why == "unparsed line":
            if re.search(r"\d", t) and not re.fullmatch(r"\s*\d{3}\s*", t):
                held.append((brand, norm(t), why))
            continue
        (held if why else out).append((brand, *pair, why) if why else (brand, *pair))
    return out, held


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    rows, held, diffs = [], [], []
    for i, p in enumerate(d):
        a, ha = pass_a(p)
        b, hb = pass_b(pl.pages[i])
        ca, cb = collections.Counter(a), collections.Counter(b)
        both = ca & cb
        if ca != cb:
            diffs.append({"page": i + 1, "only_a": list((ca - cb).elements())[:20], "only_b": list((cb - ca).elements())[:20],
                          "n_only_a": sum((ca - cb).values()), "n_only_b": sum((cb - ca).values())})
        k = 0
        for r in a:
            if both[r] > 0:
                both[r] -= 1; k += 1
                rows.append({"page": i + 1, "n": k, "brand": r[0], "competitor": r[1], "peterson": r[2]})
        hset = collections.Counter(ha) & collections.Counter(hb)
        for h in hset.elements():
            held.append({"page": i + 1, "brand": h[0], "competitor": h[1], "peterson": h[2] if len(h) > 3 else None,
                         "reason": h[-1]})
    out = {"doc": sha, "pages": d.page_count, "rows": rows, "held": held, "diffs": diffs,
           "all_rows_agree": not diffs, "by_brand": dict(collections.Counter(r["brand"] for r in rows))}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"rows": len(rows), "held": len(held), "by_brand": out["by_brand"], "diffs": diffs}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
