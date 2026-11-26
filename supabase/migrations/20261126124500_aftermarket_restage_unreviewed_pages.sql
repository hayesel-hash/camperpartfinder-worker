-- Re-stage an UNREVIEWED aftermarket chart page when the reader version changes.
-- Needed because aftermarket-xref-v1 missed caveats that the live (Excel-exported)
-- pages keep inside table cells; v2 attaches them. Rows of a reviewed page, and any
-- row already published, are never replaced: a reviewed page is frozen, and a
-- changed page arrives with a new sha256 and goes through review again.
-- Rollback: re-apply the rv_aftermarket_stage definition from
-- 20261126113000_aftermarket_replacement_lane_v1.sql.
create or replace function public.rv_aftermarket_stage(page jsonb, page_rows jsonb)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog'
as $fn$
declare s record; existing record; n integer := 0; new_page boolean := false; restaged integer := 0;
begin
  select * into s from rv_private.sources
   where id = page->>'source_id' and url = page->>'url'
     and metadata->>'kind' = 'aftermarket_manufacturer'
     and access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK');
  if not found then return jsonb_build_object('error','source not approved'); end if;
  if coalesce(page->>'sha256','') !~ '^[0-9a-f]{64}$'
     or length(coalesce(page->>'html','')) = 0 or length(page->>'html') > 2000000
     or jsonb_typeof(page_rows) <> 'array' or jsonb_array_length(page_rows) > 3000 then
    return jsonb_build_object('error','invalid payload');
  end if;

  select * into existing from rv_private.aftermarket_source_pages_v1
   where source_id = s.id and sha256 = page->>'sha256'
   for update;
  if not found then
    insert into rv_private.aftermarket_source_pages_v1(source_id, sha256, url, fetched_at, html, parser)
    values (s.id, page->>'sha256', s.url, (page->>'fetched_at')::timestamptz, page->>'html', left(page->>'parser',60));
    new_page := true;
  elsif existing.review_state = 'unreviewed' and existing.parser is distinct from left(page->>'parser',60) then
    delete from rv_private.aftermarket_assertions_v1
     where source_id = s.id and page_sha256 = existing.sha256 and status <> 'published' and claim_id is null;
    get diagnostics restaged = row_count;
    update rv_private.aftermarket_source_pages_v1
       set parser = left(page->>'parser',60), fetched_at = (page->>'fetched_at')::timestamptz
     where source_id = s.id and sha256 = existing.sha256;
  end if;

  insert into rv_private.aftermarket_assertions_v1
    (source_id, page_sha256, table_key, row_key, relation, aftermarket_maker, aftermarket_number,
     aftermarket_label, oem_brand, oem_brand_basis, oem_number, oem_model, category, qualifiers,
     row_text, status, hold_reason)
  select s.id, page->>'sha256', left(x.table_key,40), left(x.row_key,60), x.relation, x.aftermarket_maker,
         left(x.aftermarket_number,80), left(x.aftermarket_label,80), left(x.oem_brand,60), x.oem_brand_basis,
         left(x.oem_number,80), left(x.oem_model,160), x.category, coalesce(x.qualifiers,'{}'),
         left(x.row_text,500), x.status, left(x.hold_reason,200)
  from jsonb_to_recordset(page_rows) as x(table_key text, row_key text, relation text, aftermarket_maker text,
       aftermarket_number text, aftermarket_label text, oem_brand text, oem_brand_basis text, oem_number text,
       oem_model text, category text, qualifiers jsonb, row_text text, status text, hold_reason text)
  where x.aftermarket_maker = s.publisher
    and x.status in ('staged','held','skipped')
    and x.relation in ('replaces','fits_model')
    and x.category in ('refrigeration','sanitation','water','windows_doors','heating','body_trim','external_equipment','running_gear')
    and length(coalesce(x.row_text,'')) > 0
  on conflict do nothing;
  get diagnostics n = row_count;
  return jsonb_build_object('page_new', new_page, 'restaged_rows_replaced', restaged, 'rows_inserted', n);
end;
$fn$;
revoke all on function public.rv_aftermarket_stage(jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.rv_aftermarket_stage(jsonb, jsonb) to service_role;
