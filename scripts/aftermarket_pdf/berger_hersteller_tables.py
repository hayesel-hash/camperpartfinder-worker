"""Two-pass reader for the Fritz Berger "Ersatzteil-Katalog" caravan and motorhome spare-parts catalogue 2017-2018 (German;
ChatGPT splits "Berger - Caravan and Motorhome Spare Parts Catalogue 2017-2018 - pp NNN-MMM.pdf").

Tables are "Pos. | Berger-Nr. | <MAKER>-Nr. | Artikel-Bezeichnung" (7 pt; header bold) under exploded drawings, one or two
table columns per page; a table can continue in the other column under a repeated header. Product headings ("Markise F45 L -
Titanium 450-550") are 12-16 pt bold lines. Larry's 27 Nov decision on distributor catalogues: the maker's number printed
under that maker's name is that maker's part; Berger-Nr. (Berger's stock number) is never a part. Rules:
- the maker is the column header before "-Nr." (FIAMMA-Nr. -> FIAMMA); only tables whose header names the maker passed with
  --maker are read (one publisher per supplied document); other makers' tables are counted in "other_makers";
- a row needs a 1-3 digit Pos. (optionally with a letter), a 6-digit Berger-Nr. and a maker number of part-number shape that
  does not end in "-" (cut-off prints such as "05106-03-" are reported as unread);
- description = Artikel-Bezeichnung + " [<product heading>]" (nearest 12-16 pt bold heading line above the table header,
  grouped by baseline; Berger's own "(Nr. nnnnnn)" stock number is dropped from the heading);
  a line with only Artikel-Bezeichnung text continues the row above;
- a number printed with two different descriptions (heading ignored) is not loaded.
Pass A: pymupdf spans (each table row is one span; cells split on runs of 2+ spaces). Pass B: pdfplumber words assigned to the
header columns by x. Only rows both passes give identically are kept.
- --hold-unique-shapes (used for Truma): a number whose digit/letter shape no other number of the maker in the split has
  (Truma "4000-01100" among 99999-99999 / 99999-99) is held as a possible misprint.
usage: python3 -I berger_hersteller_tables.py <pdf> <out.json> --maker FIAMMA --name Fiamma [--hold-unique-shapes]
"""
import collections, hashlib, json, re, sys
import pdfplumber, pymupdf

NUM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./-]{1,39}$")
POS = re.compile(r"^[0-9]{1,3} ?[a-z]?$")  # "8 c" is printed with a space
BNR = re.compile(r"^[0-9]{6}$")
HDR = re.compile(r"^Pos\.\s+Berger-Nr\.\s+(.+?)-Nr\.\s+Artikel-Bezeichnung$")


def sp(s):
    return " ".join((s or "").split())


def headings_a(page):
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip() and s["size"] >= 11 and "Bold" in s["font"] and abs(l["dir"][0] - 1) < 0.01:
                    lines.append((s["bbox"][3], s["bbox"][0], s["text"], s["bbox"][2]))  # by baseline: " PRO - " spans are taller
    return join_heading_lines(lines)


def join_heading_lines(items):
    """Heading lines by baseline; on one baseline only the run of parts that starts with the leftmost part and has no gap
    over 30 pt is the heading (drawing callout letters "H", "S", "E" sit far to the right on the same baseline)."""
    out = []
    for y, x, t, x1 in sorted(items):
        if out and abs(out[-1][0] - y) <= 4:
            out[-1][1].append((x, t, x1))
        else:
            out.append([y, [(x, t, x1)]])
    res = []
    for y, parts in out:
        parts.sort()
        run = [parts[0]]
        for prt in parts[1:]:
            if prt[0] - max(r[2] for r in run) > 30:
                break
            run.append(prt)
        res.append((y, sp(" ".join(t for x, t, x1 in run))))
    # drawing callout letters ("S", "E", "T") are big bold too: a heading needs three letters in a row
    return [(y, t) for y, t in res if re.search(r"[A-Za-zÄÖÜäöü]{3}", t)]


def heading_for(heads, y):
    """Nearest heading line above y; Berger's own stock number "(Nr. 116100)" is dropped from it (never a part)."""
    above = [h for h in heads if h[0] < y]
    h = max(above)[1] if above else ""
    return sp(re.sub(r"\s*-?\s*\(Nr\.\s*[0-9]+\)\s*$", "", h)).rstrip(" -")


