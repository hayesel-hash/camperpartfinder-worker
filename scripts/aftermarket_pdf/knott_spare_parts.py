"""Two-pass reader for the KNOTT "Trailer Technology" spare parts catalogue 2019 (German): an exploded-drawing page
("Bremstyp: 16-1369/1 / Bremsgröße: 160x35 Spr. / Ausführung: ...") followed by list pages with one or two tables
"Pos | Bezeichnung | Bestell-nummer"; rows are vertically centred, a description can take two lines
("Bremsnabe 100x4/M12" / "Höhe: 101mm").

Pass A: text-line order after each header ("Pos", "Bezeichnung", "Bestell-", "nummer"): a position line opens a row,
description lines follow, the order-number line closes it.
Pass B: word positions per table (header words give the columns; the table's right edge is the next table's "Pos"):
row bands are cut half-way between consecutive position numbers (cells are vertically centred); description words and
the one order number inside the band.
Only rows both passes give identically are kept; a number printed with two different descriptions is not loaded
("conflicts"). Section = the first lines of the drawing page the list belongs to. Descriptions stay in German as printed.
usage: python3 -I knott_spare_parts.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

# order numbers: 42191, 23851B02, D94.013, 45877.10, 41582-2, 405859.001, 33921-1.06, 409697B002, 47305V, 69000393, 8710311314, 6J1031.006 ...
# (at least four digits, so a description line such as "M12" is never a number)
NUM = re.compile(r"^(?=(?:\D*\d){4})(?:[A-Z]?\d{2,10}(?:[A-Z]{1,2}\d{0,3})?|\d[A-Z]\d{3,6})(?:[.-]\d{1,3}){0,2}[A-Z]?$")
NO_NUM = "auf Anfrage"  # "on request": the row has no order number
POS = re.compile(r"^\d{1,3}[a-z]?$")


def norm(s):
    return " ".join(s.split())


def is_list_page(page):
    W = page.get_text("words")
    return any(w[4] == "Bezeichnung" for w in W) and any(w[4] == "Bestell-" for w in W)


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, k = [], 0
    while k < len(L):
        if L[k] == "Pos" and L[k + 1:k + 2] == ["Bezeichnung"]:
            k += 2
            while k < len(L) and L[k] in ("Bestell-", "nummer"):
                k += 1
            continue
        if POS.match(L[k]) and k + 1 < len(L) and not NUM.match(L[k + 1]):
            desc, j = [], k + 1
            while j < len(L) and not NUM.match(L[j]) and L[j] != "Pos" and len(desc) < 4:
                if L[j] == NO_NUM or L[j].endswith(" " + NO_NUM):
                    break
                desc.append(L[j]); j += 1
            if j < len(L) and (L[j] == NO_NUM or L[j].endswith(" " + NO_NUM)):
                k = j + 1; continue
            if j < len(L) and NUM.match(L[j]):
                rows.append((L[k], norm(" ".join(desc)), L[j]))
                k = j + 1; continue
        k += 1
    return rows


def lines(ws):
    """Words in reading order: lines clustered by vertical centre (3 pt; bold and regular spans differ slightly)."""
    L = []
    for w in sorted(ws, key=lambda w: (w[1] + w[3]) / 2):
        m = (w[1] + w[3]) / 2
        if L and abs(L[-1][0] - m) < 3:
            L[-1][1].append(w)
        else:
            L.append([m, [w]])
    return [w for _, ln in L for w in sorted(ln, key=lambda w: w[0])]


def pass_b(page):
    W = page.get_text("words")
    heads = sorted([w for w in W if w[4] == "Pos" and any(v[4] == "Bezeichnung" and abs(v[1] - w[1]) < 3 for v in W)],
                   key=lambda w: (round(w[1]), w[0]))
    rows = []
    for i, h in enumerate(heads):
        same = sorted([g for g in heads if abs(g[1] - h[1]) < 3], key=lambda g: g[0])
        nxt = [g for g in same if g[0] > h[0]]
        right = nxt[0][0] - 3 if nxt else page.rect.width
        below = [g for g in heads if g[1] > h[1] + 3 and abs(g[0] - h[0]) < 20]
        ybot = below[0][1] - 2 if below else page.rect.height
        bz = [v for v in W if v[4] == "Bezeichnung" and abs(v[1] - h[1]) < 3 and h[0] < v[0] < right][0]
        bs = [v for v in W if v[4] == "Bestell-" and abs(v[1] - h[1]) < 12 and bz[0] < v[0] < right][0]
        ytop = max(v[3] for v in W if v[4] == "nummer" and bz[0] < v[0] < right and abs(v[1] - h[1]) < 15)
        xnum = bs[0] - 25
        P = sorted([v for v in W if h[0] - 8 <= v[0] < bz[0] - 3 and ytop < v[1] < ybot and POS.match(v[4])], key=lambda v: v[1])
        mids = [(v[1] + v[3]) / 2 for v in P]
        for j, p in enumerate(P):
            lo = (mids[j - 1] + mids[j]) / 2 if j else ytop
            hi = (mids[j] + mids[j + 1]) / 2 if j + 1 < len(P) else mids[j] + 12
            band = [v for v in W if lo <= (v[1] + v[3]) / 2 < hi]
            desc = lines([v for v in band if bz[0] - 3 <= v[0] < xnum])
            nums = [v[4] for v in band if xnum <= v[0] < right and NUM.match(v[4])]
            if len(nums) == 1:
                rows.append((p[4], norm(" ".join(v[4] for v in desc)), nums[0]))
    return rows


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, secs, sec = [], [], {}, ""
    for i, p in enumerate(d):
        if not is_list_page(p):
            t = [l.strip() for l in p.get_text().splitlines() if l.strip() and not re.match(r"^\d{1,3}$", l.strip())]
            if t:
                sec = norm(" / ".join(t[:3]))[:160]
            continue
        a, b = pass_a(p), pass_b(p)
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:4], "only_b": [x for x in b if x not in a][:4]})
        key = secs.setdefault(sec, str(len(secs)))
        rows += [(i + 1, n, num, desc, key) for n, (pos, desc, num) in enumerate([x for x in a if x in b], 1)]
    descs = {}
    for r in rows:
        descs.setdefault(r[2], set()).add(r[3])
    conflicts = {k: sorted(v) for k, v in descs.items() if len(v) > 1}
    seen, lines = set(), []
    for pg, n, num, desc, key in rows:
        # "Seilzug siehe S. 185-191": a page reference in the number column, not an order number
        if num in seen or num in conflicts or not desc or re.search(r"siehe\s+S\.?$", desc):
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{key}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs,
           "rows_total": len(rows), "numbers": len(seen), "conflicts": conflicts,
           "sections": {v: k for k, v in secs.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "rows": len(rows), "numbers": len(seen), "conflicts": len(conflicts),
                      "diff_pages": [x["page"] for x in diffs], "diffs": diffs[:3]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:3])
