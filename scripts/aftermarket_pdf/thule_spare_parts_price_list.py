"""Two-pass reader for the Thule "RV ACCESSORIES - SPARE PARTS 2023 PRICE LIST" (Excel export, 114 pages):
exploded drawing over a table Pos | ART.NR. | DESCRIPTION | Price (GBP). Continuation pages repeat no header.

Pass A: word positions. Every token in the ART.NR. column (x0 60-140) that looks like a Thule article number opens a
row; the description is the words on the same baseline in the DESCRIPTION column (x0 145-525; the price column starts at
x0 ~530, so lengths like "2.30 M" in a description stay).
Pass B: text-line order. A line that is only an article number is followed by its description line (the Excel cells
do not wrap); prices and callout numbers sit in their own block and are never next to a number line.
Only rows both passes give identically are kept. A number printed with two different descriptions is not loaded
("conflicts"). Placeholders such as "1500002XXX" are not numbers. Section = the page heading (top-left, y 20-36; continuation rows start at y ~43).
Prices are not kept.
usage: python3 -I thule_spare_parts_price_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

PN = re.compile(r"^\d{6,10}$")
PRICE = re.compile(r"^(\d{1,4}(,\d{3})*\.\d\d|N/A)$")


def heading(page):
    W = [w for w in page.get_text("words") if 20 <= w[1] <= 36 and w[0] < 500]
    return " ".join(w[4] for w in sorted(W, key=lambda w: w[0]))


def pass_a(page):
    W = page.get_text("words")
    rows = []
    for w in W:
        if 60 <= w[0] <= 140 and PN.match(w[4]) and w[1] > 38:
            y = (w[1] + w[3]) / 2
            ds = sorted((v for v in W if 145 <= v[0] < 525 and abs((v[1] + v[3]) / 2 - y) < 2.5), key=lambda v: v[0])
            # the footer page number can share the last row's baseline: drop it when it stands apart (gap > 20 pt)
            if len(ds) > 1 and ds[-1][4] == str(page.number + 1) and ds[-1][0] - ds[-2][2] > 20:
                ds = ds[:-1]
            desc = " ".join(v[4] for v in ds)
            desc = re.sub(r"\s*See Price\s*$", "", desc).strip()
            rows.append((round(y, 1), w[4], " ".join(desc.split())))
    rows.sort()
    return [(n, d) for _, n, d in rows]


def pass_b(page):
    L = [l.strip() for l in page.get_text().splitlines()]
    out = []
    for k, l in enumerate(L):
        if PN.match(l) and k + 1 < len(L):
            nxt = L[k + 1]
            if nxt and not PN.match(nxt) and not PRICE.match(nxt):
                out.append((l, " ".join(nxt.split())))
    return out


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, secs = [], [], {}
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        if not a and not b:
            continue
        sa, sb = sorted(a), sorted(b)
        if sa != sb:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        h = heading(p)
        key = secs.setdefault(h, str(len(secs)))
        rows += [(i + 1, n, num, desc, key) for n, (num, desc) in enumerate([x for x in a if x in b], 1)]
    descs = {}
    for pg, n, num, desc, key in rows:
        descs.setdefault(num, set()).add(desc)
    conflicts = {k: sorted(v) for k, v in descs.items() if len(v) > 1}
    seen, lines = set(), []
    for pg, n, num, desc, key in rows:
        if num in seen or not desc or num in conflicts:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{key}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs,
           "rows_total": len(rows), "numbers": len(seen), "conflicts": conflicts,
           "sections": {v: k for k, v in secs.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "all_rows_agree": not diffs, "rows": len(rows),
                      "numbers": len(seen), "conflicts": len(conflicts), "diff_pages": len(diffs), "diffs": diffs[:4]},
                     ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:3])
