"""Two-pass reader for the Dexter "Trailer Parts & Accessories" catalogue V1-24 (dexterindex.com, Dexter's distribution
branches; ChatGPT splits "Dexter - Trailer Parts and Accessories Catalogue V1-24 - pp NNN-MMM.pdf").

Every table is "PART # | REF # | DESCRIPTION [| attribute columns]" under a 14 pt bold coloured heading. REF # is Dexter's
branch stock number (never a part). The catalogue is multi-brand: headings name GENUINE DEXTER, TRAILER PARTS PRO, ROCKWELL
AMERICAN, DEMCO, B&W ... or no maker at all ("REPLACEMENT COMPONENTS", "IDLER HUBS"). Rules:
- a table belongs to the nearest heading above it on the page (heading = 12.5-15 pt bold, not white) that overlaps it in x;
- only headings that start with "GENUINE DEXTER" or "DEXTER " are read as Dexter tables (maker named, never inferred); a heading
  that names two makers ("KODIAK AND DEXTER") or another maker first ("FORTRESS OIL CAP FOR DEXTER HUBS") is not Dexter;
- the other headings are counted per first word in "other_headings" (not loaded);
- description = DESCRIPTION cell + "<HEADER>: <value>" for attribute columns (DIAGRAM #, QTY and REF # dropped); the heading
  follows in brackets ("HUB-DRUM WITH STUDS AND RACES; FINISH: PAINTED [GENUINE DEXTER HUB-DRUM]");
- rows whose PART # cell is empty or not a part number shape (note rows "Brake assembly not included") are skipped.
Pass A pymupdf find_tables() cells; pass B pdfplumber words merged into cells by gaps and assigned to the nearest header
column centre, rows by baseline under the header row. Only rows both passes give identically are kept.
usage: python3 -I dexter_v124_tables.py <pdf> <out.json>
"""
import collections, hashlib, json, re, sys
import pdfplumber, pymupdf

NUM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./-]{1,39}$")
DROP_COLS = {"REF #", "DIAGRAM #", "QTY", "QTY.", "DIAGRAM"}


def sp(s):
    return " ".join((s or "").split())


def is_dexter(h):
    u = sp(h).upper()
    if " AND " in u.split("DEXTER", 1)[0] + " " or re.search(r"\bAND DEXTER\b|\bDEXTER AND\b", u):
        return False
    return u.startswith("GENUINE DEXTER") or u.startswith("DEXTER ")


