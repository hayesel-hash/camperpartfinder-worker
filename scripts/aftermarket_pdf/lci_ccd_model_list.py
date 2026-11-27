"""Two-pass reader for Lippert (LCI / Furrion) CCD documents whose parts table is
"Callout | Part # | Description | Model" (e.g. Furrion 2.4GPM tankless water heater CCD-0009617, where the
title page says "MODEL (LIPPERT PN)"). Sibling of lci_ccd_list.py (which reads the "... | Quantity" layout).

Pass A: text-line order (a Part # line opens a row; description lines follow until the model lines, which are
comma-separated model codes such as "FWH09A, FWH09A-AM,"). Pass B: word boxes by header column; description and
model words are attached to the nearest part number by vertical position (model cells are vertically centred and
may start above the number line). "N/A" part numbers are not parts and are skipped. The model cell is kept as
" [models: ...]" after the description, as printed; a Model cell reading "All" (Girard GSWH-2 CCD-0009390, cells
vertically centred over a callout group) is dropped.
usage: python3 -I lci_ccd_model_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

PN = re.compile(r"^\d{7,10}$")
CALL = re.compile(r"^[A-Z]{1,2}$")
MODEL_LINE = re.compile(r"^(?:[A-Z]{2,}\d[A-Z0-9]*(?:-[A-Z0-9]+)*,?\s*)+$")
STOP = re.compile(r"^(Rev:|Page \d+$|CCD-\d+$)")


def header(L):
    for i in range(len(L) - 4):
        if L[i] == "Callout" and L[i + 1] in ("Part #", "Part#") and L[i + 2] == "Description" and L[i + 3] == "Model":
            return i + 4
    return None


def models_text(ms):
    # "All" (Girard GSWH-2 CCD-0009390) means every model: nothing to qualify, so it is not kept
    toks = [t.strip(" ,") for m in ms for t in m.split(",") if t.strip(" ,") and t.strip(" ,") != "All"]
    return " [models: " + ", ".join(toks) + "]" if toks else ""


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    h = header(L)
    if h is None:
        return []
    L = L[h:]
    rows, k = [], 0
    while k < len(L):
        if PN.match(L[k]):
            num, desc, mods, j = L[k], [], [], k + 1
            while j < len(L) and not PN.match(L[j]) and not STOP.match(L[j]) and L[j] != "N/A":
                if CALL.match(L[j]) and j + 1 < len(L) and (PN.match(L[j + 1]) or L[j + 1] == "N/A"):
                    break
                if CALL.match(L[j]) and j + 1 < len(L) and CALL.match(L[j + 1]):
                    break  # run of exploded-view callout letters printed after the table
                if MODEL_LINE.match(L[j]) or L[j] == "All":
                    mods.append(L[j])
                elif not mods:
                    desc.append(L[j])
                else:
                    break
                j += 1
            rows.append((num, " ".join(" ".join(desc).split()) + models_text(mods)))
            k = j; continue
        k += 1
    return rows


def pass_b(page):
    W = page.get_text("words")
    hc = [w for w in W if w[4] == "Callout"]
    if not hc:
        return []
    yh = hc[0][1]
    hdr = {w[4]: w[0] for w in W if abs(w[1] - yh) < 3}
    if not all(k in hdr for k in ("Part", "Description", "Model")):
        return []
    xp, xd, xm, ytop = hdr["Part"] - 25, hdr["Description"] - 8, hdr["Model"] - 5, hc[0][3]
    nums = sorted(((w[1] + w[3]) / 2, w[4]) for w in W if w[1] > ytop and xp <= w[0] < xd and (PN.match(w[4]) or w[4] == "N/A"))
    if not nums:
        return []
    desc = {i: [] for i in range(len(nums))}; mods = {i: [] for i in range(len(nums))}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 <= ytop or y0 > 760 or x0 < xd:
            continue
        yc = (y0 + y1) / 2
        i = min(range(len(nums)), key=lambda i: abs(nums[i][0] - yc))
        if abs(nums[i][0] - yc) < 26:
            (mods if x0 >= xm else desc)[i].append((y0, x0, w))
    out = []
    for i, (yc, n) in enumerate(nums):
        if not PN.match(n):
            continue
        out.append((n, lines_text(desc[i]) + models_text([lines_text(mods[i])])))
    return out


def lines_text(ws):
    out, cur, cy = [], [], None
    for y, x, w in sorted(ws):
        if cy is not None and y - cy > 4:
            out.append(cur); cur = []
        if not cur:
            cy = y
        cur.append((x, w))
    if cur:
        out.append(cur)
    return " ".join(" ".join(w for x, w in sorted(line)) for line in out)


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs = [], []
    for i, p in enumerate(d):
        a, b = pass_a(p), pass_b(p)
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        rows += [(i + 1, n, num, desc) for n, (num, desc) in enumerate([x for x in a if x in b], 1)]
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen or not desc:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"0": section}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "diffs": diffs[:2]}, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
