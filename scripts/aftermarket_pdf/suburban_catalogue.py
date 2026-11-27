"""Two-pass readers for Suburban (Airxcel) sales literature.

mode "catalogue" (2025 Aftermarket Appliances Parts Catalogue): "<stock no.> <description>" lines, stock numbers like
5238A, 6261APW or 6-digit 234589. Pass A: text order (a number line followed by its description line); pass B: word
boxes (the words right of the number on the same baseline). Rows whose description wraps onto a second line, or is a
bare variant word ("White", "Black") without its product heading, are reported, not loaded.

mode "core" (Furnace Core Replacement model cross reference, LS122221): FIND THIS "Suburban Heater Model Number" ->
ORDER THIS "Suburban Core Stock #" (+ an NTP-STAG distributor part number, which is not loaded). Each core stock number
is loaded once as "Furnace core replacement [models: ...]" listing the heater models printed against it (model
applicability, not interchangeability). Pass A: text order (model, stock, optional distributor number); pass B: word
boxes by header column.
usage: python3 -I suburban_catalogue.py <catalogue|core> <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^(\d{4}A[A-Z]{0,3}|\d{6})$")
MODEL = re.compile(r"^(NT|SF|P)-\d{2}[A-Z]*$")
CORE = re.compile(r"^\d{4}A$")
NTP = re.compile(r"^S6U\d+-\d+$")


def cat_pass_a(page):
    L = [" ".join(l.split()) for l in page.get_text().splitlines()]
    L = [l for l in L if l]
    out = [(t, L[k + 1]) for k, t in enumerate(L[:-1]) if NUM.match(t) and not NUM.match(L[k + 1])]
    for t in L:  # number and description in one text line
        m = re.match(r"^(\d{4}A[A-Z]{0,3}|\d{6}) (\D.*)$", t)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def cat_pass_b(page):
    W = page.get_text("words")
    out, held = [], []
    for w in W:
        if not NUM.match(w[4]):
            continue
        if any(abs(v[1] - w[1]) < 2 and v[2] <= w[0] and w[0] - v[2] < 25 for v in W):
            continue  # not the first word of its line
        line = sorted([v for v in W if abs(v[1] - w[1]) < 2 and v[0] > w[2]], key=lambda v: v[0])
        words, last = [], w[2]
        for v in line:
            if v[0] - last > 30:
                break
            words.append(v); last = v[2]
        if not words:
            continue
        x0 = words[0][0]
        below = [v for v in W if 4 < v[1] - w[1] < 13 and abs(v[0] - x0) < 2]
        num_below = [v for v in W if 4 < v[1] - w[1] < 13 and NUM.match(v[4]) and abs(v[0] - w[0]) < 3]
        desc = " ".join(v[4] for v in words)
        if below and not num_below:
            held.append((w[4], desc, "description continues on the next line")); continue
        if len(desc.split()) < 2:
            held.append((w[4], desc, "bare variant word without its product heading")); continue
        out.append((w[4], desc))
    return out, held


def core_rows(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    a, k = [], 0
    while k < len(L):
        if MODEL.match(L[k]) and k + 1 < len(L) and CORE.match(L[k + 1]):
            a.append((L[k], L[k + 1])); k += 2
            if k < len(L) and NTP.match(L[k]):
                k += 1
            continue
        k += 1
    W = page.get_text("words")
    hm = [w for w in W if w[4] == "Model"]
    hs = [w for w in W if w[4] == "Stock"]
    b = []
    if hm and hs:
        for w in W:
            if MODEL.match(w[4]) and abs(w[0] - hm[0][0]) < 40:
                st = [v for v in W if abs((v[1] + v[3]) / 2 - (w[1] + w[3]) / 2) < 3 and CORE.match(v[4]) and abs(v[0] - hs[0][0]) < 40]
                if len(st) == 1:
                    b.append((w[4], st[0][4]))
    return a, b


def main(mode, pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    if not d.permissions & pymupdf.PDF_PERM_COPY:
        print(json.dumps({"sha": sha, "error": "copy-protected"})); return
    kept, diffs, held = [], [], []
    if mode == "core":
        a, b = core_rows(d[0])
        if sorted(a) != sorted(b):
            diffs.append({"page": 1, "only_a": [x for x in a if x not in b], "only_b": [x for x in b if x not in a]})
        models = {}
        for m, st in [x for x in a if x in b]:
            models.setdefault(st, []).append(m)
        kept = [(1, st, "Furnace core replacement [models: " + ", ".join(ms) + "]") for st, ms in models.items()]
    else:
        for i, p in enumerate(d):
            a = cat_pass_a(p)
            b, h = cat_pass_b(p)
            held += [{"page": i + 1, "num": n, "text": t, "why": why} for n, t, why in h]
            only_b = [x for x in b if x not in a]
            if only_b:
                diffs.append({"page": i + 1, "only_b": only_b[:6]})
            kept += [(i + 1, n, t) for n, t in b if (n, t) in a]
    seen, lines, n = {}, [], 0
    for pg, num, desc in kept:
        if num in seen:
            if seen[num] != desc:
                held.append({"page": pg, "num": num, "why": "printed again with different text (first kept)", "text": desc})
            continue
        seen[num] = desc; n += 1
        lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "numbers": len(seen),
           "sections": {"0": section}, "rows": "\n".join(lines), "held": held}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "numbers": len(seen), "held": len(held), "diffs": diffs[:3]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(*sys.argv[1:5])
