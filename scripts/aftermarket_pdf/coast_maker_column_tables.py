"""Two-pass reader for the maker-number tables in Coast to Coast RV (Australian distributor) catalogues:
"NO. | <Maker> Part No. | Coast Part No. | Description" (Carefree awning spare parts: Caravan Parts Catalogue 2017
split pp 001-076 pdf pp 36 / 38; Caravan and Leisure Catalogue 2026 split pp 001-083 pdf pp 57 / 58).

Only the maker's number is loaded. Coast Part No. (NNN-NNNNN) is the distributor's stock number and is never a part;
it is used only as the row anchor (every table row prints one). Item callouts ("6", "4a") are dropped.

Pass A: pymupdf text-line order. After a header (a line "<Maker>" followed by "Part No." and "Coast"), each row is
maker-number line(s) then the Coast number then description lines. A maker number wrapped after a hyphen
("R012530-" / "TB76L") is joined; a number and the Coast number can share a line ("R001618WHT 200-38502").
A table ends at a "Note:" line, an upper-case heading or the end of the page.
Pass B: pdfplumber word boxes. Coast numbers are clustered into table columns by x; each row's band is cut between
neighbouring Coast numbers (2017 cells are top-aligned: band from this row's top to the next row's top; 2026 cells are
vertically centred in ruled rows: band between the midpoints of neighbouring rows). Maker words lie left of the Coast
number (offset taken from the header), description words right of it up to the next table column.
Only rows both passes give identically are kept; a number printed with two different descriptions is not loaded.
usage: python3 -I coast_maker_column_tables.py <pdf> <out.json> <maker header word> <top|center> "<section label>"
"""
import hashlib, json, re, sys
import pymupdf
import pdfplumber

COAST = re.compile(r"^\d{3}-\d{5}$")
MAKERNO = re.compile(r"^(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,}$")
ITEM = re.compile(r"^\d{1,2}[a-z]?$")
VALID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./-]{1,39}$")


def norm(s):
    return " ".join(s.replace("’", "'").replace("”", '"').split())


def join_number(parts):
    """Join maker-number pieces; only a piece ending with '-' may continue on the next line."""
    if not parts:
        return None
    out = parts[0]
    for p in parts[1:]:
        if not out.endswith("-"):
            return None
        out += p
    return out if VALID.match(out) and not out.endswith("-") else None


def is_number_line(toks):
    return toks and all(COAST.match(t) or MAKERNO.match(t) or ITEM.match(t) for t in toks)


def pass_a(page, maker):
    L = [l.strip() for l in page.get_text().splitlines()]
    L = [l for l in L if l]
    rows, k, in_table = [], 0, False
    pending, cur = [], None
    while k < len(L):
        s = L[k]
        if (not in_table and s.split()[0] == maker and k + 3 < len(L) and L[k + 1].startswith("Part No")
                and L[k + 2].split()[0] == "Coast"):
            in_table, pending, cur = True, [], None
            k += 3
            while k < len(L) and L[k] in ("Part No.", "Description"):
                k += 1
            continue
        if in_table:
            toks = s.split()
            if s.startswith("Note:") or (s.upper() == s and re.search(r"[A-Z]{4}", s) and not is_number_line(toks)):
                in_table, pending, cur = False, [], None
            elif is_number_line(toks):
                for t in toks:
                    if ITEM.match(t):
                        continue
                    if COAST.match(t):
                        cur = [join_number(pending), []]
                        rows.append(cur)
                        pending = []
                    else:
                        pending.append(t)
                        cur = None
            elif cur is not None and not pending:
                cur[1].append(s)
            else:
                pending = ["?"]  # text that belongs to no row: poison the next number
        k += 1
    return [(n, norm(" ".join(d))) for n, d in rows if n]


