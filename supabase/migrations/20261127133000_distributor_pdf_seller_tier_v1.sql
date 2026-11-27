-- Distributor catalogues as a source (Larry, 27 Nov 2026 ~12:40: "yes" to "whether distributor catalogues count as a
-- source (Berger, Movera, Grove lists, Trailer Enterprises, Coast to Coast and others)"; applied on Larry's
-- explicit "apply", 27 Nov 2026 ~12:55).
--
-- A distributor's PDF catalogue that states one maker's part replaces / interchanges with another maker's part is
-- published in the existing SELLER-STATED tier (migration 20261127100000): kind 'third_party_compatibility',
-- authority 'third_party', state 'seller_stated' (never 'verified'), restrictions.tier 'seller_stated_unverified',
-- labelled "Distributor-stated, not verified by either manufacturer". As in the store lane, a distributor's statement
-- never creates a part: both parts must already exist with an exact number match (no letter-prefix tolerance).
-- Rows whose parts do not exist yet stay staged and are retried on every run.
--
-- Staging: rv_private.aftermarket_assertions_v1 rows (relation 'replaces') against a reviewed
-- aftermarket_source_pages_v1 row of a sources row whose metadata.kind = 'distributor_pdf'. In these rows
-- aftermarket_maker / aftermarket_number are the replacing part's maker and number as printed, oem_brand / oem_number
-- the replaced part; the distributor is sources.publisher. A distributor's own stock number is never a part.
-- Distributor catalogues that only list a maker's number against the distributor's stock number are identity
-- evidence for the maker's part (supplied-documents lane), not replacement claims.
--
-- Rollback: select cron.unschedule('rv-distributor-pdf-v1'); update rv_private.relationship_claims set state='revoked'
-- where verification_version = 'distributor-pdf-seller-stated-v1';

create or replace function rv_private.publish_distributor_pdf_v1()
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare
  r record; o record; a record; ev_id uuid; claim uuid; published integer := 0; waiting integer := 0; held integer := 0;
begin
  if not exists (select 1 from rv_private.factory_controls where enabled)
     or not exists (select 1 from rv_private.verification_control where enabled and auto_publish)
  then return '{"disabled":true}'::jsonb; end if;
  if not pg_try_advisory_xact_lock(741920630::bigint) then return '{"busy":true}'::jsonb; end if;
  for r in
    select x.*, s.publisher, s.url, pg.fetched_at
    from rv_private.aftermarket_assertions_v1 x
    join rv_private.aftermarket_source_pages_v1 pg
      on pg.source_id = x.source_id and pg.sha256 = x.page_sha256 and pg.review_state = 'reviewed'
    join rv_private.sources s
      on s.id = x.source_id and s.metadata->>'kind' = 'distributor_pdf'
     and s.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
    where x.status = 'staged' and x.relation = 'replaces' and x.oem_brand_basis = 'named_on_page'
      and x.hold_reason is null and x.aftermarket_number is not null and x.oem_number is not null
      and x.oem_brand is not null and x.aftermarket_maker is not null
    order by x.id limit 2000
  loop
    select * into o from rv_private.aftermarket_oem_match_v1(r.oem_brand, r.oem_number);
    select * into a from rv_private.aftermarket_oem_match_v1(r.aftermarket_maker, r.aftermarket_number);
    if o.outcome = 'ambiguous' or a.outcome = 'ambiguous' then
      update rv_private.aftermarket_assertions_v1 set status = 'held', hold_reason = 'number matches several published parts' where id = r.id;
      held := held + 1; continue;
    end if;
    if o.outcome is distinct from 'matched' or a.outcome is distinct from 'matched' then
      waiting := waiting + 1; continue;   -- seller-stated claims link existing parts only; retried next run
    end if;
    if o.part_id = a.part_id then
      update rv_private.aftermarket_assertions_v1 set status = 'held', hold_reason = 'both numbers are the same part' where id = r.id;
      held := held + 1; continue;
    end if;
    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page,
                                    position, quote, sha256, hash_kind, observed_at)
    values (r.source_id, r.row_key, r.page_sha256, r.url, (r.qualifiers->>'page')::int, coalesce(r.qualifiers->>'printed_page',''),
            r.row_key, r.row_text, r.page_sha256, 'sha256-pdf', r.fetched_at)
    on conflict (source_id, source_record_key, document_version) do nothing
    returning id into ev_id;
    if ev_id is null then
      select id into ev_id from rv_private.evidence
       where source_id = r.source_id and source_record_key = r.row_key and document_version = r.page_sha256;
    end if;
    select id into claim from rv_private.relationship_claims z
     where z.original_part_id = o.part_id and z.replacement_part_id = a.part_id
       and z.kind in ('third_party_compatibility','aftermarket_replacement','replacement','supersession')
       and z.state in ('seller_stated','verified') limit 1;
    if claim is null then
      insert into rv_private.relationship_claims(original_part_id, replacement_part_id, evidence_id, kind, authority, state,
                  restrictions, explicit_statement, verification_version)
      values (o.part_id, a.part_id, ev_id, 'third_party_compatibility', 'third_party', 'seller_stated',
        jsonb_build_object('tier','seller_stated_unverified','asserted_by', r.publisher, 'seller_url', r.url,
          'seller_role','distributor', 'oem_endorsement','none implied',
          'trust_label','Distributor-stated, not verified by either manufacturer',
          'statement_form', coalesce(r.qualifiers->>'statement_form', 'distributor catalogue cross reference'),
          'oem_brand_as_printed', r.oem_brand, 'oem_number_as_printed', r.oem_number,
          'replacement_brand_as_printed', r.aftermarket_maker, 'replacement_number_as_printed', r.aftermarket_number,
          'qualifiers', r.qualifiers, 'document_sha256', r.page_sha256, 'pdf_page', r.qualifiers->>'page', 'row', r.row_key,
          'equipment_fitment','not independently verified'),
        r.row_text, 'distributor-pdf-seller-stated-v1')
      returning id into claim;
      insert into rv_private.audit_events(action, part_id, reason)
      values ('automated_distributor_seller_stated_publish', o.part_id,
              r.publisher || ' catalogue: ' || r.oem_brand || ' ' || r.oem_number || ' -> ' || r.aftermarket_maker || ' '
              || r.aftermarket_number || ' (seller-stated, unverified); evidence ' || ev_id::text);
      published := published + 1;
    end if;
    update rv_private.aftermarket_assertions_v1 set status = 'published', claim_id = claim where id = r.id;
  end loop;
  return jsonb_build_object('seller_stated_claims', published, 'waiting_for_parts', waiting, 'held', held);
end;
$fn$;
revoke all on function rv_private.publish_distributor_pdf_v1() from public, anon, authenticated;

select cron.schedule('rv-distributor-pdf-v1', '7-57/10 * * * *', $$select rv_private.publish_distributor_pdf_v1()$$);

insert into rv_private.camper_input_change_log_v1(actor, change_category, reason, details, rollback_instructions)
values ('ClaudeL', 'replacement_volume',
  'Distributor catalogues count as a source (Larry, 27 Nov 2026: "yes")',
  jsonb_build_object('lane','distributor PDF cross references -> seller-stated tier (third_party_compatibility / seller_stated), existing parts only, exact number match',
                     'identities','distributor-printed maker numbers -> supplied-documents lane as attributed evidence for the maker''s part'),
  'See header of migration 20261127133000_distributor_pdf_seller_tier_v1.sql');
