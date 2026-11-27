"""Two-pass reader for simple one-line parts tables found by their header words, e.g.
Generac exploded-view lists "ITEM | PART NO. | QTY. | DESCRIPTION" (two tables side by side) and REMIS spare parts
catalogue "Item number | Description of spare parts | Image".

Pass A: text-line order. A line that is a part number is followed by its description: the first later line that is
neither a part number nor a bare integer (quantity / image callout).
Pass B: word positions. Columns come from the header words (number column from <num_label>, description column from
<desc_label> up to the next header word named in <stop_labels> or the next table's number header); a part number in
the number column takes the description words on its own baseline.
Only rows both passes give identically are kept; a number printed with two different descriptions is not loaded.
Rows whose description wraps onto a second line are read by pass A only and so are left out ("diffs").
Section = the page's first text line under the running header.
usage: python3 -I header_table_parts.py <pdf> <out.json> <num_label> <desc_label> [<stop_labels,comma,separated>]"""
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^(?=(?:\D*\d){3})[0-9A-Z]{5,10}$")
INT = re.compile(r"^\d{1,3}$")


def norm(s):
    return " ".join(s.split())


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    out = []
    for k, l in enumerate(L):
        if NUM.match(l):
            j = k + 1
            while j < len(L) and INT.match(L[j]):
                j += 1
            if j < len(L) and not NUM.match(L[j]):
                out.append((l, norm(L[j])))
    return out


def pass_b(page, num_label, desc_label, stops):
    W = page.get_text("words")
    heads = sorted([w for w in W if w[4] == num_label], key=lambda w: w[0])
    out = []
    for h in heads:
        d = [w for w in W if w[4] == desc_label and abs(w[1] - h[1]) < 3 and w[0] > h[0]]
        if not d:
            continue
        d = min(d, key=lambda w: w[0])
        rights = [w[0] for w in W if abs(w[1] - h[1]) < 3 and w[0] > d[0] and (w[4] in stops or w[4] == num_label)]
        nxt_num = [g[0] for g in heads if g[0] > h[0]]
        right = min(rights + [page.rect.width]) - 3
        if nxt_num:
            # the next table's first column header sits left of its number header
            right = min(right, nxt_num[0] - 40)
        xn0, xn1 = h[0] - 20, d[0] - 4
        N = [w for w in W if w[1] > h[3] and xn0 <= w[0] < xn1 and NUM.match(w[4])]
        if not N:
            continue
        # descriptions can start left of their header word (REMIS): the column begins after the widest number
        xd = min(d[0] - 4, max(w[2] for w in N) + 8)
        for w in N:
            if True:
                m = (w[1] + w[3]) / 2
                ds = sorted([v for v in W if xd <= v[0] < right and abs((v[1] + v[3]) / 2 - m) < 2.5 and not (v[0] < d[0] - 4 and INT.match(v[4]))],
                            key=lambda v: v[0])
                if ds:
                    out.append((w[4], norm(" ".join(v[4] for v in ds))))
    return out


def main(pdf, outp, num_label, desc_label, stops=""):
    stops = set(s for s in stops.split(",") if s)
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, secs = [], [], {}
    for i, p in enumerate(d):
        b = pass_b(p, num_label, desc_label, stops)
        if not b:
            continue
        a = pass_a(p)
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:4], "only_b": [x for x in b if x not in a][:4]})
        head = norm(" / ".join([l.strip() for l in p.get_text().splitlines() if l.strip()][:3]))[:160]
        key = secs.setdefault(head, str(len(secs)))
        rows += [(i + 1, n, num, desc, key) for n, (num, desc) in enumerate([x for x in b if x in a], 1)]
    descs = {}
    for r in rows:
        descs.setdefault(r[2], set()).add(r[3])
    conflicts = {k: sorted(v) for k, v in descs.items() if len(v) > 1}
    seen, lines = set(), []
    for pg, n, num, desc, key in rows:
        if num in seen or num in conflicts or not desc:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{key}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs,
           "rows_total": len(rows), "numbers": len(seen), "conflicts": conflicts,
           "sections": {v: k for k, v in secs.items()}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "rows": len(rows), "numbers": len(seen), "conflicts": len(conflicts),
                      "diff_pages": [x["page"] for x in diffs], "diffs": diffs[:3]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(*sys.argv[1:6])
