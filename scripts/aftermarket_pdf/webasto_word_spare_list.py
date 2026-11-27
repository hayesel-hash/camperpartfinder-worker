"""Reader for Webasto North-America bilingual (English / French) Word spare parts lists, e.g. "Air Top 2000 STC Spare Parts
List": ruled tables "Pos | [Gas 12V | Diesel 12V | Diesel 24V (X marks)] | Part No. | Description | Notes" or
"Pos. Item | Part Number/Référence | Description/Désignation | (size) | Remarks/Remarques"; continuation pages repeat no
header (the previous page's columns are reused when the column count matches).

Extraction: pymupdf find_tables cells. Check: every Webasto-number-like token (6-8 digits + optional letter) in the page's
text layer must be either a row's part number or sit inside a Notes / Description cell (e.g. "Alternate part 35320A",
"order adapter 5001493"); anything else is reported as unread and the document is not marked agreed. Page images are
checked by hand.
Description = English part of the Description cell (text before " / "), plus the size cell and the English part of the
Notes cell in parentheses, plus " [models: ...]" when the X marks do not cover every version column.
Output: supplied-documents JSON (rows page|n|number|description|section).
usage: python3 -I webasto_word_spare_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^\d{6,8}[A-Z]?$")
TOK = re.compile(r"(?<![\w.])\d{6,8}[A-Z]?(?![\w.])")


def norm(s):
    return " ".join((s or "").split())


def english(s):
    s = norm(s)
    return s.split(" / ")[0].strip() if " / " in s else s


def header_map(texts, boxes):
    """header row -> {role: x-centre} plus version columns [(x-centre, name)]"""
    lab = [(norm(t), b) for t, b in zip(texts, boxes) if t and norm(t) and b]
    low = [(t.lower(), (b[0] + b[2]) / 2, t) for t, b in lab]
    role = {}
    for l, cx, t in low:
        if l.startswith("pos"):
            role["pos"] = cx
        elif l.startswith("part no") or l.startswith("part number"):
            role["part"] = cx
        elif l.startswith("description"):
            role["desc"] = cx
        elif l.startswith("notes") or l.startswith("remarks"):
            role["notes"] = cx
    if "part" not in role or "desc" not in role:
        return None
    models = [(cx, t) for l, cx, t in low if role.get("pos", -1) < cx < role["part"] and not l.startswith("pos")]
    return {"role": role, "models": models}


def cells_of(t):
    """-> [(texts, boxes)] per table row (texts from extract, boxes from the row's cells)"""
    data = t.extract()
    return [(data[k], [c for c in r.cells]) for k, r in enumerate(t.rows) if k < len(data)]


def assign(texts, boxes, hm):
    """map each filled cell to the nearest header column by x-centre"""
    cols = [(cx, ("role", r)) for r, cx in hm["role"].items()] + [(cx, ("model", n)) for cx, n in hm["models"]]
    out = {}
    for t, b in zip(texts, boxes):
        if not t or not norm(t) or not b:
            continue
        cx = (b[0] + b[2]) / 2
        key = min(cols, key=lambda c: abs(c[0] - cx))[1]
        out.setdefault(key, []).append(norm(t))
    return out


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    if not d.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, sections, unread, hm, section = [], {}, [], None, ""
    for i, p in enumerate(d):
        text = p.get_text()
        # section = the page's chapter heading (largest horizontal type containing " / ", e.g. "Fuel Supply / Système
        # carburant"); continuation pages keep the previous one
        big = [(sp["size"], norm(sp["text"])) for b in p.get_text("dict")["blocks"] for ln in b.get("lines", [])
               if abs(ln["dir"][0] - 1) < 0.01 for sp in ln["spans"] if " / " in sp["text"]]
        if big:
            top = max(big)[0]
            if top >= 11:
                section = english(next(t for z, t in big if z == top))
        found, explained = [], set()
        for t in p.find_tables().tables:
            rows_c = cells_of(t)
            if not rows_c:
                continue
            h = header_map(*rows_c[0])
            if h:
                hm, body = h, rows_c[1:]
            elif hm:
                body = rows_c
            else:
                continue
            for texts, boxes in body:
                a = assign(texts, boxes, hm)
                num = " ".join(a.get(("role", "part"), []))
                cells = " ".join(norm(c) for c in texts if c)
                if not NUM.match(num):
                    explained |= set(TOK.findall(cells)); continue
                descs = a.get(("role", "desc"), [])
                desc = english(descs[0]) if descs else ""
                extra = [x for x in descs[1:]]
                note = " ".join(english(x) for x in a.get(("role", "notes"), []))
                if not desc:
                    continue
                full = " ".join([desc] + extra) + (f" ({note})" if note else "")
                if hm["models"]:
                    on = [n for cx, n in hm["models"] if "X" in [v.upper() for v in a.get(("model", n), [])]]
                    if len(on) != len(hm["models"]):
                        full += " [models: " + ", ".join(on) + "]"
                found.append((num, full))
                explained |= set(TOK.findall(cells.replace(num, "", 1)))
        if not found:
            continue
        if section not in sections.values():
            sections[str(len(sections) + 1)] = section
        code = next(k for k, v in sections.items() if v == section)
        nums = {n for n, _ in found}
        # a number inside running text (footnote "only available with 9005942A mounting kit") is not a row
        prose = {t for l in text.splitlines() if len(l.split()) > 3 for t in TOK.findall(l)}
        unread += [{"page": i + 1, "number": t} for t in sorted(set(TOK.findall(text)))
                   if t not in nums and t not in explained and t not in prose]
        rows += [(i + 1, n, num, desc, code) for n, (num, desc) in enumerate(found, 1)]
    seen, lines = set(), []
    for pg, n, num, desc, code in rows:
        if num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{code}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines) and not unread, "rows_total": len(rows),
           "numbers": len(seen), "unread": unread, "sections": sections, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "sections": sections, "unread": unread[:8]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