def pass_b(ppage, maker, mode):
    W = ppage.extract_words(keep_blank_chars=False, use_text_flow=False)
    heads = []
    for w in W:
        if w["text"] == maker:
            coast = [v for v in W if v["text"] == "Coast" and abs(v["top"] - w["top"]) < 3 and v["x0"] > w["x0"]]
            below = [v for v in W if v["text"] == "Part" and 2 < v["top"] - w["top"] < 20 and abs(v["x0"] - w["x0"]) < 6]
            if coast and below:
                heads.append((w, min(coast, key=lambda v: v["x0"]), max(v["bottom"] for v in below)))
    if not heads:
        return []
    offset = min(c["x0"] - m["x0"] for m, c, _ in heads)
    top_y = min(m["top"] for m, _, _ in heads) - 30  # a header-less side table can start level with the header
    cw = sorted([w for w in W if COAST.match(w["text"]) and w["top"] > top_y], key=lambda w: w["x0"])
    groups = []
    for w in cw:
        g = next((g for g in groups if abs(g[0]["x0"] - w["x0"]) < 12), None)
        (g.append(w) if g else groups.append([w]))
    groups.sort(key=lambda g: g[0]["x0"])
    rows = []
    for gi, g in enumerate(groups):
        gx0 = min(w["x0"] for w in g); gx1 = max(w["x1"] for w in g)
        mz0 = gx0 - offset - 3
        dz1 = (min(w["x0"] for w in groups[gi + 1]) - offset - 35) if gi + 1 < len(groups) else ppage.width
        g.sort(key=lambda w: w["top"])
        for i, c in enumerate(g):
            if mode == "top":
                y0 = c["top"] - 3
                y1 = g[i + 1]["top"] - 3 if i + 1 < len(g) else c["top"] + 40
            else:
                cy = (c["top"] + c["bottom"]) / 2
                prv = (g[i - 1]["top"] + g[i - 1]["bottom"]) / 2 if i else cy - 20
                nxt = (g[i + 1]["top"] + g[i + 1]["bottom"]) / 2 if i + 1 < len(g) else cy + 20
                y0, y1 = (prv + cy) / 2, (cy + nxt) / 2
            notes = [w["top"] for w in W if w["text"] == "Note:" and y0 <= w["top"] < y1]
            if notes:  # a table note under the last row ends the band
                y1 = min(notes) - 1
            band = [w for w in W if y0 <= (w["top"] + w["bottom"]) / 2 < y1]
            mk = sorted([w for w in band if mz0 <= w["x0"] < gx0 - 2 and not ITEM.match(w["text"])],
                        key=lambda w: (round(w["top"]), w["x0"]))
            ds = [w for w in band if gx1 + 2 <= w["x0"] < dz1]
            lines = {}
            for w in sorted(ds, key=lambda w: (w["top"], w["x0"])):
                k = next((k for k in lines if abs(k - w["top"]) < 2.5), w["top"])
                lines.setdefault(k, []).append(w["text"])
            desc = [" ".join(lines[k]) for k in sorted(lines)]
            if any(l.startswith("Note:") for l in desc):
                desc = desc[:[l.startswith("Note:") for l in desc].index(True)]
            num = join_number([w["text"] for w in mk])
            if num and desc:
                rows.append((num, norm(" ".join(desc))))
    return rows


def main(pdf, outp, maker, mode, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    got, diffs, pages_read = [], [], []
    for i, p in enumerate(d):
        if maker not in p.get_text():
            continue
        a, b = pass_a(p, maker), pass_b(pl.pages[i], maker, mode)
        if not a and not b:
            continue
        pages_read.append(i + 1)
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b], "only_b": [x for x in b if x not in a]})
        got += [(i + 1, n, desc) for n, desc in a if (n, desc) in b]
    by = {}
    for pg, n, desc in got:
        by.setdefault(n, set()).add(desc)
    conflicts = {n: sorted(v) for n, v in by.items() if len(v) > 1}
    seen, lines, k = set(), [], 0
    for pg, n, desc in got:
        if n in seen or n in conflicts:
            continue
        seen.add(n); k += 1
        lines.append(f"{pg}|{k}|{n}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "pages_read": pages_read, "agree": bool(lines), "all_rows_agree": not diffs,
           "diffs": diffs, "conflicts": conflicts, "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("doc", "pages_read", "all_rows_agree", "numbers", "diffs", "conflicts")},
                     ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:6])
