"""Two-pass reader for Webasto multilingual "Spare parts list" PDFs (InDesign layout, e.g. Air Top Evo 40/55, Thermo Top
Evo 4/5/5+): landscape table pages "Pos. | one rotated column per heater version (filled square glyph = fitted) |
Part no. | Description | Beschreibung | Description | Descrizione | Beskrivning". Chapter headings ("2 Parts for heater /
Teile zum Heizgerät / ...") sit on the drawing page before the table.

Pass A: text-line order: Pos line, one glyph line per marked version (blank cells write nothing), the part number,
then the English description line. Pass B: word boxes: number under "Part no.", English words between the first
"Description" header and "Beschreibung" whose centre lies in the row band (half-way to the neighbouring rows; cells are
vertically centred), glyphs on the number's line mapped to the nearest rotated version header.
A row is kept only when both passes give the same Pos, number, English description and number of marks. The versions
marked (from pass B, checked against the header names read in pass A) are appended as " [models: ...]" when not all
are marked. Section = English part of the last chapter heading.
Output: supplied-documents JSON (rows page|n|number|description|section).
usage: python3 -I webasto_spare_parts_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

POS = re.compile(r"^(\d{1,3}[a-z]?|-)$")
NUM = re.compile(r"^\d{6,8}[A-Z]?$")
GLYPH = ""
CHAPTER = re.compile(r"(?:^|\n)[ \t]*(\d{1,2})[ \t]*\n?[ \t]*([A-Z][^/\n]+?)[ \t]*/[ \t]*[A-ZÄÖÜ]")


def norm(s):
    return " ".join(s.split())


def header_a(L):
    """-> (index after the 5 language headers, version names) from text lines"""
    if "Pos." not in L or "Part no." not in L:
        return None, []
    i, j = L.index("Pos."), L.index("Part no.")
    names = L[i + 1:j]
    k = j + 1
    while k < len(L) and L[k] in ("Description", "Beschreibung", "Descrizione", "Beskrivning"):
        k += 1
    return k, names


def pass_a(page):
    L = [norm(l) for l in page.get_text().splitlines()]
    L = [l for l in L if l]
    k, names = header_a(L)
    if k is None:
        return [], names
    rows = []
    while k < len(L):
        if POS.match(L[k]):
            j, marks = k + 1, 0
            while j < len(L) and L[j] == GLYPH:
                marks += 1; j += 1
            if j + 1 < len(L) and NUM.match(L[j]):
                rows.append((L[k], L[j], L[j + 1], marks)); k = j + 2; continue
        k += 1
    return rows, names


def pass_b(page):
    W = page.get_text("words")
    pos_h = next((w for w in W if w[4] == "Pos."), None)
    part_h = next((w for w in W if w[4] == "Part" and any(v[4] == "no." and abs(v[3] - w[3]) < 2 for v in W)), None)
    if not pos_h or not part_h:
        return [], []
    desc_h = sorted([w for w in W if w[4] == "Description" and abs(w[3] - part_h[3]) < 3], key=lambda w: w[0])
    besch = next((w for w in W if w[4] == "Beschreibung" and abs(w[3] - part_h[3]) < 3), None)
    if not desc_h or not besch:
        return [], []
    en_x0, en_x1 = desc_h[0][0] - 3, besch[0] - 3
    # rotated version headers between Pos. and Part no.: group words by x centre
    nums = sorted([w for w in W if NUM.match(w[4]) and part_h[0] - 5 <= w[0] < en_x0 and w[1] > part_h[3]], key=lambda w: w[1])
    if not nums:
        return [], []
    # rotated labels hang down from the header bar's top to just above the first row
    hv = [w for w in W if pos_h[2] < (w[0] + w[2]) / 2 < part_h[0] and w[1] >= pos_h[1] - 5 and w[3] <= nums[0][1] - 1
          and w[4] != GLYPH]
    cols = []
    for w in sorted(hv, key=lambda w: (w[0] + w[2]) / 2):
        cx = (w[0] + w[2]) / 2
        if cols and abs(cols[-1][0] - cx) < 3:
            cols[-1][1].append(w)
        else:
            cols.append([cx, [w]])
    names = [norm(" ".join(x[4] for x in sorted(ws, key=lambda w: -w[3]))) for cx, ws in cols]
    cxs = [c[0] for c in cols]
    if not cxs:
        return [], names
    rows = []
    for k, n in enumerate(nums):
        y = (n[1] + n[3]) / 2
        top = (y + (nums[k - 1][1] + nums[k - 1][3]) / 2) / 2 if k else n[1] - 12
        bot = (y + (nums[k + 1][1] + nums[k + 1][3]) / 2) / 2 if k + 1 < len(nums) else n[3] + 12
        pos = [w[4] for w in W if w[2] <= pos_h[2] + 6 and abs((w[1] + w[3]) / 2 - y) < 3 and POS.match(w[4])]
        en = sorted([w for w in W if en_x0 <= w[0] and w[2] <= en_x1 and top <= (w[1] + w[3]) / 2 < bot],
                    key=lambda w: (round(w[3]), w[0]))
        g = [w for w in W if w[4] == GLYPH and abs((w[1] + w[3]) / 2 - y) < 3 and pos_h[2] < w[0] < part_h[0]]
        marked = sorted({min(range(len(cxs)), key=lambda i: abs(cxs[i] - (w[0] + w[2]) / 2)) for w in g})
        rows.append(((pos[0] if pos else "?"), n[4], norm(" ".join(w[4] for w in en)), len(g), tuple(marked)))
    return rows, names


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    if not d.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, diffs, sections, unread, chapter = [], [], {}, [], ""
    for i, p in enumerate(d):
        for m in CHAPTER.finditer(p.get_text()):
            chapter = norm(m.group(2))
        a, names_a = pass_a(p)
        b, names_b = pass_b(p)
        if not a and not b:
            continue
        if names_a != names_b:
            diffs.append({"page": i + 1, "names_a": names_a, "names_b": names_b}); continue
        bk = {(r[0], r[1], r[2], r[3]): r[4] for r in b}
        good = [r for r in a if r in bk]
        if len(good) != len(a) or len(good) != len(b):
            diffs.append({"page": i + 1, "only_a": [r for r in a if r not in bk][:4],
                          "only_b": [r[:4] for r in b if r[:4] not in set(a)][:4]})
        kept = {r[1] for r in good}
        unread += [{"page": i + 1, "number": r[1]} for r in b if r[1] not in kept]
        if chapter not in sections.values():
            sections[str(len(sections) + 1)] = chapter
        code = next(k for k, v in sections.items() if v == chapter)
        for n, r in enumerate(good, 1):
            marked = bk[r]
            mods = "" if len(marked) == len(names_b) else " [models: " + ", ".join(names_b[x] for x in marked) + "]"
            rows.append((i + 1, n, r[1], r[2] + mods, code))
    seen, lines = set(), []
    for pg, n, num, desc, code in rows:
        if num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{code}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines) and not any("names_a" in x for x in diffs),
           "diffs": diffs, "rows_total": len(rows), "numbers": len(seen), "unread": unread, "sections": sections,
           "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "sections": sections, "unread": unread[:6], "diffs": diffs[:3]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
