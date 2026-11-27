"""Two-pass reader for Truma dealer parts-viewer printouts (dealer.truma.com/_parts/viewer, printed to PDF, e.g.
"Mover SR - from 09/2011"): a ruled table Pos. | No. | Description | Information where the part number wraps inside
its cell ("60030-" / "88700") and a row can break across pages (prefix at the bottom of one page, Pos and suffix at
the top of the next).

Pass A: text-line order (Pos line, optional prefix line, "<suffix>  <description>" line, information lines until the
next Pos). Pass B: row bands from the horizontal rules and column edges from the vertical rules (pymupdf drawings),
word boxes assigned to cells. Placeholder number 00000-00001 ("not available") is skipped and counted. The
Information cell is kept in brackets after the description ("Exchange Control unit SR (when returning ...)").
Only rows on which both passes agree are kept.

usage: python3 -I truma_parts_viewer.py <pdf> <out.json> "<section label>"
"""
import hashlib, json, re, sys
import pymupdf

POS = re.compile(r"^\d{2}[a-z]?$")
PRE = re.compile(r"^\d{5}-$")
SUF = re.compile(r"^(\d{3,5})\s+(.*)$")
PLACEHOLDER = "00000-00001"


def norm(t):
    return " ".join(t.replace("\xa0", " ").split()).strip()


def row_text(desc, info):
    desc, info = norm(desc), norm(info)
    return f"{desc} ({info})" if info else desc


def pass_a(doc):
    rows, carry = [], None
    for pno, page in enumerate(doc, 1):
        L = [l.rstrip() for l in page.get_text().splitlines()]
        L = [l for l in L if l.strip() and not l.startswith("Page ") and "Truma/MANOEUVRING" not in l
             and not l.startswith("http://") and not re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", l.strip())]
        k = 0
        cur = None
        while k < len(L):
            s = L[k].strip()
            m_pp = re.match(r"^(\d{2}[a-z]?)\s+(\d{5}-)$", s)
            if POS.match(s) or m_pp:
                if cur:
                    rows.append(cur)
                if m_pp:
                    pos, pre = m_pp.group(1), m_pp.group(2); k += 1
                else:
                    pos = s; k += 1
                    if k < len(L) and PRE.match(L[k].strip()):
                        pre = L[k].strip(); k += 1
                    else:
                        pre, carry = carry, None
                m = SUF.match(L[k].strip()) if k < len(L) else None
                if not (pre and m):
                    cur = None; continue
                cur = {"page": pno, "pos": pos, "number": pre + m.group(1), "desc": m.group(2), "info": []}
                k += 1; continue
            if PRE.match(s) and k == len(L) - 1:
                carry = s
                if cur:
                    rows.append(cur); cur = None
                k += 1; continue
            if cur:
                cur["info"].append(s)
            k += 1
        if cur:
            rows.append(cur)
    out = []
    for r in rows:
        # the description line can carry the information cell after two or more spaces
        parts = re.split(r"\s{2,}", r["desc"], maxsplit=1)
        desc, info = parts[0], " ".join(parts[1:] + r["info"])
        out.append((r["page"], r["pos"], r["number"], row_text(desc, info)))
    return out


def rules(page):
    hs, vs = set(), set()
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "re":
                r = it[1]
                if r.width > 100 and r.height < 2:
                    hs.add(round((r.y0 + r.y1) / 2, 1))
                if r.height > 10 and r.width < 2:
                    vs.add(round((r.x0 + r.x1) / 2, 1))
            elif it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.5 and abs(a.x - b.x) > 100:
                    hs.add(round(a.y, 1))
                if abs(a.x - b.x) < 0.5 and abs(a.y - b.y) > 10:
                    vs.add(round(a.x, 1))

    def merge(v):
        out = []
        for y in sorted(v):
            if out and y - out[-1] < 3:
                continue
            out.append(y)
        return out
    return merge(hs), merge(vs)


def pass_b(doc):
    rows, carry = [], None
    for pno, page in enumerate(doc, 1):
        hs, vs = rules(page)
        W = page.get_text("words")
        hdr = [w for w in W if w[4] == "Pos." and w[0] < 75]  # not the "c/w Pos. 7 and 8" information text
        if len(vs) < 5:
            continue
        yh = hdr[0][3] if hdr else 0  # continuation pages repeat no header
        xs = vs[:5]  # left edge, Pos|No, No|Description, Description|Information, right edge
        edges = list(hs)
        if not hdr:  # continuation page: the first row sits above the first printed rule
            edges = [hs[0] - 26.0] + edges
        edges.append(edges[-1] + 26.0)  # a row cut by the page break has no closing rule
        bands = [(a, b) for a, b in zip(edges, edges[1:]) if a >= yh - 1]
        for a, b in bands:
            ws = sorted([w for w in W if a < (w[1] + w[3]) / 2 < b], key=lambda w: (round(w[1]), w[0]))
            cell = lambda x0, x1: [w for w in ws if x0 <= w[0] < x1]
            pos = " ".join(w[4] for w in cell(xs[0], xs[1]))
            num = "".join(w[4] for w in sorted(cell(xs[1], xs[2]), key=lambda w: w[1]))
            desc = " ".join(w[4] for w in cell(xs[2], xs[3]))
            info = " ".join(w[4] for w in cell(xs[3], xs[4]))
            if not pos and PRE.match(num) and not desc:
                carry = num; continue
            if not POS.match(pos):
                continue
            if re.match(r"^\d{3,5}$", num) and carry:
                num, carry = carry + num, None
            rows.append((pno, pos, num, row_text(desc, info)))
    return rows


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    a, b = pass_a(d), pass_b(d)
    keep = [r for r in a if r in b]
    diffs = {"only_a": [r for r in a if r not in b], "only_b": [r for r in b if r not in a]}
    seen, lines, placeholders, dup = {}, [], [], []
    n_on_page = {}
    for pg, pos, num, desc in keep:
        if num == PLACEHOLDER:
            placeholders.append({"page": pg, "pos": pos, "text": desc}); continue
        if num in seen:
            if seen[num] != desc:
                dup.append({"page": pg, "number": num, "first": seen[num], "here": desc})
            continue
        seen[num] = desc
        n_on_page[pg] = n_on_page.get(pg, 0) + 1
        lines.append(f"{pg}|{n_on_page[pg]}|{num}|{desc.replace('|', '/')}|0")
    agree = not diffs["only_a"] and not diffs["only_b"] and bool(lines)
    out = {"doc": sha, "pages": d.page_count, "agree": agree, "diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines), "placeholders": placeholders,
           "duplicates_other_name": dup}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": agree, "a": len(a), "b": len(b), "numbers": len(seen),
                      "only_a": diffs["only_a"][:5], "only_b": diffs["only_b"][:5], "placeholders": len(placeholders),
                      "dup": dup[:5]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
