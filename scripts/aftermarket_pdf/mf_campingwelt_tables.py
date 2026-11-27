"""Two-pass reader for the MF Campingwelt (Frankana Freiko) "Caravan Spare Parts Catalogue 2021-2022" (German; ChatGPT splits
"MF Campingwelt - Caravan Spare Parts Catalogue 2021-2022 - pp NNN-MMM.pdf").

Tables under the product photos: "<Pos> | <Bezeichnung> | Hersteller Nr. | Art-Nr." (Art-Nr. = MF / Frankana stock number such as
071/366, never a part). Larry's 27 Nov decision on distributor catalogues: the maker's number printed under the maker's name is
that maker's part. This reader only reads pages whose running head (top 40 pt, "Fiamma | Markisen", "Markisen | Thule") names a
manufacturer passed in with --makers (exact, case-insensitive); category heads ("Toiletten | Wasser", "Heizen | Gas",
"Fahrradtraeger") name no maker and are counted as unread pages.
Row rule: a baseline with one maker-number token in the Hersteller Nr. column and an Art-Nr. token right of it; description = the
words between the Pos callout and the Hersteller Nr. column; a description-only line directly under a row continues it.
Numbers ending in "-" (Fiamma's no-colour suffix, cut-off prints) and numbers printed with two descriptions are not loaded.
Pass A pymupdf words, pass B pdfplumber words, each grouped by its own baseline rule; only rows both give identically are kept.
usage: python3 -I mf_campingwelt_tables.py <pdf> <out.json> --makers Fiamma,Thule [--headings]
(--headings: on pages without a maker running head, read tables whose nearest heading names exactly one of the makers)
"""
import hashlib, json, re, sys
import pdfplumber, pymupdf

NUM = re.compile(r"^(?=[A-Za-z0-9./-]*\d)[A-Za-z0-9][A-Za-z0-9./-]{3,39}$")
ART = re.compile(r"^\d{3}/\d{2,4}(-\d{1,2})?$")
POS = re.compile(r"^\d{1,2}[a-z]?$")


def sp(s):
    return " ".join(s.split())


def lines_of(words, tol):
    """words: (x0, top, x1, bottom, text) -> list of (top, bottom, [words sorted by x])."""
    out = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        c = (w[1] + w[3]) / 2
        if out and abs(out[-1][0] - c) <= tol:
            out[-1][2].append(w)
        else:
            out.append([c, w[3], [w]])
    return [(min(x[1] for x in l[2]), max(x[3] for x in l[2]), sorted(l[2], key=lambda w: w[0])) for l in out]


def read_tables(words, tol, maker_at):
    heads = []
    for w in words:
        if w[4] == "Hersteller":
            art = [v for v in words if v[4] == "Art-Nr." and abs(v[1] - w[1]) < 3 and 0 < v[0] - w[0] < 120]
            if art:
                heads.append((w, min(art, key=lambda v: v[0])))
    heads.sort(key=lambda h: (round(h[0][1]), h[0][0]))
    rows = []
    for w, a in heads:
        mk = maker_at(w[0], w[1])
        if not mk:
            continue
        same_band = [h for h in heads if abs(h[0][1] - w[1]) < 3]
        left_heads = [h[1][2] for h in same_band if h[1][2] < w[0]]
        x_left = max(left_heads) + 4 if left_heads else 0
        x_her = w[0] - 6
        x_art = a[0] - 6
        right_heads = [h[0][0] for h in same_band if h[0][0] > a[0]]
        x_right = min(right_heads) - 60 if right_heads else 10_000
        hdr_line = [v[4] for v in words if abs((v[1] + v[3]) / 2 - (w[1] + w[3]) / 2) < 3 and x_left <= v[0] < x_right]
        extra = [t for t in hdr_line if t not in ("Hersteller", "Nr.", "Art-Nr.")]
        below = [v for v in words if v[1] > w[3] + 0.5 and x_left <= v[0] < x_right]
        cur, last_bottom, orphan = None, w[3], False
        for top, bottom, ws in lines_of(below, tol):
            if top - last_bottom > 14:
                break
            if orphan and top - last_bottom >= 3:
                orphan = False
            her = [v[4] for v in ws if x_her <= v[0] < x_art]
            art = [v[4] for v in ws if v[0] >= x_art]
            desc = [v[4] for v in ws if v[0] < x_her]
            if desc and POS.match(desc[0]):
                desc = desc[1:]
            if len(her) == 1 and art and ART.match(art[0]):
                ok = (not extra and not orphan and desc and desc[0][:1].isupper() and len(art) == 1)
                cur = [her[0] if ok else "?", desc, mk]
                rows.append(cur)
                orphan = False
            elif not her and not art and desc and cur is not None and top - last_bottom < 3:
                cur[1] = cur[1] + desc
            elif her or art:
                cur = None
                rows.append(["?", her + desc, mk])  # a row this rule cannot read
                orphan = False
            else:
                # a description-only line not continuing a row: if a row follows directly, its cell is
                # vertically centred / wrapped above the number -> that row is not read
                cur = None
                orphan = True
            last_bottom = bottom
    return [(n, sp(" ".join(d)), m) for n, d, m in rows]


