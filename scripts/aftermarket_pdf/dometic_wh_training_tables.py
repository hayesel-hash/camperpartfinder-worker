"""Two-pass reader for the Dometic (ex-Atwood) water-heater training slides (PowerPoint, Dec 2019, "WATER HEATERS
TRAINING"): ruled two-up tables "<number col> | <description col> | Status" twice per slide.

  p2 "Water Heaters and Replacement Tanks": Model | Water Heaters | Status || Part # | Replacement Tanks | Status
     (a replacement tank cell lists the heater models the tank is for; stored as "Replacement tank: <models>",
     same-maker fitment kept in the name only, never as interchangeability)
  p3 "Replacement Doors & Parts": Part # | Description | Status || Part # | Description | Status

Pass A: pymupdf find_tables() cells. Pass B: word boxes; columns from the header words' x positions, rows from the
drawn horizontal rules (word centre between two rules). The Status codes (A, K, AS, B (8))
are not explained in the document and are not loaded. A number printed twice with different descriptions on the
same document is reported as a conflict and not loaded.

usage: python3 -I dometic_wh_training_tables.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^\d{5}$")
HEAD_NUM = {"Model", "Part"}
TANK_HEAD = "Replacement Tanks"


def clean(s):
    return " ".join(s.replace("\n", " ").split())


def label(head, cell):
    return f"Replacement tank: {cell}" if head == TANK_HEAD else cell


def pass_a(page):
    out = []
    for t in page.find_tables().tables:
        rows = t.extract()
        if not rows:
            continue
        hdr = [clean(c or "") for c in rows[0]]
        groups = [i for i, h in enumerate(hdr) if h in ("Model", "Part #")]
        for r in rows[1:]:
            for g in groups:
                num, desc = clean(r[g] or ""), clean(r[g + 1] or "")
                if NUM.match(num) and desc:
                    out.append((num, label(hdr[g + 1], desc)))
    return out


def pass_b(page):
    W = page.get_text("words")
    lines = {}
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = clean("".join(s["text"] for s in l["spans"]))
            if t in ("Model", "Part #", "Water Heaters", "Replacement Tanks", "Description", "Status"):
                lines.setdefault(t, []).append(l["bbox"])
    if not lines:
        return []
    heads = sorted([(bb[0], t) for t, bbs in lines.items() for bb in bbs])
    yh = max(bb[3] for bbs in lines.values() for bb in bbs)
    cols = []  # (x_num, x_desc, x_status, desc_head)
    for i, (x, t) in enumerate(heads):
        if t in ("Model", "Part #"):
            dx, dt = heads[i + 1]; sx = heads[i + 2][0]
            cols.append((x, dx, sx, dt))
    # row bands from the drawn horizontal rules (cells are top-aligned on one side, centred on the other)
    ys = set()
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.5 and abs(it[1].x - it[2].x) > 20:
                ys.add(round(it[1].y, 1))
            elif it[0] == "re" and it[1].height < 2 and it[1].width > 20:
                ys.add(round((it[1].y0 + it[1].y1) / 2, 1))
            elif it[0] == "re" and it[1].height >= 2:
                ys.update({round(it[1].y0, 1), round(it[1].y1, 1)})
    rules = []
    for y in sorted(ys):
        if y > yh - 2 and (not rules or y - rules[-1] > 3):
            rules.append(y)
    out = []
    for gi, (xn, xd, xs, dt) in enumerate(cols):
        xnext = cols[gi + 1][0] if gi + 1 < len(cols) else 1e9
        for top, bot in zip(rules, rules[1:]):
            inband = [w for w in W if top < (w[1] + w[3]) / 2 < bot]
            nums = [w[4] for w in inband if NUM.match(w[4]) and xn - 15 <= w[0] < xn + 40]
            if len(nums) != 1:
                continue
            ws = sorted((w[1], w[0], w[4]) for w in inband if xn + 40 <= w[0] < xs - 5 and w[0] < xnext)
            desc = clean(" ".join(t for _, _, t in ws))
            if desc:
                out.append((nums[0], label(dt, desc)))
    return out


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    sections, rows, diffs, by_num = {}, [], [], {}
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        if not a and not b:
            continue
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b], "only_b": [x for x in b if x not in a]})
        title = clean(p.get_text("text").splitlines()[0])
        sections[str(len(sections))] = f"Water heater training slides (Dec 2019), slide {i + 1}: {title}"
        for n, (num, desc) in enumerate([x for x in a if x in b], 1):
            rows.append((i + 1, n, num, desc, len(sections) - 1))
            by_num.setdefault(num, set()).add(desc)
    conflicts = {k: sorted(v) for k, v in by_num.items() if len(v) > 1}
    lines, seen = [], set()
    for pg, n, num, desc, s in rows:
        if num in conflicts or num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{s}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "conflicts": conflicts,
           "rows_total": len(rows), "numbers": len(seen), "sections": sections, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("agree", "rows_total", "numbers", "conflicts", "diffs")}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
