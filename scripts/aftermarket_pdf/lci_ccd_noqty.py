"""Two-pass reader for Lippert (LCI) component lists with no Quantity column: "Callout | Part # | Description"
(Basic Power Tongue Jack CCD-0008624, Power Tongue Jack CCD-0002709, Manual Scissor Jack CCD-0002666, Ground Control
LCD CCD-0002690). One callout cell can hold several numbers ("I: 225885 Lens (Original) / 706948 Lens (Current)").

Pass A: text-line order after the "Callout / Part # / Description" header (a number line opens a row; description
lines follow until the next number, the next callout letter that is followed by a number, or the drawing's callout
labels after the table). Pass B: word positions (numbers in the Part # column, description words in the Description
column nearest each number's baseline). The inch mark is printed in the order the text layer gives it in both passes.
Only rows both passes give identically are kept; literature numbers (CCD-...) are skipped.
Rows only one pass reads (wrapped description lines, a callout cell with two numbers, "*" numbers inside a note) are
left out and listed in "diffs".
usage: python3 -I lci_ccd_noqty.py <pdf> <out.json> ["<section label if page 1 has no title>"]"""
import hashlib, json, os, re, sys
import pymupdf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lci_ccd_list import title_of, lines_text

PN = re.compile(r"^\*?\d{5,10}$")  # "*694131": footnote "*Part must be replaced using variant code."
STAR_NOTE = "*Part must be replaced using variant code."
CALL = re.compile(r"^[A-Z]{1,2}$")
STOP = re.compile(r"^(Rev:|Web:|CCD-\d+$|Note:|NOTE:)")


def table_lines(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    for k in range(len(L) - 2):
        if L[k] == "Callout" and L[k + 1] in ("Part #", "Kit #") and L[k + 2] == "Description":
            if "Quantity" in L[k + 3:k + 5]:
                return []
            return L[k + 3:]
    return []


def pass_a(page):
    L, rows, k = table_lines(page), [], 0
    while k < len(L):
        if PN.match(L[k]):
            num, desc, j = L[k], [], k + 1
            while j < len(L) and not PN.match(L[j]) and not STOP.match(L[j]):
                if CALL.match(L[j]) and (j + 1 >= len(L) or PN.match(L[j + 1]) or CALL.match(L[j + 1])):
                    break
                desc.append(L[j]); j += 1
            rows.append((num, " ".join(" ".join(desc).split())))
            k = j; continue
        k += 1
    return rows


def pass_b(page):
    W = page.get_text("words")
    hc = [w for w in W if w[4] == "Callout"]
    hp = [w for w in W if w[4] in ("Part", "Kit") and hc and abs(w[1] - hc[0][1]) < 3]
    hd = [w for w in W if w[4] == "Description" and hc and abs(w[1] - hc[0][1]) < 3]
    if not (hc and hp and hd) or any(w[4] == "Quantity" and abs(w[1] - hc[0][1]) < 3 for w in W):
        return []
    xp, xd, ytop = hp[0][0] - 25, hd[0][0] - 5, hd[0][3]
    ybot = page.rect.height - 30
    nums = sorted(((w[1] + w[3]) / 2, w[4]) for w in W if ytop < w[1] < ybot and xp <= w[0] < xd and PN.match(w[4]))
    if not nums:
        return []
    desc = {i: [] for i in range(len(nums))}
    for x0, y0, x1, y1, w, *_ in W:
        if y0 <= ytop or y0 > ybot or x0 < xd:
            continue
        yc = (y0 + y1) / 2
        i = min(range(len(nums)), key=lambda i: abs(nums[i][0] - yc))
        if abs(nums[i][0] - yc) < 8:
            desc[i].append((y0, x0, w))
    return [(n, lines_text(desc[i])) for i, (yc, n) in enumerate(nums)]


def finish(page, rows):
    """Strip the footnote star (only when the page prints its note) and an empty trailing "-" measurement cell."""
    note = STAR_NOTE in " ".join(page.get_text().split())
    out = []
    for num, desc in rows:
        desc = re.sub(r"\s+-$", "", desc)
        if num.startswith("*"):
            if not note:
                continue
            num, desc = num[1:], desc + " (*Part must be replaced using variant code)"
        out.append((num, desc))
    return out


def main(pdf, outp, label=""):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf); sec = title_of(d) or label
    rows, diffs = [], []
    for i, p in enumerate(d):
        a, b = finish(p, pass_a(p)), finish(p, pass_b(p))
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        rows += [(i + 1, n, num, desc) for n, (num, desc) in enumerate([x for x in a if x in b], 1)]
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen or not desc:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    # only rows both passes give identically are written, so "agree" means every loaded row agreed;
    # "all_rows_agree" says whether any one-pass rows were left out (listed in "diffs").
    out = {"doc": sha, "pages": d.page_count, "agree": bool(lines), "all_rows_agree": not diffs, "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"0": sec}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "title": sec, "agree": out["agree"], "all_rows_agree": not diffs, "rows": len(rows), "numbers": len(seen),
                      "diffs": diffs[:3]}, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
