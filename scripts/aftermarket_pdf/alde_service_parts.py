"""Two-pass reader for Alde service manuals ("EXPLODED DRAWING" and "SPARE PARTS" pages).

Alde prints its numbers as "NNNN NNN" (e.g. 3020 011) after a callout ("1.") with a one-line
description ("Service cover"); one callout can carry two numbers (model A / model HE). Only pages
with an "EXPLODED DRAWING" or "SPARE PARTS" heading are read, so numbers quoted in prose
(fault finding, wiring diagram) are not taken.

Pass A: text lines from get_text(): a line starting with an optional callout and a number; the
description is the rest of the line, or the next line when the number stands alone.
Pass B: word boxes grouped by baseline: a 4-digit word followed by a 3-digit word, description =
the words to the right on the same baseline up to the next callout / number / wide gap.

The supplied-documents lane does not allow spaces in numbers, so the drop stores the number with the
printed space removed (3020 011 -> 3020011); read() keeps the printed form. Output: supplied-documents JSON
(rows page|n|number|description|section).
usage: python3 -I alde_service_parts.py <pdf> <out.json> "<product label>"
"""
import hashlib, json, re, sys

HEAD = re.compile(r"^\d+\.\s+(EXPLODED DRAWING|SPARE PARTS)\s*$")
LINE = re.compile(r"^(?:\d{1,2}\.\s+)?(\d{4}) (\d{3})(?!\d)\s*(.*)$")
CALLOUT = re.compile(r"^\d{1,2}\.$")
D4, D3 = re.compile(r"^\d{4}$"), re.compile(r"^\d{3}$")


def section_of(lines):
    for l in lines:
        m = HEAD.match(l.strip())
        if m:
            return m.group(1)
    return None


def clean(s):
    return " ".join(s.split())


def pass_a(text):
    L = [l.strip() for l in text.splitlines()]
    rows = []
    for k, l in enumerate(L):
        m = LINE.match(l)
        if not m:
            continue
        desc = m.group(3).strip()
        if not desc and k + 1 < len(L) and L[k + 1] and not LINE.match(L[k + 1]) and not CALLOUT.match(L[k + 1]):
            desc = L[k + 1]
        if desc:
            rows.append((f"{m.group(1)} {m.group(2)}", clean(desc)))
    return rows


def pass_b(words):
    by = {}
    for w in words:
        by.setdefault(round(w[3]), []).append(w)
    rows = []
    for y in sorted(by):
        ws = sorted(by[y], key=lambda w: w[0])
        i = 0
        while i < len(ws) - 1:
            a, b = ws[i], ws[i + 1]
            if D4.match(a[4]) and D3.match(b[4]) and b[0] - a[2] < 20:
                desc, j, x1 = [], i + 2, b[2]
                while j < len(ws):
                    w = ws[j]
                    if CALLOUT.match(w[4]) or (D4.match(w[4]) and j + 1 < len(ws) and D3.match(ws[j + 1][4])):
                        break
                    if w[0] - x1 > 60:
                        break
                    desc.append(w[4]); x1 = w[2]; j += 1
                if desc:
                    rows.append((f"{a[4]} {b[4]}", clean(" ".join(desc))))
                i = j
                continue
            i += 1
    return rows


def order_like(a, b):
    """pass B reads baseline by baseline (both columns of a line together); compare as multisets"""
    return sorted(a) == sorted(b)


def read(pages):
    """pages: list of (text, words). -> rows [(page, n, number, desc, section)], diffs"""
    rows, diffs = [], []
    for i, (text, words) in enumerate(pages):
        sec = section_of(text.splitlines())
        if not sec:
            continue
        a, b = pass_a(text), pass_b(words)
        if not order_like(a, b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:8], "only_b": [x for x in b if x not in a][:8]})
        for k, (n, d) in enumerate(a, 1):
            rows.append((i + 1, k, n, d, sec))
    return rows, diffs


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, diffs = read([(p.get_text(), p.get_text("words")) for p in doc])
    secs = {"EXPLODED DRAWING": "1", "SPARE PARTS": "2"}
    seen, lines = set(), []
    for pg, n, num, desc, sec in rows:
        if num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num.replace(' ', '')}|{desc.replace('|', '/')[:200]}|{secs[sec]}")
    out = {"doc": sha, "pages": doc.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"1": f"{label} exploded drawing", "2": f"{label} spare parts"},
           "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "diffs": diffs[:3]},
                     ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
