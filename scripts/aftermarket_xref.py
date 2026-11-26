"""Aftermarket maker cross-reference charts -> staged assertions.

Lane 2 of the factory (target-brands-and-lanes.md). Reads an aftermarket
maker's OWN published cross-reference chart ("OEM part X -> our part Y") and
stages one assertion per chart cell pair. It never publishes: the database
publisher links a staged row only when the page has been reviewed and the
exact OEM number already exists under the brand the page names.

Policy (24 Nov 2026): a maker's statement about its own part is a
manufacturer-certified aftermarket claim, not OEM endorsement. Model fitment
("our board fits fridge model 652") is staged as fitment, never as
interchangeability. Rows the chart marks as "None", "N/A", "See Service
Alert", a "?" or an unexplained footnote are skipped or held, never guessed.

Fetching goes through rv_master_disk.open_catalogue: host allowlist, robots
rules, Crawl-delay handling and the no-cross-host-redirect rule all apply.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAKER = "Dinosaur Electronics"
BASE = "https://www.dinosaurelectronics.com/"
# Chart pages listed on the maker's own index page (reference.html).
PAGES = {
    "Nor_chart.htm": "dinosaur-xref-norcold",
    "Dom_Chart.htm": "dinosaur-xref-dometic",
    "UIB_Chart.htm": "dinosaur-xref-ignitor",
    "Msc_Chart.htm": "dinosaur-xref-other",
}
CATEGORY = {"Norcold": "refrigeration", "Dometic": "refrigeration", "Servel": "refrigeration",
            "Onan": "external_equipment", None: "heating"}
GATEWAY = "https://dlijhukwzlqwtmiynncg.supabase.co/functions/v1/rv-aftermarket-gateway"
AUDIENCE = "rv-aftermarket-dlijhukwzlqwtmiynncg"

SKIP_VALUES = {"", "N/A", "NA", "NONE", "SEE SERVICE ALERT", "-"}
# An OEM part number: starts with a digit or letters+digits, may contain . - /
OEM_NUMBER = re.compile(r"^([A-Z]{0,4}\d[A-Z0-9]*(?:[.\-/][A-Z0-9]+)*)(?:\s+(.*))?$", re.I)
PROD_ROW = re.compile(r"^(?:P[ro]{2}d\.?\s*#\s*)?(\d{6,}\s*(?:-\s*\d{6,})?)$", re.I)


# ---------------------------------------------------------------- HTML tables
class _Tables(HTMLParser):
    """Collects every <table> as rows of cell text. Text inside a nested
    table belongs to the nested table only. Text outside all tables is kept
    as page notes (the charts put their caveats there)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.notes, self._loose = [], [], [], []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None})
        elif not self.stack:
            if tag in ("br", "p", "div", "h1", "h2", "h3", "h4", "li"):
                self._flush_loose()
            return
        t = self.stack[-1]
        if tag == "tr":
            t["row"] = []
            t["rows"].append(t["row"])
        elif tag in ("td", "th"):
            if t["row"] is None:
                t["row"] = []
                t["rows"].append(t["row"])
            t["cell"] = []
            t["row"].append(t["cell"])
        elif tag == "br" and t["cell"] is not None:
            t["cell"].append("\n")

    def handle_endtag(self, tag):
        if tag == "table" and self.stack:
            t = self.stack.pop()
            rows = [[_clean(" ".join(c)) for c in r] for r in t["rows"]]
            self.tables.append([r for r in rows if any(r)])
        elif tag in ("td", "th") and self.stack:
            self.stack[-1]["cell"] = None
        elif not self.stack and tag in ("p", "div", "h1", "h2", "h3", "h4", "li"):
            self._flush_loose()

    def handle_data(self, data):
        if self.stack:
            t = self.stack[-1]
            if t["cell"] is not None:
                t["cell"].append(data)
        else:
            self._loose.append(data)

    def _flush_loose(self):
        text = _clean(" ".join(self._loose))
        self._loose = []
        if text:
            self.notes.append(text)

    def close(self):
        super().close()
        self._flush_loose()


