"""Held-out layout cases written AFTER relationship_graph_v2 was frozen.

Do not tune the extractor to these. When one fails, add a new held-out set
before changing the extractor, or the benchmark stops measuring anything.
"""
CASES = [
    ("H01 new column left of old", "manufacturer", "table-3col",
     [(40, 60, "New No."), (140, 60, "Old No."), (240, 60, "Description"),
      (40, 80, "60011"), (140, 80, "60002"), (240, 80, "Gas valve")],
     {("supersedes", "60002", "60011")}),
    ("H02 replaced-by on line below part", "manufacturer", "two-line",
     [(40, 60, "70123 Water pump 12V"), (40, 74, "Replaced by: 70188")],
     {("supersedes", "70123", "70188")}),
    ("H03 footnote asterisk on number", "manufacturer", "table-remarks",
     [(40, 60, "Part No."), (130, 60, "Description"), (330, 60, "Remarks"),
      (40, 80, "2412345*"), (130, 80, "Door seal"), (330, 80, "Replaced by 2412399")],
     {("supersedes", "2412345", "2412399")}),
    ("H04 two cards side by side", "distributor", "card",
     [(40, 40, "Art.-Nr. 318044"), (300, 40, "Art.-Nr. 318045"),
      (40, 56, "Hersteller-Nr. 30030-21500"), (300, 56, "Hersteller-Nr. 30030-21600")],
     {("oem_xref", "318044", "30030-21500"), ("oem_xref", "318045", "30030-21600")}),
    ("H05 maker-prefixed OEM label", "distributor", "card",
     [(40, 40, "Bestell-Nr. 720555"), (40, 56, "Thetford Nr. 50710")],
     {("oem_xref", "720555", "50710")}),
    ("H06 en-dash and period", "manufacturer", "inline",
     [(40, 60, "Burner 30030-21400 – superseded by 30030-21500.")],
     {("supersedes", "30030-21400", "30030-21500")}),
    ("H07 serial scope", "manufacturer", "sentence",
     [(40, 60, "From serial no. 1234567 part 80011 is replaced by 80019")],
     {("supersedes", "80011", "80019")}),
    # negatives
    ("H08 see also", "manufacturer", "negative",
     [(40, 60, "Seal 12345, see also 67890")], set()),
    ("H09 use with", "manufacturer", "negative",
     [(40, 60, "Filter 44551 use with housing 44560")], set()),
    ("H10 replaced by dealer", "manufacturer", "negative",
     [(40, 60, "Cartridge 318019 must be replaced by dealer every 24 months")], set()),
    ("H11 not replaced", "manufacturer", "negative",
     [(40, 60, "12345 is not replaced by 67890")], set()),
    ("H12 two candidate subjects", "manufacturer", "negative",
     [(40, 60, "12345 and 12346 replaced by 67890 kit")], set()),
]
