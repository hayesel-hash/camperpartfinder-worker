-- Supplied documents v1: official manufacturer documents that Larry obtains in a
-- browser (because the maker's server refuses automated downloads) and hands to
-- Claude. First: Airstream 2027 Trade Wind parts book (311 pp), obtained via the
-- "View" button on airstream.com, 26 Nov 2026.
-- Rows are extracted outside the factory (two independent passes that must agree,
-- plus page-image spot checks) and loaded here; publication records the document
-- SHA-256, PDF page and item position for every part.
-- Rollback: parts published here carry audit action automated_supplied_identity_publish
-- and identity_evidence reviewer 'supplied-document-v1'.

create table if not exists rv_private.supplied_documents_v1 (
  sha256       text primary key check (sha256 ~ '^[0-9a-f]{64}$'),
  source_id    text not null references rv_private.sources(id),
  publisher    text not null references rv_private.manufacturers(name),
  title        text not null,
  pages        integer not null check (pages > 0),
  supplied_by  text not null,
  obtained_via text not null,
  extraction   text not null,
  verification text not null,
  review_state text not null default 'unreviewed' check (review_state in ('unreviewed','reviewed','rejected')),
  created_at   timestamptz not null default now()
);

create table if not exists rv_private.supplied_document_rows_v1 (
  document_sha256 text not null references rv_private.supplied_documents_v1(sha256),
  page        integer not null check (page > 0),
  n           integer not null check (n > 0),
  number      text not null check (number ~ '^[A-Z0-9][A-Z0-9./-]{2,39}$'),
  description text not null check (length(btrim(description)) > 1),
  section     text not null default '',
  status      text not null default 'staged' check (status in ('staged','published','held')),
  part_id     uuid references rv_private.parts(id),
  primary key (document_sha256, page, n)
);

create or replace function rv_private.publish_supplied_document_v1(doc text)
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare d record; r record; mid uuid; pid uuid; ev uuid; made integer := 0; linked integer := 0;
begin
  select * into d from rv_private.supplied_documents_v1 where sha256 = doc and review_state = 'reviewed';
  if not found then return '{"error":"document not reviewed"}'::jsonb; end if;
  select id into mid from rv_private.manufacturers where name = d.publisher;
  for r in
    select distinct on (number) * from rv_private.supplied_document_rows_v1
     where document_sha256 = doc and status = 'staged'
     order by number, page, n
  loop
    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                    position, quote, sha256, hash_kind, observed_at)
    select d.source_id, 'p'||r.page||'n'||r.n, doc, s.url, r.page, r.page::text,
           'item '||r.n||' on page '||r.page, left(r.number||' | '||r.description, 300), doc, 'sha256-pdf', d.created_at
      from rv_private.sources s where s.id = d.source_id
    on conflict (source_id, source_record_key, document_version) do nothing
    returning id into ev;
    if ev is null then
      select id into ev from rv_private.evidence
       where source_id = d.source_id and source_record_key = 'p'||r.page||'n'||r.n and document_version = doc;
    end if;
    select id into pid from rv_private.parts where manufacturer_id = mid and exact_number = r.number and variant = '';
    if pid is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (mid, r.number, '', left(btrim(r.description), 200),
        case
          when lower(r.section||' '||r.description) ~ 'refrigerat|fridge|freezer' then 'refrigeration'
          when lower(r.description) ~ 'toilet|waste|black tank|grey tank|gray tank|macerator' then 'sanitation'
          when lower(r.description) ~ 'furnace|water heater|heater|aquahot|thermostat|heat duct|register' then 'heating'
          when lower(r.section||' '||r.description) ~ 'plumbing|water|pump|faucet|shower|valve|drain|pex|fitting' then 'water'
          when lower(r.section||' '||r.description) ~ 'chassis|axle|suspension|brake|hub|tire|wheel|hitch|coupler|jack|bearing|spring' then 'running_gear'
          when lower(r.description) ~ 'window|door|hatch|latch|lock|screen|stay' then 'windows_doors'
          when lower(r.section) ~ 'exterior shell|interior shell|furniture' or lower(r.description) ~ 'trim|molding|moulding|extrusion|panel|wrap|skin|sheet|decal|nameplate' then 'body_trim'
          else 'external_equipment' end,
        'published')
      returning id into pid;
      made := made + 1;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_supplied_identity_publish', pid, d.publisher||' '||d.title||' (supplied document); evidence '||ev::text);
    else
      linked := linked + 1;
    end if;
    insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (pid, ev, 'supplied-document-v1') on conflict do nothing;
    update rv_private.supplied_document_rows_v1 set status = 'published', part_id = pid
     where document_sha256 = doc and number = r.number;
  end loop;
  return jsonb_build_object('new_parts', made, 'existing_parts_evidenced', linked);
end;
$fn$;
revoke all on function rv_private.publish_supplied_document_v1(text) from public, anon, authenticated;

insert into rv_private.manufacturers(name) values ('Airstream') on conflict (name) do nothing;

insert into rv_private.sources(id, publisher, url, access_state, metadata)
values ('airstream-parts-books-supplied', 'Airstream',
        'https://www.airstream.com/support-tools/owner-resources/owners-manuals-parts-books/?s_manuals=parts',
        'PUBLIC_FACTS',
        jsonb_build_object('kind','manufacturer',
          'scope','Airstream official parts books, obtained by Larry in a browser via the site''s View button and supplied to Claude; identities only',
          'why_supplied','airstream.com answers automated downloads with 401 Unauthorized; not bypassed',
          'approvedBy','Larry, 26 Nov 2026','bulkEnabled',false))
on conflict (id) do nothing;

insert into rv_private.supplied_documents_v1(sha256, source_id, publisher, title, pages, supplied_by, obtained_via, extraction, verification, review_state)
values ('f80ee9b1f62e62d259ec63d07c66ad514ca38bc918521ba8de41ff7c23475bfe', 'airstream-parts-books-supplied', 'Airstream',
        '2027 Trade Wind Parts Book', 311, 'Larry', 'airstream.com parts-book page, View button, 26 Nov 2026',
        'airstream-partsbook-v1: text-line pass; callout and indented rows; internal laminate codes containing & excluded',
        'independent word-position pass agrees exactly (3,539 rows, 1,558 numbers, 0 discrepancies); page images 12 and 40 checked row by row (20/20, 37/37)',
        'reviewed')
on conflict (sha256) do nothing;
