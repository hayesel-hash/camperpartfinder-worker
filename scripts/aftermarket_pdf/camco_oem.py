"""Two-pass reader for the Camco "OEM Products / Quality Parts for RV Manufacturing" catalogue (2023).

Layout: each product has a 13 pt heading, then a table whose header row is white text on a coloured
fill ("PART #" | attribute columns | "QTY"), then one row per Camco number (10 pt). A few tables put the
heading under the header row (e.g. the grab handles). QTY is the OEM pack quantity and is not kept.

Pass A: plain text lines in reading order. "PART #" opens a table; the upper-case lines after it are the
column labels; a Title-case line before the first number is the heading (else the line before "PART #").
A row is a number line plus the value lines up to the next number / table / heading / note line; a final
integer is the QTY.
Pass B: dict spans with font size, colour and position: header row = white spans on the "PART #" baseline
inside that table's x-range; heading = nearest 13 pt dark line just above the header row (or just below it);
rows = dark 10 pt lines whose cell in the PART # column is a number; cells by header column; continuation
lines (no number) join the cell above.

Only rows on which both passes give the same number, heading and attribute text are kept; the rest are
reported as held. Output: supplied-documents JSON (rows page|n|number|description|section).
usage: python3 -I camco_oem.py <pdf> <out.json> [first printed page]
"""
import hashlib, json, re, sys

NUM = re.compile(r"^[A-Z]?\d{5,7}$")
PARTH = re.compile(r"^PART ?#$")
NOTE = re.compile(r"^(QAI|CSA|NSF|TEI|UL|IAPMO)\b.*(Certified|Listed)|^Replacement .* part number|^\*")
WHITE = 16777215


def norm(s):
    return " ".join(s.replace("’", "'").replace("”", '"').replace("“", '"').split())


def is_label(l):
    return bool(l) and l == l.upper() and not NUM.match(l) and any(c.isalpha() for c in l)


def is_int(l):
    return re.fullmatch(r"\d{1,4}", l) is not None


# ---------- pass A: text lines ----------
def pass_a(text):
    L = [norm(l) for l in text.splitlines()]
    L = [l for l in L if l]
    rows, k = [], 0
    while k < len(L):
        if not PARTH.match(L[k]):
            k += 1
            continue
        head = L[k - 1] if k > 0 else ""
        j = k + 1
        while j < len(L) and is_label(L[j]) and not PARTH.match(L[j]):
            j += 1
        if j < len(L) and not NUM.match(L[j]) and not PARTH.match(L[j]) and j + 1 < len(L) and NUM.match(L[j + 1]):
            head = L[j]
            j += 1
        while j < len(L) and NUM.match(L[j]):
            num, vals, j = L[j], [], j + 1
            while j < len(L) and not NUM.match(L[j]) and not PARTH.match(L[j]) and not NOTE.search(L[j]):
                if j + 1 < len(L) and PARTH.match(L[j + 1]):
                    break  # heading of the next table
                if is_int(L[j]) and vals:
                    j += 1  # QTY closes the row
                    break
                vals.append(L[j])
                j += 1
            rows.append((num, head, norm(" ".join(vals))))
        k = j if j > k else k + 1
    return rows


# ---------- pass B: dict spans ----------
def lines_of(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if s["text"].strip()]
            if not sp:
                continue
            out.append({"x0": l["bbox"][0], "y0": l["bbox"][1], "x1": l["bbox"][2], "y1": l["bbox"][3],
                        "size": round(sp[0]["size"]), "white": sp[0]["color"] == WHITE,
                        "text": norm(" ".join(s["text"] for s in sp))})
    return out


