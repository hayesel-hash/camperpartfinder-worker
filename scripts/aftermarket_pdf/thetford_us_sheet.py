"""Two-pass reader for Thetford North-America one-page toilet parts sheets (Aqua-Magic V / VI / Style II / Style Plus):
"Key No. | Part No. | Description" plus a "Not Shown | Part No. | Description" block; 5-digit numbers, "*" after a
number = "Limited Availability" (legend printed on the sheet).

Pass A: text-line order (a 5-digit number line opens a row; description lines follow until the next number, the next
key line or the Not Shown header). Pass B: word boxes; the number column and the description column come from the
"Part" and "Description" header words, wrapped description lines are attached to the number above.
A trailing "*" is removed from the number and " (limited availability)" added to the description. Rows the sheet
shades grey ("Not available" legend) are set in an italic font; a row whose number span is italic gets
" (not available)" (checked against the page images of all four first-use sheets).
Rows printed "Superseded by <new>" (C2, C402C/C403L, Campa Potti MT, Aria Deluxe) are not identity rows: they are
written to "supersessions" (old -> new, same maker) for the legacy-map v2 lane, named after the row the chain ends
on. "N/A" part-number cells anchor their row (so their description is not given to a neighbour) and are skipped.
Numbers with a "/" (e.g. T-PF.P03/B) cannot be stored by the supplied lane and are reported, not loaded.
usage: python3 -I thetford_us_sheet.py <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^(\d{5,8}|[A-Z]-[A-Z0-9]+\.[A-Z0-9]+(?:/[A-Z0-9]+)?)(\*?)$")
NA = "N/A"
KEY = re.compile(r"^\d{1,2}[a-zA-Z]?$")
SUP = re.compile(r"^Superseded(?: by)? (\S+?)\*?$", re.I)
END = re.compile(r"^(Not available|\*|Limited Availability|Revision .*|\d{1,2}/\d{1,2}/\d{4}|Parts List Continued)$", re.I)


def norm(num, star, desc):
    desc = " ".join(desc.split())
    return (num, desc + (" (limited availability)" if star else ""))


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, k, started = [], 0, False
    while k < len(L):
        t = L[k]
        if t.lower() == "description":
            started = True; k += 1; continue
        if not started:
            k += 1; continue
        m = NUM.match(t)
        if m:
            desc, j = [], k + 1
            while j < len(L):
                u = L[j]
                if NUM.match(u) or u == NA or u.lower() in ("not shown", "part no.", "description") or END.match(u):
                    break
                if KEY.match(u):  # key numbers and stray drawing callouts are never description text
                    break
                desc.append(u); j += 1
            rows.append(norm(m.group(1), m.group(2), " ".join(desc)))
            k = j; continue
        if t == NA:  # skip the N/A row and its description
            j = k + 1
            while j < len(L) and not (NUM.match(L[j]) or L[j] == NA or KEY.match(L[j]) or END.match(L[j])
                                      or L[j].lower() in ("not shown", "part no.", "description")):
                j += 1
            k = j; continue
        if END.match(t):
            started = False if t.lower() != "*" else started
        k += 1
    return rows


def pass_b(page):
    W = page.get_text("words")
    hp = [w for w in W if w[4].upper() == "PART"]
    hd = [w for w in W if w[4].upper() == "DESCRIPTION"]
    if not hp or not hd:
        return []
    xn0 = min(w[0] for w in hp) - 15
    ytop = min(w[1] for w in hd)
    # number cells are centred under the "Part No." header (numbers inside "Superseded by ..." text are not)
    cx = {}
    for w in hp:
        nxt = [v for v in W if abs(v[1] - w[1]) < 2 and 0 <= v[0] - w[2] < 8 and v[4].upper().startswith("NO")]
        cx[w[1]] = ((w[0] + (nxt[0][2] if nxt else w[2])) / 2)
    def under_header(w):
        hy = max((y for y in cx if y < w[1]), default=None)
        return hy is not None and abs((w[0] + w[2]) / 2 - cx[hy]) < 35
    numw = sorted([w for w in W if (NUM.match(w[4]) or w[4] == NA) and w[1] > ytop and under_header(w)], key=lambda w: w[1])
    if not numw:
        return []
    # descriptions start right of the number column (the "Description" header is centred over them); cells are
    # vertically centred, so each description word goes to the nearest number by vertical position
    xd0 = max(w[2] for w in numw) + 2
    hdr_y = [w[1] for w in hd]
    ys = [(w[1] + w[3]) / 2 for w in numw]
    desc = {i: [] for i in range(len(numw))}
    for x0, y0, x1, y1, w, *_ in W:
        if x0 < xd0 or y0 <= ytop + 2 or any(abs(y0 - h) < 3 for h in hdr_y):
            continue
        if END.match(w) or w in ("Not", "available"):
            continue
        yc = (y0 + y1) / 2
        i = min(range(len(ys)), key=lambda i: abs(ys[i] - yc))
        if abs(ys[i] - yc) < 13:
            desc[i].append((y0, x0, w))
    out = []
    for i, w in enumerate(numw):
        m = NUM.match(w[4])
        if not m:
            continue
        out.append(norm(m.group(1), m.group(2), lines_text(desc[i])))
    return out


def lines_text(ws):
    """join words line by line (a line = words whose tops are within 3 pt), left to right"""
    out, cur, cy = [], [], None
    for y, x, w in sorted(ws):
        if cy is not None and y - cy > 3:
            out.append(cur); cur = []
        if not cur:
            cy = y
        cur.append((x, w))
    if cur:
        out.append(cur)
    return " ".join(" ".join(w for x, w in sorted(line)) for line in out)


def italic_numbers(page):
    out = set()
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                m = NUM.match(sp["text"].strip())
                if m and (sp["flags"] & 2 or "Italic" in sp["font"]):
                    out.add(m.group(1))
    return out


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs = [], []
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        if sorted(a) != sorted(b):  # same rows; order may differ when a Not Shown block sits beside the table
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        na = italic_numbers(p)
        rows += [(i + 1, n, num, desc + (" (not available)" if num in na else ""))
                 for n, (num, desc) in enumerate([x for x in a if x in b], 1)]
    sup, ident = {}, []
    for pg, n, num, desc in rows:
        clean = desc.replace(" (not available)", "").replace(" (limited availability)", "")
        m = SUP.match(clean)
        if m:
            sup[num] = (m.group(1), pg, clean)
        else:
            ident.append((pg, n, num, desc))
    names = {num: desc for pg, n, num, desc in ident}
    supersessions = []
    for old, (new, pg, printed) in sup.items():
        tgt, hops = new, 0
        while tgt in sup and hops < 5:
            tgt, hops = sup[tgt][0], hops + 1
        supersessions.append({"page": pg, "legacy": old, "current": new, "printed": f"{old} | {printed}",
                              "storable": "/" not in old and "/" not in new,
                              "name": re.sub(r" \((not available|limited availability)\)", "", names.get(tgt, "")),
                              "chain_end": tgt})
    seen, lines, unstorable = set(), [], []
    for pg, n, num, desc in ident:
        if num in seen or not desc:
            continue
        if "/" in num:
            unstorable.append(num); continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines),
           "supersessions": supersessions, "unstorable": unstorable}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "supersessions": len(supersessions),
                      "unstorable": unstorable, "diffs": diffs[:2]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
