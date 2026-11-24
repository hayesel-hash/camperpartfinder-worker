-- Manufacturer supersessions printed as "(USE nnnnnn)" in official parts-list
-- rows (Norcold: e.g. "691124 | AC HEATER (USE 639191)").
--
-- publish_explicit_observed_manufacturer_supersessions_v1 only accepts a
-- description that is exactly "Superseded by X". This sibling accepts the
-- "(USE X)" note anywhere in the row and keeps every safeguard of v1:
--   * official manufacturer catalogue, approved non-blocked source, completed
--     batch, document hash, evidence row at the same page/position;
--   * both parts published, non-variant, non-synthetic, same manufacturer;
--   * skipped if the old part already has a different verified successor,
--     or if the link would close a cycle (recursive reach check);
--   * directional supersession only; fitment and market are not inferred.
-- Older evidence rows quote only the part number, so the evidence anchor is
-- matched by document/page/position and either quote form; the "(USE X)"
-- wording comes from the stored observation of that same row and is kept
-- verbatim (including serial-range qualifiers) as explicit_statement.
-- Shares advisory lock 741920611 with v1 so supersession writers serialise.
-- Rollback: select cron.unschedule('rv-use-note-supersessions-v1');
--           drop function rv_private.publish_use_note_manufacturer_supersessions_v1();
--           delete from rv_private.relationship_claims where verification_version='manufacturer-explicit-use-note-v1';

create or replace function rv_private.publish_use_note_manufacturer_supersessions_v1()
 returns jsonb
 language plpgsql
 set search_path to 'pg_catalog'
as $function$
declare r record; inserted_count integer:=0; conflict_count integer:=0;
begin
 if not exists(select 1 from rv_private.factory_controls where enabled)
    or not exists(select 1 from rv_private.verification_control where enabled and auto_publish)
 then return '{"disabled":true}'::jsonb; end if;
 if not pg_try_advisory_xact_lock(741920611::bigint)
 then return '{"busy":true}'::jsonb; end if;
 for r in
  select distinct on (p.id,q.id)
   c.id cid,c.publisher,c.url,c.sha256,
   o.number old_num,
   substring(o.description from '(?i)\(\s*USE\s+([A-Z0-9./-]{4,20})\s*\)') new_num,
   o.page,o.position,o.description,
   e.id evidence_id,p.id op,q.id rp
  from rv_private.master_catalogue_observations o
  join rv_private.master_catalogues c
    on c.id=o.catalogue_id and c.sha256=o.sha256
   and c.state='ready' and c.authority='manufacturer'
  join rv_private.master_catalogue_batches b
    on b.catalogue_id=c.id and b.sha256=c.sha256
   and o.page between b.page_start and b.page_end
   and b.state='complete'
  join rv_private.sources s
    on s.url=c.url and s.publisher=c.publisher
   and s.metadata->>'kind'='manufacturer'
   and s.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
  join rv_private.evidence e
    on e.source_id=s.id and e.document_version=c.sha256 and e.sha256=c.sha256
   and e.pdf_page=o.page and e.position=o.position
   and (e.quote=o.number or e.quote=left(o.number||' | '||o.description,300))
  join rv_private.manufacturers m on m.name=c.publisher
  join rv_private.parts p
    on p.manufacturer_id=m.id and p.exact_number=o.number
   and p.variant='' and p.state='published' and p.synthetic=false
  join rv_private.parts q
    on q.manufacturer_id=m.id
   and q.exact_number=substring(o.description from '(?i)\(\s*USE\s+([A-Z0-9./-]{4,20})\s*\)')
   and q.variant='' and q.state='published' and q.synthetic=false
  where o.description ~* '\(\s*USE\s+[A-Z0-9./-]{4,20}\s*\)'
    and p.id<>q.id
    and o.number ~ '[0-9]'
    and substring(o.description from '(?i)\(\s*USE\s+([A-Z0-9./-]{4,20})\s*\)') ~ '[0-9]'
    and o.position ~ '^x[0-9]+ y[0-9]+( col[0-9]+)?$'
    and c.result->>'hash'=c.sha256
    and not exists(select 1 from rv_private.sources z where z.url=c.url and z.access_state='BLOCKED')
    and not exists (
       select 1 from rv_private.relationship_claims x
       where x.original_part_id=p.id and x.replacement_part_id=q.id
       and x.state='verified' and x.kind in ('replacement','supersession'))
  order by p.id,q.id,o.catalogue_id,o.page
  limit 400
 loop
   if exists (
      select 1 from rv_private.relationship_claims x
      where x.original_part_id=r.op and x.state='verified'
      and x.kind in ('replacement','supersession')
      and x.replacement_part_id<>r.rp
   ) or exists (
      with recursive reach(id) as (
       select r.rp
       union
       select x.replacement_part_id from reach z
         join rv_private.relationship_claims x on x.original_part_id=z.id
       where x.state='verified' and x.kind in ('replacement','supersession')
      )
      select 1 from reach where id=r.op
   ) then
      conflict_count:=conflict_count+1;
      continue;
   end if;
   insert into rv_private.relationship_claims
    (original_part_id,replacement_part_id,evidence_id,kind,authority,state,
     restrictions,explicit_statement,verification_version,verified_at)
   values
    (r.op,r.rp,r.evidence_id,'supersession','manufacturer','verified',
     jsonb_build_object(
       'scope','exact old part number superseded by exact new number',
       'statement_form','"(USE n)" note in an official manufacturer parts-list row',
       'manufacturer',r.publisher,
       'source_url',r.url,'source_pdf_page',r.page,
       'document_sha256',r.sha256,
       'equipment_fitment','not independently verified',
       'market','not established',
       'evidence_method','original official manufacturer catalogue text; exact same-row number and note'
     ),
     left(r.old_num||' | '||r.description,500),
     'manufacturer-explicit-use-note-v1',
     now())
   on conflict do nothing;
   if found then
     inserted_count:=inserted_count+1;
     insert into rv_private.audit_events(action,part_id,reason)
     values ('automated_supersession_publish',r.op,
       'Official manufacturer parts-list row "(USE n)" note; evidence '||r.evidence_id::text);
   end if;
 end loop;
 return jsonb_build_object('new_verified_supersessions',inserted_count,
                          'conflict_or_cycle_skipped',conflict_count);
end;
$function$;

select cron.schedule('rv-use-note-supersessions-v1','3-58/5 * * * *',
  'select rv_private.publish_use_note_manufacturer_supersessions_v1()');
