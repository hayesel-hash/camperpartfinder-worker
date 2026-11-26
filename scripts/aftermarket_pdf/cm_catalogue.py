"""Two-pass identity reader for the Coleman-Mach 2025 aftermarket catalogue (CM-4040.02).
Pass A: text order, number line [+ profile line] + description line. Pass B: word lines, number at the left of a
line with the profile/description to its right. Only rows both passes find, with the same description, are kept.
Carrier part numbers (99-xxxxx-xx, page 9 conversion table) are not Coleman-Mach parts and are excluded.
usage: python3 -I cm_catalogue.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf
PN = re.compile(r"^(\d{4,5}[A-Z]?-?\d{3,5}[A-Z0-9]?|\d{4}[A-Z]\d{3,5})$")
PROF = re.compile(r"^(Medium|Low|Ultra-Low|Fits All Profiles|Fits [A-Za-z /&-]+ Profiles?)$")
CARRIER = re.compile(r"^99-\d{5}-\d{2}$")
# old thermostat numbers from the THIS #/REPLACES table: their row text describes the new thermostat, so they are not
# read as identities here (they are published through the supersession lane)
EXCLUDE = {"7330G3351", "7330F3852", "7330F3361", "9430-3392", "9430A3392", "9630A3351", "9630A3361", "9630A3371", "9430A3372"}
# page 8 repair-part rows that print only a colour under a section heading
CONTEXT = {"9330A3341": "Digital zone thermostat, 9330/9430 series (repair part only) - Black",
           "8330D3351": "Digital zone thermostat, 8xxx series (repair part only) - White"}

def norm(s): return " ".join(s.replace("’", "'").split())

def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    out = {}
    for i, l in enumerate(L):
        if not PN.match(l) or i + 1 >= len(L): continue
        j = i + 1; prof = ""
        if PROF.match(L[j]): prof = L[j]; j += 1
        if j < len(L) and not PN.match(L[j]) and not PROF.match(L[j]) and len(L[j]) > 3:
            out.setdefault(l, (prof, norm(L[j])))
    return out

def pass_b(page):
    lines = {}
    for x0, y0, x1, y1, w, *_ in page.get_text("words"):
        lines.setdefault(round((y0 + y1) / 2 / 2.5), []).append((x0, x1, w))
    out = {}
    for y in sorted(lines):
        ws = sorted(lines[y])
        for k, (x0, x1, w) in enumerate(ws):
            if not PN.match(w): continue
            rest = []
            for x0b, x1b, wb in ws[k + 1:]:
                if PN.match(wb): break
                rest.append(wb)
            if not rest: continue
            prof = ""
            txt = " ".join(rest)
            m = re.match(r"^(Fits [A-Za-z /&-]+? Profiles?|Ultra-Low|Medium|Low)(?: |$)", txt)
            if m: prof = m.group(1); txt = txt[len(prof):].strip()
            if txt: out.setdefault(w, (prof, norm(txt)))
    return out

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, disagree = [], []
    seen = set(); best = {}
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        for num in a:
            if CARRIER.match(num) or num in EXCLUDE: continue
            if num in b and (b[num][1] == a[num][1] or b[num][1].startswith(a[num][1])):
                prof, desc = a[num]
                desc = CONTEXT.get(num, desc)
                full = desc + (f" ({prof} profile)" if prof in ("Medium", "Low", "Ultra-Low") else f" ({prof.lower()})" if prof.startswith("Fits ") and prof != "Fits All Profiles" else "")
                if num not in best or len(desc) > len(best[num]["core"]):
                    best[num] = {"page": i + 1, "number": num, "desc": full, "core": desc, "profile": prof}
            else:
                disagree.append({"page": i + 1, "number": num, "a": a[num], "b": b.get(num)})
    rows = list(best.values())
    disagree = [x for x in disagree if x["number"] not in best]
    json.dump({"doc": sha, "pages": d.page_count, "rows": rows, "disagree": disagree}, open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "rows": len(rows), "disagree": len(disagree)}))
    for x in disagree: print("  DIS", x)

if __name__ == "__main__":
    main(*sys.argv[1:3])
