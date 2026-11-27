"""Two-pass reader for "AL-KO Spare Parts" printed by Grove Products (UK distributor; Grove logo in the page footer,
14 pages, InDesign 2020): stabilisers, overrun assemblies, wheel brakes, corner steadies, wheel locks. Tables
"Pos | AL-KO No. | Grove No. | Description", often two side by side, under a product heading ("Stabilisers" / "AKS 3004 Mk2").

Larry's 27 Nov decision on distributor catalogues: a maker's number printed under that maker's column with a description is
that maker's part (supplied lane, source kind distributor_catalogue); the Grove No. is the distributor's stock number and is
never a part. Same rules as truma_grove_catalogue.py:
- each "AL-KO No. ... Description" header line starts a table; column x positions come from the header words; the table runs
  down to the next header in the same column band;
- a row is a baseline with one AL-KO number (5-10 digits, as printed) in the AL-KO No. column and description words on the
  same baseline; a description-only baseline (no Pos) right after a row (wrapped text) puts that row on hold; a Pos line with
  a description and no number ("10 | Brake drum / Complete with bearing" over "623748 | 98 x 4 / m12 x 1.5") is a cell
  heading: the numbered lines under it in the same cell are held (their own line is not the whole name); a description that
  does not start with a word ("-7/95" under "Handbrake assy (inc 17&20)") is held;
- a number printed with two different descriptions is not loaded; the product heading above the table (pass A) is the
  section label; the passes are compared on number + description.
Pass A pymupdf words, pass B pdfplumber words; only rows both passes give identically are kept.
usage: python3 -I alko_grove_spares.py <pdf> <out.json>
"""
import hashlib, json, re, sys
import pdfplumber, pymupdf

NUM = re.compile(r"^\d{5,10}$")


def sp(s):
    return " ".join(s.split())


def words_a(page):
    return [{"x0": w[0], "top": w[1], "x1": w[2], "bottom": w[3], "text": w[4]} for w in page.get_text("words")]


def words_b(ppage):
    return [{"x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"], "text": w["text"]}
            for w in ppage.extract_words(keep_blank_chars=False, use_text_flow=False)]


