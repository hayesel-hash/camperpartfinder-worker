"""Line reader for Thetford European cooker spare-parts lists (Caprice SOH72XXX, Enigma SOH46, Triplex SOH76XXX / SOH77XXX):
the ruled table  No. | Description | Spare part number | Spare part number | Colours available.

Why a second reader next to thetford_eu_spare_list.py: on the cooker lists that reader's cell geometry is right, but
  - sub-rows lose their item name ("25 Oven burner" / "Production date: < 31-07-21 (E212Y...)" / SSPA0191),
  - italic words land out of order ("all models Light switch *not"),
  - "≥" is printed as ">" with a separate underline drawing, so the text layer says "> 14-04-2015".
This reader works line by line instead:
  - words are grouped into baselines; the description is the x-sorted words of the Description column on the number's
    own baseline; a line with no item number is a sub-row and is prefixed with the description of the item line above
    it ("Oven burner: Production date: < 31-07-21 (E212Y...)");
  - a ">" / "<" glyph with a horizontal rule drawn directly under it is read as "≥" / "≤"; a ">" / "<" whose underline
    cannot be decided (a rule only partly under it) holds the row;
  - a number in the second "Spare part number" column takes the column's sub-heading printed on the item line
    ("For lid shut off") in brackets; without a sub-heading it is held;
  - a number printed in grey is "not available anymore" (legend in the document); grey (struck) words inside a
    description hold the row; a number whose baseline has no description (a merged kit cell) is held;
  - a number printed with two different descriptions in the document is held; the same number printed on several
    sub-rows of one item (e.g. SSPA0675 front left / front right / rear left thermocouple) is one row naming all of them.
Pass A: pymupdf words, span colours and drawings.  Pass B: pdfplumber words, char colours, lines and rects.
Only rows both passes give identically are returned.  The door / knob tables (Spare part number | Glass | Print ...)
are not read.
usage: python3 -I thetford_cooker_lines.py <pdf> <out.json> "<document label>" """
import hashlib, json, re, sys
import pymupdf
import pdfplumber

NUM = re.compile(r"^(SSPA|SSPO|SMAO|SSP)[A-Z0-9.]{3,}$")
ITEM = re.compile(r"^\d{1,3}[a-z]?$")


def clean(s):
    return " ".join(s.split())


def grey(rgb):
    if rgb is None:
        return False
    if isinstance(rgb, (int, float)):
        rgb = (rgb, rgb, rgb)
    rgb = tuple(rgb)
    if len(rgb) == 1:
        rgb = rgb * 3
    if len(rgb) == 4:  # cmyk
        c, m, y, k = rgb
        rgb = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return min(rgb) > 0.3


