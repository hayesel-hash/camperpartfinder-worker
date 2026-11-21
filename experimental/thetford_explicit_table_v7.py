"""Thetford V7: staged, explicit-column manufacturer part candidates only.

Grounded in official N3000 and N4000 spare-parts tables. No fitment,
supersession, or publication is inferred. This module is opt-in.
"""
import re
from dataclasses import dataclass

PART = re.compile(r"^[0-9]{6}(?:[0-9]{2})?(?:[A-Z]{1,3})?$")
BAD = re.compile(r"(?i)(?:price|£|€|\$|sku|article\s*no|serial|model|refer to|colour|color|ean|barcode)")

@dataclass(frozen=True)
class Candidate:
    manufacturer: str
    number: str
    description: str
    source_page: int
    row_number: str
    evidence_column: str
    status: str = "staged"

def extract_rows(rows, *, source_page, manufacturer="Thetford", authority="manufacturer"):
    if manufacturer != "Thetford" or authority != "manufacturer" or source_page < 1:
        return []
    output = []
    for row in rows:
        desc = str(row.get("Description", "")).strip()
        position = str(row.get("No.", "")).strip()
        if not desc or BAD.search(desc):
            continue
        for col in ("Spare part number 1", "Spare part number 2", "Spare part number 3"):
            raw = str(row.get(col, "")).strip()
            if PART.fullmatch(raw):
                output.append(Candidate(manufacturer, raw, desc, source_page, position, col))
    return list(dict.fromkeys(output))
