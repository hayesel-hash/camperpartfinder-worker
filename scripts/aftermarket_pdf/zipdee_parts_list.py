"""Two-pass reader for Zip Dee awning parts lists (Door, Patio roller, Slideout; Acrobat 9 sheets): page 2 is a table
"Ref # | PART # | <title / description>" with one row per baseline and note lines ("(includes ...)", "(Note: specify
slope code)") under a row. Part numbers are six characters, mostly digits ("343240", "20161S"); Ref # is a callout
("3A") or "NS" (not shown). Page 1 (the drawing) has no numbers.

Pass A: text-line order (description, PART #, Ref #, then note lines until the next description). Pass B: word boxes cut
into the Ref / PART / description columns located from the header words. Notes are appended to the row's description.
Only rows both passes give identically are kept.
usage: python3 -I zipdee_parts_list.py <pdf> <out.json> "<section label>" """
import hashlib, json, re, sys
import pymupdf

PN = re.compile(r"^(?=[0-9A-Z]*\d{4})[0-9A-Z]{6,7}$")
REF = re.compile(r"^(\d{1,2}[A-Z]?|NS)$")
END = re.compile(r"^(Note: NS = Not Shown|\d\d/\d\d/\d\d)$")


def open_paren(text):
    return text.count("(") > text.count(")")


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    try:
        k = L.index("Ref #") + 1
    except ValueError:
        return []
    rows, desc = [], []
    while k < len(L):
        s = L[k]
        if END.match(s):
            break
        if s in ("PART #", "Ref #"):  # a second table header: drop its heading line
            desc = []; k += 1
            continue
        if PN.match(s) and k + 1 < len(L) and REF.match(L[k + 1]) and desc:
            rows.append([s, " ".join(desc)]); desc = []; k += 2
            continue
        if rows and not desc and (s.startswith("(") or open_paren(rows[-1][1])):
            rows[-1][1] += " " + s
        else:
            desc.append(s)
        k += 1
    return [(n, " ".join(d.split())) for n, d in rows]


def pass_b(page):
    W = page.get_text("words")
    hp = [w for w in W if w[4] == "PART"]; hr = [w for w in W if w[4] == "Ref"]
    if not hp or not hr:
        return []
    yh = hp[0][3]; xp = hp[0][0] - 8; xr = hr[0][0] - 8; xd = hp[0][2] + 30
    lines = {}
    for w in W:
        if w[1] < yh:
            continue
        key = round((w[1] + w[3]) / 2)
        k = next((k for k in lines if abs(k - key) <= 2), key)
        lines.setdefault(k, []).append(w)
    rows = []
    for y in sorted(lines):
        ws = sorted(lines[y], key=lambda w: w[0])
        ref = [w[4] for w in ws if xr <= w[0] < xp]
        num = [w[4] for w in ws if xp <= w[0] < xd]
        desc = " ".join(w[4] for w in ws if w[0] >= xd)
        if END.match(" ".join(w[4] for w in ws)) or (not num and not desc and ref and END.match(" ".join(ref))):
            break
        if len(num) == 1 and PN.match(num[0]) and len(ref) == 1 and REF.match(ref[0]) and desc:
            rows.append([num[0], desc])
        elif not num and not ref and desc and rows and (desc.startswith("(") or open_paren(rows[-1][1])):
            rows[-1][1] += " " + desc
        elif not num and not ref and desc.startswith("Note: NS"):
            break
    return [(n, " ".join(d.split())) for n, d in rows]


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs = [], []
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        rows += [(i + 1, n, num, desc) for n, (num, desc) in enumerate([x for x in a if x in b], 1)]
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen or not desc:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs,
           "rows_total": len(rows), "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "all_rows_agree": not diffs, "rows": len(rows),
                      "numbers": len(seen), "diffs": diffs[:3]}, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
