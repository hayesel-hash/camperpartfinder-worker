"""Two-pass reader for BAL (Norco) parts-identification sheets: callout blocks of 'NUMBER' + label lines.
Pass A: text order (number line, then label lines up to the next number). Pass B: text blocks (a block whose first
line starts with a number). Rows kept only where both agree. 'NUMBER - label' and 'NUMBER  size' on one line are
handled; a size-only label takes the nearest heading above (e.g. COMPRESSION ROLLER BLOCK, COUPLING NUTS).
usage: python3 -I bal_callouts.py <pdf> <out.json> [first_page]"""
import hashlib, json, re, sys
import pymupdf
NUM = re.compile(r"^([A-Z]?\d{5,8}[A-Z]?)(?:\s*-\s*|\s{2,}|\s+)?(.*)$")
STOP = re.compile(r"PARTS\s+IDENTIFICATION|^ACCU-SLIDE HYBRID|^EXACT-SLIDE|^APPLICABLE TO|^RV MANUFACTURED|^OF SEPTEMBER|^THE COUNT|^\(AKA")
HEAD = re.compile(r"^[A-Z][A-Z /&,-]{6,}$")

def clean(s): return " ".join(s.replace("”", '"').replace("“", '"').split())

def is_num(l):
    m = NUM.match(l)
    return bool(m) and bool(re.match(r"^[A-Z]?\d{5,8}[A-Z]?$", m.group(1)))

def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, head = {}, ""
    for i, l in enumerate(L):
        if not is_num(l):
            if HEAD.match(l) and not STOP.search(l): head = l
            continue
        m = NUM.match(l); num, rest = m.group(1), clean(m.group(2) or "")
        desc = []
        if rest and not re.match(r"^[\d./\"' X]+$", rest): desc.append(rest)
        j = i + 1
        while j < len(L) and not is_num(L[j]) and not STOP.search(L[j]) and L[j] not in ("COMPRESSION ROLLER BLOCK", "COUPLING NUTS", "FOR FLUSH FLOOR") and len(desc) < 4:
            desc.append(clean(L[j])); j += 1
        if rest and re.match(r"^[\d./\"' X]+$", rest):
            d = (head.title() + " " + rest).strip()
        else:
            d = " ".join(desc)
        if d: rows.setdefault(num, d)
    return rows

def pass_b(page):
    """Spatial: label lines directly under a callout number (left edges within 40pt, gaps under 16pt)."""
    L = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = clean("".join(sp["text"] for sp in ln["spans"]))
            if t: L.append((ln["bbox"][0], ln["bbox"][1], ln["bbox"][3], t))
    rows = {}
    for x0, y0, y1, t in L:
        if not is_num(t): continue
        m = NUM.match(t); num, rest = m.group(1), clean(m.group(2) or "")
        if rest and re.match(r"^[\d./\"' X]+$", rest):
            continue  # size-only rows: label comes from a heading, pass A handles them; checked separately
        desc = [rest] if rest else []
        cur = y1
        for x0b, y0b, y1b, tb in sorted(L, key=lambda z: z[1]):
            if y0b < cur - 1 or abs(x0b - x0) > 40 or y0b - cur > 16: continue
            if is_num(tb) or STOP.search(tb) or HEAD.match(tb) and desc and tb.isupper() and len(desc) >= 1 and tb in ("COMPRESSION ROLLER BLOCK", "COUPLING NUTS"): break
            desc.append(tb); cur = y1b
            if len(desc) >= 4: break
        if desc: rows.setdefault(num, " ".join(desc))
    return rows

def main(pdf, outp, first=1):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    keep, dis = {}, []
    for i in range(int(first) - 1, d.page_count):
        a, b = pass_a(d[i]), pass_b(d[i])
        for num, da in a.items():
            db = b.get(num)
            if db and (db == da or db.startswith(da) or da.startswith(db)):
                keep.setdefault(num, {"page": i + 1, "number": num, "desc": da if len(da) <= len(db) else db})
            elif db is None and re.match(r"^(Compression Roller Block|Coupling Nuts) [\d.]", da):
                keep.setdefault(num, {"page": i + 1, "number": num, "desc": da, "size_row": True})
            else:
                dis.append({"page": i + 1, "number": num, "a": da, "b": db})
    json.dump({"doc": sha, "pages": d.page_count, "rows": list(keep.values()), "disagree": dis}, open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "disagree": len(dis)}))
    for r in keep.values(): print("  ", r["page"], r["number"], "|", r["desc"])
    for x in dis: print("  DIS", x)

if __name__ == "__main__":
    main(*sys.argv[1:4])
