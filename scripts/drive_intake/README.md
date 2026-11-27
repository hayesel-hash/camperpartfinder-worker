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

## Decisions from Larry, 27 Nov 2026 ~12:40 ("yes to all")
- **Peterson / Grote truck-lighting interchanges are in scope.** Published 27 Nov ~13:00 as manufacturer-certified aftermarket
  claims: Peterson 1714 (Grote, Truck-Lite, Maxxima, Optronics -> Peterson), Grote 3058 (TruckLite, Peterson, Primatronics,
  Maxxima, Optronics -> Grote, column kept as `qualifiers.interchange` form_fit_function / fit_function, Grote's good-faith
  caveat on every claim). Readers `peterson_interchange.py`, `grote_interchange.py` (test `tests/test_lighting_interchange.py`).
  Combination cells ("40850+G4002", "150-09 + 142-49") and cells listing several numbers are held, never split.
  Letter prefixes are part of Peterson / Optronics numbers (B835 is not 835, M119A is not 119A, UL53CB is not BUL53CB): run
  `aftermarket_oem_match_v1` over staged rows before publishing and create the exact part first for every
  `matched_ignoring_letter_prefix` row (done for 47 Peterson numbers; 4 claims made mid-publish were revoked and re-published).
- **Distributor catalogues count as a source.** Handling: a maker's number printed under that maker's name / column with a
  description -> supplied-documents lane as that maker's part (source metadata kind `distributor_catalogue`,
  `printed_publisher` = the distributor); a distributor's own stock number is never a part; a statement that one maker's part
  replaces another maker's part -> stage in `aftermarket_assertions_v1` (relation `replaces`, `aftermarket_maker` /
  `aftermarket_number` = the replacing part as printed, `oem_brand` / `oem_number` = the replaced part, qualifiers as usual)
  against a reviewed page of a `sources` row whose metadata kind is `distributor_pdf` and whose publisher is the distributor.
  `rv_private.publish_distributor_pdf_v1()` (migration `20261127133000_distributor_pdf_seller_tier_v1`, applied on Larry's
  "apply" 27 Nov ~12:55; cron `rv-distributor-pdf-v1` every 10 min; you may call it) publishes them in the seller-stated tier
  (kind `third_party_compatibility`, state `seller_stated`, "Distributor-stated, not verified by either manufacturer"), only when
  BOTH parts already exist with an exact number match; rows whose parts are missing stay staged and are retried.
  The 57 distributor-held files were moved back to `new` at priority 70 with this note.
- **Zip Dee is the publisher of the Zip Dee sheets** (manufacturer `Zip Dee` added; 76 new parts). **Lippert-printed Thule numbers
  are Thule evidence** (source `lippert-ccd-thule-numbers-drive-supplied`, publisher Thule, printed by Lippert).
- **Espar / Eberspächer numbers printed with spaces** are stored in the dotted form Eberspächer uses in its own lists already in the
  DB: 12 digits "25 2069 99 06 00" -> 25.2069.99.0600; 8 digits "152 00 139" -> 152.00.139; other spaced shapes -> dots in place
  of the spaces ("CA0 00 019" -> CA0.00.019); the printed form goes in the description. The Airtronic D2/D4 manual is `new` again.
- **Copy-protected PDFs:** Larry said yes, but the intake still does not override a PDF's copy/extract restriction (standing rule:
  never bypass PDF protections). They stay held; an unrestricted copy, or the same numbers from the maker's own web pages /
  spreadsheets (e.g. the Dexter SKU harmonisation spreadsheet on dexterindex.com, already approved), can be loaded instead.
- **WFCO 2026 crossover chart:** still waits for a sharper copy (printed page 30 at 300 dpi or more, or the original PDF).

## Large cross-reference payloads
Thousands of staged rows are not pasted into SQL: `scripts/aftermarket_pdf/xref_payload.py` writes the rows as an encrypted
payload (same format and key table as supplied drops) to the supplied-drops branch as `xref-<sha16>.b64`; then
`select net.http_get('<raw url>')`, and insert from `jsonb_to_recordset(convert_from(extensions.decrypt_iv(...)))` of
`net._http_response.content` (see the 27 Nov ~13:00 Peterson / Grote loads).

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

- `scripts/aftermarket_pdf/camco_oem.py` — Camco "Quality Parts for RV Manufacturing / OEM Products 2023": a 13 pt
  product heading over a table whose white header row starts "PART #" and ends "QTY". Pass A text lines (upper-case
  labels, Title-case heading, a final integer closes the row), pass B dict spans (font size, colour, position;
  side-by-side tables keep their own heading). Only rows where both passes give the same number, heading and
  attributes are kept; QTY (pack quantity) dropped (test: `tests/test_camco_oem.py`, source
  `camco-oem-catalogue-2023-drive-supplied`). The retail pages at the back (filters, tumblers, coolers, portable
  fridges) have no table heading and are held.
