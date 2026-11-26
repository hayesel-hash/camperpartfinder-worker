-- Supplied reader v1: Airstream parts books that are too large for the Drive connector are
-- fetched by the GitHub workflow supplied-reader.yml straight from the download links Airstream
-- itself publishes (its document list marks them "private": false; files are served from its
-- CMS asset host a-us.storyblok.com). The worker runs the same two-pass extraction and gates as
-- the Drive lane (scripts/supplied/) and STAGES the result through rv-supplied-gateway; the
-- database registers the document, loads rows and publishes only when every gate passed.

insert into rv_private.sources(id, publisher, url, access_state, metadata)
values ('airstream-parts-books-direct', 'Airstream',
        'https://www.airstream.com/support-tools/owner-resources/owners-manuals-parts-books/?s_manuals=parts',
        'PUBLIC_FACTS',
        jsonb_build_object('kind','manufacturer',
          'scope','Airstream official parts books, fetched from the public download links in Airstream''s own document list (asset host a-us.storyblok.com); identities only',
          'approvedBy','Larry, 26 Nov 2026 (process all Airstream catalogues)','bulkEnabled',false))
on conflict (id) do nothing;

create table if not exists rv_private.supplied_queue_v1 (
  url        text primary key check (url ~ '^https://a-us\.storyblok\.com/f/[0-9]+/x/[0-9a-f]+/[a-z0-9-]+\.pdf$'),
  title      text not null,
  source_id  text not null references rv_private.sources(id),
  publisher  text not null references rv_private.manufacturers(name),
  status     text not null default 'pending' check (status in ('pending','leased','staged','failed','skipped')),
  lease      uuid,
  leased_at  timestamptz,
  attempts   integer not null default 0,
  doc_sha256 text,
  result     jsonb,
  updated_at timestamptz not null default now()
);
revoke all on rv_private.supplied_queue_v1 from public, anon, authenticated;

create or replace function public.rv_supplied_claim(n integer)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog' as $fn$
declare tok uuid := gen_random_uuid(); out jsonb;
begin
  update rv_private.supplied_queue_v1 set status = 'pending'
   where status = 'leased' and leased_at < now() - interval '40 minutes';
  with c as (
    select url from rv_private.supplied_queue_v1
     where status = 'pending' and attempts < 3
     order by title limit greatest(1, least(n, 10)) for update skip locked)
  update rv_private.supplied_queue_v1 q set status = 'leased', lease = tok, leased_at = now(),
         attempts = attempts + 1, updated_at = now()
    from c where q.url = c.url;
  select coalesce(jsonb_agg(jsonb_build_object('url', url, 'title', title, 'lease', lease)), '[]'::jsonb) into out
    from rv_private.supplied_queue_v1 where lease = tok;
  return out;
end;
$fn$;

create or replace function public.rv_supplied_stage(url text, lease uuid, doc jsonb)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog' as $fn$
declare q record; loaded integer; pub jsonb; sha text := doc->>'doc';
begin
  select * into q from rv_private.supplied_queue_v1 s where s.url = rv_supplied_stage.url and s.lease = rv_supplied_stage.lease and s.status = 'leased';
  if not found then return '{"error":"lease not held"}'::jsonb; end if;
  if sha !~ '^[0-9a-f]{64}$' or coalesce(doc->>'rows','') = '' then
    update rv_private.supplied_queue_v1 s set status = 'failed', result = '{"error":"malformed document"}', updated_at = now() where s.url = q.url;
    return '{"error":"malformed document"}'::jsonb;
  end if;
  if exists (select 1 from rv_private.supplied_documents_v1 where sha256 = sha) then
    update rv_private.supplied_queue_v1 s set status = 'skipped', doc_sha256 = sha, result = '{"skipped":"already loaded"}', updated_at = now() where s.url = q.url;
    return '{"skipped":"already loaded"}'::jsonb;
  end if;
  insert into rv_private.supplied_documents_v1(sha256, source_id, publisher, title, pages, supplied_by, obtained_via,
                                                extraction, verification, review_state)
  values (sha, q.source_id, q.publisher, doc->>'title', (doc->>'pages')::int, 'Airstream (published download link)',
          'supplied-reader worker, GitHub Actions, from '||q.url||', 26 Nov 2026 onwards',
          doc->>'extraction', doc->>'verification',
          case when doc->>'review_state' = 'reviewed' then 'reviewed' else 'unreviewed' end);
  loaded := rv_private.load_supplied_rows_v1(sha, doc->'sections', doc->>'rows');
  pub := case when doc->>'review_state' = 'reviewed' then rv_private.publish_supplied_document_v1(sha)
              else jsonb_build_object('held', doc->'gates') end;
  update rv_private.supplied_queue_v1 s set status = 'staged', doc_sha256 = sha, updated_at = now(),
         result = jsonb_build_object('rows_loaded', loaded) || pub where s.url = q.url;
  return jsonb_build_object('rows_loaded', loaded) || pub;
end;
$fn$;

create or replace function public.rv_supplied_fail(url text, lease uuid, reason text)
returns void language sql security definer set search_path to 'pg_catalog' as $fn$
  update rv_private.supplied_queue_v1 s set status = case when s.attempts >= 3 then 'failed' else 'pending' end,
         result = jsonb_build_object('error', left(reason, 300)), updated_at = now()
   where s.url = rv_supplied_fail.url and s.lease = rv_supplied_fail.lease;
$fn$;

revoke all on function public.rv_supplied_claim(integer) from public, anon, authenticated;
revoke all on function public.rv_supplied_stage(text, uuid, jsonb) from public, anon, authenticated;
revoke all on function public.rv_supplied_fail(text, uuid, text) from public, anon, authenticated;
grant execute on function public.rv_supplied_claim(integer) to service_role;
grant execute on function public.rv_supplied_stage(text, uuid, jsonb) to service_role;
grant execute on function public.rv_supplied_fail(text, uuid, text) to service_role;
