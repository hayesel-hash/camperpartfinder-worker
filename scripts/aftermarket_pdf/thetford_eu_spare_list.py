"""Reader for Thetford European spare-parts lists (Word / PDFMaker layout, e.g. C200, C220, C260, C500 cassette toilets,
S220 / S260 separation toilets): a ruled table  No. | Description | up to three "Spare part number" columns |
Colours available.  The page header (top right) names the model and date code ("C502C / X | 1025").

A number cell may span several item lines (Word merged / multi-paragraph cells, usually shaded grey): the number
then covers every item line inside the cell (a kit), e.g. 23343 = Cover, Seat, Hinge pin.  Italic text inside a
number cell ("C-model (before 90701)", "for outside vent version") is kept as a note.  Numbers printed in light grey
are "not available anymore" (legend "Xxxxxx = not available anymore"); they are kept with that remark when the
legend is in the document, otherwise reported.  The Colours column is not read.

Cell extents come from the visible horizontal borders of each column, found twice:
  pass A: vector paint order (black hairline rects / lines, minus white rects painted over them later);
  pass B: the rendered page (dark pixel rows at two sample x positions inside the column).
Rows are kept only when both passes give the same number, item numbers, description and note.  A cell holding two
numbers, or a number whose cell holds no item line, is reported and not loaded.
usage: python3 -I thetford_eu_spare_list.py <pdf> <out.json> "<document label>" """
import hashlib, json, re, sys
import pymupdf

NUMRE = re.compile(r"^(?!\d{1,2}-\d{1,2}-(?:\d{2,4})?$)(?=(?:.*\d){4})[A-Z0-9][A-Z0-9.\-]{4,}$")  # dates / years are qualifiers
ITEM = re.compile(r"^\d{1,3}[A-Za-z]?$")
ZOOM = 4


def clean(s):
    return " ".join(s.split())


