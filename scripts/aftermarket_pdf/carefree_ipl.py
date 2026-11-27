"""Two-pass reader for Carefree of Colorado "Illustrated Parts List" tables
(Item | Part Number | Description | Notes [| note refs]).

Pass A: text-line cells from get_text("dict") (each line bbox -> column by header x).
Pass B: word boxes from get_text("words") grouped by baseline, columns by header x.
Rows start at a part number in the Part Number column; a line with only description text
continues the row above. Order templates (lower-case placeholders such as "3nn", "xx", or
"XX"/"XXX" colour codes: R00415-3nn-XX, 19xx00, R001086XXX) are not orderable numbers and
are skipped and counted. Note references in the last column ("1,3") are dropped.

usage: python3 -I carefree_ipl.py <pdf> <out.json> "<label>"
"""
import hashlib, json, re, sys

NUM = re.compile(r"^(?=.*\d)[A-Za-z0-9][A-Za-z0-9-]{3,}$")
REFS = re.compile(r"^\d+(,\d+)*$")


def is_template(n):
    return bool(re.search(r"[a-z]", n) or "XX" in n)


def header(words):
    """-> dict of column x0 for item, number, desc, notes, and header baseline; or None"""
    by = {}
    for w in words:
        by.setdefault(round(w[3]), []).append(w)
    for y, ws in sorted(by.items()):
        t = {w[4]: w[0] for w in ws}
        if "Part" in t and "Number" in t and "Description" in t and "Notes" in t:
            return {"item": t.get("Item", t["Part"] - 45), "number": t["Part"] - 15, "desc_start": t["Part"] + 60,
                    "notes": t["Notes"] - 60, "refs": t["Notes"] + 5, "y": y}
    return None


def build(cells, h):
    """cells: list of (y_baseline, x0, text) below the header. -> [(number, description)], templates"""
    lines = []
    for y, x, t in sorted(cells):
        if lines and abs(y - lines[-1][0]) <= 2:
            lines[-1][1].append((x, t))
        else:
            lines.append([y, [(x, t)]])
    rows, templates, last, lasty = [], 0, None, None
    for y, cs in lines:
        cs.sort()
        text = " ".join(t for _, t in cs)
        if text.startswith("Notes:") or text.startswith("Notes "):
            break
        if "following items" in text.lower():
            last = None
            continue
        cs = [(x, t) for x, t in cs if not (x >= h["refs"] and REFS.match(t))]
        num = [t for x, t in cs if h["number"] <= x < h["desc_start"] - 20]
        desc = [t for x, t in cs if h["desc_start"] - 20 <= x < h["notes"]]
        notes = [t for x, t in cs if x >= h["notes"]]
        item = [t for x, t in cs if x < h["number"]]
        if num:
            n = num[0].split()[0]
            if not NUM.match(n):
                last = None
                continue
            if is_template(n):
                templates += 1; last = None
                continue
            d = " ".join(desc)
            if notes:
                d += " — " + " ".join(notes)
            rows.append([n, d]); last, lasty = rows[-1], y
            continue
        if item:
            last = None
            continue
        if last is not None and desc and y - lasty < 16:
            base, _, nt = last[1].partition(" — ")
            last[1] = base + " " + " ".join(desc) + ((" — " + nt) if nt else "")
            if notes:
                last[1] += (" " if nt else " — ") + " ".join(notes)
            lasty = y
    return [(n, " ".join(d.split())) for n, d in rows], templates


def pass_a(dict_lines, h):
    cells = []
    for (x0, y0, x1, y1), text in dict_lines:
        if y1 <= h["y"] + 2 or not text.strip():
            continue
        # a dict line may hold several cells separated by wide gaps: keep as one cell at its x0
        cells.append((round(y1), x0, text.strip()))
    return build(cells, h)


def pass_b(words, h):
    """words on one baseline are merged into a cell while the gap to the next word is <= 8 pt"""
    by = {}
    for w in words:
        if w[3] > h["y"] + 2:
            by.setdefault(round(w[3]), []).append(w)
    cells = []
    for y, ws in by.items():
        ws.sort(key=lambda w: w[0])
        cur, x0, x1 = [], None, None
        for w in ws:
            if cur and w[0] - x1 > 8:
                cells.append((y, x0, " ".join(cur))); cur = []
            if not cur:
                x0 = w[0]
            cur.append(w[4]); x1 = w[2]
        if cur:
            cells.append((y, x0, " ".join(cur)))
    return build(cells, h)


def page_inputs(p):
    dl = []
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            # split a line into cells where spans are far apart
            cur, cx0, cy1, prev_x1 = [], None, None, None
            for s in l["spans"]:
                if not s["text"].strip():
                    continue
                if cur and s["bbox"][0] - prev_x1 > 12:
                    dl.append(((cx0, 0, prev_x1, cy1), "".join(cur)))
                    cur = []
                if not cur:
                    cx0 = s["bbox"][0]
                cur.append(s["text"]); prev_x1 = s["bbox"][2]; cy1 = s["bbox"][3]
            if cur:
                dl.append(((cx0, 0, prev_x1, cy1), "".join(cur)))
    return dl, p.get_text("words")


def read(pages):
    rows, diffs, templates = [], [], 0
    for i, (dl, words) in enumerate(pages):
        h = header(words)
        if not h:
            continue
        a, ta = pass_a(dl, h)
        b, tb = pass_b(words, h)
        if a != b or ta != tb:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:8], "only_b": [x for x in b if x not in a][:8],
                          "templates": [ta, tb]})
        templates += tb
        for k, (n, d) in enumerate(b):
            rows.append((i + 1, k + 1, n, d))
    return rows, diffs, templates


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, templates = read([page_inputs(p) for p in d])
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')[:200]}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "templates_skipped": templates, "sections": {"0": label}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "templates": templates, "diffs": diffs[:3]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
