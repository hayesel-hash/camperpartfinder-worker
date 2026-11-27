"""Two-pass reader for the Espar AIRTRONIC D2/D4 "Installation, Troubleshooting & Parts Manual" (P/N 610-103-0901,
November 2001; Espar Products Inc., "a member of the Worldwide Eberspächer Group of Companies").

Parts list pages (printed "Parts List AIRTRONIC D2/D4", pdf pp 31, 33, 34):
  Ref. No. | Description | [variant cell: 12V / 24V, "ø 60", "2 mm", "20 amp", '1/4" NPT'] | Part Number | one bullet
  column per heater model (the rotated "Model #" header is drawn, not text, so applicability is NOT stored).
  "*" before a Ref = optional feature (legend printed on p34). Rows without a Ref (operator's tape, manual, fault code
  retrieval device) are parts too. "• short harness" in the description column is a sub-item of the row above
  ("Main harness: short harness"). Ref "2a" has a blank description cell under item 2 -> takes item 2's description.
Cover page (pdf p1): "For Heater Models" list, "AIRTRONIC D2 - 12 volt" + heater number.

Numbers are printed with spaces. Larry's 27 Nov decision: store them in the dotted form Eberspächer uses in its own
lists: 12 digits "25 2069 99 06 00" -> 25.2069.99.0600; any other spaced shape -> dots in place of the spaces
("152 00 139" -> 152.00.139, "CA0 00 019" -> CA0.00.019, "625 101 0102" -> 625.101.0102). The printed form is kept
in the description ("(printed 25 2069 99 06 00)").

Pass A: pymupdf text lines in reading order (a Ref line opens an item; variant lines and number lines follow).
Pass B: pdfplumber words grouped by baseline; columns from the "Description" header word; the number is the longest
token suffix of the line (left of the bullet columns) that has a number shape, the rest splits into description and
variant by the gap between them.
A number printed under two different descriptions (20 1280 09 01 03: "Grommet" and "Fuel screen") is not loaded.
usage: python3 -I espar_airtronic_parts_list.py <pdf> <out.json> "<section label>"
"""
import hashlib, json, re, sys
import pdfplumber, pymupdf

PARTS_PAGES = (31, 33, 34)   # 1-based
COVER_PAGE = 1
NUM = re.compile(r"^(?:\d{2} \d{4} \d{2} \d{2} \d{2}|\d{3} \d{2} \d{3}|[A-Z]{2}\d \d{2} \d{3}|\d{3} \d{3} \d{4})$")
REF = re.compile(r"^(\*?)\s?(\d{1,2}[a-z]?)$")
VOLT = re.compile(r"^(12V|24V)$")
VAR = re.compile(r"^(?:12V|24V|ø ?\d[\d\-]*(?: mm)?|\d+(?:\.\d+)? mm|\d+ amp|\d/\d[”\"'] ?NPT)$")
COVER = re.compile(r"^AIRTRONIC\s+(D\d)\s*-\s*(\d+)\s*volt$", re.I)


def sp(s):
    return " ".join(s.split())


def dotted(printed):
    p = printed.split()
    if len(p) == 5 and all(x.isdigit() for x in p):
        return f"{p[0]}.{p[1]}.{p[2]}.{p[3]}{p[4]}"
    return ".".join(p)


class Items:
    """Shared table semantics; both passes feed it events in reading order."""

    def __init__(self):
        self.rows, self.item, self.var = [], None, None

    def ref(self, star, ref):
        self.item = {"ref": ref, "star": bool(star), "desc": "", "cur": None, "n": 0}
        self.var = None

    def text(self, t):
        if t.startswith("• "):
            if self.item:
                self.item["cur"] = self.item["desc"] + ": " + t[2:]
            return
        if self.item is None or self.item["n"] > 0:   # a row with no Ref after a numbered item = a new item
            self.ref("", "")
        self.item["desc"] = sp(self.item["desc"] + " " + t)

    def variant(self, v):
        self.var = sp(v)

    def number(self, printed, var=None):
        it = self.item
        if it is None:
            return
        v = sp(var) if var else self.var
        self.rows.append({"ref": ("*" if it["star"] else "") + it["ref"], "desc": it["cur"] or it["desc"], "variant": v or "",
                          "printed": printed})
        it["n"] += 1
        self.var = None


def finish(rows):
    by_ref = {}
    for r in rows:
        base = re.sub(r"[a-z]$", "", r["ref"].lstrip("*"))
        if r["desc"] and base not in by_ref:
            by_ref[base] = r["desc"]
    out = []
    for r in rows:
        d = r["desc"]
        m = re.match(r"^\*?(\d+)[a-z]$", r["ref"])
        if not d and m:          # lettered sub-item with a blank description cell (2a under 2)
            d = by_ref.get(m.group(1), "")
        out.append(dict(r, desc=d))
    return out


def pass_a_page(page):
    L = [sp(l) for l in page.get_text().splitlines() if l.strip()]
    it, started = Items(), False
    skip_legend = False
    for t in L:
        if not started:
            started = t.endswith("Part Number") or t == "Number"
            continue
        if t == "•":
            continue
        if t == "*":
            skip_legend = True; continue
        if skip_legend and t == "indicates optional features":
            skip_legend = False; continue
        m = REF.match(t)
        if m:
            it.ref(m.group(1), m.group(2)); continue
        parts = t.split(" ")
        if NUM.match(t):
            it.number(t); continue
        if len(parts) > 1 and VOLT.match(parts[0]) and NUM.match(" ".join(parts[1:])):
            it.number(" ".join(parts[1:]), parts[0]); continue
        if VAR.match(t):
            it.variant(t); continue
        it.text(t)
    return finish(it.rows)