def baselines(ws):
    rows = []
    for w in sorted(ws, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"])):
        m = (w["top"] + w["bottom"]) / 2
        if rows and abs(rows[-1][0] - m) <= 2.0:
            rows[-1][1].append(w)
        else:
            rows.append([m, [w]])
    return [(m, sorted(r, key=lambda w: w["x0"])) for m, r in rows]


def heading(ws, y):
    big = [w for w in ws if (w["bottom"] - w["top"]) >= 14 and (w["top"] + w["bottom"]) / 2 < y
           and w["text"] not in ("AL-KO", "Spare", "Parts") and not re.fullmatch(r"\d{1,2}", w["text"])]
    if not big:
        return ""
    ls = baselines(big)
    return sp(" ".join(" ".join(w["text"] for w in ln) for _, ln in ls[-2:]))[:80]


def read_page(ws):
    lines = baselines(ws)
    heads = []
    for m, ln in lines:
        for k in range(len(ln) - 1):
            if ln[k]["text"] == "AL-KO" and ln[k + 1]["text"] == "No.":
                rest = [w for w in ln if w["x0"] > ln[k]["x0"]]
                gr = next((w for w in rest if w["text"] == "Grove"), None)
                de = next((w for w in rest if w["text"].startswith("Description")), None)
                if gr and de:
                    heads.append({"m": m, "tx": ln[k]["x0"], "gx": gr["x0"], "dx": de["x0"],
                                  "x_lo": ln[k]["x0"] - 32, "x_hi": de["x0"] + 128})
    rows, held = [], []
    for h in heads:
        nxt = min([g["m"] for g in heads if g is not h and g["m"] > h["m"] and g["x_lo"] < h["x_hi"] and h["x_lo"] < g["x_hi"]]
                  or [1e9])
        label = heading(ws, h["m"])
        last = None; prev_m = h["m"]; header = False
        for m, ln in lines:
            if not (h["m"] + 2 < m < nxt - 2):
                continue
            band = [w for w in ln if h["x_lo"] <= w["x0"] < h["x_hi"]]
            if not band:
                continue
            if m - prev_m > 20:          # the table has ended (rows are ~14 pt apart)
                break
            prev_m = m
            pos = [w for w in band if w["x0"] < h["tx"] - 6]
            nums = [w for w in band if h["tx"] - 6 <= w["x0"] < h["gx"] - 3 and NUM.match(w["text"])]
            other = [w for w in band if h["tx"] - 6 <= w["x0"] < h["gx"] - 3 and not NUM.match(w["text"])]
            desc = sp(" ".join(w["text"] for w in band if h["dx"] - 3 <= w["x0"] < h["x_hi"]))
            if pos:
                header = False              # a Pos cell starts a new item
            if nums:
                if len(nums) > 1 or other:
                    held.append({"numbers": [w["text"] for w in nums], "why": "more than one token in the AL-KO No. cell"}); last = None; continue
                if not desc:
                    held.append({"number": nums[0]["text"], "why": "no description on its baseline"}); last = None; continue
                if not re.match(r"[A-Za-z]", desc):
                    held.append({"number": nums[0]["text"], "why": "description does not start with a word (qualifier line of a shared cell)", "text": desc})
                    last = None; continue
                if header:
                    held.append({"number": nums[0]["text"], "why": "description continues a heading line of its cell", "text": desc})
                    last = None; continue
                last = {"number": nums[0]["text"], "desc": desc, "qual": label}
                rows.append(last)
            elif desc and pos:
                header = True               # "10 | Brake drum" with the numbers on the lines below
                last = None
            elif desc and last is not None:
                held.append({"number": last["number"], "why": "description wraps onto the next line", "text": desc})
                rows.remove(last); last = None
            elif desc:
                header = True
            else:
                last = None
    return rows, held, len(heads)


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); pl = pdfplumber.open(pdf)
    keep, diffs, held = [], [], []
    # the section label is a heading, not part data: the two passes are compared on number + description and pass A's
    # heading is kept (pdfplumber splits the large heading words differently)
    key = lambda r: (r["number"], "".join(r["desc"].split()).casefold())
    for i, p in enumerate(d):
        ra, ha, na = read_page(words_a(p))
        rb, hb, nb = read_page(words_b(pl.pages[i]))
        ka, kb = [key(r) for r in ra], [key(r) for r in rb]
        if sorted(ka) != sorted(kb) or na != nb:
            diffs.append({"page": i + 1, "only_a": [r for r in ra if key(r) not in kb][:4], "only_b": [r for r in rb if key(r) not in ka][:4],
                          "tables": [na, nb]})
        keep += [(i + 1, r) for r in ra if key(r) in kb]
        held += [dict(x, page=i + 1) for x in ha]
    names = {}
    for pg, r in keep:
        names.setdefault(r["number"], set()).add("".join(r["desc"].split()).casefold())
    conflict = {n for n, v in names.items() if len(v) > 1}
    quals = sorted({r["qual"] for _, r in keep})
    sections = {str(k): f"AL-KO Spare Parts (Grove Products print): {q}" for k, q in enumerate(quals)}
    lines, seen, per_page = [], set(), {}
    for pg, r in keep:
        if r["number"] in conflict or r["number"] in seen:
            continue
        seen.add(r["number"])
        per_page[pg] = per_page.get(pg, 0) + 1
        lines.append(f"{pg}|{per_page[pg]}|{r['number']}|{r['desc'].replace('|', '/')}|{quals.index(r['qual'])}")
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "page_diffs": diffs, "rows_total": len(keep),
           "numbers": len(seen), "sections": sections, "rows": "\n".join(lines),
           "conflicts": [{"number": n, "descs": sorted(names[n])} for n in sorted(conflict)], "held": held}
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=0)
    print(json.dumps({"sha16": sha[:16], "rows": len(keep), "numbers": len(seen), "pages_with_diffs": len(diffs),
                      "diff_sample": diffs[:3], "conflicts": out["conflicts"][:6], "held": len(held), "held_sample": held[:8]},
                     ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
