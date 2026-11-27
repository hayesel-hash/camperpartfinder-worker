"""Two-pass reader for Dometic (Duo-Therm, LaGrange) roof A/C parts lists with a model matrix, e.g. Modularized
Brisk Air 579 series parts list 3308714.025: Index | Description | Part No. | one rotated model column per unit
(57912.531(X) ... 57915.731(X)) holding a mark (a letter) or a dash, then an optional date ("2/14/03**" =
discontinue date, "8/25/03##" = start date, per the legend "** Designates Discontinue Date / ## Designates Start
Date"). Sub-items such as "A1 Overload" carry their own index. "SEE NOTE n" rows have no number and are skipped.

Only the main matrix is read. The NOTE blocks and the "Customer Options" tables (two number columns) are listed
in "unread" (every Dometic-style number on the page that is not a matrix row).

Pass A: text lines in content order: [index] description, number (or SEE NOTE), one line per model column, [date].
Pass B: word boxes by baseline; columns from the header words (Description, Part No.) and the rotated model labels
(x centre of each label); marks within 8 pt of a model column centre; a date right of the last model column.
A row is kept only if both passes give the same (index, description, number, marks, date).
Applicability = the model columns with a mark (not a dash); "[applies to: ...]" when not every model is marked.
usage: python3 -I dometic_model_matrix_list.py <pdf> <out.json> "<label>"
"""
import hashlib, json, re, sys

