-- "Replaces with conversion kit" (Larry, 26 Nov 2026 23:15).
-- A maker states that its part or unit replaces another part ONLY together with a conversion /
-- adapter / retrofit kit, or that the part is itself a retrofit kit for the original
-- (e.g. Coleman-Mach ceiling adapter 8330A5221 lets a Coleman-Mach rooftop unit replace a Carrier
-- unit; Progressive Dynamics PD4655 replaces the converter section of a WFCO 8955 power centre).
-- This is never a direct swap, so it gets its own claim kind; restrictions always carry
-- requires_conversion_kit, the kit part numbers and the maker's installation conditions.

alter table rv_private.aftermarket_assertions_v1 drop constraint aftermarket_assertions_v1_relation_check;
alter table rv_private.aftermarket_assertions_v1 add constraint aftermarket_assertions_v1_relation_check
  check (relation = any (array['replaces','fits_model','replaces_with_kit']));
alter table rv_private.aftermarket_assertions_v1 add constraint aftermarket_assertions_v1_kit_qualifiers_check
  check (relation <> 'replaces_with_kit'
         or (jsonb_typeof(qualifiers->'kit_parts') = 'array' and jsonb_array_length(qualifiers->'kit_parts') > 0
             and nullif(btrim(qualifiers->>'conditions'), '') is not null)) not valid;

alter table rv_private.relationship_claims drop constraint relationship_claims_kind_check;
alter table rv_private.relationship_claims add constraint relationship_claims_kind_check check (kind = any (array[
  'replacement','supersession','fitment','incompatible','association','kit','third_party_compatibility',
  'aftermarket_replacement','conversion_kit_replacement']));
alter table rv_private.relationship_claims drop constraint relationship_claims_check1;
alter table rv_private.relationship_claims add constraint relationship_claims_check1 check (
  (kind = any (array['replacement','supersession','aftermarket_replacement','conversion_kit_replacement']) and replacement_part_id is not null)
  or (kind <> all (array['replacement','supersession','aftermarket_replacement','conversion_kit_replacement'])));
alter table rv_private.relationship_claims drop constraint relationship_claims_check3;
alter table rv_private.relationship_claims add constraint relationship_claims_check3 check (
  state <> 'verified' or (authority = 'manufacturer'
    and kind = any (array['replacement','supersession','fitment','incompatible','aftermarket_replacement','conversion_kit_replacement'])
    and length(btrim(explicit_statement)) > 0 and verification_version is not null and verified_at is not null));
alter table rv_private.relationship_claims add constraint relationship_claims_conversion_kit_check check (
  kind <> 'conversion_kit_replacement'
  or ((restrictions->>'requires_conversion_kit') = 'true'
      and jsonb_typeof(restrictions->'kit_parts') = 'array' and jsonb_array_length(restrictions->'kit_parts') > 0
      and nullif(btrim(restrictions->>'conditions'), '') is not null
      and nullif(restrictions->>'asserted_by', '') is not null));

create or replace function rv_private.publish_conversion_kit_replacements_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare r record; m record; oem_id uuid; maker_id uuid; rp_id uuid; ev_id uuid; claim uuid;
  published int := 0; created int := 0; oem_created int := 0; held int := 0;
