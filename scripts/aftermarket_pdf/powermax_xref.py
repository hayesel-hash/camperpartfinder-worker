"""Reader for the PowerMax converter Cross Reference chart. Pass B: word positions, columns from header word centres,
rows by baseline. Pass A: every model token in the text layer must be used exactly once by pass B (multiset check).
usage: python3 -I powermax_xref.py <pdf> <out.json>"""
import collections, hashlib, json, re, sys
import pymupdf
TOK = re.compile(r"^(?=.*\d)((PM3|PPC|PCW|PMTS|WF|DLS|PD|PC|T|ITS|ATS)-?[0-9A-Za-z/-]*|\d{4}|PD\d{4}[0-9/]*)$")
SECTIONS = [(140, 300, "12V Deck Mount"), (305, 400, "Power Center Replacement Converter"),
            (400, 545, "Power Center"), (690, 735, "Transfer Switch")]

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    p = pymupdf.open(pdf)[0]
    W = p.get_text("words")
    heads = {"PowerMax": None, "WFCO": None, "IOTA": None, "Progressive": None, "Parallax": None, "Engineering": None}
    for w in W:
        if w[4] in heads and w[1] < 140: heads[w[4]] = (w[0] + w[2]) / 2
    names = {"PowerMax": "PowerMax", "WFCO": "WFCO", "IOTA": "IOTA", "Progressive": "Progressive Dynamics", "Parallax": "Parallax", "Engineering": "Todd Engineering"}
    centres = sorted((c, names[k]) for k, c in heads.items())
    bounds = [(-1, (centres[0][0] + centres[1][0]) / 2, centres[0][1])]
    for i in range(1, len(centres)):
        lo = (centres[i - 1][0] + centres[i][0]) / 2
        hi = (centres[i][0] + centres[i + 1][0]) / 2 if i + 1 < len(centres) else 999
        bounds.append((lo, hi, centres[i][1]))
    rows = collections.defaultdict(lambda: collections.defaultdict(list))
    used = []
    for x0, y0, x1, y1, t, *_ in W:
        if y0 < 145 or x0 < 110: continue
        if t in ("/",): continue
        if not TOK.match(t): continue
        xc = (x0 + x1) / 2
        col = next(b[2] for b in bounds if b[0] <= xc < b[1])
        rows[round(y0 / 6)][col].append(t); used.append(t)
    textual = [l.strip() for l in p.get_text().splitlines() if l.strip()]
    toks = []
    for l in textual:
        for part in l.split(" / "):
            part = part.strip()
            if TOK.match(part): toks.append(part)
    multiset_ok = collections.Counter(toks) == collections.Counter(used)
    out = []
    for y in sorted(rows):
        r = rows[y]
        if "PowerMax" not in r: continue
        pm = r["PowerMax"][0]
        sec = next((s for lo, hi, s in SECTIONS if lo <= y * 6 <= hi), "")
        for brand, vals in r.items():
            if brand == "PowerMax": continue
            for v in vals:
                out.append({"powermax": pm, "brand": brand, "model": v, "section": sec, "row_y": y,
                            "row_text": " | ".join(f"{b}: {' / '.join(vs)}" for b, vs in r.items())})
    json.dump({"doc": sha, "multiset_ok": multiset_ok, "only_text": list((collections.Counter(toks) - collections.Counter(used)).elements()),
               "only_pos": list((collections.Counter(used) - collections.Counter(toks)).elements()), "rows": out}, open(outp, "w"), indent=1)
    print(json.dumps({"sha16": sha[:16], "assertions": len(out), "multiset_ok": multiset_ok}))
    for o in out: print("  ", o["section"], "|", o["powermax"], "->", o["brand"], o["model"])

if __name__ == "__main__":
    main(*sys.argv[1:3])