def _clean(s):
    s = s.replace("®", "").replace("™", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_tables(html):
    p = _Tables()
    p.feed(html)
    p.close()
    return p.tables, p.notes


# -------------------------------------------------------------- classification
def _role(header):
    h = header.lower()
    if "dino" in h:
        return ("dino", _clean(re.sub(r"(?i)dino(saur)?|#|number|\(.*?\)", " ", header)) or "Replacement")
    if "jumper" in h:
        return ("jumper", None)
    if "#" in h or "model" in h or "part" in h:
        kind = "model" if "model" in h else "part"
        brand = None
        m = re.match(r"^\s*([A-Za-z][A-Za-z-]+)", header)
        if m and m.group(1).lower() not in ("mfg", "mfgs", "mfg's", "manufacturer", "part", "model", "oem"):
            brand = m.group(1)
        if re.match(r"(?i)^\s*mfg", header):
            brand = None
        return ("oem", (kind, brand))
    return ("blank", None)


def _header_index(table):
    for i, row in enumerate(table):
        roles = [_role(c) for c in row]
        if any(r[0] == "dino" for r in roles) and any(r[0] == "oem" for r in roles):
            return i, roles
    return None, None


def _groups(roles):
    """Split repeated column groups: each OEM column opens a group."""
    groups, cur = [], None
    for j, (role, info) in enumerate(roles):
        if role == "oem":
            cur = {"oem": j, "kind": info[0], "brand": info[1], "dino": [], "jumper": None}
            groups.append(cur)
        elif cur is not None and role == "dino":
            cur["dino"].append((j, info))
        elif cur is not None and role == "jumper":
            cur["jumper"] = j
        elif cur is not None and role == "blank" and cur["dino"]:
            cur["dino"].append((j, cur["dino"][-1][1]))  # continuation column
    return [g for g in groups if g["dino"]]


def _split_dino(value):
    """Return (number, qualifiers, hold_reason) for a chart's Dinosaur cell."""
    v = _clean(value)
    up = v.upper()
    if up in SKIP_VALUES:
        return None, {}, "chart gives no replacement"
    if "?" in v:
        return None, {}, "chart marks the replacement as uncertain"
    if up.startswith("SEE "):
        return None, {}, "chart refers to a service alert"
    q = {}
    if "*" in v:
        q["footnote_marker"] = "asterisk not explained on the page"
        v = v.replace("*", "").strip()
    m = re.match(r"(?i)^kit with (.+)$", v)
    if m:
        return None, {"kit_statement": v}, "kit composition statement, not a single part"
    m = re.match(r"(?i)^(.+?)\s*&\s*(.+)$", v)
    if m:
        q["also_requires"] = m.group(2).strip()
        v = m.group(1).strip()
    m = re.match(r"(?i)^(.+?)\s+(note\s*\d+)$", v)
    if m:
        q["chart_note"] = m.group(2)
        v = m.group(1)
    m = re.match(r"(?i)^(.+?)\s*\((long|short) version #?\)?,?$", v)
    if m:
        q["version"] = m.group(2).lower()
        v = m.group(1)
    v = v.strip(" ,")
    if not re.search(r"\d", v) and not re.match(r"(?i)^uib", v):
        return None, q, "replacement given without a part number"
    return v.upper(), q, None


def _split_oem(value):
    v = _clean(value).replace("*", "")
    m = OEM_NUMBER.match(v)
    if not m:
        return None, None
    rest = (m.group(2) or "").strip()
    return m.group(1).upper(), rest or None


def extract(html, page_name):
    """Pure function: chart HTML -> (rows, notes). Covered by tests."""
    tables, notes = parse_tables(html)
    caveats = [n for n in notes if re.search(r"(?i)\bnote\b|guid|must look|recommend", n)]
    out = []
    for ti, table in enumerate(tables):
        hi, roles = _header_index(table)
        if hi is None:
            continue
        groups = _groups(roles)
        last_model = {}
        for ri, row in enumerate(table[hi + 1:], start=hi + 1):
            if _header_index([row])[0] is not None:
                roles = [_role(c) for c in row]   # a repeated header row
                groups = _groups(roles) or groups
                continue
            for gi, g in enumerate(groups):
                cells = row + [""] * (max(g["oem"], *(j for j, _ in g["dino"])) + 1 - len(row))
                oem_text = cells[g["oem"]]
                dino_cells = [(cells[j], label) for j, label in g["dino"]]
                if not oem_text:
                    continue
                row_text = " | ".join(c for c in [oem_text] + [d for d, _ in dino_cells] if c)
                key = f"t{ti}r{ri}g{gi}"
                if g["kind"] == "model":
                    prod = PROD_ROW.match(oem_text)
                    if not any(d for d, _ in dino_cells):
                        if not prod:
                            last_model[gi] = oem_text   # model heading for following Prod. # rows
                        continue
                    model = oem_text
                    qual = {}
                    if prod and gi in last_model:
                        model = last_model[gi]
                        qual["production_numbers"] = prod.group(1).replace(" ", "")
                    elif not prod:
                        last_model.pop(gi, None)
                    for di, (dval, label) in enumerate(dino_cells):
                        num, q, hold = _split_dino(dval)
                        if num is None and hold == "chart gives no replacement":
                            continue
                        out.append(_row(page_name, f"{key}d{di}", "fits_model", g, None, model,
                                        num, label, {**qual, **q}, hold, row_text, caveats))
                    continue
                oem_num, oem_rest = _split_oem(oem_text)
                for di, (dval, label) in enumerate(dino_cells):
                    num, q, hold = _split_dino(dval)
                    if oem_num is None:
                        hold = hold or "OEM entry has no part number"
                    if oem_rest:
                        q["oem_entry_detail"] = oem_rest
                    if g["jumper"] is not None and cells[g["jumper"]]:
                        q["jumper_position"] = cells[g["jumper"]]
                    if num is None and hold == "chart gives no replacement":
                        out.append(_row(page_name, f"{key}d{di}", "replaces", g, oem_num, None,
                                        None, label, q, hold, row_text, caveats, status="skipped"))
                        continue
                    out.append(_row(page_name, f"{key}d{di}", "replaces", g, oem_num, None,
                                    num, label, q, hold, row_text, caveats))
    return out, caveats


def _row(page_name, key, relation, g, oem_num, model, num, label, q, hold, row_text, caveats, status=None):
    if q.get("footnote_marker") and not hold and relation == "replaces":
        hold = "unexplained footnote marker"
    brand = g["brand"]
    return {
        "table_key": key.split("r")[0],
        "row_key": key,
        "relation": relation,
        "aftermarket_maker": MAKER,
        "aftermarket_number": num,
        "aftermarket_label": label,
        "oem_brand": brand,
        "oem_brand_basis": "named_on_page" if brand else "not_named",
        "oem_number": oem_num,
        "oem_model": model,
        "category": CATEGORY.get(brand, "heating"),
        "qualifiers": {**q, **({"page_caveats": caveats} if caveats else {})},
        "row_text": row_text[:500],
        "status": status or ("held" if hold else "staged"),
        "hold_reason": hold,
    }


# ------------------------------------------------------------------- runtime
def oidc_token():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"audience": AUDIENCE})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["value"]


