"""Two-pass reader for Atwood (Dometic) hydro flame furnace "Parts Drawing & List" sheets (Word / Acrobat
PDFMaker tables): a ruled table Item | Category | P/N | Title | one rotated model column per furnace model with
"X" marks (column order Category | Item | P/N | Title in some sheets; some pages print two tables side by side).
Cells are bottom-aligned, a blank Item / Category cell continues the one above.

Pass A: text-line order. PDFMaker writes one line per table cell (blank cells as a blank line), so after the header
labels each row is: prefix cells (Item, Category), P/N, one or more Title lines, then exactly one mark cell
("X" or blank) per model column. Rows are anchored on the P/N cell.
Pass B: word boxes. Row bands come from the ruled table (pymupdf find_tables rows); in each band and table group the
P/N word sits under the "P/N" header, Title words lie right of the P/N cell and left of the first model column, and
each "X" goes to the nearest rotated model header.

Only rows on which both passes give the same number, title, category and model marks are kept. A row whose marks
do not cover every model column gets " [models: <names as printed>]" appended. Category is the row's section.
Output: supplied-documents JSON (rows page|n|number|description|section).
usage: python3 -I atwood_hf_parts_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

LABELS = {"Item", "Category", "P/N", "Title"}
MODEL = re.compile(r"^[A-Z]{0,2}\d{4}(_[A-Z0-9]+)*$|^\d{4}_[A-Z]+(_[A-Z]+)*$")
PN = re.compile(r"^\d{5}[A-Z]?$")
ITEM = re.compile(r"^\d{1,3}[A-Z]?$")


def header(lines):
    """-> (index after header, [group labels])"""
    for i, l in enumerate(lines):
        if l in ("Item", "Category") and i + 2 < len(lines) and lines[i + 1] in LABELS:
            j, labs = i, []
            while j < len(lines) and (lines[j] in LABELS or MODEL.match(lines[j])):
                labs.append(lines[j]); j += 1
            groups, cur = [], []
            for x in labs:
                if x in ("Item", "Category") and "Title" in cur:
                    groups.append(cur); cur = []
                cur.append(x)
            groups.append(cur)
            return j, groups
    return None, []


def models_text(marks, names):
    on = [n for n, m in zip(names, marks) if m]
    return "" if len(on) == len(names) else " [models: " + ", ".join(on) + "]"


def pass_a(page):
    """-> rows [group, category, number, title, marks], groups, bad. Two-up pages write each table row as the left
    group's cells then the right group's cells; an empty group-row is all blank cells."""
    lines = [l.strip() for l in page.get_text().splitlines()]
    start, groups = header(lines)
    if start is None:
        return [], groups, []
    g = groups[0]
    if any(x != g for x in groups):
        return [], groups, ["table groups differ"]
    pre = g[:g.index("P/N")]
    names = [x for x in g if x not in LABELS]
    T, rows, bad, k, gi = lines[start:], [], [], 0, 0
    width = len(pre) + 2 + len(names)
    while k < len(T):
        if not any(T[k:k + width]):          # empty group-row (or trailing blank lines)
            if k + width > len(T):
                break
            k += width; gi = (gi + 1) % len(groups); continue
        cells = dict(zip(pre, T[k:k + len(pre)]))
        j = k + len(pre)
        if j >= len(T) or not PN.match(T[j]) or not ITEM.match(cells.get("Item") or "1") \
                or (cells.get("Category") and PN.match(cells["Category"])):
            bad.append(" ".join(T[k:k + len(pre) + 1])); break
        num, j, title = T[j], j + 1, []
        while j < len(T) and T[j] not in ("", "X"):
            title.append(T[j]); j += 1
        marks = T[j:j + len(names)]
        if not title or len(marks) < len(names) or any(m not in ("", "X") for m in marks):
            bad.append(num); break
        rows.append([gi, cells.get("Category", ""), num, " ".join(" ".join(title).split()), [m == "X" for m in marks]])
        k = j + len(names); gi = (gi + 1) % len(groups)
    return rows, groups, bad


def table_rows(page):
    """row bboxes of each ruled table on the page (first row = header)"""
    return [[tuple(r.bbox) for r in t.rows] for t in page.find_tables().tables if t.rows]


def pass_b(page, tables=None):
    words = page.get_text("words")
    tables = table_rows(page) if tables is None else tables
    out = []
    for rws in tables:
        hy0, hy1 = rws[0][1], rws[0][3]
        hw = sorted([w for w in words if hy0 - 1 <= (w[1] + w[3]) / 2 <= hy1 + 1], key=lambda w: w[0])
        groups, cur = [], []
        for w in hw:
            if w[4] in ("Item", "Category") and any(c[4] == "Title" for c in cur):
                groups.append(cur); cur = []
            if w[4] in LABELS or MODEL.match(w[4]):
                cur.append(w)
        if cur:
            groups.append(cur)
        G, edge = [], -1e9
        for gi, gw in enumerate(groups):
            lab = {w[4]: w for w in gw if w[4] in LABELS}
            mods = [w for w in gw if w[4] not in LABELS]
            if "P/N" not in lab or not mods:
                continue
            cx = [(m[0] + m[2]) / 2 for m in mods]
            half = min([b - a for a, b in zip(cx, cx[1:])] or [20]) / 2
            x1 = cx[-1] + half if gi + 1 < len(groups) else 1e9
            G.append((gi, edge, x1, lab, mods, cx, half)); edge = x1
        # elementary row bands: a merged Item cell spanning two rows makes find_tables report a row covering both,
        # so cut the table at every distinct row boundary
        ys = sorted({round(v, 1) for r in rws[1:] for v in (r[1], r[3])})
        for y0, y1 in zip(ys, ys[1:]):
            if y1 - y0 < 3:
                continue
            band = [w for w in words if y0 - 0.5 <= (w[1] + w[3]) / 2 <= y1 + 0.5]
            for gi, x0, x1, lab, mods, cx, half in G:
                bw = [w for w in band if x0 <= (w[0] + w[2]) / 2 < x1]
                ph = lab["P/N"]; pcx = (ph[0] + ph[2]) / 2
                pns = [w for w in bw if PN.match(w[4]) and abs((w[0] + w[2]) / 2 - pcx) < 22]
                if len(pns) != 1:
                    if pns:
                        out.append([gi, "?", "/".join(w[4] for w in pns), "", []])
                    continue
                pw = pns[0]
                left_model = cx[0] - half
                tw = sorted([w for w in bw if w[0] > max(ph[2], pw[2]) and w[2] <= left_model],
                            key=lambda w: (round(w[3]), w[0]))
                cat = [w for w in bw if w[2] < min(ph[0], pw[0]) and not ITEM.match(w[4])]
                if "Category" in lab and "Item" in lab:
                    # category cell lies between its own header bounds: left of P/N, not the item column
                    ic = (lab["Item"][0] + lab["Item"][2]) / 2
                    cat = [w for w in cat if abs((w[0] + w[2]) / 2 - ic) > 12 or len(w[4]) > 3]
                cat = sorted(cat, key=lambda w: (round(w[3]), w[0]))
                marks = [False] * len(mods)
                for w in bw:
                    if w[4] == "X" and w[0] > left_model - 2:
                        c = (w[0] + w[2]) / 2
                        k = min(range(len(cx)), key=lambda i: abs(cx[i] - c))
                        if abs(cx[k] - c) < half:
                            marks[k] = True
                out.append([gi, " ".join(w[4] for w in cat), pw[4], " ".join(w[4] for w in tw), marks])
    return out


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, sections, unread, bad_all, prev = [], [], {}, [], [], ""
    for i, p in enumerate(d):
        a, groups, bad = pass_a(p)
        if not groups:
            continue
        names = [x for x in groups[0] if x not in LABELS]
        b = pass_b(p)
        # category carries down within the page (blank cell = same as above); the page's first rows may continue
        # the previous page's category, so carry across pages too
        def carry(rs):
            outr, last = [], {}
            for gi, cat, num, title, marks in rs:
                last[gi] = cat or last.get(gi) or prev
                outr.append((last[gi], num, title, tuple(marks)))
            return outr
        A, B = carry(a), carry(b)
        bad_all += [{"page": i + 1, "number": x} for x in bad]
        if A != B:
            diffs.append({"page": i + 1, "only_a": [x for x in A if x not in B][:4], "only_b": [x for x in B if x not in A][:4]})
        good = [x for x in A if x in B]
        if A:
            prev = A[-1][0]
        for n, (cat, num, title, marks) in enumerate(good, 1):
            if cat not in sections.values():
                sections[str(len(sections) + 1)] = cat
            code = [k for k, v in sections.items() if v == cat][0]
            rows.append((i + 1, n, num, title + models_text(marks, names), code))
        known = {r[2] for r in a} | {r[2] for r in b}
        titles = " ".join(r[3] for r in a)
        unread += [{"page": i + 1, "number": w[4]} for w in p.get_text("words")
                   if PN.match(w[4]) and w[4] not in known and w[4] not in titles]
    seen, lines = {}, []
    for pg, n, num, desc, code in rows:
        if num in seen:
            continue
        seen[num] = 1; lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{code}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and not bad_all and not unread and bool(lines),
           "diffs": diffs, "bad": bad_all, "rows_total": len(rows), "numbers": len(seen), "unread": unread,
           "sections": sections, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "sections": len(sections), "unread": unread[:5], "bad": bad_all[:5], "diffs": diffs[:2]},
                     ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
