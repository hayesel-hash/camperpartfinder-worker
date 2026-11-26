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

## Notes from scheduled runs
- Each "Verified - ..." subfolder of the 200 Catalogue Intake has a `source.txt` (original URL, page count,
  SHA-256 and the uploaded split parts). Compare the Drive copy's hash with it; ChatGPT's "Use:" line is a
  description only.
- Distributor catalogues (Trailer Enterprises sections, Berger, Vecam, Euro Accessoires, Moog) list other makers'
  numbers against their own: hold them for the third-party tier decision unless the maker of the part itself
  states the replacement.

## Conversion kits (relation `replaces_with_kit`, claim kind `conversion_kit_replacement`)
Approved by Larry, 26 Nov 2026 23:15. Use when a maker says its part/unit replaces another only
together with an adapter / conversion / retrofit kit, or its product is itself a retrofit kit.
Stage in `aftermarket_assertions_v1` with `qualifiers.kit_parts` (array of {maker, number[, description]})
and `qualifiers.conditions` (installation conditions); the replacement maker must be the publisher.
Publisher: `rv_private.publish_conversion_kit_replacements_v1()` (cron every 10 min). Claims always
carry `requires_conversion_kit`, `not_a_direct_swap`, the kit parts and the conditions.
First uses: Coleman-Mach 1976-579 Carrier adapters (16), PD4600 converter-section kits (9, reclassified).
