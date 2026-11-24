-- Catalogue archive v1: keep every catalogue we read, plus the text of every page.
-- Additive only. Does not change master_catalogues, parts, evidence or any publication path.
--
-- * catalogue_archive_v1   one row per master catalogue: archive status, lease, last check
-- * catalogue_editions_v1  every distinct edition (SHA-256) of a catalogue we have stored
-- * catalogue_page_text_v1 the text of every page of every stored edition
--
-- A catalogue whose live file no longer matches the edition its parts were read from is
-- marked edition_changed (a new edition) rather than silently overwritten. Archived rows
-- are re-checked every 30 days with a conditional request, which is how new editions are found.
--
-- Rollback: unschedule nothing (workers are GitHub-side); drop the three functions and three
-- tables below. No existing data depends on them.

create table if not exists rv_private.catalogue_archive_v1 (
  catalogue_id       text primary key references rv_private.master_catalogues(id),
  status             text not null default 'pending'
                     check (status in ('pending','archived','edition_changed','text_only','unavailable','failed')),
  expected_sha256    text,             -- edition the parts were read from
  archived_sha256    text,             -- edition we most recently stored
  storage_path       text,
  bytes              bigint,
  pages              integer,
  pages_with_text    integer,
  pages_needing_ocr  integer,
  http_etag          text,
  http_last_modified text,
  attempts           integer not null default 0,
  lease              uuid,
  lease_until        timestamptz,
  last_error         text,
  archived_at        timestamptz,
  last_checked_at    timestamptz,
  updated_at         timestamptz not null default now()
);

create table if not exists rv_private.catalogue_editions_v1 (
  catalogue_id   text not null references rv_private.master_catalogues(id),
  sha256         text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  bytes          bigint,
  pages          integer,
  storage_path   text,
  pdf_stored     boolean not null default false,
  first_seen_at  timestamptz not null default now(),
  primary key (catalogue_id, sha256)
);

create table if not exists rv_private.catalogue_page_text_v1 (
  document_sha256 text not null check (document_sha256 ~ '^[0-9a-f]{64}$'),
  page            integer not null check (page >= 1),
  text            text not null,
  chars           integer not null,
  text_sha256     text not null,       -- sha256 of PyMuPDF get_text("text"), same as evidence page_text_sha256
  method          text not null,
  extracted_at    timestamptz not null default now(),
  primary key (document_sha256, page)
);

alter table rv_private.catalogue_archive_v1   enable row level security;
alter table rv_private.catalogue_editions_v1  enable row level security;
alter table rv_private.catalogue_page_text_v1 enable row level security;

create index if not exists catalogue_archive_v1_claim_idx
  on rv_private.catalogue_archive_v1 (status, updated_at);

-- Claim the next catalogue to archive (or re-check). Seeds rows for any newly ready catalogue.
create or replace function public.rv_archive_claim(worker text)
returns jsonb language plpgsql security definer set search_path = pg_catalog as $$
declare
  r record;
  t uuid := gen_random_uuid();
begin
  insert into rv_private.catalogue_archive_v1 (catalogue_id, expected_sha256, pages)
  select m.id, m.sha256, m.pages
  from rv_private.master_catalogues m
  where m.state = 'ready' and m.sha256 is not null
  on conflict (catalogue_id) do nothing;

  select a.catalogue_id, a.status, a.expected_sha256, a.pages, a.http_etag, a.http_last_modified,
         m.url, m.publisher
    into r
  from rv_private.catalogue_archive_v1 a
  join rv_private.master_catalogues m on m.id = a.catalogue_id
  where (a.lease_until is null or a.lease_until < now())
    and (   a.status = 'pending'
         or (a.status = 'failed' and a.attempts < 4 and a.updated_at < now() - interval '1 hour')
         or (a.status in ('archived','edition_changed','text_only')
             and a.last_checked_at < now() - interval '30 days'))
  order by (a.status = 'pending') desc, random()
  limit 1
  for update of a skip locked;

  if not found then
    return null;
  end if;

  update rv_private.catalogue_archive_v1
     set lease = t, lease_until = now() + interval '25 minutes',
         attempts = attempts + 1, updated_at = now()
   where catalogue_id = r.catalogue_id;

  return jsonb_build_object(
    'id', r.catalogue_id, 'url', r.url, 'publisher', r.publisher,
    'sha256', r.expected_sha256, 'pages', r.pages, 'lease', t,
    'mode', case when r.status in ('pending','failed') then 'archive' else 'recheck' end,
    'etag', r.http_etag, 'last_modified', r.http_last_modified, 'worker', worker);
