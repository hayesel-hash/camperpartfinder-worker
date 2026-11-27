"""Two-pass reader for CURT's "ALL PRODUCTS LISTED NUMERICALLY" index (2024 Catalog & Application Guides).

Layout: four columns per page, each with the header "Part # | Description | MP | IP" and one row per
CURT part: number, description (cut to ~20 characters in the source), master-pack and inner-pack
quantities. Only pages with that exact header are read: the neighbouring "LISTED NUMERICALLY" tables
of hitches / wiring by vehicle (Part # | Years | Make / Model) are fitment and are skipped.
MP / IP (pack quantities) are not kept.

Pass A: plain text lines: a number line, then the description line, then two integer lines.
Pass B: word boxes: columns from the "Part" header words; a row is a baseline with a number at the
column's left edge; description = words between the number and the MP column; MP / IP must be integers.
Only rows on which both passes agree are kept. Output: supplied-documents JSON
(rows page|n|number|description|section).
usage: python3 -I curt_numeric_index.py <pdf> <out.json>
"""
import hashlib, json, re, sys

NUM = re.compile(r"^(?=(?:[^0-9]*[0-9]){4})[0-9A-Z][0-9A-Z-]{3,14}$")
INT = re.compile(r"^\d{1,4}$")
HDR = ["Part #", "Description", "MP", "IP"]


def norm(s):
    return " ".join(s.split())


def is_index_page(text):
    L = [norm(l) for l in text.splitlines() if l.strip()]
    for k in range(len(L) - 3):
        if L[k:k + 4] == HDR:
            return True
    return False


def split_lines(text):
    """Text lines, with cells the text layer glued together split again: "200 0" (MP IP) and
    "20002 MIRROR" (number + description)."""
    out = []
    for l in (norm(x) for x in text.splitlines() if x.strip()):
        m = re.fullmatch(r"(\d{1,4}) (\d{1,4})", l)
        if m:
            out += [m.group(1), m.group(2)]
            continue
        first, _, rest = l.partition(" ")
        prev_ends_row = not out or INT.match(out[-1]) or out[-1] == "IP"
        if rest and prev_ends_row and NUM.match(first) and not first.isalpha():
            out += [first, rest]
            continue
        out.append(l)
    return out


def pass_a(text):
    L = split_lines(text)
    rows, k = [], 0
    while k < len(L):
        if L[k:k + 4] == HDR:
            k += 4
            continue
        if NUM.match(L[k]):
            if k + 3 < len(L) and not NUM.match(L[k + 1]) and INT.match(L[k + 2]) and INT.match(L[k + 3]) \
                    and L[k + 1] not in HDR:
                rows.append((L[k], L[k + 1]))
                k += 4
                continue
            if k + 2 < len(L) and INT.match(L[k + 1]) and INT.match(L[k + 2]):
                rows.append((L[k], ""))
                k += 3
                continue
        k += 1
    return rows


def pass_b(words):
    heads = [w for w in words if w[4] == "Part" and any(v[4] == "#" and abs(v[1] - w[1]) < 2 and 0 < v[0] - w[2] < 8
                                                        for v in words)]
    mps = [w for w in words if w[4] == "MP"]
    if not heads:
        return []
    hy = min(h[3] for h in heads)
    xs = sorted(h[0] for h in heads)
    rows = []
    for ci, x0 in enumerate(xs):
        x1 = xs[ci + 1] if ci + 1 < len(xs) else 10 ** 6
        mp = [m[0] for m in mps if x0 < m[0] < x1]
        if not mp:
            continue
        mpx = mp[0]
        col = [w for w in words if x0 - 3 <= w[0] < x1 - 3 and w[1] > hy]
        by = {}
        for w in col:
            by.setdefault(round(w[3]), []).append(w)
        for y in sorted(by):
            ws = sorted(by[y], key=lambda w: w[0])
            if not ws or abs(ws[0][0] - x0) > 4 or not NUM.match(ws[0][4]):
                continue
            desc = [w[4] for w in ws[1:] if w[0] < mpx - 2]
            qty = [w[4] for w in ws[1:] if w[0] >= mpx - 2]
            if len(qty) != 2 or not all(INT.match(q) for q in qty):
                continue
            rows.append((ws[0][4], norm(" ".join(desc))))
    return rows


def read(pages):
    """pages: list of (text, words). -> rows [(page, n, number, desc)], held"""
    rows, held = [], []
    for i, (text, words) in enumerate(pages):
        if not is_index_page(text):
            continue
        A, B = pass_a(text), pass_b(words)
        a, b = set(A), set(B)
        k = 0
        for n, d in sorted(a & b, key=lambda r: r[0]):
            if not d:
                held.append({"page": i + 1, "number": n, "reason": "no description"})
                continue
            k += 1
            rows.append((i + 1, k, n, d))
        for n, d in sorted(a ^ b):
            held.append({"page": i + 1, "number": n, "desc": d, "only_in": "A" if (n, d) in a else "B"})
    return rows, held


def main(pdf, outp):
    import pymupdf
    doc = pymupdf.open(pdf)
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    rows, held = read([(p.get_text(), p.get_text("words")) for p in doc])
    lines, seen = [], set()
    for pg, n, num, desc in rows:
        if num in seen:
            continue
        seen.add(num)
        lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|1")
    out = {"doc": sha, "pages": doc.page_count, "agree": bool(lines), "held": held, "rows_total": len(rows),
           "numbers": len(seen),
           "sections": {"1": "CURT 2024 catalogue - All products listed numerically (descriptions cut short in the source)"},
           "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "rows": len(rows), "numbers": len(seen), "held": len(held)}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
