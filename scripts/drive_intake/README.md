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
- 27 Nov ~08:20 run (session_017XuwiMgNdUE7HhicEwjo7T): no new PDFs in Drive since 06:55. 23 files: Truma 5 (3 done, 2 held),
  Eberspächer 5 (3 done, 2 held), Dometic SeaLand 4 (partly published, held for rotated sheets), Girard / Girard Lippert 7 done.
  884 new parts (Truma 64, Eberspächer 164, SeaLand 463, Lippert/Girard 189), ~800 existing parts evidenced, 4 Truma
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