end $$;

-- Register the edition the worker actually downloaded and say what still needs storing.
create or replace function public.rv_archive_begin(cid text, tok uuid, doc_sha256 text, doc_bytes bigint,
                                                   doc_pages integer, etag text, last_modified text)
returns jsonb language plpgsql security definer set search_path = pg_catalog as $$
declare
  a record;
  slug text;
  path text;
  have_pdf boolean;
  have_pages integer;
begin
  select * into a from rv_private.catalogue_archive_v1
   where catalogue_id = cid and lease = tok and lease_until > now() for update;
  if not found then
    return jsonb_build_object('error', 'lease');
  end if;
  if doc_sha256 !~ '^[0-9a-f]{64}$' or doc_pages is null or doc_pages < 1 or doc_pages > 20000 then
    return jsonb_build_object('error', 'invalid');
  end if;

  select lower(regexp_replace(coalesce(m.publisher, 'unknown'), '[^A-Za-z0-9]+', '-', 'g'))
    into slug from rv_private.master_catalogues m where m.id = cid;
  path := trim(both '-' from slug) || '/' || cid || '/' || doc_sha256 || '.pdf';

  insert into rv_private.catalogue_editions_v1 as ed (catalogue_id, sha256, bytes, pages, storage_path)
  values (cid, doc_sha256, doc_bytes, doc_pages, path)
  on conflict on constraint catalogue_editions_v1_pkey do nothing;

  select exists (select 1 from storage.objects o
                  where o.bucket_id = 'rv-original-catalogues' and o.name = path
                    and (o.metadata->>'size')::bigint = doc_bytes)
    into have_pdf;
  select count(*) into have_pages from rv_private.catalogue_page_text_v1 t where t.document_sha256 = doc_sha256;

  update rv_private.catalogue_archive_v1
     set http_etag = etag, http_last_modified = last_modified, lease_until = now() + interval '25 minutes',
         updated_at = now()
   where catalogue_id = cid;

  return jsonb_build_object('path', path, 'need_upload', not have_pdf,
                            'need_pages', have_pages < doc_pages, 'pages_stored', have_pages,
                            'same_edition', doc_sha256 = a.expected_sha256);
end $$;

-- Store a batch of page texts for one edition (idempotent).
create or replace function public.rv_archive_pages(cid text, tok uuid, doc_sha256 text, page_rows jsonb)
returns integer language plpgsql security definer set search_path = pg_catalog as $$
declare
  n integer;
  maxp integer;
begin
  if not exists (select 1 from rv_private.catalogue_archive_v1
                  where catalogue_id = cid and lease = tok and lease_until > now()) then
    return -1;
  end if;
  select e.pages into maxp from rv_private.catalogue_editions_v1 e
   where e.catalogue_id = cid and e.sha256 = doc_sha256;
  if maxp is null or jsonb_typeof(page_rows) <> 'array' or jsonb_array_length(page_rows) > 500 then
    return -1;
  end if;

  insert into rv_private.catalogue_page_text_v1 (document_sha256, page, text, chars, text_sha256, method)
  select doc_sha256, x.page, x.text, length(x.text), x.text_sha256, x.method
  from jsonb_to_recordset(page_rows) as x(page integer, text text, text_sha256 text, method text)
  where x.page between 1 and maxp
    and x.text is not null
    and x.text_sha256 ~ '^[0-9a-f]{64}$'
    and x.method in ('pymupdf-text-v1')
  on conflict on constraint catalogue_page_text_v1_pkey do nothing;
  get diagnostics n = row_count;

  update rv_private.catalogue_archive_v1
     set lease_until = now() + interval '25 minutes', updated_at = now()
   where catalogue_id = cid;
  return n;
end $$;

-- Close the claim. 'archived' is only accepted if the PDF is really in storage at the right size.
create or replace function public.rv_archive_finish(cid text, tok uuid, outcome text, details jsonb)
returns jsonb language plpgsql security definer set search_path = pg_catalog as $$
declare
  a record;
  e record;
  sha text := details->>'sha256';
  stored integer;
  with_text integer;
  ocr integer;
  pdf_ok boolean := false;
  new_status text;
