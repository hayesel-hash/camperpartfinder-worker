"""Airstream parts book reader v2 (TOC-detected start; -MB/-5 style numbers): (page, n, number, description, section, subsection)."""
import json, re, sys, collections
import pymupdf

NUM = re.compile(r"^(?:\d{1,3}\.\s+)?(S[0-9]{5,6}|[0-9]{4,8}[A-Z]{0,2}(?:-[0-9A-Z]{1,6}(?:\.[0-9]{3})?){0,2})\*?\s*$")
TOC = re.compile(r"TABLE OF CONTENTS|\.{8,}\s*\d*\s*$")

def first_content_page(doc):
    last = 0
    for i in range(min(20, doc.page_count)):
        t = doc[i].get_text()
        if i == 0 or sum(1 for l in t.splitlines() if TOC.search(l)) >= 3 or "TABLE OF CONTENTS" in t:
            last = i
    return last + 1

SKIP_DESC = re.compile(r"^(?:\d{1,3}\.\s*)?$|^\d{1,3}$")

def lines_of(page):
    return [l.strip() for l in page.get_text().splitlines()]

def parse(doc):
    out = []
    start = first_content_page(doc)
    for i, page in enumerate(doc):
        lines = lines_of(page)
        if i < start:   # cover + table of contents
            continue
        section = next((l for l in lines[1:4] if l and l.isupper()), "")
        sub, n, k = "", 0, 0
        while k < len(lines):
            l = lines[k]
            m = NUM.match(l)
            if m and "&" not in l:
                j = k + 1
                while j < len(lines) and not lines[j]:
                    j += 1
                desc = lines[j] if j < len(lines) else ""
                if desc and not NUM.match(desc) and not SKIP_DESC.match(desc):
                    n += 1
                    out.append({"page": i + 1, "n": n, "number": m.group(1), "description": desc,
                                "section": section, "subsection": sub})
                    k = j + 1
                    continue
            elif l and not l.isupper() and k > 1 and not re.match(r"^\d", l):
                # a line that isn't a part row and isn't the description of one: subsection title
                prev = next((x for x in reversed(lines[:k]) if x), "")
                if not NUM.match(prev):
                    sub = l
            k += 1
    return out

def numbers_by_words(doc):
    """Independent pass: rebuild lines from word boxes, collect part-number tokens."""
    found = collections.Counter()
    start = first_content_page(doc)
    for i, page in enumerate(doc):
        if i < start:
            continue
        rows = collections.defaultdict(list)
        for x0, y0, x1, y1, w, b, ln, wn in page.get_text("words"):
            rows[(b, ln)].append((x0, w))
        for key, words in rows.items():
            text = " ".join(w for _, w in sorted(words))
            m = NUM.match(text)
            if m and "&" not in text:
                found[(i + 1, m.group(1))] += 1
    return found

if __name__ == "__main__":
    doc = pymupdf.open(sys.argv[1])
    rows = parse(doc)
    json.dump(rows, open(sys.argv[2], "w"))
    wordset = numbers_by_words(doc)
    textset = collections.Counter((r["page"], r["number"]) for r in rows)
    only_words = set(wordset) - set(textset)
    only_text = set(textset) - set(wordset)
    print(json.dumps({"start_page": first_content_page(doc) + 1, "rows": len(rows), "unique_numbers": len({r['number'] for r in rows}),
                      "pages_with_rows": len({r['page'] for r in rows}),
                      "word_pass_numbers": len(wordset), "only_in_word_pass": len(only_words),
                      "only_in_text_pass": len(only_text),
                      "examples_only_words": sorted(only_words)[:8]}))
