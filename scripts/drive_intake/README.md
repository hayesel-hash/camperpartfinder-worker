# Drive intake (supplied catalogues in Larry's Google Drive)

Larry's ChatGPT drops maker PDFs into Google Drive. Every file gets one row in
`rv_private.drive_intake_v1`, which is how ClaudeL sessions (and the scheduled intake run)
avoid doing the same file twice.

Folders watched (Drive folder ids):
- `1VPv8yDVJFuSmUaHzpwuXBYB1inByelsy` CamperPartMatch — 20 Aftermarket Parts Catalogues for Claude
- `1Vd4kdiZQOrn6A2V1AmqOY9d2XIbX4mRu` Manufacturer original catalogues — batch 1 (Airstream books:
  handled by the supplied-documents lane, `scripts/supplied/`; register them as lane `oem_parts_book`)
  - subfolder `1Qpd8lCplJ6HFY5TDZTdSWUHDfiP4sY1C` Airstream Parts Books — Split PDFs (index:
    START-HERE-Airstream-PDF-Index.csv). All 426 Airstream files were registered on 26 Nov and marked `done`
    where `supplied_documents_v1` already holds the book (matched by title and page range).
- `1wu6X8wqDNQMjPdK7kuAVYAFp-sPm337i` CamperPartMatch — Other Catalogues Split for Claude: ChatGPT's "pp NNN-MMM"
  copies of every file over 10 MB (index: START-HERE-Other-CamperPartMatch-PDF-Index.csv). The originals are
  registered as `skipped` with a pointer to their parts.
- `17pfVUZfKW78ErYmqDq2zcirzl9DrzPGu` CamperPartMatch — 200 Catalogue Intake: one "Verified - ..." subfolder per
  PDF (with a source.txt). Search it with `'17pfVU...' in ancestors`.
- Simplest complete listing: `'1EBA8SjoSBZtbyK5y7SC-BXDZr6Lo8IfN' in ancestors and mimeType = 'application/pdf'`
  (the "RV Parts Finder — Larry & Michael" root; pass `orderBy` or the connector returns 5 per page). Marine /
  BoatPartMatch folders are a different project and are not registered here.

## Lanes
- `aftermarket_xref` — a maker states "our part X replaces / is equivalent to brand Y part Z".
  Stage into `aftermarket_assertions_v1` (relation `replaces`, brand named on page, page and
  qualifiers kept) against a reviewed `aftermarket_source_pages_v1` row and a `sources` row of
  kind `aftermarket_manufacturer_pdf`; then `select rv_private.publish_aftermarket_pdf_v1();`.
  Example reader: `scripts/aftermarket_pdf/nbk_blocks.py`.
- `oem_parts_list` / `oem_parts_book` — a maker's own parts list: new identities via the
  supplied-documents lane (`scripts/supplied/README.md`): two independent passes must agree.
- `fitment_guide` — vehicle/application guides. Fitment is never interchangeability.

## Status
`new` → `claimed` (via `rv_private.claim_drive_intake_v1(session, lane, n)`, stale after 3 h)
→ `done` | `held` (note says what it waits for) | `skipped` (note says why) | `needs_split`
(over the Drive connector's 10 MB download limit: ask Larry for a compressed or
"part N of M" copy; register the copy as a new row).

Always write `doc_sha256`, `source_id`, `result` and a plain-English `note`.

## Readers added by the intake
- `scripts/aftermarket_pdf/wfco_catalogue.py` — WFCO product catalogue: door-assembly lines and the model row of
  each SPECIFICATIONS table (test: `tests/test_wfco_catalogue.py`). WFCO's crossover chart (printed p30) is a
  72-dpi raster in the Drive copy and is not read; it waits for a sharper copy.
- `scripts/aftermarket_pdf/dexter_lit119.py` — Dexter parts kit catalogue LIT-119-00 (03/2017): kit numbers with
  kit name + description, and every component row of the "Dx Part No. / Quantity / Parts Description" tables.
  Pass A reads text blocks, pass B word positions (the rotated section label on the page edge is dropped).
  Instruction/Installation Sheet and LIT- manual rows are left out (test: `tests/test_dexter_lit119.py`).

- `scripts/aftermarket_pdf/icon_tanks.py` — ICON Technologies RV parts catalogue tank pages: "<ICON no.> Replaces
  <brand> <number>[, <number>]" under the tank heading and size line. Pass A text lines, pass B word boxes by column
  and baseline (edge labels dropped). Rows with no brand printed, a misspelt brand, or an OEM number equal to ICON's
  own tank code are returned with a hold reason (test: `tests/test_icon_tanks.py`). Staged into
  `aftermarket_assertions_v1` (source `icon-rv-parts-catalogue-2027`, maker `ICON Technologies`).
- `scripts/aftermarket_pdf/carefree_ipl.py` — Carefree of Colorado Illustrated Parts Lists (Item / Part Number /
  Description / Notes). Pass A dict-layer line cells, pass B word boxes merged into cells; order templates (`3nn`,
  `xx`, `XX`/`XXX` colour codes) skipped and counted (test: `tests/test_carefree_ipl.py`). Output is a
  supplied-documents drop (source `carefree-ipl-drive-supplied`). Scanned Carefree lists still need OCR.
  Also reads President's Club parts-book tables with no Notes column (Item / Part Number / Description).
