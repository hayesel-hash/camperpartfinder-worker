"""Two-pass reader for Eberspaecher "SPARE PARTS LIST" PDFs (Airtronic S2/M2 North-America web edition, Airtronic S3/M3
Commercial): Item No. | [Quantity per unit | Quantity per SU] | Designation | Order No. (SU) | one dot column per heater.

Each item prints one or more designation blocks and one order number per line. A number takes the designation block of
its item whose first line is at or above the number's baseline (the "Blower 24 V ..." block starts on the line of the
first 24 V number). A designation line starting with an upper-case letter or digit begins a new block unless the
line above ends a sentence-in-progress ("and", ",", "-", "incl."); lines starting lower-case or "(" continue the block.
Unit dots are not read (identity only). A number printed under two different designations (890.31.054 "Fuel pipe,
intake line" / "Fuel pipe, discharge line 4 x 1 mm") is reported and not loaded; so is a number whose designation is only
a size/variant line printed under the item's base designation ("4 x 1.25 mm", "Ø 90 mm"). Cover-page heater lists ("Airtronic S3  D2L  12 V ... 25.2953.05.0000") are
read too, as the heater units' own order numbers.

Numbers must match ^\\d{2,3}(\\.\\d{2,4}){2,4}$; numbers printed with spaces ("10 2068 01 10 98") are reported, not
loaded. Items with no designation text (drawn as a picture or "Item 8" references) are reported as `no_name`.
Pass A: pymupdf words; pass B: pdfplumber words; same geometry rules; only rows on which both agree are kept.
pdfplumber decodes some glyphs of the UniversNext font in lower case ("order", "Airtronic m3") where pymupdf and the
rendered page show upper case, and splits a few words ("hos e"): rows are compared case-folded with spaces removed,
and pass A's text (checked against the page image) is stored.

usage: python3 -I eberspacher_spare_parts_list.py <pdf> <out.json> "<section label>"
"""
import hashlib, json, re, sys
import pymupdf, pdfplumber

NUM = re.compile(r"^\d{2,3}(?:\.\d{2,4}){2,4}$")
SPACED = re.compile(r"\b\d{2} \d{4} \d{2} \d{2} \d{2}\b")
ITEM = re.compile(r"^\d{1,3}[a-z]?$")
CONT_END = re.compile(r"(\band|,|-|\bincl\.|\bwith|\bfor)$")
HEATER = re.compile(r"^(Airtronic|Hydronic)\b", re.I)


def lines_of(words, tol=2.5):
    out = []
    for w in sorted(words, key=lambda w: (w[3], w[0])):
        if out and abs(out[-1][0] - w[3]) < tol:
            out[-1][1].append(w)
        else:
            out.append([w[3], [w]])
    return [(y, sorted(ws, key=lambda w: w[0])) for y, ws in out]


