"""Reader for Dometic Seitz "DOK" spare-parts sheets for windows and rooflights (S4, S5, S7, Midi Heki, Mini Heki plus):
ruled tables "[Code/item] | Description | Part No. (or Code) | Pack. Unit" under an exploded drawing.

Seitz codes such as "BG 1517" are printed with and without the space in the same document (Midi Heki p5 "BG1517",
p6 "BG 1517"), so the space after the letter prefix is removed. Codes that are not complete numbers are reported, not
loaded: size/colour placeholders ("BG1086...", "IRE05...", "BG2577.."), alternatives ("FM80/82", "FM 12/20"), and codes
with any other space or ":" ("BG 70 Z", "PP 48:..Z"). Pack units are dropped.

Geometry (shared by both passes): table header line = "Description" + "Pack." + a "Part No." or "Code" header right of
Description; columns from the vertical rules crossing the header line; table bottom = lowest end of those rules.
Rows: a text line inside the table starts a row when it has a part-number cell or an item number; other lines continue
the row above (wrapped descriptions). Rows without a part number ("only as complete frame available") are dropped.
Pass A reads pdfplumber words, pass B pymupdf words over the same geometry; only rows both give identically are kept.
usage: python3 -I seitz_spare_parts.py <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf, pdfplumber

ITEM = re.compile(r"^\d{1,2}[a-z]?$")
PREFIX = re.compile(r"^([A-Z]{2,4}) (\d)")
GOOD = re.compile(r"^[A-Z]{1,4}\d[A-Z0-9-]{1,14}$")


def vrules(page):
    out = []
    for g in page.get_drawings():
        for it in g["items"]:
            if it[0] == "l":
                p, q = it[1], it[2]
                if abs(p.x - q.x) < 0.8 and abs(p.y - q.y) > 3:
                    out.append(((p.x + q.x) / 2, min(p.y, q.y), max(p.y, q.y)))
            elif it[0] == "re":
                r = it[1]
                if r.width < 1.6 and r.height > 3:
                    out.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
    return out


def tables(page):
    """[(ytop, ybot, item_col, desc_col, pn_col, pack_col)] with columns as (x0, x1)"""
    W = page.get_text("words")
    V = vrules(page)
    out = []
    for d in W:
        if d[4] != "Description":
            continue
        line = [w for w in W if abs((w[1] + w[3]) / 2 - (d[1] + d[3]) / 2) < 4]
        pk = [w for w in line if w[4].startswith("Pack")]
        pn = [w for w in line if w[4] in ("Part", "Part-No.", "Code") and w[0] > d[2]]
        if not pk or not pn:
            continue
        yc = (d[1] + d[3]) / 2
        cross = [v for v in V if v[1] <= yc + 1 and v[2] >= yc - 1]
        xs = []
        for x in sorted(v[0] for v in cross):
            if not xs or x - xs[-1] > 2:
                xs.append(x)
        if len(xs) < 4:
            continue
        cols = list(zip(xs, xs[1:]))
        def col(x):
            return next((c for c in cols if c[0] <= x <= c[1]), None)
        dc, pc, kc = col((d[0] + d[2]) / 2), col((pn[0][0] + pn[0][2]) / 2), col((pk[0][0] + pk[0][2]) / 2)
        if not (dc and pc and kc) or len({dc, pc, kc}) < 3:
            continue
        left = [c for c in cols if c[1] <= dc[0] + 0.5]
        ic = left[-1] if left else None
        # rules are often drawn one row at a time: follow the rule on the part-number column's left edge downwards
        ybot = max(v[2] for v in cross if abs(v[0] - pc[0]) < 1.5)
        segs = sorted((v for v in V if abs(v[0] - pc[0]) < 1.5), key=lambda v: v[1])
        for v in segs:
            if v[1] <= ybot + 2.5 and v[2] > ybot:
                ybot = v[2]
        out.append((d[3] + 1, ybot, ic, dc, pc, kc))
    return out


def rows_from_words(words, tabs):
    rows = []
    for ytop, ybot, ic, dc, pc, kc in tabs:
        ws = [w for w in words if ytop < (w[1] + w[3]) / 2 < ybot]
        lines = []
        for w in sorted(ws, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
            yc = (w[1] + w[3]) / 2
            if lines and abs(yc - lines[-1][0]) < 3:
                lines[-1][1].append(w)
            else:
                lines.append([yc, [w]])
        cur = None
        for yc, lw in lines:
            inn = lambda c, w: c is not None and c[0] - 1 <= (w[0] + w[2]) / 2 <= c[1] + 1
            item = [w[4] for w in lw if inn(ic, w) and ITEM.match(w[4])]
            pn = " ".join(w[4] for w in sorted(lw, key=lambda w: w[0]) if inn(pc, w))
            desc = " ".join(w[4] for w in sorted(lw, key=lambda w: w[0]) if inn(dc, w))
            if pn or item:
                if cur:
                    rows.append(cur)
                cur = {"item": item[0] if item else "", "pn": pn, "desc": desc}
            elif cur and desc:
                cur["desc"] = (cur["desc"] + " " + desc).strip()
        if cur:
            rows.append(cur)
    return [(r["item"], r["pn"], " ".join(r["desc"].split())) for r in rows]


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    if not d.permissions & pymupdf.PDF_PERM_COPY:
        print(json.dumps({"sha": sha, "error": "copy-protected"})); return
    pl = pdfplumber.open(pdf)
    kept, diffs, skipped = [], [], []
    for i, p in enumerate(d):
        tabs = tables(p)
        if not tabs:
            continue
        b = rows_from_words(p.get_text("words"), tabs)
        a = rows_from_words([(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in pl.pages[i].extract_words(keep_blank_chars=False, use_text_flow=False)], tabs)
        loadable = lambda rows: [x for x in rows if x[1] and GOOD.match(PREFIX.sub(r"\1\2", x[1])) and x[2]]
        if loadable(a) != loadable(b):  # rows that are not loaded anyway (placeholders) may differ in spacing only
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        for item, pn, desc in [x for x in b if x in a]:
            if not pn:
                continue
            num = PREFIX.sub(r"\1\2", pn)
            if not GOOD.match(num) or not desc:
                skipped.append({"page": i + 1, "printed": pn, "desc": desc}); continue
            kept.append((i + 1, num, desc))
    seen, lines, held, n = {}, [], [], 0
    # one number printed on the same page against two different rows (S6 p9: BG1078 = right hand and left hand
    # handle) is a contradiction on the page: not loaded. Reprints on other pages keep the first printing.
    clash = {num for pg, num, desc in kept for pg2, num2, desc2 in kept if num == num2 and pg == pg2 and desc != desc2}
    for pg, num, desc in kept:
        if num in clash:
            held.append({"page": pg, "num": num, "why": "same number printed for different rows on one page", "text": desc}); continue
        if num in seen:
            if seen[num] != desc:
                held.append({"page": pg, "num": num, "why": "printed again with different text (first kept)", "text": desc})
            continue
        seen[num] = desc; n += 1
        lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "numbers": len(seen),
           "sections": {"0": section}, "rows": "\n".join(lines), "not_loaded": skipped, "held": held}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "numbers": len(seen), "not_loaded": len(skipped),
                      "held": len(held), "diffs": diffs[:3]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
