"""Relationship graph extractor v2 — layout-aware, typed, evidence-first.

Staging only. Nothing here publishes, verifies or infers interchangeability.

Why v2 exists (see benchmarks/run_relationship_benchmark.py):
  * v1 relationship grammar used re.fullmatch on a single PDF text line, so any
    extra word on the line ("12345 Seal kit - replaced by 67890") lost the edge.
  * v1 supersession tables had to be exactly two columns; real parts lists have
    description / remarks / qty columns.
  * v1 flagged a whole page as "qualified" if the word kit/only/if/note or an
    asterisk appeared anywhere on it, which is nearly every spare-parts page.
  * v1 could not read reverse wording ("B replaces A", "B ersetzt A"), stacked
    "Old part number / New part number" labels, or distributor product cards
    where the article number and the manufacturer number sit on different lines.

Edge types emitted (kind):
  supersedes   a = old number, b = new number           (direction preserved)
  oem_xref     a = distributor SKU, b = manufacturer no.  (distributor assertion)
  fits         a = part / SKU, b = stated model scope     (scope, not substitution)

Each edge carries `qualifiers` (conditions that change validity: only-with,
except, requires, adapter ...) and `scope` (date / serial ranges that bound but
do not weaken the statement). Clean = no qualifiers. Qualified edges stay
staged for review; they are never silently discarded.
"""
from __future__ import annotations

import hashlib
import re

VERSION = "relationship-graph-v2"

CODE_RE = r"[A-Z0-9][A-Z0-9./-]{3,24}"
_CODE = re.compile(r"(?<![A-Za-z0-9./-])(" + CODE_RE + r")(?![A-Za-z0-9/-])")


def valid_code(s: str) -> bool:
    s = s.rstrip(".")
    return bool(re.fullmatch(CODE_RE, s) and re.search(r"\d", s)
                and not re.fullmatch(r"\d{4}", s)               # years
                and not re.fullmatch(r"\d+[.,]\d{1,2}", s)      # prices
                and not re.fullmatch(r"\d+(?:[.,]\d+)?(?:mm|cm|kg|v|w|l)", s, re.I))


def codes_in(text: str):
    return [(m.start(1), m.group(1).rstrip(".")) for m in _CODE.finditer(text) if valid_code(m.group(1))]


# ------------------------------------------------------------------ grammar
FORWARD = re.compile(  # A ... replaced by B   (A old, B new)
    r"(?:\bis\s+|\bwird\s+)?(?:\breplaced\s+(?:by|with)|\bsuperseded\s+(?:by|with)|\bersetzt\s+(?:durch|von)"
    r"|\bnachfolger(?:artikel)?\s*(?:ist)?\s*:?|\bsuccessor\s*(?:is)?\s*:?|\bnew\s+(?:part\s*)?(?:no\.?|number|nr\.?)\s*:?"
    r"|\bneue?\s+(?:art(?:ikel)?\.?\s*-?\s*(?:nr|nummer)\.?|teilenummer)\s*:?)\s*(?:part\s*(?:no\.?|number)?\s*)?",
    re.I)
REVERSE = re.compile(  # B ... replaces A      (A old, B new)
    r"\b(?:replaces|supersedes|ersetzt(?!\s+(?:durch|von))|nachfolger(?:artikel)?\s+von|successor\s+(?:to|of))\s*"
    r"(?:part\s*(?:no\.?|number)?\s*|art(?:ikel)?\.?\s*-?\s*nr\.?\s*)?", re.I)
AMBIGUOUS = re.compile(r"\b(?:ersatz\s+für|replacement\s+for|alternative\s+(?:to|for)|equivalent\s+to)\s*", re.I)
NEGATION = re.compile(r"\b(?:not|nicht|kein(?:e|en)?|no\s+longer\s+compatible|never)\b", re.I)
QUALIFIER = re.compile(
    r"\b(?:only|nur|except|außer|ausser|unless|requires?|benötigt|erforderlich|with\s+adapter|mit\s+adapter|adapter|"
    r"if|falls|wenn|depending|abhängig|check|prüfen|modification|umbau|in\s+combination|in\s+verbindung)\b", re.I)
