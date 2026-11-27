"""Two-pass reader for Coleman-Mach (Airxcel RV Products Division) "REPAIR PARTS LIST" sheets
(R-6xx style: NO. | USED ON MODELS / CODE | PART NUMBER | DESCRIPTION | NO. REQ.).

Pass A: plain text lines. A part-number line takes the next line as its description; the nearest
line above it (after the item marker) is the used-on cell when it looks like a model code
("All", "876", "47224/47234"); a row with no used-on cell of its own (a second number under the
same item) keeps the cell printed on its line only, so it is read from the text line before it.
Pass B: word boxes grouped by baseline; columns from the header words MODELS / NUMBER /
DESCRIPTION / REQ. Only rows on which both passes give the same number, description and used-on
cell are kept. Reading stops at "ns = not shown" / "SPECIAL ORDER PARTS". Quantities are dropped.

usage: python3 -I coleman_mach_rpl.py <pdf> <out.json> "<section label>"
"""
import hashlib, json, re, sys

PN = re.compile(r"^\d{4,5}[A-Z]?-?\d{3,5}$|^\d{4,5}[A-Z]\d{3,5}$")
USED = re.compile(r"^(All|\d{3}(/\d{3})*|\d{5}(/\d{5})*)$")
ITEM = re.compile(r"^(\d{1,2}\.|ns)$")
STOP = re.compile(r"^(ns = not shown|SPECIAL ORDER PARTS)")


def norm(s):
    return " ".join(s.replace("–", "-").replace("’", "'").split())


def header(words):
    by = {}
    for w in words:
        by.setdefault(round(w[3]), []).append(w)
    for y, ws in sorted(by.items()):
        t = {w[4]: w[0] for w in ws}
        if "NUMBER" in t and "DESCRIPTION" in t and "MODELS" in t:
            req = [w[0] for w in ws if w[4].startswith("REQ")]
            return {"used": t["MODELS"] - 15, "number": t["NUMBER"] - 4, "desc": t["DESCRIPTION"] - 4,
                    "qty": (req[0] - 4) if req else 10_000, "y": y}
    return None


def pass_b(words, h):
    by = {}
    for w in words:
        if w[3] > h["y"] + 2:
            by.setdefault(round(w[3]), []).append(w)
    rows = []
    for y in sorted(by):
        ws = sorted(by[y])
        text = " ".join(w[4] for w in ws)
        if STOP.match(text):
            break
        num = [w[4] for w in ws if h["number"] <= w[0] < h["desc"]]
        if not num or not PN.match(num[0]):
            continue
        used = " ".join(w[4] for w in ws if h["used"] <= w[0] < h["number"] and not ITEM.match(w[4]))
        desc = norm(" ".join(w[4] for w in ws if h["desc"] <= w[0] < h["qty"]))
        rows.append((num[0], desc, used))
    return rows


def pass_a(text):
    L = [norm(l) for l in text.splitlines()]
    L = [l for l in L if l]
    rows, started = [], False
    for i, l in enumerate(L):
        if l == "DESCRIPTION":
            started = True
            continue
        if not started:
            continue
        if STOP.match(l):
            break
        if not PN.match(l) or i + 1 >= len(L):
            continue
        prev = L[i - 1]
        # "9. 47224/47234" or "ns 47214/47234": item marker and used-on cell share one text line
        parts = prev.split()
        if parts and ITEM.match(parts[0]):
            parts = parts[1:]
        used = " ".join(parts) if parts and USED.match(" ".join(parts)) else ""
        rows.append((l, L[i + 1], used))
    return rows


def read(pages):
    """pages: [(text, words)] -> rows [(page, n, number, description, used)], diffs"""
    rows, diffs = [], []
    for i, (text, words) in enumerate(pages):
        h = header(words)
        if not h:
            continue
        a, b = pass_a(text), pass_b(words, h)
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:8],
                          "only_b": [x for x in b if x not in a][:8]})
            keep = [x for x in b if x in a]
        else:
            keep = b
        for k, (n, d, u) in enumerate(keep):
            rows.append((i + 1, k + 1, n, d, u))
    return rows, diffs


def describe(desc, used):
    return desc if used in ("", "All") else f"{desc} - used on {used}"


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs = read([(p.get_text(), p.get_text("words")) for p in d])
    seen, lines = set(), []
    for pg, n, num, desc, used in rows:
        if num in seen:
            continue
        seen.add(num)
        lines.append(f"{pg}|{n}|{num}|{describe(desc, used).replace('|', '/')[:200]}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs,
           "rows_total": len(rows), "numbers": len(seen), "sections": {"0": label}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "diffs": diffs[:3]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
