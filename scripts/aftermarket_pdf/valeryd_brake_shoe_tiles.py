"""Valeryd 2022 catalogue (Swedish): brake-shoe set and superkit tiles (printed pp 14-18, "BROMSBACKSET").

Each tile caption reads
    Art.Nr.: 4010201A            (Valeryd article number; "XL" = superkit, "SUPERKIT" badge on the tile)
    AL-KO 1635, 1636, 1637       (the brake TYPE(S) the set is for, one or more lines)
    Storlek: 160x35              (shoe size)
Valeryd states it makes these shoes itself (printed p7, "Unik teknologi ... enbart tillgänglig hos VALERYD"), so the
article numbers are Valeryd parts. The brake types are FITMENT (kept in the description only, never a relationship).

Pass A: pymupdf text blocks (one caption per block). Pass B: pdfplumber words, column = x-range under each "Art.Nr.:"
anchor, rows grouped by `top`, stopping at the column's "Storlek:" line. Rows are kept only when both passes give the
same number, fit text and size. Pages without "Art.Nr.:" captions (diagrams, tables) give no rows.

usage: valeryd_brake_shoe_tiles.py <pdf> <out.json> [first_page last_page]   (1-based pdf pages, default all)
"""
import hashlib
import json
import re
import sys

import pdfplumber
import pymupdf

NUM = re.compile(r"^\d{7}(?:A|XL)?$")
sp = lambda s: re.sub(r"\s+", " ", s).strip()


def parse_caption(lines):
    """lines: caption lines starting with 'Art.Nr.: <n>' and ending with 'Storlek: <size>'."""
    if not lines or not lines[0].startswith("Art.Nr.:"):
        return None, "no Art.Nr. line"
    head = sp(lines[0][len("Art.Nr.:"):])
    head = sp(head.replace("SUPERKIT", ""))
    if not NUM.match(head):
        return None, f"number not read: {head!r}"
    fits, size = [], None
    for ln in lines[1:]:
        ln = sp(ln)
        if ln.startswith("Storlek:"):
            size = sp(ln[len("Storlek:"):])
            break
        if ln and ln != "SUPERKIT":
            fits.append(ln)
    if size is None:
        return None, f"{head}: no Storlek line"
    fit = sp(" ".join(fits))
    return {"number": head, "fits": fit, "size": size.upper().replace("X", "x")}, None


def pass_a(page):
    out, held = [], []
    for b in page.get_text("blocks"):
        t = b[4]
        if "Art.Nr.:" not in t:
            continue
        # a block may hold several captions if the layout glued them: split at each Art.Nr.
        parts = re.split(r"(?=Art\.Nr\.:)", t)
        for p in parts:
            if not p.strip().startswith("Art.Nr.:"):
                continue
            r, why = parse_caption([x for x in p.split("\n") if x.strip()])
            (out.append(r) if r else held.append(why))
    return out, held


def pass_b(page):
    # caption text is 9-11 pt; the red "SUPERKIT" badge (~14 pt, drawn twice) is dropped so it cannot glue onto the number
    small = page.filter(lambda o: o.get("object_type") != "char" or o.get("size", 0) < 12)
    words = small.extract_words(x_tolerance=1.5, keep_blank_chars=False)
    anchors = [w for w in words if w["text"] == "Art.Nr.:"]
    out, held = [], []
    for a in anchors:
        right = [b["x0"] for b in anchors if b["x0"] > a["x0"] + 20 and abs(b["top"] - a["top"]) < 3]
        x0, x1 = a["x0"] - 2, (min(right) - 2 if right else a["x0"] + 170)
        col = [w for w in words if x0 <= w["x0"] < x1 and w["top"] >= a["top"] - 3]
        col.sort(key=lambda w: w["top"])
        groups, top = [], None
        for w in col:  # baseline groups first, then left-to-right inside each group
            if top is None or w["top"] - top > 2.5:
                groups.append([w]); top = w["top"]
            else:
                groups[-1].append(w)
        lines = [" ".join(w["text"] for w in sorted(g, key=lambda w: w["x0"])) for g in groups]
        cap = []
        for ln in lines:
            cap.append(ln)
            if ln.startswith("Storlek:"):
                break
            if len(cap) > 1 and ln.startswith("Art.Nr.:"):
                cap = cap[:-1]
                break
        r, why = parse_caption(cap)
        (out.append(r) if r else held.append(why))
    return out, held


def main(pdf, outp, first=1, last=None):
    raw = open(pdf, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    pl = pdfplumber.open(pdf)
    last = last or d.page_count
    key = lambda r: (r["number"], r["fits"].casefold(), r["size"])
    keep, diffs, held = [], [], []
    for i in range(first - 1, last):
        ra, ha = pass_a(d[i])
        rb, hb = pass_b(pl.pages[i])
        ka, kb = [key(r) for r in ra], [key(r) for r in rb]
        if sorted(ka) != sorted(kb):
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb],
                          "only_b": [r for r in rb if key(r) not in ka]})
        keep += [(i + 1, r) for r in ra if key(r) in kb]
        held += [{"page": i + 1, "why": w} for w in sorted(set(ha) | set(hb))]
    descs = {}
    for _, r in keep:
        descs.setdefault(r["number"], set()).add(key(r)[1:])
    conflicts = {n for n, v in descs.items() if len(v) > 1}
    lines, seen, per_page = [], set(), {}
    for pg, r in keep:
        n = r["number"]
        if n in conflicts or n in seen:
            continue
        seen.add(n)
        kind = "Bromsbackset superkit" if n.endswith("XL") else (
            "" if r["fits"].lower().startswith("bromsband") else "Bromsbackset")
        desc = sp(f"{kind} {r['size']}, passar till {r['fits']}") if kind else sp(f"{r['fits']} {r['size']}")
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{n}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines) and not diffs, "page_diffs": diffs,
           "rows_total": len(keep), "numbers": len(seen),
           "sections": {"0": "Valeryd katalog 2022: BROMS - Bromsbackset / Superkit (Valeryd-made brake shoes)"},
           "rows": "\n".join(lines),
           "conflicts": [{"number": n, "variants": sorted(map(list, descs[n]))} for n in sorted(conflicts)],
           "held": held}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "numbers": len(seen), "pages_with_diffs": len(diffs),
                      "diffs": diffs[:4], "conflicts": out["conflicts"], "held": held[:10], "rows_text": out["rows"]},
                     ensure_ascii=False)[:8000])


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], *(int(x) for x in a[2:4]))
