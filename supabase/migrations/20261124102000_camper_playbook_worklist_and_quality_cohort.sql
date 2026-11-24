-- Snapshot of the playbook worklist migration deployed to Camper Supabase 2026-11-24.
create table if not exists rv_private.camper_input_worklist_v1(
 catalogue_id text primary key references rv_private.master_catalogues(id),
 slug text not null,title text not null,source_url text not null,
 publisher text not null,authority text not null,
 status text not null default 'need_source'
 check(status in ('need_source','reading','read','staged','promoted','blocked')),
 document_sha256 text,page_count integer,last_error text,
 auto_promote boolean not null default false,
 last_served_at timestamptz,last_checked_at timestamptz,
 updated_at timestamptz not null default now()
);
create index if not exists camper_input_worklist_status_idx
on rv_private.camper_input_worklist_v1(status,last_served_at);
create table if not exists rv_private.camper_input_quality_batch_v1(
 batch_label text primary key,publisher text not null,
 catalogue_id text not null references rv_private.master_catalogues(id),
 document_sha256 text not null,rule_version text not null,
 created_at timestamptz not null default now(),reviewer text,
 review_completed_at timestamptz,reviewed_rows integer not null default 0,
 accepted_rows integer not null default 0,decision text not null default 'unreviewed'
 check(decision in ('unreviewed','approved','rejected')),
 constraint batch_quality_approval check(
 decision <> 'approved' or
 (review_completed_at is not null and reviewed_rows >= 40
 and accepted_rows <= reviewed_rows and accepted_rows::numeric/reviewed_rows >= 0.90))
);
create table if not exists rv_private.camper_input_quality_sample_v1(
 batch_label text not null references rv_private.camper_input_quality_batch_v1(batch_label),
 catalogue_id text not null,document_sha256 text not null,page integer not null,
 position text not null,number text not null,proposed_name text,
 accepted boolean,review_note text,
 primary key(batch_label,catalogue_id,document_sha256,page,position,number)
);
create table if not exists rv_private.camper_input_change_log_v1(
 id bigint generated always as identity primary key,
 changed_at timestamptz not null default now(),
 actor text not null,change_category text not null,
 reason text not null,details jsonb not null default '{}'::jsonb,
 rollback_instructions text not null
);
revoke all on rv_private.camper_input_worklist_v1,
rv_private.camper_input_quality_batch_v1,rv_private.camper_input_quality_sample_v1,
rv_private.camper_input_change_log_v1 from public,anon,authenticated;

CREATE OR REPLACE FUNCTION rv_private.camper_sync_input_worklist_v1()
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare inserted_count integer; updated_count integer;
begin
 if not pg_try_advisory_xact_lock(741920974::bigint) then
   return '{"busy":true}'::jsonb;
 end if;
 with source as (
  select c.id,c.publisher,c.authority,c.url,c.sha256,c.pages,c.state,c.result,
  count(b.page_start) filter (where b.state='complete') completed,
  count(b.page_start) filter (where b.state in ('queued','retry','leased')) unfinished,
  count(b.page_start) filter (where b.state='held') held_count,
  (select count(*) from rv_private.master_catalogue_observations o
   where o.catalogue_id=c.id and o.sha256=c.sha256 and o.state='staged') staged_count
  from rv_private.master_catalogues c
  left join rv_private.master_catalogue_batches b on b.catalogue_id=c.id and b.sha256=c.sha256
  group by c.id
 )
 insert into rv_private.camper_input_worklist_v1(
  catalogue_id,slug,title,source_url,publisher,authority,status,
  document_sha256,page_count,last_error,last_checked_at
 )
 select id,id,left(publisher||' - '||coalesce(nullif(split_part(url,'/',array_length(string_to_array(url,'/'),1)),''),id),400),
   url,publisher,authority,
   case when state='held' then 'blocked'
        when sha256 is null then 'need_source'
        when unfinished>0 then 'reading'
        when staged_count>0 then 'staged'
        when completed>0 and held_count=0 then 'read'
        when held_count>0 then 'blocked'
        else 'reading' end,
   sha256,pages,coalesce(result->>'error',null),now()
 from source
 on conflict (catalogue_id) do update
 set title=excluded.title,
     source_url=excluded.source_url,
     publisher=excluded.publisher,
     authority=excluded.authority,
     status=case when rv_private.camper_input_worklist_v1.status='promoted'
                  then 'promoted' else excluded.status end,
     document_sha256=excluded.document_sha256,
     page_count=excluded.page_count,
     last_error=excluded.last_error,
     last_checked_at=now(),updated_at=now();
 get diagnostics inserted_count=row_count;
 return jsonb_build_object('synchronised_catalogues',inserted_count);
end $function$
;
revoke all on function rv_private.camper_sync_input_worklist_v1() from public,anon,authenticated;
select cron.schedule('rv-playbook-worklist-sync-v1','*/5 * * * *','select rv_private.camper_sync_input_worklist_v1()');
