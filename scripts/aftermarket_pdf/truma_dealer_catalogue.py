"""Two-pass reader for the Truma Dealer Catalog 2025 (InDesign, "Product | Part No. | Description" tables).

Every product row prints the part number (regular 8 pt) in the "Part No." column (x ~ 160-200 pt) and the product
name in bold on the same baseline in the Description column; lines below the name are details (not kept).
Pass A: pymupdf dict spans (font name, baseline). Pass B: pdfplumber words with font names, grouped by baseline.
Only rows on which both passes give the same number and the same bold name are kept.

Numbers printed inside running text ("see gas filters (50603-01)", the Mover chassis adapter-kit table) are not rows
and are reported as `embedded`. The "Changes to our product portfolio" page (old Part No. | Description | NEW part
no. | New description, numbers at x ~ 51 / ~ 300) is read separately: replacements go to `supersessions` (legacy-map
v2 lane, same-maker), "Discontinued with no replacement" numbers to `discontinued`.

usage: python3 -I truma_dealer_catalogue.py <pdf> <out.json> "<section prefix>" [first_original_page]
"""
import hashlib, json, re, sys
import pymupdf, pdfplumber

NUM = re.compile(r"^\d{5}-\d{2}(?:\d{3})?$")
ANY = re.compile(r"\b\d{5}-\d{2}(?:\d{3})?\b")
COL = (150, 205)  # Part No. column, left edge


def norm(t):
    t = t.replace("\xa0", " ").replace(" ", " ").replace(" ", " ").replace("\x07", "")
    return " ".join(t.split()).strip(" ,;")


def heading_a(page):
    hs = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["size"] >= 18 and s["bbox"][1] < 70 and s["text"].strip() and "Dealer Catalog" not in s["text"]:
                    hs.append(s["text"])
    return norm(" ".join(hs))


def pass_a(page):
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    spans.append(s)
    rows = []
    for s in spans:
        t = s["text"].strip()
        if NUM.match(t) and COL[0] <= s["bbox"][0] <= COL[1] and "Bold" not in s["font"]:
            y = s["bbox"][3]
            name = [r for r in spans if abs(r["bbox"][3] - y) < 2.5 and r["bbox"][0] > s["bbox"][2] + 5
                    and "Bold" in r["font"] and r["size"] < 12]
            name.sort(key=lambda r: r["bbox"][0])
            rows.append((round(y), t, norm(" ".join(r["text"] for r in name))))
    rows.sort()
    return [(n, d) for _, n, d in rows]


def pass_b(pl_page):
    W = pl_page.extract_words(extra_attrs=["fontname", "size"], keep_blank_chars=False, use_text_flow=False)
    rows = []
    for w in W:
        if NUM.match(w["text"]) and COL[0] <= w["x0"] <= COL[1] and "Bold" not in w["fontname"]:
            y = w["bottom"]
            name = [v for v in W if abs(v["bottom"] - y) < 2.5 and v["x0"] > w["x1"] + 5 and "Bold" in v["fontname"]
                    and v["size"] < 12]
            name.sort(key=lambda v: v["x0"])
            rows.append((round(y), w["text"], norm(" ".join(v["text"] for v in name))))
    rows.sort()
    return [(n, d) for _, n, d in rows]


def portfolio_changes(page):
    """'Changes to our product portfolio': numbers at the left column (old) and x ~ 300 (new)."""
    W = page.get_text("words")
    lines = {}
    for x0, y0, x1, y1, t, *_ in W:
        lines.setdefault(round(y1), []).append((x0, t))
    out_sup, out_disc = [], []
    hdr_new = [w for w in W if w[4] == "NEW"]
    y_new = hdr_new[0][1] if hdr_new else 1e9
    for y in sorted(lines):
        ws = sorted(lines[y])
        nums = [(x, t) for x, t in ws if NUM.match(t)]
        if not nums or nums[0][0] > 80:
            continue
        old = nums[0][1]
        new = [t for x, t in nums if 280 <= x <= 320]
        old_desc = norm(" ".join(t for x, t in ws if 80 < x < 280 and not NUM.match(t)))
        new_desc = norm(" ".join(t for x, t in ws if x > 320 and not NUM.match(t)))
        if y > y_new and new:
            out_sup.append({"old": old, "old_description": old_desc, "new": new[0], "new_description": new_desc})
        elif y > y_new:
            out_sup.append({"old": old, "old_description": old_desc, "new": None, "hold": "no new number on line"})
        else:
            out_disc.append({"number": old, "description": old_desc})
    return out_sup, out_disc


def main(pdf, outp, prefix, first_orig=1):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    rows, diffs, embedded, sections, sec_ix = [], [], [], {}, {}
    sup, disc = [], []
    for i, p in enumerate(d):
        orig = first_orig + i
        if "Changes to our product portfolio" in p.get_text():
            s, dd = portfolio_changes(p)
            sup += [dict(x, page=i + 1, original_page=orig) for x in s]
            disc += [dict(x, page=i + 1, original_page=orig) for x in dd]
            continue
        a, b = pass_a(p), pass_b(pl.pages[i])
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:6], "only_b": [x for x in b if x not in a][:6]})
        rowset = {n for n, _ in a}
        for t in ANY.findall(p.get_text()):
            if t not in rowset:
                embedded.append({"page": i + 1, "number": t})
        keep = [x for x in a if x in b]
        if not keep:
            continue
        h = heading_a(p)
        label = f"{prefix} — {h} (catalogue p {orig})" if h else f"{prefix} (catalogue p {orig})"
        if label not in sec_ix:
            sec_ix[label] = str(len(sec_ix)); sections[sec_ix[label]] = label
        for n, (num, desc) in enumerate(keep, 1):
            rows.append((i + 1, n, num, desc, sec_ix[label]))
    seen, lines, dup, noname = {}, [], [], []
    for pg, n, num, desc, sx in rows:
        if not desc:
            noname.append({"page": pg, "number": num}); continue
        if num in seen:
            if seen[num] != desc:
                dup.append({"page": pg, "number": num, "first": seen[num], "here": desc})
            continue
        seen[num] = desc
        lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{sx}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines), "embedded": embedded,
           "no_name": noname, "duplicates_other_name": dup, "supersessions": sup, "discontinued": disc}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "diffs": diffs[:3], "no_name": noname[:5], "dup_other_name": dup[:5], "supersessions": sup,
                      "discontinued": len(disc), "embedded": len(embedded)}, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 1)