def word_colours(page):
    """(x0, y0, x1, y1) -> colour for every span, to look up a word's colour."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    out.append((pymupdf.Rect(s["bbox"]), s["color"]))
    return out


def colour_of(w, spans):
    r = pymupdf.Rect(w[:4]); c = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    for sr, col in spans:
        if sr.x0 - 1 <= c[0] <= sr.x1 + 1 and sr.y0 - 1 <= c[1] <= sr.y1 + 1:
            return col
    return 0


def is_black(rgb):
    return rgb is not None and max(rgb) < 0.2


def is_white(rgb):
    return rgb is not None and min(rgb) > 0.95


def hairlines(page):
    """Horizontal paint ops in order: (kind 'black'|'white', x0, x1, y0, y1)."""
    ops = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if dr.get("fill") is not None and r.height < 2.2 and r.width > 0.3:
            if is_black(dr["fill"]):
                ops.append(("black", r.x0, r.x1, r.y0, r.y1))
            elif is_white(dr["fill"]):
                ops.append(("white", r.x0, r.x1, r.y0, r.y1))
        elif dr.get("fill") is not None and is_white(dr["fill"]):
            ops.append(("white", r.x0, r.x1, r.y0, r.y1))
        if dr.get("color") is not None and is_black(dr["color"]):
            for it in dr["items"]:
                if it[0] == "l" and abs(it[1].y - it[2].y) < 0.5:
                    w = (dr.get("width") or 0.5) / 2
                    ops.append(("black", min(it[1].x, it[2].x), max(it[1].x, it[2].x), it[1].y - w, it[1].y + w))
    return ops










def columns(page, W):
    """Column x-intervals from the header row: item no., description, number columns, colours."""
    spare = sorted([w for w in W if w[4] == "Spare"], key=lambda w: w[0])
    if not spare:
        return None
    yh = spare[0][1]
    hdr_bottom = max(w[3] for w in W if abs(w[1] - yh) < 30 and w[4] in ("number", "available"))
    ops = hairlines(page)
    segs = sorted((x0, x1) for k, x0, x1, y0, y1 in ops if k == "black" and hdr_bottom < y0 < hdr_bottom + 12 and x1 - x0 > 3)
    if not segs:
        return None
    y_top = min(y0 for k, x0, x1, y0, y1 in ops if k == "black" and hdr_bottom < y0 < hdr_bottom + 12)
    cols = [list(segs[0])]
    for x0, x1 in segs[1:]:
        if x0 - cols[-1][1] < 0.8 and x1 - x0 < 1.5:  # joint between two cell borders
            cols[-1][1] = x1; continue
        if x0 - cols[-1][1] < 0.8 and x1 - x0 >= 1.5 and cols[-1][1] - cols[-1][0] < 1.5:
            cols[-1] = [x0, x1]; continue
        cols.append([x0, x1])
    cols = [c for c in cols if c[1] - c[0] > 5]
    numcols = [i for i, c in enumerate(cols) if any(c[0] <= (w[0] + w[2]) / 2 <= c[1] for w in spare)]
    col_c = [i for i, c in enumerate(cols) if any(c[0] <= (w[0] + w[2]) / 2 <= c[1] for w in W if w[4] == "Colours")]
    if len(cols) < 3 or not numcols:
        return None
    return {"cols": cols, "num": numcols, "colour": col_c[0] if col_c else None, "y_top": y_top}


def col_of(x, cols):
    for i, (a, b) in enumerate(cols):
        if a - 0.5 <= x <= b + 0.5:
            return i
    return None


def profile_vector(page, sx, step=0.1):
    """Final paint class along x = sx from the vector paint order: 'D' dark line, 'G' grey shading, 'W' white."""
    n = int(page.rect.height / step) + 1
    prof = ["W"] * n

    def paint(y0, y1, cls):
        for k in range(max(0, int(y0 / step)), min(n, int(y1 / step) + 1)):
            prof[k] = cls

    def cls_of(rgb):
        lum = sum(rgb) / 3
        return "D" if lum < 0.45 else "G" if lum < 0.95 else "W"

    for dr in page.get_drawings():
        r = dr["rect"]
        if dr.get("fill") is not None and r.x0 - 0.05 <= sx <= r.x1 + 0.05:
            paint(r.y0, r.y1, cls_of(dr["fill"]))
        if dr.get("color") is not None and cls_of(dr["color"]) == "D":
            w = (dr.get("width") or 0.5) / 2
            for it in dr["items"]:
                if it[0] == "l" and abs(it[1].y - it[2].y) < 0.5 and min(it[1].x, it[2].x) <= sx <= max(it[1].x, it[2].x):
                    paint(it[1].y - w, it[1].y + w, "D")
    return prof, step


def profile_raster(pix, sx):
    px = int(round(sx * ZOOM))
    prof = []
    for y in range(pix.height):
        v = pix.pixel(px, y)[0]
        prof.append("D" if v < 170 else "G" if v < 238 else "W")
    return prof, 1 / ZOOM


def run_at(pr, y):
    """Maximal same-class run (in points) containing y."""
    prof, step = pr
    k = min(len(prof) - 1, max(0, int(round(y / step))))
    c = prof[k]
    if c == "D":
        return None
    a = k
    while a > 0 and prof[a - 1] == c:
        a -= 1
    b = k
    while b < len(prof) - 1 and prof[b + 1] == c:
        b += 1
    return a * step, (b + 1) * step


def cell_at(prs, y):
    runs = [run_at(pr, y) for pr in prs]
    if any(r is None for r in runs):
        return None
    return max(r[0] for r in runs), min(r[1] for r in runs)


def dark_lines(pr):
    prof, step = pr
    ys, k = [], 0
    while k < len(prof):
        if prof[k] == "D":
            j = k
            while j + 1 < len(prof) and prof[j + 1] == "D":
                j += 1
            ys.append((k + j + 1) / 2 * step); k = j + 1
        else:
            k += 1
    return ys


def grey_ends(pr):
    prof, step = pr
    return [(k + 1) * step for k in range(len(prof) - 1) if prof[k] == "G" and prof[k + 1] != "G"]


def read_page(page, pix, label, legend):
    W = [w for w in page.get_text("words")]
    geo = columns(page, W)
    if not geo:
        return None
    cols, ytop = geo["cols"], geo["y_top"]
    spans = word_colours(page)
    out = {}
    for tag in ("A", "B"):
        prs = {}
        for i, (a, b) in enumerate(cols):
            sx = (a + 2.5, b - 2.5)
            prs[i] = [profile_vector(page, x) if tag == "A" else profile_raster(pix, x) for x in sx]
        # table bottom: lowest ruled line in any column above the page footer band
        foot = page.rect.height - 70
        # a rule counts only when both sample positions of the column see it (a glyph at one edge is not a rule)
        rules = [y for c in prs for y in dark_lines(prs[c][0]) if any(abs(y - z) < 1.2 for z in dark_lines(prs[c][1]))]
        shades = [y for c in prs for y in grey_ends(prs[c][0]) if any(abs(y - z) < 1.2 for z in grey_ends(prs[c][1]))]
        ybot = max([y for y in rules + shades if ytop < y < foot] or [ytop])
        # an unruled, unshaded last row directly under the last rule (e.g. "Wiring harness*") still belongs to the table
        nxt = [(w[1] + w[3]) / 2 for w in W if ybot < (w[1] + w[3]) / 2 < ybot + 14.5 and col_of((w[0] + w[2]) / 2, cols) == 1]
        if nxt:
            ybot += 14.5
        late = [w[4] for w in W if ybot < (w[1] + w[3]) / 2 < foot and NUMRE.match(w[4])
                and col_of((w[0] + w[2]) / 2, cols) in geo["num"]]
        words = []  # (col, yc, x0, text, colour, block, line)
        for w in W:
            yc = (w[1] + w[3]) / 2
            if not (ytop + 1 < yc < ybot):
                continue
            c = col_of((w[0] + w[2]) / 2, cols)
            if c is not None:
                words.append((c, yc, w[0], w[4], colour_of(w, spans), w[5], w[6]))
        rows, held = [], []
        for c in geo["num"]:
            for n in [x for x in words if x[0] == c and NUMRE.match(x[3])]:
                cell = cell_at(prs[c], n[1])
                if not cell:
                    held.append((n[3], "no cell found")); continue
                top, bot = cell[0], min(cell[1], ybot)
                inside = [x for x in words if top < x[1] < bot]
                nums_in = sorted([x for x in inside if x[0] == c and NUMRE.match(x[3])], key=lambda x: x[1])
                item_ys = sorted({round(x[1], 1) for x in inside if x[0] == 0 and ITEM.match(x[3])})
                shade = prs[c][0][0][min(len(prs[c][0][0]) - 1, int(round(n[1] / prs[c][0][1])))]
                aligned = any(abs(y - n[1]) < 3.5 for y in item_ys)
                if len(nums_in) > 1 or (shade == "W" and len(item_ys) > 1 and aligned):
                    # one number per item line: the number's own baseline down to the next item line / next number
                    lines1 = sorted({round(x[1], 1) for x in inside if x[0] == 1})
                    anchor = [y for y in lines1 if abs(y - n[1]) < 3.5]
                    if not anchor:
                        held.append((n[3], "several numbers in one cell, not on an item line")); continue
                    a0 = anchor[0]
                    stops = [y for y in item_ys if y > a0 + 3.5] + [x[1] - 3.5 for x in nums_in if x[1] > n[1] + 3.5]
                    seg_end = min(stops + [bot])
                    top, bot = a0 - 3.5, seg_end
                    inside = [x for x in inside if top < x[1] < bot]
                items = [x[3] for x in sorted(inside, key=lambda x: x[1]) if x[0] == 0 and ITEM.match(x[3])]
                if not items:  # item number centred in a taller merged cell (e.g. 8b over two sub-rows)
                    c0 = cell_at(prs[0], (top + bot) / 2)
                    if c0:
                        items = [x[3] for x in words if x[0] == 0 and c0[0] < x[1] < c0[1] and ITEM.match(x[3])]
                desc_lines = {}
                for x in sorted(inside, key=lambda x: (x[1], x[2])):
                    if x[0] == 1:
                        desc_lines.setdefault((x[5], x[6]), []).append(x[3])
                desc = "; ".join(clean(" ".join(v)) for v in desc_lines.values())
                note = clean(" ".join(x[3] for x in sorted(inside, key=lambda x: (x[1], x[2])) if x[0] == c and x is not n
                                      and not NUMRE.match(x[3])))
                if not desc:
                    held.append((n[3], "cell has no description line")); continue
                grey = n[4] != 0
                if grey and not legend:
                    held.append((n[3], "printed in grey without a legend")); continue
                rows.append((n[3], tuple(items), desc, note, grey))
        held += [(x, "below the last ruled or shaded row") for x in late]
        out[tag] = (rows, held)
    return out


def item_span(items):
    if not items:
        return "no item number"
    return ("item " + items[0]) if len(items) == 1 else f"items {items[0]}-{items[-1]}"


def main(pdf, outp, doc_label):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    legend = any("not available anymore" in p.get_text() for p in d)
    rows, diffs, held, seen, dup, unread = [], [], [], {}, [], []
    sections, lines, nper = {}, [], {}
    for i, p in enumerate(d):
        head = next((l.strip() for l in p.get_text().splitlines() if l.strip()), "")
        model = re.sub(r"(\S.{5,}?)\1$", r"\1", clean(head.split("|")[0])); date = clean(head.split("|")[1]) if "|" in head else ""
        pix = p.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM), colorspace=pymupdf.csGRAY)
        r = read_page(p, pix, model, legend)
        if not r:
            continue
        (ra, ha), (rb, hb) = r["A"], r["B"]
        if ra != rb or ha != hb:
            diffs.append({"page": i + 1, "only_a": [x for x in ra if x not in rb][:5], "only_b": [x for x in rb if x not in ra][:5],
                          "held_a": ha[:5], "held_b": hb[:5]})
        held += [{"page": i + 1, "number": n, "why": why} for n, why in ha if (n, why) in hb]
        # every part-number-like token on a table page must be loaded, held or a repeat; the rest is reported
        got = {x[0] for x in ra + rb} | {n for n, _ in ha + hb}
        for w in p.get_text("words"):
            t = w[4].strip("*(),;")
            if NUMRE.match(t) and re.search(r"\d{5}", t) and t not in got and t not in [u["number"] for u in unread]:
                unread.append({"page": i + 1, "number": t, "as_printed": w[4]})
        sec = f"{model} ({date})" if date else model
        sk = next((k for k, v in sections.items() if v == sec), None)
        if sk is None:
            sk = str(len(sections)); sections[sk] = sec
        for num, items, desc, note, grey in [x for x in ra if x in rb]:
            extra = f" [{note}]" if note else ""
            na = " (not available anymore)" if grey else ""
            text = f"{desc}{extra}{na} ({model} {item_span(items)})"
            if num in seen:
                dup.append({"page": i + 1, "number": num, "first_page": seen[num]}); continue
            seen[num] = i + 1; nper[i + 1] = nper.get(i + 1, 0) + 1
            rows.append(num)
            lines.append(f"{i + 1}|{nper[i + 1]}|{num}|{text.replace('|', '/')}|{sk}")
    # "agree": every loaded row was given identically by both passes (rows from one pass only are in "diffs", not loaded)
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs,
           "unread": unread, "numbers": len(seen),
           "held": held, "repeats": len(dup), "legend_not_available": legend,
           "sections": {k: f"{doc_label}: {v}" for k, v in sections.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "all_rows_agree": not diffs, "numbers": len(seen),
                      "held": held[:8], "unread": unread[:12], "repeats": len(dup), "diffs": diffs[:2]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