def headings_a(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            s = l["spans"]; t = sp("".join(x["text"] for x in s))
            if t and 12.5 <= s[0]["size"] <= 15 and s[0]["color"] != 0xFFFFFF and "Bo" in s[0]["font"]:
                out.append((l["bbox"], t))
    return out


def headings_b(pl):
    lines = collections.defaultdict(list)
    for c in pl.chars:
        if 12.5 <= c["size"] <= 15 and "Bo" in c["fontname"] and c.get("non_stroking_color") not in ((1,), (1, 1, 1), [1], [1, 1, 1], (0, 0, 0, 0), [0, 0, 0, 0]):
            lines[(round(c["top"]), )].append(c)
    out = []
    for (top,), cs in lines.items():
        cs.sort(key=lambda c: c["x0"])
        txt, prev = "", None
        for c in cs:
            if prev is not None and c["x0"] - prev["x1"] > 1.5:
                txt += " "
            txt += c["text"]; prev = c
        out.append(((cs[0]["x0"], top, cs[-1]["x1"], max(c["bottom"] for c in cs)), sp(txt)))
    return out


def heading_for(heads, x0, x1, top):
    best = None
    for bb, t in heads:
        if bb[3] <= top + 1 and bb[0] < x1 and bb[2] > x0 - 30:
            if best is None or bb[3] > best[0][3]:
                best = (bb, t)
    return best[1] if best else None


def build(header, cells, heading):
    hdr = [sp(h).upper() for h in header]
    if len(hdr) < 3 or hdr[0] != "PART #" or hdr[1] != "REF #" or "DESCRIPTION" not in hdr or hdr.count("PART #") > 1:
        return None  # a second PART # column (left / right hand brake pairs) is not read
    num = sp(cells[0])
    if not NUM.match(num) or re.fullmatch(r"[0-9]{1,2}", num):
        return None
    di = hdr.index("DESCRIPTION")
    desc = sp(cells[di])
    if not desc:
        return None
    attrs = [f"{hdr[i]}: {sp(cells[i])}" for i in range(2, len(hdr))
             if i != di and hdr[i] not in DROP_COLS and sp(cells[i]) and sp(cells[i]) not in ("—", "–", "-", "N/A")]
    return {"number": num, "desc": "; ".join([desc] + attrs) + f" [{heading}]"}


def read_a(page):
    heads = headings_a(page); rows = []; tables = []
    for t in page.find_tables().tables:
        ex = [[c or "" for c in r] for r in t.extract()]
        inner = None
        if len(ex) > 1 and ex[0] and sp(ex[0][0]).upper() != "PART #" and sp(ex[1][0]).upper() == "PART #":
            inner = sp(" ".join(ex[0]))  # find_tables took the heading line in as a first row
            ex = ex[1:]
        if not ex or not ex[0] or sp(ex[0][0]).upper() != "PART #":
            continue
        if len(ex[0]) > 1 and sp(ex[0][1]).upper() == "REF # DESCRIPTION":  # merged column: split REF # off each cell
            fixed = [[ex[0][0], "REF #", "DESCRIPTION"] + ex[0][2:]]
            for r in ex[1:]:
                m = re.match(r"^\s*([0-9]{5,7})\s+(.*)$", r[1] or "", re.S)
                fixed.append([r[0], m.group(1), m.group(2)] + r[2:] if m else [r[0], "", r[1]] + r[2:])
            ex = fixed
        h = heading_for(heads, t.bbox[0], t.bbox[2], t.bbox[1] + (14 if inner else 0)) if not inner or any(inner == x for _, x in heads) else inner
        tables.append((round(t.bbox[1]), h))
        if not h or not is_dexter(h):
            continue
        for r in ex[1:]:
            b = build(ex[0], [c or "" for c in r] + [""] * (len(ex[0]) - len(r)), h)
            if b:
                rows.append(b)
    return rows, heads, tables


def read_b(pl):
    words = pl.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["size"])
    heads = headings_b(pl)
    lines = []
    for w in sorted(words, key=lambda w: (round(w["bottom"]), w["x0"])):
        if lines and abs(lines[-1][0] - w["bottom"]) <= 2.0:
            lines[-1][1].append(w)
        else:
            lines.append([w["bottom"], [w]])
    def cells_of(ws):
        ws = sorted(ws, key=lambda w: w["x0"]); out = []
        for w in ws:
            if out and w["x0"] - out[-1]["x1"] <= 6.0:
                out[-1]["text"] += " " + w["text"]; out[-1]["x1"] = w["x1"]
            else:
                out.append({"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"]})
        return out
    rows = []; i = 0
    while i < len(lines):
        cs = cells_of(lines[i][1])
        if not (cs and cs[0]["text"] == "PART #" and len(cs) > 1 and cs[1]["text"] == "REF #"):
            i += 1; continue
        header = [c["text"] for c in cs]; centres = [(c["x0"] + c["x1"]) / 2 for c in cs]
        x0, x1 = cs[0]["x0"], cs[-1]["x1"]
        h = heading_for(heads, x0, x1, cs[0]["top"])
        j = i + 1; last = lines[i][0]
        while j < len(lines):
            b, ws = lines[j]
            ws = [w for w in ws if w["x0"] >= x0 - 8 and w["x1"] <= x1 + 40]
            if not ws:
                if b - last > 14:
                    break
                j += 1; continue
            if b - last > 16 or any(w["size"] >= 12.5 for w in ws):
                break
            rc = cells_of(ws)
            if rc and rc[0]["text"] == "PART #":
                break
            vals = [""] * len(header)
            for c in rc:
                k = min(range(len(centres)), key=lambda q: abs(centres[q] - (c["x0"] + c["x1"]) / 2))
                if c["x0"] < cs[0]["x0"] + 20 and abs(c["x0"] - cs[0]["x0"]) < 4:
                    k = 0
                vals[k] = sp(vals[k] + " " + c["text"])
            if h and is_dexter(h):
                r = build(header, vals, h)
                if r:
                    rows.append(r)
            last = b; j += 1
        i = j
    return rows


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, other = [], [], collections.Counter()
    key = lambda r: (r["number"], "".join(r["desc"].split()).casefold())
    starred = []
    for i, p in enumerate(d):
        ra, heads, tables = read_a(p)
        star = set(re.findall(r"([A-Za-z0-9][A-Za-z0-9./-]+)\s?\*", p.get_text()))
        rb = [r for r in read_b(pl.pages[i]) if r["number"] not in star]
        starred += [{"page": i + 1, "number": r["number"]} for r in ra if r["number"].rstrip("*") in star or r["number"].endswith("*")]
        ra = [r for r in ra if r["number"] not in star and not r["number"].endswith("*")]
        for _, h in tables:
            if h and not is_dexter(h):
                other[h.split()[0] + (" " + h.split()[1] if h.split()[0] in ("GENUINE", "TRAILER", "ROCKWELL", "KODIAK") and len(h.split()) > 1 else "")] += 1
            elif not h:
                other["(no heading)"] += 1
        ka, kb = collections.Counter(key(r) for r in ra), collections.Counter(key(r) for r in rb)
        if ka != kb:
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb][:4], "only_b": [r for r in rb if key(r) not in ka][:4]})
        keep += [(i + 1, r) for r in ra if key(r) in kb]
    names = collections.defaultdict(set)
    for pg, r in keep:
        names[r["number"]].add("".join(r["desc"].split(" [")[0].split()).casefold())
    conflict = {n for n, v in names.items() if len(v) > 1}
    sections = {"0": "Dexter Trailer Parts & Accessories catalogue V1-24 (dexterindex.com), tables headed GENUINE DEXTER / DEXTER"}
    lines, seen, per_page = [], set(), {}
    for pg, r in keep:
        if r["number"] in conflict or r["number"] in seen:
            continue
        seen.add(r["number"])
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{r['number']}|{r['desc'].replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "page_diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines),
           "conflicts": [{"number": n, "descs": sorted(names[n])} for n in sorted(conflict)],
           "other_headings": dict(other.most_common()), "starred_held": starred}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "numbers": len(seen), "diff_pages": len(diffs), "diffs": diffs[:3],
                      "conflicts": out["conflicts"][:5], "starred": len(starred), "other": other.most_common(12)}, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
