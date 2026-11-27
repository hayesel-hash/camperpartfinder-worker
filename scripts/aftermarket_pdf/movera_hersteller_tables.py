"""Two-pass reader for the Movera "Caravan Workshop and Spare Parts Catalogue 2017-2018" (German; ChatGPT splits
"Movera - Caravan Workshop and Spare Parts Catalogue 2017-2018 - pp NNN-MMM.pdf").

Each page carries a 22 pt title "<MAKER>: <product group>" (e.g. "FIAMMA: Markisen Adapter", "THULE: ...", "TRUMA: ...") and
one or more tables "Pos. | Movera-Nr. | Hersteller-Nr. | Artikel-Bezeichnung" under exploded drawings; bold full-width rows
are sub-headings ("Fiamma Adapter für F45 (Fortsetzung)"). Larry's 27 Nov decision on distributor catalogues: the maker's number
printed under the maker's name is that maker's part; Movera-Nr. (Movera's stock number) is never a part. Rules:
- the maker is the page title before ":"; it is mapped only to a manufacturer of exactly that name (case-insensitive) in
  rv_private.manufacturers (passed in with --makers); other titles (SEITZ, CADAC, HYMER ...) are counted, not read;
- a row needs a 7-digit Movera-Nr. (or "auf Anfrage": Movera does not stock it, the maker's number is still printed) and a
  Hersteller-Nr. cell that is one token of part-number shape; "auf Anfrage", empty
  and spaced cells are counted as unread;
- description = Artikel-Bezeichnung (+ wrapped lines that hold only Artikel text) + " [<sub-heading>]" ("(Fortsetzung)"
  dropped) when a sub-heading is set;
- a number printed with two different descriptions is not loaded.
Pass A pymupdf dict lines, pass B pdfplumber words; cells by the header x positions of each table; only rows both passes give
identically are kept. Output: rows per maker.
usage: python3 -I movera_hersteller_tables.py <pdf> <out.json> --makers Fiamma,Thule,Truma,...
"""
import collections, hashlib, json, re, sys
import pdfplumber, pymupdf

NUM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./-]{1,39}$")
HDR = ("Pos.", "Movera-Nr.", "Hersteller-Nr.", "Artikel-Bezeichnung")


def sp(s):
    return " ".join((s or "").split())


