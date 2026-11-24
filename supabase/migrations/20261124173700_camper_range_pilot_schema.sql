-- CamperMatch WO-1: full reproducible migration for isolated 3-page HTTP
-- Range pilot, based on live deployed definitions. Does not publish parts.
create table if not exists rv_private.camper_range_pilot_sources_v1(
 catalogue_id text primary key references rv_private.master_catalogues(id),
 next_page integer not null default 1 check(next_page>=1),
 state text not null default 'queued'
 check(state in ('queued','reading','done','blocked')),
 lease uuid,lease_until timestamptz,
 next_attempt timestamptz not null default now(),
 last_served_at timestamptz,last_error text,enabled boolean not null default false
);
create table if not exists rv_private.camper_range_pilot_pages_v1(
 catalogue_id text not null references rv_private.master_catalogues(id),
 catalogue_sha256 text not null,
 page integer not null check(page>=1),
 text_content text not null,
 positioned_items jsonb not null default '[]'::jsonb,
 fetched_at timestamptz not null default now(),
 sha256_independently_verified boolean not null default false,
 primary key(catalogue_id,catalogue_sha256,page)
);
create table if not exists rv_private.camper_range_pilot_events_v1(
 id bigint generated always as identity primary key,
 catalogue_id text not null,recorded_at timestamptz not null default now(),
 outcome text not null,pages integer not null default 0,
 error text,elapsed_ms integer
);
create index if not exists camper_range_pilot_events_time_v1
 on rv_private.camper_range_pilot_events_v1(recorded_at,catalogue_id);
revoke all on rv_private.camper_range_pilot_sources_v1,
 rv_private.camper_range_pilot_pages_v1,
 rv_private.camper_range_pilot_events_v1 from public,anon,authenticated;

CREATE OR REPLACE FUNCTION public.rv_range_pilot_claim_v1()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare r record;newlease uuid;
begin
 if not exists(select 1 from rv_private.factory_controls where enabled)
 then return null;end if;
 select s.*,c.url,c.publisher,c.pages,c.sha256,
        case when c.result->>'bytes' ~ '^[0-9]{1,12}$'
        then (c.result->>'bytes')::bigint else null end as expected_bytes
 into r
 from rv_private.camper_range_pilot_sources_v1 s
 join rv_private.master_catalogues c on c.id=s.catalogue_id
 where s.enabled and s.next_attempt<=now()
 and (s.state='queued' or (s.state='reading' and s.lease_until<now()))
 and c.state='ready' and c.pages>0 and c.sha256 is not null
 and s.next_page<=c.pages
 and rv_private.catalogue_eligible(c.url)
 and exists(select 1 from rv_private.sources so
  where so.url=c.url and so.publisher=c.publisher
  and so.access_state in ('PUBLIC_FACTS','DOCUMENT_PROCESSING_APPROVED','LICENSED_BULK')
  and so.metadata->>'kind'=c.authority)
 and not exists(select 1 from rv_private.sources blocked
  where blocked.url=c.url and blocked.access_state='BLOCKED')
 order by s.last_served_at asc nulls first,s.catalogue_id
 for update of s skip locked limit 1;
 if not found then return null;end if;
 newlease:=gen_random_uuid();
 update rv_private.camper_range_pilot_sources_v1 set lease=newlease,
  lease_until=now()+interval '6 minutes',state='reading',
  last_served_at=now(),last_error=null
 where catalogue_id=r.catalogue_id;
 return jsonb_build_object('catalogue_id',r.catalogue_id,'url',r.url,
 'sha256',r.sha256,'publisher',r.publisher,'from',r.next_page,
 'to',least(r.next_page+2,r.pages),'total_pages',r.pages,
 'expected_bytes',r.expected_bytes,'lease',newlease);
end $function$


