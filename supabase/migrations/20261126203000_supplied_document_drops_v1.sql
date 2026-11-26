-- Supplied documents: row loaders.
-- 1. load_supplied_rows_v1: pipe-delimited rows (page|n|number|description|sectioncode)
--    for a registered, reviewed supplied document. Applied by hand on 26 Nov 2026;
--    recorded here so the repo matches the database.
-- 2. load_supplied_drop_v1: the same rows delivered as an encrypted "drop".
--    Rows extracted from a supplied document are encrypted (AES-256-CBC, a fresh
--    random key per drop) and published as base64 at a URL the database can
--    reach. The database fetches the file itself with pg_net (net.http_get), and
--    this function decrypts the response with the key passed in the call. Keys
--    are never committed. Not yet in use: where the drops live needs Larry's
--    say (26 Nov 2026); until then rows are loaded with load_supplied_rows_v1.
--    Plaintext is JSON: {"doc": <sha256 of the PDF>, "sections": {code: name}, "rows": "<pipe rows>"}.

create or replace function rv_private.load_supplied_rows_v1(doc text, sections jsonb, body text)
returns integer language plpgsql set search_path to 'pg_catalog' as $fn$
declare n integer;
begin
  insert into rv_private.supplied_document_rows_v1(document_sha256, page, n, number, description, section, status)
  select doc, split_part(l, '|', 1)::int, split_part(l, '|', 2)::int, split_part(l, '|', 3),
         split_part(l, '|', 4), coalesce(sections->>split_part(l, '|', 5), ''),
         case when split_part(l, '|', 4) ~* 'not for order' then 'held' else 'staged' end
  from regexp_split_to_table(body, E'\n') l
  where l ~ '^\d+\|\d+\|[A-Z0-9]'
  on conflict do nothing;
  get diagnostics n = row_count;
  return n;
end;
$fn$;
revoke all on function rv_private.load_supplied_rows_v1(text, jsonb, text) from public, anon, authenticated;

create or replace function rv_private.load_supplied_drop_v1(request_id bigint, key_hex text, iv_hex text)
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare body text; plain jsonb; doc text; loaded integer;
begin
  select r.content into body from net._http_response r where r.id = request_id and r.status_code = 200;
  if body is null then
    return jsonb_build_object('error', 'no 200 response yet for request '||request_id);
  end if;
  plain := convert_from(
             extensions.decrypt_iv(decode(body, 'base64'), decode(key_hex, 'hex'), decode(iv_hex, 'hex'), 'aes-cbc/pad:pkcs'),
             'UTF8')::jsonb;
  doc := plain->>'doc';
  if not exists (select 1 from rv_private.supplied_documents_v1 where sha256 = doc) then
    return jsonb_build_object('error', 'document not registered', 'doc', doc);
  end if;
  loaded := rv_private.load_supplied_rows_v1(doc, plain->'sections', plain->>'rows');
  return jsonb_build_object('doc', doc, 'rows_in_drop',
           (select count(*) from regexp_split_to_table(plain->>'rows', E'\n') l where l ~ '^\d+\|\d+\|[A-Z0-9]'),
           'rows_loaded', loaded);
end;
$fn$;
revoke all on function rv_private.load_supplied_drop_v1(bigint, text, text) from public, anon, authenticated;
