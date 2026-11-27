"""Two-pass reader for the Dometic SeaLand "Sanitation Replacement Parts Guide" (2016 compilation of SeaLand / VacuFlush
"PARTS LIST: <model>" sheets, P/N 6003xxxxx). The sheets come in two layouts: text lines "385343829 - SEAT/COVER - WHITE"
and ruled tables ITEM | PART NUMBER | DESCRIPTION. In both, the 9-digit part number and its description sit on the
same baseline, so one rule reads both: a 9-digit number word, then the words to its right on the same baseline up to
the next 9-digit number or a gap over 60 pt (leading "-" dropped). On sheets with two tables side by side the
right-hand table's ITEM number ends up between a left-hand description and the next part number; it is dropped.

Only pages whose text contains "PARTS LIST" are read (the model index pages Model | Description | Item | Ref. List # |
Page are not). Numbers with no description on their baseline (sheet P/N, numbers whose description is offset in the
sheet's own layout) are reported as `orphans`, numbers of other lengths ("38311987") as `odd_numbers`.
Sheets printed rotated on the page (page rotation, or vertical / upside-down text lines) are skipped and reported as
`rotated_pages` (the baseline rule pairs the wrong words there). Pass A: pymupdf words; pass B: pdfplumber words;
rows are compared with spaces removed (pdfplumber writes "KIT,MOUNT" and letter-spaced "( M U S T ...") and pass A's
text is stored; only rows on which both agree are kept. A number repeated on later
sheets keeps the first description; differing later wordings are reported.

usage: python3 -I dometic_sealand_parts_list.py <pdf> <out.json> "<section prefix>" [first_original_page]
"""
import hashlib, json, re, sys
import pymupdf, pdfplumber

N9 = re.compile(r"^\d{9}$")
ODD = re.compile(r"^\d{7,8}$|^\d{10}$")


def rows_from(words):
    out, orphans, odd = [], [], []
    for w in words:
        if ODD.match(w[4]):
            odd.append(w[4])
        if not N9.match(w[4]):
            continue
        y = (w[1] + w[3]) / 2
        right = sorted([v for v in words if abs((v[1] + v[3]) / 2 - y) < 2.5 and v[0] > w[2] - 1 and v != w],
                       key=lambda v: v[0])
        desc, last, hit_number = [], w[2], False
        for v in right:
            if N9.match(v[4]):
                hit_number = True; break
            if v[0] - last > 60:
                break
            desc.append(v[4]); last = v[2]
        # side-by-side tables: the right-hand table's ITEM cell sits between this description and its number
        if hit_number and len(desc) > 1 and re.match(r"^\d{1,3}[A-Z]?$", desc[-1]):
            desc = desc[:-1]
        if desc and desc[0] == "-":
            desc = desc[1:]
        t = " ".join(" ".join(desc).split())
        if t:
            out.append((round(y), w[4], t))
        else:
            orphans.append(w[4])
    out.sort()
    return [(n, t) for _, n, t in out], orphans, odd


def title_of(text):
    m = re.search(r"PARTS LIST:\s*(.+)", text)
    return " ".join(m.group(1).split()) if m else ""


def main(pdf, outp, prefix, first_orig=1):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, orphans, odd, sections, six, rotated = [], [], [], [], {}, {}, []
    for i, p in enumerate(d):
        text = p.get_text()
        if "PARTS LIST" not in text.upper():
            continue
        dirs = {tuple(round(x) for x in l["dir"]) for b in p.get_text("dict")["blocks"] for l in b.get("lines", [])
                if any(sp["text"].strip() for sp in l["spans"])}
        if p.rotation or dirs - {(1, 0)}:
            # sheet printed rotated on the page (vertical or upside-down text): the baseline rule does not apply
            rotated.append({"page": i + 1, "rotation": p.rotation, "title": title_of(text),
                            "numbers": len(re.findall(r"\b\d{9}\b", text))})
            continue
        wa = [(w[0], w[1], w[2], w[3], w[4]) for w in p.get_text("words")]
        wb = [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in pl.pages[i].extract_words()]
        a, oa, da = rows_from(wa)
        b, ob, db = rows_from(wb)
        key = lambda x: (x[0], "".join(x[1].split()))  # pdfplumber spaces some words differently ("KIT,MOUNT")
        ka, kb = {key(x) for x in a}, {key(x) for x in b}
        if ka != kb:
            diffs.append({"page": i + 1, "only_a": [x for x in a if key(x) not in kb][:5],
                          "only_b": [x for x in b if key(x) not in ka][:5]})
        orphans += [{"page": i + 1, "number": n} for n in oa]
        odd += [{"page": i + 1, "number": n} for n in da]
        agreed = [x for x in a if key(x) in kb and not re.match(r"^(\*|N/A$|&$)", x[1])]
        if not agreed:
            continue
        label = f"{prefix} — PARTS LIST: {title_of(text)} (guide p {first_orig + i})"
        if label not in six:
            six[label] = str(len(six)); sections[six[label]] = label
        keep += [(i + 1, n, t, six[label]) for n, t in agreed]
    seen, lines, other, per_page = {}, [], [], {}
    for pg, num, desc, sx in keep:
        if num in seen:
            if seen[num] != desc:
                other.append({"page": pg, "number": num, "first": seen[num], "here": desc})
            continue
        seen[num] = desc
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{num}|{desc.replace('|', '/')}|{sx}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines), "orphans": orphans, "odd_numbers": odd, "rotated_pages": rotated,
           "other_wordings": other}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(keep), "numbers": len(seen), "diffs": diffs[:3],
                      "orphans": len(orphans), "odd": odd, "rotated_pages": [(r["page"], r["numbers"]) for r in rotated], "other_wordings": len(other)}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 1)
