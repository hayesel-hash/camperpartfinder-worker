"""Two-pass reader for the Grassroutes Leisure trade catalogue (UK campervan-conversion parts distributor, 148 pp, ChatGPT
splits pp 001-037 / 038-074 / 075-148): product tiles whose BOLD BLACK heading is "<MAKER> <maker's number>" (e.g.
"WHALE GP1352"), followed by regular black description lines in the same column and a BOLD GREEN Grassroutes code
(30017). Larry's 27 Nov decision on distributor catalogues: a maker's number printed under that maker's name with a
description is that maker's part (supplied lane, source kind distributor_catalogue); the green Grassroutes code is the
distributor's stock number and is never a part.

Rules:
- the heading must be one line: the maker word given on the command line (as printed, upper case) + ONE number token
  (letters then a digit: GP1352, EP1622, RT2010); headings with more words ("COMET GEO INLINE") are not maker numbers;
- the description is every regular black line whose left edge is within 4 pt of the heading's left edge, from the heading
  down to the first bold line (green code or the next heading) in that column, each line at most `pitch` pt (bottom to
  bottom) below the previous one;
- a tile with no description, or with two or more green codes carrying different variant labels (one maker number over
  "12 V" / "24 V" stock codes), is held; a number printed with two different descriptions is not loaded;
- the page title (17 pt line at the top left) is the section label.
Pass A pymupdf spans (font name, colour), pass B pdfplumber chars grouped into lines; only rows both passes give
identically (number + description) are kept.
Options (CAN sink / hob tiles, split pp 038-074): --name-words lets the heading carry product words after the number
("CAN LA1405 RECTANGULAR SINK", "CAN FL1323GP - SINGLE HOB/SINK COMBINATION"; the words become "RECTANGULAR SINK: <description>");
--pitch=N is the largest bottom-to-bottom distance between description lines (default 20; CAN paragraph breaks are
20-21 pt); --code-pitch=N the largest one from the description to the first green code (default 52). Headings joining two numbers ("CAN FL1323/FL1324") are not read.
usage: python3 -I grassroutes_maker_tiles.py <pdf> <MAKER> <out.json> [--name-words] [--pitch=N] [--code-pitch=N]
"""
import hashlib, json, re, sys
import pdfplumber, pymupdf

NUMTOK = re.compile(r"^[A-Z]{1,4}\d[A-Z0-9-]{1,14}$")


def sp(s):
    return " ".join(s.split())


