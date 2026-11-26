"""Two-pass identity reader for Dexter's parts kit catalogue LIT-119-00 (03/2017).

Every kit is printed as a block:
    <kit name>                         <kit number>      (same baseline, number at the right)
    <one or two lines of kit description>
    Dx Part No.   Quantity   Parts Description
    <component number>  <qty>  <component description>   (one row per component)

Identities taken: the kit number (description = kit name + " " + kit description) and every
component number in the kit tables (description as printed in the "Parts Description" column).
Rows whose description is "Instruction Sheet" / "Installation Sheet" (and LIT- manuals) are literature, not parts, and are left out.
Numbers mentioned inside descriptions ("Fits E/H brake actuator K71-650-00 ...") are never taken.

Pass A: text blocks (pymupdf get_text("blocks")): the kit title is the rest of the kit number's
        block (or the block before it); component numbers, quantities and descriptions are
        separate runs of lines of equal length.
Pass B: word positions: the kit number is the right-hand word on the kit-title baseline; table
        cells are read by the x position of the "Dx", "Quantity" and "Parts" header words.
Both passes must give the same (number, description) list per page.

usage: python3 -I dexter_lit119.py <pdf> <out.json> [section label]   (writes a supplied-documents reader JSON)
"""
import hashlib, json, re, sys

NUM = re.compile(r"^(?:K\d{2}|\d{3})-\d{3}-\d{2}$")
ROWNUM = re.compile(r"^(?:(?:K\d{2}|\d{3})|LIT)-\d{3}-\d{2}$")   # LIT-608-00 = a manual listed in a kit
QTY = re.compile(r"^\d{1,3}$")
LITERATURE = re.compile(r"^(?:Instruction|Installation) Sheet\b", re.I)
TOP = {"Complete Brake Assemblies", "Brake Components", "Hub Components", "Complete Hub & Hub-Drum Kits",
       "Suspension Components"}
FURNITURE = re.compile(r"^(Rugged\b|www\.|\d+\s*\|\s*\d\d/\d{4}$|\d\d/\d{4}\s*\|\s*\d+$)")


def keep_row(num, desc):
    return not num.startswith("LIT-") and not LITERATURE.match(desc)


def clean(s):
    return " ".join(s.split())


def kit_desc(name, desc_lines):
    """Kit name and description joined with a space: where the printed title wraps onto a second
    line, the text order and the baseline order split title/description differently, so no
    separator is inserted between them."""
    text = clean(" ".join([name] + list(desc_lines)))
    return text.split(" Note: ")[0]   # usage notes ("Note: Kit is not to be used on ...") are not part of the name


def stop_line(line):
    return line in TOP or bool(FURNITURE.match(line)) or (line.upper() == line and re.search(r"[A-Z]{3}", line) is not None)


def pass_a(blines):
    """blines: [(block_no, text)] stripped non-empty text lines of one page in reading order
    (pymupdf text blocks). Returns [(number, description)]."""
    blk = [b for b, _ in blines]
    lines = [t for _, t in blines]
    rows = []
    i, last_end = 0, 0
    while i < len(lines):
        if NUM.match(lines[i]) and i > last_end:
            # kit number: the title is the rest of its text block, or the block just before it when
            # the number stands alone; the description runs to the table header
            j = i + 1
            desc = []
            while j < len(lines) and lines[j] != "Dx Part No.":
                desc.append(lines[j]); j += 1
            same = [t for b, t in blines[last_end:i] if b == blk[i]]
            if not same and blk[i - 1] != blk[i]:
                same = [t for b, t in blines[last_end:i] if b == blk[i - 1]]
            if j < len(lines) and len(desc) <= 5 and same and not any(stop_line(t) or ROWNUM.match(t) for t in same):
                rows.append((lines[i], kit_desc(" ".join(same), desc)))
                i = j
                continue
        if lines[i] == "Dx Part No." and lines[i + 1:i + 3] == ["Quantity", "Parts Description"]:
            j = i + 3
            nums = []
            while j < len(lines) and ROWNUM.match(lines[j]):
                nums.append(lines[j]); j += 1
            qtys = lines[j:j + len(nums)]
            descs = lines[j + len(nums):j + 2 * len(nums)]
            if nums and all(QTY.match(q) for q in qtys) and len(descs) == len(nums):
                rows += [(n, clean(d)) for n, d in zip(nums, descs) if keep_row(n, clean(d))]
                i = last_end = j + 2 * len(nums)
                continue
        i += 1
    return rows


