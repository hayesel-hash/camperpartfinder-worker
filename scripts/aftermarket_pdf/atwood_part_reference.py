"""Two-pass reader for Atwood "hydro flame Furnace REPLACEMENT PART REFERENCE" pages
(2007 RV Appliance Service and Parts Manual): bold section headings, then rows
"<5-digit Atwood no.>  <description>" followed by a check mark (ZapfDingbats) in each model column.

Only pages with that fingerprint are read (at least 5 number rows and model-column check marks), so the
other sections of the manual (water heater matrices, range tables, jacks, couplers) are left alone.

Pass A: text lines from get_text(): a line "NNNNN  description"; a following line that is only a
parenthetical note ("(Use with Part # 33337)", "(NOT REQUIRED)") is appended.
Pass B: word boxes grouped by baseline: a 5-digit word left of the first model column, description =
words up to the first check mark / model column; a baseline holding only a parenthetical note,
within 16 pt below the row, is appended.

Only rows on which both passes give the same number and description are kept; the others are
reported as held (typically a note line whose text order differs from its position, or a
description that runs into the model columns).

Legend glyphs: Wingdings 0x99 (NLA - no longer available) and the trailing "a" glyph (while supplies
last) become plain-words notes. Output: supplied-documents JSON (rows page|n|number|description|section).
usage: python3 -I atwood_part_reference.py <pdf> <out.json> "<label>" [first-last page]
"""
import hashlib, json, re, sys

ROW = re.compile(r"^(\d{5})\s+(\S.*)$")
NUM = re.compile(r"^\d{5}$")
CHECK = "✗"
NLA, WSL = "\x99", "a"


def notes(desc, legend_wsl):
    toks = desc.split()
    out, extra = [], []
    for k, t in enumerate(toks):
        if t in (NLA, "❖"):
            extra.append("(NLA - no longer available)")
        elif legend_wsl and t == WSL and k == len(toks) - 1:
            extra.append("(while supplies last)")
        else:
            out.append(t)
    return " ".join(out + extra)


def fingerprint(text):
    rows = sum(1 for l in text.splitlines() if ROW.match(l.strip()))
    return rows >= 5 and text.count(CHECK) >= 5


def pass_a(text):
    wsl = "While supplies last" in text or "while supplies last" in text
    L = [l.strip() for l in text.splitlines()]
    rows = []
    for k, l in enumerate(L):
        m = ROW.match(l)
        if not m:
            continue
        desc = m.group(2)
        j = k + 1
        while j < len(L) and L[j].startswith("(") and not ROW.match(L[j]):
            desc += " " + L[j]; j += 1
        rows.append((m.group(1), " ".join(notes(desc, wsl).split())))
    return rows


def pass_b(words, text):
    wsl = "While supplies last" in text or "while supplies last" in text
    checks = [w[0] for w in words if w[4] == CHECK]
    xcol = min(checks) - 4 if checks else 10_000
    by = {}
    for w in words:
        by.setdefault(round(w[3]), []).append(w)
    nx = sorted(w[0] for w in words if NUM.match(w[4]) and w[0] < xcol)
    numx = nx[len(nx) // 2] if nx else 0
    rows, last_y, head = [], None, ""
    for y in sorted(by):
        ws = sorted((w for w in by[y] if w[0] < xcol), key=lambda w: w[0])
        if not ws:
            continue
        if NUM.match(ws[0][4]) and len(ws) > 1:
            rows.append([ws[0][4], " ".join(w[4] for w in ws[1:]), head]); last_y = y
            continue
        if ws[0][0] < numx - 5 and not ws[0][4].startswith("(") and not any(c.isdigit() for c in ws[0][4][:1]):
            head = " ".join(w[4] for w in ws)
            continue
        if rows and ws[0][4].startswith("(") and last_y is not None and y - last_y <= 16 and not any(NUM.match(w[4]) for w in ws):
            rows[-1][1] += " " + " ".join(w[4] for w in ws); last_y = y
    return [(n, " ".join(notes(d, wsl).split())) for n, d, _ in rows], [h for _, _, h in rows]


def read(pages, only=None):
    """pages: list of (text, words); only: set of 1-based page numbers to read (None = all with the
    fingerprint). -> rows [(page, n, number, desc, heading)] where both passes give the same number AND
    description; held = rows only one pass produced (left out, reported). The heading (bold section
    line left of the number column, from word positions) is kept only if it also appears in the text layer."""
    rows, held = [], []
    for i, (text, words) in enumerate(pages):
        if (only and i + 1 not in only) or not fingerprint(text):
            continue
        a = pass_a(text)
        b, heads = pass_b(words, text)
        lines = {l.strip() for l in text.splitlines()}
        bs = list(zip(b, heads))
        for k, (n, d) in enumerate(a, 1):
            hit = next((x for x in bs if x[0] == (n, d)), None)
            if hit:
                bs.remove(hit); rows.append((i + 1, k, n, d, hit[1] if hit[1] in lines else ""))
            else:
                held.append({"page": i + 1, "a": [n, d]})
        held += [{"page": i + 1, "b": list(x[0])} for x in bs]
    return rows, held


def main(pdf, outp, label, pages=""):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    only = None
    if pages:
        a, _, z = pages.partition("-"); only = set(range(int(a), int(z or a) + 1))
    rows, held = read([(p.get_text(), p.get_text("words")) for p in doc], only)
    secs, seen, lines = {}, set(), []
    for pg, n, num, desc, head in rows:
        if num in seen:
            continue
        code = secs.setdefault(head, str(len(secs)))
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')[:200]}|{code}")
    out = {"doc": sha, "pages": doc.page_count, "agree": bool(lines), "held": held, "rows_total": len(rows),
           "numbers": len(seen), "pages_read": sorted({r[0] for r in rows}),
           "sections": {c: (f"{label} — {h}" if h else label) for h, c in secs.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "pages_read": out["pages_read"], "held": len(held)}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:5])
