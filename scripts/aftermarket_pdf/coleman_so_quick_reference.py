"""Two-pass reader for the Coleman-Mach pages of a distributor's "PARTS QUICK REFERENCE" (section Q, printed pp 552-567;
Drive file "Coleman Air Conditioner - RV Replacement Parts Guide.pdf"). Each page is headed "COLEMAN-MACH AIR CONDITIONER
PARTS" (or "COLEMAN AIR CONDITIONER PARTS"); a PARTS DESCRIPTION column, an ORDER # column (the distributor's stock number,
"NLA" or "S/O") and bullet model columns. Coleman-Mach's own number is printed only for special-order parts, as "(S/O nnnn-nnnn)"
in the description cell: on the description's line ("Relay (S/O 1497-5051)") or on the line right under it
("Shroud (Ivory/Ivory)" / "(S/O 6727-5781)").

Larry's 27 Nov decision on distributor catalogues: a maker's number printed under that maker's name with a description is that
maker's part (supplied lane, kind distributor_catalogue); distributor stock numbers are never parts; model bullets are
applicability only (not stored). Rules:
- only pages whose text names COLEMAN in an "... AIR CONDITIONER PARTS" heading are read (no maker inferred elsewhere);
- only "(S/O <number>)" in the description column is read; bare "S/O 9330-..." lines (X-Reference pages) are reported, not read;
- description = the words before "(S/O" on the same line, else the description-column line directly above (<= 12 pt) when that
  line is not a section heading ("SHROUDS:") and the line above it is not part of the same cell (a 3-line description is held);
- the upper-case section heading above ("CAPACITORS:") follows the description in brackets ("Fan (5-Mfd/370V) [Capacitors]");
  a description that starts with "(" ("(Ivory) With Decals") is a variant line of a longer cell and is held.
Pass A pymupdf words, pass B pdfplumber words; only rows both passes give identically are kept.
usage: python3 -I coleman_so_quick_reference.py <pdf> <out.json>
"""
import hashlib, json, re, sys
import pdfplumber, pymupdf

SO_NUM = re.compile(r"^([0-9]{4}[-A-Z][0-9]{3,4})\)$")


def sp(s):
    return " ".join(s.split())


def words_a(page):
    return [{"x0": w[0], "top": w[1], "x1": w[2], "bottom": w[3], "text": w[4]} for w in page.get_text("words")]


def words_b(ppage):
    return [{"x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"], "text": w["text"]}
            for w in ppage.extract_words(keep_blank_chars=False, use_text_flow=False)]


def baselines(ws):
    rows = []
    for w in sorted(ws, key=lambda w: (w["bottom"], w["x0"])):
        if rows and abs(rows[-1][0] - w["bottom"]) <= 2.0:
            rows[-1][1].append(w)
        else:
            rows.append([w["bottom"], [w]])
    return [(b, sorted(r, key=lambda w: w["x0"])) for b, r in rows]


def read_page(ws, text):
    if not re.search(r"COLEMAN(-MACH)?\s+AIR\s+CONDITIONER\s+PARTS", text):
        return [], [], [{"why": "page names no Coleman heading"}]
    lines = baselines(ws)
    hdr = next(((b, ln) for b, ln in lines for k in range(len(ln) - 1)
                if ln[k]["text"] == "PARTS" and ln[k + 1]["text"] == "DESCRIPTION"), None)
    if not hdr:
        return [], [], [{"why": "no PARTS DESCRIPTION header"}]
    x_lo = hdr[1][0]["x0"] - 30
    order = [w for b, ln in lines for w in ln if w["text"] == "ORDER" and abs(b - hdr[0]) < 12]
    x_hi = order[0]["x0"] - 2 if order else x_lo + 140
    col = []
    for b, ln in lines:
        if b <= hdr[0] + 2:
            continue
        ws_ = [w for w in ln if x_lo <= w["x0"] < x_hi]
        if ws_:
            col.append((b, ws_))
    rows, held, unread = [], [], []
    section = ""
    for i, (b, ln) in enumerate(col):
        t = sp(" ".join(w["text"] for w in ln))
        if re.fullmatch(r"[A-Z][A-Z &/-]+:", t):
            section = t[:-1].title()
            continue
        k = next((j for j, w in enumerate(ln) if w["text"].upper() == "(S/O"), None)
        if k is None:
            if re.search(r"\bS/O\s+\d", t):
                unread.append({"text": t, "why": "bare S/O line (not in a description cell)"})
            continue
        if k + 1 >= len(ln) or not SO_NUM.match(ln[k + 1]["text"]):
            held.append({"text": t, "why": "S/O number not in the expected form"}); continue
        num = SO_NUM.match(ln[k + 1]["text"]).group(1)
        rest = sp(" ".join(w["text"] for w in ln[k + 2:]))
        before = sp(" ".join(w["text"] for w in ln[:k]))
        if rest:
            held.append({"number": num, "why": "text after the S/O number", "text": t}); continue
        if not before:
            if i == 0 or b - col[i - 1][0] > 12.5:
                held.append({"number": num, "why": "no description line directly above"}); continue
            pb, pln = col[i - 1]
            ptxt = sp(" ".join(w["text"] for w in pln))
            if re.fullmatch(r"[A-Z][A-Z &/-]+:", ptxt) or "(S/O" in ptxt:
                held.append({"number": num, "why": "line above is a heading or another S/O line"}); continue
            if i >= 2 and pb - col[i - 2][0] <= 10.5 and not re.fullmatch(r"[A-Z][A-Z &/-]+:", sp(" ".join(w["text"] for w in col[i - 2][1]))):
                held.append({"number": num, "why": "description runs over more than one line", "text": ptxt}); continue
            before = ptxt
        if before.startswith("("):
            held.append({"number": num, "why": "description is a variant line of a longer cell", "text": before}); continue
        desc = before + (f" [{section}]" if section else "")
        rows.append({"number": num, "desc": desc})
    return rows, held, unread


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, held, unread = [], [], [], []
    key = lambda r: (r["number"], "".join(r["desc"].split()).casefold())
    for i, p in enumerate(d):
        text = p.get_text()
        ra, ha, ua = read_page(words_a(p), text)
        rb, hb, ub = read_page(words_b(pl.pages[i]), text)
        ka, kb = [key(r) for r in ra], [key(r) for r in rb]
        if sorted(ka) != sorted(kb):
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb][:4], "only_b": [r for r in rb if key(r) not in ka][:4]})
        keep += [(i + 1, r) for r in ra if key(r) in kb]
        held += [dict(x, page=i + 1) for x in ha]
        unread += [dict(x, page=i + 1) for x in ua]
    names = {}
    for pg, r in keep:
        names.setdefault(r["number"], set()).add("".join(r["desc"].split()).casefold())
    conflict = {n for n, v in names.items() if len(v) > 1}
    sections = {"0": "Distributor Parts Quick Reference, section Q (printed pp 552-567): Coleman-Mach air conditioner parts, "
                     "special-order (S/O) numbers"}
    lines, seen, per_page = [], set(), {}
    for pg, r in keep:
        if r["number"] in conflict or r["number"] in seen:
            continue
        seen.add(r["number"])
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{r['number']}|{r['desc'].replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "page_diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines),
           "conflicts": [{"number": n, "descs": sorted(names[n])} for n in sorted(conflict)], "held": held, "unread": unread}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "numbers": len(seen), "diffs": diffs[:3],
                      "conflicts": out["conflicts"][:6], "held": len(held), "held_sample": held[:8], "unread": len(unread),
                      "unread_sample": unread[:6]}, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
