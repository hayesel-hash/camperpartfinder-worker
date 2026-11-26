"""Wrap a two-pass reader output (doc, pages, agree, sections, rows) as a supplied-documents drop JSON in other_out/.
usage: python3 -I to_drop_json.py <reader.json> <title> <extraction> <verification> <scratch>"""
import json, os, sys
r = json.load(open(sys.argv[1]))
S = sys.argv[5]
out = {"doc": r["doc"], "title": sys.argv[2], "pages": r["pages"], "review_state": "reviewed" if r["agree"] else "unreviewed",
       "extraction": sys.argv[3], "verification": sys.argv[4], "sections": r["sections"], "rows": r["rows"]}
os.makedirs(os.path.join(S, "other_out"), exist_ok=True)
json.dump(out, open(os.path.join(S, "other_out", r["doc"][:16] + ".json"), "w"), ensure_ascii=False)
print(r["doc"][:16], out["review_state"], len(r["rows"].splitlines()))
