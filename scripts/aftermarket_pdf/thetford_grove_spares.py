"""Two-pass reader for "Thetford Spare Parts" printed by Grove Products (UK Thetford distributor; Grove logo in the page
footer, file Thetford_General_spares.pdf, InDesign 2020): one or more tables per page "No. | Description | Thetford Part No.
Grove Part No." next to an exploded drawing, fridges (N80 ... N112, Deluxe/Smart lines), toilets, cookers and sinks.

Larry's 27 Nov decision on distributor catalogues: a maker's number printed under that maker's column with a description is
that maker's part (supplied lane, source kind distributor_catalogue); the distributor's stock number is never a part.
Grove numbers are printed BOLD in the same cell as the Thetford number ("62698627 089278") and are dropped by font.

The "Thetford Part No." area is two sub-columns wide. The right sub-column (under "Grove Part No.") holds cells that span
several item rows (A1+A2 "Black 62974427 / Anthracite 62974490" = a cell over Latch V3 and Latch strap; A4 "690852 089239"
over Freezer door and Hinge) or a second variant / production-date variant of one item (B3 "Before 01/07/05 ..." in the left
sub-column with the numbers in the right one). Without the cell geometry those cannot be assigned safely, so this reader
loads only the high-precision case and reports the rest as "unread":
- a baseline inside a table that has description text, exactly one regular-font Thetford-shaped number in the LEFT
  sub-column (optionally after variant words such as "Black", "Grey", "5 Pole"), only bold Grove numbers after it, and
  NOTHING in the right sub-column on that baseline;
- the next baseline of the table is not a description-only line (a wrapped description) and the line itself is not a
  code-less line directly under a code line that has no number (possible continuation) -> otherwise held;
- variant words become "(<variant>)" after the description; the model heading above the table (N98, Door 6, C2 Bench) is
  the row's section label (item codes are drawing callouts and are not stored).
Pass A: pymupdf rawdict characters grouped into words by gap and font. Pass B: pdfplumber extract_words with fontname.
Only rows both passes give identically are kept; a number printed with two different descriptions is not loaded.
usage: python3 -I thetford_grove_spares.py <pdf> <out.json>
"""
import hashlib, json, re, sys
import pdfplumber, pymupdf

NUM = re.compile(r"^\d{5,9}[A-Z]?$")


def sp(s):
    return " ".join(s.split())


def words_a(page):
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l.get("dir", (1, 0)) != (1, 0):
                continue
            for s in l["spans"]:
                bold = "Bold" in s["font"]
                cur = None
                for c in s["chars"]:
                    ch = c["c"]; x0, y0, x1, y1 = c["bbox"]
                    if ch.isspace():
                        cur = None; continue
                    if cur and x0 - cur["x1"] < 1.0:
                        cur["text"] += ch; cur["x1"] = x1
                    else:
                        cur = {"x0": x0, "x1": x1, "top": y0, "bottom": y1, "text": ch, "bold": bold}
                        out.append(cur)
    return out


def words_b(ppage):
    return [{"x0": w["x0"], "x1": w["x1"], "top": w["top"], "bottom": w["bottom"], "text": w["text"],
             "bold": "Bold" in w["fontname"]}
            for w in ppage.extract_words(extra_attrs=["fontname"], keep_blank_chars=False, use_text_flow=False)
            if w.get("upright", True)]


