-- Three replacement-volume levers (Larry, 27 Nov 2026 09:03: "yes to both" — seller-stated tier,
-- and start on UK compatibles, standard part numbers, and RecPro / MC Enterprises / TRP).
--
-- 1. SELLER-STATED TIER. A retailer's or distributor's "replaces <brand> <number>" is kept as a
--    clearly labelled, lower-trust claim: kind 'third_party_compatibility', authority 'third_party',
--    state 'seller_stated' (never 'verified'), restrictions.tier = 'seller_stated_unverified' and a
--    plain-language trust label. Seller claims only ever link parts that ALREADY exist (no part is
--    created from a seller's statement). Shown through rv_private.seller_stated_replacements_v1.
--
-- 2. STORE CROSS-REFERENCES. Store pages already staged by the store reader carry "replaces ..."
--    sentences and (from this change) cross-reference tables ("Direct Replacement Chart":
--    Shurflo=4008-101-A65|WFCO=PDS3B-130-1260E|...). publish_store_replacements_v1 reads them:
--      * the product's own brand at a maker's / aftermarket maker's own store (identity published by
--        the store lane) -> manufacturer-certified aftermarket claim, same rules as the PDF/HTML
--        aftermarket lanes, including the loosened OEM-identity rule (create the named OEM part
--        when the brand is named and the number is safe to store);
--      * anything else (other brands at that store, or any product at a retailer/distributor store)
--        -> seller-stated tier, and only when both parts already exist.
--    Statements need replacement wording ("replaces", "replacement for", "direct replacement",
--    "cross reference", "interchange", "equivalent to", "OEM #"); "fits ..." is never used.
--    Each number attaches to the nearest brand named before it in the same statement. Numbers
--    must have >= 3 digits; units, sizes and bare years are ignored.
--
-- 3. STANDARD BEARING DESIGNATIONS. When two makers' own catalogues each name the same
--    industry-standard tapered-roller bearing designation for their part (Dexter 031-031-02
--    "L44649 Outer Bearing Cone", Lippert 122089 "Inner / outer bearing cone (L44649)"), the
--    parts are recorded as 'standard_designation_equivalent' both ways. The basis is the two
--    makers' own statements; the claim notes that any bearing of that designation is
--    dimensionally interchangeable and that brand quality is not asserted equal.
--
-- Rollback: unschedule rv-store-replacements-v1 and rv-standard-bearings-v1; set state='revoked'
-- on claims with verification_version in ('store-page-xref-v1','store-seller-stated-v1',
-- 'standard-designation-v1').

-- ---------------------------------------------------------------- 1. tier schema
alter table rv_private.relationship_claims drop constraint if exists relationship_claims_state_check;
alter table rv_private.relationship_claims add constraint relationship_claims_state_check
  check (state in ('pending','verified','rejected','revoked','seller_stated'));
alter table rv_private.relationship_claims add constraint relationship_claims_seller_tier_check check (
  (state <> 'seller_stated') or (
    kind = 'third_party_compatibility' and authority = 'third_party' and replacement_part_id is not null
    and restrictions->>'tier' = 'seller_stated_unverified'
    and nullif(restrictions->>'asserted_by','') is not null
    and nullif(restrictions->>'seller_url','') is not null
    and restrictions->>'oem_endorsement' = 'none implied'
    and length(btrim(coalesce(explicit_statement,''))) > 0));

alter table rv_private.relationship_claims drop constraint if exists relationship_claims_kind_check;
alter table rv_private.relationship_claims add constraint relationship_claims_kind_check check (kind in (
  'replacement','supersession','fitment','incompatible','association','kit','third_party_compatibility',
  'aftermarket_replacement','conversion_kit_replacement','standard_designation_equivalent'));
alter table rv_private.relationship_claims drop constraint if exists relationship_claims_check1;
alter table rv_private.relationship_claims add constraint relationship_claims_check1 check (
  (kind in ('replacement','supersession','aftermarket_replacement','conversion_kit_replacement',
            'standard_designation_equivalent','third_party_compatibility') and replacement_part_id is not null)
  or kind not in ('replacement','supersession','aftermarket_replacement','conversion_kit_replacement',
                  'standard_designation_equivalent','third_party_compatibility'));
