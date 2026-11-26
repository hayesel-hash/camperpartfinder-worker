-- Aftermarket publishers v2: loosened OEM-identity rule (Larry, 26 Nov 2026 23:09: "loosen this rule:
-- the original part must already be in the database from its own maker").
--
-- v1 published an aftermarket claim only when the OEM part already existed as a published part of the
-- named brand. v2 keeps every other check and changes only the no-match case:
--   * match first, exactly as before (brand or its owner via aftermarket_brand_aliases_v1, number
--     compared without punctuation); then a letter-prefix-tolerant match (WF-8955 <-> 8955) so a
--     maker's own catalogue form and a cross-reference form do not become two parts;
--   * several matches -> held (unchanged);
--   * no match -> the OEM part is created from the aftermarket maker's statement, if and only if
--       - the brand is named on the page (oem_brand_basis = 'named_on_page'; unnamed brands still wait),
--       - the number is safe to store as printed: has a digit, 3-40 chars, only letters/digits/.-,
--         no spaces or '/' (printed variant shorthand like WF-8945/AD/LiS or PD4575/90) and no
--         wildcard 'XX' tails (6212XX);
--     otherwise the row is held with the reason.
--   * a created OEM part is named "<brand> <number> (as named in <maker>'s cross-reference)", its
--     identity evidence uses reviewer 'aftermarket-oem-named-v1', and every claim records
--     restrictions.oem_identity_basis: 'oem_catalogue' when the part has evidence from any other
--     source, else 'named_in_aftermarket_document' (not yet confirmed from the OEM's own catalogue).
--     When the OEM's own catalogue is loaded later, its evidence attaches to the same part.
--   * when the named number is a family designation of variants already in the OEM catalogue (WFCO 8735 vs
--     WF-8735-AD, WF-8735-PB-DA), the claim lists them in restrictions.oem_catalogue_variants.

create or replace function rv_private.aftermarket_oem_match_v1(p_brand text, p_number text)
returns table(part_id uuid, outcome text) language plpgsql stable set search_path to 'pg_catalog' as $fn$
declare mname text; n text; cnt integer; pid uuid;
begin
  mname := coalesce((select manufacturer_name from rv_private.aftermarket_brand_aliases_v1 where alias = p_brand), p_brand);
  n := upper(regexp_replace(coalesce(p_number,''), '[^0-9A-Za-z]', '', 'g'));
  if n = '' then return query select null::uuid, 'unsafe_number_format'; return; end if;
  select count(*), (array_agg(p.id))[1] into cnt, pid
    from rv_private.parts p join rv_private.manufacturers m on m.id = p.manufacturer_id
   where m.name = mname and upper(regexp_replace(p.exact_number,'[^0-9A-Za-z]','','g')) = n
     and p.variant = '' and p.state = 'published' and not p.synthetic;
  if cnt = 1 then return query select pid, 'matched'; return; end if;
  if cnt > 1 then return query select null::uuid, 'ambiguous'; return; end if;
  select count(*), (array_agg(p.id))[1] into cnt, pid
    from rv_private.parts p join rv_private.manufacturers m on m.id = p.manufacturer_id
   where m.name = mname and p.variant = '' and p.state = 'published' and not p.synthetic
     and (upper(regexp_replace(p.exact_number,'[^0-9A-Za-z]','','g')) ~ ('^[A-Z]{1,3}' || n || '$')
          or n ~ ('^[A-Z]{1,3}' || upper(regexp_replace(p.exact_number,'[^0-9A-Za-z]','','g')) || '$'));
  if cnt = 1 then return query select pid, 'matched_ignoring_letter_prefix'; return; end if;
  if cnt > 1 then return query select null::uuid, 'ambiguous'; return; end if;
  if p_number !~ '[0-9]' or p_number ~ '[[:space:]/]' or length(p_number) not between 3 and 40
     or p_number ~ '[^A-Za-z0-9./-]' or upper(p_number) ~ '[0-9]XX' then
    return query select null::uuid, 'unsafe_number_format'; return;
  end if;
  if exists (select 1 from rv_private.parts p join rv_private.manufacturers m on m.id = p.manufacturer_id
              where m.name = mname and p.exact_number = p_number and p.variant = '') then
    return query select null::uuid, 'exists_not_published'; return;
  end if;
  return query select null::uuid, 'create';
end;
$fn$;
revoke all on function rv_private.aftermarket_oem_match_v1(text, text) from public, anon, authenticated;

create or replace function rv_private.aftermarket_oem_create_v1(p_brand text, p_number text, p_maker text, p_category text,
                                                               p_evidence uuid, p_row text)
returns uuid language plpgsql set search_path to 'pg_catalog' as $fn$
declare mname text; mid uuid; pid uuid;
begin
  mname := coalesce((select manufacturer_name from rv_private.aftermarket_brand_aliases_v1 where alias = p_brand), p_brand);
  insert into rv_private.manufacturers(name) values (mname) on conflict (name) do nothing;
  select id into mid from rv_private.manufacturers where name = mname;
  insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
  values (mid, p_number, '', left(p_brand || ' ' || p_number || ' (as named in ' || p_maker || '''s cross-reference)', 200),
          p_category, 'published')
  returning id into pid;
  insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (pid, p_evidence, 'aftermarket-oem-named-v1')
  on conflict do nothing;
  insert into rv_private.audit_events(action, part_id, reason)
  values ('automated_oem_identity_from_aftermarket_xref', pid,
          p_brand || ' ' || p_number || ' named by ' || p_maker || ' (' || left(p_row, 150) || '); evidence ' || p_evidence::text
          || '; not yet confirmed from the OEM''s own catalogue');
  return pid;
end;
$fn$;
revoke all on function rv_private.aftermarket_oem_create_v1(text, text, text, text, uuid, text) from public, anon, authenticated;

create or replace function rv_private.aftermarket_oem_basis_v1(p_part uuid)
returns text language sql stable set search_path to 'pg_catalog' as $fn$
  select case when exists (select 1 from rv_private.identity_evidence ie where ie.part_id = p_part and ie.reviewer <> 'aftermarket-oem-named-v1')
              then 'oem_catalogue' else 'named_in_aftermarket_document' end;
$fn$;
revoke all on function rv_private.aftermarket_oem_basis_v1(uuid) from public, anon, authenticated;

-- Variant numbers of the same brand that extend the named number with a suffix (WFCO "8735" vs the WFCO
-- catalogue's WF-8735-AD / WF-8735-PB-DA): recorded on the claim so readers can see the related catalogue
-- variants. Never used to choose a match.
create or replace function rv_private.aftermarket_oem_variants_v1(p_brand text, p_number text)
returns text[] language sql stable set search_path to 'pg_catalog' as $fn$
  select coalesce((select array_agg(x.exact_number order by x.exact_number) from (
    select p.exact_number from rv_private.parts p join rv_private.manufacturers m on m.id = p.manufacturer_id
     where m.name = coalesce((select manufacturer_name from rv_private.aftermarket_brand_aliases_v1 where alias = p_brand), p_brand)
       and p.variant = '' and p.state = 'published' and not p.synthetic
       and upper(regexp_replace(p.exact_number,'[^0-9A-Za-z]','','g'))
           ~ ('^[A-Z]{0,3}' || upper(regexp_replace(p_number,'[^0-9A-Za-z]','','g')) || '[A-Z]')
     order by p.exact_number limit 12) x), '{}'::text[]);
$fn$;
revoke all on function rv_private.aftermarket_oem_variants_v1(text, text) from public, anon, authenticated;

-- PDF lane (aftermarket makers' own PDF catalogues)
create or replace function rv_private.publish_aftermarket_pdf_v2()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare
  r record; tier text; m record; oem_id uuid; maker_id uuid; am_id uuid; basis text;
  ev_id uuid; claim uuid; published integer := 0; created integer := 0; oem_created integer := 0; ambiguous integer := 0; unsafe integer := 0;
begin
  if not exists (select 1 from rv_private.factory_controls where enabled)
     or not exists (select 1 from rv_private.verification_control where enabled and auto_publish)
  then return '{"disabled":true}'::jsonb; end if;
  if not pg_try_advisory_xact_lock(741920614::bigint) then return '{"busy":true}'::jsonb; end if;
  for r in
    select a.*, s.publisher, s.url, pg.fetched_at
    from rv_private.aftermarket_assertions_v1 a
    join rv_private.aftermarket_source_pages_v1 pg
      on pg.source_id = a.source_id and pg.sha256 = a.page_sha256 and pg.review_state = 'reviewed'
    join rv_private.sources s
      on s.id = a.source_id and s.metadata->>'kind' = 'aftermarket_manufacturer_pdf'
     and s.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
    where a.status = 'staged' and a.relation = 'replaces' and a.oem_brand_basis = 'named_on_page'
      and a.hold_reason is null and a.aftermarket_number is not null and a.oem_number is not null and a.oem_brand is not null
    order by a.id limit 1000
  loop
    tier := rv_private.classify_crossref_publisher_v1('aftermarket_manufacturer', r.publisher, r.aftermarket_maker, true, true);
    if tier <> 'manufacturer_certified_aftermarket_claim' then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='policy: '||tier where id=r.id;
      continue;
    end if;
    select * into m from rv_private.aftermarket_oem_match_v1(r.oem_brand, r.oem_number);
    if m.outcome = 'ambiguous' then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='OEM number matches several published parts' where id=r.id;
      ambiguous := ambiguous + 1; continue;
    elsif m.outcome in ('unsafe_number_format', 'exists_not_published') then
      update rv_private.aftermarket_assertions_v1 set status='held',
        hold_reason = case m.outcome when 'unsafe_number_format' then 'OEM number not safe to create as printed (variant shorthand, wildcard or spaces): '||r.oem_number
                                     else 'OEM part exists but is not published (withdrawn)' end
       where id=r.id;
      unsafe := unsafe + 1; continue;
    end if;
    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                    position, quote, sha256, hash_kind, observed_at)
    values (r.source_id, r.row_key, r.page_sha256, r.url, (r.qualifiers->>'page')::int, coalesce(r.qualifiers->>'printed_page',''), r.row_key, r.row_text,
            r.page_sha256, 'sha256-pdf', r.fetched_at)
    on conflict (source_id, source_record_key, document_version) do nothing
    returning id into ev_id;
    if ev_id is null then
      select id into ev_id from rv_private.evidence
       where source_id=r.source_id and source_record_key=r.row_key and document_version=r.page_sha256;
    end if;
    oem_id := m.part_id;
    if m.outcome = 'create' then
      oem_id := rv_private.aftermarket_oem_create_v1(r.oem_brand, r.oem_number, r.aftermarket_maker, r.category, ev_id, r.row_text);
      oem_created := oem_created + 1;
    end if;
    basis := rv_private.aftermarket_oem_basis_v1(oem_id);
    select id into maker_id from rv_private.manufacturers where name = r.aftermarket_maker;
    select id into am_id from rv_private.parts where manufacturer_id=maker_id and exact_number=r.aftermarket_number and variant='';
    if am_id is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (maker_id, r.aftermarket_number, '',
              left(coalesce(nullif(btrim(r.aftermarket_label),''), r.aftermarket_maker||' replacement for '||r.oem_brand||' '||r.oem_number), 200),
              r.category, 'published')
      returning id into am_id;
      insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (am_id, ev_id, 'aftermarket-pdf-v1') on conflict do nothing;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_aftermarket_identity_publish', am_id, r.aftermarket_maker||' part listed in its own catalogue cross-reference; evidence '||ev_id::text);
      created := created + 1;
    end if;
    select id into claim from rv_private.relationship_claims
     where original_part_id=oem_id and replacement_part_id=am_id and kind='aftermarket_replacement' and state='verified' limit 1;
    if claim is null then
      insert into rv_private.relationship_claims
        (original_part_id, replacement_part_id, evidence_id, kind, authority, state, restrictions, explicit_statement, verification_version, verified_at)
      values (oem_id, am_id, ev_id, 'aftermarket_replacement', 'manufacturer', 'verified',
        jsonb_build_object('tier','manufacturer_certified_aftermarket','asserted_by',r.aftermarket_maker,
          'oem_brand',r.oem_brand,'oem_endorsement','none implied','not_an_oem_supersession',true,
          'statement_form',coalesce(r.qualifiers->>'statement_form','aftermarket maker''s own catalogue: maker''s part number stated equivalent to OEM part number'),
          'oem_identity_basis', basis, 'oem_match', m.outcome,
          'oem_catalogue_variants', case when m.outcome = 'create' then to_jsonb(rv_private.aftermarket_oem_variants_v1(r.oem_brand, r.oem_number)) else '[]'::jsonb end,
          'qualifiers',r.qualifiers,'equipment_fitment','not independently verified',
          'source_url',r.url,'document_sha256',r.page_sha256,'pdf_page',r.qualifiers->>'page','row',r.row_key,
          'policy_classifier','classify_crossref_publisher_v1'),
        r.row_text, 'aftermarket-own-catalogue-pdf-v2', now())
      returning id into claim;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_aftermarket_replacement_publish', oem_id,
              r.aftermarket_maker||' catalogue: '||r.oem_brand||' '||r.oem_number||' -> '||r.aftermarket_number||' (OEM identity: '||basis||'); evidence '||ev_id::text);
      published := published + 1;
    end if;
    update rv_private.aftermarket_assertions_v1 set status='published', claim_id=claim where id=r.id;
  end loop;
  return jsonb_build_object('new_aftermarket_claims',published,'new_aftermarket_parts',created,'oem_parts_created',oem_created,
    'ambiguous_held',ambiguous,'unsafe_or_withdrawn_held',unsafe,
    'still_staged',(select count(*) from rv_private.aftermarket_assertions_v1 a join rv_private.sources s on s.id=a.source_id
      where s.metadata->>'kind'='aftermarket_manufacturer_pdf' and a.status='staged' and a.hold_reason is null));
end;
$fn$;
revoke all on function rv_private.publish_aftermarket_pdf_v2() from public, anon, authenticated;

-- HTML lane (aftermarket makers' own cross-reference web pages)
create or replace function rv_private.publish_aftermarket_replacements_v2()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare
  r record; tier text; m record; oem_id uuid; maker_id uuid; dino_id uuid; basis text;
  ev_id uuid; claim uuid; published integer := 0; created integer := 0; oem_created integer := 0; ambiguous integer := 0; unsafe integer := 0;
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
      and a.hold_reason is null and a.aftermarket_number is not null and a.oem_number is not null and a.oem_brand is not null
    order by a.id limit 500
  loop
    tier := rv_private.classify_crossref_publisher_v1('aftermarket_manufacturer', r.publisher, r.aftermarket_maker, true, true);
    if tier <> 'manufacturer_certified_aftermarket_claim' then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='policy: '||tier where id=r.id;
      continue;
    end if;
    select * into m from rv_private.aftermarket_oem_match_v1(r.oem_brand, r.oem_number);
    if m.outcome = 'ambiguous' then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='OEM number matches several published parts' where id=r.id;
      ambiguous := ambiguous + 1; continue;
    elsif m.outcome in ('unsafe_number_format', 'exists_not_published') then
      update rv_private.aftermarket_assertions_v1 set status='held',
        hold_reason = case m.outcome when 'unsafe_number_format' then 'OEM number not safe to create as printed (variant shorthand, wildcard or spaces): '||r.oem_number
                                     else 'OEM part exists but is not published (withdrawn)' end
       where id=r.id;
      unsafe := unsafe + 1; continue;
    end if;
    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                    position, quote, sha256, hash_kind, observed_at)
    values (r.source_id, r.row_key, r.page_sha256, r.url, 1, '', r.row_key, r.row_text, r.page_sha256, 'sha256-html-page', r.fetched_at)
    on conflict (source_id, source_record_key, document_version) do nothing
    returning id into ev_id;
    if ev_id is null then
      select id into ev_id from rv_private.evidence
       where source_id=r.source_id and source_record_key=r.row_key and document_version=r.page_sha256;
    end if;
    oem_id := m.part_id;
    if m.outcome = 'create' then
      oem_id := rv_private.aftermarket_oem_create_v1(r.oem_brand, r.oem_number, r.aftermarket_maker, r.category, ev_id, r.row_text);
      oem_created := oem_created + 1;
    end if;
    basis := rv_private.aftermarket_oem_basis_v1(oem_id);
    select id into maker_id from rv_private.manufacturers where name = r.aftermarket_maker;
    select id into dino_id from rv_private.parts where manufacturer_id=maker_id and exact_number=r.aftermarket_number and variant='';
    if dino_id is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (maker_id, r.aftermarket_number, '',
              case when r.aftermarket_label ilike '%control board%' then 'Replacement control board for ' else 'Replacement board for ' end || r.oem_brand,
              r.category, 'published')
      returning id into dino_id;
      insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (dino_id, ev_id, 'aftermarket-xref-v1') on conflict do nothing;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_aftermarket_identity_publish', dino_id, r.aftermarket_maker||' part listed on its own cross-reference chart; evidence '||ev_id::text);
      created := created + 1;
    end if;
    select id into claim from rv_private.relationship_claims
     where original_part_id=oem_id and replacement_part_id=dino_id and kind='aftermarket_replacement' and state='verified' limit 1;
    if claim is null then
      insert into rv_private.relationship_claims
        (original_part_id, replacement_part_id, evidence_id, kind, authority, state, restrictions, explicit_statement, verification_version, verified_at)
      values (oem_id, dino_id, ev_id, 'aftermarket_replacement', 'manufacturer', 'verified',
        jsonb_build_object('tier','manufacturer_certified_aftermarket','asserted_by',r.aftermarket_maker,
          'oem_brand',r.oem_brand,'oem_endorsement','none implied','not_an_oem_supersession',true,
          'statement_form','aftermarket maker''s own cross-reference chart: OEM part number -> maker''s part number',
          'oem_identity_basis', basis, 'oem_match', m.outcome,
          'oem_catalogue_variants', case when m.outcome = 'create' then to_jsonb(rv_private.aftermarket_oem_variants_v1(r.oem_brand, r.oem_number)) else '[]'::jsonb end,
          'qualifiers',r.qualifiers,'equipment_fitment','not independently verified',
          'source_url',r.url,'page_sha256',r.page_sha256,'row',r.row_key,'policy_classifier','classify_crossref_publisher_v1'),
        r.row_text, 'aftermarket-own-part-chart-v2', now())
      returning id into claim;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_aftermarket_replacement_publish', oem_id,
              r.aftermarket_maker||' chart: '||r.oem_number||' -> '||r.aftermarket_number||' (OEM identity: '||basis||'); evidence '||ev_id::text);
      published := published + 1;
    end if;
    update rv_private.aftermarket_assertions_v1 set status='published', claim_id=claim where id=r.id;
  end loop;
  return jsonb_build_object('new_aftermarket_claims',published,'new_aftermarket_parts',created,'oem_parts_created',oem_created,
    'ambiguous_held',ambiguous,'unsafe_or_withdrawn_held',unsafe,
    'still_staged',(select count(*) from rv_private.aftermarket_assertions_v1
      where status='staged' and relation='replaces' and oem_brand_basis='named_on_page' and hold_reason is null and aftermarket_number is not null));
end;
$fn$;
revoke all on function rv_private.publish_aftermarket_replacements_v2() from public, anon, authenticated;

-- switch the schedules to v2 (same minutes)
select cron.unschedule('rv-aftermarket-pdf-v1') where exists (select 1 from cron.job where jobname = 'rv-aftermarket-pdf-v1');
select cron.unschedule('rv-aftermarket-replacements-v1') where exists (select 1 from cron.job where jobname = 'rv-aftermarket-replacements-v1');
select cron.schedule('rv-aftermarket-pdf-v2', '9-59/10 * * * *', $$select rv_private.publish_aftermarket_pdf_v2()$$);
select cron.schedule('rv-aftermarket-replacements-v2', '7-57/10 * * * *', $$select rv_private.publish_aftermarket_replacements_v2()$$);

-- Assertion categories must be valid part categories (parts_category_check). The PD4600 rows were staged
-- with 'electrical'; converters belong to external_equipment. A check on the assertions table stops a bad
-- category from aborting a whole publisher run again.
update rv_private.aftermarket_assertions_v1 set category = 'external_equipment'
 where category not in ('refrigeration','sanitation','water','windows_doors','heating','body_trim','external_equipment','running_gear');
alter table rv_private.aftermarket_assertions_v1 drop constraint if exists aftermarket_assertions_v1_category_check;
alter table rv_private.aftermarket_assertions_v1 add constraint aftermarket_assertions_v1_category_check
  check (category in ('refrigeration','sanitation','water','windows_doors','heating','body_trim','external_equipment','running_gear'));