def pass_b(L, W):
    """L: lines_of(page); W: page width."""
    heads = sorted([l for l in L if l["white"] and PARTH.match(l["text"])], key=lambda l: (round(l["y0"]), l["x0"]))
    rows = []
    for h in heads:
        y = h["y0"]
        same = sorted([l for l in heads if abs(l["y0"] - y) < 4], key=lambda l: l["x0"])
        nxt = [l["x0"] for l in same if l["x0"] > h["x0"] + 5]
        x0, x1 = h["x0"] - 12, (nxt[0] - 12 if nxt else W)
        cols = sorted([l for l in L if l["white"] and abs(l["y0"] - y) < 12 and x0 <= l["x0"] < x1], key=lambda l: l["x0"])
        # merge two-line labels into one column (same x start)
        starts = []
        for c in cols:
            if not starts or c["x0"] - starts[-1] > 8:
                starts.append(c["x0"])
        hdr_bottom = max(c["y1"] for c in cols)
        labels, centres = [], []
        for s in starts:
            grp = [c for c in cols if abs(c["x0"] - s) <= 8]
            labels.append(" ".join(c["text"] for c in grp))
            centres.append(sum((c["x0"] + c["x1"]) / 2 for c in grp) / len(grp))
        qty_col = len(starts) - 1 if labels and labels[-1] == "QTY" else None
        above = [l for l in L if l["size"] >= 12 and not l["white"] and l["y1"] <= y + 1 and l["y1"] > y - 40
                 and x0 - 25 <= l["x0"] < x1]
        below = [l for l in L if l["size"] >= 12 and not l["white"] and hdr_bottom - 1 <= l["y0"] < hdr_bottom + 20
                 and x0 - 25 <= l["x0"] < x1]
        head = ""
        if below:
            head = sorted(below, key=lambda l: (round(l["y0"] / 4), abs(l["x0"] - h["x0"])))[0]["text"]
        elif above:
            top = sorted(above, key=lambda l: (round(l["y1"] / 4), -abs(l["x0"] - h["x0"])))
            last = top[-1]
            group = [l for l in top if last["y1"] - l["y1"] < 30 and abs(l["x0"] - last["x0"]) < 6]
            head = " ".join(l["text"] for l in group)
        body = sorted([l for l in L if not l["white"] and l["size"] <= 11 and l["y0"] >= hdr_bottom - 1
                       and x0 <= l["x0"] < x1], key=lambda l: (round(l["y0"]), l["x0"]))
        cur, last_y = None, hdr_bottom
        for l in body:
            if l["y0"] - last_y > (22 if cur else 40):
                break
            mid = (l["x0"] + l["x1"]) / 2
            ci = min(range(len(centres)), key=lambda i: abs(centres[i] - mid))
            if ci != 0 and NUM.match(l["text"]) and abs(l["x0"] - starts[0]) < 15:
                ci = 0
            if ci == 0:
                if not NUM.match(l["text"]):
                    break
                cur = {"num": l["text"], "y": l["y0"], "cells": {}}
                rows.append(cur)
                last_y = l["y0"]
                continue
            if cur is None:
                continue
            if abs(l["y0"] - cur["y"]) > 3 and l["y0"] - last_y > 16:
                break
            cur["cells"].setdefault(ci, []).append(l["text"])
            last_y = max(last_y, l["y0"])
        for r in rows:
            if "head" not in r:
                r["head"] = head
                r["qty_col"] = qty_col
    out = []
    for r in rows:
        vals = [" ".join(r["cells"][i]) for i in sorted(r["cells"]) if i != r["qty_col"]]
        out.append((r["num"], r["head"], norm(" ".join(vals)), vals))
    return out


def section_of(L):
    top = [l for l in L if l["y1"] < 55 and not re.fullmatch(r"\d+", l["text"])]
    return top[0]["text"] if top else ""


def page_input(page):
    return page.get_text(), lines_of(page), page.rect.width


def read(pages):
    """pages: list of (text, lines, width) from page_input(). -> rows [(page, n, number, desc, section)], held"""
    rows, held = [], []
    for i, (text, L, W) in enumerate(pages):
        A = pass_a(text)
        B = pass_b(L, W)
        sec = section_of(L)
        a_set = {(n, h, v) for n, h, v in A}
        k = 0
        for n, h, v, cells in B:
            if (n, h, v) in a_set and h:
                k += 1
                desc = h + (" — " + " / ".join(cells) if cells else "")
                rows.append((i + 1, k, n, desc, sec))
            else:
                held.append({"page": i + 1, "number": n, "b": [h, v], "a": [x for x in A if x[0] == n]})
        b_nums = {x[0] for x in B}
        for n, h, v in A:
            if n not in b_nums:
                held.append({"page": i + 1, "number": n, "a_only": [h, v]})
    return rows, held


def main(pdf, outp, first_page=1):
    import pymupdf
    doc = pymupdf.open(pdf)
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    rows, held = read([page_input(p) for p in doc])
    secs, lines, seen = {}, [], set()
    for pg, n, num, desc, sec in rows:
        code = secs.setdefault(sec or "Camco OEM products", str(len(secs) + 1))
        lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{code}")
        seen.add(num)
    out = {"doc": sha, "pages": doc.page_count, "agree": bool(lines), "held": held, "rows_total": len(rows),
           "numbers": len(seen), "sections": {v: f"Camco OEM catalogue 2023 — {k}" for k, v in secs.items()},
           "first_printed_page": first_page, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "rows": len(rows), "numbers": len(seen), "held": len(held)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1)
