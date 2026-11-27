"""Two-pass reader for Dometic (Duo-Therm, LaGrange IN) PageMaker "Parts List" sheets for roof air
conditioners and heat pumps: Index | Description | Part No. / Part Number [| Model], Dometic numbers
such as 3102888.009 or 309513.015.

Pass A: plain text lines. An index line ("12", "A1") starts a row; following lines are its description
until a part-number line closes it. Lines after the number (qualifier notes, model letters) are ignored
until the next index line. Rows printing "See NOTE 1" instead of a number are skipped.
Pass B: word boxes. Columns from each header line (Index / Description / Part); a baseline with a
part number in the Part column is a row; its index and description come from the same baseline, or from
the baseline above when the number sits on a second line (description continued).
Only rows on which both passes give the same index, number and description are kept; the rest are
returned as held (two-column pages interleave in the text layer, so their right-hand rows are held).
A model column with a single value (e.g. "A = 3253.334C") is dropped; otherwise the model is kept.

usage: python3 -I dometic_parts_list.py <pdf> <out.json> "<section label>"
"""
import hashlib, json, re, sys

PN = re.compile(r"^\d{6,7}\.\d{3}$")
IDX = re.compile(r"^(\d{1,3}|[A-Z]\d{1,2})$")


def norm(s):
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("–", "-")
    s = re.sub(r"\s+,", ",", " ".join(s.split()))
    return s.replace("( ", "(").replace(",,", ",")


def headers(words):
    by = {}
    for w in words:
        by.setdefault(round(w[3]), []).append(w)
    hs = []
    for y, ws in sorted(by.items()):
        ws = sorted(ws)
        for k, w in enumerate(ws):
            if w[4] != "Description":
                continue
            idx = [v for v in ws[:k] if v[4].lstrip("I").startswith("ndex") or v[4] == "Index"]
            part = [v for v in ws[k + 1:] if v[4] == "Part"]
            if not idx or not part:
                continue
            model = [v for v in ws[k + 1:] if v[4] == "Model" and v[0] > part[0][0]]
            hs.append({"y": y, "index": idx[-1][0] - 12, "desc": w[0] - 8, "part": part[0][0] - 20,
                       "model": model[0][0] - 15 if model else None})
    hs.sort(key=lambda h: (h["y"], h["index"]))
    for h in hs:
        right = [g["index"] for g in hs if g is not h and abs(g["y"] - h["y"]) < 4 and g["index"] > h["index"]]
        # the group ends at the next header to the right, or just past the part-number column (notes printed to the
        # right of the number and header-less boxes beside the table are not part of the row)
        h["right"] = min(right + [h["part"] + 95 if h["model"] is None else h["model"] + 60])
    return hs


def pass_b(words, h):
    by = {}
    for w in words:
        if w[3] > h["y"] + 2 and h["index"] <= w[0] < h["right"]:
            by.setdefault(round(w[3]), []).append(w)
    lines = [(y, sorted(by[y])) for y in sorted(by)]
    rows, prev = [], None
    for y, ws in lines:
        num = [w[4] for w in ws if h["part"] <= w[0] < h["part"] + 80 and PN.match(w[4])]
        iw = [ws[0]] if ws[0][0] < h["desc"] and IDX.match(ws[0][4]) else []
        idx = [w[4] for w in iw]
        # descriptions may start left of the centred "Description" header: every word between the index and the
        # part-number column belongs to the description
        desc = [w[4] for w in ws if w not in iw and w[0] < h["part"]]
        model = [w[4] for w in ws if h["model"] is not None and w[0] >= h["model"]]
        if num:
            if idx:
                rows.append((idx[0], num[0], norm(" ".join(desc)), " ".join(model)))
            elif prev and y - prev[0] < 14:
                rows.append((prev[1], num[0], norm(prev[2] + " " + " ".join(desc)), " ".join(model)))
            prev = None
        elif idx:
            prev = (y, idx[0], " ".join(desc))
        else:
            prev = None
    return rows


def pass_a(text):
    L = [l.strip() for l in text.splitlines() if l.strip()]
    rows, cur = [], None
    for l in L:
        if IDX.match(l):
            cur = (l, [])
            continue
        if cur is None:
            continue
        if PN.match(l):
            rows.append((cur[0], l, norm(" ".join(cur[1]))))
            cur = None
            continue
        cur[1].append(l)
    return rows


def read(pages):
    """pages: [(text, words)] -> kept [(page, n, index, number, description, model)], held, diffs"""
    kept, held, diffs = [], [], []
    for i, (text, words) in enumerate(pages):
        hs = headers(words)
        if not hs:
            continue
        a = set(pass_a(text))
        b = [r for h in hs for r in pass_b(words, h)]
        ok = [r for r in b if r[:3] in a]
        bad = [r for r in b if r[:3] not in a]
        if bad:
            diffs.append({"page": i + 1, "held": [list(r[:3]) for r in bad][:10]})
        for k, r in enumerate(ok):
            kept.append((i + 1, k + 1) + r)
        held += [(i + 1,) + r for r in bad]
        # part numbers printed on the page but not in any row read by pass B (header-less columns, two-line rows
        # interrupted by a neighbouring column): reported, never loaded
        got = {r[1] for r in b}
        for w in words:
            if PN.match(w[4]) and w[4] not in got:
                held.append((i + 1, "unread", w[4], "", ""))
    return kept, held, diffs


def describe(rows):
    models = {r[5] for r in rows}
    out = []
    for pg, n, idx, num, desc, model in rows:
        d = desc if len(models) <= 1 or not model else f"{desc} - model {model}"
        out.append((pg, n, num, d))
    return out


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    d = pymupdf.open(pdf)
    kept, held, diffs = read([(p.get_text(), p.get_text("words")) for p in d])
    seen, lines = set(), []
    for pg, n, num, desc in describe(kept):
        if num in seen:
            continue
        seen.add(num)
        lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')[:200]}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "rows_total": len(kept), "numbers": len(seen),
           "held_rows": [list(h) for h in held], "diffs": diffs, "sections": {"0": label}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "rows": len(kept), "numbers": len(seen), "held": len(held),
                      "diffs": diffs[:4]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
