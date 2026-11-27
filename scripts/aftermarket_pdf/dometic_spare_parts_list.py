"""Two-pass reader for Dometic (ex-Electrolux) "Spare parts list" PDFs (PDF PT / pdf-tools layout):
each table page starts "Exploded view no.: <id>", a Matrix table (letter | PNC | ELC | ProdDate | Model) and then
rows "Pos | Part No. | Matrix | Description" (Matrix = one letter or "-" per PNC column; e.g. DM2652 fridge lists,
CTLP3050 cassette-toilet lists).

Pass A: text-line order (a row opens on a Pos line followed by a Part No. line; the matrix tokens may share the
line with the description). Pass B: word boxes by header column (Pos / Part / Matrix / Description x positions);
a line with no part number continues the description above (e.g. "< 0923..." production-date qualifiers).
Rows whose matrix does not cover every PNC get " [applies to: <model> <PNC>, ...]" appended, as printed in the
Matrix table. Numbers are stored as printed (Dometic's "add a 0 in front of part numbers with less than 10
digits" ordering rule is not applied). Only rows on which both passes agree are kept.
usage: python3 -I dometic_spare_parts_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

POS = re.compile(r"^(\d{1,4}[A-Z]?|-)$")
NUM = re.compile(r"^\d{6,12}$")
MTOK = re.compile(r"^([A-Z]|-)$")
STOP = re.compile(r"^(- \d+ -|©.*|Page \d+)$")
PNC = re.compile(r"^\d{9}$")


def matrix_table(lines):
    """letter -> (pnc, model) from the Matrix block between 'Model' and 'Pos'."""
    if "Model" not in lines or "Pos" not in lines:
        return {}
    blk = lines[lines.index("Model") + 1:lines.index("Pos")]
    out, k = {}, 0
    while k + 4 < len(blk):
        if re.match(r"^[A-Z]$", blk[k]) and PNC.match(blk[k + 1]) and re.match(r"^\d{8}$", blk[k + 3]):
            out[blk[k]] = (blk[k + 1], blk[k + 4]); k += 5; continue
        k += 1
    return out


def view_id(page):
    m = re.search(r"Exploded view no\.:\s*(\S+)", page.get_text())
    return m.group(1) if m else None


def applies(matrix, table):
    letters = [t for t in matrix if t != "-"]
    if not table or (len(matrix) == len(table) and len(letters) == len(table)):
        return ""
    return " [applies to: " + ", ".join(f"{table[l][1]} {table[l][0]}" for l in letters if l in table) + "]"


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    if not view_id(page) or "Description" not in L or "Pos" not in L:
        return [], {}
    table = matrix_table(L)
    ncols = len(table)
    body = L[L.index("Description", L.index("Pos")) + 1:]
    rows, k = [], 0
    while k < len(body):
        if k + 1 < len(body) and POS.match(body[k]) and NUM.match(body[k + 1]):
            pos, num, j = body[k], body[k + 1], k + 2
            matrix, desc = [], []
            while j < len(body):
                if j + 1 < len(body) and POS.match(body[j]) and NUM.match(body[j + 1]):
                    break
                if STOP.match(body[j]):
                    j += 1; continue
                toks = body[j].split()
                if len(matrix) < ncols:
                    while toks and len(matrix) < ncols and MTOK.match(toks[0]):
                        matrix.append(toks.pop(0))
                if toks:
                    desc.append(" ".join(toks))
                j += 1
            rows.append((pos, num, " ".join(" ".join(desc).split()) + applies(matrix, table)))
            k = j; continue
        k += 1
    return rows, table


def pass_b(page, table):
    W = page.get_text("words")
    hp = [w for w in W if w[4] == "Pos"]
    if not hp or not view_id(page):
        return []
    yh = hp[-1][1]
    hdr = {w[4]: w[0] for w in W if abs(w[1] - yh) < 2}
    if not all(k in hdr for k in ("Pos", "Part", "Matrix", "Description")):
        return []
    xs = [hdr["Pos"] - 3, hdr["Part"] - 3, hdr["Matrix"] - 3, hdr["Description"] - 3]
    lines = {}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 <= yh + 2 or y0 > 800:
            continue
        lines.setdefault(round(y0, 0), []).append((x0, w))
    rows, cur = [], None
    for y in sorted(lines):
        cells = [[], [], [], []]
        for x, w in sorted(lines[y]):
            c = max(i for i in range(4) if x >= xs[i]) if x >= xs[0] else None
            if c is not None:
                cells[c].append(w)
        num = " ".join(cells[1])
        if NUM.match(num) and cells[0]:
            if cur: rows.append(cur)
            cur = [" ".join(cells[0]), num, list(cells[2]), list(cells[3])]
        elif cur and not cells[0] and not cells[1]:
            cur[2] += cells[2]; cur[3] += cells[3]
    if cur: rows.append(cur)
    return [(p, n, " ".join(" ".join(d).split()) + applies(m, table)) for p, n, m, d in rows]


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, sections, unread = [], [], {}, []
    for i, p in enumerate(d):
        a, table = pass_a(p)
        b = pass_b(p, table)
        if not a and not b:
            continue
        vid = view_id(p)
        code = str(len(sections) + 1)
        sections[code] = f"Exploded view {vid}"
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        good = [x for x in a if x in b]
        rows += [(i + 1, n, num, desc, code) for n, (pos, num, desc) in enumerate(good, 1)]
        # every Part-No.-like line on the page should be a row number
        nums_on_page = [w[4] for w in p.get_text("words") if NUM.match(w[4])]
        known = {r[1] for r in a} | {r[1] for r in b} | {v[0] for v in table.values()}
        unread += [{"page": i + 1, "number": n} for n in nums_on_page if n not in known and not re.match(r"^\d{8}$", n)]
    seen, lines = set(), []
    for pg, n, num, desc, code in rows:
        if num in seen or not desc:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{code}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "unread": unread, "sections": sections, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "views": len(sections), "unread": unread[:5], "diffs": diffs[:2]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
