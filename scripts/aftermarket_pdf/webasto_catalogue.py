"""Two-pass reader for the Webasto "Commercial Vehicle Heating & Air Conditioning Systems" catalogue (2024/25, North
America): tables with a dark header row "[Part Rendering |] Part Description | Voltage | Part Number", one row per part
(dotted leaders between description and voltage, "—" for no voltage), part numbers like 9039726A, 1314150A, 50487171A,
9032008, 903200B. A description may wrap onto a second line under the first (the number sits on the first line). "Kit Contents"
lists beside the kit photos are not rows.

Pass A: pymupdf dict lines (spans joined per line). Pass B: word boxes grouped by baseline. Both locate each table's
header row ("Part Number" + "Description" on one baseline), take every part-number token under "Part Number", the
description text on its baseline between the description column's left edge and the voltage column, the voltage
printed on that baseline, and continuation lines directly below that start at the same x as the description.
Only rows on which both passes give the same number, description and voltage are kept; every part-number-like token
under a "Part Number" header that is not a kept row is reported as unread. Description = text as printed, plus
" (<voltage>)" when a voltage is printed. Section = the page heading (largest type on the page).
Output: supplied-documents JSON (rows page|n|number|description|section).
usage: python3 -I webasto_catalogue.py <pdf> <out.json> [first printed page number]"""
import hashlib, json, re, sys
import pymupdf

PNUM = re.compile(r"^\d{6,8}[A-Z]?$")
DOTS = re.compile(r"^[.…·\s]+$")
DASH = {"—", "–", "-"}


def norm(s):
    return re.sub(r"\s+([®™])", r"\1", " ".join(s.split()))


def headers(words):
    """-> [(y, desc_left, volt_left, num_cx, x_right)] one per table header row"""
    out = []
    for w in words:
        if w[4] != "Number":
            continue
        same = [v for v in words if abs(v[3] - w[3]) < 2]
        part = [v for v in same if v[4] == "Part" and 0 < w[0] - v[2] < 8]
        desc = [v for v in same if v[4] == "Description"]
        volt = [v for v in same if v[4] == "Voltage"]
        if not part or not desc or not volt:
            continue
        rend = [v for v in same if v[4] == "Rendering"]
        dpart = [v for v in same if v[4] == "Part" and 0 < desc[0][0] - v[2] < 8]
        dx0 = dpart[0][0] if dpart else desc[0][0]
        desc_left = rend[0][2] + 2 if rend else -1  # rendering column holds only photos and dashes
        num_cx = (part[0][0] + w[2]) / 2
        out.append((w[3], desc_left, volt[0][0] - 22, num_cx, w[2] + 60))
    return sorted(set(out))


def rows_from_lines(lines, hdrs, heading):
    """lines: [(text, y_baseline, x0, x1)] each a run of text on one baseline (words or dict lines).
    -> rows [(number, description, voltage, section)], numbers_seen"""
    rows, seen = [], []
    for hi, (hy, dl, vl, ncx, xr) in enumerate(hdrs):
        start = len(rows)
        nxt = hdrs[hi + 1][0] if hi + 1 < len(hdrs) else 1e9
        sec = heading
        tl = [l for l in lines if hy + 2 < l[1] < nxt - 2]
        nums = sorted([l for l in tl if PNUM.match(l[0]) and abs((l[2] + l[3]) / 2 - ncx) < 45], key=lambda l: l[1])
        # adapter-selection charts below a table print "P/N:" in the cell above / before the number: not table rows
        nums = [n for n in nums if not any(l[0].startswith("P/N") and n[1] - 22 < l[1] <= n[1] + 1
                                           and l[2] < n[3] and l[3] > n[2] - 40 for l in tl)]
        seen += [n[0] for n in nums]
        prev_last = hy
        for k, n in enumerate(nums):
            y = n[1]
            on = sorted([l for l in tl if abs(l[1] - y) < 2.5 and l is not n], key=lambda l: l[2])
            desc = [l for l in on if dl <= l[2] < vl - 20 and l[3] < ncx - 40 and not DOTS.match(l[0])
                    and l[0] not in DASH]
            volt = [l for l in on if l[2] >= vl - 20 and l[3] < ncx - 30 and not DOTS.match(l[0])]
            if desc:
                # a description line directly above, not used by the previous row, means the number sits on the
                # description's last line (bottom-aligned cell): its first line(s) would be lost -> unread
                above = [l for l in tl if y - 16 < l[1] < y - 3 and l[1] > prev_last + 1 and abs(l[2] - desc[0][2]) < 3
                         and not DOTS.match(l[0])]
                if above:
                    desc = []
            if not desc:
                rows.append((n[0], "", "", sec)); prev_last = y; continue  # held: no description on its line
            x_left, last_y = desc[0][2], y
            ny = nums[k + 1][1] if k + 1 < len(nums) else nxt
            text = [l[0] for l in desc]
            for l2y in sorted({round(l[1], 1) for l in tl if y + 3 < l[1] < ny - 2}):
                cont = sorted([l for l in tl if abs(l[1] - l2y) < 1.5 and dl <= l[2] < vl - 20
                               and not DOTS.match(l[0])], key=lambda l: l[2])
                other = [l for l in tl if abs(l[1] - l2y) < 1.5 and l[2] >= vl - 20 and l[3] < xr
                         and not DOTS.match(l[0])]
                if l2y - last_y > 13:
                    break
                if not cont and not other:
                    continue  # e.g. a dash in the rendering column between the two description lines
                if not cont or other or abs(cont[0][2] - x_left) > 3 or cont[0][0].startswith("Kit Contents"):
                    break  # a voltage / number / dash on the line means a new row
                text += [l[0] for l in cont]; last_y = l2y
            v = norm(" ".join(l[0] for l in volt))
            rows.append((n[0], norm(" ".join(text)), "" if not v.strip("—–- ") else v, sec, bool(volt), y, last_y))
            prev_last = last_y
        # every row prints a voltage cell ("12 V" or a dash); a number with none on its line shares a cell with the row
        # above (two numbers for one description) or sits off its description: hold it and the row it touches
        tab = rows[start:]
        for k, r in enumerate(tab):
            if len(r) == 7 and not r[4]:
                tab[k] = (r[0], "", "", r[3])
                if k and len(tab[k - 1]) == 7 and r[5] - tab[k - 1][6] < 16:
                    q = tab[k - 1]; tab[k - 1] = (q[0], "", "", q[3])
        rows[start:] = [r[:4] for r in tab]
    return rows, seen