def pass_a(page):
    heads = headings_a(page)
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            if abs(l["dir"][0] - 1) > 0.01:
                continue
            for s in l["spans"]:
                if s["text"].strip() and s["size"] <= 7.5:
                    spans.append((s["bbox"][0], s["bbox"][1], s["bbox"][3], s["text"]))
    tables = []
    for x0, y0, y1, t in spans:
        m = HDR.match(sp(t))
        if m:
            tables.append({"x": x0, "y": y1, "maker": sp(m.group(1)), "head": heading_for(heads, y0)})
    rows, unread = [], []
    for tb in tables:
        mine = sorted((s for s in spans if abs(s[0] - tb["x"]) <= 8 and s[1] > tb["y"] - 1), key=lambda s: s[1])
        last_y, last = tb["y"], None
        for x0, y0, y1, t in mine:
            if y0 - last_y > 12 or HDR.match(sp(t)):
                break
            last_y = y1
            cells = [c for c in re.split(r"\s{2,}", t.strip()) if c]
            if len(cells) >= 4 and POS.match(cells[0]) and BNR.match(cells[1]):
                num, desc = cells[2], sp(" ".join(cells[3:]))
                if not NUM.match(num) or num.endswith("-"):
                    unread.append({"cells": cells, "maker": tb["maker"]}); last = None; continue
                last = {"maker": tb["maker"], "number": num, "desc": [desc], "head": tb["head"]}
                rows.append(last)
            elif len(cells) == 1 and last is not None and (x0 > tb["x"] + 40 or re.match(r"^\s{10,}", t)):
                # wrapped description: its own span, either placed at the description column or padded with spaces
                last["desc"].append(cells[0])
            else:
                unread.append({"cells": cells, "maker": tb["maker"]}); last = None
    return [{"maker": r["maker"], "number": r["number"], "desc": sp(" ".join(r["desc"])), "head": r["head"]} for r in rows], unread


def pass_b(pp):
    words = pp.extract_words(extra_attrs=["size", "fontname", "upright"], keep_blank_chars=False)
    hw = [(w["bottom"], w["x0"], w["text"], w["x1"]) for w in words if w["upright"] and w["size"] >= 11 and "Bold" in w["fontname"]]
    heads = join_heading_lines(hw)
    small = [w for w in words if w["upright"] and w["size"] <= 7.5]
    lines = []
    for w in sorted(small, key=lambda w: (round(w["bottom"]), w["x0"])):
        if lines and abs(lines[-1][0] - w["bottom"]) <= 1.5:
            lines[-1][1].append(w)
        else:
            lines.append([w["bottom"], [w]])
    tables = []
    for b, ws in lines:
        ws.sort(key=lambda w: w["x0"])
        for k, w in enumerate(ws):
            if w["text"] == "Pos." and k + 3 < len(ws) and ws[k + 1]["text"] == "Berger-Nr." and ws[k + 2]["text"].endswith("-Nr.") \
                    and ws[k + 3]["text"] == "Artikel-Bezeichnung":
                tables.append({"x": w["x0"], "y": b, "top": w["top"], "bn": ws[k + 1]["x0"], "mn": ws[k + 2]["x0"],
                               "ab": ws[k + 3]["x0"], "maker": ws[k + 2]["text"][:-4], "head": heading_for(heads, w["top"])})
    rows, unread = [], []
    for tb in tables:
        last_b, last = tb["y"], None
        for b, ws in lines:
            if b <= tb["y"] + 1:
                continue
            mine = [w for w in ws if tb["x"] - 8 <= w["x0"] and w["x0"] < tb["ab"] + 260]
            # a table in the next page column (started above this line) bounds this one on the right
            other_tables = [t for t in tables if t is not tb and t["x"] > tb["x"] + 120 and t["y"] < b]
            if other_tables:
                lim = min(t["x"] for t in other_tables) - 4
                mine = [w for w in mine if w["x0"] < lim]
            if not mine:
                continue
            # a new header ends the table ("bitte Pos. 3 mitbestellen" in a description does not)
            if b - last_b > 12 or (any(w["text"] == "Pos." for w in mine) and any(w["text"] == "Berger-Nr." for w in mine)):
                break
            last_b = b
            cells = {"pos": [], "bn": [], "mn": [], "ab": []}
            for w in mine:
                k = "ab" if w["x0"] >= tb["ab"] - 4 else "mn" if w["x0"] >= tb["mn"] - 6 else "bn" if w["x0"] >= tb["bn"] - 6 else "pos"
                cells[k].append(w["text"])
            c = {k: sp(" ".join(v)) for k, v in cells.items()}
            if POS.match(c["pos"]) and BNR.match(c["bn"]) and c["mn"] and c["ab"]:
                if " " in c["mn"] or not NUM.match(c["mn"]) or c["mn"].endswith("-"):
                    unread.append({"cells": c, "maker": tb["maker"]}); last = None; continue
                last = {"maker": tb["maker"], "number": c["mn"], "desc": [c["ab"]], "head": tb["head"]}
                rows.append(last)
            elif not c["pos"] and not c["bn"] and not c["mn"] and c["ab"] and last is not None:
                last["desc"].append(c["ab"])
            else:
                unread.append({"cells": c, "maker": tb["maker"]}); last = None
    return [{"maker": r["maker"], "number": r["number"], "desc": sp(" ".join(r["desc"])), "head": r["head"]} for r in rows], unread


