"""Two-pass reader for Atwood range / cooktop "Parts Identification" tables (e.g. Model 21 Oven & Slide-In
Cooktop manual, effective 2.2.10): ITEM | DESCRIPTION | one column per model, each cell a 5-digit Atwood
number (or TBD / a diamond = "order by model, colour and style", which are skipped).

The page is often a two-up spread (English table on the left half, French text on the right), so only
words inside the table's column band are used.

Pass A: text lines from get_text(): an item line ("1", "2A", "38 A", "N/S"), a description line, then the
5-digit number lines of that row; a description line with no item line before it continues the previous
item (e.g. "Range Top - stainless steel" under item 4).
Pass B: word boxes grouped by baseline: item words left of the description column, description words up
to the first model column, numbers assigned to the nearest model column (header = the one or two label
rows above the first item, e.g. "RA" over "1721 2121"; labels are combined as printed, "RA 1721").

A (number, description) pair is kept only if both passes give it with the same item; the others are held.
Output: supplied-documents JSON (rows page|n|number|description|section); the section names the model
columns in which the number is printed on that row, as printed.
usage: python3 -I atwood_range_parts.py <pdf> <out.json> "<label>"
"""
import hashlib, json, re, sys

NUM = re.compile(r"^\d{5}$")
ITEM = re.compile(r"^(\d{1,2}(?: ?[A-D])?|\d{1,2}-[A-D]|N/S)$")
SKIP = {"TBD", "◆", "♦"}


def norm(s):
    return " ".join(s.split())


def fingerprint(text):
    L = [l.strip() for l in text.splitlines()]
    return ("Item" in L and "Description" in L and sum(1 for l in L if NUM.match(l)) >= 10)


def pass_a(text):
    L = [norm(l) for l in text.splitlines()]
    L = [l for l in L if l]
    try:
        k = L.index("Description")
    except ValueError:
        return []
    rows, item, cur = [], None, None
    for l in L[k + 1:]:
        if NUM.match(l):
            if cur is not None:
                cur[2].append(l)
            continue
        if l in SKIP:
            continue
        if ITEM.match(l):
            item = l.replace(" ", ""); cur = None
            continue
        if cur is not None and not cur[2] and not ITEM.match(l):
            # a description line directly after another with no numbers between: a header / stray line
            pass
        if len(l) > 70 or l.isupper() and len(l) > 30:
            if rows and cur is not None and not cur[2]:
                cur = None
            continue
        cur = [item, l, []]
        rows.append(cur)
    out = []
    for it, d, nums in rows:
        for n in dict.fromkeys(nums):
            out.append((it, d, n))
    return out


def pass_b(words):
    item_w = next((w for w in words if w[4] == "Item"), None)
    desc_w = next((w for w in words if w[4] == "Description"), None)
    if not item_w or not desc_w:
        return [], {}
    nums = [w for w in words if NUM.match(w[4]) and w[1] > desc_w[3]]
    if not nums:
        return [], {}
    xnum = min(w[0] for w in nums) - 6
    xmax = max(w[2] for w in nums) + 20
    band = [w for w in words if item_w[0] - 12 <= w[0] <= xmax]
    first_item_y = min((w[1] for w in band if ITEM.match(w[4]) and w[0] < desc_w[0] - 2 and w[1] > desc_w[3]),
                       default=desc_w[3] + 40)
    head = [w for w in band if w[0] >= xnum - 30 and item_w[1] - 14 <= w[1] < first_item_y - 2 and w[4] not in ("Item", "Description")]
    hrows = {}
    for w in head:
        hrows.setdefault(round(w[3]), []).append(w)
    ys = sorted(hrows)
    if not ys:
        return [], {}
    sub = sorted(hrows[ys[-1]], key=lambda w: w[0])
    grp = sorted(hrows[ys[-2]], key=lambda w: w[0]) if len(ys) > 1 else []
    cols = []
    for w in sub:
        cx = (w[0] + w[2]) / 2
        g = min(grp, key=lambda g: abs((g[0] + g[2]) / 2 - cx), default=None)
        label = (g[4].upper() + " " + w[4]) if g is not None else w[4]
        cols.append((cx, label))
    by = {}
    for w in band:
        if w[1] >= first_item_y - 2:
            by.setdefault(round(w[3]), []).append(w)
    rows, item = [], None
    for y in sorted(by):
        ws = sorted(by[y], key=lambda w: w[0])
        it = [w[4] for w in ws if w[2] <= desc_w[0] - 2]
        desc = [w[4] for w in ws if w[0] >= desc_w[0] - 2 and w[0] < xnum]
        ns = [w for w in ws if w[0] >= xnum and NUM.match(w[4])]
        if it and ITEM.match(" ".join(it)):
            item = "".join(it)
        if not desc:
            continue
        d = norm(" ".join(desc))
        for w in ns:
            cx = (w[0] + w[2]) / 2
            label = min(cols, key=lambda c: abs(c[0] - cx))[1]
            rows.append((item, d, w[4], label))
    out, models = [], {}
    for it, d, n, label in rows:
        key = (it, d, n)
        if key not in models:
            out.append(key); models[key] = []
        if label not in models[key]:
            models[key].append(label)
    return out, models


def read(pages):
    """pages: list of (text, words) -> rows [(page, n, number, desc, item, models)], held"""
    rows, held = [], []
    for i, (text, words) in enumerate(pages):
        if not fingerprint(text):
            continue
        a = pass_a(text)
        b, models = pass_b(words)
        bset = set(b)
        n = 0
        for key in a:
            if key in bset:
                n += 1; bset.discard(key)
                rows.append((i + 1, n, key[2], key[1], key[0], models[key]))
            else:
                held.append({"page": i + 1, "a": list(key)})
        held += [{"page": i + 1, "b": list(k)} for k in b if k in bset]
    return rows, held


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, held = read([(p.get_text(), p.get_text("words")) for p in doc])
    secs, seen, lines = {}, set(), []
    for pg, n, num, desc, item, models in rows:
        if num in seen:
            continue
        sec = label + " — models " + ", ".join(models)
        code = secs.setdefault(sec, str(len(secs)))
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')[:200]}|{code}")
    out = {"doc": sha, "pages": doc.page_count, "agree": bool(lines) and not held, "held": held,
           "rows_total": len(rows), "numbers": len(seen), "pages_read": sorted({r[0] for r in rows}),
           "sections": {c: s for s, c in secs.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "pages_read": out["pages_read"], "held": held[:10]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