alter table rv_private.relationship_claims drop constraint if exists relationship_claims_check3;
alter table rv_private.relationship_claims add constraint relationship_claims_check3 check (
  state <> 'verified' or (authority = 'manufacturer'
    and kind in ('replacement','supersession','fitment','incompatible','aftermarket_replacement',
                 'conversion_kit_replacement','standard_designation_equivalent')
    and length(btrim(explicit_statement)) > 0 and verification_version is not null and verified_at is not null));
alter table rv_private.relationship_claims add constraint relationship_claims_standard_designation_check check (
  kind <> 'standard_designation_equivalent' or (
    nullif(restrictions->>'designation','') is not null and nullif(restrictions->>'basis','') is not null));

alter table rv_private.store_sources_v1 drop constraint if exists store_sources_v1_authority_check;
alter table rv_private.store_sources_v1 add constraint store_sources_v1_authority_check
  check (authority in ('manufacturer','distributor','retailer'));
alter table rv_private.store_products_v1
  add column if not exists xref_state text check (xref_state in ('done','none','held')),
  add column if not exists xref_note text;

-- ---------------------------------------------------------------- 2. statement parser
create or replace function rv_private.brand_lookup_v1(p text)
returns text language sql stable set search_path to 'pg_catalog' as $fn$
  select coalesce(
    (select a.manufacturer_name from rv_private.aftermarket_brand_aliases_v1 a where lower(a.alias) = lower(btrim(p)) limit 1),
    (select m.name from rv_private.manufacturers m where lower(m.name) = lower(btrim(p)) limit 1));
$fn$;
revoke all on function rv_private.brand_lookup_v1(text) from public, anon, authenticated;

-- Part-number-like tokens: >= 3 digits, 4-30 chars; not units, sizes, prices or bare years.
create or replace function rv_private.xref_numbers_v1(seg text)
returns setof text language sql immutable set search_path to 'pg_catalog' as $fn$
  select distinct t from (
    select btrim((regexp_matches(coalesce(seg,''), '([A-Za-z0-9][A-Za-z0-9./-]{2,29})', 'g'))[1], '.-/') t) x
  where length(t) between 4 and 30
    and length(regexp_replace(t, '[^0-9]', '', 'g')) >= 3
    and t !~* '^[0-9]+([.,][0-9]+)?(v|vdc|vac|a|amp|amps|w|watt|watts|gpm|psi|mm|cm|in|ft|lb|lbs|kg|btu|mah|ah|hz|rpm|oz|gal|l)$'
    and t !~* '^[0-9]+x[0-9]+'
    and not (t ~ '^(19|20)[0-9]{2}$')
    and t !~ '^[0-9]{1,3}([.,][0-9]{3})+$';
$fn$;
revoke all on function rv_private.xref_numbers_v1(text) from public, anon, authenticated;

-- (brand, number, statement) triples from one compat entry.
create or replace function rv_private.xref_pairs_v1(entry text)
returns table(brand text, num text, statement text, form text)
language plpgsql stable set search_path to 'pg_catalog' as $fn$
declare parts text[]; cell text; h text; v text; b text; n text; s text; i int;
  hits record; prev_b text; prev_pos int; seg text;