NUM = re.compile(r"^\d{6,7}\.\d{3}$")
SEE = re.compile(r"^SEE NOTE\s*\d+$")
IDX = re.compile(r"^(\d{1,2}|A\d)$")
MARK = re.compile(r"^[A-J]$")
DASH = {"–", "-", "—"}
DATE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2})(\*\*|##)$")
MODEL = re.compile(r"^\d{5}\.[\dX]{3}\(X\)$")


def norm(s):
    return " ".join(s.split())


def date_text(d):
    m = DATE.match(d) if d else None
    if not m:
        return ""
    return (" (discontinued " if m.group(2) == "**" else " (start date ") + m.group(1) + ")"


def models(words):
    ms = sorted((w for w in words if MODEL.match(w[4]) and (w[3] - w[1]) > 2 * (w[2] - w[0])), key=lambda w: w[0])
    return [((w[0] + w[2]) / 2, w[4]) for w in ms]


def pass_a(text, ncols):
    L = [norm(l) for l in text.splitlines()]
    L = [l for l in L if l]
    try:
        k = max(i for i, l in enumerate(L) if l == "No.")
    except ValueError:
        return [], "no header"
    rows, i, idx = [], k + 1, None
    while i < len(L):
        l = L[i]
        if l.startswith("NOTE") or l.startswith("Customer Options") or l.startswith("*") or MODEL.match(l):
            break
        if IDX.match(l) and i + 1 < len(L) and not (NUM.match(L[i + 1]) or SEE.match(L[i + 1])):
            idx = l; i += 1; l = L[i]
        elif IDX.match(l):
            return rows, "index without description at line %d" % i
        desc = l; i += 1
        if i >= len(L) or not (NUM.match(L[i]) or SEE.match(L[i])):
            if re.fullmatch(r"\d{1,3}", desc):  # page number at the end of the text layer
                break
            return rows, "no part number after %r" % desc
        num = L[i]; i += 1
        cells = L[i:i + ncols]; i += ncols
        if len(cells) < ncols or not all(MARK.match(c) or c in DASH for c in cells):
            return rows, "bad matrix cells after %r: %r" % (num, cells)
        date = None
        if i < len(L) and DATE.match(L[i]):
            date = L[i]; i += 1
        if NUM.match(num):
            rows.append((idx, desc, num, "".join("x" if MARK.match(c) else "-" for c in cells), date))
        idx = None if not IDX.match(idx or "") else idx
    return rows, None


def pass_b(words, cols):
    d = next((w for w in words if w[4] == "Description"), None)
    p = next((w for w in words if w[4] == "Part" and d and abs(w[3] - d[3]) < 3), None)
    if not d or not p:
        return []
    head_y = d[3] + 2
    xd, xp = d[0] - 12, p[0] - 8  # descriptions start up to ~9 pt left of their header (p4)
    xm0 = cols[0][0] - 8
    xlast = cols[-1][0] + 8
    by, cur = [], None
    for w in sorted((w for w in words if w[1] > head_y and not MODEL.match(w[4])), key=lambda w: w[3]):
        if cur is None or w[3] - cur[0] > 1.5:  # baselines within 1.5 pt form one line (bold SEE NOTE cells)
            cur = [w[3], []]; by.append(cur)
        cur[1].append(w)
    rows, idx = [], None
    for _, line in by:
        ws = sorted(line, key=lambda w: w[0])
        t = [w[4] for w in ws]
        if t and (t[0].startswith("NOTE") or t[0] == "Customer"):
            break
        ix = [w[4] for w in ws if w[2] < xd]
        desc = norm(" ".join(w[4] for w in ws if xd <= w[0] < xp))
        num = norm(" ".join(w[4] for w in ws if xp <= w[0] < xm0))
        cells = {}
        for w in ws:
            if xm0 <= w[0] < xlast:
                k = min(range(len(cols)), key=lambda k: abs(cols[k][0] - (w[0] + w[2]) / 2))
                if abs(cols[k][0] - (w[0] + w[2]) / 2) < 8:
                    cells[k] = w[4]
        date = norm(" ".join(w[4] for w in ws if w[0] >= xlast)) or None
        if ix and IDX.match(ix[0]):
            idx = ix[0]
        if not desc and (not num or re.fullmatch(r"\d{1,3}", num)):  # empty line / page number
            continue
        if not NUM.match(num):
            if not SEE.match(num):
                rows.append((idx, desc, num or None, None, date))
            continue
        marks = "".join("x" if MARK.match(cells.get(k, "")) else ("-" if cells.get(k) in DASH else "?")
                        for k in range(len(cols)))
        rows.append((idx, desc, num, marks, date))
    return rows


def read(doc):
    out, held, unread, allmodels = [], [], [], []
    for pi, page in enumerate(doc):
        words = page.get_text("words")
        cols = models(words)
        if len(cols) < 2:
            continue
        allmodels = [c[1] for c in cols]
        a, err = pass_a(page.get_text(), len(cols))
        if err:
            held.append({"page": pi + 1, "pass_a_error": err})
        b = pass_b(words, cols)
        # a row's index is printed only on its first line; pass A carries it the same way as pass B
        bl = list(b)
        n = 0
        for r in a:
            if r in bl:
                bl.remove(r); n += 1
                out.append((pi + 1, n, r, [c[1] for c in cols]))
            else:
                held.append({"page": pi + 1, "a": list(r)})
        held += [{"page": pi + 1, "b": list(r)} for r in bl]
        got = {r[2] for r in a}
        unread += [{"page": pi + 1, "number": w[4]} for w in words if NUM.match(w[4]) and w[4] not in got]
    return out, held, unread, allmodels


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, held, unread, allm = read(doc)
    seen, lines, conflicts, secs = {}, [], [], {}
    for pg, n, (idx, desc, num, marks, date), cols in rows:
        d = desc + date_text(date)
        if "x" in marks and "-" in marks:
            d += " [applies to: " + ", ".join(c for c, m in zip(cols, marks) if m == "x") + "]"
        if num in seen:
            if seen[num] != d:
                conflicts.append({"number": num, "a": seen[num], "b": d})
            continue
        seen[num] = d
        code = secs.setdefault(label, str(len(secs)))
        lines.append(f"{pg}|{n}|{num}|{d.replace('|', '/')[:200]}|{code}")
    bad = {c["number"] for c in conflicts}
    lines = [l for l in lines if l.split("|")[2] not in bad]
    out = {"doc": sha, "pages": doc.page_count, "agree": bool(lines) and not held and not conflicts,
           "held": held, "conflicts": conflicts, "unread": unread, "models": allm, "rows_total": len(rows),
           "numbers": len(lines), "sections": {c: s for s, c in secs.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(lines),
                      "models": allm, "held": held[:10], "conflicts": conflicts[:5], "unread": len(unread)},
                     ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