def lines_b(ppage):
    ws = ppage.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["size"])
    rows = {}
    for w in ws:
        key = round(w["bottom"] / 2.5)
        rows.setdefault(key, []).append(w)
    return [sorted(rows[k], key=lambda w: w["x0"]) for k in sorted(rows)]


def pass_b_page(ppage):
    L = lines_b(ppage)
    hdr = next((ln for ln in L if any(w["text"] == "Description" for w in ln) and any(w["text"] == "Part" for w in ln)), None)
    if hdr is None:
        return []
    dx = next(w["x0"] for w in hdr if w["text"] == "Description")
    hy = hdr[0]["bottom"]
    it = Items()
    for ln in L:
        if ln[0]["bottom"] <= hy + 1:
            continue
        ws = [w for w in ln if not (w["text"] == "•" and w["x0"] > dx + 300)]   # model bullet columns
        if not ws:
            continue
        txt = sp(" ".join(w["text"] for w in ws))
        if txt in ("* indicates optional features",):
            continue
        refw = [w for w in ws if w["x1"] < dx - 3]
        rest = [w for w in ws if w["x1"] >= dx - 3]
        if refw:
            m = REF.match(sp(" ".join(w["text"] for w in refw)).replace("* ", "*"))
            if not m:
                return [{"error": "ref cell not understood", "text": txt}]
            it.ref(m.group(1), m.group(2))
        if not rest:
            continue
        num, k = None, None
        for n in (5, 3):
            if len(rest) >= n and NUM.match(" ".join(w["text"] for w in rest[-n:])):
                num, k = " ".join(w["text"] for w in rest[-n:]), len(rest) - n
                break
        pre = rest[:k] if num else rest
        groups = []
        for w in pre:
            if groups and w["x0"] - groups[-1][-1]["x1"] <= 12:
                groups[-1].append(w)
            else:
                groups.append([w])
        desc = var = None
        for g in groups:
            gt = sp(" ".join(w["text"] for w in g))
            if g[0]["x0"] < dx + 20 and desc is None:
                desc = gt
            else:
                var = sp((var or "") + " " + gt)
        if desc:
            it.text(desc)
        if num:
            it.number(num, var)
        elif var:
            it.variant(var)
    return finish(it.rows)


def cover_rows(text):
    L = [sp(l) for l in text.splitlines() if l.strip()]
    out = []
    for i, t in enumerate(L[:-1]):
        m = COVER.match(t)
        if m and NUM.match(L[i + 1]):
            out.append({"ref": "", "desc": f"AIRTRONIC {m.group(1).upper()} heater, {m.group(2)} volt", "variant": "", "printed": L[i + 1]})
    return out


def cover_rows_b(ppage):
    out = []
    for ln in lines_b(ppage):
        t = sp(" ".join(w["text"] for w in ln))
        m = re.match(r"^AIRTRONIC (D\d) - (\d+) volt (\d{2} \d{4} \d{2} \d{2} \d{2})(?: [A-Z][a-z]+ \d{4})?$", t, re.I)
        if m:
            out.append({"ref": "", "desc": f"AIRTRONIC {m.group(1).upper()} heater, {m.group(2)} volt", "variant": "", "printed": m.group(3)})
    return out


def name(r):
    d = r["desc"] + (", " + r["variant"] if r["variant"] else "")
    if r["ref"].startswith("*"):
        d += " (optional feature)"
    return f"{d} (printed {r['printed']})"


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, unread = [], [], []
    key = lambda r: (r["ref"], r["printed"], "".join(r["desc"].split()).casefold(), "".join(r["variant"].split()).casefold())
    pages = [(COVER_PAGE, cover_rows(d[COVER_PAGE - 1].get_text()), cover_rows_b(pl.pages[COVER_PAGE - 1]))]
    pages += [(p, pass_a_page(d[p - 1]), pass_b_page(pl.pages[p - 1])) for p in PARTS_PAGES]
    for p, a, b in pages:
        ka, kb = [key(r) for r in a], [key(r) for r in b]
        if sorted(ka) != sorted(kb):
            diffs.append({"page": p, "only_a": [r for r in a if key(r) not in kb][:6], "only_b": [r for r in b if key(r) not in ka][:6]})
        keep += [(p, r) for r in a if key(r) in kb]
        seen = {r["printed"] for r in a} | {r["printed"] for r in b}
        txt = " ".join(d[p - 1].get_text().split())
        for m in re.finditer(r"(?<![\d.])(\d{2} \d{4} \d{2} \d{2} \d{2}|\d{3} \d{2} \d{3}|[A-Z]{2}\d \d{2} \d{3}|\d{3} \d{3} \d{4})(?![\d.])", txt):
            if m.group(1) not in seen and not txt[max(0, m.start() - 6):m.start()].endswith("P/N: "):
                unread.append({"page": p, "printed": m.group(1)})
    names = {}
    for p, r in keep:
        names.setdefault(dotted(r["printed"]), set()).add(name(r).split(" (printed")[0])
    conflict = {n for n, v in names.items() if len(v) > 1}
    lines, seen, per_page = [], set(), {}
    for p, r in keep:
        num = dotted(r["printed"])
        if num in conflict or num in seen:
            continue
        seen.add(num)
        per_page[p] = per_page.get(p, 0) + 1
        sx = "1" if p == COVER_PAGE else "0"
        lines.append(f"{p}|{per_page[p]}|{num}|{name(r).replace('|', '/')}|{sx}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": {"0": section, "1": section + " — heater models (cover page)"},
           "rows": "\n".join(lines), "conflicts": [{"number": n, "names": sorted(names[n])} for n in sorted(conflict)],
           "unread": unread}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(keep), "numbers": len(seen), "diffs": diffs[:3],
                      "conflicts": out["conflicts"], "unread": unread[:10]}, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
