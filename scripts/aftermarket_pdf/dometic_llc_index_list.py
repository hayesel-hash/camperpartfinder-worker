"""Two-pass reader for Dometic Corporation (LaGrange IN, Dometic LLC US format) refrigerator "PARTS LIST"
sheets with "Index No. | Part No. | A | B | Description" tables, e.g. RM2351 Parts List form 3311745.000 (5/07).

Each parts page carries the section heading ("DOOR ASSEMBLY"), the matrix key printed under / above the table
("Model RM2351 Prod # 921145039 = A") and rows: an index number (blank when a second part shares the index,
e.g. 17 Spring LH / Spring RH), the 10-digit part number, one letter per model column that the part applies
to, and a one-line description.

Pass A: text lines in reading order: index line opens an index, a 9-10 digit line opens a row, single matrix
letters are collected, the next line is the description. Stops at the bottom header ("Index").
Pass B: word boxes grouped by baseline; columns from the header words (Index / Part / the single letters /
Description): a number in the Part No. band opens a row, letters in their own column bands, description words
right of the Description header's left edge.

A row is kept only when both passes give the same (index, number, letters, description); everything else is
reported in "held". A row whose letters do not cover every model of the key gets "[applies to: ...]".
Output: supplied-documents JSON (rows page|n|number|description|section).
usage: python3 -I dometic_llc_index_list.py <pdf> <out.json> "<label>"
"""
import hashlib, json, re, sys

NUM = re.compile(r"^\d{9,10}$")
IDX = re.compile(r"^\d{1,3}$")
KEY = re.compile(r"Model\s+(\S+)\s+Prod\s*#\s*(\d{9,10})\s*=\s*([A-Z])")
DASH = {"--", "-", "\u2014", "\u2013"}


def norm(s):
    return " ".join(s.split())


def heading(text):
    L = [norm(l) for l in text.splitlines() if norm(l)]
    for i, l in enumerate(L):
        if l.startswith("Only Those Parts"):
            return L[i - 1] if i else ""
    return ""


def keymap(text):
    return {m.group(3): (m.group(1), m.group(2)) for m in KEY.finditer(norm(text.replace("\n", " ")))}


def pass_a(text, letters):
    L = [norm(l) for l in text.splitlines()]
    L = [l for l in L if l]
    try:
        k = next(i for i, l in enumerate(L) if l.startswith("Only Those Parts"))
    except StopIteration:
        return []
    rows, idx, cur, want_desc = [], None, None, False
    for l in L[k + 1:]:
        if KEY.search(l):
            continue
        if l == "Index":
            break
        if NUM.match(l):
            cur = [idx, l, [], None]; rows.append(cur); want_desc = True
            continue
        if IDX.match(l) and (cur is None or cur[3] is not None):
            idx = l; cur = None
            continue
        if cur is not None and want_desc and (l in letters or l in DASH):
            if l in letters:
                cur[2].append(l)
            continue
        if cur is not None and want_desc:
            cur[3] = l; want_desc = False
            continue
        rows.append([idx, None, [], l])  # stray line: reported
    return [(r[0], r[1], "".join(r[2]), r[3]) for r in rows]


def pass_b(words, letters):
    hw = {w[4]: w for w in words if w[4] in ("Index", "Part", "Description")}
    if len(hw) < 3:
        return []
    head_y = hw["Part"][3]
    lcols = {w[4]: ((w[0] + w[2]) / 2) for w in words if w[4] in letters and abs(w[3] - head_y) < 2}
    if not lcols:
        return []
    x_desc = hw["Description"][0] - 3
    x_part = hw["Part"][0] - 20
    x_let0 = min(lcols.values()) - 10
    by = {}
    for w in words:
        if w[1] > head_y + 2:
            by.setdefault(round(w[3]), []).append(w)
    rows, idx = [], None
    for y in sorted(by):
        ws = sorted(by[y], key=lambda w: w[0])
        t = [w[4] for w in ws]
        if t and t[0] == "Index" or "Only" in t and "Those" in t:
            break
        ix = [w[4] for w in ws if w[2] < x_part]
        nums = [w[4] for w in ws if x_part <= w[0] < x_let0 and NUM.match(w[4])]
        lets = sorted(w[4] for w in ws if x_let0 <= w[0] < x_desc and w[4] in letters
                      and abs((w[0] + w[2]) / 2 - lcols[w[4]]) < 8)
        desc = norm(" ".join(w[4] for w in ws if w[0] >= x_desc))
        stray = [w[4] for w in ws if x_let0 <= w[0] < x_desc and w[4] not in letters and w[4] not in DASH]
        if stray:
            desc = norm(" ".join(stray) + " " + desc)
        if ix and IDX.match(" ".join(ix)):
            idx = ix[0]
        if not nums and not desc:
            continue
        if len(nums) != 1:
            rows.append((idx, None, "".join(lets), desc or " ".join(w[4] for w in ws)))
            continue
        rows.append((idx, nums[0], "".join(lets), desc))
    return rows


def read(pages):
    """pages: list of (text, words) -> (rows, held, keys)"""
    out, held, keys = [], [], {}
    for i, (text, words) in enumerate(pages):
        km = keymap(text)
        if not km:
            continue
        keys.update(km)
        letters = set(km)
        a = pass_a(text, letters)
        b = pass_b(words, letters)
        bl = list(b)
        n = 0
        sec = heading(text)
        for r in a:
            if r[1] and r in bl:
                bl.remove(r); n += 1
                out.append((i + 1, n, r, sec, km))
            else:
                held.append({"page": i + 1, "a": list(r)})
        held += [{"page": i + 1, "b": list(r)} for r in bl]
    return out, held, keys


def main(pdf, outp, label):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    doc = pymupdf.open(pdf)
    if not doc.permissions & pymupdf.PDF_PERM_COPY:
        raise SystemExit("copy/extraction not permitted by the PDF's owner password: not read")
    rows, held, keys = read([(p.get_text(), p.get_text("words")) for p in doc])
    secs, seen, lines, conflicts = {}, {}, [], []
    for pg, n, (idx, num, lets, desc), sec, km in rows:
        d = desc
        if set(lets) != set(km):
            d += " [applies to: " + ", ".join(f"{km[l][0]} {km[l][1]}" for l in sorted(set(lets) & set(km))) + "]"
        if num in seen:
            if seen[num] != d:
                conflicts.append({"number": num, "a": seen[num], "b": d})
            continue
        seen[num] = d
        code = secs.setdefault(label + " — " + sec, str(len(secs)))
        lines.append(f"{pg}|{n}|{num}|{d.replace('|', '/')[:200]}|{code}")
    if conflicts:
        bad = {c["number"] for c in conflicts}
        lines = [l for l in lines if l.split("|")[2] not in bad]
    out = {"doc": sha, "pages": doc.page_count, "agree": bool(lines) and not held and not conflicts,
           "held": held, "conflicts": conflicts, "keys": keys, "rows_total": len(rows), "numbers": len(lines),
           "pages_read": sorted({r[0] for r in rows}), "sections": {c: s for s, c in secs.items()},
           "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(lines),
                      "pages_read": out["pages_read"], "keys": keys, "held": held[:10], "conflicts": conflicts[:5]},
                     ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
