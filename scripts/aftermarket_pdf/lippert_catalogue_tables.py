"""Two-pass reader for the Lippert 2023 retail catalogue ("2023 CATALOG", 432-LIPPERT / LIPPERT.COM footer; ChatGPT split
"Lippert_OEM_catalogue - pp NNN-MMM"). Product pages carry shaded tables whose header row starts with a part-number
column ("Part #", "Item # | Part #", colour columns "White # | Black #", pack columns "Part # | 10-Pack #") followed by a
Description column or by attribute columns (Axle Capacity, Size, Includes ...).

Pass A: pymupdf find_tables() cell text. Pass B: pdfplumber words inside each pass-A cell box (a second text
extraction over the same table geometry, as in wfco_crossref_sheet.py). A row is kept only when both passes give the
same text (spaces ignored) for the number cell and for every cell used in the description.

Description = the Description cell, or, when the table has none, the product heading (DINOT-Black >= 17 pt lines
nearest above the table that overlap it horizontally); the other cells are kept as "Header: value" attributes; a colour /
pack column label is appended ("(black)", "(10-pack)"). Columns of other numbering systems are never part columns:
"Industry #", "Industry Standard", "Bearing Kit #", "Stabilization Bar #" stay attributes. A number printed with two
different descriptions is not loaded ("conflicts"). Tables with no header row of this kind (continuation tables,
vehicle fit charts "Make / Model | Years | Part#") are not read.

usage: python3 -I lippert_catalogue_tables.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf, pdfplumber

NUM = re.compile(r"^\d{6,10}$")
PARTCOL = re.compile(r"^(?:(.+?) )?#$")
# other numbering systems or referenced accessories, never the row's own part; "t", "rt", "# industry": header cells cut
# off by the table finder (the number column is clipped too, so those tables are not read)
NOT_PART = {"industry", "bearing kit", "stabilization bar", "industry standard", "switch kit", "cartridge replacement",
            "oem", "t", "rt", "# industry", "item", "seal", "sleeve"}
# premium axle catalogue 2025: "Suggested Nut #", "Suggested Idler Hub #", "Race Industry #" name another part
NOT_PART_WORDS = ("suggested", "industry", "replacement", "stabilization", "oem")
# pack counts: "Clamshell Quantity" belongs to the clamshell number only, not to the 10-pack number on the same row
SKIP_ATTR = {"item #", "item", "qty", "quantity", "clamshell quantity"}
MARKS = re.compile(r"[®™]")


def norm(s):
    return " ".join(MARKS.sub(" ", s or "").split())


def headings(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if s["size"] >= 17 and "Black" in s["font"] and s["text"].strip()]
            if sp:
                x0 = min(s["bbox"][0] for s in sp); y0 = min(s["bbox"][1] for s in sp)
                x1 = max(s["bbox"][2] for s in sp); y1 = max(s["bbox"][3] for s in sp)
                out.append([x0, y0, x1, y1, norm(" ".join(s["text"] for s in sp))])
    # pieces of one printed line ("GOODYEAR" + "TIRE &") share a top edge
    lines = []
    for h in sorted(out, key=lambda h: (round(h[1]), h[0])):
        if lines and abs(lines[-1][1] - h[1]) < 2 and 0 <= h[0] - lines[-1][2] < 25:
            lines[-1][2] = h[2]; lines[-1][3] = max(lines[-1][3], h[3]); lines[-1][4] += " " + h[4]
        else:
            lines.append(list(h))
    # consecutive lines of one heading are ~17 pt apart and start at the same x
    groups = []
    for h in sorted(lines, key=lambda h: (h[1], h[0])):
        for g in groups:
            if abs(g[0] - h[0]) < 30 and 8 <= h[1] - g[5] <= 24:
                g[3] = h[3]; g[2] = max(g[2], h[2]); g[4] += " " + h[4]; g[5] = h[1]; break
        else:
            groups.append(list(h) + [h[1]])
    return [g[:5] for g in groups]


def heading_for(groups, bbox):
    c = [g for g in groups if g[3] <= bbox[1] + 2 and g[0] < bbox[2] and g[2] > bbox[0] - 5 and g[0] >= bbox[0] - 40]
    if not c:
        return ""
    return max(c, key=lambda g: g[3])[4]


def cell_words(words, bbox):
    x0, y0, x1, y1 = bbox
    ws = [w for w in words if (w["x0"] + w["x1"]) / 2 >= x0 and (w["x0"] + w["x1"]) / 2 <= x1
          and (w["top"] + w["bottom"]) / 2 >= y0 and (w["top"] + w["bottom"]) / 2 <= y1]
    ws.sort(key=lambda w: (round(w["top"]), w["x0"]))
    return norm(" ".join(w["text"] for w in ws))


def part_label(h):
    """None when header h is not a column of the row's own part numbers; else the variant label ("" for Part #)."""
    m = PARTCOL.match(h)
    if m:
        lab = (m.group(1) or "").strip()
    elif re.match(r"(?i)^part ?(?:no\.?|number)$", h):
        lab = ""
    else:
        return None
    if lab.lower() in NOT_PART or any(w in lab.lower() for w in NOT_PART_WORDS):
        return None
    return "" if lab.lower() in ("part", "", "kit") else lab.lower()