begin
  if entry like 'TABLE|%' then
    parts := string_to_array(entry, '|');
    if array_length(parts,1) < 3 then return; end if;
    for i in 3 .. array_length(parts,1) loop
      cell := parts[i];
      h := btrim(split_part(cell, '=', 1)); v := btrim(substr(cell, length(split_part(cell,'=',1)) + 2));
      b := rv_private.brand_lookup_v1(h);
      if b is null and h ~ '^[A-Za-z][A-Za-z &''.-]{1,24}$'
         and lower(h) !~ '^(part|parts|part ?(no|number|#)|model|models|brand|size|description|sku|item|number|no|oem|oe|replaces|replacement|application|qty|price|type|voltage|gpm|psi|fits|series|year|years|length|width|height|weight|color|colour|notes?)\.?$'
         and (entry ~* '^TABLE\|[^|]*(replac|cross|interchange|equivalent|compatib)') then
        b := h;   -- a brand printed as a chart column header; kept as printed
      end if;
      if b is null then continue; end if;
      for n in select * from rv_private.xref_numbers_v1(v) loop
        brand := b; num := n; statement := left(entry, 300); form := 'table'; return next;
      end loop;
    end loop;
    return;
  end if;
  s := entry;
  if s !~* '(replaces|replacement (for|of)|direct replacement|cross[- ]?referenc|interchang|equivalent (to|of)|\moem\M\s*(part)?\s*(#|no\.?|number))' then return; end if;
  if s ~* '^\s*fits\M' then return; end if;
  -- brand mentions, in order of position
  prev_b := null; prev_pos := null;
  for hits in
    with names as (
      select a.alias nm, a.manufacturer_name mf from rv_private.aftermarket_brand_aliases_v1 a
      union select m.name, m.name from rv_private.manufacturers m where length(m.name) >= 3)
    select distinct on (pos) mf, pos, len from (
      select nn.mf, length(nn.nm) len,
             position(lower(nn.nm) in lower(s)) pos
        from names nn
       where position(lower(nn.nm) in lower(s)) > 0
         and s ~* ('(^|[^A-Za-z])' || regexp_replace(nn.nm, '([.^$*+?()\[\]{}|\\-])', '\\\1', 'g') || '($|[^A-Za-z])')) z
    order by pos, len desc
  loop
    if prev_b is not null then
      seg := substr(s, prev_pos, hits.pos - prev_pos);
      for n in select * from rv_private.xref_numbers_v1(seg) loop
        brand := prev_b; num := n; statement := left(s, 300); form := 'sentence'; return next;
      end loop;
    end if;
    prev_b := hits.mf; prev_pos := hits.pos + hits.len;
  end loop;
  if prev_b is not null then
    seg := substr(s, prev_pos);
    for n in select * from rv_private.xref_numbers_v1(seg) loop
      brand := prev_b; num := n; statement := left(s, 300); form := 'sentence'; return next;
    end loop;
  end if;
end;
$fn$;
revoke all on function rv_private.xref_pairs_v1(text) from public, anon, authenticated;

-- ---------------------------------------------------------------- 2b. store xref publisher
create or replace function rv_private.publish_store_replacements_v1(batch int default 400)
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare r record; x record; prod uuid; own boolean; mres record; op uuid; ev uuid; mname text;
  certified int := 0; seller int := 0; created int := 0; held int := 0; noid int := 0; notes text[];
