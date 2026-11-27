"""Build the SQL that stages aftermarket rows (Drive intake, aftermarket_xref lane).

    from stage_sql import source_sql, page_sql, assertions_sql

Each helper returns one SQL statement (idempotent: on conflict do nothing) for
rv_private.sources, rv_private.aftermarket_source_pages_v1 and
rv_private.aftermarket_assertions_v1.  `page_sha256` is the SHA-256 of the whole PDF
(the evidence keeps it as document_version together with the PDF page in qualifiers.page).
Nothing here reads maker content; readers produce the rows.
"""
from __future__ import annotations

import json


def q(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def source_sql(source_id: str, publisher: str, url: str, scope: str, supplied_via: str,
               approved_by: str = "Larry, 26-27 Nov 2026 (Drive intake brief)") -> str:
    meta = {"kind": "aftermarket_manufacturer_pdf", "scope": scope, "format": "pdf",
            "approvedBy": approved_by, "supplied_via": supplied_via}
    return ("insert into rv_private.sources(id, publisher, url, access_state, metadata) values "
            f"({q(source_id)}, {q(publisher)}, {q(url)}, 'PUBLIC_FACTS', {q(meta)}) on conflict (id) do nothing;")


def page_sql(source_id: str, sha256: str, url: str, parser: str, review_note: str) -> str:
    return ("insert into rv_private.aftermarket_source_pages_v1(source_id, sha256, url, fetched_at, html, parser, "
            "review_state, reviewed_by, reviewed_at, review_note, staged_at) values "
            f"({q(source_id)}, {q(sha256)}, {q(url)}, now(), '', {q(parser)}, 'reviewed', 'ClaudeL', now(), "
            f"{q(review_note)}, now()) on conflict do nothing;")


COLS = ("source_id", "page_sha256", "table_key", "row_key", "relation", "aftermarket_maker", "aftermarket_number",
        "aftermarket_label", "oem_brand", "oem_brand_basis", "oem_number", "oem_model", "category", "qualifiers",
        "row_text", "status", "hold_reason")


def assertions_sql(rows: list[dict]) -> str:
    vals = []
    for r in rows:
        r = {"oem_brand_basis": "named_on_page", "status": "staged", "hold_reason": None, "oem_model": None, **r}
        vals.append("(" + ", ".join(q(r.get(c)) for c in COLS) + ")")
    # id is an identity column (generated always)
    return (f"insert into rv_private.aftermarket_assertions_v1({', '.join(COLS)}) values "
            + ",\n".join(vals) + " on conflict (source_id, page_sha256, row_key) do nothing;")
