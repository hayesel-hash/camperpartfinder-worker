-- Aftermarket PDF lane v1: aftermarket makers' own PDF catalogues that state "our part X is
-- equivalent to / replaces OEM brand part Y" (first: NBK Parts 2023 catalogue, "EQUIV. TO").
-- Rows are staged in rv_private.aftermarket_assertions_v1 against a reviewed document row in
-- aftermarket_source_pages_v1 (html = '' for PDFs; parser names the reader). Sources use
-- metadata kind 'aftermarket_manufacturer_pdf' so the HTML publisher (v1) never touches them.
-- Same policy as v1: classify_crossref_publisher_v1 must return a manufacturer-certified
-- aftermarket claim; the OEM part must already be a published part of the named brand (or its
-- owner, via aftermarket_brand_aliases_v1); ambiguous matches are held; nothing is inferred.
-- Evidence records the PDF SHA-256 and the PDF page.

insert into rv_private.manufacturers(name) values ('NBK') on conflict (name) do nothing;

-- Brand-ownership aliases (Atwood and Duo-Therm part numbers are carried by Dometic; the RV
-- Coleman air-conditioner line is Coleman-Mach). Matching still requires the exact OEM number.
insert into rv_private.aftermarket_brand_aliases_v1(alias, manufacturer_name) values
  ('Atwood','Dometic'), ('Duo-Therm','Dometic'), ('Coleman','Coleman-Mach'), ('Suburban','Suburban'), ('Lippert','Lippert')
on conflict do nothing;

insert into rv_private.sources(id, publisher, url, access_state, metadata)
values ('nbk-catalog-2023', 'NBK', 'https://partszone.wdarmstrong.com/documents/nbk%20catalog%20all%20parts%202023-e.pdf', 'PUBLIC_FACTS',
        jsonb_build_object('kind','aftermarket_manufacturer_pdf','format','pdf',
          'scope','NBK Parts all-parts catalogue 2023 (manufacturer-issued; hosted by distributor W.D. Armstrong); EQUIV. TO cross-references',
          'supplied_via','Larry''s Drive folder (ChatGPT handoff, 26 Nov 2026)','approvedBy','Larry, 26 Nov 2026'))
on conflict (id) do nothing;

create or replace function rv_private.publish_aftermarket_pdf_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare
  r record; tier text; oem_count integer; oem_id uuid; maker_id uuid; am_id uuid;
  ev_id uuid; claim uuid; published integer := 0; created integer := 0; ambiguous integer := 0;
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
      and a.hold_reason is null and a.aftermarket_number is not null and a.oem_number is not null
    order by a.id limit 1000
  loop
    tier := rv_private.classify_crossref_publisher_v1('aftermarket_manufacturer', r.publisher, r.aftermarket_maker, true, true);
    if tier <> 'manufacturer_certified_aftermarket_claim' then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='policy: '||tier where id=r.id;
      continue;
    end if;
    select count(*), (array_agg(p.id))[1] into oem_count, oem_id
    from rv_private.parts p join rv_private.manufacturers m on m.id = p.manufacturer_id
    where m.name = coalesce((select manufacturer_name from rv_private.aftermarket_brand_aliases_v1 where alias = r.oem_brand), r.oem_brand)
      and upper(regexp_replace(p.exact_number,'[^0-9A-Za-z]','','g')) = upper(regexp_replace(r.oem_number,'[^0-9A-Za-z]','','g'))
      and p.variant = '' and p.state = 'published' and not p.synthetic;
    if oem_count = 0 then continue; end if;
    if oem_count > 1 then
      update rv_private.aftermarket_assertions_v1 set status='held', hold_reason='OEM number matches several published parts' where id=r.id;
      ambiguous := ambiguous + 1; continue;
    end if;
    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                    position, quote, sha256, hash_kind, observed_at)
    values (r.source_id, r.row_key, r.page_sha256, r.url, (r.qualifiers->>'page')::int, '', r.row_key, r.row_text,
            r.page_sha256, 'sha256-pdf', r.fetched_at)
    on conflict (source_id, source_record_key, document_version) do nothing
    returning id into ev_id;
    if ev_id is null then
      select id into ev_id from rv_private.evidence
       where source_id=r.source_id and source_record_key=r.row_key and document_version=r.page_sha256;
    end if;
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
          'statement_form','aftermarket maker''s own catalogue: maker''s part number stated equivalent to OEM part number',
          'qualifiers',r.qualifiers,'equipment_fitment','not independently verified',
          'source_url',r.url,'document_sha256',r.page_sha256,'pdf_page',r.qualifiers->>'page','row',r.row_key,
          'policy_classifier','classify_crossref_publisher_v1'),
        r.row_text, 'aftermarket-own-catalogue-pdf-v1', now())
      returning id into claim;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_aftermarket_replacement_publish', oem_id,
              r.aftermarket_maker||' catalogue: '||r.oem_brand||' '||r.oem_number||' -> '||r.aftermarket_number||'; evidence '||ev_id::text);
      published := published + 1;
    end if;
    update rv_private.aftermarket_assertions_v1 set status='published', claim_id=claim where id=r.id;
  end loop;
  return jsonb_build_object('new_aftermarket_claims',published,'new_aftermarket_parts',created,'ambiguous_held',ambiguous,
    'waiting_for_oem_part',(select count(*) from rv_private.aftermarket_assertions_v1 a join rv_private.sources s on s.id=a.source_id
      where s.metadata->>'kind'='aftermarket_manufacturer_pdf' and a.status='staged' and a.hold_reason is null));
end;
$fn$;
revoke all on function rv_private.publish_aftermarket_pdf_v1() from public, anon, authenticated;

select cron.schedule('rv-aftermarket-pdf-v1', '9-59/10 * * * *', $$select rv_private.publish_aftermarket_pdf_v1()$$);
