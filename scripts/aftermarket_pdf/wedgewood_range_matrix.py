"""Two-pass reader for Atwood / Wedgewood (now Dometic) LP gas range and slide-in cooktop "Parts Drawing & List"
sheets with a model matrix: Item | Description | one 5-digit Atwood number per model column, under a 3-row header
(WEDGEWOOD / ATWOOD brand row, RV / CV / RA / CA type row, 1733 / 2133 / 33 size row), e.g. the 33 and 35 series
lists. Cells are vertically centred in ruled rows; a description may wrap over two lines; a colour / burner
position variant is printed right-aligned in the Description cell ("Range Top Center Latch      White"), and
continuation rows (no Item) can hold only the variant ("Black", "Bisque") or a new description ("Door Glass Insert
Sm Black"). Number cells may carry "[2 req'd]" (quantity; dropped).

Pass A: pymupdf dict lines in content order: the Item line, the description line(s) (a line starting right of the
description indent is a variant only; a line starting at the indent splits on 3+ spaces into description and
variant), then exactly one line per model column (a number, a blank cell, or a diamond).
Pass B: row bands from the drawn horizontal rules; words assigned to bands by their vertical centre; numbers to the
nearest model column; description words split at gaps > 12 pt into the left-indented description and a
right-aligned variant.
A variant-only row takes the description of the row above. A (item, description, variant, number, column) entry is
kept only if both passes give it; everything else is reported as held.
Identity text = description[, variant]; a number printed with descriptions that differ only by serial-break
qualifiers ("(after serial #F11040784) (Dbl D)") is stored without them; other differences are conflicts (not
loaded). The section names the model columns that print the number.
usage: python3 -I wedgewood_range_matrix.py <pdf> <out.json> "<label>"
"""
import hashlib, json, re, sys

NUM = re.compile(r"^\d{5}$")
ITEM = re.compile(r"^(\d{1,2}[A-Da-d]?|N/S)$")
REQ = re.compile(r"^\[\d+ req[’']d\]$")
DIAMOND = {"▲", "◆", "♦", "TBD"}
SERIAL = re.compile(r"\s*\((?:after|before) serial #?\w+\)|\s*\(Dbl D\)")


def norm(s):
    return " ".join(s.split())


def header(words):
    """-> (columns [(cx, label)], y_bottom_of_header, x_desc)"""
    item = next((w for w in words if w[4] == "Item"), None)
    desc = next((w for w in words if w[4] == "Description" and item and abs(w[3] - item[3]) < 3), None)
    if not item or not desc:
        return None
    size = sorted((w for w in words if abs(w[3] - item[3]) < 3 and re.fullmatch(r"\d{2,4}", w[4])), key=lambda w: w[0])
    typ = [w for w in words if w[4] in ("RV", "CV", "RA", "CA") and item[1] - 20 < w[3] < item[1] + 2]
    brand = [w for w in words if w[4] in ("WEDGEWOOD", "ATWOOD") and item[1] - 34 < w[3] < item[1] - 8]
    if len(size) < 2 or not typ:
        return None
    cx = lambda w: (w[0] + w[2]) / 2
    cols = []
    for s in size:
        t = min(typ, key=lambda t: abs(cx(t) - cx(s)))
        b = min(brand, key=lambda b: abs(cx(b) - cx(s)), default=None)
        cols.append((cx(s), ((b[4].title() + " ") if b else "") + t[4] + " " + s[4]))
    return cols, item[3], item[2] + 8


def split_desc(line_x0, text, indent):
    """-> (description or None, variant or None) for one printed line (pass A)."""
    t = text.strip()
    if line_x0 > indent + 12 or re.match(r"\s{3,}\S", text):
        return None, norm(t)
    parts = [p for p in re.split(r"\s{3,}", t) if p.strip()]
    if len(parts) >= 2:
        return norm(parts[0]), norm(" ".join(parts[1:]))
    return norm(t), None


def pass_a(page, ncols, indent, y_head, y_end):
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            yc = (l["bbox"][1] + l["bbox"][3]) / 2
            if yc < y_head or yc > y_end:
                continue
            lines.append((l["bbox"][0], "".join(s["text"] for s in l["spans"])))
    rows, i, item, prev = [], 0, None, None
    while i < len(lines):
        x0, t = lines[i]
        s = t.strip()
        if s.startswith("Notes"):
            break
        if not s:
            i += 1  # blank item cell of a continuation row / empty line
            continue
        if ITEM.match(s):
            item = s; i += 1
            while i < len(lines) and not lines[i][1].strip():
                i += 1
        dl = []
        while i < len(lines) and lines[i][1].strip() and not NUM.match(lines[i][1].strip()) \
                and lines[i][1].strip() not in DIAMOND and not ITEM.match(lines[i][1].strip()):
            dl.append(lines[i]); i += 1
        if not dl:
            return rows, "no description at line %d" % i
        desc, var = None, None
        for k, (lx, lt) in enumerate(dl):
            d, v = split_desc(lx, lt, indent)
            if d:
                desc = d if desc is None else desc + " " + d
            if v:
                var = v if var is None else var + " " + v
        if desc is None:
            if prev is None:
                return rows, "variant row without a description above"
            desc = prev
        prev = desc
        cells = []
        while len(cells) < ncols and i < len(lines):
            c = lines[i][1].strip(); i += 1
            if REQ.match(c):
                continue
            cells.append(c)
        while i < len(lines) and REQ.match(lines[i][1].strip()):
            i += 1
        for k, c in enumerate(cells):
            if NUM.match(c):
                rows.append((item, desc, var, c, k))
            elif c and c not in DIAMOND:
                return rows, "unexpected cell %r" % c
    return rows, None


