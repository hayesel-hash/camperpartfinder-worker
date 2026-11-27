"""Two-pass reader for Flojet (Xylem) RV pump datasheets, page "Pump Service Kits & Spares" / "Accessories", e.g.
R3426504A Rev. A 04/2024:
  - Accessories: "<number> <description>" lines (stored as "<section heading>: <description>", plus "(2-pack kit)"
    where the section's note says "All part numbers are 2-pack kits") (number column x ~120, description x ~169-318) in sections separated
    by full-width rules; the section heading sits in the left column of its band ("Accumulator", "Strainers (Required
    in all applications)", "Port Fittings", "Water Pressure Regulators"). The notes column (x >= 320) is not read.
  - Service kits: ITEM | PART NUMBER | DESCRIPTION; the item name (left column) is the description, the DESCRIPTION
    column text inside the item's row band is appended in parentheses.
Pass A pymupdf words + drawings, pass B pdfplumber words + lines/rects; a row is kept only if both passes give the
same (section, number, description). Every other Flojet-style number on the page is reported as unread.
usage: python3 -I flojet_datasheet_accessories.py <pdf> <out.json> "<label>"
"""
import hashlib, json, re, sys

NUM = re.compile(r"^\d{6,9}[A-Z]?$")


def norm(s):
    return " ".join(s.split())


def lines(words):
    out, cur = [], None
    for w in sorted(words, key=lambda w: (w[3], w[0])):
        if cur is None or w[3] - cur[0] > 1.5:
            cur = [w[3], []]; out.append(cur)
        cur[1].append(w)
    return [(y, sorted(l, key=lambda w: w[0])) for y, l in out]


def read(words, rules):
    """words (x0, y0, x1, y1, text); rules: y of full-width horizontal rules -> rows [(section, number, desc)]"""
    rows = []
    acc = next((w for w in words if w[4] == "Accessories"), None)
    if acc is not None:
        rs = sorted(r for r in rules if r > acc[3])
        for y0, y1 in zip(rs, rs[1:]):
            band = [w for w in words if y0 < (w[1] + w[3]) / 2 < y1]
            sec = norm(" ".join(w[4] for _, ln in lines([w for w in band if w[0] < 110]) for w in ln))
            short = norm(re.sub(r"\(.*?\)", "", re.sub(r"^Freshwater Delivery System\s*", "", sec)))
            notes = norm(" ".join(w[4] for _, ln in lines([w for w in band if w[0] >= 318]) for w in ln))
            kit = " (2-pack kit)" if "All part numbers are 2-pack kits" in notes else ""
            for _, ln in lines(band):
                nums = [w for w in ln if 110 <= w[0] < 160 and NUM.match(w[4])]
                if len(nums) != 1:
                    continue
                desc = norm(" ".join(w[4] for w in ln if 160 <= w[0] < 318))
                if desc:
                    rows.append((sec, nums[0][4], (short + ": " if short else "") + desc + kit))
    head = next((w for w in words if w[4] == "ITEM"), None)
    pn = next((w for w in words if w[4] == "PART" and head and abs(w[3] - head[3]) < 3), None)
    dh = next((w for w in words if w[4] == "DESCRIPTION" and head and abs(w[3] - head[3]) < 3), None)
    if head and pn and dh:
        end = min((w[1] for w in words if w[4] == "Exploded" and w[1] > head[3]), default=1e9)
        nums = sorted((w for w in words if head[3] < w[1] < end and abs(w[0] - pn[0]) < 8 and NUM.match(w[4])),
                      key=lambda w: w[1])
        items = sorted((w for w in words if head[3] < w[1] < end and w[0] < pn[0] - 8
                        and re.match(r"^\d\.", w[4])), key=lambda w: w[1])
        if len(items) == len(nums):
            for k, (it, n) in enumerate(zip(items, nums)):
                y0 = it[1] - 2
                y1 = items[k + 1][1] - 2 if k + 1 < len(items) else end
                name = norm(" ".join(w[4] for _, ln in lines([w for w in words if y0 <= w[1] < y1 and w[0] < pn[0] - 8])
                                     for w in ln))
                name = re.sub(r"^\d\.\s*", "", name)
                dl = lines([w for w in words if y0 - 6 <= w[1] < y1 - 6 and w[0] >= dh[0] - 4])
                # a line holding only a bare digit is an exploded-view callout, not description text
                desc = norm(" ".join(w[4] for _, ln in dl if not (len(ln) == 1 and re.fullmatch(r"\d", ln[0][4]))
                                     for w in ln))
                rows.append(("Pump Service Kits & Spares", n[4], name + (" (" + desc + ")" if desc else "")))
    return rows


def main(pdf, outp, label):
    import pymupdf, pdfplumber
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    out, held, unread = [], [], []
    with pdfplumber.open(pdf) as pl:
        for pi, page in enumerate(doc):
            wa = [w[:5] for w in page.get_text("words")]
            if not any(w[4] == "Accessories" for w in wa):
                continue
            ra = sorted({round(g["rect"].y0) for g in page.get_drawings()
                         if g["rect"].height < 2 and g["rect"].width > 400})
            pp = pl.pages[pi]
            wb = [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in pp.extract_words()]
            rb = sorted({round(o["top"]) for o in pp.lines + pp.rects
                         if abs(o["bottom"] - o["top"]) < 2 and o["x1"] - o["x0"] > 400})
            a, b = read(wa, ra), read(wb, rb)
            bl = list(b)
            for r in a:
                if r in bl:
                    bl.remove(r); out.append((pi + 1, r))
                else:
                    held.append({"page": pi + 1, "a": list(r)})
            held += [{"page": pi + 1, "b": list(r)} for r in bl]
            got = {r[1] for r in a}
            unread += [{"page": pi + 1, "number": w[4]} for w in wa if NUM.match(w[4]) and w[4] not in got]
    secs, rows, seen = {}, [], set()
    for n, (pg, (sec, num, desc)) in enumerate(out, 1):
        if num in seen:
            continue
        seen.add(num)
        code = secs.setdefault(label + " — " + sec, str(len(secs)))
        rows.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')[:200]}|{code}")
    res = {"doc": sha, "pages": doc.page_count, "agree": bool(rows) and not held, "held": held, "unread": unread,
           "numbers": len(rows), "sections": {c: s for s, c in secs.items()}, "rows": "\n".join(rows)}
    json.dump(res, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": res["agree"], "numbers": len(rows), "held": held[:8],
                      "unread": unread[:10]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
