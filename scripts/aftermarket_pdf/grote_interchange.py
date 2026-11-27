"""Two-pass reader for Grote Industries' catalogue interchange tables (Final Catalog Book 2016, printed pp 233-249):
"<Brand> PN | Grote Form, Fit & Function | Grote Fit & Function" for TruckLite, Peterson, Primatronics, Maxxima and
Optronics, several table groups per page, sections starting mid-column ("PRIMATRONICS-TO-GROTE INTERCHANGE").

Geometry: each group is found from its header words (brand word + "PN", then the two "Grote" headers on the same line:
the one followed by "Form," is the form-fit-function column, the one followed by "Fit" the fit-and-function column).
Column boundaries are the midpoints between header extents (cells are centred). A row band starts at a competitor
number in the brand column and ends at the next one, so wrapped cell lines ("53413+67013+" / "91740") stay in the row.

Pass A: pymupdf words. Pass B: pdfplumber words. Rows are compared per page as multisets of
(brand, competitor no., column, cell text with spaces removed: pdfplumber splits some condensed-font numbers into
single digits); only rows both passes give are returned, with pass A's text.

Cells: one Grote number -> a row ("form_fit_function" or "fit_function"); a cell joining parts with "+" or "&"
(a combination) or listing several numbers ("77353, 77931", "67050 92149": alternatives or a set, not stated) is
returned as held. Competitor numbers containing a space ("PT3000A-AB S") are held.

usage: python3 -I grote_interchange.py <pdf> <out.json> <first printed page>"""
import collections, hashlib, json, re, sys
import pymupdf, pdfplumber

BRANDS = {"TruckLite": "Truck-Lite", "Peterson": "Peterson", "Maxxima": "Maxxima", "Optronics": "Optronics",
          "Primatronics": "Primatronics"}
NUM = re.compile(r"^[A-Z0-9][A-Z0-9.\-]*$", re.I)


def find_groups(W):
    """W: list of (x0, top, x1, bottom, text). Returns groups with column bounds and data top."""
    groups = []
    for x0, top, x1, bot, t in W:
        if t not in BRANDS:
            continue
        pn = [w for w in W if w[4] == "PN" and abs(w[1] - top) < 1.5 and 0 <= w[0] - x1 < 6] or \
             [w for w in W if w[4] == "PN" and 3 < w[1] - top < 10 and x0 - 2 <= w[0] <= x1]
        if not pn:
            continue
        gro = sorted([w for w in W if w[4] == "Grote" and abs(w[1] - top) < 1.5 and 0 < w[0] - x1 < 140],
                     key=lambda w: w[0])[:2]
        if len(gro) != 2:
            continue
        nxt = lambda g: min([w for w in W if abs(w[1] - g[1]) < 1.5 and w[0] > g[2]], key=lambda w: w[0], default=None)
        n1, n2 = nxt(gro[0]), nxt(gro[1])
        if not n1 or not n2 or n1[4] != "Form," or n2[4] != "Fit":
            continue
        hdr_words = [w for w in W if top - 1 < w[1] < top + 10 and x0 - 2 <= w[0] <= gro[1][2] + 40]
        fff_right = max(w[2] for w in hdr_words if gro[0][0] - 2 <= w[0] < gro[1][0] - 2)
        ff_right = max(w[2] for w in hdr_words if w[0] >= gro[1][0] - 2)
        groups.append({"brand": BRANDS[t], "x0": x0 - 12, "top": top,
                       "data_top": max((w[1] + w[3]) / 2 for w in hdr_words) + 3,
                       "c1": (max(pn[0][2], x1) + gro[0][0]) / 2, "c2": (fff_right + gro[1][0]) / 2, "c3": ff_right + 18})
    for g in groups:
        right = [h["x0"] for h in groups if h["x0"] > g["x0"] + 25 and abs(h["top"] - g["top"]) < 400]
        if right:
            g["c3"] = min(g["c3"], min(right) - 1)
        below = [h["top"] for h in groups if h is not g and abs(h["x0"] - g["x0"]) < 25 and h["top"] > g["top"]]
        g["data_bottom"] = (min(below) - 30) if below else 1e9
    return groups


def read(W, page_h):
    out = []
    for g in find_groups(W):
        ws = [w for w in W if g["data_top"] <= w[1] < min(g["data_bottom"], page_h - 36) and g["x0"] <= w[0] < g["c3"]
              and "-TO-" not in w[4] and "INTERCHANGE" not in w[4] and not w[4].startswith("NTERC")]
        comp = sorted([w for w in ws if w[0] < g["c1"]], key=lambda w: (round(w[1]), w[0]))
        lines = []
        for w in comp:
            if lines and abs(lines[-1][0] - w[1]) < 1.5:
                lines[-1][1].append(w[4])
            else:
                lines.append([w[1], [w[4]]])
        for k, (y, parts) in enumerate(lines):
            y_end = lines[k + 1][0] - 1 if k + 1 < len(lines) else y + 9
            c = " ".join(parts)
            for col, lo, hi in (("form_fit_function", g["c1"], g["c2"]), ("fit_function", g["c2"], g["c3"])):
                cell = sorted([w for w in ws if lo <= w[0] < hi and y - 1 <= w[1] < y_end], key=lambda w: (round(w[1]), w[0]))
                txt = " ".join(w[4] for w in cell)
                txt = re.sub(r"\s*([+&,])\s*", r"\1 ", txt).replace(" ,", ",").strip()
                if txt:
                    out.append((g["brand"], c, col, txt))
    return out


def classify(comp, cell):
    if " " in comp:
        return "competitor number contains a space"
    if "+" in cell or "&" in cell:
        return "Grote cell is a combination of parts (+ / &)"
    if "," in cell or " " in cell:
        return "several Grote numbers in one cell (alternatives or a set: not stated)"
    if not NUM.match(cell) or not NUM.match(comp):
        return "not a number"
    return None


def main(pdf, outp, first_printed):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    rows, held, diffs = [], [], []
    for i, p in enumerate(d):
        A = [(w[0], w[1], w[2], w[3], w[4]) for w in p.get_text("words")]
        B = [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"])
             for w in pl.pages[i].extract_words(x_tolerance=1.5, keep_blank_chars=False)]
        ra = read(A, p.rect.height)
        key = lambda r: (r[0], r[1].replace(" ", ""), r[2], r[3].replace(" ", ""))
        a, b = collections.Counter(key(r) for r in ra), collections.Counter(key(r) for r in read(B, pl.pages[i].height))
        text_of = {key(r): r for r in ra}
        if a != b:
            diffs.append({"page": i + 1, "only_a": list((a - b).elements())[:15], "only_b": list((b - a).elements())[:15],
                          "n_only_a": sum((a - b).values()), "n_only_b": sum((b - a).values())})
        for kk, n in (a & b).items():
            brand, comp, col, cell = text_of[kk]
            for _ in range(n):
                why = classify(comp, cell)
                rec = {"page": i + 1, "printed_page": str(int(first_printed) + i), "brand": brand, "competitor": comp,
                       "column": col, "grote": cell}
                if why:
                    held.append({**rec, "reason": why})
                else:
                    rows.append(rec)
    out = {"doc": sha, "pages": d.page_count, "rows": rows, "held": held, "diffs": diffs, "all_rows_agree": not diffs,
           "by_brand": dict(collections.Counter(r["brand"] for r in rows)),
           "held_by_reason": dict(collections.Counter(h["reason"] for h in held))}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"rows": len(rows), "held": len(held), "by_brand": out["by_brand"], "held_by_reason": out["held_by_reason"],
                      "diffs": diffs}, ensure_ascii=False)[:3500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
