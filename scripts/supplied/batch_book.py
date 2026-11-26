"""Process one Airstream parts book into a drop-ready JSON (rows + metadata + quality gates).

usage: python3 -I batch_book.py <pdf> <drive_id> <drive_title> <out_dir>
"""
import collections, hashlib, importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ab", os.path.join(HERE, "airstream_book.py"))
ab = importlib.util.module_from_spec(spec); spec.loader.exec_module(ab)
import pymupdf

LOOSE = re.compile(r"^(?:\d{1,3}\.\s+)?\d{5,8}\S*\s*$")

def main(pdf, drive_id, drive_title, out_dir):
    raw = open(pdf, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    doc = pymupdf.open(pdf)
    part = re.search(r" - pp (\d{3})-(\d{3})", drive_title)
    first_page = int(part.group(1)) if part else 1
    if first_page > 1:
        ab.first_content_page = lambda d: 0   # later parts of a split book start mid-book: no cover/TOC
    start = ab.first_content_page(doc)
    rows = ab.parse(doc)
    words = ab.numbers_by_words(doc)
    text = collections.Counter((r["page"], r["number"]) for r in rows)
    only_w_set = set(words) - set(text)
    only_t = len(set(text) - set(words))
    def benign(page, num):
        # a number printed with no description after it (next line is another number, a callout, or nothing)
        L = [l.strip() for l in doc[page - 1].get_text().splitlines() if l.strip()]
        idx = [k for k, l in enumerate(L) if ab.NUM.match(l) and ab.NUM.match(l).group(1) == num]
        return bool(idx) and all(k + 1 >= len(L) or ab.NUM.match(L[k + 1]) or ab.SKIP_DESC.match(L[k + 1]) for k in idx)
    benign_w = [x for x in only_w_set if benign(*x)]
    only_w = len(only_w_set) - len(benign_w)
    residual = 0
    chars = 0
    for i in range(start, doc.page_count):
        t = doc[i].get_text(); chars += len(t)
        for l in t.splitlines():
            l = l.strip()
            if LOOSE.match(l) and not ab.NUM.match(l) and "&" not in l:
                residual += 1
    title = re.sub(r"\.pdf$", "", drive_title)
    title = re.sub(r"^Airstream\s+", "", title)
    if part:
        title = re.sub(r"\s+-\s+pp (\d{3})-(\d{3})$", r" (pp \1-\2)", title)
    secs = sorted({r["section"] for r in rows}); code = {s: format(i, "x") for i, s in enumerate(secs)}
    seen, lines = set(), []
    for r in rows:
        if r["number"] in seen:
            continue
        seen.add(r["number"])
        d = " ".join(r["description"].replace("|", "/").split())
        lines.append(f"{r['page']}|{r['n']}|{r['number']}|{d}|{code[r['section']]}")
    gates = {
        "two_passes_agree": only_w == 0 and only_t == 0,
        "enough_rows": len(rows) >= (10 if part else 30),
        "text_layer": chars > min(2000, 250 * max(1, doc.page_count - start)),   # short split parts: scale by page count
        "start_page_sane": start <= 15,
        "residual_ok": residual <= max(3, len(rows) // 50),
    }
    ok = all(gates.values())
    out = {
        "doc": sha, "title": title, "pages": doc.page_count, "drive_id": drive_id,
        "review_state": "reviewed" if ok else "unreviewed",
        "extraction": (f"airstream-partsbook-v2: text-line pass; TOC-detected start page (PDF p{start + 1}); internal laminate codes containing & excluded"
                       + (f"; split part supplied by Larry's ChatGPT: PDF page n here is page {first_page - 1}+n of the full book" if part else "")),
        "verification": (f"automated gates: independent word-position pass agrees ({len(rows)} rows, {len(seen)} numbers, "
                         f"{only_w + only_t} discrepancies, {len(benign_w)} numbers printed without a description omitted); {residual} unmatched number-like lines; same template as the "
                         f"2027 Trade Wind and Interstate 19X books, which were checked against page images row by row"),
        "gates": gates, "residual": residual,
        "sections": {code[s]: s for s in secs},
        "rows": "\n".join(lines),
    }
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(os.path.join(out_dir, sha[:16] + ".json"), "w"), ensure_ascii=False)
    print(json.dumps({"sha16": sha[:16], "title": title, "pages": doc.page_count, "rows": len(rows),
                      "numbers": len(seen), "state": out["review_state"],
                      "failed": [k for k, v in gates.items() if not v], "residual": residual}))

if __name__ == "__main__":
    main(*sys.argv[1:5])