def words_a(page):
    """(x0, y0, x1, y1, text, is_grey) from pymupdf, plus horizontal rules (x0, x1, y)."""
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                c = s["color"]; rgb = ((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255
                spans.append((pymupdf.Rect(s["bbox"]), rgb))
    out = []
    for w in page.get_text("words"):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        g = next((grey(rgb) for r, rgb in spans if r.x0 - 0.5 <= cx <= r.x1 + 0.5 and r.y0 - 0.5 <= cy <= r.y1 + 0.5), False)
        out.append((w[0], w[1], w[2], w[3], w[4], g))
    glyphs = [(ch["c"],) + tuple(ch["bbox"]) for b in page.get_text("rawdict")["blocks"] for l in b.get("lines", [])
              for s in l["spans"] for ch in s["chars"] if ch["c"] in "<>"]
    rules = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.height < 1.2 and r.width > 1:
            rules.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.3:
                rules.append((min(it[1].x, it[2].x), max(it[1].x, it[2].x), it[1].y))
    return out, rules, glyphs


def words_b(pg):
    out = []
    for w in pg.extract_words(x_tolerance=2.5, keep_blank_chars=False, extra_attrs=["non_stroking_color"]):
        out.append((w["x0"], w["top"], w["x1"], w["bottom"], w["text"], grey(w.get("non_stroking_color"))))
    rules = [(r["x0"], r["x1"], (r["top"] + r["bottom"]) / 2) for r in pg.rects if r["height"] < 1.2 and r["width"] > 1]
    rules += [(min(l["x0"], l["x1"]), max(l["x0"], l["x1"]), l["top"]) for l in pg.lines if abs(l["top"] - l["bottom"]) < 0.3]
    glyphs = [(c["text"], c["x0"], c["top"], c["x1"], c["bottom"]) for c in pg.chars if c["text"] in "<>"]
    return out, rules, glyphs


def underlined(g, rules):
    """True if a short rule sits right under the glyph box (x0, y0, x1, y1), None if a rule touches it only partly,
    else False."""
    x0, y0, x1, y1 = g; wid = x1 - x0
    best = 0
    for a, b, y in rules:
        if y1 - 3.5 <= y <= y1 + 2.5 and b - a < 12:
            best = max(best, (min(b, x1) - max(a, x0)) / wid)
    return True if best >= 0.6 else (None if best > 0.05 else False)


def fix_signs(w, rules, glyphs):
    """The word's text with each '>' / '<' read against its own glyph box; None if an underline is unclear."""
    t = w[4]
    if ">" not in t and "<" not in t:
        return t
    gs = sorted([g for g in glyphs if w[0] - 0.5 <= (g[1] + g[3]) / 2 <= w[2] + 0.5 and w[1] - 1 <= (g[2] + g[4]) / 2 <= w[3] + 1],
                key=lambda g: g[1])
    signs = [c for c in t if c in "<>"]
    if len(gs) != len(signs):
        return None
    out, k = [], 0
    for c in t:
        if c in "<>":
            u = underlined(gs[k][1:], rules); k += 1
            if u is None:
                return None
            c = ("≥" if c == ">" else "≤") if u else c
        out.append(c)
    return "".join(out)


def read(words, rules, glyphs):
    """Rows (number, item, description, grey) and held (number, why) for one page of one pass."""
    # the parts table header: "Spare part number" column heads right of the description and "Colours available" on the
    # same line (the door / knob tables print "Spare part number" as a row label at the left edge and are not read)
    spare = sorted([w for w in words if w[4] == "Spare" and w[0] > 250], key=lambda w: w[0])
    if not spare:
        return None
    yh = spare[0][1]
    spare = [w for w in spare if abs(w[1] - yh) < 3]
    colours = [w for w in words if w[4] == "Colours" and w[0] > spare[-1][2] and abs(w[1] - yh) < 3]
    if not colours:
        return None
    hdr_bot = max(w[3] for w in words if abs(w[1] - yh) < 30 and w[4] in ("number", "available", "Spare", "part", "Colours"))
    numx = [((w[0] + w[2]) / 2) for w in spare]
    desc_x0 = min(w[0] for w in words if w[1] > hdr_bot and ITEM.match(w[4]) is None and w[0] > 70 and w[2] < numx[0] - 40)
    col_x = numx + [(colours[0][0] + colours[0][2]) / 2]
    foot = max(w[1] for w in words if "anymore" in w[4]) if any("anymore" in w[4] for w in words) else 99999

    def col(w):
        cx = (w[0] + w[2]) / 2
        if w[2] < desc_x0 - 2:
            return "item"
        if cx < numx[0] - 40:
            return "desc"
        return min(range(len(col_x)), key=lambda i: abs(col_x[i] - cx))  # 0, 1 = number columns, 2 = colours

    body = sorted([w for w in words if hdr_bot + 1 < (w[1] + w[3]) / 2 < foot - 2], key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines = []
    for w in body:
        yc = (w[1] + w[3]) / 2
        if lines and abs(lines[-1][0] - yc) < 2.5:
            lines[-1][1].append(w)
        else:
            lines.append([yc, [w]])
    rows, held = [], []
    item, parent, subhead, parent_numbered = None, "", {}, False
    ncols = len(numx)
    for li, (yc, ws) in enumerate(lines):
        ws = sorted(ws, key=lambda w: w[0])
        it = [w for w in ws if col(w) == "item" and ITEM.match(w[4])]
        dws = [w for w in ws if col(w) == "desc"]
        parts = []
        for w in dws:
            t = fix_signs(w, rules, glyphs)
            parts.append("?UNDERLINE?" if t is None else t)
        desc = clean(" ".join(parts)).replace("( ", "(")
        desc_grey = any(w[5] for w in dws)
        nums = [(col(w), w) for w in ws if isinstance(col(w), int) and col(w) < ncols and NUM.match(w[4])]
        other = [(col(w), w[4]) for w in ws if isinstance(col(w), int) and col(w) < ncols and not NUM.match(w[4])]
        heading = False
        if it:
            item = it[0][4]; parent = desc; subhead = {}; heading = True
            parent_numbered = bool(nums)  # then the lines below without an item number are variants, not sub-rows
        elif (not nums and desc and item is not None and not parent_numbered
              and not any(re.match(r"^(Not|available|Refer|to|page|\d+)$", x) for _, x in other)):
            # a sub-heading inside an item ("Production date: >= 25-06-2012 (>= E176N...)" over a second group of rows)
            parent = parent.split(" || ")[0] + " || " + desc; heading = True
        if heading:
            for c in range(ncols):
                t = clean(" ".join(x for cc, x in other if cc == c))
                if t and not re.match(r"^(Refer to page \d+|Not available)$", t):
                    subhead[c] = t
        for c, w in nums:
            n = w[4]
            # words printed under the number in its own column on a line with no description ("> 06-12-16 (E340T...)")
            # qualify it: such numbers are held
            nxt = lines[li + 1][1] if li + 1 < len(lines) else []
            if nxt and not any(col(x) in ("item", "desc") for x in nxt) and any(col(x) == c and not NUM.match(x[4]) for x in nxt):
                held.append((n, "qualifier printed under the number in its cell")); continue
            if not desc:
                held.append((n, "no description on the number's line (merged cell)")); continue
            if desc_grey and not w[5]:
                held.append((n, "grey (struck) words inside the description")); continue
            if "?UNDERLINE?" in desc:
                held.append((n, "'>' / '<' with an unclear underline")); continue
            if item is None:
                held.append((n, "no item number above")); continue
            d = desc if (it or parent_numbered) else f"{parent.replace(' || ', ': ')}: {desc}"
            tag = ""
            if c > 0:
                if c not in subhead:
                    held.append((n, "second number column without a sub-heading")); continue
                tag = f" [{subhead[c]}]"
            # a remark printed in another number column of the same line ("Use 800W version") is kept as a note
            rem = clean(" ".join(x[4] for x in ws if isinstance(col(x), int) and col(x) < ncols and col(x) != c
                                 and not NUM.match(x[4])))
            if rem and not it and not re.match(r"^(Refer to page \d+|Not available)$", rem):
                tag += f" [{rem}]"
            rows.append((n, item, d, bool(w[5]), tag))
    return rows, held


def main(pdf, outp, label):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    legend = any("not available anymore" in p.get_text() for p in d)
    per = {}
    diffs = []
    held = []
    one_pass = set()
    model = ""
    for i, p in enumerate(d):
        head = next((l.strip() for l in p.get_text().splitlines() if l.strip()), "")
        if "|" in head and not model:
            model = clean(head.split("|")[0]); date = clean(head.split("|")[1])
        ra = read(*words_a(p)); rb = read(*words_b(pl.pages[i]))
        if ra is None and rb is None:
            continue
        if ra is None or rb is None:
            diffs.append({"page": i + 1, "why": "table found by one pass only"}); continue
        if ra != rb:
            oa = [x for x in ra[0] if x not in rb[0]]; ob = [x for x in rb[0] if x not in ra[0]]
            diffs.append({"page": i + 1, "only_a": oa[:6], "only_b": ob[:6]})
            # a number with any occurrence given by one pass only is not loaded at all (its description could be partial)
            one_pass.update(x[0] for x in oa + ob)
        for r in ra[0]:
            if r in rb[0]:
                per.setdefault(r[0], []).append((i + 1,) + r)
        held += [{"page": i + 1, "number": n, "why": why} for n, why in ra[1] if (n, why) in rb[1]]
    if not legend and any(r[4] for v in per.values() for r in v):
        raise SystemExit("grey numbers without a legend")
    rows, conflicts = [], []
    for n, occ in per.items():
        if n in one_pass:
            held.append({"page": occ[0][0], "number": n, "why": "one occurrence read by one pass only"}); continue
        descs = {o[3] for o in occ}
        tags = {o[5] for o in occ}
        if len(tags) > 1:
            conflicts.append({"number": n, "descriptions": sorted(o[3] + o[5] for o in occ)}); continue
        tag = tags.pop()
        if len(descs) > 1:
            heads = {dd.rsplit(": ", 1)[0] for dd in descs}
            items = {o[2] for o in occ}
            if len(heads) == 1 and len(items) == 1 and all(":" in dd for dd in descs):
                h = heads.pop(); order = [o[3] for o in occ]
                desc = h + ": " + " / ".join(dd.rsplit(": ", 1)[1].strip() for dd in sorted(descs, key=order.index))
            else:
                conflicts.append({"number": n, "descriptions": sorted(descs)}); continue
        else:
            desc = descs.pop()
        desc += tag
        o = occ[0]
        na = " (not available anymore)" if any(x[4] for x in occ) else ""
        rows.append((o[0], n, f"{desc}{na} ({model} item {o[2]})"))
    rows.sort()
    lines, nper = [], {}
    for pg, n, text in rows:
        nper[pg] = nper.get(pg, 0) + 1
        lines.append(f"{pg}|{nper[pg]}|{n}|{text.replace('|', '/')}|0")
    held_nums = {h["number"] for h in held} - {r[1] for r in rows}
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs, "numbers": len(rows),
           "held": [h for h in held if h["number"] in held_nums], "conflicts": conflicts,
           "sections": {"0": f"{label}: {model} ({date})"}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("doc", "agree", "numbers", "diffs", "held", "conflicts")}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
