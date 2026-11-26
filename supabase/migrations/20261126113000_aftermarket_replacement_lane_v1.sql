-- Aftermarket replacement lane v1 (Lane 2 in engineering/target-brands-and-lanes.md).
--
-- An aftermarket maker's own chart saying "our part replaces OEM part X" is a
-- manufacturer-certified aftermarket claim (policy of 24 Nov 2026, encoded in
-- rv_private.classify_crossref_publisher_v1). It is NOT an OEM supersession,
-- so it gets its own claim kind: existing supersession publishers treat any
-- 'replacement'/'supersession' as a part's single successor, and an aftermarket
-- alternative must never block or be confused with that.
--
-- Flow: GitHub workflow aftermarket-xref.yml -> rv-aftermarket-gateway (OIDC,
-- stage only) -> public.rv_aftermarket_stage -> staging tables. Publication is
-- rv_private.publish_aftermarket_replacements_v1, which only uses rows from a
-- page marked 'reviewed', a brand the page names, and an exact OEM number that
-- already exists as a published part. Unmatched rows wait and publish later as
-- OEM coverage grows. Model fitment is staged only.
--
-- Rollback: unschedule cron job rv-aftermarket-replacements-v1; set the
-- aftermarket claims to state 'revoked'; drop the functions and the two
-- staging tables; restore the three relationship_claims checks below to their
-- previous definitions (without 'aftermarket_replacement').

-- 1. Claim kind ---------------------------------------------------------------
alter table rv_private.relationship_claims drop constraint relationship_claims_kind_check;
alter table rv_private.relationship_claims add constraint relationship_claims_kind_check
  check (kind = any (array['replacement','supersession','fitment','incompatible','association',
                           'kit','third_party_compatibility','aftermarket_replacement']));

alter table rv_private.relationship_claims drop constraint relationship_claims_check1;
alter table rv_private.relationship_claims add constraint relationship_claims_check1
  check ((kind = any (array['replacement','supersession','aftermarket_replacement']) and replacement_part_id is not null)
         or kind <> all (array['replacement','supersession','aftermarket_replacement']));

alter table rv_private.relationship_claims drop constraint relationship_claims_check3;
alter table rv_private.relationship_claims add constraint relationship_claims_check3
  check (state <> 'verified'
         or (authority = 'manufacturer'
             and kind = any (array['replacement','supersession','fitment','incompatible','aftermarket_replacement'])
             and length(btrim(explicit_statement)) > 0
             and verification_version is not null and verified_at is not null));

-- Every aftermarket claim says who asserts it and that no OEM endorsement is implied.
alter table rv_private.relationship_claims add constraint relationship_claims_aftermarket_tier_check
  check (kind <> 'aftermarket_replacement'
         or (restrictions->>'tier' = 'manufacturer_certified_aftermarket'
             and nullif(restrictions->>'asserted_by','') is not null
             and restrictions->>'oem_endorsement' = 'none implied'));

-- 2. Maker, sources, brand names ---------------------------------------------
insert into rv_private.manufacturers(name) values ('Dinosaur Electronics') on conflict (name) do nothing;

insert into rv_private.sources(id, publisher, url, access_state, metadata)
select v.id, 'Dinosaur Electronics', v.url, 'PUBLIC_FACTS',
       jsonb_build_object('kind','aftermarket_manufacturer',
         'scope','Maker''s own cross-reference chart: OEM part number -> maker''s part number. Model fitment staged only.',
         'allowedManufacturers', jsonb_build_array('Dinosaur Electronics'),
         'approvedBy','Larry, 26 Nov 2026', 'bulkEnabled', false,
         'robotsReview','enforced at fetch time by the worker robots policy')
from (values
  ('dinosaur-xref-norcold','https://www.dinosaurelectronics.com/Nor_chart.htm'),
  ('dinosaur-xref-dometic','https://www.dinosaurelectronics.com/Dom_Chart.htm'),
  ('dinosaur-xref-ignitor','https://www.dinosaurelectronics.com/UIB_Chart.htm'),
  ('dinosaur-xref-other',  'https://www.dinosaurelectronics.com/Msc_Chart.htm')) v(id,url)
on conflict (id) do nothing;

-- How a chart names an OEM brand -> our manufacturers.name. Exact, reviewed entries only.
create table if not exists rv_private.aftermarket_brand_aliases_v1 (
  alias text primary key,
  manufacturer_name text not null
);
insert into rv_private.aftermarket_brand_aliases_v1 values
  ('Norcold','Norcold'), ('Dometic','Dometic'), ('Onan','Cummins Onan'), ('Servel','Servel')
on conflict do nothing;

