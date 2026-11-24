-- Two independently page-checked, existing Norcold manufacturer statements.
-- Catalogue publisher Norcold (Thetford official N7/N8 Polar parts list),
-- PDF physical page 7: old 639569 -> 693298, old 639570 -> 693299.
-- This is a manual evidence correction, not a new extractor batch.
do $fn$
declare inserted int;
begin
 if not exists(select 1 from rv_private.factory_controls where enabled)
 or not exists(select 1 from rv_private.verification_control where enabled and auto_publish)
 then raise exception 'publication disabled';end if;
 if (select count(*) from rv_private.parts p join rv_private.manufacturers m
       on m.id=p.manufacturer_id where m.name='Norcold' and p.state='published'
       and p.variant='' and p.synthetic=false
       and p.exact_number in ('639569','693298','639570','693299'))<>4
 then raise exception 'Norcold old/new part identities not uniquely published';end if;
 if not exists(
   select 1 from rv_private.master_catalogues c
   join rv_private.sources s on s.id=c.id and s.url=c.url
   where c.id='master-580aedc37afa5ed897d128ee65f32786'
   and c.publisher='Norcold' and c.authority='manufacturer' and c.state='ready'
   and c.result->>'hash'=c.sha256 and s.access_state='PUBLIC_FACTS'
   and s.metadata->>'kind'='manufacturer'
 ) then raise exception 'manufacturer source authority not established';end if;
 if (select count(*) from rv_private.master_catalogue_observations o
   where o.catalogue_id='master-580aedc37afa5ed897d128ee65f32786'
   and o.sha256='721025230cdddf24562ba8e8541e5fc7980271a8085d309de92aefab75e1b2af'
   and o.page=7 and (
      (o.number='639569' and o.description='SUPERSEDED BY 693298') or
      (o.number='639570' and o.description='SUPERSEDED BY 693299')))<>2
 then raise exception 'exact manufacturer source text missing';end if;
 if exists(
   select 1 from rv_private.relationship_claims r
   join rv_private.parts p on p.id=r.original_part_id
   join rv_private.manufacturers m on m.id=p.manufacturer_id
   where m.name='Norcold' and p.exact_number in ('639569','639570')
   and r.state='verified' and r.kind in ('supersession','replacement')
 ) then raise exception 'original already has verified successor; investigate';end if;
 insert into rv_private.evidence
  (source_id,source_record_key,document_version,url,pdf_page,printed_page,
   position,quote,sha256,hash_kind,observed_at)
 select 'master-580aedc37afa5ed897d128ee65f32786',
  'norcold-page7-supersession-'||o.number,
  o.sha256,c.url,o.page,'N7/N8 printed page 7',
  o.position,o.number||' '||o.description,o.sha256,'document-sha256',now()
 from rv_private.master_catalogue_observations o
 join rv_private.master_catalogues c on c.id=o.catalogue_id
 where o.catalogue_id='master-580aedc37afa5ed897d128ee65f32786'
 and o.page=7 and (
    (o.number='639569' and o.description='SUPERSEDED BY 693298') or
    (o.number='639570' and o.description='SUPERSEDED BY 693299'))
 on conflict(source_id,source_record_key,document_version) do nothing;
 insert into rv_private.relationship_claims
 (original_part_id,replacement_part_id,evidence_id,kind,authority,state,
 restrictions,explicit_statement,verification_version,verified_at)
 select p.id,n.id,e.id,'supersession','manufacturer','verified',
  jsonb_build_object('manufacturer','Norcold','source_type','official manufacturer parts list',
   'model_family','N7/N8 Polar','source_url',c.url,'pdf_page',o.page,
   'document_sha256',c.sha256,'fitment','not inferred',
   'scope','explicit directional manufacturer supersession'),
  o.number||' '||o.description,
  'official-manufacturer-exact-row-manual-20261124-v1',now()
 from rv_private.master_catalogue_observations o
 join rv_private.master_catalogues c on c.id=o.catalogue_id and c.sha256=o.sha256
 join rv_private.manufacturers m on m.name='Norcold'
 join rv_private.parts p on p.manufacturer_id=m.id and p.exact_number=o.number
 join rv_private.parts n on n.manufacturer_id=m.id and
  n.exact_number=substring(o.description from 'SUPERSEDED BY ([0-9]+)')
 join rv_private.evidence e on e.source_id=c.id
   and e.source_record_key='norcold-page7-supersession-'||o.number
   and e.document_version=c.sha256
 where o.catalogue_id='master-580aedc37afa5ed897d128ee65f32786'
 and o.page=7 and o.number in ('639569','639570')
 and p.state='published' and n.state='published'
 and p.variant='' and n.variant=''
 and p.synthetic=false and n.synthetic=false
 and o.description='SUPERSEDED BY '||n.exact_number
 on conflict do nothing;
 get diagnostics inserted=row_count;
 if inserted<>2 then raise exception 'expected exactly 2 verified new Norcold statements, inserted %',inserted;end if;
 insert into rv_private.camper_input_change_log_v1(actor,change_category,reason,details,rollback_instructions)
 values('ChatGPT','manual_manufacturer_supersession_publication',
 'Promote two exact Norcold manufacturer statements after confirming the PDF text, identities, and no conflicting links; no new extractor batch',
 jsonb_build_object('new_verified_edges',inserted,'manufacturer','Norcold',
 'source','https://www.thetford.com/app/uploads/2024/09/639735_PL_N7N8POLAR_082225.pdf',
 'pdf_page',7,'pairs',jsonb_build_array('639569 -> 693298','639570 -> 693299'),
 'verification_version','official-manufacturer-exact-row-manual-20261124-v1'),
 'If contradicted, move only these two claims to held following a documented review; preserve evidence/audit.');
end $fn$;
