"""Shurflo RV catalogue product tables -> identities. Words grouped by row band; a row starts at a model
number in the 'Model #' column; the name is the text left of it in the same band; a bracketed number
right after the OEM number is the aftermarket version."""
import re, sys, json, hashlib, pymupdf
MN = re.compile(r"^[\(\[]?(\d{2,6}-[0-9A-Z]{2,4}(?:-[0-9A-Z]{2,3})?)[\)\]]?$")
PAGES = [6, 7, 8, 9, 10, 12, 14]
def rows_of(page):
    W = page.get_text("words")
    heads = [w for w in W if w[4] == "Model"]
    out = []
    for h in heads:
        xm = h[0] - 25
        # table region: below this header, until next header below
        below = [g for g in heads if g[1] > h[1] + 5 and abs(g[0] - h[0]) < 60]
        ybot = min([g[1] for g in below] + [page.rect.height - 60])
        cand = sorted([w for w in W if xm <= w[0] <= h[0] + 70 and h[3] + 2 < w[1] < ybot and MN.match(w[4])], key=lambda w: w[1])
        used = set()
        for w in cand:
            if id(w) in used: continue
            num = MN.match(w[4]).group(1)
            if w[4].startswith(("(", "[")) and not any(abs(c[1] - w[1]) < 1 for c in cand if c is not w):
                # bracket-only row (aftermarket-only item, e.g. hose nozzle)
                pass
            yc = (w[1] + w[3]) / 2
            nxt = [c for c in cand if c is not w and 0 < c[1] - w[1] < 12 and c[4].startswith(("(", "["))]
            aft = MN.match(nxt[0][4]).group(1) if nxt else None
            if nxt: used.add(id(nxt[0]))
            name = [x for x in W if x[2] < w[0] - 3 and x[0] > 150 and abs((x[1] + x[3]) / 2 - yc) < 11 and not re.fullmatch(r"[A-D—]", x[4])]
            name = " ".join(x[4] for x in sorted(name, key=lambda x: (round(x[1] / 4), x[0])))
            out.append((num, aft if aft != num else None, name.strip()))
    return out
if __name__ == "__main__":
    d = pymupdf.open(sys.argv[1])
    for p in PAGES:
        for r in rows_of(d[p - 1]): print(p, r)