def items_a(page):
    """(x0, top, x1, bottom, text, bold, size) per pymupdf span."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            if abs(l["dir"][0] - 1) > 0.01:  # rotated side labels ("Ersatzteil-Dienst", "MARKISEN")
                continue
            for s in l["spans"]:
                if s["text"].strip():
                    x0, y0, x1, y1 = s["bbox"]
                    out.append((x0, y0, x1, y1, s["text"].strip(), "Bold" in s["font"] or "Black" in s["font"], s["size"]))
    return out


def items_b(pl):
    out = []
    for w in pl.extract_words(extra_attrs=["fontname", "size", "upright"], keep_blank_chars=False):
        if not w["upright"]:
            continue
        out.append((w["x0"], w["top"], w["x1"], w["bottom"], w["text"], "Bold" in w["fontname"] or "Black" in w["fontname"], w["size"]))
    return out


def title_of(items):
    for x0, y0, x1, y1, t, b, s in sorted(items, key=lambda i: i[1]):
        if s >= 18 and y0 < 60 and ":" in t:
            return sp(t.split(":")[0])
    # pdfplumber splits the title into words: join the big words on the top line
    big = [i for i in items if i[6] >= 18 and i[1] < 60]
    if big:
        txt = sp(" ".join(i[4] for i in sorted(big, key=lambda i: i[0])))
        if ":" in txt:
            return sp(txt.split(":")[0])
    return None


def read(items):
    lines = []
    for it in sorted(items, key=lambda i: (round(i[3]), i[0])):
        if lines and abs(lines[-1][0] - it[3]) <= 2.0:
            lines[-1][1].append(it)
        else:
            lines.append([it[3], [it]])
    rows, unread = [], []
    groups = []  # header groups: (bottom, x positions)
    for b, its in lines:
        txt = [sp(i[4]) for i in sorted(its, key=lambda i: i[0])]
        joined = " ".join(txt)
        for m in re.finditer(r"Pos\. Movera-Nr\. Hersteller-Nr\. Artikel-Bezeichnung", joined):
            pass
        heads = [i for i in its if sp(i[4]) in HDR or sp(i[4]) in ("Pos.", "Movera-Nr.", "Hersteller-Nr.", "Artikel-Bezeichnung")]
        poss = sorted([i for i in heads if sp(i[4]) == "Pos."], key=lambda i: i[0])
        for k, p in enumerate(poss):
            xend = poss[k + 1][0] - 4 if k + 1 < len(poss) else 10_000
            def hx(name):
                c = [i for i in heads if sp(i[4]) == name and p[0] <= i[0] < xend]
                return c[0][0] if c else None
            mv, hn, ab = hx("Movera-Nr."), hx("Hersteller-Nr."), hx("Artikel-Bezeichnung")
            if mv and hn and ab:
                groups.append({"y": b, "pos": p[0], "mv": mv, "hn": hn, "ab": ab, "end": xend})
    for g in groups:
        sub, last_row, last_b = None, None, g["y"]
        for b, its in lines:
            if b <= g["y"] + 1:
                continue
            its = [i for i in its if g["pos"] - 6 <= i[0] < g["end"] and i[6] <= 9.6]  # table text is 8.5 pt; drawing labels 10-14 pt
            if not its:
                continue
            if b - last_b > 16:
                break
            if any(sp(i[4]) == "Pos." for i in its):
                break
            cells = {"pos": [], "mv": [], "hn": [], "ab": []}
            for i in sorted(its, key=lambda i: i[0]):
                k = "ab" if i[0] >= g["ab"] - 4 else "hn" if i[0] >= g["hn"] - 6 else "mv" if i[0] >= g["mv"] - 6 else "pos"
                cells[k].append(i)
            c = {k: sp(" ".join(i[4] for i in v)) for k, v in cells.items()}
            last_b = b
            first = min(its, key=lambda i: i[0])
            if all(i[5] for i in its) and not re.fullmatch(r"[0-9]{7}", c["mv"]) and first[0] < g["mv"] - 6 \
                    and not re.fullmatch(r"[0-9]{1,3}[a-z]?", c["pos"]):
                full = sp(" ".join(i[4] for i in sorted(its, key=lambda i: i[0])))
                sub = sp(re.sub(r"\(Fortsetzung\)", "", full)); last_row = None
                continue
            if not c["mv"] and not c["hn"] and not c["pos"] and c["ab"] and last_row is not None:
                last_row["desc_parts"].append(c["ab"]); continue
            if not re.fullmatch(r"[0-9]{7}", c["mv"]) and c["mv"].casefold() != "auf anfrage":
                if c["mv"] or c["hn"]:
                    unread.append({"cells": c})
                last_row = None
                continue
            hn = c["hn"]
            if not hn or " " in hn or not NUM.match(hn) or hn.endswith("-") or not c["ab"]:
                unread.append({"cells": c}); last_row = None
                continue
            last_row = {"number": hn, "desc_parts": [c["ab"]], "sub": sub}
            rows.append(last_row)
    out = []
    for r in rows:
        d = sp(" ".join(r["desc_parts"]))
        out.append({"number": r["number"], "desc": d + (f" [{r['sub']}]" if r["sub"] else "")})
    return out, unread


def main(pdf, outp, makers):
    mk = {m.upper(): m for m in makers}
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, other, unread_n = collections.defaultdict(list), [], collections.Counter(), 0
    key = lambda r: (r["number"], "".join(r["desc"].split()).casefold())
    for i, p in enumerate(d):
        ia = items_a(p); t = title_of(ia)
        if not t:
            continue
        if t.upper() not in mk:
            other[t] += 1; continue
        ra, ua = read(ia)
        rb, ub = read(items_b(pl.pages[i]))
        unread_n += len(ua)
        ka, kb = collections.Counter(key(r) for r in ra), collections.Counter(key(r) for r in rb)
        if ka != kb:
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb][:3], "only_b": [r for r in rb if key(r) not in ka][:3]})
        keep[mk[t.upper()]] += [(i + 1, r) for r in ra if key(r) in kb]
    res_unread = []
    res = {"doc": sha, "pages": d.page_count, "page_diffs": diffs, "other_titles": dict(other), "unread": unread_n, "makers": {}}
    for m, kr in keep.items():
        names = collections.defaultdict(set)
        for pg, r in kr:
            names[r["number"]].add("".join(r["desc"].split(" [")[0].split()).casefold())
        conflict = {n for n, v in names.items() if len(v) > 1}
        lines, seen, per = [], set(), {}
        for pg, r in kr:
            if r["number"] in conflict or r["number"] in seen:
                continue
            seen.add(r["number"]); per[pg] = per.get(pg, 0) + 1
            lines.append(f"{pg}|{per[pg]}|{r['number']}|{r['desc'].replace('|', '/')}|0")
        res["makers"][m] = {"rows": "\n".join(lines), "numbers": len(seen), "conflicts": sorted(conflict)}
    json.dump(res, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "diff_pages": len(diffs), "diffs": diffs[:2], "unread": unread_n,
                      "makers": {m: (v["numbers"], len(v["conflicts"])) for m, v in res["makers"].items()},
                      "other": other.most_common(8)}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    mk = sys.argv[sys.argv.index("--makers") + 1].split(",") if "--makers" in sys.argv else []
    main(sys.argv[1], sys.argv[2], mk)
