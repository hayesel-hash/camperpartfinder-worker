"""Two-pass reader for Norcold (Thetford North America) refrigerator parts lists: InDesign tables
"NO. | PART # | DESCRIPTION | one X (or quantity) cell per rotated model column [| WARRANTABLE]"
(N2090 640999, N2152 641000, N7/N8 639735, N8DC/N10DC 640138, 2118 PolarMax 637110).

Numbers are 6-8 digits; a trailing "*" and grey cell shading carry the meaning printed in the page legend, which differs
between sheets ("*" = LIMITED AVAILABILITY and grey = NOT AVAILABLE on the 2025 Thetford-styled lists; "*" = NOT AVAILABLE
and grey = NO LONGER AVAILABLE on the 2118 list), so the legend is read from each page and appended in words.
One PART # cell may span several description rows (e.g. 692758 = DOOR LATCH + WINTER LOCK SUPPORT): those descriptions are
joined with "; ". Same-maker notes "(SUPERSEDED TO n)", "SUPERSEDED TO n", "(USE n)" and "- REPLACES a & b" are returned in
"supersessions" for the legacy-map v2 lane (a row that is nothing but "SUPERSEDED TO n" is not an identity row).

Pass A: text-line order. After a header (a "DESCRIPTION" line preceded by "PART #"), a number line opens a row; lines with
letters (not "X", not "NS") are description; X lines are counted; a description line that follows the X cells of a row
without a new number continues the same number cell (merged cell).
Pass B: geometry. Columns from the header words and the ruled lines; each number cell's vertical span is cut by the
horizontal rules that cross the PART # column, description rows by the rules that cross the DESCRIPTION column; a number
cell owns every description row whose centre lies inside it. Mark cells (X or quantity digit) are read per model column.
Rows are kept only when both passes give the same number, description and X count. Model applicability
("[models: ...]", quantities as "xN") comes from pass B and is added when a row is not marked in every model column
(WARRANTABLE is not a model column and is left out).
usage: python3 -I norcold_parts_list.py <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^(\d{6,8}|\d[A-Z]\d{4}) ?(\*{0,3})$")
NOTOK = re.compile(r"^(\d{1,3}(-\d{1,3})?|NS)$")
MARK = re.compile(r"^(X|x|\d)$")
LEG = re.compile(r"^(NOT AVAILABLE|NO LONGER AVAILABLE|LIMITED AVAILABILITY|NS ?- ?NOT SHOWN|NOT SHOWN|\*{1,3}|NS)$", re.I)
FOOT = re.compile(r"(PART LIST|PARTS LIST) - PAGE \d+$", re.I)
SUPS = [re.compile(r"[\(\[]?SUPERSEDED TO (\d{6,8})[\)\]]?", re.I), re.compile(r"\(USE (\d{6,8})\)", re.I)]
REPL = re.compile(r"- REPLACES ((?:\d{6,8}(?:\s*(?:&|,|AND)\s*)?)+)$", re.I)


def clean(s):
    return " ".join(s.replace("”", '"').replace("“", '"').split())


def has_letters(t):
    return re.search(r"[A-Za-z]", t) is not None


# ---------------------------------------------------------------- pass A
def pass_a(page):
    L = [clean(l) for l in page.get_text().splitlines()]
    L = [l for l in L if l]
    rows, cur, state, k = [], None, "out", 0
    def close():
        nonlocal cur
        if cur:
            g = cur["desc"]
            while len(g) > 1 and g[-1][1] == 0:  # band row / note after the row (no X under it): not this number's
                g.pop()
            rows.append((cur["num"], cur["star"], " ; ".join(" ".join(x[0]) for x in g if x[0]), sum(x[1] for x in g)))
        cur = None
    while k < len(L):
        t = L[k]
        if t.upper().startswith("DESCRIPTION") and k > 0 and L[k - 1].upper().endswith("PART #"):
            close(); state = "hdr"; k += 1; continue
        if state == "out":
            k += 1; continue
        if state == "hdr":  # model / warrantable header labels and band rows until the first row token
            if NOTOK.match(t) or NUM.match(t):
                state = "rows"
            else:
                k += 1; continue
        if FOOT.search(t) or (LEG.match(t) and t not in ("NS",)) or t.upper().startswith("NOTE"):
            close(); state = "out"; k += 1; continue
        if t == "NS" and k + 1 < len(L) and L[k + 1].upper() == "NOT SHOWN":
            close(); state = "out"; k += 1; continue
        if re.fullmatch(r"(NO\. ?)?PART #|NO\.", t, re.I):
            close(); k += 1; continue
        m = NUM.match(t)
        if m:
            close(); cur = {"num": m.group(1), "star": len(m.group(2)), "desc": [[[], 0]], "after": False}
        elif t in ("X", "x"):
            if cur:
                cur["desc"][-1][1] += 1; cur["after"] = True
        elif NOTOK.match(t) or MARK.match(t):
            pass  # item numbers and quantity cells
        elif has_letters(t):
            if cur is None:
                pass  # description row whose number cell is missing: not a row
            elif cur["after"]:  # a description after the row's marks without a new number: merged number cell
                cur["desc"].append([[t], 0]); cur["after"] = False
            else:
                cur["desc"][-1][0].append(t)
        k += 1
    close()
    return rows


# ---------------------------------------------------------------- pass B
def hlines(page):
    out = []
    for g in page.get_drawings():
        for it in g["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                if abs(p.y - q.y) < 0.8 and abs(p.x - q.x) > 3:
                    out.append((min(p.x, q.x), max(p.x, q.x), (p.y + q.y) / 2))
            elif it[0] == "re":
                r = it[1]
                if r.height < 1.6:
                    out.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
                else:
                    out.append((r.x0, r.x1, r.y0)); out.append((r.x0, r.x1, r.y1))
    return out


def vlines(page):
    out = []
    for g in page.get_drawings():
        for it in g["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                if abs(p.x - q.x) < 0.8 and abs(p.y - q.y) > 3:
                    out.append(((p.x + q.x) / 2, min(p.y, q.y), max(p.y, q.y)))
            elif it[0] == "re":
                r = it[1]
                if r.width < 1.6:
                    out.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                else:
                    out.append((r.x0, r.y0, r.y1)); out.append((r.x1, r.y0, r.y1))
    return out


def grey_rects(page):
    out = []
    for g in page.get_drawings():
        f = g.get("fill")
        if f and len(f) == 3 and abs(f[0] - f[1]) < 0.02 and abs(f[1] - f[2]) < 0.02 and 0.3 < f[0] < 0.9:
            for it in g["items"]:
                if it[0] == "re":
                    out.append(it[1])
    return out


def cuts(H, x, y0, y1):
    ys = sorted({round(y, 1) for a, b, y in H if a - 1 <= x <= b + 1 and y0 - 2 <= y <= y1 + 2})
    m = []
    for y in ys:
        if not m or y - m[-1] > 2.5:
            m.append(y)
    return m


def span_of(ys, y):
    above = [v for v in ys if v <= y]
    below = [v for v in ys if v > y]
    return (above[-1] if above else None, below[0] if below else None)


def headers(W):
    """(x0 of NO., part word, description word) for each table header on the page"""
    out = []
    for w in W:
        if w[4] == "PART":
            hs = [v for v in W if abs(v[1] - w[1]) < 3 and v[4] == "#" and 0 <= v[0] - w[2] < 10]
            ds = [v for v in W if abs(v[1] - w[1]) < 3 and v[4] == "DESCRIPTION" and v[0] > w[2]]
            if hs and ds:
                out.append((w, hs[0], ds[0]))
    return sorted(out, key=lambda h: h[0][1])


def pass_b(page):
    W = page.get_text("words")
    H, V = hlines(page), vlines(page)
    rows, cols_all = [], []
    hdrs = headers(W)
    for hi, (pw, hw, dw) in enumerate(hdrs):
        ytop = max(pw[3], dw[3])
        ylim = hdrs[hi + 1][0][1] - 5 if hi + 1 < len(hdrs) else page.rect.y1
        # vertical rules below the header bottom: column boundaries
        vx = sorted({round(x, 1) for x, a, b in V if a <= ytop + 4 and b >= ytop + 8})
        cx = []
        for x in vx:
            if not cx or x - cx[-1] > 2.5:
                cx.append(x)
        def col(x):
            for i in range(len(cx) - 1):
                if cx[i] - 0.5 <= x <= cx[i + 1] + 0.5:
                    return i
            return None
        pc, dc = col((pw[0] + hw[2]) / 2), col(dw[0] + 2)
        if pc is None or dc is None:
            continue
        # model columns: every column right of DESCRIPTION; names from the (rotated) header words in the column
        hdr_top = pw[1] - 80
        mcols = []
        for i in range(dc + 1, len(cx) - 1):
            ws = [w for w in W if cx[i] <= (w[0] + w[2]) / 2 <= cx[i + 1] and hdr_top < w[1] and w[3] <= ytop + 25
                  and not MARK.match(w[4])]
            if ws and all((w[2] - w[0]) >= (w[3] - w[1]) for w in ws):  # horizontal header lines: top to bottom
                ws.sort(key=lambda w: (round(w[1] / 3), w[0]))
            else:  # rotated header text: left to right, each line bottom to top
                ws.sort(key=lambda w: (round(w[0]), -w[3]))
            name = " ".join(w[4] for w in ws)
            if (cx[i + 1] - cx[i]) < 4 or not name:  # gap between the model box and the WARRANTABLE box
                continue
            mcols.append((i, name))
        # table bottom: first legend / footer word below the header in the description column
        ybot = ylim
        for w in W:
            if w[1] > ytop + 2 and w[1] < ybot and w[4] in ("NOT", "NO", "LIMITED", "*") and cx[dc] <= w[0] <= cx[dc + 1]:
                line = " ".join(v[4] for v in W if abs(v[1] - w[1]) < 2 and cx[dc] <= v[0] <= cx[dc + 1])
                if LEG.match(clean(line)):
                    ybot = w[1]
        # header row bottom = the first horizontal rule across the PART column below the header text
        pcx = (cx[pc] + cx[pc + 1]) / 2
        dcx = (cx[dc] + cx[dc + 1]) / 2
        pys = cuts(H, pcx, ytop, ybot)
        dys = cuts(H, dcx, ytop, ybot)
        nums = [w for w in W if NUM.match(w[4]) and cx[pc] <= (w[0] + w[2]) / 2 <= cx[pc + 1] and ytop < w[1] < ybot]
        drows = []
        for a, b in zip(dys, dys[1:]):
            ws = [w for w in W if cx[dc] <= w[0] and w[2] <= cx[dc + 1] + 1 and a < (w[1] + w[3]) / 2 < b]
            if not ws:
                continue
            txt = lines_text([(w[1], w[0], w[4]) for w in ws])
            marks = {}
            for i, name in mcols:
                ms = [w[4] for w in W if cx[i] <= (w[0] + w[2]) / 2 <= cx[i + 1] and a < (w[1] + w[3]) / 2 < b and MARK.match(w[4])]
                if ms:
                    marks[i] = ms[0]
            drows.append({"y0": a, "y1": b, "text": txt, "marks": marks, "own": False})
        for nw in nums:
            m = NUM.match(nw[4])
            nstar = len(m.group(2)) or max([len(v[4]) for v in W if re.fullmatch(r"\*{1,3}", v[4]) and abs(v[1] - nw[1]) < 2
                                             and 0 <= v[0] - nw[2] < 6] or [0])
            yc = (nw[1] + nw[3]) / 2
            a, b = span_of(pys, yc)
            if a is None or b is None:
                continue
            mine = [r for r in drows if a - 1 <= (r["y0"] + r["y1"]) / 2 <= b + 1]
            for r in mine:
                r["own"] = True
            desc = " ".join(r["text"] for r in mine) if len(mine) == 1 else " ; ".join(r["text"] for r in mine)
            nx = sum(1 for r in mine for v in r["marks"].values() if v in ("X", "x"))
            marked = {}
            for r in mine:
                for i, v in r["marks"].items():
                    marked.setdefault(i, v)
            rows.append({"num": m.group(1), "star": nstar, "desc": desc, "nx": nx, "y": yc, "x": nw[0],
                         "marked": marked, "mcols": mcols, "rect": pymupdf.Rect(nw[:4])})
        cols_all.append(mcols)
    return rows


def lines_text(ws):
    out, cur, cy = [], [], None
    for y, x, w in sorted(ws):
        if cy is not None and y - cy > 3:
            out.append(cur); cur = []
        if not cur:
            cy = y
        cur.append((x, w))
    if cur:
        out.append(cur)
    return clean(" ".join(" ".join(w for x, w in sorted(line)) for line in out))


def line_right(W, x, yc, first=40, gap=20):
    ws = sorted([v for v in W if abs((v[1] + v[3]) / 2 - yc) < 4 and v[0] >= x - 0.5], key=lambda v: v[0])
    out, last = [], None
    for v in ws:
        if (last is None and v[0] - x > first) or (last is not None and v[0] - last > gap):
            break
        out.append(v[4]); last = v[2]
    return clean(" ".join(out))


def legend(page):
    """meaning of '*', '***' and grey shading, read from the legend printed on the page"""
    W = page.get_text("words")
    stars, shade = {}, None
    for w in W:
        if re.fullmatch(r"\*{1,3}", w[4]):
            lab = line_right(W, w[2], (w[1] + w[3]) / 2, first=120)
            if lab and not NUM.match(lab.split()[0]):
                stars[len(w[4])] = lab.lower()
    for r in grey_rects(page):
        lab = line_right(W, r.x1, (r.y0 + r.y1) / 2)
        inside = [v for v in W if r.contains(pymupdf.Rect(v[:4])) and v[4].strip()]
        if not inside and LEG.match(lab) and "AVAILAB" in lab.upper():
            shade = lab.lower()
    return stars, shade


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    if not d.permissions & pymupdf.PDF_PERM_COPY:
        print(json.dumps({"sha": sha, "error": "copy-protected"})); return
    kept, diffs, held, sups, rows_total = [], [], [], [], 0
    for pi, p in enumerate(d):
        a = pass_a(p)
        b = pass_b(p)
        if not a and not b:
            continue
        stars_l, shade_l = legend(p)
        greys = grey_rects(p)
        rows_total += len(b)
        bkey = {}
        for r in b:
            bkey.setdefault((r["num"], r["star"], r["desc"], r["nx"]), []).append(r)
        akeys = list(a)
        only_a = [x for x in akeys if x not in bkey]
        only_b = [k for k in bkey if k not in akeys]
        if only_a or only_b:
            diffs.append({"page": pi + 1, "only_a": only_a[:6], "only_b": only_b[:6]})
        for k in akeys:
            if k not in bkey:
                held.append({"page": pi + 1, "num": k[0], "why": "passes disagree"}); continue
            r = bkey[k][0]
            num, star, desc, nx = k
            if (star and star not in stars_l) or (any(g.contains(r["rect"]) or g.intersects(r["rect"]) for g in greys) and not shade_l):
                held.append({"page": pi + 1, "num": num, "why": "availability legend not found"}); continue
            shaded = any(pymupdf.Rect(g).intersect(r["rect"]).get_area() > 0.5 * r["rect"].get_area() for g in greys)
            # same-maker supersession notes
            for rx in SUPS:
                for m in rx.finditer(desc):
                    if m.group(1) != num:
                        sups.append({"page": pi + 1, "legacy": num, "current": m.group(1), "printed": f"{num} | {desc}"})
            m = REPL.search(desc)
            if m:
                for old in re.findall(r"\d{6,8}", m.group(1)):
                    if old != num:
                        sups.append({"page": pi + 1, "legacy": old, "current": num, "printed": f"{num} | {desc}"})
            if re.fullmatch(r"SUPERSEDED TO \d{6,8}", desc, re.I):
                continue  # not an identity row
            mc = [(i, n) for i, n in r["mcols"] if "WARRANTABLE" not in n.upper()]
            marked = [(n, r["marked"][i]) for i, n in mc if i in r["marked"]]
            text = desc
            if len(mc) > 1 and marked and len(marked) < len(mc) or any(v not in ("X", "x") for n, v in marked):
                text += " [models: " + ", ".join(n + ("" if v in ("X", "x") else f" x{v}") for n, v in marked) + "]"
            if star:
                text += f" ({stars_l[star]})"
            if shaded:
                text += f" ({shade_l})"
            kept.append((pi + 1, num, text))
    seen, lines, n = {}, [], 0
    for pg, num, text in kept:
        if num in seen:
            if seen[num] != text:
                held.append({"page": pg, "num": num, "why": "printed twice with different text (first kept)", "text": text})
            continue
        seen[num] = text; n += 1
        lines.append(f"{pg}|{n}|{num}|{text.replace('|', '/')}|0")
    # supersession chains: name from the row the chain ends on
    smap, targets = {}, {}
    for s in sups:
        smap.setdefault(s["legacy"], s)
        targets.setdefault(s["legacy"], set()).add(s["current"])
    for old, t in targets.items():  # the list names two different successors for one number: not loaded
        if len(t) > 1:
            held.append({"num": old, "why": "conflicting supersession targets " + ", ".join(sorted(t))})
            smap.pop(old, None)
    out_s = []
    for old, s in smap.items():
        tgt, hops = s["current"], 0
        while tgt in smap and hops < 5:
            tgt, hops = smap[tgt]["current"], hops + 1
        nm = re.sub(r" \[models:.*?\]| \((not available|no longer available|limited availability)\)", "", seen.get(tgt, ""))
        out_s.append(dict(s, chain_end=tgt, name=nm, storable=True))
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": rows_total,
           "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines), "supersessions": out_s, "held": held}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows_b": rows_total, "numbers": len(seen),
                      "supersessions": len(out_s), "held": held[:8], "diffs": diffs[:3]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
