"""Two-pass reader for Dometic (ex-Atwood) RV water-heater service-kit lists. Two layouts:

1. "Service Kit Parts Descriptions" (InDesign, e.g. form 3317892.000 for WH-6GA / 6GEA / 9GEA / 10GEA / 16GEA):
   model columns with X marks | Service Kit Number | Description. Footnote superscripts on the model headers
   ("9GEA" + small "1") are dropped by font size; a description line that starts with "(" and has no number
   continues the row above. The illustration page ("Service Kits by Part Number" callouts) is not a table: its
   numbers are only compared with the table and differences reported.
2. DITA "Spare Parts" table (Apache FOP, e.g. WH6EA 4445105273): Ref.No. | Pos | Qty | Description. Only the
   English table (header "Ref.No.") is read; the Spanish / French repeats on the last page are skipped.

Pass A reads text-line order, pass B word boxes by header column. Rows are kept only when both passes give the same
number, description and (layout 1) the same set of model columns, (layout 2) the same Pos callout.
usage: python3 -I dometic_wh_service_kits.py <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^\d{5}$|^\d{10}$")
POS = re.compile(r"^\d{4}$")
FOOT = re.compile(r"^\d[\x07 ]?[A-Z][a-z]")  # footnote "1\x07The water heaters ..."


def clean(s):
    return " ".join(s.split())


# ---------- layout 1: X columns | Service Kit Number | Description ----------
def models_from_header(page):
    """Model header names left of 'Service Kit Number', superscript footnote digits dropped by font size."""
    D = page.get_text("dict")
    spans = [s for b in D["blocks"] for l in b.get("lines", []) for s in l["spans"] if s["text"].strip()]
    # the table header cell is "Service Kit" over "Number" (the running head "Service Kit Parts Descriptions" is not)
    svc = [s for s in spans if s["text"].strip() == "Service Kit"]
    if not svc:
        return []
    y0, x_svc = svc[0]["bbox"][1], svc[0]["bbox"][0]
    hdr = [s for s in spans if abs(s["bbox"][1] - y0) < 12 and s["bbox"][2] <= x_svc + 1]
    if not hdr:
        return []
    big = max(s["size"] for s in hdr)
    cols = []
    for s in sorted(hdr, key=lambda s: s["bbox"][0]):
        if s["size"] < 0.8 * big:
            continue  # footnote superscript
        cols.append((s["text"].strip(), (s["bbox"][0] + s["bbox"][2]) / 2))
    return cols


def a_kits(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if not any(l.startswith("Service Kit") for l in L) or "Description" not in L:
        return []
    k = L.index("Description", next(i for i, l in enumerate(L) if l.startswith("Service Kit")))
    body = L[k + 1:]
    rows, xs, i = [], 0, 0
    while i < len(body):
        t = body[i]
        if t == "X":
            xs += 1; i += 1; continue
        if NUM.match(t):
            j, desc = i + 1, []
            while j < len(body) and body[j] != "X" and not NUM.match(body[j]) and not FOOT.match(body[j]):
                desc.append(body[j]); j += 1
            rows.append((t, clean(" ".join(desc)), xs))
            xs, i = 0, j; continue
        i += 1
    return rows


def b_kits(page):
    W = page.get_text("words")
    cols = models_from_header(page)
    hn = [w for w in W if w[4] == "Number"]
    hd = [w for w in W if w[4] == "Description"]
    if not cols or not hn or not hd:
        return [], {}
    y_hdr = hn[0][3]
    x_n0, x_n1 = hn[0][0] - 12, hn[0][2] + 12
    lines = {}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 <= y_hdr + 1:
            continue
        lines.setdefault(round((y0 + y1) / 2), []).append((x0, x1, w))
    rows, models, last_y = [], {}, None
    for y in sorted(lines):
        ws = sorted(lines[y])
        num = [w for x0, x1, w in ws if x_n0 <= x0 < x_n1 and NUM.match(w)]
        left = [(x0, x1, w) for x0, x1, w in ws if x1 <= x_n0]
        desc = clean(" ".join(w for x0, x1, w in ws if x0 >= x_n1))
        if num:
            marks = [min(cols, key=lambda c: abs(c[1] - (x0 + x1) / 2))[0] for x0, x1, w in left if w == "X"]
            others = [w for x0, x1, w in left if w != "X"]
            if others:
                continue
            rows.append([num[0], desc, len(marks)]); models[num[0]] = [c[0] for c in cols if c[0] in marks]
            last_y = y; continue
        # continuation line: description column only, directly under the previous row, starts with "("
        if rows and last_y is not None and not left and desc.startswith("(") and y - last_y < 14:
            rows[-1][1] = clean(rows[-1][1] + " " + desc); last_y = y
    return [tuple(r) for r in rows], models


def illustration_numbers(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if not any("Service Kits by Part Number" in l for l in L):
        return []
    return sorted({l for l in L if NUM.match(l)})


# ---------- layout 2: Ref.No. | Pos | Qty | Description (English table only) ----------
def a_dita(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if "Ref.No." not in L:
        return []
    k = L.index("Description", L.index("Ref.No."))
    body, rows, i = L[k + 1:], [], 0
    while i < len(body):
        if NUM.match(body[i]) and i + 1 < len(body) and POS.match(body[i + 1]):
            num, pos, j, desc = body[i], body[i + 1], i + 2, []
            while j < len(body) and not (NUM.match(body[j]) and j + 1 < len(body) and POS.match(body[j + 1])):
                if body[j] in ("YOUR LOCAL DEALER",):
                    break
                desc.append(body[j]); j += 1
            rows.append((num, clean(" ".join(desc)), pos)); i = j; continue
        i += 1
    return rows


def b_dita(page):
    W = page.get_text("words")
    h = {w[4]: w for w in W if w[4] in ("Ref.No.", "Pos", "Qty", "Description")}
    if len(h) < 4:
        return []
    yh = h["Ref.No."][3]
    xp, xq, xd = h["Pos"][0] - 5, h["Qty"][0] - 5, h["Description"][0] - 5
    lines = {}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 > yh + 1:
            lines.setdefault(round((y0 + y1) / 2), []).append((x0, w))
    rows = []
    for y in sorted(lines):
        ws = sorted(lines[y])
        num = [w for x, w in ws if x < xp and NUM.match(w)]
        pos = [w for x, w in ws if xp <= x < xq and POS.match(w)]
        desc = clean(" ".join(w for x, w in ws if x >= xd))
        if num and pos:
            rows.append((num[0], desc, pos[0]))
    return rows


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, illus = [], [], []
    for i, p in enumerate(d):
        illus += illustration_numbers(p)
        a, (b, models) = a_kits(p), b_kits(p)
        if a or b:
            if a != b:
                diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
            for num, desc, nx in [x for x in a if x in b]:
                rows.append((i + 1, num, f"{desc} (used on: {', '.join(models[num])})"))
            continue
        a, b = a_dita(p), b_dita(p)
        if a or b:
            if a != b:
                diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
            for num, desc, pos in [x for x in a if x in b]:
                rows.append((i + 1, num, f"{desc} (Pos {pos})"))
    seen, lines, n = set(), [], {}
    for pg, num, desc in rows:
        if num in seen:
            continue
        seen.add(num); n[pg] = n.get(pg, 0) + 1
        lines.append(f"{pg}|{n[pg]}|{num}|{desc.replace('|', '/')}|0")
    ill = sorted(set(illus))
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "illustration_only": [x for x in ill if x not in seen],
           "table_not_in_illustration": [x for x in sorted(seen) if ill and x not in ill],
           "sections": {"0": section}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("agree", "rows_total", "numbers", "illustration_only", "table_not_in_illustration")}
                     | {"sha16": sha[:16], "diffs": diffs[:2]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
