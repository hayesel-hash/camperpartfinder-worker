"""NBK 2023 catalogue cards -> aftermarket assertions (RV appliance brands only)."""
import hashlib, json, re, sys, pymupdf

BRANDS = [(r"DOMET-?IC", "Dometic"), (r"DUO[ -]?THERM", "Duo-Therm"), (r"ATW(?:OOD)?", "Atwood"),
          (r"SUB(?:URBAN)?", "Suburban"), (r"COLEMAN", "Coleman"), (r"NOR(?:COLD)?", "Norcold"),
          (r"HYDRO[ -]?FLAME", "Hydro Flame"), (r"LIP(?:PERT)?", "Lippert")]
OTHER = re.compile(r"^(FAS(?:CO)?|FAS-CO|CENTURY|AO SMITH|A\.O\. SMITH|PACK-?ARD|DAYTON|EMERSON|MARS|REVCOR|GE|REFERENCE)\b")
NUM = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{2,24}$")

def split_equiv(raw):
    out, brand = [], None
    for tok in [t.strip() for t in re.split(r",\s*", raw) if t.strip()]:
        tok = re.sub(r"^EQUIVALENT\s+", "", tok)
        m = re.match(r"^([A-Z][A-Z .\-]*?)\s*[/ ]\s*([A-Z0-9][A-Z0-9.\-]*)$", tok)
        if m and not NUM.match(tok.replace(" ", "")):
            b, num = m.group(1).strip(), m.group(2)
            brand = next((name for pat, name in BRANDS if re.fullmatch(pat, b)), None)
            if brand is None and not OTHER.match(b):
                brand = None
            if brand: out.append((brand, num))
            continue
        if brand and NUM.match(tok):
            out.append((brand, tok))
        else:
            brand = None if not NUM.match(tok) else brand
    return out

def cards(doc):
    for pi in range(doc.page_count):
        bl = [(b[0], b[1], b[2], b[3], " ".join(b[4].split())) for b in doc[pi].get_text("blocks") if b[4].strip()]
        for x0, y0, x1, y1, t in bl:
            m = re.fullmatch(r"ITEM # (NBK-\d{4,6}[A-Z]?)", t)
            if not m: continue
            eq = [b for b in bl if x0 + 10 <= b[0] <= x0 + 45 and y0 + 5 <= b[1] <= y0 + 20 and not b[4].startswith("EQUIV. TO")]
            ds = [b for b in bl if abs(b[0] - x0) <= 8 and y0 - 30 <= b[3] <= y0 + 1 and b[1] < y0]
            if len(eq) != 1: continue
            yield pi + 1, m.group(1), eq[0][4], (ds[-1][4] if ds else "")

if __name__ == "__main__":
    pdf = sys.argv[1]; sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    rows, seen = [], set()
    for page, item, eq, desc in cards(pymupdf.open(pdf)):
        for brand, num in split_equiv(eq.upper()):
            key = f"p{page}:{item}:{brand}:{num}"
            if key in seen: continue
            seen.add(key)
            rows.append({"page": page, "item": item, "desc": desc, "brand": brand, "oem": num,
                         "row_text": f"{item} EQUIV. TO {eq} | {desc}"[:300], "row_key": key})
    json.dump({"sha256": sha, "rows": rows}, open(sys.argv[2], "w"))
    print(sha, len(rows), "assertions;", len({r['item'] for r in rows}), "NBK items")
    for r in rows[:40]: print(r["page"], r["item"], r["brand"], r["oem"], "|", r["desc"][:45])
