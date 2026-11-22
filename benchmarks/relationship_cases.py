"""Synthetic layout-variant benchmark for typed relationship extraction.

These pages reproduce layout PATTERNS seen in RV spare-parts and distributor
catalogues (supersession tables with 3+ columns, remarks columns, product
cards that put the item number and the OEM number on different lines,
two-line old/new labels, reverse-direction wording, German grammar).

They are NOT a substitute for hand-annotated pages from real catalogues. Their
job is to show, deterministically and in CI, which layout classes an extractor
can and cannot represent, so a parser change is judged before any costly
full-catalogue replay.

Each case gives gold edges as (kind, a, b):
  ("supersedes", old_number, new_number)            directional
  ("oem_xref",   distributor_sku, oem_number)       distributor assertion only
  ("fits",       sku, model_substring)              scope claim, not interchangeability
Negative cases have no gold edges: any clean, unqualified edge is a false positive.
"""
from __future__ import annotations

import pymupdf

# (name, authority, layout class, [(x, y, text)], gold edges)
CASES = [
    # ---------------- supersession: manufacturer parts lists ----------------
    ("S01 sentence", "manufacturer", "sentence",
     [(40, 60, "Part 12345 replaced by 67890")],
     {("supersedes", "12345", "67890")}),
    ("S02 old/new/description table", "manufacturer", "table-3col",
     [(40, 60, "Old part no."), (150, 60, "New part no."), (270, 60, "Description"),
      (40, 80, "30012"), (150, 80, "30019"), (270, 80, "Burner jet"),
      (40, 100, "30044"), (150, 100, "30051"), (270, 100, "Thermocouple"),
      (40, 120, "30060"), (150, 120, "30072"), (270, 120, "Ignition electrode")],
     {("supersedes", "30012", "30019"), ("supersedes", "30044", "30051"), ("supersedes", "30060", "30072")}),
    ("S03 remarks column", "manufacturer", "table-remarks",
     [(40, 60, "Part No."), (130, 60, "Description"), (330, 60, "Remarks"),
      (40, 80, "2412345"), (130, 80, "Door seal 520 mm"), (330, 80, "Replaced by 2412399"),
      (40, 100, "2412346"), (130, 100, "Hinge, upper"), (330, 100, ""),
      (40, 120, "2412347"), (130, 120, "Hinge, lower"), (330, 120, "Superseded by 2412401")],
     {("supersedes", "2412345", "2412399"), ("supersedes", "2412347", "2412401")}),
    ("S04 inline trailing replacement", "manufacturer", "inline",
     [(40, 60, "12345 Seal kit - replaced by 67890")],
     {("supersedes", "12345", "67890")}),
    ("S05 trailing condition text", "manufacturer", "inline",
     [(40, 60, "40123 superseded by 40188 from 2019 production")],
     {("supersedes", "40123", "40188")}),
    ("S06 reverse direction", "manufacturer", "sentence",
     [(40, 60, "New burner 30030-21500 replaces 30030-21400")],
     {("supersedes", "30030-21400", "30030-21500")}),
    ("S07 two-line old/new labels", "manufacturer", "stacked-labels",
     [(40, 60, "Old part number: 3307441.012"), (40, 74, "New part number: 3307441.020")],
     {("supersedes", "3307441.012", "3307441.020")}),
    ("S08 German Nachfolger", "manufacturer", "sentence-de",
     [(40, 60, "Art.-Nr. 318019 Nachfolger: 318020")],
     {("supersedes", "318019", "318020")}),
    ("S09 German ersetzt (reverse)", "manufacturer", "sentence-de",
     [(40, 60, "Neue Version 318020 ersetzt 318019")],
     {("supersedes", "318019", "318020")}),
    ("S10 page contains the word kit", "manufacturer", "sentence",
     [(40, 40, "Spare parts - burner kit"), (40, 60, "Part 55501 replaced by 55509")],
     {("supersedes", "55501", "55509")}),

    # --------- distributor catalogue: SKU <-> OEM number correspondence ---------
    ("O01 same line", "distributor", "same-line",
     [(40, 60, "Reimo Art.Nr. 318019 Hersteller-Nr. 270.99S Dometic")],
     {("oem_xref", "318019", "270.99S")}),
    ("O02 product card, separate lines", "distributor", "card",
     [(40, 40, "Ersatz-Brennerduese"), (40, 56, "Art.-Nr. 318044"),
      (40, 72, "Hersteller-Nr. 30030-21500"), (40, 88, "passend für Truma S3004")],
     {("oem_xref", "318044", "30030-21500"), ("fits", "318044", "Truma S3004")}),
    ("O03 distributor table", "distributor", "table",
     [(40, 60, "Art.-Nr."), (110, 60, "Hersteller"), (200, 60, "Hersteller-Nr."), (310, 60, "Bezeichnung"),
      (40, 80, "720101"), (110, 80, "Thetford"), (200, 80, "50710"), (310, 80, "Dichtung Cassette C200"),
      (40, 100, "720102"), (110, 100, "Thetford"), (200, 100, "23718"), (310, 100, "Schieberdichtung"),
      (40, 120, "720103"), (110, 120, "Dometic"), (200, 120, "241333710"), (310, 120, "Tuerdichtung")],
     {("oem_xref", "720101", "50710"), ("oem_xref", "720102", "23718"), ("oem_xref", "720103", "241333710")}),
    ("O04 fitment same line", "distributor", "same-line",
     [(40, 60, "Art.Nr. 318019 passend für Truma S3004")],
     {("fits", "318019", "Truma S3004")}),

    # ---------------- negatives: must NOT yield clean edges ----------------
    ("N01 not interchangeable", "manufacturer", "negative",
     [(40, 60, "12345 is not interchangeable with 67890")], set()),
    ("N02 adjacent numbers", "manufacturer", "negative",
     [(40, 60, "Part No."), (130, 60, "Description"), (40, 80, "12345"), (130, 80, "67890 Seal")], set()),
    ("N03 qualified replacement", "manufacturer", "negative",
     [(40, 60, "12345 replaced by 67890 only with adapter 11111")], set()),
    ("N04 compatible list", "manufacturer", "negative",
     [(40, 60, "Compatible with 12345 and 67890")], set()),
    ("N05 price column next to SKU", "distributor", "negative",
     [(40, 60, "Art.-Nr. 318019"), (140, 60, "129,95")], set()),
]


def build(case):
    _name, _authority, _cls, items, _gold = case
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text in items:
        if text:
            page.insert_text((x, y), text, fontsize=9)
    return doc, page