begin
  if not pg_try_advisory_xact_lock(741920614::bigint) then return '{"busy":true}'::jsonb; end if;
  for r in
    select p.*, s.publisher, s.authority, s.brand_allowlist, s.source_id
      from rv_private.store_products_v1 p
      join rv_private.store_sources_v1 s on s.id = p.store_id and s.enabled and s.review_state = 'reviewed'
      join rv_private.sources src on src.id = s.source_id
       and src.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
     where p.xref_state is null and p.status in ('published','held')
       and jsonb_array_length(p.compat) > 0
     order by p.staged_at limit batch
  loop
    notes := '{}';
    own := r.authority = 'manufacturer' and r.part_id is not null and r.status = 'published';
    prod := case when own then r.part_id end;
    if prod is null and r.brand is not null and r.sku is not null then
      select m.part_id into prod from rv_private.aftermarket_oem_match_v1(coalesce(rv_private.brand_lookup_v1(r.brand), r.brand), r.sku) m
       where m.outcome in ('matched','matched_ignoring_letter_prefix');
    end if;
    if prod is null then
      update rv_private.store_products_v1 set xref_state = 'none', xref_note = 'product identity not in the database'
       where store_id = r.store_id and url = r.url and page_sha256 = r.page_sha256;
      noid := noid + 1; continue;
    end if;

    for x in
      select distinct on (upper(regexp_replace(q.num,'[^0-9A-Za-z]','','g')), q.brand) q.*
        from jsonb_array_elements_text(r.compat) e, lateral rv_private.xref_pairs_v1(e) q
    loop
      if not own and rv_private.brand_lookup_v1(x.brand) is null then continue; end if;
      if coalesce(rv_private.brand_lookup_v1(x.brand), x.brand) =
         (select m.name from rv_private.parts pp join rv_private.manufacturers m on m.id = pp.manufacturer_id where pp.id = prod) then
        continue;   -- same maker's own number: not an aftermarket statement
      end if;
      select * into mres from rv_private.aftermarket_oem_match_v1(x.brand, x.num) limit 1;
      op := mres.part_id;
      if op = prod then continue; end if;
      if op is null and not (own and mres.outcome = 'create') then
        notes := notes || (x.brand || ' ' || x.num || ': ' || mres.outcome);
        held := held + 1; continue;
      end if;

      insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                      position, quote, sha256, hash_kind, observed_at)
      values (r.source_id, r.url || '#xref-' || md5(x.statement), r.page_sha256, r.url, 1, '',
              'product page ' || x.form || ' statement', left(x.statement, 300), r.page_sha256, 'sha256-html-page', r.fetched_at)
      on conflict (source_id, source_record_key, document_version) do nothing returning id into ev;
      if ev is null then
        select id into ev from rv_private.evidence where source_id = r.source_id
           and source_record_key = r.url || '#xref-' || md5(x.statement) and document_version = r.page_sha256;
      end if;

      if op is null then
        op := rv_private.aftermarket_oem_create_v1(x.brand, x.num, r.publisher,
                (select pp.category from rv_private.parts pp where pp.id = prod), ev, x.statement);
        created := created + 1;
      end if;
      if own then
        if not exists (select 1 from rv_private.relationship_claims z where z.original_part_id = op and z.replacement_part_id = prod
                        and z.kind = 'aftermarket_replacement' and z.state = 'verified') then
          insert into rv_private.relationship_claims(original_part_id, replacement_part_id, evidence_id, kind, authority, state,
                      restrictions, explicit_statement, verification_version, verified_at)
          values (op, prod, ev, 'aftermarket_replacement', 'manufacturer', 'verified',
            jsonb_build_object('tier','manufacturer_certified_aftermarket','asserted_by', r.publisher,
              'oem_endorsement','none implied','source_page', r.url, 'statement_form', x.form,
              'oem_brand_as_printed', x.brand, 'oem_number_as_printed', x.num,
              'oem_identity_basis', rv_private.aftermarket_oem_basis_v1(op),
              'oem_catalogue_variants', to_jsonb(rv_private.aftermarket_oem_variants_v1(x.brand, x.num)),
              'equipment_fitment','not independently verified','market','not established for GB'),
            x.statement, 'store-page-xref-v1', now());
          certified := certified + 1;
        end if;
      else
        if not exists (select 1 from rv_private.relationship_claims z where z.original_part_id = op and z.replacement_part_id = prod
                        and z.kind in ('third_party_compatibility','aftermarket_replacement','replacement','supersession')
                        and z.state in ('seller_stated','verified')) then
          insert into rv_private.relationship_claims(original_part_id, replacement_part_id, evidence_id, kind, authority, state,
                      restrictions, explicit_statement, verification_version)
          values (op, prod, ev, 'third_party_compatibility', 'third_party', 'seller_stated',
            jsonb_build_object('tier','seller_stated_unverified','asserted_by', r.publisher, 'seller_url', r.url,
              'seller_role', r.authority, 'oem_endorsement','none implied',
              'trust_label','Seller-stated, not verified by either manufacturer',
              'statement_form', x.form, 'oem_brand_as_printed', x.brand, 'oem_number_as_printed', x.num,
              'equipment_fitment','not independently verified','market','not established for GB'),
            x.statement, 'store-seller-stated-v1');
          seller := seller + 1;
        end if;
      end if;
    end loop;
    update rv_private.store_products_v1 set xref_state = case when cardinality(notes) > 0 then 'held' else 'done' end,
           xref_note = nullif(left(array_to_string(notes, '; '), 500), '')
     where store_id = r.store_id and url = r.url and page_sha256 = r.page_sha256;
  end loop;
  return jsonb_build_object('certified_claims', certified, 'seller_stated_claims', seller, 'oem_parts_created', created,
                            'pairs_held', held, 'products_without_identity', noid);
end;
$fn$;
revoke all on function rv_private.publish_store_replacements_v1(int) from public, anon, authenticated;

