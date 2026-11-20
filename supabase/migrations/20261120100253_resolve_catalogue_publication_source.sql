CREATE OR REPLACE FUNCTION rv_private.publish_generic_master_identities()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare r record;mid uuid;pid uuid;eid uuid;n int:=0;k int:=0;cat text;
begin
if not exists(select 1 from rv_private.factory_controls where enabled) or not exists(select 1 from rv_private.verification_control where enabled and auto_publish) then return '{"disabled":true}'::jsonb;end if;
if not pg_try_advisory_xact_lock(741920612::bigint) then return '{"busy":true}'::jsonb;end if;
for r in select distinct on(c.publisher,o.number) c.publisher,c.id cid,src.id source_id,c.url,o.sha256,o.page,o.position,o.number,o.description
from rv_private.master_catalogue_observations o join rv_private.master_catalogues c on c.id=o.catalogue_id and c.sha256=o.sha256
join lateral (
    select s.id from rv_private.sources s
    where s.url=c.url and s.publisher=c.publisher and s.metadata->>'kind'='manufacturer'
      and s.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
      and not exists (
        select 1 from rv_private.sources z where z.url=c.url
          and (z.access_state='BLOCKED' or (z.metadata->>'kind'='manufacturer' and z.publisher<>c.publisher))
      )
    order by (s.id=c.id) desc,s.id limit 1
) src on true
join rv_private.master_catalogue_batches b on b.catalogue_id=c.id and b.sha256=o.sha256 and o.page between b.page_start and b.page_end and b.state='complete'
where c.authority='manufacturer' and c.adapter in ('generic-table-v1','suburban-kit-v2','coleman-stock-v2','adaptive-table-v3') and c.result->>'hash'=o.sha256 and o.state='staged' and o.extraction_method='labelled-column-v1'
and o.number ~ '^[A-Z0-9][A-Z0-9.-]{3,24}$' and o.number ~ '[0-9]' and o.description ~ '[A-Za-z]{3}' and o.position ~ '^x[0-9]+ y[0-9]+ col[0-9]+$'
and (c.result->>'engine'='pymupdf' or exists(select 1 from rv_private.fallback_attempts_v2 f where f.catalogue_id=c.id and f.sha256=c.sha256 and f.page_start=b.page_start and f.parser_version='edge-layout-v3' and f.outcome='complete' and f.details->>'hash'=c.sha256 and b.result->>'engine'='edge-layout-v3')) and c.url like 'https://%' and rv_private.catalogue_eligible(c.url)
order by c.publisher,o.number,o.page,o.position limit 5000 loop
cat:=case when r.url ilike '%refrigerator%' then 'refrigeration' when r.url ilike '%toilet%' or r.url ilike '%sanitation%' or (r.publisher='Thetford' and r.url ~* 'portapotti|campa.?potti|cassette|separation.toilet') then 'sanitation' when r.publisher in ('Truma','Suburban','Coleman-Mach') then 'heating' else 'external_equipment' end;
select id into mid from rv_private.manufacturers where name=r.publisher order by id limit 1;
if mid is null then insert into rv_private.manufacturers(name) values(r.publisher) returning id into mid;end if;
if exists(select 1 from rv_private.parts where manufacturer_id=mid and exact_number=r.number and (state<>'published' or variant<>'' or synthetic)) then continue;end if;
pid:=null;eid:=null;
insert into rv_private.parts(manufacturer_id,exact_number,name,category,state) values(mid,r.number,r.description,cat,'published') on conflict(manufacturer_id,exact_number,variant) do nothing returning id into pid;
if pid is not null then n:=n+1;insert into rv_private.audit_events(action,part_id,reason) values('automated_identity_publish',pid,'Official manufacturer labelled spare-parts table');else select id into strict pid from rv_private.parts where manufacturer_id=mid and exact_number=r.number and variant='';end if;
insert into rv_private.evidence(source_id,source_record_key,document_version,url,pdf_page,printed_page,position,quote,sha256,hash_kind,observed_at) values(r.source_id,'page'||r.page||'-'||r.position||'-'||r.number,r.sha256,r.url,r.page,'unknown',r.position,left(r.number||' | '||r.description,300),r.sha256,'document-sha256',now()) on conflict(source_id,source_record_key,document_version) do nothing returning id into eid;
if eid is null then select id into strict eid from rv_private.evidence where source_id=r.source_id and source_record_key='page'||r.page||'-'||r.position||'-'||r.number and document_version=r.sha256;end if;
insert into rv_private.identity_evidence(part_id,evidence_id,reviewer) values(pid,eid,'manufacturer-labelled-column-v1') on conflict do nothing;
update rv_private.master_catalogue_observations set state='published' where catalogue_id=r.cid and sha256=r.sha256 and number=r.number and state='staged';k:=k+1;
end loop;
return jsonb_build_object('new_parts',n,'linked',k);end$function$;