def pass_a(page, maker_at):
    return read_tables([w[:5] for w in page.get_text("words")], 2.0, maker_at)


def pass_b(ppage, maker_at):
    return read_tables([(w["x0"], w["top"], w["x1"], w["bottom"], w["text"]) for w in ppage.extract_words(x_tolerance=1.5)], 2.5,
                       maker_at)


def heading_maker(page, makers):
    """Tables on pages without a maker running head: the maker must be named as a word in the nearest >= 12 pt heading
    above the table header (same column: heading starts within 300 pt left of the header and ends right of the table's
    left edge). "Ersatzteile fuer Truma Mover SE" -> Truma; "Ersatzteile Carry-Bike" (a product name only) -> nothing."""
    heads = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = sp(" ".join(s["text"] for s in l["spans"]))
            if t and max(s["size"] for s in l["spans"]) >= 12 and l["bbox"][1] > 40:
                heads.append((l["bbox"], t))

    def at(x, y):
        cand = [(bb, t) for bb, t in heads if bb[3] <= y + 1 and y - bb[3] < 320 and bb[0] <= x and x - bb[0] < 330]
        if not cand:
            return None
        bb, t = max(cand, key=lambda c: c[0][3])
        hit = [m for m in makers if re.search(r"(?<![A-Za-z])" + re.escape(m) + r"(?![A-Za-z])", t, re.I)]
        return hit[0] if len(hit) == 1 else None
    return at


def running_head(page):
    return sp(" ".join(s["text"] for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
                       if s["bbox"][1] < 40 and s["text"].strip()))


def main(pdf, outp, *opts):
    makers = [m.strip() for m in opts[opts.index("--makers") + 1].split(",")]
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    per_maker, diffs, unread_pages, skipped = {}, [], {}, []
    for i, p in enumerate(d):
        if "Hersteller" not in p.get_text():
            continue
        head = running_head(p)
        parts = [x.strip().lower() for x in head.split("|")]
        mk = [m for m in makers if m.lower() in parts]
        if len(mk) == 1:
            maker_at = lambda x, y, m=mk[0]: m
        elif "--headings" in opts:
            maker_at = heading_maker(p, makers)
        else:
            unread_pages[i + 1] = head
            continue
        a, b = pass_a(p, maker_at), pass_b(pl.pages[i], maker_at)
        if not a and not b:
            unread_pages[i + 1] = head
            continue
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:6], "only_b": [x for x in b if x not in a][:6]})
        for n, desc, m in a:
            if (n, desc, m) not in b or n == "?" or not NUM.match(n) or n.endswith("-") or not desc:
                if n != "?" and (n, desc, m) in b:
                    skipped.append([i + 1, n, desc])
                continue
            per_maker.setdefault(m, []).append((i + 1, n, desc))
    out = {"doc": sha, "pages": d.page_count, "unread_pages": unread_pages, "diffs": diffs, "skipped": skipped, "makers": {}}
    for m, rows in per_maker.items():
        by = {}
        for pg, n, desc in rows:
            by.setdefault(n, set()).add(desc)
        conflicts = {n: sorted(v) for n, v in by.items() if len(v) > 1}
        seen, lines, k = set(), [], 0
        for pg, n, desc in rows:
            if n in seen or n in conflicts:
                continue
            seen.add(n); k += 1
            lines.append(f"{pg}|{k}|{n}|{desc.replace('|', '/')}|0")
        out["makers"][m] = {"numbers": len(seen), "conflicts": conflicts, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"doc": sha[:16], "makers": {m: {"numbers": v["numbers"], "conflicts": len(v["conflicts"])} for m, v in out["makers"].items()},
                      "diff_pages": [x["page"] for x in diffs], "diffs": diffs[:4], "skipped": len(skipped),
                      "unread_pages": len(unread_pages)}, ensure_ascii=False)[:3500])


if __name__ == "__main__":
    main(*sys.argv[1:])
