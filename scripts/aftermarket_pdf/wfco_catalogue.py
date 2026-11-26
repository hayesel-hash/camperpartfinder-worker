"""Two-pass identity reader for the WFCO product catalogue (power centers, converters, panels, switches).

Identities come from two places only:
  * "Part # WF-..., Door Assembly for ..." lines on the door-assembly pages;
  * the model header row of each "SPECIFICATIONS" table (e.g. WF-8935-AD ... WF-8975-AD).
Model numbers mentioned in prose are not taken. Description = the page's series heading
(largest type on the page), or the door-assembly text as printed.

Pass A: text lines (pymupdf get_text). Pass B: word positions (words on the same baseline as
"SPECIFICATIONS"; the word after "Part #" plus the rest of that line). Both must agree.
The crossover chart (printed page 30) is a 72-dpi raster in the supplied copy and is not read here.

usage: python3 -I wfco_catalogue.py <pdf> <out.json>    (writes a supplied-documents reader JSON)
"""
import hashlib, json, re, sys

MODEL = re.compile(r"^(WF-\d{4,5}[A-Z0-9/\-]*|T-\d{2}[A-Z]*|EM-\d{2})$")
DOOR = re.compile(r"^Part #\s*(WF-[A-Z0-9/\-]+),\s*(.+?)\s*$")


def heading(spans):
    """Series heading: the title band at the top of the page (topmost span of 15 pt or more within
    90 pt of the top, plus every span of the same size in that band; slogans use other sizes)."""
    top = sorted((s for s in spans if s["y0"] < 90 and s["size"] >= 15 and s["text"].strip()), key=lambda s: s["y0"])
    if not top:
        return ""
    size = top[0]["size"]
    keep = sorted((s for s in top if abs(s["size"] - size) < 0.3), key=lambda s: (round(s["y0"] / 6), s["x0"]))
    return " ".join(" ".join(s["text"].split()) for s in keep)


def pass_a(lines, head):
    rows = []
    for k, line in enumerate(lines):
        m = DOOR.match(line)
        if m:
            rows.append((m.group(1), m.group(2)))
            continue
        toks = line.split()
        if toks and toks[0] == "SPECIFICATIONS":
            found = [t for t in toks[1:] if MODEL.match(t)]
            j = k + 1
            while j < len(lines) and lines[j].split() and all(MODEL.match(t) for t in lines[j].split()):
                found += lines[j].split(); j += 1
            rows += [(t, head) for t in found]
    return rows


def pass_b(words, head):
    """words: (x0, y0, x1, y1, text, block, line, wordno)."""
    rows = []
    for i, w in enumerate(words):
        if w[4] == "Part" and i + 2 < len(words) and words[i + 1][4] == "#":
            num = words[i + 2][4].rstrip(",")
            same = [v for v in words[i + 3:] if (v[5], v[6]) == (w[5], w[6])]
            if num.startswith("WF-") and words[i + 2][4].endswith(","):
                rows.append((num, " ".join(v[4] for v in same)))
        if w[4] == "SPECIFICATIONS":
            yc = (w[1] + w[3]) / 2
            band = sorted((v for v in words if abs((v[1] + v[3]) / 2 - yc) <= 4 and v[0] > w[2] and MODEL.match(v[4])),
                          key=lambda v: v[0])
            rows += [(v[4], head) for v in band]
    return rows


def page_inputs(page):
    lines = [l.strip() for l in page.get_text().splitlines() if l.strip()]
    words = [tuple(w) for w in page.get_text("words")]
    spans = [{"text": s["text"], "size": s["size"], "x0": s["bbox"][0], "y0": s["bbox"][1]}
             for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]]
    return lines, words, spans


def read(pages_in):
    """pages_in: list of (lines, words, spans). Returns rows [(page, n, number, desc)], diffs."""
    rows, diffs = [], []
    for i, (lines, words, spans) in enumerate(pages_in):
        head = heading(spans)
        a, b = pass_a(lines, head), pass_b(words, head)
        if sorted(a) != sorted(b):
            diffs.append({"page": i + 1, "only_a": [x for x in a if x not in b][:5], "only_b": [x for x in b if x not in a][:5]})
        rows += [(i + 1, n, num, desc) for n, (num, desc) in enumerate(a, 1)]
    return rows, diffs


def main(pdf, outp):
    import pymupdf
    sha = hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    d = pymupdf.open(pdf)
    rows, diffs = read([page_inputs(p) for p in d])
    seen, lines = set(), []
    for pg, n, num, desc in rows:
        if num in seen or not desc:
            continue
        seen.add(num); lines.append(f"{pg}|{n}|{num}|{desc.replace('|', '/')}|0")
    out = {"doc": sha, "pages": d.page_count, "agree": not diffs and bool(lines), "diffs": diffs, "rows_total": len(rows),
           "numbers": len(seen), "sections": {"0": "WFCO 2026 product catalogue"}, "rows": "\n".join(lines)}
    json.dump(out, open(outp, "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "agree": out["agree"], "rows": len(rows), "numbers": len(seen), "diffs": diffs[:3]})[:1500])


if __name__ == "__main__":
    main(*sys.argv[1:3])