def read_page(words):
    """words: list of (x0, y0, x1, y1, text). Returns (rows, cover_rows, spaced, no_name)."""
    hdr_d = [w for w in words if w[4].lower() == "designation"]
    hdr_o = [w for w in words if w[4].lower() == "order" and any(v[4].lower() == "no." and abs(v[3] - w[3]) < 2 and 0 < v[0] - w[2] < 8
                                                       for v in words)]
    rows, no_name = [], []
    if hdr_d and hdr_o:
        yd = max(hdr_d[0][3], hdr_o[0][3])
        xd, xo = hdr_d[0][0] - 2, hdr_o[0][0] - 3
        x_item_max = xd - 15
        body = [w for w in words if w[1] > yd + 1 and not w[4].startswith("Spare") and w[3] < 800]
        items = sorted([w for w in body if w[0] < 60 and ITEM.match(w[4])], key=lambda w: w[1])
        nums = [w for w in body if xo <= w[0] < xo + 85 and NUM.match(w[4])]
        dwords = [w for w in body if xd <= w[0] < xo - 2]
        # stop at the page footer (line "Spare parts list | ..." or the page number) – footer words sit below 790
        dlines = lines_of(dwords)
        for k, it in enumerate(items):
            y0 = it[1] - 2
            y1 = items[k + 1][1] - 2 if k + 1 < len(items) else 790
            blocks = []
            for y, ws in dlines:
                if not (y0 <= y - 5 < y1):
                    continue
                text = " ".join(w[4] for w in ws)
                first = text[:1]
                repeat = bool(blocks) and text.split()[0].casefold() == blocks[0][1].split()[0].casefold()
                starts_new = not blocks or ((first.isupper() or first.isdigit() or repeat)
                                            and not CONT_END.search(blocks[-1][1]))
                if starts_new:
                    # a block that starts with a size ("4 x 1.25 mm", "70 – 90 mm", "Ø 75 mm") is a variant line of the
                    # item's base designation printed in a right-hand sub-column: reported, not loaded
                    blocks.append([ws[0][1], text, bool(blocks) and (first.isdigit() or first in "Ø–-")])
                else:
                    blocks[-1][1] = blocks[-1][1] + " " + text
            for n in sorted([w for w in nums if y0 <= w[1] < y1], key=lambda w: w[1]):
                cand = [b for b in blocks if b[0] <= n[1] + 2]
                desc = cand[-1][1] if cand else ""
                if cand and cand[-1][2]:
                    no_name.append({"item": it[4], "number": n[4], "variant_line": desc}); continue
                desc = " ".join(desc.replace("ﬂ", "fl").replace("ﬁ", "fi").split())
                desc = re.sub(r"(\w)- (\w)", r"\1\2", desc)  # "separa- tion" -> "separation"
                if re.fullmatch(r"(Item \d+[a-z]?\s*)+|C( C)*", desc) or not desc:
                    no_name.append({"item": it[4], "number": n[4]}); continue
                rows.append((it[4], n[4], desc))
    cover = []
    for y, ws in lines_of(words):
        text = [w[4] for w in ws]
        if ws and HEATER.match(text[0]) and NUM.match(text[-1]) and text[-1].endswith(".0000") and len(text) >= 3:
            label = " ".join(t for t in text[:-1]).replace(" ,", ",")
            cover.append(("unit", text[-1], " ".join(label.split())))
    return rows, cover, no_name


def words_a(page):
    return [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]


def words_b(pl_page):
    return [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in pl_page.extract_words(keep_blank_chars=False)]


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, spaced, no_name = [], [], [], []
    for i, p in enumerate(d):
        ra, ca, na = read_page(words_a(p))
        rb, cb, nb = read_page(words_b(pl.pages[i]))
        a, b = ra + ca, rb + cb
        key = lambda x: (x[0], x[1], "".join(x[2].split()).casefold())
        kb = {key(x) for x in b}; ka = {key(x) for x in a}
        if ka != kb:
            diffs.append({"page": i + 1, "only_a": [x for x in a if key(x) not in kb][:5],
                          "only_b": [x for x in b if key(x) not in ka][:5]})
        keep += [(i + 1, x) for x in a if key(x) in kb]
        no_name += [dict(x, page=i + 1) for x in na]
        spaced += [{"page": i + 1, "number": s} for s in SPACED.findall(p.get_text())]
    seen, lines, dup, per_page = {}, [], [], {}
    sections = {"0": section, "1": section + " — heaters covered (title page)"}
    names = {}
    for pg, (item, num, desc) in keep:
        names.setdefault(num, set()).add(desc)
    conflict = {n for n, v in names.items() if len(v) > 1}  # one number printed under two designations: not loaded
    dup = [{"number": n, "names": sorted(names[n])} for n in sorted(conflict)]
    for pg, (item, num, desc) in keep:
        if num in seen or num in conflict:
            continue
        seen[num] = desc
        per_page[pg] = per_page.get(pg, 0) + 1
        sx = "1" if item == "unit" else "0"
        lines.append(f"{pg}|{per_page[pg]}|{num}|{desc.replace('|', '/')}|{sx}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines), "no_name": no_name, "spaced": spaced,
           "duplicates_other_name": dup}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(keep), "numbers": len(seen), "diffs": diffs[:3],
                      "no_name": no_name[:8], "spaced": spaced, "dup": dup[:6]}, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
