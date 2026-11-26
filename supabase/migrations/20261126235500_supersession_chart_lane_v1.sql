-- Supersession charts v1: a maker's own "previous part number -> replaced by" table, published
-- through the legacy-number-map lane (first used for Dexter/UFP renumbering). v2 of the publisher
-- reads the category, scope, note, part names and verification version from the reviewed document
-- and per-row qualifiers instead of the Dexter-specific constants, so any maker's chart can use it.
-- First document: Pentair SHURflo "RV Pump Conversion Chart" (Rev. 6-19-15), from the camper
-- catalogue handoff in Larry's Drive. Blue numbers are the aftermarket (retail) variants per the
-- chart's own note; that channel is kept per number. OEM -> aftermarket pairing between rows is
-- NOT inferred: only the printed "Previous Part Number -> Replaced by" rows become claims.

alter table rv_private.legacy_map_documents_v1
  add column if not exists category text,
  add column if not exists scope text,
  add column if not exists note text,
  add column if not exists part_name text,
  add column if not exists verification_version text;
alter table rv_private.legacy_number_map_v1
  add column if not exists qualifiers jsonb not null default '{}'::jsonb;

insert into rv_private.manufacturers(name) values ('SHURflo') on conflict (name) do nothing;

insert into rv_private.sources(id, publisher, url, access_state, metadata)
values ('shurflo-rv-pump-conversion-chart', 'Pentair (SHURflo)',
        'https://www.pentair.com/content/dam/extranet/spray-specialty/product-related/hypro_shurflo/shurflo/RV-Pump-Conversion-Chart.pdf',
        'PUBLIC_FACTS',
        jsonb_build_object('kind','manufacturer_supersession_chart','format','pdf',
          'scope','SHURflo RV Pump Conversion Chart, fresh water pumps: Previous Part Number -> Replaced by (Rev. 6-19-15)',
          'supplied_via','Larry''s Drive folder (ChatGPT handoff, 26 Nov 2026)','approvedBy','Larry, 26 Nov 2026 (blanket approval)'))
on conflict (id) do nothing;

create or replace function rv_private.publish_legacy_number_map_v2(doc text)
returns jsonb language plpgsql set search_path to 'pg_catalog' as $fn$
declare d record; s record; r record; cm uuid; lm uuid; cp uuid; lp uuid; ev uuid;
  new_parts int := 0; linked int := 0; claims int := 0; skipped int := 0; held int := 0;
begin
  select * into d from rv_private.legacy_map_documents_v1 where document_sha256 = doc and review_state = 'reviewed';
  if not found then return '{"error":"document not reviewed"}'::jsonb; end if;
  select * into s from rv_private.sources where id = d.source_id;
  for r in select * from rv_private.legacy_number_map_v1
            where document_sha256 = doc and status = 'staged' and coalesce(btrim(description),'') <> ''
            order by page, legacy_number, current_number
  loop
    select id into cm from rv_private.manufacturers where name = r.current_brand;
    select id into lm from rv_private.manufacturers where name = r.legacy_brand;
    if cm is null or lm is null then skipped := skipped + 1; continue; end if;
    insert into rv_private.evidence(source_id, source_record_key, document_version, url, pdf_page, printed_page, position, quote, sha256, hash_kind, observed_at)
    values (d.source_id, 'legacy-'||r.page||'-'||r.current_number||'-'||r.legacy_number, doc, s.url, r.page,
            coalesce(r.qualifiers->>'printed_page',''),
            'table row '||r.statement||' on page '||r.page, left(r.statement||' | '||r.description, 300), doc, 'sha256-pdf', now())
    on conflict (source_id, source_record_key, document_version) do nothing returning id into ev;
    if ev is null then
      select id into ev from rv_private.evidence where source_id = d.source_id
        and source_record_key = 'legacy-'||r.page||'-'||r.current_number||'-'||r.legacy_number and document_version = doc;
    end if;
    select id into cp from rv_private.parts where manufacturer_id = cm and exact_number = r.current_number and variant = '';
    if cp is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (cm, r.current_number, '', left(coalesce(r.qualifiers->>'current_name', d.part_name, r.description), 200),
              coalesce(d.category, 'running_gear'), 'published') returning id into cp;
      new_parts := new_parts + 1;
      insert into rv_private.audit_events(action, part_id, reason) values ('automated_legacy_map_identity_publish', cp, d.title||'; evidence '||ev::text);
    else linked := linked + 1; end if;
    select id into lp from rv_private.parts where manufacturer_id = lm and exact_number = r.legacy_number and variant = '';
    if lp is null then
      insert into rv_private.parts(manufacturer_id, exact_number, variant, name, category, state)
      values (lm, r.legacy_number, '', left(coalesce(r.qualifiers->>'legacy_name', d.part_name, r.description), 200),
              coalesce(d.category, 'running_gear'), 'published') returning id into lp;
      new_parts := new_parts + 1;
      insert into rv_private.audit_events(action, part_id, reason) values ('automated_legacy_map_identity_publish', lp, d.title||'; evidence '||ev::text);
    else linked := linked + 1; end if;
    insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (cp, ev, 'legacy-map-v2') on conflict do nothing;
    insert into rv_private.identity_evidence(part_id, evidence_id, reviewer) values (lp, ev, 'legacy-map-v2') on conflict do nothing;
    if exists (select 1 from rv_private.relationship_claims z where z.original_part_id = lp and z.state = 'verified'
                and z.kind in ('replacement','supersession') and z.replacement_part_id <> cp) then
      update rv_private.legacy_number_map_v1 set status = 'held', hold_reason = 'legacy part already has a different verified successor'
       where document_sha256 = doc and legacy_number = r.legacy_number and current_number = r.current_number;
      held := held + 1;
      continue;
    end if;
    if not exists (select 1 from rv_private.relationship_claims z where z.original_part_id = lp and z.replacement_part_id = cp
                    and z.kind = 'supersession' and z.state = 'verified') then
      insert into rv_private.relationship_claims(original_part_id, replacement_part_id, evidence_id, kind, authority, state, restrictions, explicit_statement, verification_version, verified_at)
      values (lp, cp, ev, 'supersession', 'manufacturer', 'verified',
        jsonb_build_object('scope', coalesce(d.scope, 'legacy_renumbering'),
                           'note', coalesce(d.note, 'Legacy '||r.legacy_brand||' number printed in brackets beside the current '||r.current_brand||' number; same product renumbered'),
                           'catalogue', d.title, 'printed_row', r.statement||' | '||r.description, 'qualifiers', r.qualifiers,
                           'equipment_fitment','not independently verified','market','not established for GB'),
        r.statement, coalesce(d.verification_version, 'manufacturer-pdf-two-pass-layout-and-visual-v1'), now());
      claims := claims + 1;
    end if;
    update rv_private.legacy_number_map_v1 set status = 'published'
     where document_sha256 = doc and legacy_number = r.legacy_number and current_number = r.current_number;
  end loop;
  return jsonb_build_object('new_parts', new_parts, 'existing_parts_evidenced', linked, 'claims', claims, 'held', held, 'skipped', skipped);
end;
$fn$;
revoke all on function rv_private.publish_legacy_number_map_v2(text) from public, anon, authenticated;
