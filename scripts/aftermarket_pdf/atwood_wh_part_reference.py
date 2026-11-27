"""Two-pass reader for the Atwood 2007 RV Appliance Service and Parts Manual "Electronic Water Heaters REPLACEMENT
PART REFERENCE" pages (split pp 001-093, pages 46-47): rows "[callout] NNNNN description" with a check mark (✗) in each
rotated model column; description continuation lines below the row ("(Use with 93870)", "(post electrode
connection)") and bold-italic notes printed across the model columns ("No Longer Available (Use 91504)").

The furnace reader (atwood_part_reference.py) does not fit these pages: callout numbers (1, 4A, 15-A, NS, N/S) sit
on the row baseline and continuation lines come after the check marks in text order.

Pass A: text lines from get_text(): a row line "NNNNN  description[ ✗]"; following lines that are not check marks,
callouts, rows or model-header lines are appended (continuations and notes).
Pass B: word boxes: a 5-digit word in the number column opens a row band down to the next number word; words left
of the first check-mark column are the description, non-✗ words right of it are notes; words ordered by line, then x.
Only rows on which both passes agree are kept. Model applicability (check marks) is not stored; descriptions,
"WSL" / "NLA" markers and "No Longer Available (Use N)" notes are kept as printed.

usage: python3 -I atwood_wh_part_reference.py <pdf> <out.json> <first-last page>"""
import hashlib, json, re, sys
import pymupdf

ROW = re.compile(r"^(\d{5})\s+(\S.*)$")
NUM = re.compile(r"^\d{5}$")
CALLOUT = re.compile(r"^(\d{1,2}[A-Z]?|\d{1,2}-[A-Z]|NS|N/S|a)$")
MODEL = re.compile(r"^G[A-Z0-9]*\d+[A-Z]?-\d")
CHECK = "✗"


def clean(s):
    return " ".join(s.replace(CHECK, " ").split())


NLA_NOTE = re.compile(r"\s*No Longer Available \(Use (\d{5})\)")


def tidy(desc):
    """Move the "No Longer Available (Use N)" note (printed across the model columns) to the end."""
    m = NLA_NOTE.search(desc)
    if not m:
        return desc
    return clean(NLA_NOTE.sub("", desc) + f" - No Longer Available (Use {m.group(1)})")


def is_wh_page(page):
    t = page.get_text()
    return "Water Heaters" in t and "REPLACEMENT PART REFERENCE" in t


def pass_a(page):
    L = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    rows, cur = [], None
    for l in L:
        m = ROW.match(l)
        if m:
            cur = [m.group(1), clean(m.group(2))]; rows.append(cur); continue
        if cur is None or l == CHECK or set(l) <= {CHECK, " "} or CALLOUT.match(l):
            continue
        if MODEL.match(l) or re.match(r"^\d{1,3}$", l):
            cur = None; continue
        cur[1] = clean(cur[1] + " " + l)
    return [tuple(r) for r in rows]


def pass_b(page):
    W = [w for w in page.get_text("words")]
    checks = [w for w in W if w[4] == CHECK]
    if not checks:
        return []
    x_model = min(w[0] for w in checks) - 2
    nums = sorted([w for w in W if NUM.match(w[4]) and w[0] < x_model - 60], key=lambda w: w[1])
    if not nums:
        return []
    x_num1 = max(w[2] for w in nums)
    y_stop = min((w[1] for w in W if MODEL.match(w[4]) and w[1] > nums[-1][1]), default=page.rect.height - 40)
    out = []
    for k, n in enumerate(nums):
        top = n[1] - 2
        bot = nums[k + 1][1] - 2 if k + 1 < len(nums) else min(n[1] + 30, y_stop)
        ws = [w for w in W if top <= w[1] < bot and w is not n and w[4] != CHECK and w[0] > x_num1 - 1
              and not MODEL.match(w[4])]
        # group by printed line (baseline within 3 pt), then left to right
        ws.sort(key=lambda w: (round(w[3]), w[0]))
        lines = []
        for w in ws:
            if lines and abs(lines[-1][0] - w[3]) < 3:
                lines[-1][1].append(w)
            else:
                lines.append([w[3], [w]])
        desc = " ".join(" ".join(x[4] for x in sorted(g, key=lambda x: x[0])) for _, g in lines)
        out.append((n[4], clean(desc)))
    return out


def main(pdf, outp, rng):
    a0, a1 = (int(x) for x in rng.split("-"))
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    sections = {"0": "Atwood 2007 RV Appliance Service and Parts Manual: Electronic Water Heaters REPLACEMENT PART "
                     "REFERENCE (January 2007); model applicability by check-mark column in the source"}
    rows, diffs, by_num, pages = [], [], {}, []
    for pn in range(a0, a1 + 1):
        p = d[pn - 1]
        if not is_wh_page(p):
            continue
        pages.append(pn)
        a, b = pass_a(p), pass_b(p)
        if a != b:
            diffs.append({"page": pn, "only_a": [x for x in a if x not in b], "only_b": [x for x in b if x not in a]})
        for n, (num, desc) in enumerate([x for x in a if x in b], 1):
            desc = tidy(desc)
            rows.append((pn, n, num, desc))
            by_num.setdefault(num, set()).add(desc)
    conflicts = {k: sorted(v) for k, v in by_num.items() if len(v) > 1}
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in conflicts or num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    supersessions = [{"page": pg, "old": num, "new": NLA_NOTE.search(desc).group(1)} for pg, n, num, desc in rows
                     if NLA_NOTE.search(desc)]
    out = {"doc": sha, "pages": d.page_count, "pages_read": pages, "supersessions": supersessions, "agree": bool(lines), "all_rows_agree": not diffs,
           "diffs": diffs, "conflicts": conflicts, "rows_total": len(rows), "numbers": len(seen), "sections": sections,
           "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({k: out[k] for k in ("pages_read", "supersessions", "all_rows_agree", "rows_total", "numbers", "conflicts", "diffs")},
                     ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