begin
  if not exists (select 1 from rv_private.factory_controls where enabled)
     or not exists (select 1 from rv_private.verification_control where enabled and auto_publish)
  then return '{"disabled":true}'::jsonb; end if;
  if not pg_try_advisory_xact_lock(741920615::bigint) then return '{"busy":true}'::jsonb; end if;
  for r in
    select a.*, s.publisher, s.url, pg.fetched_at
      from rv_private.aftermarket_assertions_v1 a
      join rv_private.aftermarket_source_pages_v1 pg on pg.source_id = a.source_id and pg.sha256 = a.page_sha256 and pg.review_state = 'reviewed'
      join rv_private.sources s on s.id = a.source_id and s.metadata->>'kind' in ('aftermarket_manufacturer_pdf','manufacturer')
       and s.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
     where a.status = 'staged' and a.relation = 'replaces_with_kit' and a.oem_brand_basis = 'named_on_page'
       and a.hold_reason is null and a.aftermarket_number is not null and a.oem_number is not null and a.oem_brand is not null
     order by a.id limit 1000
  loop
    -- the replacement maker must be the document's publisher: makers speak only for their own parts
    if r.aftermarket_maker is distinct from r.publisher
       and not exists (select 1 from rv_private.aftermarket_brand_aliases_v1 where alias = r.publisher and manufacturer_name = r.aftermarket_maker) then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='kit maker is not the document publisher' where id=r.id;
      held := held + 1; continue;
    end if;
    select * into m from rv_private.aftermarket_oem_match_v1(r.oem_brand, r.oem_number);
    if m.outcome not in ('matched','matched_ignoring_letter_prefix','create') then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='original part: '||m.outcome where id=r.id;
      held := held + 1; continue;
    end if;
    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page, position, quote, sha256, hash_kind, observed_at)
    values (r.source_id, r.row_key, r.page_sha256, r.url, (r.qualifiers->>'page')::int, coalesce(r.qualifiers->>'printed_page',''), r.row_key, r.row_text,
            r.page_sha256, 'sha256-pdf', r.fetched_at)
    on conflict (source_id, source_record_key, document_version) do nothing returning id into ev_id;
    if ev_id is null then
      select id into ev_id from rv_private.evidence where source_id=r.source_id and source_record_key=r.row_key and document_version=r.page_sha256;
    end if;
    oem_id := m.part_id;
    if m.outcome = 'create' then
      oem_id := rv_private.aftermarket_oem_create_v1(r.oem_brand, r.oem_number, r.aftermarket_maker, r.category, ev_id, r.row_text);
      oem_created := oem_created + 1;
    end if;
    select id into maker_id from rv_private.manufacturers where name = r.aftermarket_maker;
    select id into rp_id from rv_private.parts where manufacturer_id=maker_id and exact_number=r.aftermarket_number and variant='';
    if rp_id is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (maker_id, r.aftermarket_number, '', left(coalesce(nullif(btrim(r.aftermarket_label),''), r.aftermarket_maker||' conversion kit'), 200), r.category, 'published')
      returning id into rp_id;
      insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (rp_id, ev_id, 'conversion-kit-v1') on conflict do nothing;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_conversion_kit_identity_publish', rp_id, r.aftermarket_maker||' part in its own conversion/retrofit document; evidence '||ev_id::text);
      created := created + 1;
    end if;
    select id into claim from rv_private.relationship_claims
     where original_part_id=oem_id and replacement_part_id=rp_id and kind='conversion_kit_replacement' and state='verified' limit 1;
    if claim is null then
      insert into rv_private.relationship_claims(original_part_id, replacement_part_id, evidence_id, kind, authority, state, restrictions,
                                                 explicit_statement, verification_version, verified_at)
      values (oem_id, rp_id, ev_id, 'conversion_kit_replacement', 'manufacturer', 'verified',
        jsonb_build_object('requires_conversion_kit', true, 'not_a_direct_swap', true,
          'kit_parts', r.qualifiers->'kit_parts', 'conditions', r.qualifiers->>'conditions',
          'asserted_by', r.aftermarket_maker, 'oem_brand', r.oem_brand, 'oem_endorsement', 'none implied',
          'qualifiers', r.qualifiers, 'source_url', r.url, 'document_sha256', r.page_sha256, 'pdf_page', r.qualifiers->>'page', 'row', r.row_key),
        r.row_text, 'conversion-kit-own-document-v1', now())
      returning id into claim;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_conversion_kit_replacement_publish', oem_id,
              r.aftermarket_maker||': '||r.oem_brand||' '||r.oem_number||' -> '||r.aftermarket_number||' with conversion kit; evidence '||ev_id::text);
      published := published + 1;
    end if;
    update rv_private.aftermarket_assertions_v1 set status='published', claim_id=claim where id=r.id;
  end loop;
  return jsonb_build_object('new_conversion_kit_claims', published, 'new_kit_parts', created, 'original_parts_created', oem_created, 'held', held,
    'waiting', (select count(*) from rv_private.aftermarket_assertions_v1 where relation='replaces_with_kit' and status='staged' and hold_reason is null));
end; $fn$;
revoke all on function rv_private.publish_conversion_kit_replacements_v1() from public, anon, authenticated;

select cron.schedule('rv-conversion-kit-replacements-v1', '4-54/10 * * * *', 'select rv_private.publish_conversion_kit_replacements_v1()');

-- Reclassify the 9 Progressive Dynamics PD4600 rows (published 26 Nov as plain aftermarket
-- replacements): the guide says each kit replaces the converter SECTION inside the existing
-- power centre, so they are conversion-kit replacements.
update rv_private.aftermarket_assertions_v1
   set relation = 'replaces_with_kit',
       qualifiers = qualifiers || jsonb_build_object('kit_parts', jsonb_build_array(jsonb_build_object('maker','Progressive Dynamics','number',aftermarket_number)),
                     'conditions', 'Retrofit kit: replaces the converter section of the existing power centre; do not install a higher amperage than the original')
 where source_id = 'progressive-dynamics-pd4600-guide';
update rv_private.relationship_claims c
   set kind = 'conversion_kit_replacement',
       verification_version = 'conversion-kit-own-document-v1',
       restrictions = (c.restrictions - 'tier' - 'not_an_oem_supersession')
         || jsonb_build_object('requires_conversion_kit', true, 'not_a_direct_swap', true,
              'kit_parts', a.qualifiers->'kit_parts', 'conditions', a.qualifiers->>'conditions', 'reclassified', '2026-11-26 from aftermarket_replacement')
  from rv_private.aftermarket_assertions_v1 a
 where a.source_id = 'progressive-dynamics-pd4600-guide' and a.claim_id = c.id and c.kind = 'aftermarket_replacement';
