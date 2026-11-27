-- Store cross-reference publisher: boilerplate guard (27 Nov 2026). A sentence repeated word for word on
-- three or more product pages of one store is held, not published (Panther RV printed "This is an Aftermarket
-- replacement for the Dometic 3104133." on 10 different MC Enterprises parts). Tables are exempt: RecPro
-- prints the same pump chart on colour variants of one pump.
create or replace function rv_private.publish_store_replacements_v1(batch int default 400)
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare r record; x record; prod uuid; own boolean; mres record; op uuid; ev uuid; mname text;
  certified int := 0; seller int := 0; created int := 0; held int := 0; noid int := 0; newprod int := 0; notes text[];
begin
  if not pg_try_advisory_xact_lock(741920614::bigint) then return '{"busy":true}'::jsonb; end if;
  for r in
    select p.*, s.publisher, s.authority, s.brand_allowlist, s.source_id, s.sku_is_maker_number
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
    -- No identity yet: at a retailer the product is created from the listing (brand + MPN/SKU as
    -- printed), but only once one of its statements links to an OEM part that already exists.
    if prod is null and (own or not r.sku_is_maker_number or r.brand is null or coalesce(r.sku,'') !~ '^[A-Za-z0-9][A-Za-z0-9./-]{2,39}$'
                         or lower(r.brand) in (lower(r.publisher), 'generic', 'unbranded', 'universal')) then
      update rv_private.store_products_v1 set xref_state = 'none', xref_note = 'product identity not in the database'
       where store_id = r.store_id and url = r.url and page_sha256 = r.page_sha256;
      noid := noid + 1; continue;
    end if;

    for x in
      select distinct on (upper(regexp_replace(q.num,'[^0-9A-Za-z]','','g')), q.brand) q.*
        from jsonb_array_elements_text(r.compat) e, lateral rv_private.xref_pairs_v1(e) q
    loop
      if not own and rv_private.brand_lookup_v1(x.brand) is null then continue; end if;
      -- Boilerplate guard: a sentence copied onto 3+ different product pages of the same store
      -- (e.g. Panther's "Aftermarket replacement for the Dometic 3104133" on 10 different MC parts)
      -- is a template, not a statement about this product.
      if x.form = 'sentence' and (select count(distinct p2.url) from rv_private.store_products_v1 p2,
             jsonb_array_elements_text(p2.compat) e2 where p2.store_id = r.store_id and e2 = x.statement) >= 3 then
        notes := notes || ('boilerplate sentence on 3+ products: ' || left(x.statement, 80));
        held := held + 1; continue;
      end if;
      if coalesce(rv_private.brand_lookup_v1(x.brand), x.brand) = coalesce(
         (select m.name from rv_private.parts pp join rv_private.manufacturers m on m.id = pp.manufacturer_id where pp.id = prod),
         rv_private.brand_lookup_v1(r.brand), r.brand) then
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

      if prod is null then
        mname := coalesce(rv_private.brand_lookup_v1(r.brand), r.brand);
        insert into rv_private.manufacturers(name) values (mname) on conflict (name) do nothing;
        insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
        values ((select id from rv_private.manufacturers where name = mname), upper(r.sku), '',
                left(coalesce(nullif(btrim(r.name),''), mname || ' ' || r.sku), 200),
                (select pp.category from rv_private.parts pp where pp.id = op), 'published')
        on conflict do nothing returning id into prod;
        if prod is null then
          select p2.id into prod from rv_private.parts p2 join rv_private.manufacturers m2 on m2.id = p2.manufacturer_id
           where m2.name = mname and p2.exact_number = upper(r.sku) and p2.variant = '';
        end if;
        insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (prod, ev, 'store-retailer-listing-v1') on conflict do nothing;
        insert into rv_private.audit_events(action, part_id, reason)
        values ('automated_identity_from_retailer_listing', prod, mname || ' ' || r.sku || ' as listed by ' || r.publisher || ' (' || r.url || '); evidence ' || ev::text);
        newprod := newprod + 1;
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
    update rv_private.store_products_v1 set xref_state = case when prod is null then 'none' when cardinality(notes) > 0 then 'held' else 'done' end,
           xref_note = nullif(left(array_to_string(notes, '; '), 500), '')
     where store_id = r.store_id and url = r.url and page_sha256 = r.page_sha256;
  end loop;
  return jsonb_build_object('certified_claims', certified, 'seller_stated_claims', seller, 'oem_parts_created', created,
                            'pairs_held', held, 'products_without_identity', noid, 'retailer_products_created', newprod);
end;
$fn$;
revoke all on function rv_private.publish_store_replacements_v1(int) from public, anon, authenticated;