def word_lines(page):
    """pass B units: single words"""
    return [(w[4], w[3], w[0], w[2]) for w in page.get_text("words")]


def dict_lines(page):
    """pass A units: dict lines, split where a span of leader dots or a wide gap separates cells"""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            cur, prev_x1 = [], None
            for s in ln["spans"]:
                t = s["text"]
                if not t.strip():
                    continue
                if prev_x1 is not None and (s["bbox"][0] - prev_x1 > 6 or DOTS.match(t)) and cur:
                    out.append(cur); cur = []
                if DOTS.match(t):
                    prev_x1 = s["bbox"][2]; continue
                cur.append(s); prev_x1 = s["bbox"][2]
            if cur:
                out.append(cur)
    res = []
    for spans in out:
        t = norm(" ".join(s["text"] for s in spans))
        t = re.sub(r"\s*\.{3,}.*$", "", t)  # leader dots glued into a span
        if not t:
            continue
        res.append((t, max(s["bbox"][3] for s in spans) - 0.0, spans[0]["bbox"][0], spans[-1]["bbox"][2]))
    return res


def heading(page):
    best = None
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            if abs(ln["dir"][0] - 1) > 0.01:
                continue  # rotated side-tab labels
            for s in ln["spans"]:
                if s["text"].strip().startswith(("A complete list", "For more information")):
                    continue  # running notes, not headings
                if s["text"].strip() and (best is None or s["size"] > best[0] + 0.5):
                    best = (s["size"], norm(s["text"]))
    return best[1] if best else ""


def merge_words(units):
    """pass B: join words on one baseline into runs separated by gaps > 6 pt (cells)"""
    by = {}
    for t, y, x0, x1 in units:
        by.setdefault(round(y, 1), []).append((t, y, x0, x1))
    out = []
    for y, ws in by.items():
        ws.sort(key=lambda w: w[2])
        cur = [ws[0]]
        for w in ws[1:]:
            if w[2] - cur[-1][3] > 6 or DOTS.match(w[0]) or DOTS.match(cur[-1][0]):
                out.append(cur); cur = [w]
            else:
                cur.append(w)
        out.append(cur)
    res = []
    for run in out:
        if all(DOTS.match(w[0]) for w in run):
            continue
        t = norm(" ".join(w[0] for w in run if not DOTS.match(w[0])))
        # a part number or voltage glued to its neighbours stays its own unit
        res.append((t, run[0][1], run[0][2], run[-1][3]))
    return res


def read_page(page):
    words = page.get_text("words")
    hdrs = headers(words)
    if not hdrs:
        return [], [], []
    h = heading(page)
    a, seen_a = rows_from_lines(dict_lines(page), hdrs, h)
    b, seen_b = rows_from_lines(merge_words(word_lines(page)), hdrs, h)
    return a, b, sorted(set(seen_a) | set(seen_b))


def main(pdf, outp, first=None):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    if not d.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, diffs, sections, unread = [], [], {}, []
    for i, p in enumerate(d):
        a, b, seen = read_page(p)
        if not seen:
            continue
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:4], "only_b": [x for x in b if x not in a][:4]})
        good = [x for x in a if x in b and x[1]]
        kept = {x[0] for x in good}
        unread += [{"page": i + 1, "number": n} for n in seen if n not in kept]
        for n, (num, desc, volt, sec) in enumerate(good, 1):
            code = next((k for k, v in sections.items() if v == sec), None)
            if code is None:
                code = str(len(sections) + 1); sections[code] = sec
            rows.append((i + 1, n, num, desc + (f" ({volt})" if volt else ""), code))
    seen, lines = set(), []
    for pg, n, num, desc, code in rows:
        if num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{code}")
    # kept rows are those both passes give identically; unread numbers are reported (held), not loaded
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs,
           "rows_total": len(rows), "numbers": len(seen), "unread": unread, "sections": sections, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen),
                      "sections": len(sections), "unread": unread[:6], "diffs": diffs[:2]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:3])