def groups_of(hdr):
    """split side-by-side tables merged into one: a new group starts where the first header repeats"""
    first = hdr[0]
    idx = [k for k, h in enumerate(hdr) if h == first] if first else [0]
    if not idx or idx[0] != 0:
        idx = [0] + idx
    bounds = idx + [len(hdr)]
    return [list(range(bounds[i], bounds[i + 1])) for i in range(len(bounds) - 1)]


def read_page(page, plpage):
    words = plpage.extract_words(keep_blank_chars=False, use_text_flow=False)
    hg = headings(page)
    rows, diffs, unread = [], [], []
    for t in page.find_tables().tables:
        data = t.extract()
        if not data or len(data) < 2:
            continue
        hdr = [norm(c) for c in data[0]]
        heading = heading_for(hg, t.bbox)
        for grp in groups_of(hdr):
            pcols = [(k, part_label(hdr[k])) for k in grp if part_label(hdr[k]) is not None]
            if not pcols:
                continue
            dcol = [k for k in grp if hdr[k].lower() == "description"]
            acols = [k for k in grp if k not in [p for p, _ in pcols] and k not in dcol and hdr[k] and hdr[k].lower() not in SKIP_ATTR]
            for ri, r in enumerate(t.rows[1:], 1):
                cells = r.cells
                if len(cells) != len(hdr):
                    continue
                a = [norm(c) for c in data[ri]]
                b = [cell_words(words, c) if c else "" for c in cells]
                base_a = a[dcol[0]] if dcol else heading
                base_b = b[dcol[0]] if dcol else heading
                attrs_a = "; ".join(f"{hdr[k]}: {a[k]}" for k in acols if a[k] and a[k] not in ("--", "-"))
                attrs_b = "; ".join(f"{hdr[k]}: {b[k]}" for k in acols if b[k] and b[k] not in ("--", "-"))
                for k, lab in pcols:
                    na, nb = a[k], b[k]
                    if not na and not nb:
                        continue
                    if not NUM.match(na.replace(" ", "")):
                        if re.search(r"\d{5,}", na):
                            unread.append({"cell": na, "header": hdr[k]})
                        continue
                    da = base_a + (f" ({attrs_a})" if attrs_a else "") + (f" ({lab})" if lab else "")
                    db = base_b + (f" ({attrs_b})" if attrs_b else "") + (f" ({lab})" if lab else "")
                    if na.replace(" ", "") == nb.replace(" ", "") and da.replace(" ", "") == db.replace(" ", "") and base_a:
                        rows.append((na.replace(" ", ""), da, heading))
                    else:
                        diffs.append({"a": [na, da], "b": [nb, db]})
    return rows, diffs, unread


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    allrows, diffs, unread, secs = [], [], [], {}
    for i, p in enumerate(d):
        r, df, un = read_page(p, pl.pages[i])
        for num, desc, head in r:
            key = secs.setdefault(head or f"page {i + 1}", str(len(secs)))
            allrows.append((i + 1, num, desc, key))
        diffs += [dict(x, page=i + 1) for x in df]
        unread += [dict(x, page=i + 1) for x in un]
    descs = {}
    for pg, num, desc, key in allrows:
        descs.setdefault(num, set()).add(desc)
    conflicts = {k: sorted(v) for k, v in descs.items() if len(v) > 1}
    seen, lines = set(), []
    for pg, num, desc, key in allrows:
        if num in seen or num in conflicts:
            continue
        seen.add(num); lines.append(f"{pg}|{len(lines) + 1}|{num}|{desc.replace('|', '/')}|{key}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs,
           "unread": unread, "rows_total": len(allrows), "numbers": len(seen), "conflicts": conflicts,
           "sections": {v: k for k, v in secs.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(allrows), "numbers": len(seen), "conflicts": len(conflicts),
                      "diffs": len(diffs), "unread": len(unread)}))


if __name__ == "__main__":
    main(*sys.argv[1:3])