- `scripts/aftermarket_pdf/alde_service_parts.py` — Alde boiler service manuals: "EXPLODED DRAWING" and "SPARE PARTS"
  pages only ("<callout>. NNNN NNN <description>", two numbers per callout allowed). Pass A text lines, pass B word
  boxes by baseline. Alde prints "3020 011"; the drop stores "3020011" (the supplied lane allows no spaces)
  (test: `tests/test_alde_service_parts.py`, source `alde-service-manuals-drive-supplied`).
- `scripts/aftermarket_pdf/atwood_part_reference.py` — Atwood 2007 service manual "hydro flame Furnace REPLACEMENT PART
  REFERENCE" pages ("NNNNN description" + model-column check marks; bold section headings kept as the row section;
  NLA / while-supplies-last glyphs turned into words). Optional page range argument. Only rows on which both passes
  give the same number and description are kept; the rest are reported as held
  (test: `tests/test_atwood_part_reference.py`, source `atwood-2007-rv-appliance-service-parts-manual`, publisher
  Dometic per the Atwood alias).

- `scripts/aftermarket_pdf/atwood_range_parts.py` — Atwood range / cooktop "Parts Identification" tables (ITEM /
  DESCRIPTION / one 5-digit number per model column, e.g. Model 21 manual, page 8 two-up spread). Pass A text lines
  (item line, description, numbers; un-numbered description lines continue the item), pass B word boxes with the
  model columns read from the one or two header rows ("RA" over "1721 2121" -> "RA 1721"). TBD and diamond cells are
  skipped; each row's section names the model columns it is printed under (test: `tests/test_atwood_range_parts.py`,
  source `atwood-range-cooktop-manuals-drive-supplied`, publisher Dometic). Candidate for the range/oven matrices in
  the Atwood 2007 manual split pp 001-093.

## Drop mechanics (learned 27 Nov)
- `supplied_document_rows_v1.number` must match `^[A-Za-z0-9][A-Za-z0-9./-]{1,39}$` (no spaces).
- `supplied_drops_v1.url` must be the `.../supplied-drops/<name>.b64` branch URL; when re-pushing a corrected drop
  under the same name, check that raw.githubusercontent.com already serves the new bytes before re-queueing.
- The publisher name must exist in `rv_private.manufacturers` (Alde was added 27 Nov).

## More distributor catalogues (held for the third-party tier decision)
- Fritz Berger Ersatzteil-Katalog 2017-2018 (all 8 splits): Berger-Nr. against FIAMMA-Nr. / Thetford-Nr. /
  Hersteller-Nr.
- Coast to Coast RV Caravan and Leisure Catalogue 2026 (Australian distributor stock numbers such as 200-04802).
- Multi-layout catalogues held for dedicated readers: AL-KO Australia Vehicle Technology Comprehensive Catalogue 2020
  (3 splits, ~25 table layouts) and the Atwood 2007 manual's water-heater / range matrices and jack / coupler pages.

## Notes from scheduled runs
- Each "Verified - ..." subfolder of the 200 Catalogue Intake has a `source.txt` (original URL, page count,
  SHA-256 and the uploaded split parts). Compare the Drive copy's hash with it; ChatGPT's "Use:" line is a
  description only.
- Distributor catalogues (Trailer Enterprises sections, Berger, Vecam, Euro Accessoires, Moog) list other makers'
  numbers against their own: hold them for the third-party tier decision unless the maker of the part itself
  states the replacement. Same for the "AL-KO Spare Parts" list with a Grove No. column (Grove Products, UK) and the
  AL-KO Australia "Genuine Dexter Parts" sheets (AL-KO stock numbers against Dexter numbers).
- 27 Nov ~02:30 run: "Coleman Air Conditioner - RV Replacement Parts Guide" is section Q of a distributor catalogue
  (ORDER # = distributor stock numbers; Coleman-Mach numbers only in "(S/O ...)" notes) -> held with the distributors.
  Same-maker "takes place of" kit sheets (Coleman-Mach 1976-532) go to the legacy-map v2 lane with the rewiring
  condition and kit contents as qualifiers. Cummins Onan parts manuals (0983-0201, 0981-0200, 981-0246) are
  copy-restricted (AES, owner password) -> held. CURT 2024 catalogue (4 splits): multi-layout, application guides are
  fitment -> held for dedicated readers.
- Check `pymupdf.Document.permissions` before reading: a PDF whose owner password forbids copying/extraction
  (e.g. Dexter "AL-KO Genuine Parts by Dexter" cross reference, 27 Nov) is held for Larry's decision, not read.

## Conversion kits (relation `replaces_with_kit`, claim kind `conversion_kit_replacement`)
Approved by Larry, 26 Nov 2026 23:15. Use when a maker says its part/unit replaces another only
together with an adapter / conversion / retrofit kit, or its product is itself a retrofit kit.
Stage in `aftermarket_assertions_v1` with `qualifiers.kit_parts` (array of {maker, number[, description]})
and `qualifiers.conditions` (installation conditions); the replacement maker must be the publisher.
Publisher: `rv_private.publish_conversion_kit_replacements_v1()` (cron every 10 min). Claims always
carry `requires_conversion_kit`, `not_a_direct_swap`, the kit parts and the conditions.
First uses: Coleman-Mach 1976-579 Carrier adapters (16), PD4600 converter-section kits (9, reclassified).