def bands(page, y_head):
    ys = sorted(round(g["rect"].y0, 1) for g in page.get_drawings()
                if g["rect"].height < 2 and g["rect"].width > 20 and g["rect"].y0 > y_head - 4)
    out = []
    for y in ys:
        if not out or y - out[-1] > 2:
            out.append(y)
    return out


def pass_b(page, words, cols, indent, y_head):
    bs = bands(page, y_head)
    xnum = min(c[0] for c in cols) - 20
    rows, item, prev = [], None, None
    for y0, y1 in zip(bs, bs[1:]):
        ws = [w for w in words if y0 < (w[1] + w[3]) / 2 < y1]
        if not ws or any(w[4].startswith("Notes") for w in ws):
            continue
        it = [w[4] for w in ws if w[2] <= indent - 2]
        if it and ITEM.match(" ".join(it)):
            item = " ".join(it)
        dw = sorted((w for w in ws if indent - 2 < w[0] < xnum), key=lambda w: (round(w[3]), w[0]))
        lines = {}
        for w in dw:
            lines.setdefault(round(w[3]), []).append(w)
        desc, var = None, None
        for y in sorted(lines):
            segs, cur = [], []
            for w in lines[y]:
                if cur and w[0] - cur[-1][2] > 12:
                    segs.append(cur); cur = []
                cur.append(w)
            if cur:
                segs.append(cur)
            for sg in segs:
                txt = " ".join(w[4] for w in sg)
                if sg[0][0] <= indent + 12:
                    desc = txt if desc is None else desc + " " + txt
                else:
                    var = txt if var is None else var + " " + txt
        if desc is None and var is None:
            continue
        if desc is None:
            desc = prev
        prev = desc
        for w in ws:
            if w[0] >= xnum and NUM.match(w[4]):
                k = min(range(len(cols)), key=lambda k: abs(cols[k][0] - (w[0] + w[2]) / 2))
                rows.append((item, norm(desc) if desc else None, norm(var) if var else None, w[4], k))
    return rows


def read(doc):
    out, held, colsets = [], [], {}
    for pi, page in enumerate(doc):
        words = page.get_text("words")
        h = header(words)
        if not h:
            continue
        cols, y_head, indent = h
        colsets[pi + 1] = [c[1] for c in cols]
        bs = bands(page, y_head + 2)
        a, err = pass_a(page, len(cols), indent, y_head + 2, bs[-1] if bs else 1e9)
        if err:
            held.append({"page": pi + 1, "pass_a_error": err})
        b = pass_b(page, words, cols, indent, y_head + 2)
        bl = list(b)
        n = 0
        for r in a:
            if r in bl:
                bl.remove(r); n += 1
                out.append((pi + 1, n, r, cols[r[4]][1]))
            else:
                held.append({"page": pi + 1, "a": list(r)})
        held += [{"page": pi + 1, "b": list(r)} for r in bl]
    return out, held, colsets


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, held, colsets = read(doc)
    by = {}
    for pg, n, (item, desc, var, num, k), col in rows:
        e = by.setdefault(num, {"first": (pg, n), "texts": [], "cols": []})
        t = desc + (", " + var if var else "")
        if t not in e["texts"]:
            e["texts"].append(t)
        if col not in e["cols"]:
            e["cols"].append(col)
    secs, lines, conflicts, stripped = {}, [], [], 0
    for num, e in sorted(by.items(), key=lambda kv: kv[1]["first"]):
        texts = e["texts"]
        if len(texts) > 1:
            base = {norm(SERIAL.sub("", t)) for t in texts}
            if len(base) != 1:
                conflicts.append({"number": num, "texts": texts}); continue
            texts = [base.pop()]; stripped += 1
        sec = label + " — models " + ", ".join(e["cols"])
        code = secs.setdefault(sec, str(len(secs)))
        pg, n = e["first"]
        lines.append(f"{pg}|{n}|{num}|{texts[0].replace('|', '/')[:200]}|{code}")
    out = {"doc": sha, "pages": doc.page_count, "agree": bool(lines) and not held, "held": held,
           "conflicts": conflicts, "serial_qualifiers_stripped": stripped, "columns": colsets,
           "rows_total": len(rows), "numbers": len(lines), "sections": {c: s for s, c in secs.items()},
           "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(lines),
                      "columns": colsets, "held": held[:12], "conflicts": conflicts[:6], "stripped": stripped},
                     ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