-- 3. Staging ------------------------------------------------------------------
create table if not exists rv_private.aftermarket_source_pages_v1 (
  source_id    text not null references rv_private.sources(id),
  sha256       text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  url          text not null,
  fetched_at   timestamptz not null,
  html         text not null,          -- private evidence copy; never exposed
  parser       text not null,
  review_state text not null default 'unreviewed' check (review_state in ('unreviewed','reviewed','rejected')),
  reviewed_by  text, reviewed_at timestamptz, review_note text,
  staged_at    timestamptz not null default now(),
  primary key (source_id, sha256)
);

create table if not exists rv_private.aftermarket_assertions_v1 (
  id                 bigint generated always as identity primary key,
  source_id          text not null,
  page_sha256        text not null,
  table_key          text not null,
  row_key            text not null,
  relation           text not null check (relation in ('replaces','fits_model')),
  aftermarket_maker  text not null,
  aftermarket_number text,
  aftermarket_label  text,
  oem_brand          text,
  oem_brand_basis    text not null check (oem_brand_basis in ('named_on_page','not_named')),
  oem_number         text,
  oem_model          text,
  category           text not null,
  qualifiers         jsonb not null default '{}' check (jsonb_typeof(qualifiers) = 'object'),
  row_text           text not null,
  status             text not null check (status in ('staged','held','skipped','published')),
  hold_reason        text,
  claim_id           uuid references rv_private.relationship_claims(id),
  created_at         timestamptz not null default now(),
  foreign key (source_id, page_sha256) references rv_private.aftermarket_source_pages_v1(source_id, sha256),
  unique (source_id, page_sha256, row_key)
);
create index if not exists aftermarket_assertions_v1_open
  on rv_private.aftermarket_assertions_v1 (status, relation) where status = 'staged';

-- 4. Gateway RPC (service role only) ------------------------------------------
create or replace function public.rv_aftermarket_stage(page jsonb, page_rows jsonb)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog'
as $fn$
declare s record; n integer := 0; new_page boolean := false;
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

  insert into rv_private.aftermarket_source_pages_v1(source_id, sha256, url, fetched_at, html, parser)
  values (s.id, page->>'sha256', s.url, (page->>'fetched_at')::timestamptz, page->>'html', left(page->>'parser',60))
  on conflict do nothing;
  new_page := found;

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
  where x.aftermarket_maker = s.publisher                 -- a source can only speak for its own maker
    and x.status in ('staged','held','skipped')
    and x.relation in ('replaces','fits_model')
    and x.category in ('refrigeration','sanitation','water','windows_doors','heating','body_trim','external_equipment','running_gear')
    and length(coalesce(x.row_text,'')) > 0
  on conflict do nothing;
  get diagnostics n = row_count;
  return jsonb_build_object('page_new', new_page, 'rows_inserted', n);
end;
$fn$;
revoke all on function public.rv_aftermarket_stage(jsonb, jsonb) from public, anon, authenticated;
grant execute on function public.rv_aftermarket_stage(jsonb, jsonb) to service_role;

-- 5. Publisher ----------------------------------------------------------------
create or replace function rv_private.publish_aftermarket_replacements_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog'
as $fn$
declare
  r record; tier text; oem_count integer; oem_id uuid; maker_id uuid; dino_id uuid;
  ev_id uuid; claim uuid; published integer := 0; created integer := 0; ambiguous integer := 0;