- `scripts/aftermarket_pdf/curt_numeric_index.py` — CURT 2024 catalogue "ALL PRODUCTS LISTED NUMERICALLY" index
  (Part # | Description | MP | IP, four columns a page; descriptions cut to ~20 characters in the source). Pages with
  the vehicle listings (Part # | Years | Make / Model) are fitment and skipped. Pass A text lines (glued "200 0" and
  "20002 MIRROR" cells split; a description starting with a number is not a part), pass B word boxes by column
  (test: `tests/test_curt_numeric_index.py`, source `curt-2024-catalogue-drive-supplied`, manufacturer `CURT` as
  printed). 1433 CURT parts from split pp 264-307; the other CURT splits stay held only for their own tables.

- `scripts/aftermarket_pdf/coleman_mach_rpl.py` — Coleman-Mach (Airxcel RV Products Division) "REPAIR PARTS LIST" sheets
  (R-6xx: NO. | USED ON MODELS / CODE | PART NUMBER | DESCRIPTION | NO. REQ.). Pass A text lines (used-on cell = the
  line before the number, item marker stripped), pass B word boxes by header column. The used-on cell goes into the
  description unless it is "All"; quantities dropped; stops at "ns = not shown" (test: `tests/test_coleman_mach_rpl.py`,
  source `coleman-mach-repair-parts-lists-drive-supplied`). First use: Mach 8 472X4*87X R-607C, 30 rows.
- `scripts/aftermarket_pdf/dometic_parts_list.py` — Dometic / Duo-Therm (LaGrange) PageMaker "PARTS LIST" sheets for roof
  A/Cs and heat pumps (Index | Description | Part No. / Part Number [| Model], numbers like 3102888.009). Pass A text
  lines (index line opens a row, number line closes it), pass B word boxes per header group (a number on a second line
  continues the index line above). Only agreeing rows are kept; every other Dometic-style number on the page is reported
  as `unread` (header-less right-hand columns, "Customer Option" boxes where the number comes first, NOTE shroud kits)
  (test: `tests/test_dometic_parts_list.py`, source `dometic-ac-parts-lists-drive-supplied`). First use: 620315.421,
  B3200 3253.334C, 630515.321 heat pump. Candidate extension: the header-less right column and the option boxes.

- `scripts/aftermarket_pdf/dometic_spare_parts_list.py` — Dometic (ex-Electrolux) "Spare parts list" PDFs (pdf-tools
  layout): "Exploded view no." pages with a Matrix table (letter | PNC | ELC | ProdDate | Model) and Pos | Part No. |
  Matrix | Description rows. Pass A text lines (matrix tokens may share the line with the description), pass B word
  boxes by header column; continuation lines ("< 0923..." production-date qualifiers) kept; Pos "-" rows read; rows
  whose matrix does not cover every PNC get "[applies to: <model> <PNC>, ...]". Numbers stored as printed (Dometic's
  "add a 0 in front" ordering rule not applied) (test: `tests/test_dometic_spare_parts_list.py`, source
  `dometic-spare-parts-lists-drive-supplied`). First use 27 Nov: DM2652, RM1350, RM2820, RM3762, RM8501, RMD8555,
  RML8330, RML8555 fridges and CTLP3050/CTS3110 cassette toilets (918 rows, 601 new parts).
- `scripts/aftermarket_pdf/lci_ccd_model_list.py` — Lippert/Furrion CCD documents whose table is Callout | Part # |
  Description | Model (vertically centred model cells; "N/A" numbers skipped); model applicability kept as
  "[models: ...]" (source `lippert-ccd-component-lists`, publisher Lippert: the Furrion manual titles the numbers
  "LIPPERT PN"). First use: Furrion 2.4GPM tankless water heater CCD-0009617 (31 parts).
- `scripts/aftermarket_pdf/dometic_parts_web.py` — short Dometic NA A/C service-part tables (Dometic Parts Web exports:
  Pos | PartNo | Qty | Description | Specification; PowerPoint sheets: ID | SERVICE PART | DESCRIPTION), numbers like
  3315332.000 (source `dometic-ac-service-part-sheets-drive-supplied`). First use: Penguin II 641935, Brisk II B59516.
- `scripts/aftermarket_pdf/dometic_df_furnace.py` — Dometic DF Series furnace Service Parts List form 33402: SCV_KIT is the
  part number, SPI No. the exploded-view callout, X marks give the furnace sizes (kept only when both passes agree on the
  X count). Loads 31501 and 35100, which until then existed only as NBK cross-reference targets (source
  `dometic-df-furnace-parts-list-drive-supplied`). Tests for these three: `tests/test_drive_intake_small_readers.py`.
- `scripts/aftermarket_pdf/thetford_us_sheet.py` — Thetford North-America one-page toilet parts sheets (Key No. | Part No. |
  Description + Not Shown block). Number cells must sit under the "Part No." header (numbers inside "Superseded by"
  text are not row numbers); description words go to the nearest number (cells are vertically centred); N/A rows anchor
  and are skipped; "*" -> "(limited availability)"; italic rows = grey "Not available" shading -> "(not available)".
  "Superseded by" rows go to the legacy-map v2 lane (`supersessions` in the output), named after the row the chain ends
  on; numbers containing "/" (Aria T-PF.P03/B) are reported, not loaded (test: `tests/test_thetford_us_sheet.py`, source
  `thetford-us-parts-sheets-drive-supplied`).

- `scripts/aftermarket_pdf/atwood_hf_parts_list.py` — Atwood (Dometic) hydro flame furnace "Parts Drawing & List" sheets
  (Word/PDFMaker ruled table Item | Category | P/N | Title | X per rotated model column; some sheets Category | Item first;
  some pages two tables side by side). Pass A: one text line per cell (blank cells = blank lines), rows read group by group;
  pass B: find_tables row bands cut at every row boundary (merged Item cells) + word boxes. Category carries down per table
  group; "[models: ...]" when not every model is marked (test: `tests/test_atwood_hf_parts_list.py`, source
  `atwood-hydro-flame-parts-lists-drive-supplied`, publisher Dometic). First use 27 Nov: 7900-II/8012-II, 8500-IV, 8900-III.
- `scripts/aftermarket_pdf/webasto_catalogue.py` — Webasto 2024/25 Commercial Vehicle Heating & A/C catalogue (North America):
  "[Part Rendering |] Part Description | Voltage | Part Number" tables. Pass A dict lines, pass B word runs by baseline;
  wrapped description lines joined; voltage appended "(12 V)". Held (reported, not loaded): numbers with no voltage cell on
  their line (two numbers in one cell, bottom-aligned cells), numbers with a description line directly above them, "P/N:"
  numbers in adapter-selection charts (test: `tests/test_webasto_readers.py`, source
  `webasto-cv-heating-catalogue-2024-drive-supplied`, manufacturer `Webasto` added 27 Nov).
- `scripts/aftermarket_pdf/webasto_spare_parts_list.py` — Webasto multilingual InDesign "Spare parts list" PDFs (Pos | rotated
  version columns with square glyphs | Part no. | Description in 5 languages; Air Top Evo 40/55, Thermo Top Evo 4/5/5+).
  English description only; rows whose English text wraps are held (pass A reads one line). Source
  `webasto-spare-parts-lists-drive-supplied`.
- `scripts/aftermarket_pdf/webasto_word_spare_list.py` — Webasto North-America bilingual Word spare parts lists (Air Top
  2000 STC): find_tables cells mapped to header columns by x (find_tables splits columns oddly under rotated headers);
  checked by "every number on the page is a row, inside a Notes cell or in a footnote sentence" + page image. No unit test
  (needs real table geometry).

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
  Nearly every Dexter product bulletin and the Dexter running-gear service manual are protected this way
  (PB427, PB469, PB479, PB493, PB494, PB522 so far): test `doc.permissions & pymupdf.PDF_PERM_COPY` first.
- 27 Nov ~03:20 run: Ventmate replacement vent lid sheets name only the vent styles they fit (Ventline, 1995+
  Elixir, Heng's, 1995+ Jensen) with no OEM numbers: Ventmate identities loaded, no replacement links (fitment).
  Automatic Distributors (Autodist) 2016 trailer catalogue (4 splits): PART # (distributor stock) / MFG # (unnamed
  maker) with prices -> held with the distributors.
- 27 Nov ~04:20 run: Dexter "Trailer Parts & Accessories" catalogue V1-24 (dexterindex.com, 8 splits, 516 pages) is
  Dexter's branch/distribution catalogue: every table is PART # / REF # (branch stock number) / DESCRIPTION, but it is
  multi-brand and only ~48 of ~570 tables in pp 1-387 have a "GENUINE DEXTER" / "DEXTER" heading (others: TRAILER
  PARTS PRO, ROCKWELL AMERICAN, "KODIAK AND DEXTER", "FITS AL-KO ...", or no maker printed). The last split's
  "PART # INDEX" gives page numbers only (no description, no maker), so it is not an identity source like the CURT
  index. All 8 splits held with the distributors; a reader would keep only Dexter-headed tables (watch the duplicated
  K08-249-1G on printed B12/B13, listed once as idler hub and once as hub-drum).
  "Dexter and Kodiak - Trailer Brake Parts Catalogue" is really "Section C Brake Assemblies" of a distributor
  catalogue branded "TRAILER REPAIR PARTS" (PART NO. / REF. NO.) -> held with the distributors. Keystone RV safety
  advisory 21-214 (approved replacement regulators for the recalled Winn-Tec 6020) is an RV builder's statement about
  other makers' regulators -> held for the third-party tier decision. PB442, PB461 and PB509 are copy-restricted
  like the other Dexter bulletins. Kodiak 2019 disc brake catalogue (3 splits, 44 pages): multi-layout kit / caliper /
  bracket tables -> held for a dedicated Kodiak reader.

## Conversion kits (relation `replaces_with_kit`, claim kind `conversion_kit_replacement`)
Approved by Larry, 26 Nov 2026 23:15. Use when a maker says its part/unit replaces another only
together with an adapter / conversion / retrofit kit, or its product is itself a retrofit kit.
Stage in `aftermarket_assertions_v1` with `qualifiers.kit_parts` (array of {maker, number[, description]})
and `qualifiers.conditions` (installation conditions); the replacement maker must be the publisher.
Publisher: `rv_private.publish_conversion_kit_replacements_v1()` (cron every 10 min). Claims always
carry `requires_conversion_kit`, `not_a_direct_swap`, the kit parts and the conditions.
First uses: Coleman-Mach 1976-579 Carrier adapters (16), PD4600 converter-section kits (9, reclassified).
- 27 Nov ~05:20 run: 31 new PDFs registered (Webasto 2024-2025 heating/A-C catalogue 6 splits, Pennine & BCA converter
  catalogue 4 splits, Reimo windows/doors/locks 2025 4 splits, Dometic fridge/A-C/furnace lists, Lippert/Furrion CCD sheets,
  SHURflo 4008, Camec doors). PB456, PB473 and PB520 are copy-restricted like the other Dexter bulletins. The two
  "Dexter UFP LIT-708-00UFP" splits are ChatGPT copies of the catalogue already published in full on 26 Nov (source.txt
  original hash 50943e2e...) -> done, nothing new. Dometic 620325.421 has a private font encoding (text layer is
  gibberish) -> held for OCR; don't decode by guesswork. Camec DOORS section (catalogue pp 216-227) held for a dedicated
  reader (code - description lines, spec tables with empty cells and repeated rows). Kodiak 2019 splits pp 21-38 and
  39-44 held with pp 1-20.
- 27 Nov ~06:19 run (session_017XuwiKsner4TF8gQhL3Z3a): batch-2 folder (1C7JQKHZ...) holds only the 00 brief so far (no
  PDFs, no SOURCES.md). 31 files processed: 21 done (Dometic fridges/toilets x9, Dometic Penguin II, Brisk II, DF furnace,
  Furrion tankless, Thetford US sheets x8), 10 held. Held for OCR: Dometic RM2410 106847 and RM2310 (scans), RM2193 106800
  and ice maker 106600 (private font encoding, like 620325.421). Held for readers: Dometic RM2351 (Dometic LLC US
  "Index No. | Part No. | A | B" layout), Modularized Brisk Air 579 3308714.025 (rotated model columns + discontinue /
  start dates + option tables), Thetford European spare-parts-list layout (C500, C220, Caprice cooker SOH72XXX, Bravura:
  up to three "Spare part number" columns per row). Remaining Dometic family files: RV Customer Service Replacement and
  Training Binder, WH-6GA/WH-16GEA and WH6EA water-heater lists (not yet looked at).
- 27 Nov ~06:49 run (session_017XuwiLwXBAG6sjfMy26bDA): no new PDFs in Drive since 05:05 (batch-2 folder still only the 00
  brief). Families: dometic atwood (9 files: 3 furnace lists published, 80 new parts; training manual pp 1-27 nothing to
  load; pp 28-54 parts pages are images -> OCR; Wedgewood 33/35 range matrices and the water-heater training slides held for
  readers) and webasto (9 files, all done: 372 new parts). Wedgewood 33/35: Item | Description | 6 model columns under a
  3-row header (WEDGEWOOD/ATWOOD, RV/CV/RA/CA, 1733/2133/33) with colour / burner-position variants right-aligned in the
  Description cell and continuation rows holding only the variant ("Black", "Bisque") -> base description + variant.
  Thetford family (8 files): Electra Magic 80 and Porta Potti Curve published with thetford_us_sheet.py (Curve: 8
  supersessions to the legacy-map v2 lane); Tecma Silence Plus 2G held (shared "Superseded by" / seat-model cells);
  Triplex SOH76/SOH77, Enigma SOH46 cookers and N3000 / N4000 fridge lists held for the Thetford European
  spare-parts-list reader (SSPAnnnn numbers with production-date qualifier lines and colour suffixes).
- 27 Nov ~07:19 run (session_017XuwiMe8BmEoSayDLzFYRZ): batch-2 folder now has 9 PDFs + SOURCES.md (all registered at
  priority 10). Their titles use " – " (en dash), so the generated `family` column is the whole lower-cased title
  (it splits on " - " only); claim them with `claim_drive_intake_v2(session, n, null, 'aftermarket_xref')`.
  Published (relation `replaces`, staged via `scripts/aftermarket_pdf/stage_sql.py`-style SQL, compact VALUES):
  Dometic fridge replacement chart 151 rows (whole-unit, dimensions + cut-out check on every claim), Progressive
  Dynamics crossover 66 rows (54 new claims), WFCO 2025 cross-reference sheet 148 rows (144), RV Designer vent lids 12,
  SKF interchange 5 Dexter seal rows. Advent Air Coleman chart: 27 rows staged as `fits_model` (compatibility through
  ACCOLKIT; no Coleman part is replaced), not published. Peterson + the two Grote lighting interchanges held for
  Larry's scope decision (~3,200 bare heavy-truck lighting number pairs, no descriptions, none of the makers in the DB).
  Brand aliases added: Powermax/POWER MAX -> PowerMax, Iota -> IOTA, CAMCO -> Camco, HENGS -> Heng's,
  VENTLINE -> Ventline, plus upper-case WFCO headings (MAGNETEK -> Parallax as before, FURRION, XANTREX, ...).
- **Prefix-ignoring OEM match hazard** (`aftermarket_oem_match_v1` outcome `matched_ignoring_letter_prefix`): when one
  batch creates an OEM identity "641" and later rows name "N641", the later rows match "641". It happened with the Dometic
  chart (Norcold 641/N641, 841/N841): the wrong claim was revoked (`state='revoked'`, reason in restrictions), Norcold
  N641/N841 created with `aftermarket_oem_create_v1`, the six rows re-staged and re-published. After publishing, check
  `restrictions->>'oem_match'` for anything other than `create` / `matched` and look at each one (WFCO WF-8735 -> 8735
  is a correct example).
- Readers added: `dometic_fridge_replacement_chart.py` (pdftotext -layout vs word columns; bare option numbers take the
  previous prefix only if that full model is printed somewhere on the page), `advent_coleman_chart.py`,
  `pd_crossover_list.py` (merged PD cells from the ruled lines; text-layer line multiset check), `rvd_vent_lid_xref.py`,
  `skf_interchange.py` (dotted-leader "Mfr no. | Mfr. | Part no." index, any page), `wfco_crossref_sheet.py`
  (pdfplumber vs pymupdf words over the same table geometry; WF-5220/5320 pairs, "/" shorthand, broken numbers and
  continuation lines printed in the WFCO column are held). Helper tests: `tests/test_batch2_xref_readers.py`.
- 27 Nov ~07:50 run (session_017XuwiLc3tgwP1DWnddbwAz): no new PDFs in Drive since 06:55. 24 files: Norcold 7 (5 done,
  N41/N51 623424 and N61/N81 623421 copy-protected -> skipped), Dometic Seitz 6 done, Suburban 5 (4 done, water-heater
  service manual held: Paper Capture OCR layer with errors), small Dometic families 6 (RM2553 and CT3000 Australia with
  dometic_spare_parts_list.py, B3200 3253.332C and Duo-Therm 6206xx.33(X) with dometic_parts_list.py; 59516 Brisk Air list
  held: private font; CAL61/CAL136 held: 4 of 7 pages are scans). 507 new parts, 31 Norcold supersession claims.
  - `scripts/aftermarket_pdf/norcold_parts_list.py` — Norcold / Thetford-NA refrigerator lists (NO. | PART # | DESCRIPTION |
    model columns [| WARRANTABLE]). The legend differs between lists and even between pages of one list (2118 p7: "*" = not
    available, grey = no longer available; other pages "*" = limited availability, grey = not available) -> read per page;
    "***" footnotes kept in words; grey shading from filled rects (cell-only on 2118, whole row on N2090/N2152). One PART #
    cell spanning two rows (692758 DOOR LATCH ; WINTER LOCK SUPPORT) keeps both texts. SUPERSEDED TO / (USE n) / "- REPLACES
    a & b" go to the legacy-map v2 lane; a number given two different successors (2118: 636863, 633325) is held.
    Test: `tests/test_norcold_parts_list.py`.
  - `scripts/aftermarket_pdf/seitz_spare_parts.py` — Dometic Seitz DOK window / rooflight sheets. "BG 1517" stored as BG1517
    (the sheets print both); placeholders ("BG1086...", "IRE05..."), alternatives ("FM80/82") and other spaced codes are
    reported, not loaded; a number printed for two different rows on one page (S6 BG1078 right and left handle) is held.
    Test: `tests/test_seitz_spare_parts.py`.
  - `scripts/aftermarket_pdf/suburban_parts_table.py` (IW60 / SFV ruled tables, reuses the Norcold geometry helpers) and
    `suburban_catalogue.py` (2025 aftermarket catalogue stock-number lines; furnace core cross reference -> 11 cores named
    "Furnace core replacement [models: ...]", NTP-STAG distributor numbers not loaded). The catalogue's "Dometic/Atwood Style
    Replacement Panel" and "only direct replacement for 6-gallon Atwood/Dometic water heaters" name no Dometic/Atwood part
    number -> no links. Test: `tests/test_suburban_literature.py`.
- Norcold N1095 (624870) is copy-protected -> skipped. N2090, N2152 and 2118 PolarMax were claimed and released
  unprocessed with layout notes (NO. | PART # | DESCRIPTION | X model columns; vertically centred numbers; SUPERSEDED TO
  notes; shaded = NOT AVAILABLE); 105 of their 267 numbers are already Norcold parts.
- 27 Nov ~08:20 run (session_017XuwiMgNdUE7HhicEwjo7T): no new PDFs in Drive since 06:55. 21 files: Truma 5 (3 done, 2 held),
  Eberspächer 5 (3 done, 2 held), Dometic SeaLand 4 (partly published, held for rotated sheets), Girard / Girard Lippert 7 done.
  880 new parts (Truma 64, Eberspächer 164, SeaLand 463, Lippert/Girard 189), 557 existing parts evidenced, 4 Truma
  supersessions. Manufacturer `Eberspächer` added (brand aliases Eberspaecher / Eberspacher / upper case).
  - "Truma - Caravan Heating and Water System Spare Parts Catalogue" (2 splits, camperlands.co.uk copy) prints Truma No. |
    Grove No. on every table -> held with the distributors, like the AL-KO / Grove list.
  - The Truma Dealer Catalog 2025 was already loaded (source `truma-dealer-2025-reviewed`, selected tables); that load had
    merged page 5's old/new columns into names ("Truma CP plus 36023-01 Truma CP plus") -> 6 names corrected with
    `name_correction` audit events; the page's "Discontinued with replacement" table went to the legacy-map v2 lane.
  - `scripts/aftermarket_pdf/truma_dealer_catalogue.py` — Truma Dealer Catalog 2025: part number in the Part No. column + bold
    product name on the same baseline (pymupdf spans vs pdfplumber words with font names); "Changes to our product portfolio"
    page -> `supersessions` / `discontinued`.
  - `scripts/aftermarket_pdf/truma_parts_viewer.py` — Truma dealer parts-viewer printouts (Pos. | No. | Description |
    Information; number wrapped in its cell "60030-" / "88700", rows broken across pages; row bands from the drawn rules;
    placeholder 00000-00001 skipped). First use: Mover SR from 09/2011.
  - `scripts/aftermarket_pdf/eberspacher_spare_parts_list.py` — Eberspaecher SPARE PARTS LIST (Airtronic S3/M3, Airtronic 2 NA):
    number -> designation block of its item starting at or above it ("Blower 24 V ..." starts on the first 24 V number);
    pdfplumber lower-cases some UniversNext capitals ("order", "m3") -> rows compared case-folded; size/variant-line numbers
    ("Ø 90 mm") and numbers under two designations not loaded. Still held: Espar Airtronic D2/D4 manual (numbers printed with
    spaces "25 2069 99 06 00": needs a number-format decision) and the 2022 NA catalogue (heading + variant-line layout).
  - `scripts/aftermarket_pdf/dometic_sealand_parts_list.py` (+ `sealand_colour_conflicts.py`) — SeaLand guide: 9-digit number +
    description on one baseline (dash lines and ruled tables alike); right-hand table ITEM numbers between a description and
    the next number dropped; sheets printed rotated on the page skipped (~600 numbers across the 4 splits wait for a rotated-
    sheet extension: transform word boxes by the line direction); 18 numbers printed with different colours on different
    sheets not loaded. Model index pages (Model | Description | Item | Ref. List #) not read yet.
  - `scripts/aftermarket_pdf/lci_component_chart.py` — Lippert/Girard component charts without Quantity/Model columns
    (pymupdf find_tables vs pdfplumber extract_tables; colour part-number columns; header-less continuation tables).
    `lci_ccd_model_list.py` extended: "All" model cells dropped, callout-letter runs end a description (Girard GSWH-2).
  - Tests: `tests/test_drive_intake_mgnd_readers.py`.
- 27 Nov ~08:50 run (session_017XuwiPbNJ6nszrfu5pC1BQ): no new PDFs in Drive since 06:55 (batch-2 folder unchanged).
  14 files: 8 done, 6 held; 70 new parts (Dometic 41, Thetford 29), 310 rows loaded, no cross-maker links (all OEM lists).
  - `scripts/aftermarket_pdf/dometic_wh_service_kits.py` — Dometic (ex-Atwood) water-heater service-kit lists: InDesign
    "Service Kit Parts Descriptions" (X-mark model columns | Service Kit Number | Description; footnote superscripts on
    the model headers dropped by font size; "(like 91858 ...)" continuation lines; footnotes "1\x07The ..." stop a row)
    and the DITA "Spare Parts" table (Ref.No. | Pos | Qty | Description, English table only). The illustration page's
    callout numbers are compared with the table (WH-6GA list: 92568 / 94016 / 94067 printed only on the illustration,
    not loaded). Source `dometic-water-heater-service-kit-lists-drive-supplied`. The WH6EA sheet carries a DRAFT
    watermark (kept in the section label).
  - `scripts/aftermarket_pdf/thetford_eu_spare_list.py` — Thetford Europe Word spare-parts tables (No. | Description |
    1-3 "Spare part number" columns | Colours). A number covers every item line of its cell; cells are bounded by the
    same-class run (rule / grey shading / white) at two sample x positions per column, computed twice: pass A from the
    vector paint order, pass B from the rendered page. Needed because visible rules alone over-extend shaded cells
    that sit on an unshaded cell with no rule (C200 23848), and shading alone cannot split two shaded cells with no
    rule. Several numbers in one cell, or a white cell over several item lines with the number on one item's baseline
    (S220 212369 "Rim"), are matched to their own item line. Grey numbers = "not available anymore" (only when the
    legend is in the document). Dates (06-12-16) are qualifiers, not numbers. Source
    `thetford-eu-spare-parts-lists-drive-supplied`. Published: C200, C220, C260, C500, S220, S260, Bravura page 2.
    Still held: Bravura page-3 "Optional Extra's" (letter items, no "Spare part number" header); cookers Caprice
    SOH72, Enigma SOH46, Triplex SOH76 / SOH77: the production-date qualifiers print "≥" as ">" plus a separate
    underline drawing (the text layer says ">"), item rows with production-date sub-rows lose the item name, and two
    SSPA numbers at mid-row positions in one shaded cell are not assignable. In SOH76 the "≥" is a ">" glyph with a
    glyph-wide underline drawing just below it (C260's ">" has none), so an underline check would fix blocker 1.
    N4000 (116 numbers) and N3000 (141 numbers) partly published: only rows both passes give identically; N3000 rows
    with < > ≥ ≤ qualifiers or cut-off italic descriptions (text running into the number column) left out. Not read
    yet: continuation pages without a header (N4000 pp 24, 29), control-panel pages with a one-line "Spare part
    number" header (N4000 pp 33/35/37), "626985**" footnote-marked numbers and framed/frameless variant rows whose
    numbers sit off the header columns (N4000 p7). The reader now reports every unread part-like token ("unread")
    and loads only agreed rows ("agree" = loaded rows agreed; "all_rows_agree" = no one-pass rows).
  - Dometic RV Customer Service Training Binder (81 pp) held: all same-maker (awning FRTA obsolete -> replacement tables
    with wildcard numbers like 834(XX)YY.400, A/C replacement decision trees, control-conversion kits, Air Command spec
    table); legacy-map v2 candidates once a storage rule for the wildcard patterns is decided.
  - Tests: `tests/test_thetford_eu_and_dometic_wh.py`.
- 27 Nov ~09:20 run (session_017XuwiLAuZNuf7cwtm4tBN9): no new PDFs in Drive since 06:55. 64 files: 53 done, 11 held; 359 new
  parts (Dometic 65, Lippert 294), 25 Lippert supersession claims, no cross-maker links.
  - `scripts/aftermarket_pdf/dometic_coolfreeze_parts_list.py` — Dometic LLC (Waeco) CoolFreeze CF parts list 3312482.023
    (Index | Part Number | [Model] | Description; "CF-035AC110 = A" legends with A / B / -- marks; "fits serial numbers:"
    ranges and "(same p/n as above)" rows folded into the row above as qualifiers; "*" = WAECO branded units, "**" picture
    marks dropped). Source `dometic-portable-fridge-parts-lists-drive-supplied`, drop c1f9e08b55c473ca (105 rows, 65 new).
    Test: `tests/test_dometic_coolfreeze_parts_list.py`.
  - Fiamma: the 12 "Spare Parts Catalogue 2026" splits (source.txt original 7d4f7cb4..., fiammaexpert.com) and the 15
    "Fiamma_2024_spare_parts" splits (number set = the fiammausa.com 2024 load 77cd0ec4...) are copies of catalogues loaded in
    full on 18-19 Nov -> done, nothing new. Quick duplicate check without pasting thousands of numbers: compare per-prefix
    md5s of the sorted number sets (`left(number,6)`, `md5(string_agg(number, ',' order by number collate "C"))` on
    `rv_read.parts where sha256=...`) with the same computed locally from the splits' text layers. Only footnote-marked
    prints differ (02426A09A*, 98660-249*/250*/251*, 98655-941(Top), 08455-01P-, ...): a footnote-aware reader could add ~10.
  - Fiamma 2009 (3 splits) held: 570 of its 848 numbers are not in the DB, but the catalogue (like all Fiamma spare-parts
    catalogues) is exploded drawings with callouts only, no part names, so the supplied lane has no description to load.
    Needs the lane that loaded 2024/2026 (page + position evidence, placeholder names) or Larry's OK to use the drawing
    heading as the description. Fiamma 2025 (14 splits) still `new`: check its number set against 2024/2026 the same way first.
  - Thetford_General_spares.pdf (104 pp, Thetford Part No. | Grove Part No., no publisher printed) held with the
    Grove-numbered distributor lists.
  - Fiamma 2025 (13 splits): 2597 numbers, all but 98673-365 already loaded from 2024/2026 -> 12 done, pp 001-009 held with the
    2009 callouts for that one number.
  - `scripts/aftermarket_pdf/lci_ccd_noqty.py` — Lippert CCD lists with no Quantity column ("Callout | Part # (or Kit #) |
    Description"): text-line pass vs word-position pass, agreed rows only ("all_rows_agree" says whether one-pass rows were
    left out: wrapped descriptions, a callout cell with two numbers). "*" numbers are loaded only on a page that prints
    "*Part must be replaced using variant code" (note kept in the description); an empty trailing "-" Measurements cell is
    dropped. Used for CCD-0008624, 0002690, 0002709, 0002666, 0001966, 0001602, 0007723, 0004465, 0002589, 0002688 (source
    `lippert-ccd-component-lists`). JT's Strong Arm (with a Quantity column) still reads with `lci_ccd_list.py`.
    Test: `tests/test_lci_ccd_noqty.py`.
  - Lippert "(OBSOLETE - Use N)" / "(Obsolete: Replace with N)" notes in agreed rows -> legacy-map v2 lane (scope
    `manufacturer_supersession_chart`, extraction `lci-ccd-obsolete-note-v1`): 18 pairs over 5 CCDs. LIP Sheet 0280 (through-
    frame slide-out inner tube revision) "Old w/ Rear Roller -> New w/ Wear Tab" table: 7 pairs ("100% interchangable"), the
    5 new-only arm assemblies and the 3 page-1 components through a small drop.
  - Held: Lippert IDO-484 (Print-to-PDF scan, OCR); Lippert Premium Axle and Suspension Parts Catalogue 2025, 2 splits
    (multi-layout: retail clamshell tables, Part # | Item # | Description | Qty wheel-end tables, product pages). CCD-0010172
    (Gen I -> Gen II jack procedure) names no part pairs -> done, nothing to load.
  - Zip Dee door / patio / slideout awning parts sheets held: no maker name or logo printed anywhere in them (only source.txt
    says awningsbyzipdee.com, hash matches), and "Zip Dee" is not a manufacturer in the DB yet -> Larry's call on the
    publisher. Reader ready: `scripts/aftermarket_pdf/zipdee_parts_list.py` (Ref # | PART # | description; patio 40/40 rows
    agree, door 30, slideout 21; kit-content blocks where the kit title row has no Ref # are left out).
- 27 Nov ~09:49 run (session_017XuwiLMGPirfH4HBEcuVj8): no new PDFs in Drive since 06:55. 24 files: 4 done, 20 held.
  109 new cross-maker replacement links (MORryde pin boxes), 319 new Valterra parts.
  - `scripts/aftermarket_pdf/morryde_pin_box_chart.py` — MORryde Aftermarket Product Catalogue 2021 v7b, "RUBBER PIN BOX FIT
    CHART" (printed p16, split pp 011-021 page 6): Cross Reference Guide MFG | MODEL# (stock pin box) | MORryde part per trailer
    GVWR band | MORryde Pin Box Rating; MORryde asks for the stock pin box's part number to order, and p15 says the Rubber Pin
    Box is "designed to directly replace the Lippert Rhino Pin Box". pymupdf find_tables vs pdfplumber extract_tables (43/43
    rows agree). Staged as relation `replaces` (source `morryde-aftermarket-catalogue-2021-v7b`, maker `MORryde` added, category
    running_gear) with trailer_gvwr, morryde_pin_box_rating and the "GVWR above are general guidelines" footnote on every claim:
    109 claims published (Lippert, Leland, Fabex, Youngs Welding, RBW, Dexter pin boxes; 35 stock pin box identities created,
    no prefix-ignoring matches). Comma lists of plain numbers split (Leland "7920, 7921", Fabex "300,314,316"). Held: named
    sizes without numbers (Lippert Rhino, Venture Med/Long, Seitz Long, Youngs Welding Long/Medium/Short/45 degree),
    "Lippert 1621, SHD-TA" (one model or two?), "Atwood AB-34 HD" (space) and Atwood AB-72: the DB alias Atwood -> Dometic was
    set for Atwood appliances and the page does not say who makes Atwood pin boxes now. Other MORryde splits (steps, TV
    mounts, trays, X-Brace) and the Airstream StepAbove size chart: MORryde's own products by trailer dimension -> held
    (fitment lane; supplied-lane candidates).
  - `scripts/aftermarket_pdf/valterra_retail_catalogue.py` — Valterra RV Retail Parts Catalogue (39 pp, "Part No. | Ctn.Qty. |
    Ctn.Wt. | Retail Price"): pymupdf words vs pdfplumber words with one row rule (Part No. column + three numeric cells right
    of Ctn.Qty., "50/200" carton cells allowed; wrapped lines at the description indent belong to the row). pdfplumber glues
    words around commas, so the passes are compared with spaces removed. Drop e8971a7e156befc8 (key id
    `drops-2026-11-27-intake-lmgp`, source `valterra-retail-catalogue-drive-supplied`, manufacturer `Valterra` added): 319 new
    parts. Not loaded: 14 "Same as above" rows, 10 one-pass rows (superscript fractions lost by pdfplumber), 2 numbers printed
    twice with different wording. "Bladex valves are interchangeable with Valterra, Grentec, Anonda, Larden, and Bristol
    brands" names no numbers -> no links.
  - Tests: `tests/test_morryde_valterra_readers.py`.
  - Held with the distributors: Movera Caravan Workshop and Spare Parts Catalogue 2017-2018 (5 splits; Movera-Nr. | Hersteller-Nr.
    under maker headings FIAMMA / THULE / TRUMA / THETFORD / SEITZ / AL-KO) and "20 RV Designer - Dealer Hardware Catalogue
    Excerpt" (really a distributor's section G, "G20_233-244": 5-digit order numbers + "#" maker numbers, JR Products etc.).
  - Held, fitment: Firestone Airide 2026 application guide (2 splits) and Ride-Rite service air springs (2 splits): vehicle
    tables of Firestone's own kits and service springs, no other maker's numbers. TriMark Handles Catalogue (2 splits): all
    62 pages are images -> OCR.
  - Held for readers: Marshall Excelsior LP gas catalogue 2023-2024 (free-form product blocks with "Bulk# / Packaged#"),
    Ventline (Dexter) ventilation parts catalogue (multi-layout; garnish numbers built from base + suffix columns), Flojet
    R3426504A datasheet (~25 accessory numbers on p3). Flojet Q301V-117S-3A "Replaces (closest matches): 04406143A R4406143M"
    is Flojet's own older models and only "closest" -> not loaded. SHURflo 4048 / 4008 data sheets: every number already in
    the DB -> done, nothing new.
- 27 Nov ~10:19 run (session_017XuwiLMxKKnRRrA9Uyz3gG): no new PDFs in Drive since 06:55. 42 files: 7 done, 33 held, 2 skipped.
  1939 new parts (Thule 1670, Generac 221, Knott 40, Lippert 8), 1015 existing parts got new evidence (Knott 709, REMIS 287,
  Lippert 19), 1 Lippert supersession (HappiJac controller 139315 -> upgrade kit 733540). No cross-maker links (all own lists or
  distributor catalogues). Manufacturers added: `Thule`, `Generac`.
  - `scripts/aftermarket_pdf/thule_spare_parts_price_list.py` — Thule "RV Accessories Spare Parts 2023 price list" (Excel export:
    Pos | ART.NR. | DESCRIPTION | Price under each drawing; continuation pages repeat no header and start at y ~43; the footer
    page number can share the last row's baseline). Word positions vs text-line order. 143 numbers printed with two different
    descriptions (one roller tube for 4200 / 5200 / Tristor) are not loaded. Source `thule-rv-spare-parts-price-list-drive-supplied`.
  - `scripts/aftermarket_pdf/knott_spare_parts.py` — KNOTT Trailer Technology spare parts catalogue 2019 (German): Pos | Bezeichnung |
    Bestell-nummer, rows vertically centred (pass B cuts row bands half-way between position numbers), "auf Anfrage" rows have no
    number, "siehe S. 185-191" is a page reference. Order numbers: 42191, D94.013, 33921-1.06, 409697B002, 47305V, 8710311314,
    6J1031.006 ... Split pp 193-384 pdf pp 158-181 (overview tables) are not read yet. Source `knott-spare-parts-catalogue-2019-drive-supplied`;
    673 of its 713 numbers were already Knott parts from the 2026 catalogues.
  - `scripts/aftermarket_pdf/header_table_parts.py` — generic one-line parts table found by header words
    (`<num_label> <desc_label> [stop labels]`): Generac "PART DESCRIPTION ITEM,QTY." and REMIS "number Description Image".
    Descriptions may start left of their header word (REMIS), so the column begins after the widest number.
  - `lci_ccd_noqty.py`: left/right callouts "E/L", "E/R" now end a description (Thule 5200 CCD-0003803); a number printed
    against two different descriptions (LH and RH endcap) is not loaded and is listed in "conflicts".
  - Tests: `tests/test_thule_knott_readers.py`.
  - **Lippert CCDs for Thule awnings print Thule ART.NR. numbers** (CCD-0003803: 10 of 18 numbers identical to Thule's own 2023
    list) without saying whose numbers they are -> held for Larry: load them as Thule evidence, or not at all (as Lippert parts
    they would duplicate the Thule identities).
  - Held for readers: MPK rooflight catalogue (bilingual colour-column tables with sub-rows; a first attempt agreed on too few
    rows), Zadi 2026-2027 locks (multi-layout), Reimo 2025 windows/doors (vehicle fitment tables with prices), Demco 2026
    (product attribute tables; "SAME AS" = same-maker knocked-down kit), Roadmaster Falcon / Sterling tow bar component pages
    (dotted leaders, two-line descriptions), Kwikee step guide 82-ST0501 and kit sheet #214 (also a maker-name question:
    Kwikee / Power Gear are not manufacturers in the DB).
  - Held with the distributors: MF Campingwelt 2021-2022 (Hersteller Nr. | Art-Nr.), Euro Accessoires 2008, Moog 2024 ("für/for
    ALKO / KNOTT / BPW" axle and coupling types = fitment), Vecam 2015 (R-numbers, partly private-font text), Grassroutes Leisure,
    Pennine Leisure Supplies / BCA converter catalogue, the RV Supplies (NZ) Powrtouch Evolution list.
  - Skipped (copy-protected): Power Gear hydraulic leveler manual 82-L0040, Knott Avonride UK catalogue.
- 27 Nov ~10:49 run (session_017XuwiMX8W6KFHvosgMG6Yg): no new PDFs in Drive since 06:55. 13 files: 6 done, 9 held (11 new + 2 held
  re-checked), plus 2 turned SeaLand sheets read for a held split. 444 new Lippert parts, 16 new Dometic (SeaLand) parts, ~1,100 existing
  parts evidenced. No cross-maker links (all own-maker lists or fitment guides).
  - `scripts/aftermarket_pdf/lippert_catalogue_tables.py` — Lippert retail catalogues (2023 CATALOG, 3 ChatGPT splits; Premium Axle and
    Suspension Parts Catalogue 2025, 2 splits): shaded product tables with a part-number column ("Part #", colour columns "Black # |
    White #", packaging columns "Retail Clamshell # | 10-Pack # | Brown Box #"). Pass A pymupdf find_tables() cells, pass B pdfplumber
    words inside the same cell boxes. Description = Description cell or the product heading (DINOT-Black >= 17 pt lines above the table)
    + "Header: value" attributes; colour / packaging label appended. "Industry #", "OEM #", "Bearing Kit #", "Suggested Nut #",
    "Suggested Idler Hub #", "Seal #", "Sleeve #", "Switch Kit #", "Cartridge Replacement #" are never part columns. Tables whose number
    column find_tables clips ("t #" headers: Kwikee steps, pin boxes) and vehicle fit charts ("Part#") are not read. Test:
    `tests/test_lippert_catalogue_tables.py`. Sources `lippert-2023-catalog-drive-supplied` (URL = Drive copy of the unsplit file; the
    original web URL is not recorded) and `lippert-premium-axle-catalogue-2025-drive-supplied`.
  - The 2023 catalogue's cross-brand wording is fitment only: Solera "universal hardware" fits Carefree / Dometic (A&E) awning models,
    Girard door kits fit Suburban / Atwood / Dometic water-heater sizes, and the awning page maps new to old Solera series names (no
    numbers). The pin box tables (split 3 pp 66-69) print "OEM #" 1621 / 1116 / 0719 next to Lippert pin box numbers, which may answer
    MORryde's "Lippert 1621" question, but the part-number column is clipped by the table finder there (not read).
  - `dometic_sealand_parts_list.py`: sheets printed turned on the page with every line running bottom-to-top (dir (0, -1)) are now read in
    the sheet's reading frame (x' = page height - y, y' = x; pdfplumber `char_dir_rotated="btt"`). Split pp 001-033 guide pp 17-18 loaded as
    a supplement drop under the same name (previous result kept as `result.previous_load`). The other three splits still list rotated
    pages: re-run them with the extension (check each page's direction set first; upside-down / top-to-bottom sheets are still skipped).
  - Held, fitment: Cummins Onan F-1061 Green Label parts reference (Onan filters / plugs / kits by generator model; the superscript letters
    after numbers such as 140-2105C are service intervals), Air Lift Load Support Application Guide (2 splits; p 10-11 service parts are a
    supplied-lane candidate), Horizon Global Towing & Trailering 2022 Application Guide (5 splits; multi-layout catalogue, no Horizon Global
    brand in the DB yet; ModuLite 119147 "(Replaces 119179)" etc. on split pp 126-250 PDF p61 = same-maker supersessions).
- 27 Nov ~11:19 run (session_017XuwiMBAChqhVFCTEkQZJ1): no new PDFs in Drive since 06:55 (nothing registered). Re-checked 9 held files
  (claimed from `held` by setting status `claimed` with this session id): 5 done, 4 re-held (one of them partly published). 295 new parts
  (Dometic: RM2351 48, Wedgewood 33 series 75, Wedgewood 35 series 27, Brisk Air 579 96, 620315.421 options 23; Flojet 26), 148 existing
  parts evidenced. No cross-maker links (all
  own-maker lists; every held cross-reference file still waits on one of Larry's decisions: third-party tier, Peterson/Grote scope,
  Zip Dee publisher, Lippert-printed Thule numbers).
  - `scripts/aftermarket_pdf/dometic_llc_index_list.py` — Dometic Corporation US-format refrigerator PARTS LIST (RM2351 form 3311745.000):
    Index No. | Part No. | A | B | Description with the "Model RM2351 Prod # 921145039 = A" key printed above or below the table ("--" =
    not for that Prod #, kept as "[applies to: ...]"). Pass A text lines from the "Only Those Parts ..." line (the key lines can come after
    the table in text order), pass B word boxes by header columns. Source `dometic-us-refrigerator-parts-lists-drive-supplied` (new).
  - `scripts/aftermarket_pdf/wedgewood_range_matrix.py` — Atwood / Wedgewood range & slide-in cooktop "Parts Drawing & List" matrices
    (33 and 35 series): 3-row header (WEDGEWOOD/ATWOOD, RV/CV/RA/CA, 1733/2133/33 -> "Wedgewood RV 1733" ...), cells vertically centred in
    ruled rows. Pass A pymupdf dict lines (blank cells are printed as whitespace-only lines, so each row is exactly one line per model
    column; a line that starts with 3+ spaces or right of the indent is a variant only), pass B row bands from the drawn horizontal rules +
    word boxes (variant = a segment that starts right of the indent after a > 12 pt gap). Variant-only rows take the description above.
    Numbers printed on rows that differ only by serial-break notes are stored without the notes. Source
    `atwood-range-cooktop-manuals-drive-supplied` (publisher Dometic per the Atwood alias). 35-series 18B/18C print only "Center Front" /
    "Right Rear": names say they are listed after 18A "Burner Tube - Left Rear" (`name_correction` audit events).
  - `scripts/aftermarket_pdf/dometic_model_matrix_list.py` — Dometic (Duo-Therm) roof A/C parts lists with rotated model columns (Brisk
    Air 579 series 3308714.025): Index | Description | Part No. | a mark or a dash per model | "**" discontinue / "##" start date. Marks are
    applicability only (the 579 list prints "G H" under the 57915.631/.731 columns on one row). Descriptions start ~9 pt left of their
    header. NOTE blocks and the "Customer Options (Required / Not Required)" tables (two unit-family columns, "----" = not offered) are read
    with pymupdf words vs pdfplumber words. Source `dometic-ac-parts-lists-drive-supplied`. Candidate for the other Dometic roof A/C lists
    with model matrices.
  - Supplement drops under an existing name: after pushing new bytes, raw.githubusercontent.com served the old file for ~5 minutes; wait
    until it serves the new bytes, then set the drop back to `queued` (rows with new `n` values load; existing rows are kept).
  - Tests: `tests/test_dometic_matrix_readers.py`.
  - `scripts/aftermarket_pdf/dometic_option_tables.py` — the "Customer Option" tables of Dometic roof A/C PARTS LIST sheets that
    dometic_parts_list.py leaves unread: "Component | Description" boxes (number first) and "Description | Part No. | Part No." assembly
    tables with one assembly number under each header ("[for 3106615.010]" when only one column prints the number). pymupdf vs pdfplumber
    words; optional page list. 620315.421 pp 5 and 7: 31 rows (supplement drop under the existing name 1b74f52430172388, n 201-231, key
    re-pointed to this run's key). Its p8 sensor table and p9 return-air kit table give empty descriptions (description cells apart from
    the numbers): not loaded; the 991760360 heat pump prints no such table.
  - `scripts/aftermarket_pdf/flojet_datasheet_accessories.py` — Flojet (Xylem) pump datasheet p3: Accessories sections split by the drawn
    full-width rules (heading in the left column of each band; names "<heading>: <description>", "(2-pack kit)" from the section note) and
    Pump Service Kits & Spares (item name + description column). R3426504A: 26 new parts, manufacturer `Flojet` added, source
    `flojet-pump-datasheets-drive-supplied`. Candidate for the Q301V-117S-3A datasheet (held only for its "closest matches" line).
  - Roadmaster Falcon / Sterling All Terrain tow bar component lists re-checked and re-held with layout notes (two text columns, dotted
    leaders glued to numbers, sub-entries without callouts, Falcon item 6 text layer clipped; Sterling 9 "replaces obsolete ... 200680-00
    and 654303" = same-maker supersession). Roadmaster is not a manufacturer in the DB yet.
- 27 Nov ~11:49 run (session_017XuwiLbFmcYsRLTJ2rAW5H): no new PDFs in Drive since 06:55. New folder "CamperPartMatch – Michael intake"
  (12ol5LqIt1YeJx3wDy166-Q3K6YpI4A35, created 11:27) holds only a "Source log" sheet of retailer web pages (Truma, lane A), no PDFs
  -> nothing registered. Re-checked the 4 held SeaLand guide splits: 172 rows, 124 new Dometic (SeaLand) parts, 48 existing evidenced.
  - `dometic_sealand_parts_list.py`: model-matrix sheets (ITEM | PART NUMBER with one column per toilet model | DESCRIPTION, guide p 57
    EcoVac 146-149, p 72 VacuFlush 1006-1049): a number whose baseline holds only other 9-digit numbers / N/A up to a stand-alone
    DESCRIPTION header column takes that column's words (left-aligned within 25 pt of the column; text far right is the models column:
    p 13 "974MSD" is not a description, the "MSD fitting" text is missing from the text layer). Leading "N/A" cells are dropped (the
    first load had published 385310137 / 385311086 as "N/A ..." names: corrected with `name_correction` audit events); descriptions
    starting lower-case are note sentences ("322404005 and 322404008 have non vented caps.") and are dropped.
  - `sealand_colour_conflicts.py`: the guide's colour abbreviations are compared as the full word (WHT/WHITE, BLK/BLACK, EBY/EBONY,
    CHR/CHROME, PLAT/PLATINUM, GRAY/GREY). 18 of the 21 "conflicts" were abbreviations only; 3 real ones stay out (385310809,
    385340177, 385345377). Test: `tests/test_sealand_matrix_rows.py`.
  - Supplement drops under the four existing names (n 301+ on each page, key `drops-2026-11-27-intake-lbfm`, previous results kept in
    `result.previous_load`). Only numbers not already loaded from the same split were sent.
  - **The SeaLand splits still need OCR**: about 49 sheets across the 4 splits have no text layer (sheet text drawn as vector outlines,
    e.g. guide p 34 "PARTS LIST: 4310 MODEL", or page images). Split 1 also waits for the model index pages (pp 3-11). All 4 stay held.
  - Atwood 2007 manual split pp 001-093 re-checked and re-held with per-page layout notes in its register row (~390 of ~510 five-digit
    numbers on split pp 46-83 are not in the DB). The p 67 / 69 "Parts Identification" text layer prints the while-supplies-last symbol
    as a trailing "a" (53198a) and obsolete cells as "52634OBS"; wedgewood_range_matrix.py finds no header on pp 65 / 71 even with
    upper-case ITEM / DESCRIPTION allowed.
- 27 Nov ~12:19 run (session_017XuwiPbS2EkJuxdRuDmsyT): no new PDFs in Drive since 06:55 (the Michael intake folder got six etrailer /
  Kwikee "xref.csv" files at 12:18: CSVs of retailer pages, not catalogue PDFs -> not registered). Re-checked 2 held Dometic/Atwood
  water-heater files: 1 done, 1 partly published and re-held. 57 new Dometic (Atwood) parts, 29 existing evidenced, 2 supersession
  claims; no cross-maker links (every held cross-reference file still waits on one of Larry's decisions).
  - `scripts/aftermarket_pdf/dometic_wh_training_tables.py` — Dometic water-heater training slides (PowerPoint, Dec 2019): two-up ruled
    tables "Model / Part # | Water Heaters / Replacement Tanks / Description | Status". Pass A find_tables cells, pass B word boxes in
    the row bands between drawn rules (tank cells are top-aligned, so number-anchored bands pick up the next row). Tank rows named
    "Replacement tank: <models printed in the cell>". Status codes (A, K, AS, B (8)) have no legend -> not loaded. 91514 is printed
    for a 6 gal Colonial White and a 10 gal Beige door -> not loaded. Source `dometic-water-heater-service-kit-lists-drive-supplied`.
  - `scripts/aftermarket_pdf/atwood_wh_part_reference.py` — Atwood 2007 manual "Electronic Water Heaters REPLACEMENT PART REFERENCE"
    (split pp 001-093, pages 46-47): "[callout] NNNNN description" with continuation lines after the check marks in text order and
    bold-italic "No Longer Available (Use N)" notes across the model columns (moved to the end of the description; the pairs go to
    the legacy-map v2 lane, extraction `atwood-wh-part-reference-nla-note-v1`). Model applicability not stored. The pilot
    water-heater pages 42-43 match the fingerprint but descriptions wrap onto 2-3 lines beside the number there, so the word pass
    disagrees; read only 46-47 (range argument). Test: `tests/test_atwood_wh_readers.py`.
- 27 Nov ~12:49 run (session_017XuwiNgVLgCkWhXNXs6DHQ): registered 32 files from Michael's folder (12ol5Lq...): 2 Thetford PDFs and 30
  Lane B "<source> - xref.csv" files. The prompt asks for family `michael-xref-csv`, but `family` is a generated column (first " - "
  part of the title); the migration that would map `%xref.csv` titles to that family was refused by the session's permission check,
  so the CSVs are registered with lane `other`, priority 15 and claimed with `claim_drive_intake_v2(session, n, null, 'other')`.
  35 files done: 1,010 new parts (Truma 926 via the Grove print, Eberspächer 84), 222 existing parts evidenced, no cross-maker links.
  - **Michael's CSVs (30 files, 49 lead rows) are all lippert.com (26), etrailer (2) and RecPro (2) pages** -> covered by the store
    readers, nothing staged (Results tab rows 2-31). Gaps found: 22 of the 26 lippert.com pages are not in `store_products_v1` or
    the store frontier (the 26 Nov sitemap load did not list them), and the store reader's compat rule does not capture lippert.com's
    labelled spec fields "Manufacturer Reference Number" + "Reference Vendor/Manufacturer Name" (Kwikee, Power Gear numbers) or
    "<builder> Part Number" (Jayco, Winnebago, Keystone RV, Thor, Grand Design), nor RecPro's "Heng's Part #" bullet (Heng's 90110-C1DL
    and 90112-C1 are already parts). A store-reader extension (store lane, not the intake) would turn these into evidence at scale.
  - Thetford C2 Electric Rev C: byte-identical to the C2 sheet already loaded. C402C/C403L Rev C: every number and all 14 supersession
    pairs already published from Rev D. Both done, nothing new.
  - `scripts/aftermarket_pdf/espar_airtronic_parts_list.py` — Espar AIRTRONIC D2/D4 manual parts list (pdf pp 31, 33-34) + cover
    heater list: Ref | Description | variant cell (12V/24V, ø, mm, amp, NPT) | Part Number | bullet model columns (header drawn, not
    text -> applicability not stored). Pass A pymupdf text lines, pass B pdfplumber words (number = longest numeric-shaped token
    suffix, description / variant split by the gap). Numbers in Eberspächer's dotted form per Larry's decision, printed form in the
    description; "*" -> "(optional feature)"; "• short harness" -> "Main harness: short harness"; 2a (blank description under 2)
    takes item 2's description. 20 1280 09 01 03 is printed as "Grommet" and as "Fuel screen" -> not loaded. Drop d12955f4a890693e:
    102 rows, 84 new, 18 existing (descriptions agree, e.g. 25.2069.06.0001 combustion chamber seal), confirming the dotted rule.
  - `scripts/aftermarket_pdf/truma_grove_catalogue.py` — Truma Spare Parts catalogue printed by Grove Products (Pos | Truma No. |
    Grove No. | Description | Qty, two tables per page): first distributor-catalogue load under Larry's decision. New source
    `truma-grove-spare-parts-catalogue-drive-supplied` (publisher Truma, metadata kind distributor_catalogue, printed_publisher Grove
    Products). Truma numbers only; Grove numbers never parts; "Includes items below" dropped; rows whose description wraps or is
    missing are held; header qualifiers ("from 06/14", "TEB 3 / TEN 3") are section labels; numbers printed with two descriptions
    not loaded (49 over the two splits, mostly language / abbreviation variants such as "O-ring 52x5" vs "O-ring 52 x 5 mm, VMQ").
    Drops c25d4160f1c53a69 (433 new, 103 existing) and 1c2893016b400186 (493 new, 101 existing). Candidate for the other Grove-numbered
    lists still `new` (Thetford_General_spares.pdf: Thetford Part No. | Grove Part No.; the AL-KO list with a Grove No. column).
  - Tests: `tests/test_espar_truma_grove_readers.py`. Drop key id `drops-2026-11-27-intake-ngvl`.
- 27 Nov ~13:19 run (session_017XuwiMDDEbyg6XoszojTZX): no new PDFs in Drive since 12:23. Michael's folder: 2 new Lane B CSVs (dealer-hosted
  catalogue extracts at pictures.dealer.com): p455 SeaLand covered (fits_model rows; Dometic 385311641 / 385310063 already parts), p315
  Suburban held (cited web PDF could not be opened from the scheduled run: the web fetch needs a permission nobody can grant unattended;
  the line names no maker for #110-504 / #110-509 and no brand for #3200289, and joins two numbers with "or"). Replies 03 (Michael's
  Claude) and 04 (Michael's ChatGPT) written; both of their messages were numbered 02. 8 distributor files: 2 done with drops, 2 done
  nothing new, 4 re-held (one of them partly published). 425 new parts (Thetford 152, AL-KO 230, Coleman-Mach 43), 177 existing Thetford
  parts evidenced; no cross-maker links.
  - Trailer Enterprises sections (Section C brakes "Dexter and Kodiak", axle components, Section D suspensions) re-read under the
    distributor decision: no maker-to-maker statement anywhere. The "Electric / Hydraulic Brake Parts Replacement Chart" (Redline Trailer
    Repair Parts logo) lists service parts per brake model column (fitment); the p39 seal table pairs RG06-0x0 / seal / "INTERCHANGE#"
    numbers with no maker printed for any of them; Part No. cells are not labelled with a maker per row -> held.
  - `scripts/aftermarket_pdf/thetford_grove_spares.py` — Thetford Spare Parts printed by Grove (Thetford_General_spares.pdf, 104 pp):
    "No. | Description | Thetford Part No. Grove Part No." with the Grove number BOLD in the same cell (dropped by font). The number area
    is two sub-columns; cells can span several item rows (kits such as "Signal white 92403111" over items 1-4, production-date blocks
    "Before 01/07/05 ... 623064 / 628450 / 633570", colour lists over a whole sub-assembly). Baselines alone are NOT enough: "Ruby red
    92405130" sits exactly on the "O-ring" baseline inside a 10-row kit cell. The reader takes each number's smallest filled cell
    rectangle (pymupdf get_drawings / pdfplumber rects) and only loads numbers whose cell is one row high; multi-row cells -> "unread".
    Drop e83e283aedc10388 (source `thetford-grove-spare-parts-catalogue-drive-supplied`): 329 numbers, 152 new, 177 existing. 335 numbers
    not loaded (multi-row cells, wraps, 32 printed with two descriptions) -> file re-held for a multi-row-cell extension.
  - `scripts/aftermarket_pdf/alko_grove_spares.py` — "AL-KO Spare Parts" printed by Grove (14 pp, Pos | AL-KO No. | Grove No. |
    Description): manufacturer `AL-KO` added (as printed). Rows compared on number + description (pdfplumber splits the big heading words
    differently; heading from pass A). Held: wraps, numbered lines under a "Pos | heading" line ("10 | Brake drum / Complete with bearing"
    over 623748 ...), qualifier-only descriptions ("-7/95"). Drop 4ec4873c0c803170 (source `alko-grove-spare-parts-list-drive-supplied`):
    230 new AL-KO parts.
  - AL-KO Australia Dexter sheets: all 7 Dexter numbers already parts -> done.
  - `scripts/aftermarket_pdf/coleman_so_quick_reference.py` — Coleman section Q of a distributor's "PARTS QUICK REFERENCE" (printed
    pp 552-567): only "(S/O <number>)" in the description column of pages headed COLEMAN(-MACH) AIR CONDITIONER PARTS (the special-order
    number is Coleman-Mach's own; ORDER # is the distributor's stock number); description from the same line or the line directly above,
    section heading in brackets. Drop 1d36332bfe44360d (source `coleman-mach-so-quick-reference-distributor-drive-supplied`): 43 new
    Coleman-Mach parts; ~36 numbers held (multi-line cells, variant lines, 6 printed with two descriptions, X-Reference pp 13-15 not read).
  - Drop key id `drops-2026-11-27-intake-mddeb`. Tests: `tests/test_grove_thetford_alko_readers.py`.
- 27 Nov ~13:49 run (session_017XuwiMmBbRj9SFy48EqsnL): no new PDFs or CSVs in Drive since 12:57 (only message docs 03-05 and the
  Will thread doc 26, left to the :19 run). 11 files claimed, all re-held with what was publishable published: 981 new parts
  (Thule 517, Truma 183, Thetford 118, Fiamma 109, Dexter 54), 900 existing parts evidenced; no cross-maker links.
  - `scripts/aftermarket_pdf/dexter_v124_tables.py` — Dexter "Trailer Parts & Accessories" V1-24 branch catalogue: PART # | REF # |
    DESCRIPTION [| attribute columns] tables under 14 pt coloured headings; only headings starting GENUINE DEXTER / DEXTER are read
    (KODIAK AND DEXTER, FORTRESS ... FOR DEXTER HUBS are not). Pass A find_tables cells (heading line taken into the table and merged
    "REF # DESCRIPTION" header cells handled), pass B pdfplumber word cells by header centres. Tables with two PART # columns (left /
    right hand brakes) and "*" numbers are not read. Source `dexter-v124-branch-catalogue-drive-supplied` (publisher Dexter).
    **Dexter short-form numbers held**: the catalogue prints 8-213-51, 8-219-9UC3, 10-19 ...; the DB stores Dexter numbers padded
    (008-213-51 exists) and has no short forms, so 71 short-form numbers in split pp 130-193 wait for Larry (normalise to the padded
    form, or wait for the SKU harmonisation spreadsheet). Loaded only K08-...-1G kits, D008-..., K71-..., 84656/42655UC1-style numbers.
  - `scripts/aftermarket_pdf/movera_hersteller_tables.py` — Movera Caravan Workshop and Spare Parts Catalogue 2017-2018 (German):
    maker from the 22 pt page title ("THULE: ..."), mapped only to a manufacturer of exactly that name; Pos. | Movera-Nr. |
    Hersteller-Nr. | Artikel-Bezeichnung; "auf Anfrage" in the Movera-Nr. column still reads the maker number; rotated side labels
    and 10-14 pt drawing callouts dropped (table text is 8.5 pt); bold full-width rows are sub-headings ("(Fortsetzung)" dropped).
    Sources `movera-workshop-catalogue-2017-<maker>-drive-supplied` (kind distributor_catalogue, printed_publisher Movera GmbH).
  - **The supplied lane takes one publisher per document** (`supplied_drops_v1.name` must equal the document hash prefix and
    `supplied_documents_v1` has one publisher), so a multi-maker distributor catalogue can load only one maker per split. Movera: the
    main maker of each split was loaded; ~920 numbers of the other makers (Truma 262, Fiamma 306, Thetford 96, AL-KO 92, REMIS 65,
    Dometic 36, Thule 117) wait for per-row maker support. The same limit blocks Berger, MF Campingwelt, Coast to Coast, Vecam, Euro
    Accessoires and the other-brand tables of the Dexter V1-24 catalogue.
  - Movera prints Thetford 7101 / 7102 without the leading zero Thetford uses (07101 Lip Seal, 07102 Vent seal): created as printed,
    flagged for review in the register row; not merged.
  - Keystone advisory 21-214 (approved replacement regulators for the recalled Winn-Tec 6020) and the Powrtouch NZ retailer list
    ("Vendor Code" column, no maker named) stay held for Larry. Tests: `tests/test_dexter_v124_movera_readers.py`.
- 27 Nov ~14:19 run (session_017XuwiKsq9J2HCbJkKwUc82): no new PDFs or CSVs in Drive since 12:57. Michael's folder: messages 05 (Michael's
  ChatGPT: source-only boundary set by Michael, one new JLS Distribution Thule/Omnistor web lead) and 06 (Michael's Claude: no new CSVs,
  asks which Lane B maker PDFs we want) answered with 07 and 08; no new files, so no Results rows. 12 files: 7 done, 5 held. 122 new parts
  (Coleman-Mach 18, Fiamma 54, Thule 20, Truma 30), ~520 existing parts evidenced; no cross-maker links (distributor catalogues only).
  - Dexter V1-24 splits pp 388-451 and 452-516: no GENUINE DEXTER / DEXTER headings (dexter_v124_tables.py: 0 rows). pp 388-451 done (no
    table names the maker of its PART # numbers); pp 452-516 held only for the Dutton-Lainson / Fulton T-winch tables (BRAND column per
    row, ~32 rows) = per-row maker support.
  - Coleman section Q "X-Reference" pages 13-15: "X-Reference" is just the section-tab list in the page header. The pages are 9000-series
    ceiling-assembly parts tables; `coleman_so_quick_reference.py` now reads them (`read_ceiling_page`: Coleman number = MFG # cell or the
    number after "S/O" in ORDER #; description from the number's row band +-3.5 pt because page 566 prints descriptions ~2 pt below the
    numbers). Supplement drop 1d36332bfe44360d (n 201+): 18 new Coleman-Mach parts. Held: 9330-3551 (two descriptions), "Vane (White"
    misprint, 9330-305 / 9330-306 (p13 short prints beside 9330-3051 / 9330-3061 with the same description).
  - RV Designer "dealer hardware" excerpt re-checked: JR Products (~105 five-digit numbers, none in the DB) and RV Designer (96 of its
    numbers already in the DB) under block headings in 2-3 columns -> held for a heading-geometry reader + per-row maker support.
  - `scripts/aftermarket_pdf/berger_hersteller_tables.py` — Fritz Berger Ersatzteil-Katalog 2017-2018 (German, 8 splits): "Pos. |
    Berger-Nr. | <MAKER>-Nr. | Artikel-Bezeichnung" (maker named in the column header). Pass A: each table row is ONE pymupdf span,
    cells split on runs of 2+ spaces; wrapped descriptions are their own span padded with leading whitespace. Pass B: pdfplumber words by
    the header columns. Lessons: (1) pymupdf and pdfplumber coordinates differ on some pages (crop box), so each pass uses its own
    geometry; (2) a table in the other page column bounds a table only if it started above the line and lies > 120 pt to the right;
    (3) "bitte Pos. 3 mitbestellen" inside a description is not a new header (a header needs "Pos." AND "Berger-Nr."); (4) headings are
    12-16 pt bold lines grouped by BASELINE (" PRO - " spans are taller) and only the leftmost run without a > 30 pt gap: drawing callout
    letters (S, E, T, H) are big bold too and sit on heading baselines; a heading needs three letters in a row; Berger's own "(Nr. 116100)"
    stock number is dropped from it. The first load of pp 035-046 / 047-069 had 74 descriptions with callout letters in the bracket:
    corrected in place (rows, evidence quotes, 20 part names with `name_correction` audit events). `--hold-unique-shapes` (used for Truma)
    holds a number whose digit/letter shape is unique in the split ("4000-01100"). Berger prints the same Fiamma number with different
    words across tables (98655-434 "Endanschlagvorrichtung links" and "... rechts"): such numbers are never loaded.
    Sources `berger-ersatzteil-katalog-2017-{fiamma,thule,truma}-drive-supplied` (kind distributor_catalogue, printed_publisher Fritz
    Berger). Loaded the main maker per split: Fiamma pp 035-046 / 047-069 / 070-092, Thule pp 093-138, Truma pp 139-161 / 162-184.
    Held: pp 001-023 (CADAC 38 rows, ALKO 35, Dometic 30, Comet 19, Crespo 16, Alu Line 11, Alde 10, Cobb 10: per-row maker support) and
    pp 024-034 (Dometic). **Dometic number-format question for Larry**: Berger prints Dometic (ex-Electrolux) numbers as "2412137-00/8";
    the DB stores Dometic's own lists as the 10 digits 2412137008 (9 of the 74 printed numbers already exist that way). Loading as printed
    would duplicate parts; the window-pane table "Berger | Dometic Nr. | Bestellmaß mm | Glasmaß mm | Bezeichnung" is a second layout.
    Drop key id `drops-2026-11-27-intake-ksq9`. Tests: `tests/test_berger_coleman_ceiling_readers.py`.
