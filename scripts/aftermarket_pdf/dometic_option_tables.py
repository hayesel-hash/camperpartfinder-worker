"""Two-pass reader for the "Customer Option" tables of Dometic (Duo-Therm, LaGrange) roof A/C PARTS LIST sheets
(e.g. 620315.421 form 3106797.024), which dometic_parts_list.py leaves unread:

  kind "component": a box headed "Component | Description" with the number first on each line
                    ("3106615.002  Box asm., complete").
  kind "columns":   a table headed "Description | Part No. | Part No." with one assembly number printed under each
                    "Part No." header (3106615.002 / 3106615.010) and an index column (C1, D2 ...); a number printed in
                    only one column is that assembly's part ("[for 3106615.010]").

Pass A pymupdf words, pass B pdfplumber words; both grouped by baseline (1.5 pt). A row is kept only when both
passes give the same (kind, description, number, qualifier). Every other Dometic-style number on the page is
reported as "unread".
usage: python3 -I dometic_option_tables.py <pdf> <out.json> "<label>" [first_n] [pages, e.g. 5,7]
"""
import hashlib, json, re, sys

NUM = re.compile(r"^\d{5,7}\.\d{3}$")
IDX = re.compile(r"^[A-Z]\d{1,2}$")


def norm(s):
    return " ".join(s.split())


def lines(words):
    out, cur = [], None
    for w in sorted(words, key=lambda w: (w[3], w[0])):
        if cur is None or w[3] - cur[0] > 1.5:
            cur = [w[3], []]; out.append(cur)
        cur[1].append(w)
    return [(y, sorted(l, key=lambda w: w[0])) for y, l in out]


def component_rows(L):
    rows = []
    for i, (y, ln) in enumerate(L):
        t = [w[4] for w in ln]
        if "Component" in t and "Description" in t:
            xc = next(w for w in ln if w[4] == "Component")[0]
            xd = next(w for w in ln if w[4] == "Description")[0]
            last = y
            for y2, ln2 in L[i + 1:]:
                if y2 - last > 16:
                    break
                band = [w for w in ln2 if xc - 6 <= w[0] < xd + 200]
                if not band:
                    continue  # a line of the neighbouring parts table only
                if not NUM.match(band[0][4]) or abs(band[0][0] - xc) > 6:
                    break
                desc = norm(" ".join(w[4] for w in band[1:] if w[0] >= xd - 6))
                if desc:
                    rows.append(("component", desc, band[0][4], ""))
                last = y2
    return rows


def column_rows(L):
    rows = []
    for i, (y, ln) in enumerate(L):
        pn = [w for w in ln if w[4] == "Part"]
        if len(pn) != 2 or not any(w[4] == "Description" for w in ln):
            continue
        xd = next(w for w in ln if w[4] == "Description")[0]
        if i + 1 >= len(L):
            continue
        sub = [w for w in L[i + 1][1] if NUM.match(w[4])]
        if len(sub) != 2:
            continue
        cols = [((w[0] + w[2]) / 2, w[4]) for w in sub]
        last = L[i + 1][0]
        for y2, ln2 in L[i + 2:]:
            if y2 - last > 22:
                break
            nums = [w for w in ln2 if NUM.match(w[4]) and w[0] > xd + 60]
            desc = norm(" ".join(w[4] for w in ln2 if xd - 60 <= w[0] < min((n[0] for n in nums), default=1e9)
                                 and not IDX.match(w[4]) and not NUM.match(w[4])))
            if not nums:
                if desc:
                    break
                continue
            last = y2
            got = {}
            for n in nums:
                k = min(range(2), key=lambda k: abs(cols[k][0] - (n[0] + n[2]) / 2))
                got[k] = n[4]
            vals = set(got.values())
            for v in vals:
                ks = [k for k in got if got[k] == v]
                q = "" if len(ks) == 2 else " [for " + cols[ks[0]][1] + "]"
                rows.append(("columns", desc, v, q))
    return rows


def read_words(words):
    L = lines(words)
    return component_rows(L) + column_rows(L)


def main(pdf, outp, label, first_n="201", pages=""):
    only = {int(x) for x in pages.split(",") if x}
    import pymupdf, pdfplumber
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    out, held, unread = [], [], []
    with pdfplumber.open(pdf) as pl:
        for pi, page in enumerate(doc):
            wa = [w[:5] for w in page.get_text("words")]
            wb = [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in pl.pages[pi].extract_words()]
            if only and pi + 1 not in only:
                continue
            a, b = read_words(wa), read_words(wb)
            bl = list(b)
            for r in a:
                if r in bl:
                    bl.remove(r); out.append((pi + 1, r))
                else:
                    held.append({"page": pi + 1, "a": list(r)})
            held += [{"page": pi + 1, "b": list(r)} for r in bl]
            got = {r[2] for r in a}
            unread += [{"page": pi + 1, "number": w[4]} for w in wa if NUM.match(w[4]) and w[4] not in got]
    seen, lines_out, conflicts, secs, n = {}, [], [], {}, int(first_n) - 1
    for pg, (kind, desc, num, q) in out:
        d = desc + q
        if num in seen:
            if seen[num] != d:
                conflicts.append({"number": num, "a": seen[num], "b": d})
            continue
        seen[num] = d
        code = secs.setdefault(label + " — Customer Options", str(len(secs)))
        n += 1
        lines_out.append(f"{pg}|{n}|{num}|{d.replace('|', '/')[:200]}|{code}")
    bad = {c["number"] for c in conflicts}
    lines_out = [l for l in lines_out if l.split("|")[2] not in bad]
    res = {"doc": sha, "pages": doc.page_count, "agree": bool(lines_out) and not held and not conflicts, "held": held,
           "conflicts": conflicts, "unread": unread, "numbers": len(lines_out),
           "sections": {c: s for s, c in secs.items()}, "rows": "\n".join(lines_out)}
    json.dump(res, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": res["agree"], "numbers": len(lines_out), "held": held[:10],
                      "conflicts": conflicts[:5], "unread": len(unread)}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:])
