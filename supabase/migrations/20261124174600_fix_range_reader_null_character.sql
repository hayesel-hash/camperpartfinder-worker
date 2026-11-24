-- Fix: PostgreSQL chr(0) raises "null character not permitted".
-- Edge worker removes NUL from text before RPC and samples are held from publication.
create or replace function public.rv_range_pilot_stage_v1(
 p_catalogue_id text,p_lease uuid,p_rows jsonb,p_elapsed_ms integer)
returns jsonb language plpgsql security definer set search_path to 'pg_catalog' as $fn$
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
end $fn$;
revoke all on function public.rv_range_pilot_stage_v1(text,uuid,jsonb,integer)
 from public,anon,authenticated;
grant execute on function public.rv_range_pilot_stage_v1(text,uuid,jsonb,integer)
 to service_role;
