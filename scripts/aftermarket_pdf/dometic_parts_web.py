"""Two-pass reader for short Dometic North-America A/C service-part tables with numbers like 3315332.000:
"Dometic Parts Web" exports (Pos | PartNo | Qty | Description | Specification, e.g. Brisk II B59516) and the
PowerPoint sheets (ID | SERVICE PART | DESCRIPTION, e.g. Penguin II 641935).

Pass A: text-line order (a row is a Pos/ID line followed by a part-number line; description lines follow until the
next such pair). Pass B: word boxes; the part-number column and the description column are located from the
header words, wrapped description lines are attached to the part number above. "NO LONGER AVAILABLE" is kept as
the printed description. Only rows on which both passes agree are kept.
usage: python3 -I dometic_parts_web.py <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^\d{7}\.\d{3}$")
POS = re.compile(r"^\d{1,3}[A-Z]?$")
STOP = re.compile(r"^(\d\d/\d\d/\d{4}|©.*|\d+)$")


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, k = [], 0
    while k < len(L):
        if k + 1 < len(L) and POS.match(L[k]) and NUM.match(L[k + 1]):
            num, desc, j = L[k + 1], [], k + 2
            while j < len(L):
                if j + 1 < len(L) and POS.match(L[j]) and NUM.match(L[j + 1]):
                    break
                if NUM.match(L[j]) or re.match(r"^\d\d/\d\d/\d{4}$", L[j]) or L[j].startswith("©"):
                    break
                desc.append(L[j]); j += 1
            rows.append((num, " ".join(" ".join(desc).split())))
            k = j; continue
        k += 1
    return rows


def pass_b(page):
    W = page.get_text("words")
    dh = [w for w in W if w[4].lower() == "description"]
    if not dh:
        return []
    yh = dh[0][1]; xd = dh[0][0] - 3
    nums = [w for w in W if NUM.match(w[4]) and w[1] > yh]
    if not nums:
        return []
    xn = min(w[0] for w in nums) - 3
    # description words: left edge at or right of the description column (the Penguin sheet indents descriptions)
    dcol = min((w[0] for w in W if w[1] > yh + 5 and w[0] >= xd - 110 and not NUM.match(w[4]) and not POS.match(w[4])
                and w[0] > xn + 60), default=xd)
    rows = sorted(((w[1], w[4]) for w in nums))
    y_last = rows[-1][0]
    desc = {i: [] for i in range(len(rows))}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 <= yh + 2 or x0 < dcol - 3:
            continue
        cand = [i for i, (y, n) in enumerate(rows) if y <= y0 + 2]
        if not cand:
            continue
        i = cand[-1]
        nxt = rows[i + 1][0] if i + 1 < len(rows) else y_last + 45  # last row: at most ~3 wrapped lines, never the footer
        if y0 < nxt - 2:
            desc[i].append((y0, x0, w))
    out = []
    for i, (y, n) in enumerate(rows):
        ws = sorted(desc[i])
        out.append((n, " ".join(" ".join(w for _, _, w in ws).split())))
    return out


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs = [], []
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        rows += [(i + 1, n, num, desc) for n, (num, desc) in enumerate([x for x in a if x in b], 1)]
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen or not desc:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "diffs": diffs[:2]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