create or replace view rv_private.seller_stated_replacements_v1 as
select c.id, o.exact_number as original_number, om.name as original_brand, o.name as original_name,
       r.exact_number as replacement_number, rm.name as replacement_brand, r.name as replacement_name,
       c.restrictions->>'trust_label' as trust, c.restrictions->>'asserted_by' as asserted_by,
       c.restrictions->>'seller_url' as seller_url, c.explicit_statement
  from rv_private.relationship_claims c
  join rv_private.parts o on o.id = c.original_part_id join rv_private.manufacturers om on om.id = o.manufacturer_id
  join rv_private.parts r on r.id = c.replacement_part_id join rv_private.manufacturers rm on rm.id = r.manufacturer_id
 where c.state = 'seller_stated' and o.state = 'published' and r.state = 'published';
revoke all on rv_private.seller_stated_replacements_v1 from public, anon, authenticated;

-- ---------------------------------------------------------------- 3. standard bearing designations
create or replace function rv_private.publish_standard_bearings_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare r record; n int := 0;
begin
  if not pg_try_advisory_xact_lock(741920615::bigint) then return '{"busy":true}'::jsonb; end if;
  for r in
    with c as (
      select p.id, p.manufacturer_id, p.exact_number, p.name,
             (select array_agg(t[1]) from regexp_matches(p.name, '\m((?:L|LM|JL|JM|HM|M)?[0-9]{4,6}(?:A|X)?)\M', 'g') t) toks,
             (select ie.evidence_id from rv_private.identity_evidence ie where ie.part_id = p.id order by ie.evidence_id limit 1) ev
        from rv_private.parts p
       where p.state = 'published' and not p.synthetic
         and (p.name ~* '\mbearing\s+(cup|cone)' or p.name ~* '^(cup|cone)\s*\(' or p.name ~* '\m(cup|cone)\s*/\s*race')
         and p.name !~* 'hub|drum|kit|assembly|\mset\M|stud|seal|grease|holder|vent|measuring'),
    d as (select c.*, toks[1] des, case when name ~* 'cup|race' then 'cup' else 'cone' end comp
            from c where cardinality(toks) = 1 and ev is not null)
    select a.id aid, b.id bid, b.ev bev, a.ev aev, a.des, a.comp, a.name aname, b.name bname
      from d a join d b on a.des = b.des and a.comp = b.comp and a.manufacturer_id <> b.manufacturer_id
  loop
    if not exists (select 1 from rv_private.relationship_claims z where z.original_part_id = r.aid and z.replacement_part_id = r.bid
                    and z.kind = 'standard_designation_equivalent' and z.state = 'verified') then
      insert into rv_private.relationship_claims(original_part_id, replacement_part_id, evidence_id, kind, authority, state,
                  restrictions, explicit_statement, verification_version, verified_at)
      values (r.aid, r.bid, r.bev, 'standard_designation_equivalent', 'manufacturer', 'verified',
        jsonb_build_object('designation', r.des, 'component', 'tapered roller bearing ' || r.comp,
          'basis', 'Both makers'' own catalogues name the same industry-standard bearing designation for their part',
          'original_statement', r.aname, 'original_evidence', r.aev, 'replacement_statement', r.bname,
          'note', 'Any ' || r.des || ' bearing ' || r.comp || ' is dimensionally interchangeable by designation; brand quality is not asserted equal. Fit cups and cones as matched pairs.',
          'equipment_fitment','not independently verified'),
        r.aname || ' = ' || r.bname, 'standard-designation-v1', now());
      n := n + 1;
    end if;
  end loop;
  return jsonb_build_object('claims', n);
end;
$fn$;
revoke all on function rv_private.publish_standard_bearings_v1() from public, anon, authenticated;

select cron.schedule('rv-store-replacements-v1', '3-58/5 * * * *', 'select rv_private.publish_store_replacements_v1()');
select cron.schedule('rv-standard-bearings-v1', '29 * * * *', 'select rv_private.publish_standard_bearings_v1()');

insert into rv_private.camper_input_change_log_v1(actor, change_category, reason, details, rollback_instructions)
values ('ClaudeL', 'replacement_volume',
  'Seller-stated tier, store cross-reference publisher and standard bearing designations (Larry, 27 Nov 2026: "yes to both")',
  jsonb_build_object('seller_tier','third_party_compatibility / seller_stated, existing parts only, labelled',
                     'store_xref','own-brand at maker store = certified aftermarket; else seller-stated',
                     'standard','same bearing designation named in two makers'' catalogues'),
  'See header of migration 20261127100000_seller_tier_store_xref_standard_bearings.sql');