def baselines(ws):
    rows = []
    for w in sorted(ws, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"])):
        m = (w["top"] + w["bottom"]) / 2
        if rows and abs(rows[-1][0] - m) <= 2.2:
            rows[-1][1].append(w)
        else:
            rows.append([m, [w]])
    return [(m, sorted(r, key=lambda w: w["x0"])) for m, r in rows]


def model_label(ws, y):
    """The model heading of a table (e.g. "N98", "Door 6", "C2 Bench"): the closest line of the tallest words (>= 14 pt) up
    to 220 pt above the table header at y (or level with it), excluding the banner words and single drawing letters."""
    big = [w for w in ws if (w["bottom"] - w["top"]) >= 14 and w["text"] not in ("Thetford", "Spare", "Parts")
           and not re.fullmatch(r"[A-Z]", w["text"]) and (w["top"] + w["bottom"]) / 2 < y + 12]
    big = [w for w in big if (w["top"] + w["bottom"]) / 2 > y - 220]
    if not big:
        return ""
    hmax = max(w["bottom"] - w["top"] for w in big)
    ls = [ln for _, ln in baselines([w for w in big if (w["bottom"] - w["top"]) >= hmax - 1.5])]
    return sp(" ".join(w["text"] for w in ls[-1]))[:60]


def rects_a(page):
    out = []
    for g in page.get_drawings():
        if g.get("fill") is None:
            continue
        for it in g["items"]:
            if it[0] == "re":
                r = it[1]; out.append((r.x0, r.y0, r.x1, r.y1))
    return out


def rects_b(ppage):
    return [(r["x0"], r["top"], r["x1"], r["bottom"]) for r in ppage.rects if r.get("fill")]


def cell_of(w, rects, x_lo, x_hi):
    """Smallest filled rectangle inside the table's number area that contains the word's centre."""
    cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
    best = None
    for r in rects:
        if r[0] - 0.5 <= cx <= r[2] + 0.5 and r[1] - 0.5 <= cy <= r[3] + 0.5 and r[0] >= x_lo - 2 and r[2] <= x_hi + 20:
            if (r[3] - r[1]) < 2:
                continue
            if best is None or (r[2] - r[0]) * (r[3] - r[1]) < (best[2] - best[0]) * (best[3] - best[1]):
                best = r
    return best


def read_page(ws, rects):
    lines = baselines(ws)
    heads = []
    for m, ln in lines:
        for k, w in enumerate(ln):
            if w["text"] == "Description":
                rest = ln[k + 1:]
                th = next((x for x in rest if x["text"] == "Thetford"), None)
                gr = next((x for x in rest if x["text"] == "Grove"), None)
                if th and gr:
                    heads.append({"m": m, "dx": w["x0"], "tx": th["x0"], "gx": gr["x0"],
                                  "x_lo": w["x0"] - 26, "x_hi": gr["x0"] + 108})
    rows, held, unread = [], [], []
    for h in heads:
        label = model_label(ws, h["m"])
        nxt = min([g["m"] for g in heads if g is not h and g["m"] > h["m"] and g["x_lo"] < h["x_hi"] and h["x_lo"] < g["x_hi"]]
                  or [1e9])
        tl = []
        for m, ln in lines:
            if not (h["m"] + 3 < m < nxt - 3):
                continue
            band = [w for w in ln if h["x_lo"] <= w["x0"] < h["x_hi"]]
            if not band:
                continue
            code = [w for w in band if w["x0"] < h["dx"] - 3]
            desc = [w for w in band if h["dx"] - 3 <= w["x0"] < h["tx"] - 3]
            left = [w for w in band if h["tx"] - 3 <= w["x0"] < h["gx"] + 18]
            right = [w for w in band if w["x0"] >= h["gx"] + 18]
            tl.append({"m": m, "code": sp(" ".join(w["text"] for w in code)), "desc": sp(" ".join(w["text"] for w in desc)),
                       "left": left, "right": right})
        # a table ends where its lines stop (gap > 40 pt)
        cut = len(tl)
        for i in range(1, len(tl)):
            if tl[i]["m"] - tl[i - 1]["m"] > 40:
                cut = i; break
        tl = tl[:cut]
        # single row height = the most common height of the filled cells in the number area
        hs = sorted(round(r[3] - r[1], 1) for r in rects
                    if h["tx"] - 6 <= r[0] <= h["gx"] + 30 and h["m"] < r[1] < nxt and 6 < r[3] - r[1] < 40)
        rowh = max(set(hs), key=hs.count) if hs else None
        for i, t in enumerate(tl):
          for side, other in (("left", "right"), ("right", "left")):
            nums = [w for w in t[side] if not w["bold"] and NUM.match(w["text"])]
            if not nums:
                continue
            if len(nums) > 1:
                for w in nums:
                    unread.append({"number": w["text"], "why": f"two numbers in the {side} sub-column on one baseline", "item": t["code"]})
                continue
            n = nums[0]
            cell = cell_of(n, rects, h["tx"] - 6, h["x_hi"])
            before = [w for w in t[side] if w["x0"] < n["x0"]]
            after = [w for w in t[side] if w["x0"] > n["x0"]]
            why = None
            if rowh is None or cell is None:
                why = "no filled table cell found around the number"
            elif (cell[3] - cell[1]) > rowh * 1.5:
                unread.append({"number": n["text"], "why": f"cell spans {round((cell[3] - cell[1]) / rowh, 1)} rows (kit / merged cell)",
                               "item": t["code"], "desc": t["desc"]})
                continue
            elif t[other] and cell_of(t[other][0], rects, h["tx"] - 6, h["x_hi"]) == cell:
                why = "both sub-columns in one cell"
            elif not t["desc"]:
                why = "no description on its baseline"
            elif any(not w["bold"] for w in after):
                why = "regular text after the number"
            elif any(w["bold"] or NUM.match(w["text"]) for w in before):
                why = "unexpected token before the number"
            elif i + 1 < len(tl) and tl[i + 1]["desc"] and not tl[i + 1]["code"] and not tl[i + 1]["left"] and not tl[i + 1]["right"] \
                    and tl[i + 1]["m"] - t["m"] < 12:
                why = "description may wrap onto the next line"
            elif not t["code"] and i > 0 and tl[i - 1]["code"] and tl[i - 1]["desc"] and not tl[i - 1]["left"] \
                    and t["m"] - tl[i - 1]["m"] < 12:
                why = "code-less line under an item line without a number (continuation or sub-item?)"
            if why:
                held.append({"number": n["text"], "why": why, "item": t["code"], "desc": t["desc"]})
                continue
            var = sp(" ".join(w["text"] for w in before))
            d = t["desc"] + (f" ({var})" if var else "")
            rows.append({"number": n["text"], "desc": d, "qual": label})
    return rows, held, unread, len(heads)


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, held, unread = [], [], [], []
    key = lambda r: (r["number"], "".join(r["desc"].split()).casefold(), "".join(r["qual"].split()).casefold())
    for i, p in enumerate(d):
        ra, ha, ua, na = read_page(words_a(p), rects_a(p))
        rb, hb, ub, nb = read_page(words_b(pl.pages[i]), rects_b(pl.pages[i]))
        ka, kb = [key(r) for r in ra], [key(r) for r in rb]
        if sorted(ka) != sorted(kb) or na != nb:
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb][:4], "only_b": [r for r in rb if key(r) not in ka][:4],
                          "tables": [na, nb]})
        keep += [(i + 1, r) for r in ra if key(r) in kb]
        held += [dict(x, page=i + 1) for x in ha]
        unread += [dict(x, page=i + 1) for x in ua]
    names = {}
    for pg, r in keep:
        names.setdefault(r["number"], set()).add("".join(r["desc"].split()).casefold())
    conflict = {n for n, v in names.items() if len(v) > 1}
    quals = sorted({r["qual"] for _, r in keep})
    sections = {str(k): f"Thetford Spare Parts (Grove Products print): {q}" for k, q in enumerate(quals)}
    lines, seen, per_page = [], set(), {}
    for pg, r in keep:
        if r["number"] in conflict or r["number"] in seen:
            continue
        seen.add(r["number"])
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{r['number']}|{r['desc'].replace('|', '/')}|{quals.index(r['qual'])}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "page_diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines),
           "conflicts": [{"number": n, "descs": sorted(names[n])} for n in sorted(conflict)], "held": held, "unread": unread}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "numbers": len(seen), "pages_with_diffs": len(diffs),
                      "diff_sample": diffs[:2], "conflicts": len(conflict), "held": len(held), "held_sample": held[:5],
                      "unread": len(unread)}, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