def main(pdf, outp, maker, name, hold_unique_shapes=False):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, other, unread = [], [], collections.Counter(), []
    key = lambda r: (r["maker"].upper(), r["number"], "".join(r["desc"].split()).casefold(), "".join(r["head"].split()).casefold())
    for i, p in enumerate(d):
        ra, ua = pass_a(p)
        rb, ub = pass_b(pl.pages[i])
        ra_m = [r for r in ra if r["maker"].upper() == maker.upper()]
        rb_m = [r for r in rb if r["maker"].upper() == maker.upper()]
        other.update(r["maker"] for r in ra if r["maker"].upper() != maker.upper())
        ka, kb = collections.Counter(key(r) for r in ra_m), collections.Counter(key(r) for r in rb_m)
        if ka != kb:
            diffs.append({"page": i + 1, "only_a": [r for r in ra_m if key(r) not in kb][:3], "only_b": [r for r in rb_m if key(r) not in ka][:3]})
        keep += [(i + 1, r) for r in ra_m if key(r) in kb]
        unread += [dict(u, page=i + 1) for u in ua if u["maker"].upper() == maker.upper()]
    names = collections.defaultdict(set)
    for pg, r in keep:
        names[r["number"]].add("".join(r["desc"].split()).casefold())
    conflict = {n for n, v in names.items() if len(v) > 1}
    shape = lambda n: re.sub(r"[A-Za-z]", "A", re.sub(r"[0-9]", "9", n))
    shapes = collections.Counter(shape(n) for n in names)
    odd = set()
    if hold_unique_shapes and len(names) >= 20:
        # e.g. Truma "4000-01100" among 99999-99999 / 99999-99 numbers: a digit is probably missing
        odd = {n for n in names if shapes[shape(n)] == 1}
    conflict |= odd
    lines, seen, per = [], set(), {}
    for pg, r in keep:
        if r["number"] in conflict or r["number"] in seen:
            continue
        seen.add(r["number"]); per[pg] = per.get(pg, 0) + 1
        desc = r["desc"] + (f" [{r['head']}]" if r["head"] else "")
        lines.append(f"{pg}|{per[pg]}|{r['number']}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines) and not diffs, "page_diffs": diffs,
           "rows_total": len(keep), "numbers": len(seen), "maker": name,
           "sections": {"0": f"Fritz Berger Ersatzteil-Katalog 2017-2018 (distributor): {name} numbers from the {maker}-Nr. column"},
           "rows": "\n".join(lines), "conflicts": sorted(conflict - odd), "odd_shape_held": sorted(odd), "other_makers": dict(other), "unread": unread}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "numbers": len(seen), "diff_pages": len(diffs), "diffs": diffs[:2],
                      "conflicts": sorted(conflict)[:10], "other": other.most_common(8), "unread": len(unread),
                      "unread_sample": unread[:5]}, ensure_ascii=False)[:3500])


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[a.index("--maker") + 1], a[a.index("--name") + 1], "--hold-unique-shapes" in a)