def baselines(words, tol=2.5):
    """Group words (x0, y0, x1, y1, text, ...) into lines by vertical centre; sorted top to bottom."""
    out = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        yc = (w[1] + w[3]) / 2
        if out and abs(out[-1][0] - yc) <= tol:
            out[-1][1].append(w)
        else:
            out.append([yc, [w]])
    return [(yc, sorted(ws, key=lambda w: w[0])) for yc, ws in out]


def pass_b(words):
    rows = []
    lines = baselines(words)
    k = 0
    while k < len(lines):
        yc, ws = lines[k]
        texts = [w[4] for w in ws]
        if texts[:3] == ["Dx", "Part", "No."] and "Quantity" in texts and "Parts" in texts:
            num_x = ws[0][0]
            qty_x = next(w[0] for w in ws if w[4] == "Quantity")
            desc_x = next(w[0] for w in ws if w[4] == "Parts")
            # kit header: the nearest line above whose right-most word is a number right of desc_x
            up = k - 1
            while up >= 0 and not (lines[up][1][-1][0] > desc_x and NUM.match(lines[up][1][-1][4])
                                   and lines[up][1][0][0] < qty_x):
                up -= 1
            if up >= 0 and k - up <= 6:
                head = lines[up][1]
                name = " ".join(w[4] for w in head[:-1] if w[0] >= num_x - 3)
                desc = [" ".join(w[4] for w in lines[m][1] if w[0] >= num_x - 3) for m in range(up + 1, k)]
                rows.append((head[-1][4], kit_desc(name, desc)))
            k += 1
            while k < len(lines):
                cells = [w for w in lines[k][1] if w[0] >= num_x - 3]
                if not cells:
                    k += 1
                    continue
                if abs(cells[0][0] - num_x) > 3 or not ROWNUM.match(cells[0][4]):
                    break
                qty = [w[4] for w in cells[1:] if w[0] < desc_x - 3]
                desc = clean(" ".join(w[4] for w in cells[1:] if w[0] >= desc_x - 3))
                if len(qty) == 1 and QTY.match(qty[0]) and desc and keep_row(cells[0][4], desc):
                    rows.append((cells[0][4], desc))
                k += 1
            continue
        k += 1
    return rows


def rotated_boxes(page):
    """Boxes of text lines that do not run left to right (the section label printed up the page edge)."""
    return [l["bbox"] for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) if abs(l["dir"][0] - 1) > 0.01]


def upright(w, boxes):
    cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
    return not any(b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1 for b in boxes)


def page_inputs(page):
    lines = [(b[5], l.strip()) for b in page.get_text("blocks") for l in b[4].splitlines() if l.strip()]
    boxes = rotated_boxes(page)
    words = [tuple(w[:5]) for w in page.get_text("words") if upright(w, boxes)]
    return lines, words


def read(pages_in):
    """pages_in: list of (block lines, words). Returns rows [(page, n, number, desc)], diffs."""
    rows, diffs = [], []
    for i, (lines, words) in enumerate(pages_in):
        a, b = pass_a(lines), pass_b(words)
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        rows += [(i + 1, n, num, desc) for n, (num, desc) in enumerate(a, 1)]
    return rows, diffs


def main(pdf, outp, label="Dexter LIT-119-00 parts kit catalogue (03/2017)"):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs = read([page_inputs(p) for p in d])
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')[:200]}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"0": label}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "diffs": diffs[:4]})[:3000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