SCOPE = re.compile(
    r"\b(?:from|ab|since|seit|until|bis|up\s+to)\s+(?:serial\s*(?:no\.?)?\s*|seriennr\.?\s*|baujahr\s*|model\s+year\s*|production\s*|produktion\s*|week\s*|kw\s*)?"
    r"[A-Z0-9./-]{2,20}(?:\s+(?:production|produktion|onwards?))?", re.I)

OLD_LABEL = re.compile(r"^(?:old|original|obsolete|previous|former|superseded|alte?|bisherige)\s+(?:part\s*|art(?:ikel)?\.?\s*-?\s*)?(?:no\.?|number|nr\.?|nummer|#)\s*:?\s*(" + CODE_RE + r")$", re.I)
NEW_LABEL = re.compile(r"^(?:new|replacement|successor|superseding|current|neue?|nachfolger)\s+(?:part\s*|art(?:ikel)?\.?\s*-?\s*)?(?:no\.?|number|nr\.?|nummer|#)?\s*:?\s*(" + CODE_RE + r")$", re.I)

SKU_LABEL = re.compile(r"\b(?:art(?:ikel)?\.?\s*-?\s*(?:nr|nummer)\.?|bestell\s*-?\s*(?:nr|nummer)\.?|item\s*(?:no\.?|number)|order\s*(?:no\.?|number))\s*[:#]?\s*(\d{5,7})\b", re.I)
MAKERS = ("Dometic", "Thetford", "Truma", "AL-KO", "Lippert", "Fiamma", "Dexter", "Jokon", "Knott", "Norcold",
          "Suburban", "Coleman-Mach", "REMIS", "HWH", "Alde", "Thule", "Carefree", "Carbest", "Webasto", "Eberspächer",
          "Whale", "Shurflo", "Reich", "Seitz", "Hella", "Electrolux", "Cramer", "Smev", "Thule Omnistor")
_MAKER = re.compile(r"\b(" + "|".join(re.escape(m) for m in MAKERS) + r")\b", re.I)
OEM_LABEL = re.compile(
    r"\b(?:hersteller\s*-?\s*(?:nr|nummer)\.?|herst\.?\s*-?\s*nr\.?|oem\s*-?\s*(?:nr|no|number)\.?|original\s*-?\s*(?:nr|nummer|no|number)\.?"
    r"|manufacturer(?:'s)?\s*(?:part\s*)?(?:no\.?|number)|(?:" + "|".join(re.escape(m) for m in MAKERS) + r")\s*(?:part\s*)?(?:nr|no|number)\.?)"
    r"\s*[:#]?\s*(" + CODE_RE + r")", re.I)
FITS = re.compile(r"\b(?:passend\s+für|passend\s+zu|geeignet\s+für|kompatibel\s+mit|fits?(?:\s+models?)?|suitable\s+for|for\s+use\s+with)\s*:?\s*(.{3,130})", re.I)

# Column-role header vocabulary for table analysis.
ROLES = [
    ("old", re.compile(r"(?:old|original|obsolete|previous|former|superseded|alte?|bisherige)\s*(?:part\s*|art(?:ikel)?\.?\s*-?\s*)?(?:no\.?|number|nr\.?|nummer|#)|alt", re.I)),
    ("new", re.compile(r"(?:new|replacement|successor|superseding|current|neue?)\s*(?:part\s*|art(?:ikel)?\.?\s*-?\s*)?(?:no\.?|number|nr\.?|nummer|#)|neu|nachfolger", re.I)),
    ("oem", re.compile(r"hersteller\s*-?\s*(?:nr|nummer)\.?|herst\.?\s*-?\s*nr\.?|oem\s*-?\s*(?:nr|no|number)\.?|original\s*-?\s*(?:nr|nummer)\.?|manufacturer(?:'s)?\s*(?:part\s*)?(?:no\.?|number)", re.I)),
    ("part", re.compile(r"(?:spare\s+|replacement\s+|service\s+)?(?:part|kit|article|art(?:ikel)?\.?|item|order|bestell|ersatzteil)\s*-?\s*(?:no\.?|number|nr\.?|nummer|#|code)|p\s*/\s*n|artikelnummer|teilenummer", re.I)),
    ("maker", re.compile(r"hersteller|manufacturer|brand|marke|fabrikat", re.I)),
    ("desc", re.compile(r"(?:part\s+)?description|designation|désignation|bezeichnung|benennung|omschrijving|beschreibung|part\s+name", re.I)),
    ("remarks", re.compile(r"remarks?|notes?|comments?|bemerkung(?:en)?|hinweis(?:e)?|anmerkung(?:en)?|info", re.I)),
]


