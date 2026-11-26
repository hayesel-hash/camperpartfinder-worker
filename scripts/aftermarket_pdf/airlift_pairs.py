"""Two-pass reader for the Air Lift 'Replacement Air Springs' guide (kit -> replacement air spring).
usage: python3 -I airlift_pairs.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf
N = re.compile(r"^\d{5}$")

def pass_a(page):
    toks = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    pairs, i, section = [], 0, "AIR LIFT"
    while i < len(toks):
        t = toks[i]
        if t.startswith("AIR LIFT PROSERIES"): section = "AIR LIFT PROSERIES"
        if N.match(t) and i + 1 < len(toks) and N.match(toks[i + 1]):
            pairs.append((t, toks[i + 1])); i += 2; continue
        i += 1
    return pairs

def pass_b(page):
    words = [(w[0], (w[1] + w[3]) / 2, w[4]) for w in page.get_text("words") if N.match(w[4])]
    rows = {}
    for x, y, t in words:
        rows.setdefault(round(y / 3), []).append((x, t))
    pairs = []
    for y in sorted(rows):
        ws = sorted(rows[y])
        if len(ws) % 2:
            raise SystemExit(f"odd row at y~{y*3}: {ws}")
        for k in range(0, len(ws), 2):
            pairs.append((ws[k][1], ws[k + 1][1]))
    return pairs

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    p = pymupdf.open(pdf)[0]
    a, b = pass_a(p), pass_b(p)
    from collections import Counter
    agree = Counter(a) == Counter(b)
    # section: ProSeries table is the lower block on the page
    words = {w[4]: w[1] for w in p.get_text("words")}
    pro_y = min(w[1] for w in p.get_text("words") if w[4] == "PROSERIES")
    out = []
    seen = set()
    for kit, spring in a:
        if (kit, spring) in seen: continue
        seen.add((kit, spring))
        ys = [w[1] for w in p.get_text("words") if w[4] == kit]
        out.append({"kit": kit, "spring": spring, "section": "ProSeries" if ys and min(ys) > pro_y else "Air Lift"})
    json.dump({"sha256": sha, "agree": agree, "pairs_a": len(a), "pairs_b": len(b), "rows": out}, open(outp, "w"), indent=1)
    print(json.dumps({"sha16": sha[:16], "agree": agree, "a": len(a), "b": len(b), "unique": len(out),
                      "same_number": sum(1 for r in out if r["kit"] == r["spring"]),
                      "kit_with_two_springs": [k for k, v in Counter(r["kit"] for r in out).items() if v > 1]}))

if __name__ == "__main__":
    main(*sys.argv[1:3])
