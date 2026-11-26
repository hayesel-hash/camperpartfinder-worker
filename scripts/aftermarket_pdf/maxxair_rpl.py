"""Reader for Maxxair (Airxcel) MAXXFAN repair parts lists.
Tables (CODE | USED ON MODELS | PART NUMBER | DESCRIPTION | NO. REQ.): pass B = word positions with columns from the
page header; pass A = part-number order and description adjacency in the text layer. A blank description cell in a
continuation row (same code) inherits the description above (the cell spans rows in the printed table).
Overview pages ("GARNISH RING INTERIOR / Black: 10-20209"): heading + "Label: number" from the text layer.
usage: python3 -I maxxair_rpl.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf
PN = re.compile(r"^\d{2}[A-Z-]\d{5}[A-Z0-9.-]*$")

def hsegs(page):
    out = []
    for g in page.get_drawings():
        for it in g["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.6 and abs(a.x - b.x) > 12: out.append((a.y, min(a.x, b.x), max(a.x, b.x)))
            elif it[0] == "re":
                r = it[1]
                if r.height < 1.6 and r.width > 12: out.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
    return out

def table_rows(page):
    """Grid reader: column and cell boundaries come from the drawn table rules, so merged cells (code, description,
    quantity spanning several part rows) are assigned to every row they span."""
    W = page.get_text("words")
    hx = {w[4]: w for w in W if w[4] in ("CODE", "USED", "PART", "NUMBER", "DESCRIPTION", "REQ.")}
    if not all(k in hx for k in ("CODE", "USED", "DESCRIPTION", "REQ.")) or not ("PART" in hx or "NUMBER" in hx):
        return None
    hbot = max(w[3] for w in hx.values()); htop = min(w[1] for w in hx.values())
    S = [x for x in hsegs(page) if x[0] > htop - 15]
    # column edges from the rule just below the header
    below = sorted({round(y, 1) for y, a, b in S if y > hbot - 1})
    if not below: return None
    yh = below[0]
    spans = sorted({(round(a), round(b)) for y, a, b in S if abs(y - yh) < 0.8})
    cols = []
    for a0, b0 in spans:
        if cols and a0 < cols[-1][1] - 3: continue   # overlapping duplicate
        cols.append((a0, b0))
    if len(cols) < 5: return None
    cols = cols[:5]  # code, models, part, desc, qty
    def bounds(ci):
        x0, x1 = cols[ci]; mid = (x0 + x1) / 2
        return sorted({round(y, 1) for y, a, b in S if a - 1 <= mid <= b + 1 and y >= yh - 0.8})
    B = [bounds(ci) for ci in range(5)]
    def cell_of(ci, y):
        b = B[ci]
        for lo, hi in zip(b[:-1], b[1:]):
            if lo <= y <= hi: return (lo, hi)
        return None
    def text_in(ci, cell):
        x0, x1 = cols[ci]; lo, hi = cell
        ws = sorted((round(w[3]), w[0], w[4]) for w in W if x0 <= (w[0] + w[2]) / 2 <= x1 and lo <= (w[1] + w[3]) / 2 <= hi)
        return " ".join(t for y, x, t in ws)
    rows = []
    for lo, hi in zip(B[2][:-1], B[2][1:]):
        pn = [t for t in text_in(2, (lo, hi)).split() if PN.match(t)]
        if not pn: continue
        ym = (lo + hi) / 2
        get = lambda ci: text_in(ci, cell_of(ci, ym)) if cell_of(ci, ym) else ""
        rows.append({"code": get(0), "models": get(1), "number": pn[0], "desc": get(3), "qty": get(4),
                     "desc_inherited": cell_of(3, ym) != (lo, hi)})
    return rows

def text_check(page, rows):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    seq = [l for l in L if PN.match(l)]
    ok_order = seq == [r["number"] for r in rows]
    bad = []
    joined = "\n".join(L)
    for r in rows:
        if r["desc"] and r["desc"] not in joined and r["desc"].replace(" ", "") not in joined.replace(" ", "").replace("\n", ""):
            bad.append((r["number"], r["desc"]))
    return ok_order, seq, bad

def overview_rows(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, head = [], ""
    for i, l in enumerate(L):
        m = re.match(r"^([A-Za-z /&-]+):\s*(\S+)?$", l)
        if l.isupper() and not PN.match(l) and len(l) > 3 and not l.startswith(("REPAIR PARTS", "FOR ", "KEY PAD", "AND KEY", "SEE ")):
            head = l
        elif m and head:
            num = m.group(2) or (L[i + 1] if i + 1 < len(L) else "")
            if PN.match(num): rows.append({"number": num, "desc": f"{head.title()}, {m.group(1).strip()}"})
        elif PN.match(l) and head and i > 0 and not re.match(r"^[A-Za-z /&-]+:\s*$", L[i - 1]):
            rows.append({"number": l, "desc": head.title()})
    return rows

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    title = " ".join(d[0].get_text().split())[:200]
    out, report = [], []
    for i, p in enumerate(d):
        tr = table_rows(p)
        if tr is not None:
            ok, seq, bad = text_check(p, tr)
            report.append({"page": i + 1, "kind": "table", "rows": len(tr), "order_agrees": ok, "desc_mismatch": bad[:5],
                           "only_text": [s for s in seq if s not in [r["number"] for r in tr]]})
            for r in tr: out.append(dict(r, page=i + 1))
        else:
            ov = overview_rows(p)
            if ov:
                report.append({"page": i + 1, "kind": "overview", "rows": len(ov)})
                for r in ov: out.append(dict(r, page=i + 1, code="", models="", qty="", desc_inherited=False))
    json.dump({"doc": sha, "pages": d.page_count, "title": title, "report": report, "rows": out}, open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "rows": len(out), "report": report}, ensure_ascii=False)[:2500])

if __name__ == "__main__":
    main(*sys.argv[1:3])