def lines_a(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            spans = [s for s in l["spans"] if s["text"].strip()]
            if not spans:
                continue
            s0 = spans[0]
            green = s0["color"] != 0
            out.append({"x": round(s0["bbox"][0], 1), "top": round(min(s["bbox"][1] for s in spans), 1),
                        "bottom": round(max(s["bbox"][3] for s in spans), 1), "bold": "Bold" in s0["font"],
                        "green": green, "size": round(s0["size"], 1), "text": sp("".join(s["text"] for s in spans))})
    return out


def lines_b(ppage):
    chars = [c for c in ppage.chars if c["text"].strip() or c["text"] == " "]
    groups = []
    for c in sorted(chars, key=lambda c: (round(c["top"]), c["x0"])):
        col = tuple(round(v, 2) for v in (c["non_stroking_color"] or (0,)))
        bold = "Bold" in c["fontname"]
        key = (bold, col, round(c["size"], 1))
        for g in groups:
            if g["key"] == key and abs(g["top"] - c["top"]) < 2 and -1.5 < c["x0"] - g["x1"] < 6:
                g["chars"].append(c); g["x1"] = c["x1"]; break
        else:
            groups.append({"key": key, "top": c["top"], "x1": c["x1"], "chars": [c]})
    out = []
    for g in groups:
        txt = "".join(c["text"] for c in g["chars"])
        if not txt.strip():
            continue
        cs = [c for c in g["chars"] if c["text"].strip()]
        bold, col, size = g["key"]
        green = any(v > 0.1 for v in col)
        out.append({"x": round(cs[0]["x0"], 1), "top": round(min(c["top"] for c in cs), 1),
                    "bottom": round(max(c["bottom"] for c in cs), 1), "bold": bold, "green": green, "size": size,
                    "text": sp(txt)})
    return out


def title(lines):
    t = [l for l in lines if l["size"] >= 15 and l["top"] < 70 and l["x"] < 120]
    return sp(t[0]["text"].replace("\x08", "")) if t else ""


def read_page(lines, maker, name_words=False, pitch=20, code_pitch=52):
    rows, held = [], []
    if name_words:
        pat = re.compile(r"^" + re.escape(maker) + r" (\S+)(?: -)?(?: ([A-Z][A-Z0-9 /&'.-]*))?$")
    else:
        pat = re.compile(r"^" + re.escape(maker) + r" (\S+)$")
    for h in lines:
        if not h["bold"] or h["green"]:
            continue
        m = pat.match(h["text"])
        if not m or not NUMTOK.match(m.group(1)):
            continue
        num = m.group(1)
        head = sp(m.group(2) or "") if name_words else ""
        col = sorted([l for l in lines if abs(l["x"] - h["x"]) <= 4 and l["top"] > h["top"] + 2], key=lambda l: l["top"])
        desc, codes, y, k = [], [], h["bottom"], 0
        # gaps are measured bottom to bottom (pymupdf line boxes and pdfplumber glyph boxes differ by ~3 pt at the top)
        # description: regular black lines right under the heading, each at most `pitch` pt below the previous one
        while k < len(col) and not col[k]["bold"] and col[k]["bottom"] - y <= pitch:
            desc.append(col[k]["text"]); y = col[k]["bottom"]; k += 1
        # stock codes: green bold lines at most `code_pitch` pt below the description, stacked within 32 pt
        while k < len(col) and col[k]["bold"] and col[k]["green"] and col[k]["bottom"] - y <= (code_pitch if not codes else 32):
            codes.append(col[k]); y = col[k]["bottom"]; k += 1
        # variant labels printed to the right of each green code on the same baseline
        labels = set()
        for c in codes:
            lab = [l["text"] for l in lines if not l["bold"] and abs(l["top"] - c["top"]) < 2.5 and 0 < l["x"] - c["x"] < 80]
            labels.add(" ".join(lab))
        text = sp(" ".join(desc))
        if text and head:
            text = head + ": " + text
        if not text:
            held.append({"number": num, "why": "no description under the heading"}); continue
        if len(codes) > 1 and len(labels) > 1:
            held.append({"number": num, "why": "one maker number over several stock codes with variant labels", "labels": sorted(labels)})
            continue
        if not codes:
            held.append({"number": num, "why": "no Grassroutes code closes the tile", "desc": text}); continue
        rows.append({"number": num, "desc": text})
    return rows, held


def main(pdf, maker, outp, name_words=False, pitch=20, code_pitch=52):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, held, titles = [], [], [], {}
    key = lambda r: (r["number"], "".join(r["desc"].split()).casefold())
    for i, p in enumerate(d):
        la, lb = lines_a(p), lines_b(pl.pages[i])
        ra, ha = read_page(la, maker, name_words, pitch, code_pitch)
        rb, hb = read_page(lb, maker, name_words, pitch, code_pitch)
        ka, kb = [key(r) for r in ra], [key(r) for r in rb]
        if sorted(ka) != sorted(kb):
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb], "only_b": [r for r in rb if key(r) not in ka]})
        tt = title(la)
        for r in ra:
            if key(r) in kb:
                keep.append((i + 1, r, tt))
        held += [dict(x, page=i + 1) for x in ha]
    names = {}
    for pg, r, _ in keep:
        names.setdefault(r["number"], set()).add("".join(r["desc"].split()).casefold())
    conflict = {n for n, v in names.items() if len(v) > 1}
    quals = sorted({t for _, _, t in keep})
    sections = {str(k): f"Grassroutes Leisure trade catalogue (distributor print): {q}" for k, q in enumerate(quals)}
    lines, seen, per_page = [], set(), {}
    for pg, r, t in keep:
        if r["number"] in conflict or r["number"] in seen:
            continue
        seen.add(r["number"])
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{r['number']}|{r['desc'].replace('|', '/')}|{quals.index(t)}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines) and not diffs, "page_diffs": diffs,
           "rows_total": len(keep), "numbers": len(seen), "sections": sections, "rows": "\n".join(lines),
           "conflicts": [{"number": n, "descs": sorted(names[n])} for n in sorted(conflict)], "held": held}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "numbers": len(seen), "pages_with_diffs": len(diffs),
                      "diffs": diffs[:4], "conflicts": out["conflicts"], "held": held, "rows_text": out["rows"]},
                     ensure_ascii=False)[:6000])


if __name__ == "__main__":
    a = sys.argv[1:]
    opts = dict(x.split("=", 1) for x in a[3:] if "=" in x)
    main(a[0], a[1], a[2], name_words="--name-words" in a, pitch=float(opts.get("--pitch", 20)),
         code_pitch=float(opts.get("--code-pitch", 52)))