def gateway(action, args, jwt):
    req = urllib.request.Request(GATEWAY, data=json.dumps({"action": action, "args": args}).encode(),
                                 headers={"Authorization": "Bearer " + jwt, "Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def run():
    sys.path.insert(0, os.path.dirname(__file__))
    import rv_master_disk as worker
    jwt = oidc_token()
    summary = {}
    for name, source_id in PAGES.items():
        url = BASE + name
        try:
            with worker.open_catalogue(url) as r:
                raw = r.read(2_000_001)
        except worker.Held as exc:
            summary[name] = {"held": str(exc)}
            print(json.dumps({"page": name, "held": str(exc)}), flush=True)
            continue
        if len(raw) > 2_000_000:
            summary[name] = {"held": "page too large"}
            continue
        sha = hashlib.sha256(raw).hexdigest()
        html = raw.decode("utf-8", errors="replace") if b"charset=utf-8" in raw[:2000].lower() else raw.decode("cp1252", errors="replace")
        rows, caveats = extract(html, name)
        result = gateway("stage", {"page": {"source_id": source_id, "url": url, "sha256": sha,
                                            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                            "html": html, "parser": "aftermarket-xref-v1"},
                                   "page_rows": rows}, jwt)
        counts = {}
        for row in rows:
            counts[f"{row['relation']}:{row['status']}"] = counts.get(f"{row['relation']}:{row['status']}", 0) + 1
        summary[name] = {"sha256": sha, "rows": counts, "gateway": result}
        print(json.dumps({"page": name, **summary[name]}), flush=True)
        time.sleep(2)
    if all("held" in v for v in summary.values()):
        sys.exit("every page held; nothing staged")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import unittest
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
        suite = unittest.defaultTestLoader.loadTestsFromName("test_aftermarket_xref")
        sys.exit(0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1)
    run()
