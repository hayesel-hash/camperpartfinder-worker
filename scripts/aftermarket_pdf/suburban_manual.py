"""Two-pass reader for Suburban (Airxcel) RV appliance parts manuals (ILLUSTRATED ITEM | DESCRIPTION | PART NO.).
Pass B: fonts/positions - bold 10pt lines in the description column are item headings, 8pt lines are model
applicability, 6-digit numbers in the PART NO. column are part numbers (paired with the model line on the same
baseline, else the nearest line above). Pass A: plain text order with a heading heuristic (line without model codes,
in capitals, not a number). Rows are kept where both passes give the same heading for the number.
usage: python3 -I suburban_manual.py <pdf> <out.json>"""
import collections, hashlib, json, re, sys
import pymupdf
NUM = re.compile(r"^\d{6}$")
MODEL = re.compile(r"\b(NT|SF|SH|SW|SAW|DD|SHD|SRNA|SCNA|SSNA|SDN|SGN|SFV|P|SR|IH|ST)[- ]?\d|Serial|SERIAL|Inch|INCH|;|/|MODELS")

def pass_b(page):
    """Model lines are assigned to the part number whose vertical centre is nearest (numbers are centred on
    multi-line model blocks), within the same item heading."""
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(sp["text"] for sp in l["spans"]).strip()
            if not t: continue
            sp = l["spans"][0]
            lines.append(((l["bbox"][1] + l["bbox"][3]) / 2, l["bbox"][0], t, sp["size"], "Bold" in sp["font"] or "Black" in sp["font"]))
    lines.sort()
    heads = [(y, t) for y, x, t, size, bold in lines if bold and size >= 8.9 and 120 < x < 450 and t not in ("DESCRIPTION", "PART NO.", "ILLUSTRATED ITEM")]
    def head_at(y):
        h = [t for hy, t in heads if hy < y + 3]
        return (len(h), h[-1] if h else "")
    nums = [(y, t, head_at(y)) for y, x, t, size, bold in lines if x > 450 and NUM.match(t)]
    blocks = {k: [] for k in range(len(nums))}
    for y, x, t, size, bold in lines:
        if bold or not (120 < x < 450) or size >= 8.9: continue
        hk = head_at(y)
        cands = [k for k, (ny, nt, nh) in enumerate(nums) if nh[0] == hk[0]]
        if not cands: continue
        k = min(cands, key=lambda k: abs(nums[k][0] - y))
        if abs(nums[k][0] - y) < 14: blocks[k].append(t)
    return [(nt, nh[1], " ".join(blocks[k])) for k, (ny, nt, nh) in enumerate(nums)]

def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    head, rows, pend = "", [], []
    for l in L:
        if NUM.match(l):
            rows.append((l, head)); pend = []
        elif l.isupper() and not MODEL.search(l) and len(l) > 3 and l not in ("DESCRIPTION", "PART NO.", "ILLUSTRATED ITEM", "PICTURE NOT AVAILABLE"):
            head = l
    return rows

def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    agg = collections.OrderedDict(); dis = []
    for i, p in enumerate(d):
        b = pass_b(p); a = pass_a(p)
        amap = collections.defaultdict(set)
        for num, h in a: amap[num].add(h)
        for num, h, models in b:
            if h and h in amap.get(num, set()):
                e = agg.setdefault(num, {"page": i + 1, "number": num, "head": h, "models": []})
                if h == e["head"] and models and models not in e["models"]: e["models"].append(models)
            else:
                dis.append({"page": i + 1, "number": num, "b": h, "a": sorted(amap.get(num, []))})
    rows = []
    for e in agg.values():
        ms = "; ".join(e["models"])
        rows.append({"page": e["page"], "number": e["number"], "desc": e["head"].title() + (f" (for {ms})" if ms else "")})
    json.dump({"doc": sha, "pages": d.page_count, "rows": rows, "disagree": dis}, open(outp, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"sha16": sha[:16], "rows": len(rows), "disagree": len(dis)}))
    for x in dis[:15]: print("  DIS", x)

if __name__ == "__main__":
    main(*sys.argv[1:3])
