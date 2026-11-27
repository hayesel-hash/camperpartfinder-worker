"""Cross-document check for dometic_sealand_parts_list.py outputs: a SeaLand number printed with different colour words on
different sheets (385340177 "BOWL WATER SUPPLY HOSE - WHITE" on one sheet, "HOSE, SUPPLY - BONE, EBONY, PLAT, TEAL" on
another) is removed from every output's rows and listed under `colour_conflicts`, so no colour is guessed.
usage: python3 -I sealand_colour_conflicts.py <out1.json> [<out2.json> ...]   (rewrites the files in place)"""
import json, re, sys
COL = {"WHITE", "WHT", "BONE", "EBONY", "EBY", "BLACK", "BLK", "CHROME", "CHR", "PLAT", "PLATINUM", "TEAL", "GREY", "GRAY",
       "SILVER", "BEIGE", "SAND", "BLUE"}
outs = {f: json.load(open(f)) for f in sys.argv[1:]}
words = {}
for f, r in outs.items():
    texts = [(l.split("|")[2], l.split("|")[3]) for l in r["rows"].splitlines()]
    texts += [(o["number"], o["first"]) for o in r.get("other_wordings", [])] + [(o["number"], o["here"]) for o in r.get("other_wordings", [])]
    for n, t in texts:
        c = frozenset(w for w in re.findall(r"[A-Z]+", t.upper()) if w in COL)
        words.setdefault(n, set()).add(c)
bad = {n for n, cs in words.items() if len({c for c in cs if c}) > 1}
for f, r in outs.items():
    keep, gone = [], []
    for l in r["rows"].splitlines():
        (gone if l.split("|")[2] in bad else keep).append(l)
    r["rows"] = "\n".join(keep); r["colour_conflicts"] = sorted({l.split("|")[2] for l in gone})
    r["numbers"] = len(keep)
    json.dump(r, open(f, "w"), ensure_ascii=False, indent=0)
    print(f.split("/")[-1], "kept", len(keep), "removed", len(gone))
print("conflicting numbers:", len(bad))