begin
  if not exists (select 1 from rv_private.factory_controls where enabled)
     or not exists (select 1 from rv_private.verification_control where enabled and auto_publish)
  then return '{"disabled":true}'::jsonb; end if;
  if not pg_try_advisory_xact_lock(741920612::bigint) then return '{"busy":true}'::jsonb; end if;

  for r in
    select a.*, s.publisher, s.url, pg.fetched_at
    from rv_private.aftermarket_assertions_v1 a
    join rv_private.aftermarket_source_pages_v1 pg
      on pg.source_id = a.source_id and pg.sha256 = a.page_sha256 and pg.review_state = 'reviewed'
    join rv_private.sources s
      on s.id = a.source_id and s.metadata->>'kind' = 'aftermarket_manufacturer'
     and s.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
    where a.status = 'staged' and a.relation = 'replaces' and a.oem_brand_basis = 'named_on_page'
      and a.hold_reason is null and a.aftermarket_number is not null and a.oem_number is not null
    order by a.id
    limit 500
  loop
    tier := rv_private.classify_crossref_publisher_v1('aftermarket_manufacturer', r.publisher, r.aftermarket_maker, true, true);
    if tier <> 'manufacturer_certified_aftermarket_claim' then
      update rv_private.aftermarket_assertions_v1 set status = 'held', hold_reason = 'policy: ' || tier where id = r.id;
      continue;
    end if;

    -- The OEM part must already exist: exact number (punctuation ignored), the brand the page names.
    select count(*), (array_agg(p.id))[1] into oem_count, oem_id
    from rv_private.parts p
    join rv_private.manufacturers m on m.id = p.manufacturer_id
    where m.name = coalesce((select manufacturer_name from rv_private.aftermarket_brand_aliases_v1 where alias = r.oem_brand), r.oem_brand)
      and upper(regexp_replace(p.exact_number, '[^0-9A-Za-z]', '', 'g')) = upper(regexp_replace(r.oem_number, '[^0-9A-Za-z]', '', 'g'))
      and p.variant = '' and p.state = 'published' and not p.synthetic;
    if oem_count = 0 then continue; end if;          -- waits for OEM coverage
    if oem_count > 1 then
      update rv_private.aftermarket_assertions_v1 set status = 'held', hold_reason = 'OEM number matches several published parts' where id = r.id;
      ambiguous := ambiguous + 1;
      continue;
    end if;

    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                    position, quote, sha256, hash_kind, observed_at)
    values (r.source_id, r.row_key, r.page_sha256, r.url, 1, '', r.row_key, r.row_text, r.page_sha256,
            'sha256-html-page', r.fetched_at)
    on conflict (source_id, source_record_key, document_version) do nothing
    returning id into ev_id;
    if ev_id is null then
      select id into ev_id from rv_private.evidence
       where source_id = r.source_id and source_record_key = r.row_key and document_version = r.page_sha256;
    end if;

    select id into maker_id from rv_private.manufacturers where name = r.aftermarket_maker;
    select id into dino_id from rv_private.parts
     where manufacturer_id = maker_id and exact_number = r.aftermarket_number and variant = '';
    if dino_id is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (maker_id, r.aftermarket_number, '',
              case when r.aftermarket_label ilike '%control board%' then 'Replacement control board for '
                   else 'Replacement board for ' end || r.oem_brand,
              r.category, 'published')
      returning id into dino_id;
      insert into rv_private.identity_evidence(part_id, evidence_id, reviewer)
      values (dino_id, ev_id, 'aftermarket-xref-v1') on conflict do nothing;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_aftermarket_identity_publish', dino_id,
              r.aftermarket_maker || ' part listed on its own cross-reference chart; evidence ' || ev_id::text);
      created := created + 1;
    end if;

    select id into claim from rv_private.relationship_claims
     where original_part_id = oem_id and replacement_part_id = dino_id
       and kind = 'aftermarket_replacement' and state = 'verified'
     limit 1;
    if claim is null then
      insert into rv_private.relationship_claims
        (original_part_id, replacement_part_id, evidence_id, kind, authority, state,
         restrictions, explicit_statement, verification_version, verified_at)
      values (oem_id, dino_id, ev_id, 'aftermarket_replacement', 'manufacturer', 'verified',
        jsonb_build_object(
          'tier', 'manufacturer_certified_aftermarket',
          'asserted_by', r.aftermarket_maker,
          'oem_brand', r.oem_brand,
          'oem_endorsement', 'none implied',
          'not_an_oem_supersession', true,
          'statement_form', 'aftermarket maker''s own cross-reference chart: OEM part number -> maker''s part number',
          'qualifiers', r.qualifiers,
          'equipment_fitment', 'not independently verified',
          'source_url', r.url, 'page_sha256', r.page_sha256, 'row', r.row_key,
          'policy_classifier', 'classify_crossref_publisher_v1'),
        r.row_text, 'aftermarket-own-part-chart-v1', now())
      returning id into claim;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_aftermarket_replacement_publish', oem_id,
              r.aftermarket_maker || ' chart: ' || r.oem_number || ' -> ' || r.aftermarket_number || '; evidence ' || ev_id::text);
      published := published + 1;
    end if;
    update rv_private.aftermarket_assertions_v1 set status = 'published', claim_id = claim where id = r.id;
  end loop;

  return jsonb_build_object(
    'new_aftermarket_claims', published, 'new_aftermarket_parts', created, 'ambiguous_held', ambiguous,
    'waiting_for_oem_part', (select count(*) from rv_private.aftermarket_assertions_v1
                              where status = 'staged' and relation = 'replaces' and oem_brand_basis = 'named_on_page'
                                and hold_reason is null and aftermarket_number is not null));
end;
$fn$;
revoke all on function rv_private.publish_aftermarket_replacements_v1() from public, anon, authenticated;

select cron.schedule('rv-aftermarket-replacements-v1', '7-57/10 * * * *',
                     'select rv_private.publish_aftermarket_replacements_v1()');

insert into rv_private.camper_input_change_log_v1(actor, change_category, reason, details, rollback_instructions)
values ('ClaudeL', 'aftermarket_lane',
  'Lane 2 machinery: stage aftermarket makers'' own cross-reference charts and publish them as manufacturer-certified aftermarket alternatives (Larry, 26 Nov 2026)',
  jsonb_build_object('claim_kind','aftermarket_replacement','first_maker','Dinosaur Electronics',
    'publication','reviewed page + named brand + exact existing OEM part only','fitment','staged only'),
  'See header of migration 20261126113000_aftermarket_replacement_lane_v1.sql');
