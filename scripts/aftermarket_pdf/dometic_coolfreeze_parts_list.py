"""Two-pass reader for the Dometic LLC (Waeco) CoolFreeze CF portable-fridge parts list (form 3312482.023, 2010-04):
one table page per model (or model pair) with Index | Part Number | [Model] | Description, where two-model pages carry
a legend "CF-035AC110 = A / CF-040AC110 = B" and A / B / -- marks in the Model column. Under a row, "fits serial
numbers:" lines give serial ranges; "(same p/n as above)" rows add another model's serial ranges to the row above.
"*" after a range = "WAECO branded units" (the page footnote); "**" after a number = "see page 16 for pictures" (dropped).

Pass A: text-line order (get_text). Pass B: word boxes cut into the header columns. Only rows both passes give
identically are kept; the drop row description is the printed description plus "[models: ...]" when not every model
of the page is marked, plus the serial ranges.
usage: python3 -I dometic_coolfreeze_parts_list.py <pdf> <out.json>"""
import hashlib, json, re, sys
import pymupdf

NUM = re.compile(r"^(?=[0-9A-Z-]*\d)[0-9A-Z][0-9A-Z-]{5,}$")
RANGE = re.compile(r"^\.*([A-Z]{0,2}\d{8}-[A-Z]{0,2}\d{8})(,?\s*\*)?(\s*&\s*higher)?,?$")
MODEL = re.compile(r"^CF-\d{3}(?:DC|AC110)$")
IDX = re.compile(r"^(\d{1,2}|[A-Z])$")
MARK = {"A", "B", "--"}


def range_text(m):
    t = m.group(1)
    if m.group(3):
        t += " & higher"
    if m.group(2):
        t += " (WAECO branded units)"
    return t


def page_models(page):
    W = page.get_text("words")
    legend = {}
    for i, w in enumerate(W):
        if MODEL.match(w[4]) and i + 2 < len(W) and W[i + 1][4] == "=" and W[i + 2][4] in ("A", "B"):
            legend[W[i + 2][4]] = w[4]
    if legend:
        return legend
    ms = []
    for w in W:
        if MODEL.match(w[4]) and w[4] not in ms:
            ms.append(w[4])
    return {"A": ms[0]} if len(ms) == 1 else {}


def finish(rows, legend):
    out = []
    for r in rows:
        desc = r["desc"]
        models = [legend[m] for m in ("A", "B") if m in r["models"] and m in legend]
        if len(legend) > 1 and len(models) < len(legend):
            desc += " [models: " + ", ".join(models) + "]"
        groups = [(g, rs) for g, rs in r["serials"] if rs]
        if len(groups) == 1:
            desc += " [fits serial numbers: " + ", ".join(groups[0][1]) + "]"
        elif groups:
            parts = []
            for g, rs in groups:
                names = ", ".join(legend[m] for m in ("A", "B") if m in g and m in legend)
                parts.append(f"{names}: " + ", ".join(rs))
            desc += " [fits serial numbers " + "; ".join(parts) + "]"
        out.append((r["num"], " ".join(desc.split())))
    return out


def pass_a(page, legend):
    L = [l.strip() for l in page.get_text().splitlines()]
    L = [l for l in L if l]
    try:
        k = L.index("Description") + 1
    except ValueError:
        return []
    two = len(legend) > 1
    rows, cur, in_serial = [], None, False
    while k < len(L):
        s = L[k]
        if s.startswith("*"):
            break
        m = RANGE.match(s)
        if in_serial and m and cur is not None:
            cur["serials"][-1][1].append(range_text(m)); k += 1; continue
        if s.startswith("fits serial numbers"):
            in_serial = True; k += 1; continue
        in_serial = False
        num = re.sub(r"\s*\*\*$", "", s)
        if NUM.match(num) or s.startswith("(same p/n as above)"):
            j = k + 1; marks = []
            while two and j < len(L) and L[j] in MARK:
                marks.append(L[j]); j += 1
            models = {x for x in marks if x != "--"} if two else {"A"}
            desc = L[j] if j < len(L) else ""
            if s.startswith("(same p/n"):
                if cur is not None:
                    cur["models"] |= models
                    cur["serials"].append((tuple(sorted(models)), []))
            else:
                cur = {"num": num, "models": set(models), "desc": desc, "serials": [(tuple(sorted(models)), [])]}
                rows.append(cur)
            k = j + 1; continue
        k += 1
    return finish(rows, legend)


def pass_b(page, legend):
    W = page.get_text("words")
    hdr = {w[4]: w for w in W if w[4] in ("Index", "Part", "Model", "Description")}
    if "Part" not in hdr or "Description" not in hdr:
        return []
    yh = hdr["Description"][1] + 3
    xp = hdr["Part"][0] - 3; xd = hdr["Description"][0] - 3
    xm = hdr["Model"][0] - 3 if "Model" in hdr else xd
    lines = {}
    for w in W:
        if w[1] <= yh:
            continue
        key = round((w[1] + w[3]) / 2)
        k = next((k for k in lines if abs(k - key) <= 2), key)
        lines.setdefault(k, []).append(w)
    rows, cur = [], None
    for y in sorted(lines):
        ws = sorted(lines[y], key=lambda w: w[0])
        part = [w[4] for w in ws if xp <= w[0] < xm]
        marks = [w[4] for w in ws if xm <= w[0] < xd]
        desc = " ".join(w[4] for w in ws if w[0] >= xd)
        if (part and part[0].startswith("*")) or (not part and desc.startswith("*")):
            break
        if part[:3] == ["fits", "serial", "numbers:"] or (not part and not marks and desc):
            m = RANGE.match(desc)
            if m and cur is not None:
                if part:
                    cur["serials"][-1] = (cur["serials"][-1][0], cur["serials"][-1][1] + [range_text(m)])
                else:
                    cur["serials"][-1][1].append(range_text(m))
            continue
        if not part:
            continue
        ptxt = " ".join(part)
        models = {x for x in marks if x != "--"} if len(legend) > 1 else {"A"}
        if ptxt.startswith("(same p/n as above)"):
            if cur is not None:
                cur["models"] |= models
                cur["serials"].append((tuple(sorted(models)), []))
            continue
        num = part[0]
        if NUM.match(num) and all(p == "**" for p in part[1:]):
            cur = {"num": num, "models": set(models), "desc": desc, "serials": [(tuple(sorted(models)), [])]}
            rows.append(cur)
    return finish(rows, legend)


def main(pdf, outp):
    raw = open(pdf, "rb").read(); sha = hashlib.sha256(raw).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs, sections = [], [], {}
    for i, p in enumerate(d):
        legend = page_models(p)
        if not legend:
            continue
        a, b = pass_a(p, legend), pass_b(p, legend)
        if not a and not b:
            continue
        if a != b:
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:6], "only_b": [x for x in b if x not in a][:6]})
        sec = str(len(sections))
        sections[sec] = "Dometic (Waeco) CoolFreeze " + " / ".join(legend[m] for m in ("A", "B") if m in legend) + \
            " portable refrigerator, parts list form 3312482.023 (2010-04)"
        rows += [(i + 1, n, num, desc, sec) for n, (num, desc) in enumerate([x for x in a if x in b], 1)]
    lines = [f"{pg}|{n}|{num}|{desc.replace('|', '/')}|{sec}" for pg, n, num, desc, sec in rows if desc]
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len({r[2] for r in rows}), "sections": sections, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": out["numbers"],
                      "diffs": diffs[:3]}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
