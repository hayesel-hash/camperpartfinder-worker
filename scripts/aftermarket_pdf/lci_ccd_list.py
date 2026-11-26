"""Two-pass reader for Lippert (LCI) component lists, CCD-000xxxx ("Callout | Part # | Description | Quantity").
Pass A: text-line order. Pass B: word positions (part # column between the "Part" header and "Description").
Literature numbers (CCD-...) are not parts and are skipped. Writes a supplied-documents JSON
(rows as page|n|number|desc|sectioncode). usage: python3 -I lci_ccd_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf
PN = re.compile(r"^\d{5,10}$")
CALL = re.compile(r"^[A-Z]{1,2}$")
QTY = re.compile(r"^\d{1,3}$")
STOP = re.compile(r"^(Rev:|Web:|AWNINGS$|CCD-\d+$)")

def title_of(doc):
    p = doc[0]
    big = [w for w in p.get_text("words") if w[1] < 60 and (w[3] - w[1]) > 18]
    return " ".join(w[4] for w in sorted(big, key=lambda w: (round(w[1] / 10), w[0])))

def table_lines(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if "Quantity" not in L or "Callout" not in L:
        return []
    return L[L.index("Quantity") + 1:]

def pass_a(page):
    L, rows, k = table_lines(page), [], 0
    while k < len(L):
        if PN.match(L[k]):
            num, desc, j = L[k], [], k + 1
            while j < len(L) and not PN.match(L[j]) and not L[j].startswith("CCD-") and not STOP.match(L[j]):
                if QTY.match(L[j]) and (j + 1 >= len(L) or CALL.match(L[j + 1]) or PN.match(L[j + 1]) or L[j + 1].startswith("CCD-")):
                    j += 1; break
                if CALL.match(L[j]) and j + 1 < len(L) and (PN.match(L[j + 1]) or L[j + 1].startswith("CCD-")):
                    break
                desc.append(L[j]); j += 1
            rows.append((num, " ".join(" ".join(desc).split())))
            k = j; continue
        k += 1
    return rows

def pass_b(page):
    W = page.get_text("words")
    hp = [w for w in W if w[4] == "Part"]; hd = [w for w in W if w[4] == "Description"]; hq = [w for w in W if w[4] == "Quantity"]
    if not (hp and hd and hq): return []
    xp, xd, xq, ytop = hp[0][0] - 10, hd[0][0] - 5, hq[0][0] - 5, hd[0][3]
    nums = sorted(((w[1] + w[3]) / 2, w[4]) for w in W if w[1] > ytop and ((xp <= w[0] < xd and PN.match(w[4])) or (xp - 40 <= w[0] < xd and w[4].startswith("CCD-"))))
    if not nums: return []
    desc = {i: [] for i in range(len(nums))}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 <= ytop or not (xd <= x0 < xq) or y0 > 750: continue
        yc = (y0 + y1) / 2
        i = min(range(len(nums)), key=lambda i: abs(nums[i][0] - yc))
        if abs(nums[i][0] - yc) < 20: desc[i].append((y0, x0, w))
    return [(n, lines_text(desc[i])) for i, (yc, n) in enumerate(nums) if PN.match(n)]

def lines_text(ws):
    out, cur, cy = [], [], None
    for y, x, w in sorted(ws):
        if cy is not None and y - cy > 4:
            out.append(cur); cur = []
        if not cur: cy = y
        cur.append((x, w))
    if cur: out.append(cur)
    return " ".join(w for line in out for x, w in sorted(line))

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); sec = title_of(d)
    rows, diffs = [], []
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        if a != b: diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        rows += [(i + 1, n, num, desc) for n, (num, desc) in enumerate(a, 1)]
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen or not desc: continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"0": sec}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "title": sec, "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "diffs": diffs[:2]}, ensure_ascii=False)[:1500])

if __name__ == "__main__":
    main(*sys.argv[1:3])