begin
  select * into a from rv_private.catalogue_archive_v1
   where catalogue_id = cid and lease = tok for update;
  if not found then
    return jsonb_build_object('error', 'lease');
  end if;

  if outcome = 'unchanged' then
    update rv_private.catalogue_archive_v1
       set last_checked_at = now(), lease = null, lease_until = null, last_error = null, updated_at = now()
     where catalogue_id = cid;
    return jsonb_build_object('status', a.status);
  end if;

  if outcome in ('archived','text_only') then
    select * into e from rv_private.catalogue_editions_v1 where catalogue_id = cid and sha256 = sha;
    if not found then
      outcome := 'failed';
      details := jsonb_build_object('error', 'edition not registered');
    else
      select count(*), count(*) filter (where chars >= 20), count(*) filter (where chars < 20)
        into stored, with_text, ocr
      from rv_private.catalogue_page_text_v1 where document_sha256 = sha;
      select exists (select 1 from storage.objects o
                      where o.bucket_id = 'rv-original-catalogues' and o.name = e.storage_path
                        and (o.metadata->>'size')::bigint = e.bytes)
        into pdf_ok;
      if stored < e.pages then
        outcome := 'failed';
        details := jsonb_build_object('error', format('page text incomplete: %s of %s', stored, e.pages));
      elsif outcome = 'archived' and not pdf_ok then
        outcome := 'failed';
        details := jsonb_build_object('error', 'PDF not found in storage at expected size');
      end if;
    end if;
  end if;

  if outcome in ('archived','text_only') then
    update rv_private.catalogue_editions_v1 set pdf_stored = pdf_ok where catalogue_id = cid and sha256 = sha;
    new_status := case when sha is distinct from a.expected_sha256 then 'edition_changed'
                       when outcome = 'text_only' then 'text_only'
                       else 'archived' end;
    update rv_private.catalogue_archive_v1
       set status = new_status, archived_sha256 = sha, storage_path = case when pdf_ok then e.storage_path end,
           bytes = e.bytes, pages = e.pages, pages_with_text = with_text, pages_needing_ocr = ocr,
           archived_at = now(), last_checked_at = now(), last_error = left(details->>'note', 300),
           lease = null, lease_until = null, updated_at = now()
     where catalogue_id = cid;
    return jsonb_build_object('status', new_status, 'pages_with_text', with_text, 'pages_needing_ocr', ocr);
  end if;

  if outcome not in ('unavailable','failed') then
    outcome := 'failed';
  end if;
  update rv_private.catalogue_archive_v1
     set status = case when a.status in ('archived','edition_changed','text_only') and outcome = 'failed'
                       then a.status else outcome end,
         last_error = left(coalesce(details->>'error', 'unknown'), 300),
         last_checked_at = case when outcome = 'unavailable' then now() else a.last_checked_at end,
         lease = null, lease_until = null, updated_at = now()
   where catalogue_id = cid;
  return jsonb_build_object('status', outcome);
end $$;

revoke all on function public.rv_archive_claim(text) from public, anon, authenticated;
revoke all on function public.rv_archive_begin(text, uuid, text, bigint, integer, text, text) from public, anon, authenticated;
revoke all on function public.rv_archive_pages(text, uuid, text, jsonb) from public, anon, authenticated;
revoke all on function public.rv_archive_finish(text, uuid, text, jsonb) from public, anon, authenticated;
grant execute on function public.rv_archive_claim(text) to service_role;
grant execute on function public.rv_archive_begin(text, uuid, text, bigint, integer, text, text) to service_role;
grant execute on function public.rv_archive_pages(text, uuid, text, jsonb) to service_role;
grant execute on function public.rv_archive_finish(text, uuid, text, jsonb) to service_role;

insert into rv_private.camper_input_change_log_v1 (actor, change_category, reason, details, rollback_instructions)
values ('Claude', 'catalogue_archive',
        'Keep every catalogue PDF and the text of every page so facts can be re-verified and new editions detected.',
        jsonb_build_object('tables', jsonb_build_array('rv_private.catalogue_archive_v1','rv_private.catalogue_editions_v1','rv_private.catalogue_page_text_v1'),
                           'bucket', 'rv-original-catalogues',
                           'functions', jsonb_build_array('rv_archive_claim','rv_archive_begin','rv_archive_pages','rv_archive_finish'),
                           'gateway', 'rv-catalogue-archive-gateway',
                           'workflow', '.github/workflows/rv-catalogue-archive.yml'),
        'Disable the rv-catalogue-archive.yml workflow; drop the four rv_archive_* functions and the three catalogue_*_v1 tables. Nothing else depends on them.');
