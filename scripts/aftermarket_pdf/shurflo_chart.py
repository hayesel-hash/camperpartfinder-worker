"""Two-pass reader for the Pentair SHURflo RV Pump Conversion Chart (Previous Part Number -> Replaced by).
Pass A: span positions (column by x, row by y), with span colour (blue = aftermarket per the chart's own note).
Pass B: plain text-line order. Rows must agree exactly. Rows with no description (series headings like 200 -> 2088) are skipped.
usage: python3 -I shurflo_chart.py <pdf> <out.json>
"""
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^[0-9]{3,4}(?:-[0-9A-Z]{3,4}){1,2}$")

def pass_a(page):
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                t = s["text"].strip()
                if t:
                    spans.append((round(s["bbox"][1] / 4), s["bbox"][0], t, s["color"]))
    rows = {}
    for y, x, t, c in sorted(spans, key=lambda z: (z[0], z[1])):
        if y * 4 < 285 or y * 4 > 712:
            continue
        r = rows.setdefault(y, {"prev": None, "repl": None, "desc": [], "colors": {}})
        col = "prev" if x < 190 else "repl" if x < 310 else "desc"
        if col == "desc":
            r["desc"].append(t); r["colors"]["desc"] = c
        else:
            r[col] = t; r["colors"][col] = c
    out = []
    for y in sorted(rows):
        r = rows[y]
        desc = "".join((t if t.startswith("\u2122") or i == 0 else " " + t) for i, t in enumerate(r["desc"])).strip()
        if not desc or not r["repl"]:
            continue
        blue = lambda c: c is not None and (c & 0xFF) > 0x99 and ((c >> 16) & 0xFF) < 0x40
        out.append({"y": y, "previous": r["prev"], "replacement": r["repl"], "description": desc,
                    "previous_channel": "aftermarket" if blue(r["colors"].get("prev")) else "oem",
                    "replacement_channel": "aftermarket" if blue(r["colors"].get("repl")) else "oem"})
    return out

def pass_b(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    i = L.index("FRESH WATER PUMPS")
    out, k = [], i
    while k < len(L):
        if NUM.match(L[k]) and k + 2 < len(L) and NUM.match(L[k + 1]) and not NUM.match(L[k + 2]) and not L[k + 2].startswith("8-6-14"):
            out.append((L[k], L[k + 1], L[k + 2])); k += 3
        elif NUM.match(L[k]) and k + 1 < len(L) and not NUM.match(L[k + 1]) and not L[k + 1].startswith("8-6-14") and out and k >= 1 and L[k-1] == out[-1][2]:
            # a row whose previous-number cell is empty (replacement + description only)
            out.append((None, L[k], L[k + 1])); k += 2
        else:
            k += 1
    return out

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); p = d[0]
    a = pass_a(p); b = pass_b(p)
    ka = [(r["previous"], r["replacement"], r["description"]) for r in a]
    agree = ka == b
    rows = [r for r in a if r["previous"]]
    json.dump({"sha256": sha, "pages": d.page_count, "agree": agree, "rows": rows,
               "only_a": [x for x in ka if x not in b], "only_b": [x for x in b if x not in ka]},
              open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "agree": agree, "rows_a": len(a), "rows_b": len(b), "with_previous": len(rows)}))

if __name__ == "__main__":
    main(*sys.argv[1:3])
