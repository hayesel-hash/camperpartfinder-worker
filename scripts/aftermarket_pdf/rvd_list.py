"""Two-pass reader for the RV Designer Complete Parts List (RVD Part # | Quantity Per Pack | Description).
Pass A: text-line order. Pass B: word positions (part # column x < 110, qty column, description column).
Writes a supplied-documents JSON (rows as page|n|number|desc|sectioncode).
usage: python3 -I rvd_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf
PN = re.compile(r"^(?:[A-Z]{1,3}\d{1,5}[A-Z]?|Lid-?(?:Kit)?[A-Z]?\d{3}[A-Z]?)$")
QTY = re.compile(r"^\d{1,4}(?: [A-Za-z]{2,6}\.?)?$")
QNUM = re.compile(r"^\d{1,4}$")
SECT = re.compile(r"^[A-Z][A-Z /&-]{3,}$")
HEAD = {"v 03/2017", "RVD", "Part #", "Quantity", "Per Pack Description", "Quantity Per Pack Description"}

def section_of(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    return L[-1] if L and L[-1].isupper() and not PN.match(L[-1]) else ""

def pass_a(page, sec):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, k = [], 0
    while k < len(L):
        if PN.match(L[k]) and k + 2 < len(L) and QTY.match(L[k + 1]):
            num, qty, desc = L[k], L[k + 1], [L[k + 2]]
            j = k + 3
            while j < len(L) and not (PN.match(L[j]) and j + 1 < len(L) and QTY.match(L[j + 1])) and L[j] != sec and L[j] not in HEAD and not SECT.match(L[j]) and not L[j].startswith("v 03/2017"):
                desc.append(L[j]); j += 1
            rows.append((num, qty, " ".join(" ".join(desc).split())))
            k = j; continue
        k += 1
    return rows

def pass_b(page, sec):
    words = page.get_text("words")
    hq = [w for w in words if w[4] == "Quantity"]
    hd = [w for w in words if w[4] == "Description"]
    if not hq or not hd:
        return []
    xq, xd, ytop = hq[0][0], hd[0][0], hd[0][3]
    anchors = sorted(((w[1] + w[3]) / 2, w[4]) for w in words if w[0] < xq - 5 and PN.match(w[4]) and w[1] > ytop)
    qty, desc = {}, {i: [] for i in range(len(anchors))}
    for x0, y0, x1, y1, w, *_ in words:
        yc = (y0 + y1) / 2
        if y0 <= ytop or y0 > 735 or not anchors or (x0 < xq - 5):
            continue
        i = min(range(len(anchors)), key=lambda i: abs(anchors[i][0] - yc))
        if abs(anchors[i][0] - yc) >= 25 or w == sec:
            continue
        if x0 < xd - 2:
            qty[i] = (qty.get(i, "") + " " + w).strip()
        else:
            desc[i].append((round(y1), x0, w))
    out = []
    for i, (yc, num) in enumerate(anchors):
        if i not in qty or not QTY.match(qty[i]): continue
        out.append((num, qty[i], " ".join(w for y, x, w in sorted(desc[i]))))
    return out

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    allrows, diffs, secs = [], [], []
    for i, p in enumerate(d):
        sec = section_of(p)
        a, b = pass_a(p, sec), pass_b(p, sec)
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        for n, (num, qty, desc) in enumerate(a, 1):
            allrows.append((i + 1, n, num, qty, desc, sec))
            if sec not in secs: secs.append(sec)
    code = {s: format(i, "x") for i, s in enumerate(secs)}
    seen, lines = set(), []
    for pg, n, num, qty, desc, sec in allrows:
        if num in seen: continue
        seen.add(num)
        dd = desc.replace("|", "/") + (f" (quantity per pack: {qty})" if qty != "1" else "")
        lines.append(f"{pg}|{n}|{num}|{dd}|{code[sec]}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs, "diffs": diffs, "rows_total": len(allrows), "numbers": len(seen),
           "sections": {v: k for k, v in code.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": not diffs, "rows": len(allrows), "numbers": len(seen), "diffs": diffs[:3]}, ensure_ascii=False)[:2000])

if __name__ == "__main__":
    main(*sys.argv[1:3])