CREATE OR REPLACE FUNCTION public.rv_range_pilot_stage_v1(p_catalogue_id text, p_lease uuid, p_rows jsonb, p_elapsed_ms integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare j record;c record;v jsonb;n int:=0;start_page int;last_page int;
begin
 select * into j from rv_private.camper_range_pilot_sources_v1
 where catalogue_id=p_catalogue_id and lease=p_lease and state='reading'
 and lease_until>now() for update;
 if not found then raise exception 'lease invalid or expired';end if;
 select * into c from rv_private.master_catalogues where id=p_catalogue_id;
 if c.state<>'ready' or c.sha256 is null then raise exception 'source no longer ready';end if;
 if jsonb_typeof(p_rows)<>'array' or jsonb_array_length(p_rows) not between 1 and 3
 then raise exception 'invalid page batch';end if;
 start_page:=j.next_page;
 last_page:=least(start_page+2,c.pages);
 if jsonb_array_length(p_rows)<>(last_page-start_page+1) then
  raise exception 'page batch incomplete';end if;
 for v in select value from jsonb_array_elements(p_rows) loop
  if (v->>'page')::integer not between start_page and last_page or
     coalesce(length(v->>'text'),0)>750000 or
     jsonb_typeof(v->'items')<>'array' or
     jsonb_array_length(v->'items')>20000
  then raise exception 'invalid raw page payload';end if;
  insert into rv_private.camper_range_pilot_pages_v1(
    catalogue_id,catalogue_sha256,page,text_content,positioned_items)
  values(p_catalogue_id,c.sha256,(v->>'page')::integer,
    coalesce(v->>'text',''),v->'items')
  on conflict(catalogue_id,catalogue_sha256,page) do nothing;
  n:=n+1;
 end loop;
 if (select count(distinct page) from rv_private.camper_range_pilot_pages_v1
  where catalogue_id=p_catalogue_id and catalogue_sha256=c.sha256
  and page between start_page and last_page)<(last_page-start_page+1)
 then raise exception 'missing persisted pages';end if;
 update rv_private.camper_range_pilot_sources_v1 set
 next_page=last_page+1,
 state=case when last_page>=c.pages then 'done' else 'queued' end,
 lease=null,lease_until=null,next_attempt=now(),last_error=null
 where catalogue_id=p_catalogue_id;
 insert into rv_private.camper_range_pilot_events_v1(
  catalogue_id,outcome,pages,elapsed_ms)
 values(p_catalogue_id,'complete',n,p_elapsed_ms);
 return jsonb_build_object('saved_pages',n,'next_page',last_page+1,
   'done',last_page>=c.pages,'sha256_verified',false);
end $function$


CREATE OR REPLACE FUNCTION public.rv_range_pilot_release_v1(p_catalogue_id text, p_lease uuid, p_error text, p_elapsed_ms integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare recent_count integer;
begin
 perform 1 from rv_private.camper_range_pilot_sources_v1 where
 catalogue_id=p_catalogue_id and lease=p_lease and state='reading' for update;
 if not found then return '{"lease_not_active":true}'::jsonb;end if;
 insert into rv_private.camper_range_pilot_events_v1(catalogue_id,outcome,error,elapsed_ms)
 values(p_catalogue_id,'failed',left(p_error,500),p_elapsed_ms);
 select count(*) into recent_count from rv_private.camper_range_pilot_events_v1
 where catalogue_id=p_catalogue_id and outcome='failed'
 and recorded_at>=now()-interval '20 minutes';
 update rv_private.camper_range_pilot_sources_v1 set
 state=case when recent_count>=6 then 'blocked' else 'queued' end,
 lease=null,lease_until=null,
 next_attempt=now()+make_interval(secs=>least(120,10*recent_count)),
 last_error=left(p_error,500)
 where catalogue_id=p_catalogue_id;
 return jsonb_build_object('failed_in_last_20m',recent_count,
 'blocked',recent_count>=6);
end $function$


revoke all on function public.rv_range_pilot_claim_v1(),
 public.rv_range_pilot_stage_v1(text,uuid,jsonb,integer),
 public.rv_range_pilot_release_v1(text,uuid,text,integer)
 from public,anon,authenticated;
grant execute on function public.rv_range_pilot_claim_v1(),
 public.rv_range_pilot_stage_v1(text,uuid,jsonb,integer),
 public.rv_range_pilot_release_v1(text,uuid,text,integer)
 to service_role;
