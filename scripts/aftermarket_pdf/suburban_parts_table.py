"""Two-pass reader for Suburban (Airxcel) "Factory Replacement Parts" sheets with ruled tables:
"ITEM NO. | PART NUMBER | DESCRIPTION | QTY." (Nautilus IW60 205256XP) and "ITEM NO. | DESCRIPTION | PART NUMBER"
(SFV-35Q/42Q 205877XP, two tables side by side). English tables only (the French copy has no "PART" header).

Pass A: text-line order per table. Number-first layout: a 6-digit line opens a row and the lines with letters after it
are its description; description-first layout: lines with letters collect until a 6-digit line closes the row.
Item numbers (1, 3A) and quantities (2, A/R) are skipped.
Pass B: geometry (helpers shared with norcold_parts_list.py): columns from the vertical rules crossing the header,
number cells cut by the horizontal rules crossing the PART NUMBER column, description rows by the rules crossing the
DESCRIPTION column; a number cell owns the description rows whose centre lies inside it.
Rows are kept only when both passes give the same number and description.
usage: python3 -I suburban_parts_table.py <pdf> <out.json> "<section label>" """
import hashlib, json, os, re, sys
import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from norcold_parts_list import hlines, cuts, span_of, lines_text, clean  # noqa: E402
from seitz_spare_parts import vrules  # noqa: E402

NUM = re.compile(r"^\d{6}$")
ITEM = re.compile(r"^\d{1,3}[A-Z]?$")
QTY = re.compile(r"^(\d{1,2}|A/R)$")


def headers(page):
    W = page.get_text("words")
    out = []
    for d in W:
        if d[4] != "DESCRIPTION":
            continue
        others = [w[0] for w in W if w[4] == "DESCRIPTION" and w is not d and abs(w[1] - d[1]) < 12]
        # the PART header of the same table: no other table's DESCRIPTION header between them
        part = [w for w in W if w[4] == "PART" and abs(w[1] - d[1]) < 12
                and not any(min(w[0], d[0]) < x < max(w[0], d[0]) for x in others)]
        if not part:
            continue
        right = [w for w in part if w[0] > d[0]]
        p = min(right, key=lambda w: w[0]) if right else max(part, key=lambda w: w[0])
        num_first = p[0] < d[0]
        out.append((d, p, num_first))
    return out


def table_geom(page, d, p):
    V = vrules(page)
    yc = (d[1] + d[3]) / 2
    xs = []
    for x in sorted(v[0] for v in V if v[1] <= yc + 2 and v[2] >= yc - 2):
        if not xs or x - xs[-1] > 2:
            xs.append(x)
    cols = list(zip(xs, xs[1:]))
    col = lambda x: next((c for c in cols if c[0] <= x <= c[1]), None)
    dc, pc = col((d[0] + d[2]) / 2), col((p[0] + p[2]) / 2)
    if not dc or not pc or dc == pc:
        return None
    # table bottom: follow the rule on the number column's left edge down
    ybot = max([v[2] for v in V if abs(v[0] - pc[0]) < 1.5 and v[1] <= yc + 2 and v[2] >= yc - 2] or [yc])
    for v in sorted((v for v in V if abs(v[0] - pc[0]) < 1.5), key=lambda v: v[1]):
        if v[1] <= ybot + 2.5 and v[2] > ybot:
            ybot = v[2]
    ytop = max(w[3] for w in page.get_text("words") if abs(w[1] - d[1]) < 12 and (dc[0] <= w[0] <= pc[1] or pc[0] <= w[0] <= dc[1]))
    return ytop, ybot, dc, pc


def pass_b(page):
    W = page.get_text("words")
    H = hlines(page)
    rows = []
    for d, p, nf in headers(page):
        g = table_geom(page, d, p)
        if not g:
            continue
        ytop, ybot, dc, pc = g
        pys = cuts(H, (pc[0] + pc[1]) / 2, ytop, ybot)
        dys = cuts(H, (dc[0] + dc[1]) / 2, ytop, ybot)
        drows = []
        for a, b in zip(dys, dys[1:]):
            ws = [w for w in W if dc[0] - 1 <= w[0] and w[2] <= dc[1] + 1 and a < (w[1] + w[3]) / 2 < b]
            if ws:
                drows.append((a, b, lines_text([(w[1], w[0], w[4]) for w in ws])))
        for nw in sorted((w for w in W if NUM.match(w[4]) and pc[0] <= (w[0] + w[2]) / 2 <= pc[1] and ytop < w[1] < ybot), key=lambda w: w[1]):
            a, b = span_of(pys, (nw[1] + nw[3]) / 2)
            if a is None or b is None:
                continue
            mine = [t for y0, y1, t in drows if a - 1 <= (y0 + y1) / 2 <= b + 1]
            rows.append((nw[4], " ; ".join(mine)))
    return rows


def pass_a(page):
    hs = headers(page)
    if not hs:
        return []
    nf = hs[0][2]
    rows = []
    for blk in page.get_text("blocks"):
        pass
    L = [clean(l) for l in page.get_text().splitlines()]
    L = [l for l in L if l]
    started, cur, desc = False, None, []
    for t in L:
        if t in ("DESCRIPTION",):
            started = True; cur = None; desc = []; continue
        if not started or t in ("ITEM", "NO.", "PART", "NUMBER", "QTY.", "ITEM NO.", "PART NUMBER"):
            continue
        if NUM.match(t):
            if nf:
                if cur:
                    rows.append((cur[0], " ".join(cur[1])))
                cur = (t, [])
            else:
                rows.append((t, " ".join(desc))); desc = []
        elif ITEM.match(t) or QTY.match(t):
            continue
        elif re.search(r"[A-Za-z]", t):
            if nf:
                if cur:
                    cur[1].append(t)
            else:
                desc.append(t)
    if nf and cur:
        rows.append((cur[0], " ".join(cur[1])))
    return rows


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    if not d.permissions & pymupdf.PDF_PERM_COPY:
        print(json.dumps({"sha": sha, "error": "copy-protected"})); return
    kept, diffs = [], []
    for i, p in enumerate(d):
        b = pass_b(p)
        if not b:
            continue
        a = pass_a(p)
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:6], "only_b": [x for x in b if x not in a][:6]})
        kept += [(i + 1, num, desc) for num, desc in b if (num, desc) in a and desc]
    seen, lines, held, n = {}, [], [], 0
    for pg, num, desc in kept:
        if num in seen:
            if seen[num] != desc:
                held.append({"page": pg, "num": num, "why": "printed again with different text (first kept)", "text": desc})
            continue
        seen[num] = desc; n += 1
        lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "numbers": len(seen),
           "sections": {"0": section}, "rows": "\n".join(lines), "held": held}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "numbers": len(seen), "held": held[:5], "diffs": diffs[:3]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
