"""Two-pass reader for the Dometic DF Series Furnace Service Parts List (form 33402, 09/17) "PART NUMBER LIST":
Small | Medium | Large DC | Large AC (X marks) | SPI No. | SCV_KIT | Description.
SPI No. is the callout used on the exploded views (pages 2-4); SCV_KIT is the service kit (part) number.
A row with no SCV_KIT number (e.g. 4850 blower housing rear LG) is not a part and is skipped.

Pass A: text-line order (X lines, SPI line, SCV line, description line(s)). Pass B: word boxes by header column
(description is centred under its header, so anything right of the SCV_KIT column is description). Rows are kept
only when both passes give the same SPI, number, description and number of X marks; the furnace sizes are then
taken from pass B's X positions and kept with the SPI callout as "(SPI 4501; used on: Medium)".
usage: python3 -I dometic_df_furnace.py <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf

SPI = re.compile(r"^\d{4}$")
SCV = re.compile(r"^\d{5}$")
SIZES = ["Small", "Medium", "Large DC", "Large AC"]


def is_table(L):
    return "SPI No." in L and "SCV_KIT" in L and "Description" in L


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if not is_table(L):
        return []
    body = L[L.index("Description", L.index("SCV_KIT")) + 1:]
    rows, xs, k = [], 0, 0
    while k < len(body):
        t = body[k]
        if t == "X":
            xs += 1; k += 1; continue
        if SPI.match(t):
            spi, num, j = t, None, k + 1
            if j < len(body) and SCV.match(body[j]):
                num = body[j]; j += 1
            desc = []
            while j < len(body) and body[j] != "X" and not SPI.match(body[j]) and not body[j].startswith("RED TEXT"):
                desc.append(body[j]); j += 1
            rows.append((spi, num, " ".join(" ".join(desc).split()), xs))
            xs, k = 0, j; continue
        k += 1
    return rows


def pass_b(page):
    W = page.get_text("words")
    hs = [w for w in W if w[4] == "SPI"]
    hk = [w for w in W if w[4] == "SCV_KIT"]
    if not hs or not hk:
        return [], {}
    yh = hs[0][1]
    hdr = [w for w in W if abs(w[1] - yh) < 3]
    # size column centres from the header words (two-word headers "Large DC" / "Large AC")
    cols, k = [], 0
    hw = sorted(hdr, key=lambda w: w[0])
    while k < len(hw):
        w = hw[k]
        if w[4] in ("Small", "Medium"):
            cols.append((w[4], (w[0] + w[2]) / 2)); k += 1; continue
        if w[4] == "Large" and k + 1 < len(hw) and hw[k + 1][4] in ("DC", "AC"):
            cols.append(("Large " + hw[k + 1][4], (w[0] + hw[k + 1][2]) / 2)); k += 2; continue
        k += 1
    x_spi0, x_scv0, x_scv1 = hs[0][0] - 15, hk[0][0] - 15, hk[0][2] + 15
    lines = {}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 <= yh + 3 or w == "X":
            continue
        lines.setdefault(round((y0 + y1) / 2), []).append((x0, x1, w))
    xmarks = [((w[1] + w[3]) / 2, w[0], w[2]) for w in W if w[4] == "X" and w[1] > yh + 3 and w[0] < x_spi0]
    rows, sizes, ys = [], {}, []
    for y in sorted(lines):
        ws = sorted(lines[y])
        spi = [w for x0, x1, w in ws if x_spi0 <= x0 < x_scv0 and SPI.match(w)]
        if not spi:
            continue
        num = [w for x0, x1, w in ws if x_scv0 <= x0 < x_scv1 and SCV.match(w)]
        desc = " ".join(w for x0, x1, w in ws if x0 >= x_scv1)
        rows.append([spi[0], num[0] if num else None, " ".join(desc.split()), 0]); ys.append(y)
    marks = {i: [] for i in range(len(rows))}
    for yc, x0, x1 in xmarks:
        if not ys:
            break
        i = min(range(len(ys)), key=lambda i: abs(ys[i] - yc))
        if abs(ys[i] - yc) < 6:
            marks[i].append(min(cols, key=lambda c: abs(c[1] - (x0 + x1) / 2))[0])
    for i, r in enumerate(rows):
        r[3] = len(marks[i]); sizes[r[0]] = [s for s in SIZES if s in marks[i]]
    rows = [tuple(r) for r in rows]
    return rows, sizes


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, skipped = [], [], []
    for i, p in enumerate(d):
        a = pass_a(p); b, sizes = pass_b(p)
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        n = 0
        for spi, num, desc, nx in [x for x in a if x in b]:
            if not num:
                skipped.append({"page": i + 1, "spi": spi, "description": desc}); continue
            n += 1
            rows.append((i + 1, n, num, f"{desc} (SPI {spi}; used on: {', '.join(sizes.get(spi, []))})"))
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "skipped_no_number": skipped, "sections": {"0": section}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "skipped": skipped,
                      "diffs": diffs[:2]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
