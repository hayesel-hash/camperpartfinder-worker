"""Two-pass reader for the "Truma Spare Parts" catalogue printed by Grove Products (UK Truma distributor; Grove logo in
the page footer, copy from camperlands.co.uk): tables "Pos | Truma No. | Grove No. | Description | Qty", usually two
tables side by side, section headings above them ("Spare Parts", "Casing", "Wall Flue").

Larry's 27 Nov decision on distributor catalogues: a maker's number printed under that maker's column with a
description is that maker's part (supplied lane, source kind distributor_catalogue); the distributor's own stock number
(Grove No.) is never a part and is not loaded.

Both passes use the same geometry rule with different text engines (pass A pymupdf words, pass B pdfplumber words):
- each "Truma No. ... Qty" header line starts a table; its column x positions come from the header words, and the table
  runs down to the next header in the same column band;
- a row is a baseline with a Truma number (NNNNN-NN or NNNNN-NNNNN) in the Truma No. column and description words on
  the same baseline (stacked cells such as "Control panel cable 3 m / 5 m" are one baseline each);
- "Includes items below" is dropped; a description-only baseline that follows a row (wrapped text) puts the row on hold;
- "Description from 06/14" / "to 05/14" header qualifiers become the row's section label, not part of the description;
- a number printed with two different descriptions is not loaded.
usage: python3 -I truma_grove_catalogue.py <pdf> <out.json> "<section label>"
"""
import hashlib, json, re, sys
import pdfplumber, pymupdf

TNUM = re.compile(r"^\d{5}-\d{2}(?:\d{3})?$")
INCL = re.compile(r",?\s*Includes items below\s*$", re.I)


def sp(s):
    return " ".join(s.split())


def words_a(page):
    return [{"x0": w[0], "top": w[1], "x1": w[2], "bottom": w[3], "text": w[4]} for w in page.get_text("words")]


def words_b(ppage):
    return [{"x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"], "text": w["text"]}
            for w in ppage.extract_words(keep_blank_chars=False, use_text_flow=False)]


def baselines(ws):
    rows = []
    for w in sorted(ws, key=lambda w: (w["bottom"], w["x0"])):
        if rows and abs(rows[-1][0] - w["bottom"]) <= 2.0:
            rows[-1][1].append(w)
        else:
            rows.append([w["bottom"], [w]])
    return [(b, sorted(r, key=lambda w: w["x0"])) for b, r in rows]


def read_page(ws):
    lines = baselines(ws)
    heads = []
    for b, ln in lines:
        t = [w["text"] for w in ln]
        for k in range(len(ln) - 1):
            if ln[k]["text"] == "Truma" and ln[k + 1]["text"] == "No.":
                rest = [w for w in ln if w["x0"] > ln[k]["x0"]]
                desc = next((w for w in rest if w["text"].startswith("Description")), None)
                qty = next((w for w in rest if w["text"] == "Qty"), None)
                grove = next((w for w in rest if w["text"] == "Grove"), None)
                if desc and qty:
                    qual = sp(" ".join(w["text"] for w in rest if desc["x1"] <= w["x0"] < qty["x0"] - 2))
                    heads.append({"y": b, "tx": ln[k]["x0"], "gx": grove["x0"] if grove else desc["x0"], "dx": desc["x0"],
                                  "qx": qty["x0"], "x_lo": ln[k]["x0"] - 24, "x_hi": qty["x1"] + 8, "qual": qual})
    rows, held = [], []
    for h in heads:
        nxt = min([g["y"] for g in heads if g is not h and g["y"] > h["y"] and g["x_lo"] < h["x_hi"] and h["x_lo"] < g["x_hi"]] or [1e9])
        last = None
        for b, ln in lines:
            if not (h["y"] + 1 < b < nxt - 1):
                continue
            band = [w for w in ln if h["x_lo"] <= w["x0"] < h["x_hi"]]
            if not band:
                continue
            nums = [w for w in band if h["tx"] - 6 <= w["x0"] < h["gx"] - 3 and TNUM.match(w["text"])]
            desc = sp(" ".join(w["text"] for w in band if h["dx"] - 3 <= w["x0"] < h["qx"] - 3))
            desc_plain = sp(INCL.sub("", desc))
            if nums:
                if len(nums) > 1:
                    held.append({"numbers": [w["text"] for w in nums], "why": "two numbers on one baseline"}); last = None; continue
                if not desc_plain:
                    held.append({"number": nums[0]["text"], "why": "no description on its baseline"}); last = None; continue
                last = {"number": nums[0]["text"], "desc": desc_plain, "qual": h["qual"]}
                rows.append(last)
            elif desc and last is not None:
                if INCL.sub("", desc).strip() == "":
                    continue
                held.append({"number": last["number"], "why": "description wraps onto the next line", "text": desc})
                rows.remove(last); last = None
    return rows, held, len(heads)


def main(pdf, outp, section):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, held, unread = [], [], [], []
    key = lambda r: (r["number"], "".join(r["desc"].split()).casefold(), r["qual"])
    for i, p in enumerate(d):
        ra, ha, na = read_page(words_a(p))
        rb, hb, nb = read_page(words_b(pl.pages[i]))
        ka, kb = [key(r) for r in ra], [key(r) for r in rb]
        if sorted(ka) != sorted(kb) or na != nb:
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb][:5], "only_b": [r for r in rb if key(r) not in ka][:5],
                          "tables": [na, nb]})
        keep += [(i + 1, r) for r in ra if key(r) in kb]
        held += [dict(x, page=i + 1) for x in ha]
        got = {r["number"] for r in ra} | {x.get("number") for x in ha}
        for x in ha:
            got |= set(x.get("numbers", []))
        for m in re.finditer(r"(?<![\d-])(\d{5}-\d{2}(?:\d{3})?)(?![\d-])", p.get_text()):
            if m.group(1) not in got:
                unread.append({"page": i + 1, "number": m.group(1)})
    names = {}
    for pg, r in keep:
        names.setdefault(r["number"], set()).add("".join(r["desc"].split()).casefold())
    conflict = {n for n, v in names.items() if len(v) > 1}
    quals = sorted({r["qual"] for _, r in keep})
    sections = {str(k): section + (f" — table header 'Description {q}'" if q else "") for k, q in enumerate(quals)}
    lines, seen, per_page = [], set(), {}
    for pg, r in keep:
        if r["number"] in conflict or r["number"] in seen:
            continue
        seen.add(r["number"])
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{r['number']}|{r['desc'].replace('|', '/')}|{quals.index(r['qual'])}")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines),
           "conflicts": [{"number": n} for n in sorted(conflict)], "held": held, "unread": unread}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(keep), "numbers": len(seen), "diffs": diffs[:3],
                      "conflicts": len(conflict), "held": len(held), "held_sample": held[:6], "unread": len(unread),
                      "unread_sample": unread[:10]}, ensure_ascii=False)[:5000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
