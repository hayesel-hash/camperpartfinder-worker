# Drive intake (supplied catalogues in Larry's Google Drive)

Larry's ChatGPT drops maker PDFs into Google Drive. Every file gets one row in
`rv_private.drive_intake_v1`, which is how ClaudeL sessions (and the scheduled intake run)
avoid doing the same file twice.

Folders watched (Drive folder ids):
- `1VPv8yDVJFuSmUaHzpwuXBYB1inByelsy` CamperPartMatch — 20 Aftermarket Parts Catalogues for Claude
- `1Vd4kdiZQOrn6A2V1AmqOY9d2XIbX4mRu` Manufacturer original catalogues — batch 1 (Airstream books:
  handled by the supplied-documents lane, `scripts/supplied/`; register them as lane `oem_parts_book`)

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
