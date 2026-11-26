"""Two-pass reader for Norcold 1200-series 'CROSS REFERENCE - OBSOLETE DOORS' tables.
Pass A: text-line order. Pass B: word positions (row = same baseline, columns by x).
usage: python3 -I norcold_xref.py <pdf> <out.json>
"""
import hashlib, json, re, sys
import pymupdf

PN = re.compile(r"^\d{6}$")
COLOR = {"BLACK", "WHITE", "GRAY", "SS"}
REPL = re.compile(r"^(\d{6})(?:\s*,\s*(\d{6}))?$|^SEE NOTE")

def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, table, k = [], None, 0
    while k < len(L):
        l = L[k]
        if l == "PART #" and k + 1 < len(L):
            table = L[k + 1]; k += 2; continue
        if PN.match(l) and k + 5 < len(L) and L[k + 2] in COLOR and re.match(r"^\d{6,7}$", L[k + 3]) and re.match(r"^\d{6,7}$", L[k + 4]) and REPL.match(L[k + 5]):
            rows.append({"table": table, "part": l, "desc": L[k + 1], "color": L[k + 2], "from": L[k + 3], "to": L[k + 4],
                         "repl": re.sub(r"\s*,\s*", ", ", L[k + 5])})
            k += 6; continue
        k += 1
    return rows

def pass_b(page):
    words = page.get_text("words")
    lines = {}
    for x0, y0, x1, y1, w, *_ in words:
        lines.setdefault(round(y1), []).append((x0, w))
    out = []
    for y in sorted(lines):
        ws = sorted(lines[y])
        if not ws or not PN.match(ws[0][1]) or ws[0][0] > 80:
            continue
        rest = ws[1:]
        # colour column is the first token that is a colour after the description
        ci = next((i for i, (x, w) in enumerate(rest) if w in COLOR and x > 250), None)
        if ci is None or len(rest) < ci + 4:
            continue
        desc = " ".join(w for x, w in rest[:ci])
        tail = [w for x, w in rest[ci + 1:]]
        out.append((ws[0][1], desc, rest[ci][1], tail[0], tail[1], re.sub(r"\s*,\s*", ", ", " ".join(tail[2:]).replace(" ,", ","))))
    return out

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    res = []
    agree = True; diffs = []
    for i, p in enumerate(d):
        t = p.get_text()
        if "CROSS REFERENCE - OBSOLETE" not in t:
            continue
        title = next(l.strip() for l in t.splitlines() if "CROSS REFERENCE" in l)
        a = pass_a(p); b = pass_b(p)
        ka = [(r["part"], r["desc"], r["color"], r["from"], r["to"], r["repl"]) for r in a]
        kb = [(x[0], x[1], x[2], x[3], x[4], x[5].replace("SEE NOTE “A”", "SEE NOTE “A”")) for x in b]
        norm = lambda r: tuple(" ".join(str(v).split()) for v in r)
        if [norm(x) for x in ka] != [norm(x) for x in kb]:
            agree = False
            diffs.append({"page": i + 1, "only_a": [x for x in map(norm, ka) if x not in map(norm, kb)], "only_b": [x for x in map(norm, kb) if x not in list(map(norm, ka))]})
        notes = [l.strip() for l in t.splitlines() if l.strip().upper().startswith(("NOTE", "“NOTE"))]
        for r in a:
            r.update({"page": i + 1, "title": title, "notes": notes})
            res.append(r)
    json.dump({"sha256": sha, "agree": agree, "diffs": diffs, "rows": res}, open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "agree": agree, "rows": len(res), "pages": sorted({r["page"] for r in res}),
                      "diffs": diffs[:3]}, ensure_ascii=False)[:1500])

if __name__ == "__main__":
    main(*sys.argv[1:3])
