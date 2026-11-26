# Supplied-documents tools

Offline tools for maker documents that are supplied by hand (e.g. Airstream parts books,
whose site refuses automated downloads). Nothing here contains maker content.

- `airstream_book.py`: two independent extraction passes (text lines, word positions).
- `batch_book.py <pdf> <drive_id> <title> <out_dir>`: writes one JSON per book with rows,
  sections and the automated gates (passes agree, text layer, row count, no unexplained
  number-like lines). Books failing a gate are marked `unreviewed` and held.
- `make_drops.py <dir>`: encrypts each JSON as base64(IV + AES-256-CBC) for the
  `supplied-drops` branch; the key lives only in `rv_private.supplied_drop_keys_v1`.

Loading: register names in `rv_private.supplied_drops_v1`, then
`select rv_private.fetch_supplied_drops_v1();` and `select rv_private.ingest_supplied_drops_v1();`.