# ------------------------------------------------------------------ geometry
def _rows(words, tol=3.0):
    rows = []
    for w in sorted(words, key=lambda w: (round(w[3], 1), w[0])):
        if rows and abs(w[3] - rows[-1]["base"]) <= tol:
            rows[-1]["words"].append(w)
        else:
            rows.append({"base": w[3], "words": [w]})
    for r in rows:
        r["words"].sort(key=lambda w: w[0])
        r["y0"] = min(w[1] for w in r["words"])
        r["y1"] = max(w[3] for w in r["words"])
    return rows


def _segments(row, gap=18.0):
    """Split a baseline row into visually separate runs (columns / adjacent cards)."""
    segs, cur = [], [row["words"][0]]
    for a, b in zip(row["words"], row["words"][1:]):
        if b[0] - a[2] > gap:
            segs.append(cur)
            cur = []
        cur.append(b)
    segs.append(cur)
    return [{"words": s, "text": " ".join(w[4] for w in s), "x0": s[0][0], "x1": s[-1][2],
             "y0": min(w[1] for w in s), "y1": max(w[3] for w in s)} for s in segs]


def _clusters(segments, dy=10.0, dx=40.0):
    """Group vertically adjacent, left-aligned or overlapping segments (product cards)."""
    segs = sorted(segments, key=lambda s: (s["y0"], s["x0"]))
    parent = list(range(len(segs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(segs):
        for j in range(i + 1, len(segs)):
            b = segs[j]
            gap = b["y0"] - a["y1"]
            if gap > dy:
                break
            if gap < -2:
                continue
            if abs(b["x0"] - a["x0"]) <= dx or (b["x0"] < a["x1"] and a["x0"] < b["x1"]):
                parent[find(j)] = find(i)
    groups = {}
    for i, s in enumerate(segs):
        groups.setdefault(find(i), []).append(s)
    return list(groups.values())


def _edge(kind, a, b, statement, box, method, authority, page_sha, qualifiers=(), scope="", maker=""):
    return {"kind": kind, "a": a, "b": b, "statement": statement[:300],
            "position": f"x{round(box[0])} y{round(box[1])}", "method": f"{VERSION}/{method}",
            "authority": authority,
            "assertion_class": "manufacturer_assertion" if authority == "manufacturer" else "distributor_assertion",
            "qualifiers": sorted(set(q.lower() for q in qualifiers)), "scope": scope, "manufacturer": maker,
            "page_text_sha256": page_sha}


def _conditions(text):
    scope = "; ".join(m.group(0) for m in SCOPE.finditer(text))
    rest = SCOPE.sub(" ", text)
    return [m.group(0) for m in QUALIFIER.finditer(rest)], scope


# ------------------------------------------------------------------ rules
def _statement_edges(seg, authority, sha):
    t = seg["text"]
    out = []
    if len(t) > 300:
        return out
    codes = codes_in(t)
    if len(codes) < 2:
        return out
    box = (seg["x0"], seg["y0"])
    for pattern, direction in ((FORWARD, "forward"), (REVERSE, "reverse"), (AMBIGUOUS, "ambiguous")):
        for m in pattern.finditer(t):
            before = [c for c in codes if c[0] < m.start()]
            after = [c for c in codes if c[0] >= m.end() - 1]
            if not before or not after:
                continue
            subj, obj = before[-1], after[0]
            # The subject must be unambiguous inside its clause.
            clause_start = max(t.rfind(sep, 0, m.start()) for sep in (";", "|", ". ", " / ")) + 1
            in_clause = [c for c in before if c[0] >= clause_start]
            if len(in_clause) != 1 or subj[1] == obj[1]:
                continue
            between = t[subj[0]:m.start()]
            if NEGATION.search(between) or NEGATION.search(t[m.start():obj[0]]):
                continue
            tail_end = next((c[0] for c in after[1:]), len(t))
            quals, scope = _conditions(t[subj[0]:]) if direction != "ambiguous" else ([m.group(0).strip()], "")
            # A further code after the object inside the clause is a qualifier
            # (e.g. "... only with adapter 11111").
            if tail_end < len(t) and direction != "ambiguous" and not quals:
                quals = ["additional_number_in_clause"]
            old, new = (subj[1], obj[1]) if direction in ("forward", "ambiguous") else (obj[1], subj[1])
            if direction == "ambiguous":
                old, new = obj[1], subj[1]  # "B replacement for A": staged only
            out.append(_edge("supersedes", old, new, t, box, f"statement-{direction}", authority, sha, quals, scope))
    return out


def _stacked_label_edges(segments, authority, sha):
    out = []
    for a in segments:
        m = OLD_LABEL.match(a["text"])
        if not m:
            continue
        for b in segments:
            if b is a or not (0 <= b["y0"] - a["y1"] <= 12) or abs(b["x0"] - a["x0"]) > 30:
                continue
            n = NEW_LABEL.match(b["text"])
            if n and valid_code(m[1]) and valid_code(n[1]) and m[1] != n[1]:
                out.append(_edge("supersedes", m[1].rstrip("."), n[1].rstrip("."), a["text"] + " / " + b["text"],
                                 (a["x0"], a["y0"]), "stacked-old-new-labels", authority, sha))
    return out


def _header_roles(row):
    ws = row["words"]
    found = []
    i = 0
    while i < len(ws):
        hit = None
        for n in (4, 3, 2, 1):
            group = ws[i:i + n]
            if len(group) != n or any(b[0] - a[2] > 14 for a, b in zip(group, group[1:])):
                continue
            text = " ".join(w[4] for w in group).strip(" :")
            for role, rx in ROLES:
                if rx.fullmatch(text):
                    hit = (role, group[0][0], group[-1][2], text, n)
                    break
            if hit:
                break
        if hit:
            found.append(hit[:4])
            i += hit[4]
        else:
            i += 1
    return found


def _table_edges(rows, page_width, authority, sha):
    out = []
    for hi, row in enumerate(rows):
        heads = _header_roles(row)
        roles = [h[0] for h in heads]
        if len(heads) < 2 or len(set(roles)) != len(roles):
            continue
        has = set(roles)
        if not ({"old", "new"} <= has or {"part", "oem"} <= has or {"part", "remarks"} <= has or {"part", "desc"} <= has):
            continue
        # Non-header words on the header line would mean prose, not a header.
        covered = sum(1 for w in row["words"] if any(h[1] - 1 <= w[0] and w[2] <= h[2] + 1 for h in heads))
        if covered < len(row["words"]) - 1:
            continue
        heads.sort(key=lambda h: h[1])
        bounds = []
        for j, h in enumerate(heads):
            left = 0 if j == 0 else (heads[j - 1][2] + h[1]) / 2
            right = page_width if j == len(heads) - 1 else (h[2] + heads[j + 1][1]) / 2
            bounds.append((h[0], left, right, h[3]))
        prev = row["y1"]
        for r in rows[hi + 1:]:
            if r["y0"] - prev > 40 or len(_header_roles(r)) >= 2:
                break
            prev = r["y1"]
            cells = {}
            for w in r["words"]:
                cx = (w[0] + w[2]) / 2
                for role, left, right, _ in bounds:
                    if left <= cx < right:
                        cells.setdefault(role, []).append(w[4])
            cells = {k: " ".join(v) for k, v in cells.items()}
            box = (r["words"][0][0], r["y0"])
            stmt = " | ".join(f"{h[3]}: {cells.get(h[0], '')}" for h in bounds)
            remark = cells.get("remarks", "")
            quals, scope = _conditions(remark) if remark else ([], "")
            if "old" in cells and "new" in cells:
                o, n = cells["old"].split(), cells["new"].split()
                if len(o) == 1 and len(n) == 1 and valid_code(o[0]) and valid_code(n[0]) and o[0] != n[0]:
                    out.append(_edge("supersedes", o[0], n[0], stmt, box, "table-old-new-columns", authority, sha, quals, scope))
                continue
            part = cells.get("part", "").split()
            if len(part) != 1 or not valid_code(part[0]):
                continue
            pnum = part[0].rstrip(".")
            if "oem" in cells and authority == "distributor":
                oem = cells["oem"].split()
                if len(oem) == 1 and valid_code(oem[0]) and oem[0] != pnum:
                    maker = cells.get("maker", "")
                    mk = _MAKER.search(maker)
                    out.append(_edge("oem_xref", pnum, oem[0].rstrip("."), stmt, box, "table-sku-oem-columns",
                                     authority, sha, maker=mk.group(1) if mk else maker[:40]))
            for col in ("remarks", "desc"):
                text = cells.get(col, "")
                if not text:
                    continue
                synthetic = {"text": pnum + " " + text, "x0": box[0], "y0": box[1]}
                for e in _statement_edges(synthetic, authority, sha):
                    if pnum in (e["a"], e["b"]):
                        e["method"] = f"{VERSION}/table-{col}-statement"
                        e["statement"] = stmt[:300]
                        out.append(e)
    return out


def _card_edges(clusters, authority, sha):
    out = []
    for cl in clusters:
        text = " \n ".join(s["text"] for s in cl)
        skus = {m[1] for m in SKU_LABEL.finditer(text)}
        if len(skus) != 1:
            continue
        sku = next(iter(skus))
        box = (min(s["x0"] for s in cl), min(s["y0"] for s in cl))
        if authority == "distributor":
            oems = {m[1].rstrip(".") for m in OEM_LABEL.finditer(text) if valid_code(m[1]) and m[1] != sku}
            if len(oems) == 1:
                makers = {m.group(1).lower() for m in _MAKER.finditer(text)}
                maker = next(iter(makers)) if len(makers) == 1 else ""
                out.append(_edge("oem_xref", sku, next(iter(oems)), text, box, "card-sku-oem-labels", authority, sha, maker=maker))
        for s in cl:
            m = FITS.search(s["text"])
            if not m:
                continue
            scope_text = m[1].strip(" .;,:")
            if NEGATION.search(s["text"]) or len(scope_text.split()) > 18:
                continue
            quals, scope = _conditions(scope_text)
            out.append(_edge("fits", sku, scope_text, s["text"], (s["x0"], s["y0"]), "card-fitment", authority, sha, quals, scope))
    return out


def extract_page(page, p=None, authority="manufacturer"):
    words = [w for w in page.get_text("words") if w[4].strip()]
    if not words:
        return []
    sha = hashlib.sha256(page.get_text("text").encode()).hexdigest()
    rows = _rows(words)
    segments = [s for r in rows for s in _segments(r)]
    edges = []
    edges += _table_edges(rows, page.rect.width, authority, sha)
    for s in segments:
        edges += _statement_edges(s, authority, sha)
    edges += _stacked_label_edges(segments, authority, sha)
    edges += _card_edges(_clusters(segments), authority, sha)
    best = {}
    for e in edges:
        if p is not None:
            e["page"] = p
        key = (e["kind"], e["a"], e["b"])
        # Conservative merge: a condition seen by ANY rule stays attached, so a
        # narrower rule can never launder a qualified statement into a clean one.
        if key in best:
            merged = sorted(set(best[key]["qualifiers"]) | set(e["qualifiers"]))
            best[key]["qualifiers"] = merged
            best[key].setdefault("corroborating_methods", []).append(e["method"])
        else:
            best[key] = e
    return list(best.values())
